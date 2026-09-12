"""Run job lines with N workers; skip labels whose results/<label>/summary.json exists; drop partial dirs."""
import re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
jobs = [l.strip() for l in open(sys.argv[2] if len(sys.argv) > 2 else ROOT / "results/screen783-jobs.txt") if l.strip()]
def run(cmd):
    label = re.search(r"--label (\S+)", cmd).group(1)
    d = ROOT / "results" / label
    if (d / "summary.json").exists():
        return f"skip {label}"
    if d.exists():
        shutil.rmtree(d)
    rc = subprocess.run(cmd, shell=True, cwd=ROOT).returncode
    return f"{'ok' if rc == 0 else 'FAIL'} {label} rc={rc}"
with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 3) as ex:
    for line in ex.map(run, jobs):
        print(line, flush=True)
