"""Small runnable regression check for the measurement boundary."""
import csv
import json
import tempfile
from pathlib import Path

from pilot import metric, selfcheck


def check_stop_window():
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        (folder / "events.json").write_text(json.dumps({"onset_tick": 1}))
        for low_samples, expected in ((10, False), (11, True)):
            with (folder / "trajectory.csv").open("w") as stream:
                writer = csv.DictWriter(stream, fieldnames=["t_s", "speed_mm_s", "yaw_rad"])
                writer.writeheader()
                for i in range(20):
                    writer.writerow({"t_s":(i+1)*.015, "speed_mm_s":0 if 1 <= i < 1+low_samples else 5, "yaw_rad":0})
            result = metric(folder, "stop")
            assert result["success"] is expected, result
    print("stop window check passed")


if __name__ == "__main__":
    selfcheck()
    check_stop_window()
