# Searching for a usable input

The goal of this screen was to find a sensory input that produces a **bilateral, lateralised** response in the descending neurons without driving the network into a global avalanche. It is a wiring diagnostic, not a behavioural result, and it says nothing about the biological fly.

## Method

`brain_probe.py sensory783` selects input neurons from the official FlyWire annotations by `cell_class`, `cell_sub_class` and side, where side means the side at which the nerve enters. Excitation is the model's own Poisson input at 150 Hz for one second, seed 0, with the original equations and parameters of the Shiu model. We ran every subclass that carries a side label and has at most about 250 cells per side; eye bristles (555 and 557) and the unlabelled olfactory group (913 and 925) were not run.

Six runs contained annotated identifiers that are absent from the model's completeness table, two to five cells each. Those runs were repeated with `--allow-missing`, which drops exactly those cells and records them in `excluded_ids.json`. Without the flag the run refuses to start, so nothing is excluded silently.

Aggregation is `screen_analysis.py`, which writes `results/screen783-analysis/runs.csv`, `lateralisation.csv` and `summary.md`.

## Result 1: the avalanche is a fixed attractor of the network

Every hygrosensory and thermosensory input, the pheromone group, the accessory pharyngeal receptors, and sugar/water on the right at 100 Hz all drive the network into one and the same state: about 8,400 active neurons, roughly 460,000 spikes per second, DNa02L at 45–55 Hz, DNa01L at 15–25 Hz, DNa02R at zero — regardless of modality or side. Three to seven input cells are enough. Sugar/water on the right gives no avalanche at 50 Hz (217 active neurons, DNa silent) but does at 100 and 150 Hz. Sugar/water on the left gives no avalanche even at 300 Hz.

The consequence matters: the apparent response of the right-hand sugar set, reported in our first round as "the right set activates DNa", is a property of the avalanche rather than a taste-to-turn pathway. The left-right asymmetry inside the avalanche belongs to the network, or to the reconstruction, not to the stimulus. Any readout taken during an avalanche is invalid. The avalanche threshold used in the analysis, 3,000 active neurons, sits inside a gap: the screen contains runs with 746 active neurons and runs with 8,338, and nothing in between.

## Result 2: head bristles are the only cleanly lateralised input

Mechanosensory head bristles: 150 cells on the left, 155 on the right, no avalanche (746 and 622 active neurons).

| Input | DNa01L | DNa01R | DNa02L | DNa02R |
|---|---:|---:|---:|---:|
| left, 150 Hz | 0 | 10 | 17 | 0 |
| right, 150 Hz | 0 | 0 | 0 | 12 |

DNa02 responds ipsilaterally and mirror-symmetrically. Beyond DNa02, more than twenty descending types reach a lateralisation index (ipsi − contra)/(ipsi + contra) of 0.9 or above with at least 50 spikes: DNge132, DNge036, DNge100, DNge133, DNg39, DNp13, DNg61, DNde006, DNge019 among them. The full list is in `lateralisation.csv`.

Bitter receptors weakly excite DNa from the left (6–8 Hz) and almost not at all from the right; low-salt and taste-peg inputs reach only MN9; grooming bristles, hearing, wind and gravity, and the polarised-light receptors all produce a network response (79–636 active neurons) with no avalanche but leave all four DNa neurons silent.

## Result 3: pulse probes, 15 ms windows

A pulse probe runs one network for 0.9 s with the stimulus on only during [0.3, 0.6) s and records new spikes per 15 ms tick.

Left input: DNa02L fires 4 spikes during the stimulus and none outside it; DNa01R fires 4; the remaining outputs and MN9 are silent. Right input: DNa02R fires 2 during the stimulus and none outside. Mirror-symmetric, but far too sparse for a per-tick readout from single cells.

The whole descending population is a different matter. With the left input it produces 2,436 spikes during the stimulus against 26 outside it, the first spike arriving 4 ms after onset; per tick the left population fires 70–84 spikes and the right one 42–53. With the right input the left population totals 531 spikes and the right 930, the first spike arriving after 4.6 ms. The per-tick difference L − R runs from +18 to +39 for a left stimulus and from −30 to −8 for a right one; in no single tick does the sign match the opposite side. That difference is fast, causal and mirror-symmetric, which is what made it usable as a readout.

## What this licensed, and what it did not

It licensed one specific wiring: head bristles left and right as the stimulus, matching the left and right tasks of the A/B pilot, and a turn command derived from the descending population difference. It did not license a stopping output: sugar to MN9 remains a hypothesis and is not treated as a speed readout.

Limitations. One seed per run. The side of a descending neuron is taken from the annotation, not from function. The correspondence between head bristles and DNa02 agrees with the published role of DNa02 in ipsilateral turning, but we did not verify that correspondence behaviourally — we used it as a hint and measured the rest ourselves. The absence of a response from a class at 150 Hz does not mean the pathway does not exist.
