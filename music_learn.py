"""The fly learns which notes are worth playing, by smelling them.

The wiring measurement that shaped this: sound never reaches the mushroom body
in this connectome (zero direct contacts from auditory Johnston's organ cells to
Kenyon cells, fourteen at two hops), so a note cannot be taught through the ear.
Odour can: the olfactory pathway into the mushroom body is exactly what the
learning circuit is built around. So each pitch class is presented as one
olfactory receptor class. That mapping is an invention and is declared as one;
everything downstream of it is the connectome's own wiring.

Per musical step the composition rules propose a few scale degrees. Each
candidate is presented as its odour, and the fly's answer is the difference in
spikes between two disjoint halves of the mushroom body output neurons. The
candidate with the highest answer is played. Then the teacher speaks: a chord
tone drives the appetitive dopaminergic cluster (PAM), anything else drives the
aversive one (PPL1), and dopamine depresses the Kenyon-cell synapses that just
argued for the choice — depression only, as in the animal, with slow recovery
towards the connectome's own weights.

Nothing else in the brain changes. The plastic bundle is 62,261 of the model's
15,091,983 connections, four tenths of one per cent.

    .venv-brain/bin/python music_learn.py --label music-learn-v1 --bars 12
    .venv-brain/bin/python music_learn.py --label music-learn-v1-frozen --no-plasticity
    .venv-brain/bin/python music_learn.py --label music-learn-v1-shuffled --shuffle-seed 4000
    .venv-brain/bin/python music_learn.py --label music-learn-v1-deaf --deaf
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

# One olfactory receptor class per scale degree. Chosen for cell count, nothing else.
DEGREE_ODOUR = ["ORN_DM1", "ORN_DM2", "ORN_DL5", "ORN_VA2", "ORN_DM3", "ORN_DL1", "ORN_VM4"]
# Twelve-bar blues in A, as in results/fun-fly-midi/fly_blues.py.
PROGRESSION = [0, 0, 0, 0, 5, 5, 0, 0, 7, 5, 0, 7]
SCALE = (0, 2, 3, 5, 7, 9, 10)          # dorian, seven degrees, one odour each
SEVENTH = (0, 4, 7, 10)
STEPS_PER_BAR = 8
NETWORK_SEED, VALENCE_SEED = 20000, 7001


def chord_tones(bar):
    root = PROGRESSION[bar % len(PROGRESSION)]
    return {(root + t) % 12 for t in SEVENTH}


def main(args):
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    ann = pd.read_csv(ANN, sep="\t", low_memory=False)
    ann["root_id"] = ann["root_id"].astype("int64")
    comp = BRAIN / "Completeness_783.csv"
    con = BRAIN / "Connectivity_783.parquet"
    index = pd.read_csv(comp, index_col=0).index
    mapping = {int(v): i for i, v in enumerate(index)}
    ct = ann.cell_type.astype(str)

    def indices(mask):
        return np.array(sorted(mapping[int(r)] for r in ann.loc[mask, "root_id"] if int(r) in mapping))

    kc = indices(ct.str.startswith("KC"))
    mbon = indices(ct.str.startswith("MBON"))
    dn = indices(ann.super_class == "descending")
    pam = indices(ct.str.match(r"^PAM"))
    ppl1 = indices(ct.str.match(r"^PPL1"))
    # Two disjoint halves of each population, fixed by seed and declared in advance.
    # The mushroom body's verdict does reach the motor output — 361 direct contacts from
    # output neurons onto 160 descending cells, 663 descending cells within two hops — and the
    # descending population fires hundreds of times more than the output neurons themselves,
    # so the decision is read there and both readouts are logged.
    rng = np.random.default_rng(VALENCE_SEED)
    order = rng.permutation(len(mbon))
    yes, no = mbon[order[:len(mbon) // 2]], mbon[order[len(mbon) // 2:]]
    order_dn = rng.permutation(len(dn))
    dn_yes, dn_no = dn[order_dn[:len(dn) // 2]], dn[order_dn[len(dn) // 2:]]

    odour_cells, span = [], {}
    for degree, name in enumerate(DEGREE_ODOUR):
        cells = [mapping[int(r)] for r in ann.loc[ct == name, "root_id"] if int(r) in mapping]
        assert len(cells) >= 20, f"{name}: {len(cells)} cells"
        span[degree] = (len(odour_cells), len(odour_cells) + len(cells))
        odour_cells += cells
    teach_span = {}
    for name, cells in (("PAM", pam), ("PPL1", ppl1)):
        teach_span[name] = (len(odour_cells), len(odour_cells) + len(cells))
        odour_cells += list(cells)
    odour_cells = np.array(odour_cells)

    b.start_scope()
    b.defaultclock.dt = .1 * b.ms
    b.seed(NETWORK_SEED)
    params = model.default_params.copy()
    source = con if args.shuffle_seed is None else shuffled_connectivity(con, args.shuffle_seed)
    neu, syn, monitor = model.create_model(comp, source, params)
    if args.wsyn is not None:
        # The published weight per synapse (0.275 mV) puts the network in a supercritical
        # regime where any input recruits the same ~8,200-neuron avalanche and no two odours
        # can be told apart at the mushroom body (identity margin +0.001, results/music-probe-v4).
        # Weakening the recurrence and driving the input harder restores identity (+0.143 at
        # 0.12 mV and 400 Hz, results/music-probe-v6). This is a changed model, and is labelled one.
        syn.w[:] = (np.asarray(syn.w[:]) * (args.wsyn / (float(params["w_syn"] / b.volt) * 1000.))) * b.volt
    neu.rfc[odour_cells] = 0 * b.ms
    drive = b.PoissonGroup(len(odour_cells), rates=0 * b.Hz, name="drive")
    feed = b.Synapses(drive, neu, on_pre="v_post += w_in",
                      namespace={"w_in": params["w_syn"] * params["f_poi"]}, name="feed")
    feed.connect(i=np.arange(len(odour_cells)), j=odour_cells)
    net = b.Network(neu, syn, monitor, drive, feed)

    # Synapse k of `syn` is row k of the connectivity table, so the plastic bundle is a row mask.
    table = pd.read_parquet(source, columns=["Presynaptic_Index", "Postsynaptic_Index"])
    pre_idx = table.Presynaptic_Index.values
    post_idx = table.Postsynaptic_Index.values
    plastic = np.flatnonzero(np.isin(pre_idx, kc) & np.isin(post_idx, mbon))
    plastic_pre = pre_idx[plastic]
    plastic_post = post_idx[plastic]
    baseline = np.asarray(syn.w[plastic]).copy()
    onto_yes = np.isin(plastic_post, yes)
    print(f"plastic bundle: {len(plastic)} synapses, {len(np.unique(plastic_pre))} Kenyon cells, "
          f"{len(np.unique(plastic_post))} output neurons ({onto_yes.sum()} onto the 'yes' half)", flush=True)

    counted = np.zeros(len(index), dtype=np.int64)

    def run_window(ms, rates):
        nonlocal counted
        drive.rates = 0 * b.Hz
        for lo, hi, hz in rates:
            drive.rates[lo:hi] = hz * b.Hz
        net.run(ms * b.ms)
        now = np.asarray(monitor.count[:]).copy()
        fresh = now - counted
        counted = now
        return fresh

    choice_rng = np.random.default_rng(args.choice_seed)
    log, wall = [], time.monotonic()
    weights_moved = 0.
    for step in range(args.bars * STEPS_PER_BAR):
        bar, beat = divmod(step, STEPS_PER_BAR)
        good = chord_tones(bar)
        options = sorted(choice_rng.choice(len(SCALE), size=args.candidates, replace=False).tolist())
        answers, active_kc, both = [], {}, []
        for degree in options:
            lo, hi = span[degree]
            fresh = run_window(args.eval_ms, [] if args.deaf else [(lo, hi, args.hz)])
            mbon_answer = int(fresh[yes].sum()) - int(fresh[no].sum())
            dn_answer = int(fresh[dn_yes].sum()) - int(fresh[dn_no].sum())
            answers.append(dn_answer if args.readout == "descending" else mbon_answer)
            both.append({"degree": int(degree), "mbon": mbon_answer, "descending": dn_answer,
                         "kc_active": int((fresh[kc] > 0).sum())})
            active_kc[degree] = fresh[kc] > 0
        picked = options[int(np.argmax(answers))]
        pitch_class = SCALE[picked]
        hit = pitch_class in good

        # The teacher speaks in every arm, so the network sees the same dynamics; only the
        # weight update below is switched off by --no-plasticity.
        cluster = "PAM" if hit else "PPL1"
        lo, hi = teach_span[cluster]
        run_window(args.teach_ms, [(lo, hi, args.teach_hz)])

        if not args.no_plasticity:
            fired = active_kc[picked]
            eligible = fired[np.searchsorted(kc, plastic_pre)]
            target = onto_yes if not hit else ~onto_yes      # depress what argued for a wrong note
            touched = eligible & target
            w = np.asarray(syn.w[plastic]).copy()
            before = w.copy()
            w[touched] *= (1 - args.lr)
            w += args.recovery * (baseline - w)              # slow return to the connectome's own weights
            syn.w[plastic] = w * b.volt
            weights_moved += float(np.abs(w - before).sum())

        log.append({"step": step, "bar": bar, "beat": beat, "options": options, "answers": answers, "readouts": both,
                    "picked": picked, "pitch_class": int(pitch_class), "chord_tone": bool(hit),
                    "kc_active": int(active_kc[picked].sum())})
        if beat == STEPS_PER_BAR - 1:
            recent = [r["chord_tone"] for r in log[-STEPS_PER_BAR:]]
            print(f"bar {bar + 1:>3}: chord tones {sum(recent)}/{len(recent)}, "
                  f"mean answer {np.mean([max(r['answers']) for r in log[-STEPS_PER_BAR:]]):.1f}, "
                  f"KC active {np.mean([r['kc_active'] for r in log[-STEPS_PER_BAR:]]):.0f}, "
                  f"{time.monotonic() - wall:.0f} s", flush=True)

    hits = [r["chord_tone"] for r in log]
    quarter = max(1, len(hits) // 4)
    summary = {"label": args.label, "bars": args.bars, "hz": args.hz, "teach_hz": args.teach_hz,
               "wsyn_mV": args.wsyn, "eval_ms": args.eval_ms, "teach_ms": args.teach_ms, "readout": args.readout,
               "candidates": args.candidates,
               "lr": args.lr, "recovery": args.recovery, "plasticity": not args.no_plasticity,
               "deaf": args.deaf, "shuffle_seed": args.shuffle_seed,
               "network_seed": NETWORK_SEED, "valence_seed": VALENCE_SEED, "choice_seed": args.choice_seed,
               "notes": len(hits), "chord_tone_rate": round(float(np.mean(hits)), 3),
               "first_quarter": round(float(np.mean(hits[:quarter])), 3),
               "last_quarter": round(float(np.mean(hits[-quarter:])), 3),
               "chance_rate": round(float(np.mean([d in chord_tones(bar_) for bar_ in range(args.bars) for d in SCALE])), 3),
               "weights_moved_mV": round(weights_moved * 1000, 3),
               "plastic_synapses": int(len(plastic)),
               "wall_s": round(time.monotonic() - wall, 1),
               "annotation_sha256": hashlib.sha256(ANN.read_bytes()).hexdigest()}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "steps.json").write_text(json.dumps(log, indent=1))
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--label", required=True)
    p.add_argument("--bars", type=int, default=12)
    p.add_argument("--hz", type=float, default=400.)
    p.add_argument("--teach-hz", type=float, default=400.)
    p.add_argument("--wsyn", type=float, default=.12, help="weight per synapse in mV; the published model uses 0.275")
    p.add_argument("--eval-ms", type=float, default=300.)
    p.add_argument("--candidates", type=int, default=3)
    p.add_argument("--choice-seed", type=int, default=7002,
                   help="which degrees the rules offer at each step; paired across arms")
    p.add_argument("--teach-ms", type=float, default=150.)
    p.add_argument("--lr", type=float, default=.2)
    p.add_argument("--recovery", type=float, default=.02)
    p.add_argument("--no-plasticity", action="store_true")
    p.add_argument("--deaf", action="store_true")
    p.add_argument("--readout", choices=("descending", "mbon"), default="descending")
    p.add_argument("--shuffle-seed", type=int, default=None)
    main(p.parse_args())
