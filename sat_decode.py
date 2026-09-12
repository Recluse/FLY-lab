"""Diagnostic: can a linear decoder read the observation bits out of the reservoir response at all?

Explains (or refutes) the RL failure. For each reservoir we drive it with the same random-walk episodes the agents
see, record (bits at tick t, features at tick t), and fit logistic regression per bit with a train/test split.
Also decodes the PREVIOUS tick's bits from the current features: that measures the memory the LIF state carries.
Chance level is reported as the majority-class rate of the same test split.
"""
import argparse
import json
import random
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "sat-fly"
BITS = ("value", "pos_in_unsat", "neg_in_unsat")


def collect(kind, seed, episodes):
    from sat_fly import Env, FlyReservoir, OUT as SAT_OUT
    sets = json.loads((SAT_OUT / "formulas.json").read_text())
    train = [f for f in sets["train"] if f["satisfiable"]]
    feat = FlyReservoir(shuffle_seed=4000 + seed if kind == "fly-shuffled" else None,
                        random_seed=4000 + seed if kind == "fly-random" else None)
    rng = random.Random(f"decode:{kind}:{seed}")
    X, Y, Yprev = [], [], []
    for _ in range(episodes):
        env = Env(rng.choice(train), rng)
        feat.reset(rng.getrandbits(32))
        prev = None
        while not env.solved() and env.steps < env.budget:
            i = env.next_variable()
            obs = env.observe(i)
            f = feat(obs)
            X.append(f)
            Y.append(obs)
            Yprev.append(prev if prev is not None else (-1, -1, -1))
            prev = obs
            env.act(i, rng.randint(0, 1))
    return np.array(X), np.array(Y), np.array(Yprev), feat.wiring


def fit_logistic(X, y, iters=400, lr=.5, l2=1e-3):
    """Plain gradient-descent logistic regression on standardised features (no sklearn in this venv)."""
    w, b = np.zeros(X.shape[1]), 0.
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = p - y
        w -= lr * (X.T @ g / len(y) + l2 * w)
        b -= lr * g.mean()
    return w, b


def decode(X, Y, Yprev):
    n = len(X)
    split = int(.7 * n)
    mu, sd = X[:split].mean(0), X[:split].std(0) + 1e-9
    Xs = (X - mu) / sd
    out = {}
    for name, target in (("current", Y), ("previous", Yprev)):
        rows = {}
        for k, bit in enumerate(BITS):
            y = target[:, k]
            mask = y >= 0  # previous-tick labels are -1 on the first decision of an episode
            Xtr, ytr = Xs[:split][mask[:split]], y[:split][mask[:split]]
            Xte, yte = Xs[split:][mask[split:]], y[split:][mask[split:]]
            if len(np.unique(ytr)) < 2 or len(yte) < 20:
                rows[bit] = {"note": "degenerate label"}
                continue
            w, b = fit_logistic(Xtr, ytr)
            pred = ((Xte @ w + b) > 0).astype(int)
            chance = max(yte.mean(), 1 - yte.mean())
            rows[bit] = {"test_accuracy": round(float((pred == yte).mean()), 3), "majority_class_rate": round(float(chance), 3),
                         "n_test": int(len(yte)), "positive_rate": round(float(yte.mean()), 3)}
        out[name] = rows
    return out


def main(args):
    report = {}
    for kind in args.kinds:
        t = time.time()
        X, Y, Yprev, wiring = collect(kind, args.seed, args.episodes)
        report[kind] = {"n_samples": int(len(X)), "feature_dim": int(X.shape[1]), "mean_feature_norm": round(float(np.linalg.norm(X, axis=1).mean()), 3),
                        "nonzero_feature_fraction": round(float((X != 0).mean()), 4), "wiring": wiring, "decoding": decode(X, Y, Yprev),
                        "collect_wall_s": round(time.time() - t, 1)}
        print(kind, json.dumps(report[kind]["decoding"]), flush=True)
    name = OUT / f"decodability-{'-'.join(args.kinds)}-s{args.seed}.json"
    name.write_text(json.dumps(report, indent=1))
    print("saved", name)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--kinds", nargs="+", default=["fly", "fly-shuffled", "fly-random"])
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--episodes", type=int, default=60)
    main(p.parse_args())
