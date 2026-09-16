# Teaching the fly which notes to play

The other half of the side experiment that produced [`criticality.md`](criticality.md). The
question a reader asked: can the fly be rewarded when it hits a note that fits the chord, and
does it then hit more of them?

**The short answer.** In three paired runs the network with dopamine-gated plasticity chose
more chord tones than the same network with its synapses frozen — by 12, 9 and 11 notes out of
288, that is +3.1 to +4.2 percentage points. The direction is consistent and the mechanism is
the connectome's own, but the effect is small, three seeds are few, and neither arm is
dramatically better than a coin. This is a lead, not a result.

## What learns, and what does not

Only one bundle of synapses changes: the 62,261 connections from Kenyon cells to mushroom body
output neurons, four tenths of one per cent of the model's 15,091,983. Everything else keeps
the weights the connectome gives it.

The rule is the one the animal is thought to use — depression gated by dopamine, never
potentiation, with slow recovery towards the original weight:

- a candidate note is presented as an odour (one olfactory receptor class per scale degree);
- the fly's answer is the difference in spikes between two disjoint halves of the descending
  population, and the candidate with the highest answer is played;
- if the played note is a chord tone, the appetitive dopaminergic cluster PAM is driven;
  otherwise the aversive cluster PPL1 is;
- the Kenyon-cell synapses that fired during the chosen candidate, onto the half of the output
  neurons that argued for it, are depressed by 20 per cent; all plastic synapses relax 2 per
  cent of the way back to their connectome value at every step.

The decision is read from the descending neurons rather than from the mushroom body output
because in the working regime only two to five output neurons fire per window, while the
descending population fires hundreds of times — and the mushroom body reaches it directly
(361 contacts onto 160 descending cells).

## Arms and controls

All four arms share the same network seed, the same sequence of offered scale degrees and, as
it turned out, the same stream of Poisson noise: the network is built once per run with a
fixed seed and every arm makes the same number of simulation calls of the same length. That is
common random numbers, and it is why the paired differences below are far steadier than the
runs themselves.

| arm | what changes |
|---|---|
| connectome, plastic | the experiment |
| connectome, frozen | identical, including the dopamine stimulation, but weights never change |
| shuffled connectome, plastic | degree-preserving shuffle; the odour barely reaches the mushroom body |
| no odour input, plastic | the candidate is never presented; the fly chooses among equal answers |

## Results

Three seeds per arm, 288 decisions each.

| arm | chord tones chosen | what a coin would score | first quarter | last quarter |
|---|---:|---:|---:|---:|
| connectome, plastic | 0.458 | 0.456 | 0.375 | 0.532 |
| connectome, frozen | 0.421 | 0.468 | 0.352 | 0.440 |
| shuffled connectome | 0.522 | 0.475 | 0.565 | 0.537 |
| no odour input | 0.453 | 0.460 | 0.458 | 0.481 |

Paired, plastic minus frozen: **+0.042, +0.031, +0.038** across the three seeds — the same sign
and nearly the same size every time, because the two arms share their noise stream.

Read as advantage over a coin on the same offers, quarter by quarter:

| arm | 1st | 2nd | 3rd | 4th |
|---|---:|---:|---:|---:|
| connectome, plastic | −0.048 | +0.022 | −0.008 | **+0.042** |
| connectome, frozen | −0.094 | −0.042 | −0.005 | **−0.046** |
| shuffled connectome | +0.108 | +0.062 | −0.032 | +0.051 |
| no odour input | +0.015 | −0.015 | −0.015 | −0.015 |

The plastic arm ends a little above a coin and the frozen arm a little below it; over the whole
run the plastic arm is level with chance (+0.002) and the frozen arm below it (−0.047).

Two things are worth saying plainly. The intact network starts *below* chance and climbs — most
of that climb happens in both arms, so it is not the plasticity; the teacher's dopaminergic
stimulation reaches the network in both. And the two broken arms do not climb at all, which is
what says the climb has something to do with the wiring being intact.

![Chord tones chosen over a run, running mean of 48 decisions](../paper/figures/music2-learning-en.png)

## Why this is a lead and not a result

At 288 decisions a run, the standard error of a single arm's hit rate is about 3 percentage
points, and the quarter-by-quarter numbers carry about 6. The paired difference is steadier
than that because of the shared noise stream, but three seeds still give no useful interval.
To claim a number rather than a direction, this wants ten to fifteen seeds — the same
arithmetic that governs every other campaign in this repository.

A defect found and fixed along the way, kept here because it is the more instructive part: in
the first campaign the winner among equal answers was chosen by `argmax`, which returns the
first. The candidates were sorted, so with the input switched off the policy always played the
lowest degree offered — the root of the scale, a chord tone in eight bars of twelve. The deaf
control scored 0.503 that way, above the coin, while knowing nothing. It is the same failure
as the "always flip" policy in the SAT experiment, caught this time by a control rather than by
luck. Ties are now broken at random; the first campaign's four runs are kept in
`results/music-v1-*` as the record.

## Reproducing

```sh
.venv-brain/bin/python music_learn.py --label music-v2-learn-s7002 --bars 36 --candidates 3 \
    --eval-ms 200 --teach-ms 150 --hz 1200 --teach-hz 1200 --wsyn 0.12 --choice-seed 7002
.venv-brain/bin/python music_learn.py --label music-v2-frozen-s7002 ... --no-plasticity
.venv-brain/bin/python music_learn.py --label music-v2-shuffled-s7002 ... --shuffle-seed 4000
.venv-brain/bin/python music_learn.py --label music-v2-deaf-s7002 ... --deaf
.venv-body/bin/python music_analysis.py music-v2
.venv-body/bin/python paper/music_figures.py
```

One run is about 26 minutes on one core; two at a time is the limit on 32 GB. The full campaign
is `results/music-v2-jobs.txt`, run with `results/screen783-run.py 2`.
