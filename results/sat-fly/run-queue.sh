#!/bin/sh
# usage: run-queue.sh "agent seed [--shaping]" ...
cd /Users/recluse/Work/FLY-lab
export OMP_NUM_THREADS=2
for spec in "$@"; do
  set -- $spec
  .venv-brain/bin/python sat_fly.py run --agent $1 --seed $2 --episodes 600 $3 > results/sat-fly/$1-s$2$(echo $3 | tr -d " -").log 2>&1
  echo "$1 s$2 $3 exit=$?"
done
