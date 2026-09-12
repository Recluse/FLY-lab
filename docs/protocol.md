# Protocol

Everything in this file was written down before the corresponding test outcomes were looked at. Where something had to be corrected, the correction and the reason for it are recorded rather than quietly applied.

## The shared chain

Local sensors → swappable action-selection module → shared command adapter → stock `HybridTurningController` → NeuroMechFly body. Physics timestep 0.1 ms; the command is refreshed every 15 ms, which is 150 physics steps. Vision is disabled in every variant. A fresh body is created for every episode, which also rules out any leakage of the controller's persistence counter through the library's own reset.

The adapter takes a dimensionless speed in [0, 1] and a turn in [−1, 1] and produces `drive_left = speed·(1 − 0.5·turn)` and `drive_right = speed·(1 + 0.5·turn)`, both within [0, 1.5]. Physical speed is measured separately; a zero drive is never treated as proof of stopping without measuring the body's velocity. The adapter accepts finite numbers only.

No module receives coordinates, event times, future observations or a clock. The evaluator reads the event stream separately from the controller.

## Variants

**A** — constant command: speed 0.8, turn 0.

**B** — a memoryless rule on the same two sensory channels: turn 1 when the left channel is at or above 0.5, −1 when the right one is, 0 when both have the same status. In the stopping task, speed 0 when either channel is at or above 0.5.

**C** — the connectome. Input: every annotated mechanosensory head-bristle cell of materialisation 783, 150 on the left and 155 on the right, where side means the side at which the nerve enters. Excitation uses the model's own `PoissonInput` (N = 1, 150 Hz, weight = `w_syn·f_poi`), switched on and off through the `active` flag according to the local sensor of the same side, threshold 0.5. Toggling `active` does not reset the network state; this was verified with the pulse probes. The network is created once per episode, with network seed 10000 + episode seed, and its state is preserved between ticks.

Output: every annotated descending neuron with side left or right, 645 and 646 respectively; four further annotated descending neurons are absent from the model and are recorded as excluded. For every 15 ms tick the new spikes of the left and right populations are counted as L and R. The individual rates of DNa01 and DNa02 are stored as a secondary measurement and take no part in the command.

Readout: `x_k = ema·x_{k−1} + (1 − ema)·(L_k − R_k)`, and `turn_k = 0` when `|x_k| < deadband`, otherwise `clip(gain·x_k, −1, 1)`. Speed is 0.8, the same constant as in A; the brain chooses only the turn. Only ticks up to and including k are used. The three parameters were chosen once, on calibration seeds 1000–1009, by maximising per-tick agreement with rule B — the sign must match and `|turn| ≥ 0.5` whenever B turns, and `turn = 0` whenever B does not. The grid was gain ∈ {1/5, 1/10, 1/20, 1/40}, deadband ∈ {0, 3, 6, 10}, ema ∈ {0, 0.5}; ties were broken towards the smaller ema, deadband and gain. Result: `results/c-brain-cal-v1-readout.json`. The parameters were not touched afterwards.

**D** — feedback broken. The constant-output form coincides with A and was not run separately. The replay form takes the brain ticks of the same seed from a different scenario (none ← left, left ← right, right ← none) and passes them through the same readout; the run asserts that the event checksums differ.

**E** — shuffled connectome. Five networks, seeds 4000–4004. Directed double-edge swaps within each sign class, ten rounds over all edges, rejecting self-loops and duplicate pairs. Preserved exactly: each node's in-degree and out-degree per sign, the global multiset of weights (each weight stays with its presynaptic edge), the absence of self-loops and duplicates. Preserved only approximately: the distribution of incoming weights per node. The fraction of changed (pre, post) pairs is recorded per network and was 100% in all five. Two comparisons are made: with the readout fixed at C's parameters, and after a limited recalibration by the same rule on calibration data.

## Tick order

Sensors of tick k → excitation → advance the network by 15 ms → new spikes → causal filter → command for tick k → advance the body by 15 ms. Brain and body model time is checked by assertion at every tick.

Because the stimuli in this round are external and independent of the body, the brain pass is computed by `brain_loop.py` separately and fed to the body tick by tick. The network is advanced in segments between stimulus changes, and per-tick counts are binned from recorded spike times. This was verified to be bit-identical to per-tick stepping (`c-brain-smoke2` against `c-brain-smoke3`), and the underlying segmentation was verified against a single continuous run (`brain-stream-0`). Scenarios with contact feedback will require a genuine joint loop.

## Tasks, seeds and metrics

Calibration seeds 1000–1009, test seeds 2000–2029, separated before any parameter was chosen; debug seeds 0–9 belong to neither. Events come from their own random number generator keyed by scenario and seed, so a variant cannot shift them by consuming randomness differently. Shuffled networks use seeds 4000–4004, brain instances 10000 + episode seed.

The stimulus switches on at a tick drawn uniformly from 12 to 20, that is between 180 and 300 ms, and then stays on. Episode length is 1.005 s for the turning and background tasks and 3 s for stopping.

Primary metrics, fixed in advance:

- **No stimulus** — success means no false turn or stop command during the whole episode.
- **Stimulus left or right** — success means a heading change greater than 0.2 radians in the correct direction within 0.5 s of onset.
- **Stopping** — success means the speed staying below 1 mm/s across eleven consecutive samples 15 ms apart, which span 150 ms. The delay to the first such sample is also stored; an episode that never stops is censored, not excluded.

A computational failure marks an episode invalid; invalid episodes enter the full denominator and block interpretation rather than being silently reported as a biological failure.

Comparisons are paired on identical events, with event files checked by SHA-256. The paired bootstrap resamples whole episodes, 10,000 replicates, seed 81291. Because the bootstrap degenerates when every pair has the same outcome, the main tables use a conservative exact interval built from Clopper–Pearson bounds on the two kinds of discordant pair, combined with a Bonferroni correction. For the shuffled networks the bootstrap is hierarchical: networks first, then paired episodes within a network. The margin of practical equivalence declared in advance is 5 percentage points of success and 0.1 s of stopping delay; an interval wider than that means the comparison is inconclusive, not that the variants are equal.

## Corrections made, and when

**Stop-window arithmetic (before the test outcomes were seen).** Ten instantaneous samples 15 ms apart span 135 ms, not 150. The criterion was corrected to eleven samples. The correction was verified on the stored calibration data, where rule B's success fell from 9 of 10 to 4 of 10, before any test outcome for stopping was examined. Controllers, stimuli, horizon and thresholds were unchanged. Raw trajectories and the old summaries were kept; corrected evaluations live in `metric-v2/` subdirectories.

**Stopping horizon (after calibration v1, before the test was opened).** At 1.005 s rule B reached the criterion in only 4 of 10 calibration episodes, which showed the observation window was too short for braking. Only the stopping task was extended to 3.000 s; the speed threshold and all controllers were kept, and the new horizon was re-checked on the same ten calibration seeds.

**Zero-spike brain passes.** The first version of `brain_loop.py` asserted on a non-empty spike array, which made a legitimately silent network (the no-stimulus scenario) look like a failure. The assertion was relaxed and the affected passes were recomputed.

## Admission of the brain variants

Before C, D or E could be run as a behavioural comparison, the following had to hold: verified identifiers from a single materialisation; no hidden target in the observation; stimulation applied to sensory neurons only; commands that disappear when the readout is disconnected; finite numbers and correct units; and demonstrable changes of the output in response to the stimulus. The machine-readable statement of what was admitted, and on what basis, is `results/brain-body-gate-v2.json`. Admission covers the none, left and right tasks only; stopping remains blocked for the brain variants because no validated speed output exists.

## Planned but not done

Scenarios: stimulus disappearance, changes of intensity and duration, conflicting inputs, noise and dropouts, navigation to a target, new positions and orientations, uneven terrain and perturbations. A small neural-network controller as a separate contestant, trained either to solve the task or to imitate the brain's output — these are different tests and must be labelled as such. Feeding and grooming are not implemented and are never claimed as performed; vision is excluded from this round entirely.
