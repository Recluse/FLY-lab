# Command reference

A condensed list of every command used to produce the published results. The narrative version, with explanations, is in the [README](../README.md). Run commands one at a time and check the exit code; each label is new and never overwrites an existing directory.

## Environments

```sh
git clone https://github.com/philshiu/Drosophila_brain_model.git vendor/Drosophila_brain_model
git -C vendor/Drosophila_brain_model checkout 91bdd1e7dcf193f3e7ca5a8933497fcef63b7960
git clone https://github.com/NeLy-EPFL/flygym-gymnasium.git vendor/flygym-gymnasium
git -C vendor/flygym-gymnasium checkout d285260a1c8a7b3494150cd1590f2c9fe4b5e06b
git clone https://github.com/flyconnectome/flywire_annotations.git vendor/flywire_annotations
git -C vendor/flywire_annotations checkout 8587524c1748ce5ef2080822a2fc890fc03bf597
uv venv --python 3.10.21 .venv-brain
uv pip install --python .venv-brain/bin/python -r requirements/brain.txt
uv venv --python 3.12.14 .venv-body
uv pip install --python .venv-body/bin/python -r requirements/body.txt -e vendor/flygym-gymnasium
```

## Self-checks

```sh
.venv-body/bin/python pilot.py check
.venv-body/bin/python test_pilot.py
.venv-brain/bin/python brain_loop.py --check
.venv-body/bin/python -m pytest -q vendor/flygym-gymnasium/flygym_gymnasium/examples/locomotion/tests/test_hybrid_turning.py::test_turning
```

## Body and brain in isolation

```sh
.venv-body/bin/python experiment.py body --label body-straight-0 --seconds 1.005
.venv-body/bin/python experiment.py body --label body-left-0  --command left  --seconds 1.005
.venv-body/bin/python experiment.py body --label body-right-0 --command right --seconds 1.005
.venv-body/bin/python experiment.py body --label body-stop-0  --command stop  --seconds 3
.venv-brain/bin/python experiment.py brain --label sugar-reference-30 --trials 30
.venv-brain/bin/python brain_probe.py stream --label brain-stream-0
.venv-brain/bin/python brain_probe.py audit  --label brain783-audit-0
```

## Sensory screen

```sh
.venv-brain/bin/python brain_probe.py sensory783 --label NEW_NAME --side left \
    --cell-class mechanosensory --sub-class 'head bristle' --hz 150
.venv-brain/bin/python brain_probe.py pulse783   --label NEW_NAME --side left \
    --cell-class mechanosensory --sub-class 'head bristle' --hz 150
.venv-brain/bin/python results/screen783-run.py 1 results/screen783-jobs.txt
.venv-brain/bin/python screen_analysis.py screen783-
```

`--sub-class '*'` matches any subclass. `--allow-missing` drops annotated identifiers that the model does not contain and records them in `excluded_ids.json`; without it the run refuses to start.

`results/screen783-run.py N FILE` runs a list of commands with N workers, skips labels that already have a `summary.json` and removes half-written directories. Use at most two workers: three concurrent Brian2 networks exhaust 32 GB.

## A and B

```sh
.venv-body/bin/python pilot.py calibration --tag ab-calibration-v1 --workers 4
.venv-body/bin/python pilot.py test --tag ab-test-v1 --workers 4 --scenarios none left right
.venv-body/bin/python pilot.py test --tag ab-test-stop-v2 --workers 4 --scenarios stop
.venv-body/bin/python pilot.py analyse --tag SERIES_NAME     # re-evaluate with the corrected stop metric
```

## Brain passes

```sh
.venv-brain/bin/python brain_loop.py --label c-brain-cal-v1-left-1000 --scenario left --seed 1000
.venv-brain/bin/python results/screen783-run.py 2 results/c-brain-cal-v1-jobs.txt
.venv-brain/bin/python results/screen783-run.py 2 results/c-brain-test-v1-jobs.txt
.venv-brain/bin/python brain_loop.py --make-shuffled 4000 4001 4002 4003 4004
.venv-brain/bin/python results/screen783-run.py 2 results/e-brain-v1-jobs.txt
```

`--shuffle-seed N` runs the pass on the cached shuffled connectivity for seed N; `--make-random N …` builds the random-topology null used by the side experiment.

## C, D and E on the body

```sh
.venv-body/bin/python pilot.py calibrate-readout --brain-tag c-brain-cal-v1
.venv-body/bin/python pilot.py calibration --tag c-cal-v1 --workers 2 --scenarios none left right \
    --policies C --brain-tag c-brain-cal-v1 --readout results/c-brain-cal-v1-readout.json
.venv-body/bin/python pilot.py test --tag cd-test-v1 --workers 2 --scenarios none left right \
    --policies C D --brain-tag c-brain-test-v1 --readout results/c-brain-cal-v1-readout.json
.venv-body/bin/python pilot.py calibrate-readout --brain-tag e-brain-cal-v1-s4000
results/e-body-run.sh 4000 4001 4002 4003 4004
```

Add `--resume` to continue an interrupted series under the same tag.

## Comparisons

```sh
.venv-body/bin/python pilot.py compare --tag cd-test-v1 --against ab-test-v1 --pair C A
.venv-body/bin/python pilot.py compare --tag cd-test-v1 --against ab-test-v1 --pair C B
.venv-body/bin/python pilot.py compare-networks --tag e-compare-fixed-v1 --against cd-test-v1 --pair E C \
    --network-tags e-test-v1-s4000 e-test-v1-s4001 e-test-v1-s4002 e-test-v1-s4003 e-test-v1-s4004
.venv-body/bin/python pilot.py compare-networks --tag e-compare-recal-v1 --against cd-test-v1 --pair E C \
    --network-tags e-recal-test-v1-s4000 e-recal-test-v1-s4001 e-recal-test-v1-s4002 e-recal-test-v1-s4003 e-recal-test-v1-s4004
```

## Videos, figures and the report

```sh
.venv-body/bin/python results/screen783-run.py 1 results/video-C-jobs.txt
.venv-body/bin/python paper/figures.py
cd paper && weasyprint fly-lab-en.html fly-lab-en.pdf && weasyprint fly-lab-ru.html fly-lab-ru.pdf
```

Primary measurements are made without video. Recording video does not change the trajectory: the video runs and the measurement runs on the same seed produce byte-identical `trajectory.csv`.
