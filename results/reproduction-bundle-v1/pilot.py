"""A/B pulse pilot. Controllers only receive two local stimulus intensities."""
import argparse
import concurrent.futures
import csv
import hashlib
import json
import math
import random
import subprocess
import sys
from pathlib import Path
from experiment import ROOT, save

SCENARIOS = ("none", "left", "right", "stop")
SEEDS = {"calibration": list(range(1000, 1010)), "test": list(range(2000, 2030))}


def events_for(scenario, seed, blocks):
    # Independent event RNG: consuming controller/network randomness cannot change it.
    rng = random.Random(f"FLY-lab-pulse-v1:{scenario}:{seed}")
    onset = rng.randint(12, 20)  # 180..300 ms; not passed to controller
    observations = [[0., 0.] for _ in range(blocks)]
    for k in range(onset, blocks):
        if scenario == "left":
            observations[k] = [1., 0.]
        elif scenario == "right":
            observations[k] = [0., 1.]
        elif scenario == "stop":
            observations[k] = [1., 1.]
    return {"seed": seed, "scenario": scenario, "onset_tick": onset, "dt_s": .015,
            "description": "externally applied local receptor stimulus, no navigation target", "observations": observations}


def select_command(policy, task, observation):
    left, right = observation
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in observation):
        raise ValueError("invalid local sensor values")
    if policy == "A":
        return .8, 0.
    if policy != "B":
        raise ValueError("unvalidated brain variants are blocked")
    if task == "stop" and max(left, right) >= .5:
        return 0., 0.
    return .8, (float(left >= .5) - float(right >= .5))


def adapt(command):
    import numpy as np
    speed, turn = command
    if not all(math.isfinite(x) for x in command):
        raise ValueError("nonfinite command")
    speed = min(1., max(0., speed))
    turn = min(1., max(-1., turn))
    return np.array([speed * (1 - .5 * turn), speed * (1 + .5 * turn)])


def metric(folder, scenario):
    import numpy as np
    rows = list(csv.DictReader((folder / "trajectory.csv").open()))
    event = json.loads((folder / "events.json").read_text())
    onset = event["onset_tick"]
    yaw = np.unwrap([float(r["yaw_rad"]) for r in rows])
    if scenario == "none":
        success = all(float(r["turn_command"]) == 0 and float(r["speed_command"]) == .8 for r in rows)
        value = float(not success)
    elif scenario in {"left", "right"}:
        end = onset + math.ceil(.5 / .015) - 1
        if end >= len(rows):
            raise ValueError("episode too short for prespecified response window")
        value = float((yaw[end] - yaw[onset-1]) * (1 if scenario == "left" else -1))
        success = value > .2
    else:
        value = None
        # Eleven samples 15 ms apart span 150 ms; ten span only 135 ms.
        for k in range(onset, len(rows)-10):
            if all(float(r["speed_mm_s"]) < 1 for r in rows[k:k+11]):
                value = float(rows[k]["t_s"]) - onset * .015
                break
        success = value is not None
    return {"success": bool(success), "value": value}


def episode(job):
    scenario, seed, policy, tag = job
    label = f"{tag}-{scenario}-{policy}-{seed}"
    folder = ROOT / "results" / label
    if folder.exists():
        raise FileExistsError(f"Refusing to reuse existing episode: {folder}")
    log = ROOT / "results" / f"{label}.log"
    command = [sys.executable, str(ROOT / "experiment.py"), "body", "--label", label,
               "--policy", policy, "--scenario", scenario, "--seed", str(seed), "--seconds", "3" if scenario == "stop" else "1.005"]
    with log.open("w") as stream:
        result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
    record = {"scenario": scenario, "seed": seed, "policy": policy, "folder": str(folder.relative_to(ROOT)), "returncode": result.returncode}
    if result.returncode:
        record.update(success=False, value=None, invalid=True)
    else:
        record.update(metric(folder, scenario), invalid=False)
        record["event_sha256"] = hashlib.sha256((folder / "events.json").read_bytes()).hexdigest()
    return record


def exact_pair_interval(differences):
    from scipy.stats import beta
    n = len(differences)
    def interval(k):
        return (float(beta.ppf(.0125, k, n-k+1)) if k else 0.,
                float(beta.ppf(.9875, k+1, n-k)) if k < n else 1.)
    plus = interval(differences.count(1))
    minus = interval(differences.count(-1))
    return [plus[0]-minus[1], plus[1]-minus[0]]


def selfcheck():
    assert select_command("B", "left", (1,0)) == (.8,1)
    assert select_command("B", "right", (0,1)) == (.8,-1)
    assert select_command("B", "stop", (1,1)) == (0,0)
    assert select_command("A", "stop", (1,1)) == (.8,0)
    assert events_for("left", 1000, 67) == events_for("left", 1000, 67)
    assert tuple(adapt((0, 1))) == (0,0)
    lo,hi = exact_pair_interval([0]*30)
    assert lo < 0 < hi
    assert exact_pair_interval([1]*30)[0] > 0
    try:
        adapt((float("nan"),0))
    except ValueError:
        pass
    else:
        raise AssertionError("NaN accepted")
    print("pilot selfcheck passed")


def main(args):
    if args.mode == "check":
        selfcheck()
        return
    if args.mode == "analyse":
        folder = ROOT / "results" / args.tag
        records = json.loads((folder / "episodes.json").read_text())
        plan = json.loads((folder / "plan.json").read_text())
        seeds = sorted({job[1] for job in plan["jobs"]})
        scenarios = list(dict.fromkeys(job[0] for job in plan["jobs"]))
        out = folder / "metric-v2"
        out.mkdir(exist_ok=False)
        for record in records:
            if not record["invalid"]:
                record.update(metric(ROOT / record["folder"], record["scenario"]))
        save(out / "episodes.json", records)
        save(out / "summary.json", summarize(records, scenarios, seeds))
        return
    out = ROOT / "results" / args.tag
    out.mkdir(parents=True, exist_ok=False)
    jobs = [(s, seed, policy, args.tag) for s in args.scenarios for seed in SEEDS[args.mode] for policy in ("A","B")]
    save(out / "plan.json", {"split": args.mode, "jobs": jobs, "episode_s": {s:3.0 if s == "stop" else 1.005 for s in args.scenarios}, "workers": args.workers,
         "primary": {"none":"no false command", "left/right":"signed yaw change >0.2rad within 0.5s", "stop":"speed<1mm/s for 0.15s before horizon"},
         "equivalence_margin_success": .05, "bootstrap_seed": 81291, "bootstrap_replicates": 10000})
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(episode, jobs):
            records.append(record)
            save(out / "episodes.json", records)
            print(json.dumps(record), flush=True)
    save(out / "summary.json", summarize(records, args.scenarios, SEEDS[args.mode]))


def summarize(records, scenarios, seeds):
    report = {}
    rng = random.Random(81291)
    for scenario in scenarios:
        selected = [r for r in records if r["scenario"] == scenario]
        pairs = []
        for seed in seeds:
            a,b = [next(r for r in selected if r["seed"] == seed and r["policy"] == policy) for policy in ("A","B")]
            if a["invalid"] or b["invalid"]:
                continue
            assert a["event_sha256"] == b["event_sha256"]
            pairs.append(int(b["success"])-int(a["success"]))
        n = len(pairs)
        samples = sorted(sum(rng.choices(pairs, k=n))/n for _ in range(10000)) if n else []
        report[scenario] = {"A_successes":sum(r["success"] for r in selected if r["policy"]=="A"),
                            "B_successes":sum(r["success"] for r in selected if r["policy"]=="B"),
                            "denominator_each":len(seeds), "invalid_episodes":sum(r["invalid"] for r in selected),
                            "valid_pairs":n, "difference_B_minus_A":sum(pairs)/n if n else None,
                            "paired_episode_bootstrap_95": [samples[249],samples[9749]] if n else None,
                            "paired_exact_conservative_95": exact_pair_interval(pairs) if n else None,
                            "inference_note":"invalid episodes block inference; degenerate bootstrap at boundary does not prove population equivalence"}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check","calibration","test","analyse"])
    parser.add_argument("--tag", default="ab-calibration-v1")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or Path(args.tag).name != args.tag or args.tag in {".",".."}:
        parser.error("invalid workers or tag")
    main(args)
