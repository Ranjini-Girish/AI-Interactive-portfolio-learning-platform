"""Dev-only: run solve.sh bodies and pytest for named tasks."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent

TASKS = (
    ("dns-ttl-floor-audit", "DTF", "dnsfloor"),
    ("rust-lock-rank-audit", "RLR", "lockrank"),
    ("nonce-gap-mempool-audit", "NGM", "mempoolgap"),
    ("vnode-handoff-ring-audit", "VHR", "vnodering"),
)


def run_one(task: str, prefix: str, domain: str) -> int:
    task_dir = WORKSPACE / "tasks" / task
    data = task_dir / "environment" / domain
    audit = task_dir / "local-audit"
    audit.mkdir(exist_ok=True)
    os.environ[f"{prefix}_DATA_DIR"] = str(data)
    os.environ[f"{prefix}_AUDIT_DIR"] = str(audit)
    src = (task_dir / "solution" / "solve.sh").read_text(encoding="utf-8")
    marker = "python3 - <<'PYEOF'"
    start = src.index(marker) + len(marker)
    end = src.index("PYEOF", start)
    exec(compile(src[start:end], str(task_dir / "solution" / "solve.sh"), "exec"), {})
    return subprocess.call(
        [sys.executable, "-m", "pytest", "tests/test_outputs.py", "-q"],
        cwd=task_dir,
        env=os.environ.copy(),
    )


def main() -> None:
    for task, prefix, domain in TASKS:
        rc = run_one(task, prefix, domain)
        if rc != 0:
            print(f"FAIL {task}")
            sys.exit(rc)
        print(f"OK {task}")
    print("all passed")


if __name__ == "__main__":
    main()
