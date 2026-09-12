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


BRAIN_POLICIES = ("C", "D", "E")  # C original network; D replay of another episode's network output; E shuffled network
READOUT_GRID = {"gain": (1/5, 1/10, 1/20, 1/40), "deadband": (0, 3, 6, 10), "ema": (0., .5)}


def readout_turns(ticks, gain, deadband, ema):
    """Causal turn command per tick from descending population counts: x_k = ema*x_{k-1} + (1-ema)*(L_k-R_k);
    turn_k = 0 if |x_k| < deadband else clip(gain*x_k, -1, 1). Uses only ticks <= k."""
    turns, x = [], 0.
    for t in ticks:
        d = t["DN_left"] - t["DN_right"]
        x = ema * x + (1 - ema) * d
        turns.append(0. if abs(x) < deadband else min(1., max(-1., gain * x)))
    return turns


def select_command(policy, task, observation, brain_turn=None):
    left, right = observation
    if any(not math.isfinite(x) or not 0 <= x <= 1 for x in observation):
        raise ValueError("invalid local sensor values")
    if policy == "A":
        return .8, 0.
    if policy in BRAIN_POLICIES:
        if brain_turn is None or not math.isfinite(brain_turn):
            raise ValueError("brain policy without a finite readout value")
        return .8, brain_turn  # background drive is the same constant as A; the brain only chooses the turn
    if policy != "B":
        raise ValueError("unknown policy")
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


REPLAY_SOURCE = {"none": "left", "left": "right", "right": "none"}  # D: same seed, other scenario => different events, same time structure


def brain_ticks_path(brain_tag, policy, scenario, seed):
    source = REPLAY_SOURCE[scenario] if policy == "D" else scenario
    return ROOT / "results" / f"{brain_tag}-{source}-{seed}" / "brain_ticks.json"


def episode(job):
    scenario, seed, policy, tag = job[:4]
    extra = job[4] if len(job) > 4 else {}
    label = f"{tag}-{scenario}-{policy}-{seed}"
    folder = ROOT / "results" / label
    if folder.exists():
        raise FileExistsError(f"Refusing to reuse existing episode: {folder}")
    log = ROOT / "results" / f"{label}.log"
    command = [sys.executable, str(ROOT / "experiment.py"), "body", "--label", label,
               "--policy", policy, "--scenario", scenario, "--seed", str(seed), "--seconds", "3" if scenario == "stop" else "1.005"]
    if policy in BRAIN_POLICIES:
        readout = extra["readout"]
        command += ["--brain-ticks", str(brain_ticks_path(extra["brain_tag"], policy, scenario, seed)),
                    "--readout-gain", str(readout["gain"]), "--readout-deadband", str(readout["deadband"]), "--readout-ema", str(readout["ema"])]
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
    assert select_command("C", "left", (1,0), brain_turn=.7) == (.8,.7)
    ticks = [{"DN_left":0,"DN_right":0}, {"DN_left":30,"DN_right":5}, {"DN_left":2,"DN_right":0}, {"DN_left":0,"DN_right":40}]
    assert readout_turns(ticks, 1/10, 3, 0.) == [0., 1., 0., -1.]
    assert readout_turns(ticks[:2], 1/10, 3, 0.) == readout_turns(ticks, 1/10, 3, 0.)[:2], "readout must be causal"
    assert abs(readout_turns(ticks, 1/10, 0, .5)[1] - 1.) < 1e-9 and 0 < readout_turns(ticks, 1/10, 0, .5)[2] < 1
    try:
        select_command("C", "left", (1,0))
    except ValueError:
        pass
    else:
        raise AssertionError("brain policy accepted without readout")
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
    if args.mode == "calibrate-readout":
        calibrate_readout(args.brain_tag)
        return
    if args.mode == "compare":
        compare(args.tag, args.against, args.pair)
        return
    if args.mode == "compare-networks":
        compare_networks(args.network_tags, args.against, args.pair[1], args.tag)
        return
    extra = {}
    if any(p in BRAIN_POLICIES for p in args.policies):
        if not args.brain_tag or not args.readout:
            raise SystemExit("brain policies need --brain-tag and --readout")
        extra = {"brain_tag": args.brain_tag, "readout": json.loads(Path(args.readout).read_text())["chosen"]}
    out = ROOT / "results" / args.tag
    jobs = [(s, seed, policy, args.tag, extra) for s in args.scenarios for seed in SEEDS[args.mode] for policy in args.policies]
    records = []
    if args.resume and out.exists():
        # Continue an interrupted series: keep recorded episodes, drop folders of episodes that were cut off mid-run.
        import shutil
        records = json.loads((out / "episodes.json").read_text())
        done = {(r["scenario"], r["seed"], r["policy"]) for r in records}
        jobs = [j for j in jobs if (j[0], j[1], j[2]) not in done]
        for j in jobs:
            folder = ROOT / "results" / f"{args.tag}-{j[0]}-{j[2]}-{j[1]}"
            if folder.exists():
                shutil.rmtree(folder)
        save(out / "resume.json", {"resumed_with_records": len(records), "remaining_jobs": len(jobs)})
    else:
        out.mkdir(parents=True, exist_ok=False)
        save(out / "plan.json", {"split": args.mode, "jobs": jobs, "episode_s": {s:3.0 if s == "stop" else 1.005 for s in args.scenarios}, "workers": args.workers,
             "primary": {"none":"no false command", "left/right":"signed yaw change >0.2rad within 0.5s", "stop":"speed<1mm/s for 0.15s before horizon"},
             "equivalence_margin_success": .05, "bootstrap_seed": 81291, "bootstrap_replicates": 10000})
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for record in pool.map(episode, jobs):
            records.append(record)
            save(out / "episodes.json", records)
            print(json.dumps(record), flush=True)
    if len(args.policies) == 2:
        save(out / "summary.json", summarize(records, args.scenarios, SEEDS[args.mode], tuple(args.policies)))


def calibrate_readout(brain_tag):
    """Choose readout parameters on calibration brain passes only: maximise per-tick agreement with the B rule
    (which succeeded 30/30 on left/right): sign match every tick, and |turn| >= .5 whenever B turns. Ties -> simplest."""
    import itertools
    scores = []
    for gain, deadband, ema in itertools.product(*READOUT_GRID.values()):
        agree = total = 0
        for scenario in ("none", "left", "right"):
            for seed in SEEDS["calibration"]:
                data = json.loads(brain_ticks_path(brain_tag, "C", scenario, seed).read_text())
                events = events_for(scenario, seed, len(data["ticks"]))
                assert data["events_sha256"] == hashlib.sha256((json.dumps(events, indent=2, allow_nan=False) + "\n").encode()).hexdigest()
                turns = readout_turns(data["ticks"], gain, deadband, ema)
                for k, obs in enumerate(events["observations"]):
                    b_turn = select_command("B", scenario, obs)[1]
                    ok = (turns[k] == 0) if b_turn == 0 else (math.copysign(1, turns[k]) == b_turn and abs(turns[k]) >= .5)
                    agree += ok; total += 1
        scores.append({"gain": gain, "deadband": deadband, "ema": ema, "agreement": agree / total})
    best = max(s["agreement"] for s in scores)
    chosen = sorted((s for s in scores if s["agreement"] == best), key=lambda s: (s["ema"], s["deadband"], s["gain"]))[0]
    save(ROOT / "results" / f"{brain_tag}-readout.json", {"brain_tag": brain_tag, "rule": "max per-tick agreement with rule B on calibration seeds; ties: ema, deadband, gain ascending",
                                                            "grid": READOUT_GRID, "scores": scores, "chosen": chosen})
    print(json.dumps(chosen))


def compare(tag, against, pair):
    """Pair episodes of policy pair[0] from results/<tag> with pair[1] from results/<against> on identical events."""
    records = []
    for folder, policy in ((tag, pair[0]), (against, pair[1])):
        records += [r for r in json.loads((ROOT / "results" / folder / "episodes.json").read_text()) if r["policy"] == policy]
    scenarios = list(dict.fromkeys(r["scenario"] for r in records if r["policy"] == pair[0]))
    seeds = sorted({r["seed"] for r in records if r["policy"] == pair[0]})
    out = ROOT / "results" / tag / f"compare-{pair[0]}-vs-{pair[1]}-{against}"
    out.mkdir(exist_ok=False)
    save(out / "summary.json", summarize(records, scenarios, seeds, (pair[1], pair[0])))
    print(json.dumps(json.loads((out / "summary.json").read_text()), indent=1))


def compare_networks(tags, reference_tag, reference_policy, out_name):
    """E vs reference: paired per-seed differences for each shuffled network; hierarchical bootstrap resamples
    networks first, then paired episodes within each network (10000 replicates, seed 81291)."""
    import numpy as np
    reference = [r for r in json.loads((ROOT / "results" / reference_tag / "episodes.json").read_text()) if r["policy"] == reference_policy]
    networks = {tag: [r for r in json.loads((ROOT / "results" / tag / "episodes.json").read_text()) if r["policy"] == "E"] for tag in tags}
    rng = np.random.default_rng(81291)
    report = {}
    for scenario in list(dict.fromkeys(r["scenario"] for r in reference)):
        ref = {r["seed"]: r for r in reference if r["scenario"] == scenario}
        diffs, per_network = [], {}
        for tag, records in networks.items():
            rows = [r for r in records if r["scenario"] == scenario]
            invalid = sum(r["invalid"] for r in rows) + sum(ref[r["seed"]]["invalid"] for r in rows)
            for r in rows:
                if not r["invalid"]:
                    assert r["event_sha256"] == ref[r["seed"]]["event_sha256"]
            d = [int(r["success"]) - int(ref[r["seed"]]["success"]) for r in rows if not r["invalid"] and not ref[r["seed"]]["invalid"]]
            diffs.append(d)
            per_network[tag] = {"E_successes": sum(r["success"] for r in rows), "denominator": len(rows), "invalid": invalid, "mean_difference_E_minus_ref": sum(d) / len(d) if d else None}
        point = float(np.mean([np.mean(d) for d in diffs]))
        samples = []
        for _ in range(10000):
            picked = rng.integers(0, len(diffs), len(diffs))
            samples.append(np.mean([np.mean(rng.choice(diffs[j], len(diffs[j]))) for j in picked]))
        samples.sort()
        report[scenario] = {"reference": f"{reference_tag}:{reference_policy}", "networks": per_network, "mean_difference_E_minus_ref": point,
                            "hierarchical_bootstrap_95": [float(samples[249]), float(samples[9749])], "n_networks": len(diffs),
                            "note": "networks resampled first, then paired episodes; silence/saturation of shuffled networks is reported, not interpreted as computation in the original"}
    save(ROOT / "results" / out_name / "summary.json", report)
    print(json.dumps(report, indent=1))


def summarize(records, scenarios, seeds, policies=("A", "B")):
    first, second = policies
    report = {}
    rng = random.Random(81291)
    for scenario in scenarios:
        selected = [r for r in records if r["scenario"] == scenario]
        pairs = []
        for seed in seeds:
            a,b = [next(r for r in selected if r["seed"] == seed and r["policy"] == policy) for policy in policies]
            if a["invalid"] or b["invalid"]:
                continue
            assert a["event_sha256"] == b["event_sha256"]
            pairs.append(int(b["success"])-int(a["success"]))
        n = len(pairs)
        samples = sorted(sum(rng.choices(pairs, k=n))/n for _ in range(10000)) if n else []
        report[scenario] = {f"{first}_successes":sum(r["success"] for r in selected if r["policy"]==first),
                            f"{second}_successes":sum(r["success"] for r in selected if r["policy"]==second),
                            "denominator_each":len(seeds), "invalid_episodes":sum(r["invalid"] for r in selected),
                            "valid_pairs":n, f"difference_{second}_minus_{first}":sum(pairs)/n if n else None,
                            "paired_episode_bootstrap_95": [samples[249],samples[9749]] if n else None,
                            "paired_exact_conservative_95": exact_pair_interval(pairs) if n else None,
                            "inference_note":"invalid episodes block inference; degenerate bootstrap at boundary does not prove population equivalence"}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["check","calibration","test","analyse","calibrate-readout","compare","compare-networks"])
    parser.add_argument("--tag", default="ab-calibration-v1")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--policies", nargs="+", choices=("A","B")+BRAIN_POLICIES, default=["A","B"])
    parser.add_argument("--brain-tag", help="results prefix of brain_loop passes, e.g. c-brain-cal-v1")
    parser.add_argument("--readout", help="path to <brain-tag>-readout.json from calibrate-readout")
    parser.add_argument("--against", help="compare: tag holding the reference policy episodes")
    parser.add_argument("--pair", nargs=2, default=["C","A"], help="compare: policy in --tag, policy in --against")
    parser.add_argument("--network-tags", nargs="+", help="compare-networks: tags of E test runs, one per shuffled network")
    parser.add_argument("--resume", action="store_true", help="continue an interrupted calibration/test series under the same tag")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4 or Path(args.tag).name != args.tag or args.tag in {".",".."}:
        parser.error("invalid workers or tag")
    main(args)
