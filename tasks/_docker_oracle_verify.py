"""Docker oracle + pytest for named tasks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

TASKS = (
    ("cryostat-lattice-audit", "cryostat"),
    ("stokes-diffusion-audit", "stokes_lab"),
)


def docker_verify(task: str, data_sub: str) -> tuple[int, str]:
    td = WORKSPACE / "tasks" / task
    tag = f"tb2-oracle-{task.replace('_', '-')}"
    env_dir = td / "environment"
    build = subprocess.run(
        ["docker", "build", "-t", tag, str(env_dir)],
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        return build.returncode, f"build failed:\n{build.stderr[-4000:]}"

    # Run solve.sh then pytest inside container
    script = r"""
set -euo pipefail
mkdir -p /app/audit /logs/verifier
bash /solution/solve.sh
bash /tests/test.sh
cat /logs/verifier/reward.txt
"""
    run = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{td / 'solution'}:/solution:ro",
            "-v",
            f"{td / 'tests'}:/tests:ro",
            tag,
            "bash",
            "-lc",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    reward = ""
    for line in (run.stdout or "").splitlines():
        if line.strip() in ("0", "1"):
            reward = line.strip()
    tail = (run.stdout or "") + (run.stderr or "")
    # pytest summary line
    summary = ""
    for line in tail.splitlines():
        if " passed" in line and " in " in line:
            summary = line.strip()
    msg = f"reward={reward} {summary}\n{tail[-6000:]}"
    if run.returncode != 0 or reward != "1":
        return run.returncode or 1, msg
    return 0, msg


def main() -> None:
    ok = True
    for task, sub in TASKS:
        print(f"\n######## {task} ########")
        rc, msg = docker_verify(task, sub)
        print(msg[-2000:])
        if rc != 0:
            ok = False
            print(f"FAIL {task} rc={rc}")
        else:
            print(f"PASS {task}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
