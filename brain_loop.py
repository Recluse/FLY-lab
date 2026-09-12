"""Brain half of variant C/E: head-bristle L/R Poisson inputs driven by pilot events, per-tick descending counts.

No body here: the pilot stimulus is external and independent of the body, so the brain pass for an
episode can be computed once and consumed by experiment.py (policy C). Same 15 ms tick order as the
protocol: sensors at tick start -> network advances 15 ms -> new spikes -> command for that tick.
"""
import argparse
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
from experiment import ROOT, BRAIN, save, manifest
from pilot import events_for
sys.path.insert(0, str(BRAIN))
import model

ANN = ROOT / "vendor/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
OUTPUTS = {"DNa01L": 720575940627787609, "DNa01R": 720575940644438551, "DNa02L": 720575940629327659, "DNa02R": 720575940604737708}
NETWORK_SEED_BASE = 10000  # network seed = 10000 + episode seed: separate from event RNG, body seeds and shuffle seeds 4000..4004


def shuffle_edges(pre, post, weight, rng, rounds=10):
    """Directed double-edge swaps within each sign class, vectorised in batches: for edges (a->b), (c->d) pick
    (a->d), (c->b). Rejected: self-loops, swaps sharing a node, results that duplicate an existing edge, and
    batch-internal collisions. Preserves exactly: every node's out-degree and in-degree per sign, and the global
    multiset of weights (each weight stays with its presynaptic edge). Not preserved: which weights arrive at a node.
    Returns new arrays and the fraction of edges whose (pre, post) changed."""
    pre, post, weight = pre.copy(), post.copy(), weight.copy()
    n_nodes = int(max(pre.max(), post.max())) + 1
    key = lambda p, q: p.astype(np.int64) * n_nodes + q.astype(np.int64)
    original = key(pre, post)
    existing = set(original.tolist())  # all signs: a swapped edge must not coincide with any existing pair
    for sign in (1, -1):
        idx = np.flatnonzero(np.sign(weight) == sign)
        for _ in range(rounds):
            perm = rng.permutation(len(idx))
            half = len(perm) // 2
            ia, ic = idx[perm[:half]], idx[perm[half:2 * half]]  # disjoint edge pairs within the batch
            pa, qa, pc, qc = pre[ia], post[ia], pre[ic], post[ic]
            ok = (pa != pc) & (qa != qc) & (pa != qc) & (pc != qa)
            new1, new2 = key(pa, qc), key(pc, qa)
            current = np.fromiter(existing, dtype=np.int64, count=len(existing))
            ok &= ~np.isin(new1, current) & ~np.isin(new2, current)
            both = np.concatenate([new1[ok], new2[ok]])
            _, inverse, counts = np.unique(both, return_inverse=True, return_counts=True)
            dup = counts[inverse] > 1  # any key appearing twice inside the batch: reject all swaps involved
            m = ok.sum()
            bad = dup[:m] | dup[m:]
            sel = np.flatnonzero(ok)[~bad]
            for k in key(pa[sel], qa[sel]).tolist() + key(pc[sel], qc[sel]).tolist():
                existing.discard(k)
            existing.update(new1[sel].tolist()); existing.update(new2[sel].tolist())
            post[ia[sel]], post[ic[sel]] = qc[sel], qa[sel]
    changed = float(np.mean(key(pre, post) != original))
    return pre, post, weight, changed


def selfcheck():
    """Shuffle invariants on a synthetic graph: degrees per sign, weight multiset, no self-loops, no duplicate pairs."""
    rng = np.random.default_rng(0)
    n, m = 2000, 40000
    pre, post, w = rng.integers(0, n, m), rng.integers(0, n, m), rng.choice([-1., 1., 2., -3.], m)
    keep = pre != post
    pre, post, w = pre[keep], post[keep], w[keep]
    u = np.unique(pre.astype(np.int64) * n + post, return_index=True)[1]
    pre, post, w = pre[u], post[u], w[u]
    p2, q2, w2, changed = shuffle_edges(pre, post, w, np.random.default_rng(1))
    for sign in (1, -1):
        a, b_ = np.sign(w) == sign, np.sign(w2) == sign
        assert np.array_equal(np.bincount(pre[a], minlength=n), np.bincount(p2[b_], minlength=n)), "out-degree per sign"
        assert np.array_equal(np.bincount(post[a], minlength=n), np.bincount(q2[b_], minlength=n)), "in-degree per sign"
    assert np.array_equal(np.sort(w), np.sort(w2)), "weight multiset"
    assert (p2 != q2).all(), "self loops"
    assert len(np.unique(p2.astype(np.int64) * n + q2)) == len(p2), "duplicate pairs"
    assert changed > .9, "shuffle barely changed the graph"
    print(f"brain_loop selfcheck passed; changed fraction {changed:.3f}")


def shuffled_connectivity(con, shuffle_seed):
    """Shuffle the v783 connectivity once per seed and cache it; every E episode with this seed reuses the file."""
    target = ROOT / "results" / f"shuffled-connectivity-{shuffle_seed}.parquet"
    if target.exists():
        return target
    df = pd.read_parquet(con)
    pre, post, w, changed = shuffle_edges(df.Presynaptic_Index.to_numpy(), df.Postsynaptic_Index.to_numpy(), df["Excitatory x Connectivity"].to_numpy(), np.random.default_rng(shuffle_seed))
    out = pd.DataFrame({"Presynaptic_Index": pre, "Postsynaptic_Index": post, "Excitatory x Connectivity": w})
    assert not out.duplicated(["Presynaptic_Index", "Postsynaptic_Index"]).any() and (pre != post).all()
    for sign in (1, -1):
        a, b_ = np.sign(df["Excitatory x Connectivity"].to_numpy()) == sign, np.sign(w) == sign
        n = len(pd.read_csv(BRAIN / "Completeness_783.csv", index_col=0))
        assert np.array_equal(np.bincount(df.Presynaptic_Index.to_numpy()[a], minlength=n), np.bincount(pre[b_], minlength=n))
        assert np.array_equal(np.bincount(df.Postsynaptic_Index.to_numpy()[a], minlength=n), np.bincount(post[b_], minlength=n))
    tmp = target.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    save(target.with_suffix(".json"), {"shuffle_seed": shuffle_seed, "source_sha256": hashlib.sha256(con.read_bytes()).hexdigest(), "edges": len(out), "fraction_edges_changed": changed,
                                       "preserved_exactly": ["out-degree per node per sign", "in-degree per node per sign", "global weight multiset (weight stays with its presynaptic edge)", "no self-loops", "no duplicate pairs"],
                                       "preserved_approximately": ["per-node incoming weight distribution"], "swap_rounds": 10})
    tmp.rename(target)
    return target


def random_connectivity(con, seed):
    """Null reservoir for the SAT experiment: same neuron count, edge count and weight multiset as v783, but presynaptic
    and postsynaptic indices drawn uniformly at random (no degree preservation). Self-loops and duplicate pairs dropped."""
    target = ROOT / "results" / f"random-connectivity-{seed}.parquet"
    if target.exists():
        return target
    df = pd.read_parquet(con)
    n = len(pd.read_csv(BRAIN / "Completeness_783.csv", index_col=0))
    rng = np.random.default_rng(seed)
    pre, post = rng.integers(0, n, len(df)), rng.integers(0, n, len(df))
    w = rng.permutation(df["Excitatory x Connectivity"].to_numpy())
    keep = pre != post
    out = pd.DataFrame({"Presynaptic_Index": pre[keep], "Postsynaptic_Index": post[keep], "Excitatory x Connectivity": w[keep]})
    out = out.drop_duplicates(["Presynaptic_Index", "Postsynaptic_Index"])
    tmp = target.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    save(target.with_suffix(".json"), {"random_seed": seed, "source_edges": len(df), "edges": len(out), "dropped_self_loops_or_duplicates": int(len(df) - len(out)),
                                       "preserved": ["neuron count", "edge count (minus dropped)", "weight multiset (permuted, minus dropped)"], "not_preserved": ["degrees", "any topology"]})
    tmp.rename(target)
    return target


def run(args):
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    save(out / "manifest.json", manifest())
    blocks = round(args.seconds / .015)
    events = events_for(args.scenario, args.seed, blocks)
    save(out / "events.json", events)
    ann = pd.read_csv(ANN, sep="\t", low_memory=False)
    ann["root_id"] = ann["root_id"].astype("int64")
    comp, con = BRAIN / "Completeness_783.csv", BRAIN / "Connectivity_783.parquet"
    index = pd.read_csv(comp, index_col=0).index
    mapping = {int(v): i for i, v in enumerate(index)}
    sens = ann[(ann.cell_class == "mechanosensory") & (ann.cell_sub_class == "head bristle")]
    inputs = {side: [int(r) for r in sens[sens.side == side].root_id] for side in ("left", "right")}
    missing = [v for side in inputs for v in inputs[side] if v not in mapping]
    if missing:
        raise ValueError(f"{len(missing)} head bristle IDs absent from model; refusing silent exclusion")
    dn = ann[ann.super_class == "descending"]
    readout = {side: np.array([mapping[int(r)] for r in dn[dn.side == side].root_id if int(r) in mapping]) for side in ("left", "right")}
    dn_missing = int(dn.side.isin(["left", "right"]).sum() - len(readout["left"]) - len(readout["right"]))
    assert all(v in mapping for v in OUTPUTS.values())
    save(out / "wiring.json", {"materialization": 783, "annotation_commit": subprocess.check_output(["git", "-C", str(ROOT / "vendor/flywire_annotations"), "rev-parse", "HEAD"], text=True).strip(),
                               "annotation_sha256": hashlib.sha256(ANN.read_bytes()).hexdigest(),
                               "input_selection": "cell_class=mechanosensory, cell_sub_class=head bristle, side=nerve-entry side", "n_inputs": {k: len(v) for k, v in inputs.items()},
                               "input_ids": {k: [str(v) for v in v_] for k, v_ in inputs.items()}, "input_hz": args.hz,
                               "readout": "all annotated super_class=descending with side left/right; per-tick new spike counts", "n_readout": {k: int(len(v)) for k, v in readout.items()},
                               "readout_ids_absent_from_model": dn_missing, "network_seed": args.network_seed, "shuffle_seed": args.shuffle_seed})
    b.start_scope()
    b.defaultclock.dt = .1 * b.ms
    b.seed(args.network_seed)
    params = model.default_params.copy()
    params["r_poi"] = args.hz * b.Hz
    if args.shuffle_seed is None:
        neu, syn, monitor = model.create_model(comp, con, params)
    else:
        shuffled = shuffled_connectivity(con, args.shuffle_seed)
        save(out / "shuffle.json", {**json.loads(shuffled.with_suffix(".json").read_text()), "sha256": hashlib.sha256(shuffled.read_bytes()).hexdigest()})
        neu, syn, monitor = model.create_model(comp, shuffled, params)
    pois = {}
    for side in ("left", "right"):
        pois[side], neu = model.poi(neu, [mapping[v] for v in inputs[side]], [], params)
    net = b.Network(neu, syn, monitor, *pois["left"], *pois["right"])
    # The stimulus is external and piecewise constant, so the network is advanced in segments between stimulus
    # changes and per-tick counts are binned from recorded spike times. brain-stream-0 showed segmented and
    # continuous runs are bitwise identical, and c-brain-smoke2 (per-tick stepping) reproduces these bins exactly.
    active_per_tick = [{side: bool(val >= .5) for side, val in zip(("left", "right"), events["observations"][k])} for k in range(blocks)]
    start = time.monotonic()
    k = 0
    while k < blocks:
        active = active_per_tick[k]
        length = 1
        while k + length < blocks and active_per_tick[k + length] == active:
            length += 1
        for side in ("left", "right"):
            for p in pois[side]:
                p.active = active[side]
        net.run(length * 15 * b.ms)
        k += length
        assert abs(float(net.t / b.second) - k * .015) < 1e-12
    spike_i = np.asarray(monitor.i[:])
    spike_tick = np.floor(np.asarray(monitor.t[:] / b.second) / .015 + 1e-9).astype(int)
    assert len(spike_tick) == 0 or (spike_tick.min() >= 0 and spike_tick.max() < blocks)  # a silent network (no stimulus) is a valid outcome
    def per_tick(indices):
        mask = np.isin(spike_i, indices)
        return np.bincount(spike_tick[mask], minlength=blocks)
    dn_left, dn_right, total = per_tick(readout["left"]), per_tick(readout["right"]), np.bincount(spike_tick, minlength=blocks)
    outputs = {name: per_tick(np.array([mapping[v]])) for name, v in OUTPUTS.items()}
    ticks = [{"tick": k, "t_end_s": (k + 1) * .015, "input_left": active_per_tick[k]["left"], "input_right": active_per_tick[k]["right"],
              "DN_left": int(dn_left[k]), "DN_right": int(dn_right[k]), **{name: int(outputs[name][k]) for name in OUTPUTS}, "spikes": int(total[k])} for k in range(blocks)]
    assert np.isfinite(neu.v[:]).all() and np.isfinite(neu.g[:]).all()
    save(out / "brain_ticks.json", {"scenario": args.scenario, "seed": args.seed, "network_seed": args.network_seed, "shuffle_seed": args.shuffle_seed, "dt_s": .015,
                                    "events_sha256": hashlib.sha256((out / "events.json").read_bytes()).hexdigest(), "ticks": ticks})
    model.construct_dataframe([model.get_spk_trn(monitor)], "brain_loop", dict(enumerate(index))).to_parquet(out / "spikes.parquet", index=False)
    counts = np.asarray(monitor.count[:])
    summary = {"scenario": args.scenario, "seed": args.seed, "network_seed": args.network_seed, "shuffle_seed": args.shuffle_seed, "blocks": blocks, "spikes": int(counts.sum()),
               "active_neurons": int((counts > 0).sum()), "DN_left_total": sum(t["DN_left"] for t in ticks), "DN_right_total": sum(t["DN_right"] for t in ticks),
               "wall_s": time.monotonic() - start, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    save(out / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    if sys.argv[1:] == ["--check"]:
        selfcheck()
        sys.exit(0)
    if sys.argv[1:2] == ["--make-random"]:
        for seed in map(int, sys.argv[2:]):
            print(random_connectivity(BRAIN / "Connectivity_783.parquet", seed), flush=True)
        sys.exit(0)
    if sys.argv[1:2] == ["--make-shuffled"]:
        for seed in map(int, sys.argv[2:]):
            print(shuffled_connectivity(BRAIN / "Connectivity_783.parquet", seed), flush=True)
        sys.exit(0)
    p.add_argument("--label", required=True)
    p.add_argument("--scenario", choices=["none", "left", "right"], required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--seconds", type=float, default=1.005)
    p.add_argument("--hz", type=float, default=150)
    p.add_argument("--network-seed", type=int, default=None, help="default 10000 + seed")
    p.add_argument("--shuffle-seed", type=int, default=None, help="variant E: degree-preserving edge shuffle with this seed")
    a = p.parse_args()
    if Path(a.label).name != a.label or a.label in {".", ".."} or not 0 <= a.hz <= 1000 or a.seconds <= 0:
        p.error("invalid label, rate or duration")
    if a.network_seed is None:
        a.network_seed = NETWORK_SEED_BASE + a.seed
    run(a)
