"""Upyachka dance: kinematic keyframes on NeuroMechFly, no CPG, no brain."""
import os
import numpy as np
import imageio.v2 as imageio
from pathlib import Path
from flygym_gymnasium import Fly, YawOnlyCamera, SingleFlySimulation
from flygym_gymnasium.arena import FlatTerrain
from flygym_gymnasium.preprogrammed import all_leg_dofs
from flygym_gymnasium.examples.locomotion import PreprogrammedSteps

OUT = Path(__file__).parent / ("dance-" + os.environ.get("CAM", "front"))
OUT.mkdir(exist_ok=True)
steps = PreprogrammedSteps()
neutral = np.concatenate([steps.neutral_pos[leg].ravel() for leg in steps.legs])
idx = {name: i for i, name in enumerate(all_leg_dofs)}

def pose(offsets_deg):
    q = neutral.copy()
    for k, v in offsets_deg.items():
        q[idx["joint_" + k]] += np.radians(v)
    return q

HANG = {"LFCoxa": 45, "RFCoxa": 45, "LFTibia": 30, "RFTibia": 30}
KEYFRAMES = [  # matches the 4 GIF frames in order
    {**HANG, "LMFemur": 20, "LHFemur": 20},                                   # hunch, lean left
    {**HANG, "RMFemur": 20, "RHFemur": 20},                                   # hunch, lean right
    {"LFCoxa_roll": 40, "RFCoxa_roll": -40, "LFFemur": 60, "RFFemur": 60, "LFTibia": -40, "RFTibia": -40},  # arms up, bent
    {"LFCoxa_roll": 60, "RFCoxa_roll": -60, "LFFemur": 40, "RFFemur": 40, "LFTibia": -30, "RFTibia": -30,
     "LHCoxa_roll": 20, "RHCoxa_roll": -20},                                  # arms and legs wide
]
HOLD_S, RAMP_S, CYCLES, DT = 0.3, 0.12, int(os.environ.get("CYCLES", 6)), 1e-4
FRONT_UP = [False, False, True, True]  # adhesion off on LF/RF while lifted

fly = Fly(actuated_joints=all_leg_dofs, enable_adhesion=True, enable_vision=False, control="position")
cam = YawOnlyCamera(attachment_point=fly.model.worldbody, camera_name="cam_dance", targeted_fly_names=fly.name,
                    camera_parameters={"front": {"class": "nmf", "mode": "track", "ipd": 0.068, "pos": [4.0, 0, 1.6], "euler": [1.25, 0, 1.57]},
                                       "bottom": {"class": "nmf", "mode": "track", "ipd": 0.068, "pos": [0, 0, -4.3], "euler": [0, 3.14, float(os.environ.get("ROLL", -1.57))]}}[os.environ.get("CAM", "front")],
                    play_speed=1.0, fps=30, play_speed_text=False)
sim = SingleFlySimulation(fly=fly, cameras=[cam], arena=FlatTerrain(), timestep=DT)
sim.reset()
targets = [pose(k) for k in KEYFRAMES]
snapshots = []
for _ in range(int(0.4 / DT)):  # settle in neutral
    obs, *_ = sim.step({"joints": neutral, "adhesion": np.ones(6)})
    sim.render()
current = neutral.copy()
for cycle in range(CYCLES):
    for k, q in enumerate(targets):
        adhesion = np.ones(6)
        if FRONT_UP[k]:
            adhesion[[0, 3]] = 0
        start = current.copy()
        n = int(HOLD_S / DT)
        for i in range(n):
            a = min(1.0, i * DT / RAMP_S)
            current = start + a * (q - start)
            obs, *_ = sim.step({"joints": current, "adhesion": adhesion})
            sim.render()
        assert np.isfinite(obs["fly"]).all()
        if cycle == 1:
            snapshots.append(cam._frames[-1][::2, ::2])
        print(f"cycle {cycle} pose {k} z={obs['fly'][0, 2]:.2f}", flush=True)
cam.save_video(OUT / "fly_dance_raw.mp4", stabilization_time=0)
imageio.imwrite(OUT / "keyframes.png", np.concatenate(snapshots, axis=1))
sim.close()
