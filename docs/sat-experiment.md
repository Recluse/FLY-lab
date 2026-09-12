# A fly brain and an NP-complete problem

A side experiment: using the *Drosophila* connectome as a fixed reservoir for Boolean satisfiability. The full write-up with figures is [`paper/sat-en.pdf`](../paper/sat-en.pdf) (Russian: [`paper/sat-ru.pdf`](../paper/sat-ru.pdf)). Nothing in the main experiment depends on this one.

**The honest headline.** The connectome cannot solve SAT, does not scale, and none of this bears on P versus NP. What it does do is conduct the task's information to its output neurons far better than either null model of the same size — well enough that a single linear layer can approximate a hand-written rule, which neither null model manages at all.

## Setup

Random 3-SAT at the hard ratio, m ≈ 4.26 n. Training: n ∈ {3, 4, 5, 6}, forty satisfiable formulas each. In-distribution test: the same sizes, thirty satisfiable plus ten unsatisfiable each, disjoint from training by canonical form. Extrapolation test: n ∈ {8, 10, 12}, same counts. Exhaustive search labels satisfiability and verifies every claimed solution; it never enters a policy.

The agent inspects one variable at a time, in an order reshuffled every sweep, and decides flip or keep. Its observation is three bits: the variable's value, whether it occurs positively in an unsatisfied clause, and whether it occurs negatively in one. The same scorer applies to every variable and the variable count appears nowhere, so n = 12 is genuine extrapolation from n ≤ 6. Budget: 8n decisions.

Three reservoirs are compared, differing **only** in wiring: the real v783 connectome, a degree-preserving shuffle of it, and a random topology with the same neuron count, edge count and weight multiset. In all three, the observation bits plus one always-on channel drive four groups of forty head-bristle neurons through the model's own Poisson inputs; the network advances 15 ms per decision; the features are the fresh spikes of all 1,299 descending neurons. Only a linear layer is trained.

## Results

### The first attempt failed a leak check, not the task

Reinforcement learning produced policies that solved as many instances with a **zeroed observation** as with the real one (97–114 of 120 against 104–110). They had learned "always flip" and nothing else. Judged on solve rate alone they looked functional. The first version also lacked the always-on input channel, so the state "variable is in no unsatisfied clause" produced an all-zero feature vector; those runs are kept in `results/sat-fly/v1-no-tonic/` as a negative control.

### The information is present, and the topology decides how much

A linear decoder recovering the three observation bits from one 15 ms tick of descending activity:

| Reservoir | value | "+" in unsat | "−" in unsat | previous tick | active per tick |
|---|---:|---:|---:|---:|---:|
| Fly connectome | 98.6% | 94.8% | 99.7% | 87–98% | 3.5% |
| Shuffled, degrees preserved | 72.5% | 68.1% | 73.1% | 77–81% | 0.09% |
| Random topology | 68.8% | 73.3% | 64.2% | 63–66% | 0.03% |

Chance is 50–59% depending on the bit. So the reinforcement-learning failure was one of optimisation, not of representation.

### Cloning the honest rule separates the reservoirs cleanly

The same linear layer trained by supervision to reproduce the honest local rule's decisions, on states visited under a mixed policy. Three seeds each.

| Reservoir | cloning accuracy | solved, n ≤ 6 | solved, n ∈ {8,10,12} | zeroed-observation control |
|---|---:|---:|---:|---:|
| Honest rule (no learning) | — | 108–116 / 120 | 51–54 / 90 | 7–15 / 120 |
| Raw bits, no fly | 100% | 107–112 / 120 | 47–52 / 90 | 11–20 / 120 |
| Fly connectome | 96.5–96.9% | 107–110 / 120 | 36–43 / 90 | 43–53 / 120 |
| Shuffled connectome | 84.8–85.8% | 103–105 / 120 | 22–25 / 90 | 100–110 / 120 |
| Random topology | 84.7–85.9% | 103–104 / 120 | 20–27 / 90 | 98–105 / 120 |
| Random search | — | 85–94 / 120 | 5–10 / 90 | 92–94 / 120 |

The majority class in the cloning data has frequency 0.86, so 84.7–85.9% means the surrogate layers learned nothing beyond "flip". The ablation column agrees: the connectome policy loses most of its performance with a blanked observation, the surrogates lose nothing because they never used it.

The connectome still trails direct access to the three bits, 36–43 against 47–52, because four per cent of cloning errors compound across an episode of up to 96 decisions.

### The scaling exponent is not a complexity measurement

Fitted log-log slopes of median decisions-to-solution against n: honest rule 1.83, raw-bit clone 2.21, connectome 2.06, shuffled 2.12, random topology 2.07, random search 1.54. Every one looks polynomial and none of them means anything: the median is taken over solved instances only while the solved fraction collapses with n, the budget is capped at 8n, and random search — which cannot have good complexity — shows the flattest slope of all. See `results/sat-fly/powerlaw-fits.json`, which carries the same warning.

## Checks

- No policy has access to the formula, the solution or the oracle; it receives one three-bit tuple per decision.
- No agent ever "solved" an unsatisfiable formula, in any run.
- Training and test sets are disjoint by canonical form, with no duplicates within a set.
- Averaged over all satisfying assignments, P(variable is true) ranges 0.39–0.54 across positions; the agent never sees a variable index in any case.
- Positive-literal fraction is 0.489–0.498 across all three sets.
- Every learned policy is reported with the zeroed-observation ablation.

Dataset checks are in `results/sat-fly/dataset-checks.json`; the per-agent summary is in `results/sat-fly/summary-table.json`.

## Reproducing

```sh
.venv-brain/bin/python sat_fly.py check
.venv-brain/bin/python sat_fly.py gen
.venv-brain/bin/python sat_fly.py run --agent random    --seed 0
.venv-brain/bin/python sat_fly.py run --agent heuristic --seed 0
.venv-brain/bin/python sat_fly.py run --agent linear-raw   --seed 0 --clone
.venv-brain/bin/python sat_fly.py run --agent fly          --seed 0 --clone
.venv-brain/bin/python sat_fly.py run --agent fly-shuffled --seed 0 --clone
.venv-brain/bin/python sat_fly.py run --agent fly-random   --seed 0 --clone
.venv-brain/bin/python sat_decode.py --kinds fly --seed 0 --episodes 60
.venv-body/bin/python paper/sat_figures.py
```

`--shaping` selects the reinforcement-learning variant instead of `--clone`. A reservoir run takes roughly forty minutes on one core; keep at most four in parallel on a 32 GB machine. The random-topology null is generated with `brain_loop.py --make-random 4000 4001 4002`.
