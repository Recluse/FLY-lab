"""Run from either isolated environment; see README.md."""
import argparse
import ast
import csv
import gc
import hashlib
import json
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRAIN = ROOT / "vendor/Drosophila_brain_model"
BODY = ROOT / "vendor/flygym-gymnasium"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def notebook_assignment(filename, name):
    for cell in json.loads((BRAIN / filename).read_text())["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                return ast.literal_eval(node.value)
    raise ValueError(f"Missing notebook assignment: {name}")


def manifest():
    from importlib.metadata import distributions
    hashes = {}
    for file in sorted(list(BRAIN.iterdir()) + list(ROOT.glob("*.py"))):
        if file.suffix in {".csv", ".parquet", ".py", ".ipynb", ".yml"}:
            with file.open("rb") as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            hashes[str(file.relative_to(ROOT))] = digest.hexdigest()
    return {"python": sys.version, "executable": sys.executable,
            "os": platform.platform(), "machine": platform.machine(),
            "hardware": "Apple M5, 10 CPU cores, 32 GB unified RAM",
            "packages": sorted(f"{d.metadata['Name']}=={d.version}" for d in distributions()),
            "repositories": {str(p.relative_to(ROOT)): subprocess.check_output(["git", "-C", str(p), "rev-parse", "HEAD"], text=True).strip() for p in [BRAIN, BODY]},
            "sha256": hashes}


def brain(args):
    import numpy as np
    import pandas as pd
    import brian2 as b
    sys.path.insert(0, str(BRAIN))
    import model
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    save(out / "manifest.json", manifest())
    ids = notebook_assignment("example.ipynb", "neu_sugar")
    mn9 = notebook_assignment("example.ipynb", "id_mn9")
    comp = BRAIN / "2023_03_23_completeness_630_final.csv"
    con = BRAIN / "2023_03_23_connectivity_630_final.parquet"
    index = pd.read_csv(comp, index_col=0).index
    assert index.is_unique
    mapping = {int(v): i for i, v in enumerate(index)}
    assert all(v in mapping for v in ids + [mn9])
    save(out / "ids.json", {"materialization": 630, "sugar_right": [str(v) for v in ids], "MN9": str(mn9), "source": "example.ipynb cells 3 and 17", "motor_mapping": None})
    b.defaultclock.dt = 0.1 * b.ms
    params = model.default_params.copy()
    params["r_poi"] = args.hz * b.Hz
    save(out / "config.json", {"trials": args.trials, "seeds": list(range(args.seed, args.seed + args.trials)), "input_hz": args.hz, "duration_s": 1, "dt_s": 0.0001, "parameters": {k: str(v) for k, v in params.items()}, "mode": "upstream run_trial, notebook sugarR reaction"})
    rows = []
    start = time.monotonic()
    for trial in range(args.trials):
        gc.collect()
        b.start_scope()
        b.seed(args.seed + trial)
        t0 = time.monotonic()
        spikes = model.run_trial([mapping[v] for v in ids], [], [], comp, con, params)
        frame = model.construct_dataframe([spikes], "sugarR", dict(enumerate(index)))
        frame.to_parquet(out / f"spikes-{trial:03d}.parquet", index=False)
        mn9_rate = len(spikes.get(mapping[mn9], []))
        assert all(np.isfinite(np.asarray(v)).all() for v in spikes.values())
        row = {"trial": trial, "seed": args.seed + trial, "MN9_hz": mn9_rate, "active_neurons": len(spikes), "spikes": len(frame), "wall_s": time.monotonic() - t0}
        rows.append(row)
        save(out / "episodes.json", rows)
        print(json.dumps(row), flush=True)
    save(out / "summary.json", {"trials": len(rows), "MN9_mean_hz": float(np.mean([r["MN9_hz"] for r in rows])), "wall_s": time.monotonic() - start, "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "gpu": "unused"})


def body(args):
    import numpy as np
    from flygym_gymnasium import Fly, YawOnlyCamera
    from flygym_gymnasium.arena import FlatTerrain, MixedTerrain
    from flygym_gymnasium.preprogrammed import default_leg_sensor_placements
    from flygym_gymnasium.examples.locomotion import HybridTurningController
    out = ROOT / "results" / args.label
    out.mkdir(parents=True, exist_ok=False)
    save(out / "manifest.json", manifest())
    save(out / "config.json", vars(args))
    np.random.seed(args.seed)
    fly = Fly(enable_adhesion=True, contact_sensor_placements=default_leg_sensor_placements, enable_vision=False)
    cameras = [YawOnlyCamera(attachment_point=fly.model.worldbody, camera_name="camera_right", targeted_fly_names=fly.name, play_speed=0.2)] if args.video else []
    sim = HybridTurningController(fly=fly, cameras=cameras, timestep=0.0001, seed=args.seed, arena=MixedTerrain() if args.terrain == "mixed" else FlatTerrain())
    obs, info = sim.reset(seed=args.seed)
    initial = obs["fly"][0].copy()
    rows = []
    start = time.monotonic()
    blocks = round(args.seconds / 0.015)
    assert blocks > 0
    events = None
    if args.policy:
        from pilot import events_for, select_command, adapt
        events = events_for(args.scenario, args.seed, blocks)
        save(out / "events.json", events)
    try:
        for block in range(blocks):
            t = block * 0.015
            if events is not None:
                sensory = tuple(events["observations"][block])
                command = select_command(args.policy, args.scenario, sensory)
                action = adapt(command)
            elif args.command == "straight":
                action = np.array([1., 1.])
            elif args.command == "left":
                action = np.array([0.4, 1.2])
            elif args.command == "right":
                action = np.array([1.2, 0.4])
            elif args.command == "stop":
                action = np.array([1., 1.]) if t < 0.99 else np.zeros(2)
            else:
                action = np.array([1.2, 0.4]) if t < blocks * 0.015 / 2 else np.array([0.4, 1.2])
            flips = 0
            for _ in range(150):
                obs, _, terminated, truncated, info = sim.step(action)
                assert np.isfinite(obs["fly"]).all(), "Nonfinite body state"
                flips += int(info.get("flip", False))
                if args.video:
                    sim.render()
                if terminated or truncated:
                    raise RuntimeError(f"Simulation ended at {sim.curr_time}: {info}")
            assert abs(sim.curr_time - (block + 1) * 0.015) < 1e-8
            direction = obs["fly_orientation"]
            rows.append({"t_s": (block + 1) * 0.015, "x_mm": float(obs["fly"][0,0]), "y_mm": float(obs["fly"][0,1]), "z_mm": float(obs["fly"][0,2]), "speed_mm_s": float(np.linalg.norm(obs["fly"][1,:2])), "yaw_rad": float(np.arctan2(direction[1], direction[0])), "left_drive": float(action[0]), "right_drive": float(action[1]), "flipped_physics_steps": flips})
            if events is not None:
                rows[-1].update(sensor_left=sensory[0], sensor_right=sensory[1], speed_command=command[0], turn_command=command[1])
    finally:
        if rows:
            with (out / "trajectory.csv").open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
        sim.close()
    wall = time.monotonic() - start
    yaw = np.unwrap([r["yaw_rad"] for r in rows])
    summary = {"seed": args.seed, "command": args.command, "terrain": args.terrain, "model_s": blocks * .015, "wall_s": wall, "model_to_wall": blocks * .015 / wall, "displacement_mm": (obs["fly"][0] - initial).tolist(), "yaw_change_rad": float(yaw[-1] - yaw[0]), "upright_fraction": 1 - sum(r["flipped_physics_steps"] for r in rows)/(blocks*150), "final_speed_mm_s": rows[-1]["speed_mm_s"], "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "gpu": "physics on CPU; graphics only for optional video"}
    save(out / "summary.json", summary)
    if args.video:
        cameras[0].save_video(out / "body.mp4", stabilization_time=0)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["brain", "body"])
    parser.add_argument("--label", required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--hz", type=float, default=150)
    parser.add_argument("--seconds", type=float, default=1.005)
    parser.add_argument("--terrain", choices=["flat", "mixed"], default="flat")
    parser.add_argument("--command", choices=["straight", "left", "right", "stop", "turns"], default="straight")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--policy", choices=["A", "B"])
    parser.add_argument("--scenario", choices=["none", "left", "right", "stop"], default="none")
    args = parser.parse_args()
    if not args.label or Path(args.label).name != args.label or args.label in {".", ".."}:
        parser.error("label must be a single directory name")
    if args.trials < 1 or args.hz < 0 or args.seconds <= 0:
        parser.error("invalid duration, trials or rate")
    {"brain": brain, "body": body}[args.mode](args)
