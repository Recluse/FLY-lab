"""Figures for the SAT side experiment. Run with .venv-body after all sat-fly runs have finished."""
import json
import re
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
S = ROOT / "results" / "sat-fly"
FIG = Path(__file__).resolve().parent / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False, "figure.dpi": 170})
INK, BLUE, ORANGE, GREEN, RED, GREY, PURPLE = "#1a1a1a", "#2c6fbb", "#e08a1e", "#3a9e57", "#c0392b", "#8a8a8a", "#9b59b6"
SIZES = [3, 4, 5, 6, 8, 10, 12]

LABELS = {
    "ru": {"random": "случайный перебор", "heuristic": "честное локальное правило", "linear-raw-clone": "линейный слой на сырых битах",
           "fly-clone": "коннектом мухи", "fly-shuffled-clone": "перемешанный коннектом", "fly-random-clone": "случайная топология",
           "linear-raw-shaped": "сырые биты, обучение с подкреплением", "fly-shaped": "коннектом, обучение с подкреплением"},
    "en": {"random": "random search", "heuristic": "honest local rule", "linear-raw-clone": "linear layer on the raw bits",
           "fly-clone": "fly connectome", "fly-shuffled-clone": "shuffled connectome", "fly-random-clone": "random topology",
           "linear-raw-shaped": "raw bits, reinforcement learning", "fly-shaped": "connectome, reinforcement learning"},
}
SHORT = {"ru": {"heuristic": "честное\nправило", "linear-raw-clone": "сырые биты\nбез мухи", "fly-clone": "коннектом", "fly-shuffled-clone": "перемешанный\nконнектом", "fly-random-clone": "случайная\nтопология", "random": "случайный\nперебор"},
         "en": {"heuristic": "honest\nrule", "linear-raw-clone": "raw bits,\nno fly", "fly-clone": "connectome", "fly-shuffled-clone": "shuffled\nconnectome", "fly-random-clone": "random\ntopology", "random": "random\nsearch"}}
ORDER = ["heuristic", "linear-raw-clone", "fly-clone", "fly-shuffled-clone", "fly-random-clone", "random"]
COLOURS = {"heuristic": GREEN, "linear-raw-clone": INK, "fly-clone": BLUE, "fly-shuffled-clone": PURPLE,
           "fly-random-clone": GREY, "random": RED, "linear-raw-shaped": "#777", "fly-shaped": "#8ab4dd"}


def load():
    runs = {}
    for path in sorted(S.glob("*-s[0-9]*.json")):
        if "v1-no-tonic" in str(path):
            continue
        m = re.match(r"(.+)-s(\d+)(-clone|-shaped)?\.json", path.name)
        if not m:
            continue
        key = m.group(1) + (m.group(3) or "")
        log = json.loads(path.read_text())
        if "leak_checks" not in log or "eval" not in log:
            continue
        runs.setdefault(key, []).append(log)
    return runs


def sat_records(log):
    return [r for split in ("test-in", "test-out") for r in log["eval"][split] if r["satisfiable"]]


def per_size(recs):
    out = {}
    for n in SIZES:
        rows = [r for r in recs if r["n"] == n]
        if not rows:
            continue
        solved = [r for r in rows if r["solved"]]
        out[n] = {"success": len(solved) / len(rows), "n": len(rows),
                  "median_steps": float(np.median([r["steps"] for r in solved])) if solved else np.nan}
    return out


def fig_ladder(runs, lang):
    T = {"ru": dict(title="Доля решённых формул: чем больше переменных, тем яснее разница",
                    xlabel="переменных в формуле (клауз ≈ 4.26 n)", ylabel="доля решённых выполнимых формул",
                    train="размеры, на которых обучались", note="Бюджет — восемь решений на переменную. Полосы показывают разброс между независимыми запусками."),
         "en": dict(title="Fraction of formulas solved: the more variables, the clearer the gap",
                    xlabel="variables in the formula (clauses ≈ 4.26 n)", ylabel="fraction of satisfiable formulas solved",
                    train="training sizes", note="The budget is eight decisions per variable. Bands show the spread across independent runs.")}[lang]
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    for key in ORDER:
        if key not in runs:
            continue
        M = np.array([[per_size(sat_records(l)).get(n, {}).get("success", np.nan) for n in SIZES] for l in runs[key]], dtype=float)
        mean = np.nanmean(M, 0)
        ax.plot(SIZES, mean, marker="o", ms=4, color=COLOURS[key], lw=1.8, label=LABELS[lang][key])
        if len(M) > 1:
            ax.fill_between(SIZES, np.nanmin(M, 0), np.nanmax(M, 0), color=COLOURS[key], alpha=.13, lw=0)
    ax.axvspan(2.6, 6.4, color="#f0f0f0", zorder=0)
    ax.text(3.0, 1.0, T["train"], fontsize=7.5, color=GREY)
    ax.set_xticks(SIZES); ax.set_xlabel(T["xlabel"]); ax.set_ylabel(T["ylabel"]); ax.set_ylim(0, 1.05)
    ax.legend(fontsize=7.5, frameon=False, loc="lower left")
    ax.set_title(T["title"], fontsize=10, loc="left")
    ax.text(0, -.19, T["note"], fontsize=7, color=GREY, transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(FIG / f"sat1-ladder-{lang}.png", bbox_inches="tight"); plt.close(fig)


def fig_leak(runs, lang):
    T = {"ru": dict(title="Пользуется ли политика наблюдением: подменяем наблюдение нулями",
                    ylabel="решено при нулевом наблюдении, из 120",
                    note="Если качество не падает при нулевом входе, политика наблюдением не пользуется. Серая линия — уровень «всегда менять значение», то есть случайный перебор."),
         "en": dict(title="Does the policy use its observation? Replace the observation with zeros",
                    ylabel="solved with a zeroed observation, out of 120",
                    note="If performance does not drop with a zero input, the policy is not using the observation. The grey line is the “always flip” level, that is, random search.")}[lang]
    keys = [k for k in ["heuristic", "linear-raw-clone", "fly-clone", "fly-shuffled-clone", "fly-random-clone", "random"] if k in runs]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for i, key in enumerate(keys):
        vals = [l["leak_checks"]["zero_obs_solved"] for l in runs[key]]
        ax.bar(i, np.mean(vals), .58, color=COLOURS[key],
               yerr=[[np.mean(vals) - min(vals)], [max(vals) - np.mean(vals)]] if len(vals) > 1 else None,
               capsize=3, error_kw=dict(lw=.8, ecolor="#444"))
        ax.text(i, np.mean(vals) + 3, f"{np.mean(vals):.0f}", ha="center", fontsize=7.5)
    if "random" in runs:
        base = np.mean([l["leak_checks"]["zero_obs_solved"] for l in runs["random"]])
        ax.axhline(base, color=GREY, lw=1, ls="--")
    ax.set_xticks(range(len(keys)))
    ax.set_xticklabels([SHORT[lang][k] for k in keys], fontsize=7.8)
    ax.set_ylabel(T["ylabel"]); ax.set_ylim(0, 125)
    ax.set_title(T["title"], fontsize=10, loc="left")
    ax.text(0, -.30, T["note"], fontsize=7, color=GREY, transform=ax.transAxes)
    fig.tight_layout(); fig.savefig(FIG / f"sat2-leakcheck-{lang}.png", bbox_inches="tight"); plt.close(fig)


def fig_complexity(runs, lang):
    T = {"ru": dict(title="Empirical complexity of Drosophila-based SAT solving",
                    sub="случайный 3-SAT, m ≈ 4.26 n; медиана по решённым формулам, планки — разброс между запусками",
                    xlabel="переменных n", ylabel="решений до выполняющего присваивания"),
         "en": dict(title="Empirical complexity of Drosophila-based SAT solving",
                    sub="random 3-SAT, m ≈ 4.26 n; median over solved instances, whiskers show the spread across runs",
                    xlabel="variables n", ylabel="decisions to a satisfying assignment")}[lang]
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    fits = {}
    for key in ORDER:
        if key not in runs:
            continue
        M = np.array([[per_size(sat_records(l)).get(n, {}).get("median_steps", np.nan) for n in SIZES] for l in runs[key]], dtype=float)
        y = np.nanmean(M, 0)
        ok = ~np.isnan(y)
        if ok.sum() >= 3:
            slope = np.polyfit(np.log(np.array(SIZES)[ok]), np.log(y[ok]), 1)[0]
            fits[key] = round(float(slope), 2)
        lo = y - np.nanmin(M, 0) if len(M) > 1 else None
        hi = np.nanmax(M, 0) - y if len(M) > 1 else None
        ax.errorbar(SIZES, y, yerr=[lo, hi] if lo is not None else None, marker="o", ms=4, capsize=2.5,
                    color=COLOURS[key], lw=1.6, label=LABELS[lang][key] + (f"   ∝ n^{fits[key]:.2f}" if key in fits else ""))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(SIZES); ax.set_xticklabels(SIZES); ax.minorticks_off()
    ax.set_xlabel(T["xlabel"]); ax.set_ylabel(T["ylabel"])
    ax.grid(alpha=.25, which="both")
    ax.legend(fontsize=7.5, frameon=False, loc="upper left")
    ax.set_title(T["title"] + "\n" + T["sub"], fontsize=10, loc="left")
    fig.tight_layout(); fig.savefig(FIG / f"sat3-complexity-{lang}.png", bbox_inches="tight"); plt.close(fig)
    (S / "powerlaw-fits.json").write_text(json.dumps(
        {"note": "log-log slope of median decisions to solution against n, over solved instances only; success rate falls with n, so this is a description of the solved subset and NOT a complexity measurement",
         "slopes": fits}, indent=1))
    return fits


if __name__ == "__main__":
    runs = load()
    print("runs:", {k: len(v) for k, v in sorted(runs.items())})
    for lang in ("ru", "en"):
        fig_ladder(runs, lang); fig_leak(runs, lang); fits = fig_complexity(runs, lang)
    print("power-law slopes:", fits)
    table = {}
    for key, logs in runs.items():
        table[key] = {"runs": len(logs),
                      "clone_accuracy": [l.get("clone", {}).get("clone_train_accuracy") for l in logs] if key.endswith("clone") else None,
                      "zero_obs_solved_of_120": [l["leak_checks"]["zero_obs_solved"] for l in logs],
                      "unsat_claimed_solved": sum(l["leak_checks"]["unsat_claimed_solved"] for l in logs),
                      "per_size_success": {n: round(float(np.mean([per_size(sat_records(l)).get(n, {}).get("success", np.nan) for l in logs])), 3) for n in SIZES}}
    (S / "summary-table.json").write_text(json.dumps(table, indent=1))
    print("saved", S / "summary-table.json")
