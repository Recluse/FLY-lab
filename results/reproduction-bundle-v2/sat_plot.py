"""Aggregate results/sat-fly/*.json into tables and scaling plots (run with .venv-body: matplotlib lives there)."""
import json
import glob
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent / "results" / "sat-fly"
ORDER = ["random", "heuristic", "linear-raw", "linear-raw-shaped", "fly-random-shaped", "fly-shuffled-shaped", "fly-shaped", "fly"]
LABEL = {"random": "random search", "heuristic": "honest local rule", "linear-raw": "linear readout, raw bits (sparse reward)",
         "linear-raw-shaped": "linear readout, raw bits", "fly-shaped": "Drosophila connectome reservoir + linear readout",
         "fly": "connectome reservoir (sparse reward)", "fly-shuffled-shaped": "degree-shuffled connectome reservoir", "fly-random-shaped": "random LIF reservoir (same size, edges, weights)"}


def load():
    runs = {}
    for path in sorted(OUT.glob("*-s[0-9]*.json")):
        m = re.match(r"(.+)-s(\d+)(-shaped)?\.json", path.name)
        if not m:
            continue
        key = m.group(1) + (m.group(3) or "")
        runs.setdefault(key, []).append(json.loads(path.read_text()))
    return runs


def per_size(records):
    """records: list of eval dicts (satisfiable only). Returns {n: (success_rate, median_steps_of_solved, mean_wall, counts)}"""
    out = {}
    for n in sorted({r["n"] for r in records}):
        rows = [r for r in records if r["n"] == n]
        solved = [r for r in rows if r["solved"]]
        out[n] = {"success": len(solved) / len(rows), "n_solved": len(solved), "n_total": len(rows),
                  "median_steps_solved": float(np.median([r["steps"] for r in solved])) if solved else None,
                  "median_sweeps_solved": float(np.median([r["sweeps"] for r in solved])) if solved else None,
                  "mean_wall_s": float(np.mean([r["wall_s"] for r in rows]))}
    return out


def main():
    runs = load()
    table = {}
    for key, logs in runs.items():
        seeds = []
        for log in logs:
            recs = [r for split in ("test-in", "test-out") for r in log["eval"][split] if r["satisfiable"]]
            seeds.append({"seed": log["seed"], "per_size": per_size(recs), "leak_checks": log.get("leak_checks"),
                          "train_last50_success": (np.mean([r["solved"] for r in log["train"][-50:]]) if log["train"] else None)})
        table[key] = seeds
    (OUT / "summary.json").write_text(json.dumps(table, indent=1))

    sizes = [3, 4, 5, 6, 8, 10, 12]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
    for key in ORDER:
        if key not in table:
            continue
        S = np.array([[s["per_size"].get(n, {}).get("success", np.nan) for n in sizes] for s in table[key]], dtype=float)
        St = np.array([[s["per_size"].get(n, {}).get("median_steps_solved") or np.nan for n in sizes] for s in table[key]], dtype=float)
        W = np.array([[s["per_size"].get(n, {}).get("mean_wall_s", np.nan) for n in sizes] for s in table[key]], dtype=float)
        for ax, M, name in ((axes[0], S, "success rate within 8n decisions"), (axes[1], St, "median decisions to solution (solved only)"), (axes[2], W, "wall-clock per instance, s")):
            mean, lo, hi = np.nanmean(M, 0), np.nanmin(M, 0), np.nanmax(M, 0)
            ax.plot(sizes, mean, marker="o", label=LABEL.get(key, key))
            ax.fill_between(sizes, lo, hi, alpha=.15)
            ax.set_title(name); ax.set_xlabel("variables n (clauses ≈ 4.26 n)")
    axes[1].set_yscale("log"); axes[2].set_yscale("log")
    axes[0].axvspan(2.5, 6.5, color="grey", alpha=.08); axes[0].text(3, .05, "training sizes", fontsize=8)
    axes[0].legend(fontsize=7, loc="lower left")
    fig.suptitle("Empirical complexity of Drosophila-based SAT solving (random 3-SAT, seeds = shaded min–max)")
    fig.tight_layout()
    fig.savefig(OUT / "scaling.png", dpi=150)
    print(json.dumps({k: {n: round(v["per_size"][n]["success"], 2) for n in sizes if n in v["per_size"]} for k, v in ((k, t[0]) for k, t in table.items())}, indent=1))
    print("saved", OUT / "summary.json", OUT / "scaling.png")


if __name__ == "__main__":
    main()
