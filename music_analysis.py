"""Aggregate the music-learning campaign: did the fly get better at choosing chord tones?

Pre-declared metric: the fraction of chosen notes that are chord tones, in the first and the
last quarter of a run, against the rate a coin would get given the same offered candidates.
Arms are paired by the seed that decides which degrees are offered, so learn/frozen/shuffled/deaf
see exactly the same choices.

    .venv-body/bin/python music_analysis.py
"""
import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ARMS = ("learn", "frozen", "shuffled", "deaf")
NAMES = {"learn": "connectome, plastic", "frozen": "connectome, frozen",
         "shuffled": "shuffled connectome, plastic", "deaf": "no odour input, plastic"}


def runs(prefix):
    out = {}
    for path in sorted((ROOT / "results").glob(f"{prefix}-*/summary.json")):
        label = path.parent.name
        arm = label.split("-")[2]
        seed = int(label.split("-s")[-1])
        summary = json.loads(path.read_text())
        steps = json.loads((path.parent / "steps.json").read_text())
        out.setdefault(arm, {})[seed] = (summary, steps)
    return out


def offered_chance(steps, chord_tones):
    """What a coin would score: the mean fraction of offered candidates that are chord tones."""
    good = 0
    for row in steps:
        tones = chord_tones(row["bar"])
        good += sum(1 for d in row["options"] if SCALE[d] in tones) / len(row["options"])
    return good / len(steps)


SCALE = (0, 2, 3, 5, 7, 9, 10)
PROGRESSION = [0, 0, 0, 0, 5, 5, 0, 0, 7, 5, 0, 7]
SEVENTH = (0, 4, 7, 10)


def chord_tones(bar):
    root = PROGRESSION[bar % len(PROGRESSION)]
    return {(root + t) % 12 for t in SEVENTH}


def quarters(steps):
    hits = [r["chord_tone"] for r in steps]
    q = max(1, len(hits) // 4)
    return st.mean(hits[:q]), st.mean(hits[-q:]), st.mean(hits)


def advantage(steps):
    """Per quarter: how much better than a coin, on the same offered candidates.

    The offered candidates drift a little over a run, so the raw hit rate is not comparable
    between quarters; this subtracts the rate a coin would score on exactly those offers.
    """
    out, q = [], max(1, len(steps) // 4)
    for lo in range(0, len(steps) - q + 1, q):
        chunk = steps[lo:lo + q]
        coin = st.mean(sum(1 for d in r["options"] if SCALE[d] in chord_tones(r["bar"])) / len(r["options"])
                       for r in chunk)
        out.append(st.mean(r["chord_tone"] for r in chunk) - coin)
    return out[:4]


def preference(steps, key="descending"):
    """Mean answer for candidates that are chord tones minus the rest, per quarter.

    More sensitive than the choice rate: it looks at the readout itself rather than at
    which of three candidates happened to win.
    """
    out = []
    q = max(1, len(steps) // 4)
    for lo in range(0, len(steps) - q + 1, q):
        good, bad = [], []
        for row in steps[lo:lo + q]:
            tones = chord_tones(row["bar"])
            for r in row.get("readouts", []):
                (good if SCALE[r["degree"]] in tones else bad).append(r[key])
        out.append(st.mean(good) - st.mean(bad) if good and bad else float("nan"))
    return out[:4]


def main():
    prefix = sys.argv[1] if len(sys.argv) > 1 else "music-v2"
    data = runs(prefix)
    if not data:
        print("no runs yet")
        return
    print(f"{'arm':<30} {'runs':>4} {'first quarter':>14} {'last quarter':>13} {'whole run':>10} {'coin':>7}")
    table = {}
    for arm in ARMS:
        if arm not in data:
            continue
        firsts, lasts, wholes, coins = [], [], [], []
        for seed, (summary, steps) in sorted(data[arm].items()):
            f, l, w = quarters(steps)
            firsts.append(f); lasts.append(l); wholes.append(w)
            coins.append(offered_chance(steps, chord_tones))
        table[arm] = {"first": firsts, "last": lasts, "whole": wholes, "coin": coins}
        print(f"{NAMES[arm]:<30} {len(firsts):>4} {st.mean(firsts):>13.3f} {st.mean(lasts):>13.3f} "
              f"{st.mean(wholes):>10.3f} {st.mean(coins):>7.3f}")

    if "learn" in table and "frozen" in table:
        seeds = sorted(set(data["learn"]) & set(data["frozen"]))
        diffs = [quarters(data["learn"][s][1])[2] - quarters(data["frozen"][s][1])[2] for s in seeds]
        print(f"\npaired, plastic minus frozen, over {len(diffs)} seeds: "
              f"{st.mean(diffs):+.3f} (per seed: {', '.join(f'{d:+.3f}' for d in diffs)})")
    for arm in ARMS:
        if arm in table:
            gains = [l - f for f, l in zip(table[arm]["first"], table[arm]["last"])]
            print(f"{NAMES[arm]:<30} last minus first quarter: {st.mean(gains):+.3f} "
                  f"({', '.join(f'{g:+.3f}' for g in gains)})")

    print()
    for arm in ARMS:
        if arm not in data:
            continue
        adv = [advantage(steps) for _, (summary, steps) in sorted(data[arm].items())]
        mean = [st.mean(a[i] for a in adv) for i in range(min(len(a) for a in adv))]
        print(f"{NAMES[arm]:<30} advantage over a coin, by quarter: {', '.join(f'{m:+.3f}' for m in mean)}")
        table[arm]["advantage"] = mean

    print()
    for arm in ARMS:
        if arm not in data:
            continue
        curves = [preference(steps) for _, (summary, steps) in sorted(data[arm].items())]
        mean = [st.mean(c[i] for c in curves) for i in range(min(len(c) for c in curves))]
        print(f"{NAMES[arm]:<30} preference for chord tones by quarter (descending readout): "
              f"{', '.join(f'{m:+.1f}' for m in mean)}")
        table[arm]["preference"] = mean

    out = {arm: {k: [round(x, 4) for x in v] for k, v in vals.items()} for arm, vals in table.items()}
    (ROOT / "results" / f"{prefix}-summary.json").write_text(json.dumps(out, indent=1))
    print(f"\nsaved results/{prefix}-summary.json")


if __name__ == "__main__":
    main()
