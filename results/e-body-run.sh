#!/bin/sh
# Sequential E body tests: fixed readout (C's) and recalibrated readout, per shuffled network given as args.
cd /Users/recluse/Work/FLY-lab
for s in "$@"; do
  .venv-body/bin/python pilot.py test --tag e-test-v1-s$s --workers 2 --scenarios none left right --policies E --brain-tag e-brain-test-v1-s$s --readout results/c-brain-cal-v1-readout.json > results/e-test-v1-s$s.runner.log 2>&1
  echo "e-test-v1-s$s exit=$?"
  .venv-body/bin/python pilot.py test --tag e-recal-test-v1-s$s --workers 2 --scenarios none left right --policies E --brain-tag e-brain-test-v1-s$s --readout results/e-brain-cal-v1-s$s-readout.json > results/e-recal-test-v1-s$s.runner.log 2>&1
  echo "e-recal-test-v1-s$s exit=$?"
done
