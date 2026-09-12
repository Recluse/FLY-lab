"""Aggregate screen783-* runs: DNa rates, avalanche flag, lateralized descending readouts. Read-only over results/."""
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
ANN = ROOT / "vendor/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv"
AVALANCHE_ACTIVE = 3000  # ponytail: threshold from left(503) vs right(8723) sugar runs; revisit if screen shows a continuum


def md(df):
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(lines)


def load_runs(prefix):
    rows = []
    for folder in sorted(ROOT.glob(f"results/{prefix}*")):
        if not folder.is_dir() or not (folder / "summary.json").exists():
            continue
        s = json.loads((folder / "summary.json").read_text())
        rows.append({"label": folder.name, "cell_class": s.get("cell_class"), "sub_class": s.get("cell_sub_class"), "side": s["input_side"], "hz": s["input_hz"],
                     "n_inputs": s["n_inputs"], "spikes": s["spikes"], "active": s["active_neurons"], **{k: round(v, 1) for k, v in s["output_hz"].items()},
                     "avalanche": s["active_neurons"] > AVALANCHE_ACTIVE, "wall_s": round(s["wall_s"])})
    return pd.DataFrame(rows)


def dn_rates(label, ann):
    spikes = pd.read_parquet(ROOT / "results" / label / "spikes.parquet")
    counts = spikes.groupby("flywire_id").size().rename("spikes").reset_index()
    counts["flywire_id"] = counts["flywire_id"].astype("int64")
    dn = ann[ann.super_class == "descending"][["root_id", "side", "cell_type"]]
    return dn.merge(counts, left_on="root_id", right_on="flywire_id", how="left").fillna({"spikes": 0})


def lateralization(runs, ann):
    """For each class with both sides run and no avalanche: DN types whose ipsilateral copy responds to ipsilateral input on both sides."""
    out = []
    for (c, sc, hz), grp in runs.groupby(["cell_class", "sub_class", "hz"]):
        sides = dict(zip(grp.side, grp.label))
        if {"left", "right"} - set(sides) or grp.avalanche.any():
            continue
        left, right = dn_rates(sides["left"], ann), dn_rates(sides["right"], ann)
        merged = left.merge(right, on=["root_id", "side", "cell_type"], suffixes=("_Lin", "_Rin"))
        merged = merged[merged.side.isin(["left", "right"]) & merged.cell_type.notna()]
        for ct, g in merged.groupby("cell_type"):
            ipsi = g[g.side == "left"].spikes_Lin.sum() + g[g.side == "right"].spikes_Rin.sum()
            contra = g[g.side == "left"].spikes_Rin.sum() + g[g.side == "right"].spikes_Lin.sum()
            if ipsi + contra == 0:
                continue
            out.append({"cell_class": c, "sub_class": sc, "hz": hz, "DN_type": ct, "n_cells": len(g), "ipsi_spikes": int(ipsi), "contra_spikes": int(contra),
                        "index": round((ipsi - contra) / (ipsi + contra), 2)})
    return pd.DataFrame(out)


if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else "screen783-"
    ann = pd.read_csv(ANN, sep="\t", low_memory=False)
    ann["root_id"] = ann["root_id"].astype("int64")
    runs = load_runs(prefix)
    out = ROOT / "results" / (prefix.rstrip("-") + "-analysis")
    out.mkdir(exist_ok=True)
    runs.to_csv(out / "runs.csv", index=False)
    lat = lateralization(runs, ann)
    lat.sort_values(["index", "ipsi_spikes"], ascending=False).to_csv(out / "lateralization.csv", index=False)
    with (out / "summary.md").open("w") as f:
        f.write("# Screen 783: runs\n\n" + md(runs.drop(columns=["label"])) + "\n\n")
        strong = lat[(lat.ipsi_spikes + lat.contra_spikes >= 20)].sort_values("index", ascending=False)
        f.write("# Lateralized descending types (|index| = (ipsi-contra)/(ipsi+contra), both-side consistent, no-avalanche classes only, >=20 spikes)\n\n")
        f.write(md(strong.head(60)) + "\n")
    print(runs.drop(columns=["label"]).to_string(index=False))
    print(f"\nlateralization rows: {len(lat)}; written to {out}")
