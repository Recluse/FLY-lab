"""Independent neural gates; never writes body commands."""
import argparse
import csv
import gc
import hashlib
import json
import resource
import subprocess
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import brian2 as b
from experiment import ROOT, BRAIN, save, manifest, notebook_assignment
sys.path.insert(0, str(BRAIN))
import model


def audit(out):
    comp = pd.read_csv(BRAIN / "Completeness_783.csv", index_col=0).index.to_numpy()
    con = pd.read_parquet(BRAIN / "Connectivity_783.parquet")
    pre = con.Presynaptic_Index.to_numpy()
    post = con.Postsynaptic_Index.to_numpy()
    weight = con["Excitatory x Connectivity"].to_numpy()
    assert np.array_equal(comp[pre], con.Presynaptic_ID.to_numpy())
    assert np.array_equal(comp[post], con.Postsynaptic_ID.to_numpy())
    assert np.isfinite(weight).all()
    assert np.array_equal(weight, con.Connectivity.to_numpy()*con.Excitatory.to_numpy())
    mapping = {int(v): i for i,v in enumerate(comp)}
    targets = {"DNa01L":720575940627787609, "DNa01R":720575940644438551, "DNa02L":720575940629327659, "DNa02R":720575940604737708}
    result = {"edges_checked":len(con), "all_indices_and_weights_valid":True, "sides":{}}
    for side in ("left", "right"):
        folder = ROOT / "results" / f"brain783-{side}-0"
        inputs = json.loads((folder / "sensory_ids.json").read_text())["rows"]
        reached = np.zeros(len(comp), dtype=bool)
        reached[[mapping[int(r["root_id"])] for r in inputs]] = True
        hops = {}
        for hop in range(1, 9):
            reached[post[reached[pre] & (weight > 0)]] = True
            for name, ident in targets.items():
                if reached[mapping[ident]] and name not in hops:
                    hops[name] = hop
            if len(hops) == len(targets):
                break
        spikes = pd.read_parquet(folder / "spikes.parquet")
        counts = spikes.groupby("flywire_id").size().reindex(comp, fill_value=0).to_numpy()
        drive = {}
        for name,ident in targets.items():
            mask = post == mapping[ident]
            w = weight[mask]
            events = counts[pre[mask]]
            drive[name] = {"excitatory_weight_times_spikes":int((w[w>0]*events[w>0]).sum()), "inhibitory_weight_times_spikes":int((w[w<0]*events[w<0]).sum()), "active_presynaptic_neurons":int(len(np.unique(pre[mask][events>0])))}
        result["sides"][side] = {"positive_path_hops_up_to_8":hops, "aggregate_presynaptic_events":drive}
    result["limitation"] = "Structural reachability and aggregate signed synapse-count times spikes do not imply threshold crossing; temporal order and conductance decay are not represented by this aggregate."
    save(out / "summary.json", result)
    print(json.dumps(result), flush=True)


def run(args):
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    save(out / "manifest.json", manifest())
    if args.mode == "audit":
        audit(out)
        return
    b.start_scope()
    b.defaultclock.dt = .1 * b.ms
    b.seed(args.seed)
    params = model.default_params.copy()
    params["r_poi"] = args.hz * b.Hz
    if args.mode == "stream":
        comp = BRAIN / "2023_03_23_completeness_630_final.csv"
        con = BRAIN / "2023_03_23_connectivity_630_final.parquet"
        inputs = notebook_assignment("example.ipynb", "neu_sugar")
    else:
        comp = BRAIN / "Completeness_783.csv"
        con = BRAIN / "Connectivity_783.parquet"
        repo = ROOT / "vendor/flywire_annotations"
        table = repo / "supplemental_files/Supplemental_file1_neuron_annotations.tsv"
        rows = list(csv.DictReader(table.open(), delimiter="\t"))
        selected = [r for r in rows if r["cell_class"] == "gustatory" and r["cell_sub_class"] == "sugar/water" and (r["side"] == args.side or args.side == "both")]
        inputs = [int(r["root_id"]) for r in selected]
        save(out / "sensory_ids.json", {"materialization": 783, "selection": "all gustatory sugar/water cells; side is nerve-entry side", "annotation_commit": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(), "annotation_sha256": hashlib.sha256(table.read_bytes()).hexdigest(), "rows": selected})
    index = pd.read_csv(comp, index_col=0).index
    mapping = {int(v): i for i, v in enumerate(index)}
    missing = [str(v) for v in inputs if v not in mapping]
    if missing:
        save(out / "blocked.json", {"reason": "verified sensory IDs absent from model completeness", "missing": missing})
        raise ValueError(f"Missing {len(missing)} IDs; refusing silent exclusion")
    neu, syn, monitor = model.create_model(comp, con, params)
    pois, neu = model.poi(neu, [mapping[v] for v in inputs], [], params)
    net = b.Network(neu, syn, monitor, *pois)
    outputs = {"DNa01L":720575940627787609, "DNa01R":720575940644438551, "DNa02L":720575940629327659, "DNa02R":720575940604737708, "MN9":720575940660219265}
    start = time.monotonic()
    if args.mode == "stream":
        net.store("initial")
        net.run(1005 * b.ms)
        expected = [monitor.i[:].copy(), np.asarray(monitor.t[:]).copy(), np.asarray(neu.v[:]).copy(), np.asarray(neu.g[:]).copy()]
        net.restore("initial", restore_random_state=True)
        for tick in range(67):
            net.run(15 * b.ms)
            assert abs(float(net.t / b.second) - (tick + 1) * .015) < 1e-12
        actual = [monitor.i[:], np.asarray(monitor.t[:]), np.asarray(neu.v[:]), np.asarray(neu.g[:])]
        equal = [np.array_equal(x, y) for x, y in zip(expected, actual)]
        save(out / "summary.json", {"mode": "whole vs 67 x 15ms", "seed": args.seed, "spike_indices_equal": equal[0], "spike_times_equal": equal[1], "potentials_equal": equal[2], "synaptic_state_equal": equal[3], "spikes": len(monitor.i), "wall_s": time.monotonic()-start})
        assert all(equal), "Streaming changed model dynamics"
    else:
        assert all(v in mapping for v in outputs.values())
        trace = b.StateMonitor(neu, ["v", "g"], record=[mapping[v] for v in outputs.values()])
        net.add(trace)
        if args.mode == "pulse783":
            ticks = []
            previous = np.zeros(len(outputs), dtype=int)
            for tick in range(60):
                active = 20 <= tick < 40
                for source in pois:
                    source.active = active
                net.run(15 * b.ms)
                assert abs(float(net.t / b.second)-(tick+1)*.015) < 1e-12
                counts_now = np.array([monitor.count[mapping[v]] for v in outputs.values()])
                ticks.append({"t_end_s":(tick+1)*.015, "input_active":active,
                              "new_output_spikes":dict(zip(outputs, (counts_now-previous).tolist()))})
                previous = counts_now
            save(out / "ticks.json", ticks)
        else:
            net.run(1000 * b.ms)
        duration = float(net.t / b.second)
        assert np.isfinite(neu.v[:]).all() and np.isfinite(neu.g[:]).all()
        np.savez_compressed(out / "output_states.npz", time_s=np.asarray(trace.t/b.second),
                            voltage_mV=np.asarray(trace.v/b.mV), g_mV=np.asarray(trace.g/b.mV), names=list(outputs))
        state_stats = {name:{"max_voltage_mV":float(np.max(trace.v[i]/b.mV)), "min_voltage_mV":float(np.min(trace.v[i]/b.mV))} for i,name in enumerate(outputs)}
        rates = {k: int(monitor.count[mapping[v]])/duration for k,v in outputs.items()}
        counts = np.asarray(monitor.count[:])
        row = {"materialization":783, "mode":args.mode, "seed":args.seed, "input_side":args.side, "input_hz":args.hz, "n_inputs":len(inputs), "duration_s":duration, "output_hz":rates, "output_states":state_stats, "spikes":int(counts.sum()), "active_neurons":int((counts>0).sum()), "wall_s":time.monotonic()-start, "peak_rss_bytes":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
        save(out / "summary.json", row)
        model.construct_dataframe([model.get_spk_trn(monitor)], "probe783", dict(enumerate(index))).to_parquet(out / "spikes.parquet", index=False)
        print(json.dumps(row), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["stream", "sensory783", "pulse783", "audit"])
    p.add_argument("--label", required=True)
    p.add_argument("--side", choices=["left","right","both"], default="left")
    p.add_argument("--hz", type=float, default=150)
    p.add_argument("--seed", type=int, default=0)
    a=p.parse_args()
    if Path(a.label).name != a.label or a.label in {".",".."} or not np.isfinite(a.hz) or not 0 <= a.hz <= 1000:
        p.error("invalid label or rate")
    run(a)
