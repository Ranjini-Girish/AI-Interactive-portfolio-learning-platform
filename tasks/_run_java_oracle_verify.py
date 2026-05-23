"""Dev-only: run Java solve.sh and pytest for cryostat + stokes tasks."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

TASKS = (
    ("cryostat-lattice-audit", "CLR_DATA_DIR", "CLR_AUDIT_DIR", "cryostat"),
    ("stokes-diffusion-audit", "SDA_DATA_DIR", "SDA_AUDIT_DIR", "stokes_lab"),
)


def verify_one(task: str, data_env: str, audit_env: str, data_sub: str) -> tuple[int, str]:
    td = WORKSPACE / "tasks" / task
    data = td / "environment" / data_sub
    audit = td / "local-audit"
    if audit.exists():
        shutil.rmtree(audit)
    audit.mkdir()
    env = os.environ.copy()
    env[data_env] = str(data.resolve())
    env[audit_env] = str(audit.resolve())
    solve = td / "solution" / "solve.sh"
    bash = shutil.which("bash") or shutil.which("wsl")
    if not bash:
        return 127, "no bash"
    cmd = [bash, str(solve)] if bash.endswith("bash") or bash.endswith("bash.exe") else ["wsl", "bash", str(solve)]
    r = subprocess.run(cmd, cwd=td / "solution", capture_output=True, text=True, env=env)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-3000:]
        return r.returncode, f"solve failed:\n{err}"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_outputs.py", "-v", "--tb=short"],
        cwd=td,
        env=env,
        capture_output=True,
        text=True,
    )
    out = r.stdout + r.stderr
    # extract passed count
    summary = ""
    for line in out.splitlines():
        if "passed" in line and ("failed" in line or "error" in line or line.strip().endswith("passed")):
            summary = line.strip()
    if r.returncode != 0:
        return r.returncode, out[-8000:]
    return 0, summary or "all passed"


def main() -> None:
    results = []
    for task, de, ae, sub in TASKS:
        rc, msg = verify_one(task, de, ae, sub)
        results.append((task, rc, msg))
        print(f"=== {task} rc={rc} ===")
        print(msg[-500:] if len(msg) > 500 else msg)
    failed = [t for t, rc, _ in results if rc != 0]
    if failed:
        sys.exit(1)
    print("ALL OK")


if __name__ == "__main__":
    main()
