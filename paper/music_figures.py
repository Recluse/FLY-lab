"""Figures for the odour-identity probes: why the published model cannot tell one input from another.

Reads results/music-probe-v*/summary.json and draws two panels — how much of the network a
single odour sets alight as the recurrent weight is lowered, and how much of the response is
about which odour it was, across the regimes tried. Run with .venv-body.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
FIG = Path(__file__).resolve().parent / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 170})
BLUE, ORANGE, GREY, RED, GREEN = "#2c6fbb", "#e08a1e", "#8a8a8a", "#c0392b", "#3a9e57"
PUBLISHED = 0.275


def probes():
    out = {}
    for path in sorted((ROOT / "results").glob("music-probe-v*/summary.json")):
        out[path.parent.name] = json.loads(path.read_text())
    return out


def rows_of(data):
    """(level, hz, shuffled) -> list of per-odour rows, and the identity margins."""
    rows, margins = {}, {}
    shuffled = data.get("shuffle_seed") is not None
    # Older summaries carry the input rate only on the per-odour rows.
    seen = [v.get("hz") for v in data["results"].values() if isinstance(v, dict) and "odour" in v]
    hz = float(data.get("hz") or (seen[0] if seen else 50.))
    for key, value in data["results"].items():
        parts = key.split(":")
        try:
            level = float(parts[0])
        except ValueError:
            continue                      # the first probe, before the sweeps had levels
        if isinstance(value, dict) and "odour" in value:
            rows.setdefault((level, value.get("hz", hz), shuffled), []).append(value)
        elif len(parts) == 3 and parts[2] in ("within", "between"):
            margins.setdefault((level, hz, shuffled), {})[f"{parts[1]}:{parts[2]}"] = value
    return rows, margins


def main():
    all_rows, all_margins = {}, {}
    for name, data in probes().items():
        rows, margins = rows_of(data)
        for k, v in rows.items():
            all_rows.setdefault(k, []).extend(v)
        all_margins.update(margins)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.6, 3.9))

    # Panel 1: the gain sweep at the model's own input rate.
    gain = sorted(k for k in all_rows if abs(k[1] - 50.) < 1e-6 and not k[2])
    levels = [k[0] for k in gain]
    active = [np.mean([r["active_neurons"] for r in all_rows[k]]) for k in gain]
    kc = [np.mean([r["KC_fraction"] for r in all_rows[k]]) * 100 for k in gain]
    ax1.plot(levels, active, marker="o", ms=4, color=BLUE, lw=1.8)
    ax1.set_yscale("log")
    ax1.set_xlabel("weight per synapse, mV")
    ax1.set_ylabel("neurons firing in 300 ms", color=BLUE)
    ax1b = ax1.twinx()
    ax1b.plot(levels, kc, marker="s", ms=3.5, color=ORANGE, lw=1.4)
    ax1b.set_ylabel("Kenyon cells firing, %", color=ORANGE)
    ax1b.spines["top"].set_visible(False)
    ax1.axvline(PUBLISHED, color=GREY, ls="--", lw=1)
    ax1.annotate("as published", (PUBLISHED, max(active)), fontsize=7.5, color=GREY,
                 xytext=(-4, -2), textcoords="offset points", ha="right", va="top")
    ax1.set_title("One odour, and how much of the brain it ignites", fontsize=10, loc="left")
    ax1.text(0, -.22, "Below 0.1 mV the signal never reaches the mushroom body; above it, everything burns at once.",
             fontsize=7, color=GREY, transform=ax1.transAxes)

    # Panel 2: identity margin across the regimes tried.
    order = [((0.275, 50., False), "as published\n0.275 mV, 50 Hz"),
             ((0.14, 50., False), "0.14 mV\n50 Hz"),
             ((0.12, 50., False), "0.12 mV\n50 Hz"),
             ((0.10, 50., False), "0.10 mV\n50 Hz"),
             ((0.12, 400., False), "0.12 mV\n400 Hz"),
             ((0.12, 1200., False), "0.12 mV\n1200 Hz"),
             ((0.14, 1200., False), "0.14 mV\n1200 Hz"),
             ((0.12, 1200., True), "shuffled\n0.12 mV, 1200 Hz")]
    labels, values, colours, notes = [], [], [], []
    for key, label in order:
        m = all_margins.get(key)
        if not m or "KC_vector:within" not in m:
            continue
        labels.append(label)
        values.append(m["KC_vector:within"] - m["KC_vector:between"])
        colours.append(RED if key[2] else (GREEN if values[-1] > .05 else BLUE))
        notes.append(np.mean([r["active_neurons"] for r in all_rows.get(key, [])]) if key in all_rows else np.nan)
    bars = ax2.bar(range(len(values)), values, .6, color=colours)
    for i, (bar, n) in enumerate(zip(bars, notes)):
        if np.isfinite(n):
            ax2.text(i, bar.get_height() + .02, f"{n:.0f}\nneurons", ha="center", fontsize=6.5, color=GREY)
    ax2.set_xticks(range(len(labels)))
    ax2.set_xticklabels(labels, fontsize=6.8)
    ax2.set_ylabel("identity margin\n(same odour − different odour)")
    ax2.set_ylim(0, 1.15)
    ax2.set_title("How much of the answer says which odour it was", fontsize=10, loc="left")
    ax2.text(0, -.30, "The shuffled control scores highest for a boring reason: almost nothing fires at all,\n"
                      "so two odours light up disjoint handfuls of cells. Read it beside the neuron counts.",
             fontsize=7, color=GREY, transform=ax2.transAxes)
    fig.tight_layout()
    fig.savefig(FIG / "music1-criticality-en.png", bbox_inches="tight")
    print("saved", FIG / "music1-criticality-en.png")
    for (level, hz, sh), m in sorted(all_margins.items()):
        n = np.mean([r["active_neurons"] for r in all_rows.get((level, hz, sh), [])]) if (level, hz, sh) in all_rows else float("nan")
        print(f"w_syn {level:<6} {hz:>6.0f} Hz {'shuffled' if sh else 'real':<9} "
              f"KC margin {m.get('KC_vector:within', 0) - m.get('KC_vector:between', 0):+.4f}  "
              f"MBON margin {m.get('MBON_vector:within', 0) - m.get('MBON_vector:between', 0):+.4f}  "
              f"{n:.0f} neurons active")


def learning_curve():
    """Second figure: does the fly get better at choosing chord tones as the run goes on?"""
    import statistics as stx
    arms = {"learn": ("connectome, plastic", GREEN), "frozen": ("connectome, frozen", BLUE),
            "shuffled": ("shuffled connectome", GREY), "deaf": ("no odour input", RED)}
    runs = {}
    for path in sorted((ROOT / "results").glob("music-v2-*/steps.json")):
        arm = path.parent.name.split("-")[2]
        runs.setdefault(arm, []).append(json.loads(path.read_text()))
    if not runs:
        return
    fig, ax = plt.subplots(figsize=(7.2, 3.9))
    window = 48                                   # six bars
    chance = []
    for arm, (label, colour) in arms.items():
        if arm not in runs:
            continue
        curves = []
        for steps in runs[arm]:
            hits = [1 if r["chord_tone"] else 0 for r in steps]
            curves.append([stx.mean(hits[max(0, i - window):i + 1]) for i in range(len(hits))])
        n = min(len(c) for c in curves)
        mean = [stx.mean(c[i] for c in curves) for i in range(n)]
        ax.plot(range(n), mean, color=colour, lw=1.8, label=f"{label} ({len(curves)} runs)")
        if len(curves) > 1:
            lo = [min(c[i] for c in curves) for i in range(n)]
            hi = [max(c[i] for c in curves) for i in range(n)]
            ax.fill_between(range(n), lo, hi, color=colour, alpha=.12, lw=0)
    for steps in runs.get("learn", []):
        chance.append(stx.mean(sum(1 for d in r["options"]) and
                               sum(1 for d in r["options"] if SCALE[d] in CHORD(r["bar"])) / len(r["options"])
                               for r in steps))
    if chance:
        ax.axhline(stx.mean(chance), color="#444", ls="--", lw=1)
        ax.text(2, stx.mean(chance) + .012, "what a coin would score on the same offers", fontsize=7.5, color="#444")
    ax.set_xlabel("decision (eight per bar, 36 bars)")
    ax.set_ylabel(f"chord tones chosen, running mean of {window}")
    ax.set_ylim(0, 1)
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.set_title("Learning to prefer notes that fit the chord", fontsize=10, loc="left")
    ax.grid(alpha=.2)
    fig.tight_layout()
    fig.savefig(FIG / "music2-learning-en.png", bbox_inches="tight")
    print("saved", FIG / "music2-learning-en.png")


SCALE = (0, 2, 3, 5, 7, 9, 10)
PROGRESSION = [0, 0, 0, 0, 5, 5, 0, 0, 7, 5, 0, 7]
SEVENTH = (0, 4, 7, 10)


def CHORD(bar):
    root = PROGRESSION[bar % len(PROGRESSION)]
    return {(root + t) % 12 for t in SEVENTH}


if __name__ == "__main__":
    main()
    learning_curve()
