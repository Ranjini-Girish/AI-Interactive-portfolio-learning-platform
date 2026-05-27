#!/usr/bin/env python3
"""Generate 10 tier-quota TE2 tasks (unique names + perturbed fixtures)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
SRC = Path(__file__).resolve().parent / "batch15_src"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gen_portfolio_batch15 import (  # noqa: E402
    QUOTA_OUTPUTS,
    TEST_SH,
    _hash_inputs,
    _hash_outputs,
    _quota_instruction,
    _rubric_quota,
    _run_quota_oracle,
    _spec_json_bytes,
)

BATCH10 = [
    ("amber-tier-cap-audit", "go", "build-and-dependency-management", ["go", "bash"], 1),
    ("bronze-tier-cap-audit", "rust", "software-engineering", ["rust", "bash"], 2),
    ("copper-tier-cap-audit", "java", "data-processing", ["java", "bash"], 3),
    ("dune-tier-cap-audit", "kotlin", "system-administration", ["kotlin", "bash"], 4),
    ("ember-tier-cap-audit", "elixir", "scientific-computing", ["elixir"], 5),
    ("flint-tier-cap-audit", "cpp", "debugging", ["c++", "bash"], 6),
    ("granite-tier-cap-audit", "haskell", "games", ["haskell"], 7),
    ("hazel-tier-cap-audit", "javascript", "security", ["javascript"], 8),
    ("ivory-tier-cap-audit", "typescript", "machine-learning", ["typescript"], 9),
    ("jade-tier-cap-audit", "c", "scientific-computing", ["c", "bash"], 10),
]

LANG_ORACLE_SRC = {
    "go": "go-tier-quota-audit",
    "rust": "rust-tier-quota-audit",
    "java": "java-tier-quota-audit",
    "kotlin": "kotlin-tier-quota-audit",
    "elixir": "elixir-tier-quota-audit",
    "cpp": "cpp-tier-quota-audit",
    "haskell": "hs-tier-quota-audit",
    "javascript": "js-tier-quota-audit",
    "typescript": "ts-tier-quota-audit",
    "c": "c-tier-quota-audit",
}


def _write_test_outputs(
    path: Path,
    name: str,
    input_hashes: dict[str, str],
    out_hashes: dict[str, str],
    field_hashes: dict[str, str],
) -> None:
    template = (
        TASKS / "py-tier-quota-audit" / "tests" / "test_outputs.py"
    ).read_text(encoding="utf-8")
    text = template.replace(
        '"""Verifier suite for py-tier-quota-audit."""',
        f'"""Verifier suite for {name}."""',
        1,
    )

    def _sub_dict(label: str, payload: dict[str, str]) -> None:
        nonlocal text
        body = json.dumps(payload, indent=4)
        text, n = re.subn(
            rf"{label} = \{{.*?\n\}}\n",
            f"{label} = {body}\n\n",
            text,
            count=1,
            flags=re.DOTALL,
        )
        if n != 1:
            raise RuntimeError(f"failed to patch {label} in test template")

    _sub_dict("EXPECTED_INPUT_HASHES", input_hashes)
    _sub_dict("EXPECTED_OUTPUT_CANONICAL_HASHES", out_hashes)
    _sub_dict("EXPECTED_FIELD_HASHES", field_hashes)
    path.write_text(text, encoding="utf-8")


def _task_toml(name: str, category: str, languages: list[str]) -> str:
    return f"""version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous"
difficulty = "hard"
category = "{category}"
subcategories = []
number_of_milestones = 0
codebase_size = "small"
languages = {json.dumps(languages)}
tags = ["tier-cap", "json-audit", "deterministic"]
expert_time_estimate_min = 180
junior_time_estimate_min = 360

[verifier]
timeout_sec = 600.0

[agent]
timeout_sec = 1500.0

[environment]
build_timeout_sec = 600.0
cpus = 2
memory_mb = 3072
storage_mb = 10240
workdir = "/app"
allow_internet = false
"""


def _perturb_quota_lab(data_dir: Path, variant: int) -> None:
    """Change hashes while preserving semantic-test invariants."""
    policy_path = data_dir / "policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    day = 12 + variant
    policy["audit_day"] = day
    policy_path.write_text(
        json.dumps(policy, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    events_path = data_dir / "events.json"
    events = json.loads(events_path.read_text(encoding="utf-8"))
    for fr in events.get("item_freezes", []):
        if fr["item_id"] == "item-03":
            fr["start_day"] = day - 2
            fr["end_day"] = day + 2
    events_path.write_text(
        json.dumps(events, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    aux = {"bundle": f"tier-cap-batch-{variant:02d}", "revision": variant}
    (data_dir / "aux-meta.json").write_text(
        json.dumps(aux, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    items_dir = data_dir / "items"
    for path in sorted(items_dir.glob("item-*.json")):
        num = int(path.stem.split("-", 1)[1])
        if num < 18:
            continue
        row = json.loads(path.read_text(encoding="utf-8"))
        row["demand"] = int(row["demand"]) + variant * 3
        path.write_text(
            json.dumps(row, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _copy_quota_env(dest: Path, variant: int) -> Path:
    src = TASKS / "py-tier-quota-audit" / "environment" / "quota_lab"
    dst = dest / "environment" / "quota_lab"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    _perturb_quota_lab(dst, variant)
    return dst


def _copy_solution(lang: str, sol: Path) -> None:
    src_task = TASKS / LANG_ORACLE_SRC[lang]
    src_sol = src_task / "solution"
    for path in src_sol.iterdir():
        if path.name == "solve.sh":
            continue
        if path.is_file():
            shutil.copy2(path, sol / path.name)
        elif path.is_dir():
            dest = sol / path.name
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(path, dest)


def _solve_sh(lang: str) -> str:
    src = (TASKS / LANG_ORACLE_SRC[lang] / "solution" / "solve.sh").read_text(
        encoding="utf-8"
    )
    return src


def _dockerfile(lang: str) -> str:
    return (TASKS / LANG_ORACLE_SRC[lang] / "environment" / "Dockerfile").read_text(
        encoding="utf-8"
    )


def build_one(
    name: str, lang: str, category: str, languages: list[str], variant: int
) -> None:
    td = TASKS / name
    if td.exists():
        shutil.rmtree(td)
    for sub in ("environment", "solution", "tests"):
        (td / sub).mkdir(parents=True)

    data_dir = _copy_quota_env(td, variant)
    (td / "environment" / "Dockerfile").write_text(_dockerfile(lang), encoding="utf-8")
    (td / "instruction.md").write_text(_quota_instruction(), encoding="utf-8")
    (td / "task.toml").write_text(_task_toml(name, category, languages), encoding="utf-8")
    (td / "rubrics.txt").write_text(_rubric_quota(), encoding="utf-8")
    (td / "tests" / "test.sh").write_text(
        TEST_SH.replace("python3 -m pytest", "python -m pytest"),
        encoding="utf-8",
    )

    sol = td / "solution"
    _copy_solution(lang, sol)
    solve = _solve_sh(lang).replace(
        'p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\\n", encoding="utf-8")',
        'p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\\n", encoding="utf-8", newline="\\n")',
    )
    (sol / "solve.sh").write_text(solve, encoding="utf-8", newline="\n")
    os.chmod(sol / "solve.sh", 0o755)

    # Normalize any copied oracle sources to LF for Linux solve.sh execution.
    for path in sol.rglob("*"):
        if path.is_file() and path.suffix in {
            ".sh",
            ".go",
            ".rs",
            ".java",
            ".kt",
            ".kts",
            ".exs",
            ".hs",
            ".cpp",
            ".c",
            ".mjs",
            ".ts",
            ".toml",
            ".mod",
        }:
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("\r\n", "\n"), encoding="utf-8", newline="\n")

    audit_local = td / "local-audit"
    audit_local.mkdir()
    _run_quota_oracle(data_dir, audit_local)
    for n in QUOTA_OUTPUTS:
        raw = (audit_local / n).read_bytes()
        (audit_local / n).write_bytes(_spec_json_bytes(json.loads(raw.decode())))

    inp = _hash_inputs(data_dir)
    out, fld = _hash_outputs(audit_local, QUOTA_OUTPUTS)
    _write_test_outputs(td / "tests" / "test_outputs.py", name, inp, out, fld)
    shutil.rmtree(audit_local)
    print(f"built {name} (variant {variant})")


def main() -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py",
        SRC / "quota_audit.py",
    )
    for name, lang, cat, langs, variant in BATCH10:
        build_one(name, lang, cat, langs, variant)
    print("batch10 done")


if __name__ == "__main__":
    main()
