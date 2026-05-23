#!/usr/bin/env python3
"""Batch QC for 24 Ayesha-converted tasks."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = [
    "aead-nonce-reuse-audit",
    "antireplay-window-audit",
    "arc-cache-replay-audit",
    "cgroup-quota-replay-audit",
    "circuit-breaker-replay",
    "counting-bloom-replay",
    "event-ledger-reconcile",
    "igmp-snooping-replay",
    "leaky-bucket-shaper-audit",
    "lock-order-deadlock-audit",
    "lsm-compaction-replay",
    "mqtt-router-replay-audit",
    "proc-tree-harvest-audit",
    "proc-tree-reaper-audit",
    "quota-hierarchy-replay",
    "region-coalescer-replay",
    "shard-rebalance-replay",
    "snapshot-retention-replay",
    "tail-sampling-trace-audit",
    "firewall-rule-shadow-audit",
    "k8s-manifest-rollout-audit",
    "postgres-migration-impact",
    "spectral-calibration-audit",
    "user-acct-hardening-audit",
]

LEAK_PAT = re.compile(r"solve\.sh|solution/|/solution|/sol\b|oracle", re.I)
PREFLIGHT = ROOT / "tools" / "terminus-task-tools" / "terminus_zip.py"


def env_file_count(task_dir: Path) -> int:
    env = task_dir / "environment"
    if not env.is_dir():
        return 0
    n = 0
    for p in env.rglob("*"):
        if p.is_file() and p.name not in ("Dockerfile", "docker-compose.yaml"):
            n += 1
    return n


def read_toml_checks(task_dir: Path) -> list[str]:
    issues: list[str] = []
    toml = task_dir / "task.toml"
    if not toml.is_file():
        issues.append("missing task.toml")
        return issues
    text = toml.read_text(encoding="utf-8")
    if "allow_internet = false" not in text:
        issues.append("allow_internet!=false")
    if 'workdir = "/app"' not in text:
        issues.append("workdir!=/app")
    langs_ok = False
    if re.search(r'languages\s*=\s*\[\s*"java"\s*\]', text):
        langs_ok = True
    if re.search(r'"typescript".*"bash"|"bash".*"typescript"', text, re.S):
        langs_ok = True
    # java+bash is the standard TB-2 replay stack (agent Java + wrapper bash)
    if re.search(r'"java".*"bash"|"bash".*"java"', text, re.S):
        langs_ok = True
    if not langs_ok:
        m = re.search(r"languages\s*=\s*\[([^\]]+)\]", text)
        issues.append(f"languages={m.group(1).strip() if m else '?'}")
    return issues


def leakage_scan(task_dir: Path) -> tuple[bool, str]:
    hits: list[str] = []
    for rel in ("instruction.md", "tests/test_outputs.py", "rubrics.txt"):
        p = task_dir / rel
        if not p.is_file():
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if LEAK_PAT.search(line):
                hits.append(f"{rel}:{i}")
    if hits:
        return False, "; ".join(hits[:3]) + ("..." if len(hits) > 3 else "")
    return True, "clean"


def remove_scaffold_line(task_dir: Path) -> bool:
    p = task_dir / "tests" / "test_outputs.py"
    if not p.is_file():
        return False
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    if lines and lines[0].startswith("# scaffold-status:"):
        p.write_text("".join(lines[1:]), encoding="utf-8")
        return True
    return False


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def run_ruff(task_dir: Path) -> tuple[str, str]:
    r = subprocess.run(
        [sys.executable, "-m", "ruff", "check", str(task_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    if r.returncode == 0:
        return "pass", ""
    err = _strip_ansi((r.stdout + r.stderr).strip())
    # Prefer first error code line (F401, invalid-syntax, etc.)
    detail = "fail"
    for line in err.splitlines():
        if "invalid-syntax" in line or "F401" in line or "-->" in line:
            detail = line.strip()[:100]
            break
    if detail == "fail" and err:
        detail = err.splitlines()[0][:100]
    return "fail", detail


def run_preflight(task_dir: Path) -> tuple[str, str]:
    r = subprocess.run(
        [sys.executable, str(PREFLIGHT), "preflight", str(task_dir)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    out = _strip_ansi((r.stdout + r.stderr).strip())
    if r.returncode == 0:
        return "pass", ""
    for line in out.splitlines():
        if "FAIL" in line or "ERROR" in line or "leakage" in line.lower():
            return "fail", line.strip()[:100]
        if "WARN" in line and "env" in line.lower():
            return "warn", line.strip()[:100]
    return ("fail" if r.returncode else "pass"), (out.splitlines()[-1][:100] if out else "")


def top_blocker(
    ruff: str,
    preflight: str,
    env_count: int,
    leakage_ok: bool,
    toml_issues: list[str],
    ruff_detail: str,
    preflight_detail: str,
    leakage_detail: str,
    codebase_size: str,
) -> str:
    blockers: list[str] = []
    if ruff != "pass":
        blockers.append(f"ruff: {ruff_detail}")
    if preflight != "pass":
        blockers.append(f"preflight: {preflight_detail}")
    if not leakage_ok:
        blockers.append(f"leakage: {leakage_detail}")
    if toml_issues:
        blockers.append("toml: " + ", ".join(toml_issues))
    if codebase_size == "minimal":
        blockers.append("codebase_size=minimal (blocked)")
    elif codebase_size == "small" and env_count < 20:
        blockers.append(f"env_count {env_count}<20")
    if not blockers:
        return "oracle/Java scaffold pending"
    return blockers[0][:100]


def main() -> None:
    fixed_scaffold: list[str] = []
    rows: list[dict] = []

    for name in TASKS:
        td = ROOT / "tasks" / name
        if remove_scaffold_line(td):
            fixed_scaffold.append(name)

        ruff_status, ruff_detail = run_ruff(td)
        pre_status, pre_detail = run_preflight(td)
        env_n = env_file_count(td)
        leak_ok, leak_detail = leakage_scan(td)

        toml_text = (td / "task.toml").read_text(encoding="utf-8") if (td / "task.toml").is_file() else ""
        cs = "?"
        m = re.search(r'codebase_size\s*=\s*"(\w+)"', toml_text)
        if m:
            cs = m.group(1)

        toml_issues = read_toml_checks(td)
        blocker = top_blocker(
            ruff_status,
            pre_status,
            env_n,
            leak_ok,
            toml_issues,
            ruff_detail,
            pre_detail,
            leak_detail,
            cs,
        )

        rows.append(
            {
                "task": name,
                "ruff": ruff_status,
                "preflight": pre_status,
                "env_count": env_n,
                "leakage": "clean" if leak_ok else leak_detail[:40],
                "blocker": blocker,
                "scaffold_removed": name in fixed_scaffold,
            }
        )

    if fixed_scaffold:
        print("SCAFFOLD_REMOVED:", ", ".join(fixed_scaffold), file=sys.stderr)

    print("| task | ruff | preflight | env_count | leakage | top blocker |")
    print("|---|---|---|---:|---|---|")
    for r in rows:
        print(
            f"| {r['task']} | {r['ruff']} | {r['preflight']} | {r['env_count']} | "
            f"{r['leakage']} | {r['blocker']} |"
        )


if __name__ == "__main__":
    main()
