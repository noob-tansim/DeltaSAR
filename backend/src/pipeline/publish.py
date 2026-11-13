"""Build outputs in a staging folder, then swap it in atomically, so the live dashboard never sees half-written files.

  python -m src.pipeline.publish                       # run_aoi --replay + forecast into outputs_next, then swap
  python -m src.pipeline.publish --steps forecast      # only the forecast

Steps run as subprocesses with DELTASAR_OUTPUTS=<staging>. The staging folder starts as a copy of the live outputs
(so steps that are not re-run keep their files). On success: outputs -> outputs_prev, staging -> outputs
(two renames; the previous version is kept for one rollback). On failure nothing changes.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time

from src.config import ROOT

LIVE = ROOT / "outputs"
STAGE = ROOT / "outputs_next"
PREV = ROOT / "outputs_prev"
STEPS = {"run_aoi": [sys.executable, "-m", "src.pipeline.run_aoi", "--replay"],
         "forecast": [sys.executable, "-m", "src.compute.forecast"],
         "insights": [sys.executable, "-m", "src.compute.insights"],
         "compare": [sys.executable, "scripts/precompute_compare.py"]}


def build_and_swap(steps=("run_aoi", "forecast"), extra_env=None) -> dict:
    t0 = time.time()
    if STAGE.exists():
        shutil.rmtree(STAGE)
    if LIVE.exists():
        shutil.copytree(LIVE, STAGE)
    env = dict(os.environ, DELTASAR_OUTPUTS=str(STAGE), **(extra_env or {}))
    for s in steps:
        r = subprocess.run(STEPS[s], cwd=ROOT, env=env)
        if r.returncode != 0:
            return {"ok": False, "failed_step": s, "seconds": round(time.time() - t0)}
    if PREV.exists():
        shutil.rmtree(PREV)
    if LIVE.exists():
        LIVE.rename(PREV)
    STAGE.rename(LIVE)
    return {"ok": True, "steps": list(steps), "seconds": round(time.time() - t0)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", nargs="+", default=["run_aoi", "forecast"], choices=list(STEPS))
    print(build_and_swap(ap.parse_args().steps))
