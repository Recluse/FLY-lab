# Can the model tell one input from another?

A side investigation that started as a joke — teach the fly to play the blues — and turned
into a measurement about the published brain model itself. Nothing in the main experiment
depends on it.

**The headline.** With the weight per synapse the model ships with, four different olfactory
receptor classes produce the same response to four decimal places: the identity margin at the
mushroom body output is **+0.0001**, and at the Kenyon cells **0.0000**. The network is
supercritical — one spike delivers about three spikes' worth of drive to its targets — so any
input recruits the same global avalanche of roughly 8,200 neurons and the question "which
input was it?" has no answer downstream. Weakening the recurrence by half and driving the
input harder restores identity, to **+0.26**.

## How the question came up

The plan was to let the fly learn which notes are worth playing: the mushroom body is the
insect's learning circuit, dopaminergic neurons carry reinforcement, and all of it is in the
connectome. The first measurement killed the obvious design and is worth recording:

| path | direct contacts | at two hops |
|---|---:|---:|
| auditory Johnston's organ cells → Kenyon cells | **0** | 14 edges via 4 neurons |
| mushroom body output neurons → descending neurons | 361 edges onto 160 cells | 663 cells |

So a note cannot be taught through the ear — sound never reaches the learning circuit in this
wiring — while the mushroom body's verdict does reach the motor output on its own. The note
was therefore presented as an odour: one olfactory receptor class per scale degree, which is
an invention, and declared as one.

## The measurement

Four receptor classes, 300 ms of stimulation each, three repeats per class with different
input noise. For each condition we record how many neurons fire at all, how many Kenyon cells
fire, and the response vector of the mushroom body output neurons. The **identity margin** is
the cosine similarity between two presentations of the same odour minus the similarity
between two different odours: it is zero when the network cannot tell them apart and one when
different odours share nothing.

| weight per synapse | input rate | neurons firing | Kenyon cells | identity margin (Kenyon) | (output) |
|---:|---:|---:|---:|---:|---:|
| 0.275 — **as published** | 50 Hz | 8,200 | 64% | **0.0000** | **+0.0001** |
| 0.14 | 50 Hz | 2,899 | 14% | +0.0072 | +0.0012 |
| 0.12 | 50 Hz | 2,133 | 6% | +0.0106 | +0.0003 |
| 0.10 | 50 Hz | 1,467 | 2% | +0.0334 | 0 (output silent) |
| 0.12 | 400 Hz | 2,195 | 7% | +0.0816 | +0.0810 |
| **0.12** | **1200 Hz** | 2,287 | 8% | **+0.1960** | **+0.2622** |
| 0.14 | 1200 Hz | 3,107 | 16% | +0.1145 | +0.0595 |

Two things fall out. The identity is not recovered by turning the stimulus down — 5, 10, 20
and 40 Hz all give the same avalanche — but by turning the *network* down and the stimulus
up, so that what fires is decided by what was presented rather than by what the recurrence
does with it. And there is a cliff: below about 0.1 mV per synapse nothing reaches the
mushroom body at all, above about 0.14 the avalanche returns.

## Why the network burns

Counted from the connectivity table: a neuron's spike delivers, summed over its targets and
signed by predicted transmitter, about **21 mV** on average, against a threshold sitting
**7 mV** above rest. One spike is worth about three. A branching ratio near one is what keeps
a network's activity finite; three is a fire.

This is not a flaw the authors hid — the weight per synapse is documented as a free parameter,
and the comment in the source says 250 (the input scaling) is "sufficient to cause spiking".
For the question the model was built to answer — does sugar on the proboscis reach the motor
neuron — a supercritical network is harmless. For any question of the form "which of these
inputs was it?", it is fatal, and this is the cleanest explanation we have for why our own
main experiment could only ever read *side*, never identity.

## The control that nearly fooled us

A degree-preserving shuffle of the connectome, in the working regime, scores an identity
margin of **+0.98** — seven times better than the real wiring. It is an artefact: in the
shuffled network only 255–482 neurons fire at all and between 4 and 23 Kenyon cells, against
2,287 and 400 in the real one. Two odours light up disjoint handfuls of random cells, so
their cosine is zero and the margin is enormous. The honest statement is that in the shuffled
network the odour never arrives at the mushroom body — the same collapse the main experiment
found for the descending pathway — and the margin must always be read beside the activity
level.

## Files

- `music_probe.py` — the sweeps: `--rates` (stimulus rate), `--mv` (volts per input event),
  `--wsyn` (the model's own weight per synapse), `--trials`, `--shuffle-seed`.
- `results/music-probe-v*/summary.json` — every condition, with per-odour response vectors.
- `paper/music_figures.py` → `paper/figures/music1-criticality-en.png`.

```sh
.venv-brain/bin/python music_probe.py --label music-probe-v10-published --wsyn 0.275 --hz 50 --trials 2 --keep-kc
.venv-brain/bin/python music_probe.py --label music-probe-v8 --wsyn 0.12 0.14 --hz 1200 --trials 2 --keep-kc
.venv-brain/bin/python music_probe.py --label music-probe-v9-shuffled --wsyn 0.12 --hz 1200 --trials 2 --keep-kc --shuffle-seed 4000
.venv-body/bin/python paper/music_figures.py
```
