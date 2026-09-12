"""3-SAT with the connectome as a fixed reservoir: only a linear readout learns. Separate from the NeuroMechFly pilot.

Interface (size-agnostic): the agent inspects one variable at a time and decides flip / keep. Observation per
decision = 3 bits: current value x_i, "x_i appears positively in an unsatisfied clause", "x_i appears negatively in
an unsatisfied clause". Nothing else reaches any agent. The brute-force oracle only labels sat/unsat and verifies
claimed solutions; it is never consulted by a policy. Reward: +1 on solving; optional shaping by change in satisfied-clause count (computed from the same
observation-level information, reported separately); discounted returns (gamma 0.9), no per-decision cost.
"""
import argparse
import itertools
import json
import math
import random
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "results" / "sat-fly"
RATIO = 4.26
BUDGET_PER_VAR = 8  # decisions allowed = BUDGET_PER_VAR * n


# ---------------------------------------------------------------- formulas and oracle
def generate(n, m, rng):
    clauses = []
    while len(clauses) < m:
        vs = rng.sample(range(n), 3)
        clauses.append(tuple(sorted((v + 1) * (1 if rng.random() < .5 else -1) for v in vs)))
    return clauses


def satisfied_count(clauses, x):
    return sum(any((x[abs(l) - 1] == 1) == (l > 0) for l in c) for c in clauses)


def oracle_satisfiable(clauses, n):
    """Brute force; n <= 12. Used only for labelling instances and verifying claimed solutions."""
    return any(satisfied_count(clauses, x) == len(clauses) for x in itertools.product((0, 1), repeat=n))


def make_dataset(seed, sizes, n_sat, n_unsat):
    rng = random.Random(f"sat-fly:{seed}")
    rows = []
    for n in sizes:
        m = max(1, round(RATIO * n))
        got = {True: 0, False: 0}
        while got[True] < n_sat or got[False] < n_unsat:
            clauses = generate(n, m, rng)
            sat = oracle_satisfiable(clauses, n)
            if got[sat] < (n_sat if sat else n_unsat):
                got[sat] += 1
                rows.append({"n": n, "m": m, "clauses": [list(c) for c in clauses], "satisfiable": sat})
    return rows


# ---------------------------------------------------------------- environment
class Env:
    def __init__(self, formula, rng):
        self.n, self.clauses = formula["n"], [tuple(c) for c in formula["clauses"]]
        self.m = len(self.clauses)
        self.rng = rng
        self.x = [rng.randint(0, 1) for _ in range(self.n)]
        self.budget = BUDGET_PER_VAR * self.n
        self.steps = 0
        self.order = []

    def unsatisfied(self):
        return [c for c in self.clauses if not any((self.x[abs(l) - 1] == 1) == (l > 0) for l in c)]

    def solved(self):
        return not self.unsatisfied()

    def next_variable(self):
        if not self.order:  # random sweep order, refreshed every sweep: no variable-order leak
            self.order = list(range(self.n))
            self.rng.shuffle(self.order)
        return self.order.pop()

    def observe(self, i):
        unsat = self.unsatisfied()
        pos = any((i + 1) in c for c in unsat)
        neg = any(-(i + 1) in c for c in unsat)
        return (self.x[i], int(pos), int(neg))  # the ONLY information any agent receives

    def act(self, i, flip):
        before = self.m - len(self.unsatisfied())
        if flip:
            self.x[i] ^= 1
        self.steps += 1
        after = self.m - len(self.unsatisfied())
        return after - before


# ---------------------------------------------------------------- agents
class RandomAgent:
    name = "random"
    def features(self, obs): return None
    def p_flip(self, f, obs): return .5
    def update(self, *a): pass


class HeuristicAgent:
    """Honest local rule on the same 3 bits: flip iff the variable sits in an unsatisfied clause (WalkSAT-like, no break counts)."""
    name = "heuristic"
    def features(self, obs): return None
    def p_flip(self, f, obs): return 1. if (obs[1] or obs[2]) else 0.
    def update(self, *a): pass


class LinearAgent:
    """Logistic policy p(flip) = sigmoid(w.f + b) trained by REINFORCE. Features come from `featurizer`."""
    def __init__(self, name, dim, rng, lr=.5, gamma=.5):
        self.name, self.rng, self.lr, self.gamma = name, rng, lr, gamma
        self.w = np.zeros(dim)
        self.b = 0.
        self.baseline = 0.

    def p_flip(self, f, obs):
        return 1 / (1 + math.exp(-float(self.w @ f + self.b)))

    def update(self, trajectory):
        # trajectory: list of (features, action, reward); REINFORCE with return-to-go and a running mean baseline
        G, grads_w, grads_b = 0., np.zeros_like(self.w), 0.
        returns = []
        for _, _, r in reversed(trajectory):
            G = r + self.gamma * G  # discounted return-to-go keeps credit local to the decision
            returns.append(G)
        returns.reverse()
        for (f, a, _), G in zip(trajectory, returns):
            adv = G
            p = self.p_flip(f, None)
            g = (a - p)  # d log pi / d logit
            grads_w += adv * g * f
            grads_b += adv * g
        # no running baseline: with a shared bias and skewed state frequencies it pushed the policy toward 'always flip'
        self.w += self.lr * grads_w  # summed over decisions: rewards are O(1/m), a per-step mean learned too slowly
        self.b += self.lr * grads_b


class RawFeatures:
    """The 3 observation bits plus their complement 'free' (not in any unsatisfied clause), so a linear policy can
    express keep-vs-flip per state without relying on the shared bias."""
    dim = 4
    def __call__(self, obs): return np.array([*obs, 1 - max(obs[1], obs[2])], dtype=float)
    def reset(self, seed=None): pass


class FlyReservoir:
    """v783 connectome (or its degree-preserving shuffle) as a fixed reservoir. Three head-bristle groups are the input
    channels for the three observation bits; features are the new spikes of every descending neuron in 15 ms."""
    def __init__(self, shuffle_seed=None, random_seed=None, neurons_per_channel=40, tick_ms=15):
        import brian2 as b
        import pandas as pd
        sys.path.insert(0, str(ROOT / "vendor/Drosophila_brain_model"))
        import model
        from brain_loop import ANN, shuffled_connectivity, random_connectivity, BRAIN
        self.b, self.tick_ms = b, tick_ms
        ann = pd.read_csv(ANN, sep="\t", low_memory=False)
        ann["root_id"] = ann["root_id"].astype("int64")
        comp, con = BRAIN / "Completeness_783.csv", BRAIN / "Connectivity_783.parquet"
        index = pd.read_csv(comp, index_col=0).index
        mapping = {int(v): i for i, v in enumerate(index)}
        hb = ann[(ann.cell_class == "mechanosensory") & (ann.cell_sub_class == "head bristle")]
        left = sorted(mapping[int(r)] for r in hb[hb.side == "left"].root_id)
        right = sorted(mapping[int(r)] for r in hb[hb.side == "right"].root_id)
        k = neurons_per_channel
        # bits: value, positive-in-unsat, negative-in-unsat, plus a constant-on channel so that the all-zero observation
        # still drives the network (v1 without it produced zero features there and the readout could only learn a bias)
        self.channels = [left[:k], right[:k], left[k:2 * k], right[k:2 * k]]
        dn = ann[ann.super_class == "descending"]
        self.dn = np.array(sorted(mapping[int(r)] for r in dn.root_id if int(r) in mapping))
        self.dim = len(self.dn)
        b.start_scope()
        b.defaultclock.dt = .1 * b.ms
        params = model.default_params.copy()
        if shuffle_seed is not None:
            con = shuffled_connectivity(con, shuffle_seed)
        if random_seed is not None:
            con = random_connectivity(con, random_seed)
        neu, syn, self.monitor = model.create_model(comp, con, params)
        self.pois = []
        for ch in self.channels:
            p, neu = model.poi(neu, ch, [], params)
            self.pois.append(p)
        self.net = b.Network(neu, syn, self.monitor, *[p for ch in self.pois for p in ch])
        self.net.store("init")
        self.prev = np.zeros(len(index), dtype=int)
        self.wiring = {"materialization": 783, "shuffle_seed": shuffle_seed, "random_seed": random_seed, "channels": "head bristle left[:k], right[:k], left[k:2k], right[k:2k]=constant on", "neurons_per_channel": k,
                       "readout_population": "all annotated descending neurons present in model", "n_readout": int(self.dim), "tick_ms": tick_ms}

    def reset(self, seed=None):
        self.net.restore("init", restore_random_state=True)
        if seed is not None:
            self.b.seed(seed)  # per-episode Poisson noise is reproducible from the agent RNG
        self.prev = np.zeros_like(self.prev)

    def __call__(self, obs):
        for bit, ch in zip((*obs, 1), self.pois):
            for p in ch:
                p.active = bool(bit)
        self.net.run(self.tick_ms * self.b.ms)
        counts = np.asarray(self.monitor.count[:])
        new = counts - self.prev
        self.prev = counts
        return new[self.dn] / 4.  # typical norm ~1-2, comparable to the raw-bit features so both readouts learn at similar rates


# ---------------------------------------------------------------- episodes
def run_episode(agent, featurizer, formula, rng, shaping=False, train=False, zero_obs=False):
    env = Env(formula, rng)
    featurizer.reset(rng.getrandbits(32))
    trajectory = []
    t0 = time.monotonic()
    while not env.solved() and env.steps < env.budget:
        i = env.next_variable()
        obs = env.observe(i)
        if zero_obs:
            obs = (0, 0, 0)
        f = featurizer(obs)
        p = agent.p_flip(f, obs)
        a = int(rng.random() < p)
        delta = env.act(i, a)
        # shaped: reward is only the change in satisfied clauses (solving = all of them); unshaped: +1 at solving only.
        # A terminal bonus on top of shaping inflated the shared bias toward 'always flip' because the last decision is always a flip.
        r = (delta / env.m) if shaping else (1. if env.solved() else 0.)
        trajectory.append((f, a, r))
    if train and trajectory:
        agent.update(trajectory)
    solved = env.solved()
    if solved:
        assert satisfied_count(env.clauses, env.x) == env.m  # oracle-level verification of the claimed solution
    return {"n": env.n, "m": env.m, "satisfiable": formula["satisfiable"], "solved": solved, "steps": env.steps, "budget": env.budget,
            "sweeps": env.steps / env.n, "wall_s": time.monotonic() - t0, "return": sum(r for _, _, r in trajectory)}


def clone_train(agent, featurizer, formulas, rng, samples=4000, iters=600, lr=.5, l2=1e-3):
    """Supervised upper bound: fit the SAME linear readout to reproduce the honest local rule's decision from the
    reservoir features. Data is collected under a mixed policy (heuristic with 25% random flips) so the states visited
    are not only the rule's own. This asks 'can this reservoir support the rule at all', not 'can RL find it'."""
    X, Y = [], []
    rule = HeuristicAgent()
    while len(X) < samples:
        env = Env(rng.choice(formulas), rng)
        featurizer.reset(rng.getrandbits(32))
        while not env.solved() and env.steps < env.budget and len(X) < samples:
            i = env.next_variable()
            obs = env.observe(i)
            X.append(featurizer(obs))
            Y.append(int(rule.p_flip(None, obs)))
            env.act(i, rng.randint(0, 1) if rng.random() < .25 else int(rule.p_flip(None, obs)))
    X, Y = np.array(X), np.array(Y, dtype=float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Xs = (X - mu) / sd
    w, b = np.zeros(X.shape[1]), 0.
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(Xs @ w + b)))
        g = p - Y
        w -= lr * (Xs.T @ g / len(Y) + l2 * w)
        b -= lr * g.mean()
    accuracy = float((((Xs @ w + b) > 0).astype(float) == Y).mean())
    agent.w, agent.b = w / sd, float(b - (mu / sd) @ w)  # fold standardisation into the weights
    return {"clone_train_samples": len(Y), "clone_train_accuracy": round(accuracy, 4), "clone_positive_rate": round(float(Y.mean()), 3)}


def build(agent_name, seed, shuffle_seed=None):
    rng = random.Random(f"sat-fly-agent:{agent_name}:{seed}")
    if agent_name == "random":
        return RandomAgent(), RawFeatures(), rng
    if agent_name == "heuristic":
        return HeuristicAgent(), RawFeatures(), rng
    if agent_name == "linear-raw":
        return LinearAgent("linear-raw", 4, rng), RawFeatures(), rng
    if agent_name in ("fly", "fly-shuffled", "fly-random"):
        feat = FlyReservoir(shuffle_seed=(4000 + seed) if agent_name == "fly-shuffled" else None,
                            random_seed=(4000 + seed) if agent_name == "fly-random" else None)
        return LinearAgent(agent_name, feat.dim, rng), feat, rng
    raise ValueError(agent_name)


def main(args):
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "gen":
        sets = {"train": make_dataset("train", [3, 4, 5, 6], 40, 0),
                "test-in": make_dataset("test-in", [3, 4, 5, 6], 30, 10),
                "test-out": make_dataset("test-out", [8, 10, 12], 30, 10)}
        canon = lambda f: (f["n"], tuple(sorted(tuple(c) for c in f["clauses"])))
        train_keys = {canon(f) for f in sets["train"]}
        for name in ("test-in", "test-out"):
            sets[name] = [f for f in sets[name] if canon(f) not in train_keys]
        (OUT / "formulas.json").write_text(json.dumps(sets))
        print({k: len(v) for k, v in sets.items()})
        return
    if args.mode == "check":
        selfcheck()
        return
    sets = json.loads((OUT / "formulas.json").read_text())
    agent, featurizer, rng = build(args.agent, args.seed)
    tag = f"{args.agent}-s{args.seed}" + ("-clone" if args.clone else ("-shaped" if args.shaping else ""))
    log = {"agent": args.agent, "seed": args.seed, "shaping": args.shaping, "wiring": getattr(featurizer, "wiring", None), "train": [], "eval": {}, "leak_checks": {}}
    if isinstance(agent, LinearAgent) and args.clone:
        log["clone"] = clone_train(agent, featurizer, [f for f in sets["train"] if f["satisfiable"]], random.Random(f"clone:{args.seed}"))
        print(json.dumps(log["clone"]), flush=True)
    elif isinstance(agent, LinearAgent):
        train_rng = random.Random(f"sat-fly-train:{args.seed}")
        sat_train = [f for f in sets["train"] if f["satisfiable"]]
        for ep in range(args.episodes):
            f = train_rng.choice(sat_train)
            rec = run_episode(agent, featurizer, f, rng, shaping=args.shaping, train=True)
            rec["episode"] = ep
            log["train"].append(rec)
            if ep % 25 == 0:
                recent = log["train"][-25:]
                print(f"train ep {ep} solved {sum(r['solved'] for r in recent)}/{len(recent)} mean steps {np.mean([r['steps'] for r in recent]):.1f}", flush=True)
        log["weights"] = {"w_norm": float(np.linalg.norm(agent.w)), "b": agent.b}
    for split in ("test-in", "test-out"):
        log["eval"][split] = [run_episode(agent, featurizer, f, rng) for f in sets[split]]
        print(split, "solved", sum(r["solved"] for r in log["eval"][split] if r["satisfiable"]), "of", sum(r["satisfiable"] for r in log["eval"][split]),
              "| unsat claimed solved:", sum(r["solved"] for r in log["eval"][split] if not r["satisfiable"]), flush=True)
    # leak checks: zeroed observations must collapse the policy; unsat instances must never be "solved"
    sat_in = [f for f in sets["test-in"] if f["satisfiable"]]
    log["leak_checks"]["zero_obs_solved"] = sum(run_episode(agent, featurizer, f, rng, zero_obs=True)["solved"] for f in sat_in)
    log["leak_checks"]["zero_obs_denominator"] = len(sat_in)
    log["leak_checks"]["unsat_claimed_solved"] = sum(r["solved"] for s in log["eval"].values() for r in s if not r["satisfiable"])
    (OUT / f"{tag}.json").write_text(json.dumps(log))
    print("saved", OUT / f"{tag}.json")


def selfcheck():
    rng = random.Random(0)
    assert oracle_satisfiable([(1, 2, 3)], 3) and not oracle_satisfiable([(1,), (-1,)], 1)
    f = {"n": 3, "m": 1, "clauses": [[1, 2, 3]], "satisfiable": True}
    env = Env(f, random.Random(1))
    env.x = [0, 0, 0]
    assert env.observe(0) == (0, 1, 0) and not env.solved()
    assert env.act(0, 1) == 1 and env.solved()
    rec = run_episode(HeuristicAgent(), RawFeatures(), f, random.Random(2))
    assert rec["solved"] and rec["steps"] <= 3
    # a linear agent on raw features must learn the trivial rule "flip when in an unsatisfied clause"
    agent = LinearAgent("t", 4, rng, lr=.5)
    data = make_dataset("check", [3, 4], 20, 0)
    for _ in range(300):
        run_episode(agent, RawFeatures(), rng.choice(data), rng, shaping=True, train=True)
    solved = sum(run_episode(agent, RawFeatures(), d, rng)["solved"] for d in data)
    assert solved >= .8 * len(data), solved
    print("sat_fly selfcheck passed; trained linear-raw solved", solved, "of", len(data))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["gen", "run", "check"])
    p.add_argument("--agent", choices=["random", "heuristic", "linear-raw", "fly", "fly-shuffled", "fly-random"], default="random")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--episodes", type=int, default=400)
    p.add_argument("--shaping", action="store_true")
    p.add_argument("--clone", action="store_true", help="supervised: fit the readout to the honest rule instead of REINFORCE")
    main(p.parse_args())
