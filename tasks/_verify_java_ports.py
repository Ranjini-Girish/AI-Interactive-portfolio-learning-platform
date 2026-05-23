#!/usr/bin/env python3
"""Compare native Replay.java output to oracle_impl.py for ported tasks."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
TASKS = (
    "aead-nonce-reuse-audit",
    "event-ledger-reconcile",
    "proc-tree-harvest-audit",
)
IMAGE = (
    "eclipse-temurin:21-jdk"
    "@sha256:be5aea962f8215d917d30c7d5a5ed32359580aef9c353b921487362b24650dde"
)


def canonical(path: Path) -> str:
    return json.dumps(json.loads(path.read_text(encoding="utf-8")), sort_keys=True)


def run_oracle(task_dir: Path, in_dir: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    script = task_dir / "solution" / "oracle_impl.py"
    subprocess.run(
        [sys.executable, str(script), str(in_dir), str(out_dir)],
        check=True,
        cwd=task_dir,
    )


def run_java(task_dir: Path, in_dir: Path, out_dir: Path, docs_mount: Path | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "Replay.java").write_text(
            (task_dir / "solution" / "Replay.java").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "curl",
                "-fsSL",
                "-o",
                str(t / "gson.jar"),
                "https://repo1.maven.org/maven2/com/google/code/gson/gson/2.11.0/gson-2.11.0.jar",
            ],
            check=True,
        )
        vols = [
            f"{t}:/work",
            f"{in_dir}:/in:ro",
            f"{out_dir}:/out",
        ]
        if docs_mount is not None:
            vols.append(f"{docs_mount}:/app/docs:ro")
        cmd = ["docker", "run", "--rm"] + [x for v in vols for x in ("-v", v)]
        cmd += [
            IMAGE,
            "bash",
            "-lc",
            "cd /work && javac -encoding UTF-8 -cp gson.jar Replay.java && "
            "java -cp .:gson.jar Replay /in /out",
        ]
        subprocess.run(cmd, check=True)


def outputs_for(task: str) -> list[str]:
    if task == "aead-nonce-reuse-audit":
        return [
            "key_states.json",
            "encryption_log.json",
            "audit_log.json",
            "diagnostics.json",
            "summary.json",
        ]
    if task == "event-ledger-reconcile":
        return [
            "account_state.json",
            "event_diagnostics.json",
            "reconciliation_report.json",
            "compliance_summary.json",
        ]
    return [
        "process_state.json",
        "harvest_log.json",
        "process_diagnostics.json",
        "lineage_graph.json",
        "summary.json",
    ]


def verify_task(task: str) -> bool:
    task_dir = WORKSPACE / "tasks" / task
    data = task_dir / "environment" / "data"
    docs = task_dir / "environment" / "docs" if task == "proc-tree-harvest-audit" else None
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        py_out = base / "py"
        java_out = base / "java"
        run_oracle(task_dir, data, py_out)
        run_java(task_dir, data, java_out, docs)
        ok = True
        for name in outputs_for(task):
            p_py = py_out / name
            p_java = java_out / name
            if not p_java.is_file():
                print(f"  MISSING java output: {name}")
                ok = False
                continue
            if canonical(p_py) != canonical(p_java):
                print(f"  MISMATCH: {name}")
                ok = False
            else:
                print(f"  OK {name}")
        return ok


def main() -> None:
    all_ok = True
    for task in TASKS:
        print(f"== {task} ==")
        try:
            if not verify_task(task):
                all_ok = False
        except subprocess.CalledProcessError as exc:
            print(f"  ERROR: {exc}")
            all_ok = False
    if not all_ok:
        sys.exit(1)
    print("all java ports match oracle")


if __name__ == "__main__":
    main()
