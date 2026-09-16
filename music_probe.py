"""Find a drive level at which an odour is an odour and not an avalanche.

The plan for the music-learning loop needs three things to be true in this model:
Kenyon cells must fire when an olfactory receptor class is driven, mushroom body
output neurons must respond, and two different receptor classes must produce
different output patterns. The first run at 100 Hz produced the same global
avalanche the sensory screen found — 8,288 neurons active, two thirds of all
Kenyon cells — so this version sweeps the drive instead of assuming one.

Input is a PoissonGroup with per-cell rates that can be changed between runs,
rather than the model's own PoissonInput whose rate is fixed at construction.
Weight and target variable are the model's: v += w_syn * f_poi.

    .venv-brain/bin/python music_probe.py --label music-probe-v2 --rates 5 10 20 40
"""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import brian2 as b
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
BRAIN = ROOT / "vendor" / "Drosophila_brain_model"
ANN = ROOT / "vendor" / "flywire_annotations" / "supplemental_files" / "Supplemental_file1_neuron_annotations.tsv"
sys.path.insert(0, str(BRAIN))
import model  # noqa: E402
from brain_loop import shuffled_connectivity  # noqa: E402

ODOURS = ["ORN_DM1", "ORN_DM2", "ORN_DL5", "ORN_VA2"]   # overridden by --odours
NETWORK_SEED = 20000


def groups(ann, mapping):
    ct = ann.cell_type.astype(str)
    sets = {
        "KC": ann.loc[ct.str.startswith("KC"), "root_id"],
        "MBON": ann.loc[ct.str.startswith("MBON"), "root_id"],
        "DAN": ann.loc[ct.str.match(r"^(PAM|PPL1)"), "root_id"],
        "DN": ann.loc[ann.super_class == "descending", "root_id"],
    }
    return {name: np.array(sorted(mapping[int(r)] for r in ids if int(r) in mapping)) for name, ids in sets.items()}


def cosine(a, c):
    a, c = np.array(a, float), np.array(c, float)
    if not a.any() or not c.any():
        return None
    return round(float(a @ c / (np.linalg.norm(a) * np.linalg.norm(c))), 3)


def main(args):
    global ODOURS
    if args.odours:
        ODOURS = args.odours
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    ann = pd.read_csv(ANN, sep="\t", low_memory=False)
    ann["root_id"] = ann["root_id"].astype("int64")
    comp, con = BRAIN / "Completeness_783.csv", BRAIN / "Connectivity_783.parquet"
    index = pd.read_csv(comp, index_col=0).index
    mapping = {int(v): i for i, v in enumerate(index)}
    marks = groups(ann, mapping)

    ct = ann.cell_type.astype(str)
    cells, spans = [], {}
    for odour in ODOURS:
        present = [mapping[int(r)] for r in ann.loc[ct == odour, "root_id"] if int(r) in mapping]
        assert len(present) >= 20, f"{odour}: only {len(present)} cells in the model"
        spans[odour] = (len(cells), len(cells) + len(present))
        cells += present

    b.start_scope()
    b.defaultclock.dt = .1 * b.ms
    b.seed(NETWORK_SEED)
    params = model.default_params.copy()
    source = con if args.shuffle_seed is None else shuffled_connectivity(con, args.shuffle_seed)
    neu, syn, monitor = model.create_model(comp, source, params)
    neu.rfc[np.array(cells)] = 0 * b.ms                      # as model.poi does for driven cells
    drive = b.PoissonGroup(len(cells), rates=0 * b.Hz, name="odour_drive")
    feed = b.Synapses(drive, neu, "w_in : volt", on_pre="v_post += w_in", name="odour_feed")
    feed.connect(i=np.arange(len(cells)), j=np.array(cells))
    feed.w_in = params["w_syn"] * params["f_poi"]
    net = b.Network(neu, syn, monitor, drive, feed)
    net.store("rest")

    results = {}
    if args.wsyn:
        sweep = [("wsyn", v) for v in args.wsyn]
    elif args.mv:
        sweep = [("mV", v) for v in args.mv]
    else:
        sweep = [("Hz", v) for v in args.rates]
    baseline_w = np.asarray(syn.w[:]).copy()
    for kind, level in sweep:
        hz = level if kind == "Hz" else args.hz
        for odour, trial in [(o, t) for o in ODOURS for t in range(args.trials)]:
            net.restore("rest")
            b.seed(NETWORK_SEED + 101 * (trial + 1))
            before = np.asarray(monitor.count[:]).copy()
            lo, hi = spans[odour]
            drive.rates = 0 * b.Hz
            drive.rates[lo:hi] = hz * b.Hz
            if kind == "mV":
                feed.w_in = level * b.mV
            if kind == "wsyn":
                syn.w[:] = (baseline_w * (level / float(params["w_syn"] / b.volt) / 1000.)) * b.volt
            start = time.monotonic()
            net.run(args.ms * b.ms)
            counts = np.asarray(monitor.count[:]) - before
            row = {"hz": hz, "mv": (level if kind == "mV" else float(params["w_syn"] * params["f_poi"] / b.mV)), "odour": odour, "wall_s": round(time.monotonic() - start, 1),
                   "spikes_total": int(counts.sum()), "active_neurons": int((counts > 0).sum()),
                   **{f"{name}_spikes": int(counts[idx].sum()) for name, idx in marks.items()},
                   **{f"{name}_active": int((counts[idx] > 0).sum()) for name, idx in marks.items()},
                   "KC_fraction": round(float((counts[marks["KC"]] > 0).mean()), 3),
                   "MBON_vector": counts[marks["MBON"]].tolist(),
                   "KC_vector": counts[marks["KC"]].tolist() if args.keep_kc else None}
            row["trial"] = trial
            results[f"{level}:{odour}:{trial}"] = row
            print(f"{level:>6.2f} {kind} {odour} t{trial}: {row['spikes_total']:>7} spikes, {row['active_neurons']:>5} neurons, "
                  f"KC {row['KC_active']:>4} ({row['KC_fraction']:.0%}), MBON {row['MBON_active']:>3} cells / {row['MBON_spikes']:>5} spikes, "
                  f"DN {row['DN_spikes']:>5}", flush=True)
        def vec(o, t, key="MBON_vector"):
            return results[f"{level}:{o}:{t}"][key]
        pairs = {f"{x}|{y}": cosine(vec(x, 0), vec(y, 0)) for i, x in enumerate(ODOURS) for y in ODOURS[i + 1:]}
        if args.trials > 1:
            for key in ("MBON_vector", "KC_vector") if args.keep_kc else ("MBON_vector",):
                within = [cosine(vec(o, t, key), vec(o, u, key)) for o in ODOURS
                          for t in range(args.trials) for u in range(t + 1, args.trials)]
                between = [cosine(vec(x, t, key), vec(y, u, key)) for i, x in enumerate(ODOURS) for y in ODOURS[i + 1:]
                           for t in range(args.trials) for u in range(args.trials)]
                within = [c for c in within if c is not None]
                between = [c for c in between if c is not None]
                if within and between:
                    print(f"       {key}: same odour, different input seed {np.mean(within):.4f}; "
                          f"different odours {np.mean(between):.4f}; identity margin {np.mean(within) - np.mean(between):+.4f}", flush=True)
                    results[f"{level}:{key}:within"] = round(float(np.mean(within)), 4)
                    results[f"{level}:{key}:between"] = round(float(np.mean(between)), 4)
        shown = ", ".join("{}/{} {}".format(k.split("|")[0][4:], k.split("|")[1][4:], v) for k, v in pairs.items())
        print(f"       MBON pattern similarity at {level:g} {kind} (1.0 = the same odour to the fly): {shown}", flush=True)
        results[f"{level}:cosine"] = pairs

    (out / "summary.json").write_text(json.dumps(
        {"rates": args.rates, "ms": args.ms, "network_seed": NETWORK_SEED, "shuffle_seed": args.shuffle_seed,
         "hz": args.hz, "odours": ODOURS, "trials": args.trials,
         "n_cells": {o: spans[o][1] - spans[o][0] for o in ODOURS},
         "group_sizes": {k: int(len(v)) for k, v in marks.items()},
         "annotation_sha256": hashlib.sha256(ANN.read_bytes()).hexdigest(),
         "results": results}, indent=1))
    print("saved", out / "summary.json")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--rates", type=float, nargs="+", default=[5, 10, 20, 40])
    p.add_argument("--mv", type=float, nargs="+", default=None,
                   help="sweep the injected millivolts per input event instead of the rate; "
                        "the model's own value is w_syn*f_poi = 68.75 mV, which fires any cell instantly")
    p.add_argument("--ms", type=float, default=300.)
    p.add_argument("--trials", type=int, default=1,
                   help="repeat every condition with a different input seed, to separate "
                        "within-odour variation from between-odour difference")
    p.add_argument("--shuffle-seed", type=int, default=None,
                   help="degree-preserving shuffle of the connectome: the control that says whether "
                        "the identity we measure comes from the wiring or only from the input fan-out")
    p.add_argument("--odours", nargs="+", default=None, help="olfactory receptor classes to compare")
    p.add_argument("--keep-kc", action="store_true", help="also store the Kenyon cell response vector")
    p.add_argument("--hz", type=float, default=10., help="rate used when sweeping millivolts")
    p.add_argument("--wsyn", type=float, nargs="+", default=None,
                   help="sweep the model's own weight per synapse in mV (published value 0.275); "
                        "this changes the network, not the stimulus, so it is a different model and must be labelled one")
    main(p.parse_args())
