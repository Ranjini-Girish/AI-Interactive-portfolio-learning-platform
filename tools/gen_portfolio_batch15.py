#!/usr/bin/env python3
"""Generate 15 language-portfolio TB2 tasks and hash-lock tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "tasks"
SRC = Path(__file__).resolve().parent / "batch15_src"
DEBIAN_DIGEST = "f9c6a2fd2ddbc23e336b6257a5245e31f996953ef06cd13a59fa0a1df2d5c252"
NODE_DIGEST = "868499d55378719bffa87b0ed1f099591823c029b543043c09c2483468e93201"

QUOTA_OUTPUTS = ("allocations.json", "summary.json")
RELAY_OUTPUTS = ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json")

TEST_SH = """#!/bin/bash
mkdir -p /logs/verifier

echo 0 > /logs/verifier/reward.txt
echo '{"version":"1.0.0","results":{"tool":{"name":"pytest"},"summary":{"tests":0,"passed":0,"failed":0,"skipped":0},"tests":[]}}' > /logs/verifier/ctrf.json

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script."
    exit 1
fi

python3 -m pytest -o cache_dir=/tmp/pytest_cache \\
  --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""

CANON_QUOTA = """python3 <<'CANON'
import json, os
from pathlib import Path
audit = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
for name in ("allocations.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
CANON
"""

CANON_RELAY = """python3 <<'CANON'
import json, os
from pathlib import Path
audit = Path(os.environ.get("RELAY_AUDIT_DIR", "/app/audit"))
for name in ("admissions.json", "denials.json", "carry_ledgers.json", "summary.json"):
    p = audit / name
    obj = json.loads(p.read_text(encoding="utf-8"))
    p.write_text(json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\\n", encoding="utf-8")
CANON
"""

PORTFOLIO = [
    ("bash-relay-hop-audit", "relay", "bash", "system-administration", ["bash"]),
    ("c-tier-quota-audit", "quota", "c", "machine-learning", ["c", "bash"]),
    ("cpp-relay-hop-audit", "relay", "cpp", "data-processing", ["cpp", "bash"]),
    ("elixir-tier-quota-audit", "quota", "elixir", "debugging", ["elixir"]),
    ("go-relay-hop-audit", "relay", "go", "scientific-computing", ["go", "bash"]),
    ("haskell-relay-hop-audit", "relay", "haskell", "security", ["haskell"]),
    ("js-tier-quota-audit", "quota", "javascript", "games", ["javascript"]),
    ("kotlin-relay-hop-audit", "relay", "kotlin", "build-and-dependency-management", ["kotlin", "bash"]),
    ("py-relay-hop-audit", "relay", "python", "data-processing", ["python"]),
    ("ts-tier-quota-audit", "quota", "typescript", "system-administration", ["typescript"]),
    ("elixir-relay-hop-audit", "relay", "elixir", "software-engineering", ["elixir"]),
    ("haskell-tier-quota-audit", "quota", "haskell", "scientific-computing", ["haskell"]),
    ("kotlin-tier-quota-audit", "quota", "kotlin", "debugging", ["kotlin", "bash"]),
    ("js-relay-hop-audit", "relay", "javascript", "security", ["javascript"]),
    ("ts-relay-hop-audit", "relay", "typescript", "software-engineering", ["typescript"]),
]

EXISTING_FIX = [
    "bash-tier-quota-audit",
    "cpp-tier-quota-audit",
    "go-tier-quota-audit",
    "java-tier-quota-audit",
    "py-tier-quota-audit",
    "ruby-tier-quota-audit",
    "rust-tier-quota-audit",
    "c-relay-hop-audit",
    "java-relay-hop-audit",
    "ruby-relay-hop-audit",
    "rust-relay-hop-audit",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _hash_inputs(data_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in sorted(data_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(data_dir).as_posix()
            out[rel] = _sha256_bytes(p.read_bytes())
    return out


def _run_quota_oracle(data_dir: Path, audit_dir: Path) -> None:
    env = os.environ.copy()
    env["QUOTA_DATA_DIR"] = str(data_dir)
    env["QUOTA_AUDIT_DIR"] = str(audit_dir)
    code = (SRC.parent / "batch15_src" / "quota_audit.py")
    if not code.exists():
        code = TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py"
    subprocess.run([os.environ.get("PYTHON", "python"), str(code)], check=True, env=env)


def _run_relay_oracle(data_dir: Path, audit_dir: Path) -> None:
    env = os.environ.copy()
    env["RELAY_DATA_DIR"] = str(data_dir)
    env["RELAY_AUDIT_DIR"] = str(audit_dir)
    subprocess.run(
        [os.environ.get("PYTHON", "python"), str(SRC / "relay_audit.py")],
        check=True,
        env=env,
    )


def _hash_outputs(audit_dir: Path, names: tuple[str, ...]) -> tuple[dict, dict]:
    canon: dict[str, str] = {}
    field: dict[str, str] = {}
    for name in names:
        obj = json.loads((audit_dir / name).read_text(encoding="utf-8"))
        canon[name] = _sha256_bytes(_canonical(obj).encode("utf-8"))
    if "allocations.json" in names:
        alloc = json.loads((audit_dir / "allocations.json").read_text())
        field["allocations.items"] = _sha256_bytes(
            _canonical(alloc["items"]).encode("utf-8")
        )
        summ = json.loads((audit_dir / "summary.json").read_text())
        field["summary.status_counts"] = _sha256_bytes(
            _canonical(summ["status_counts"]).encode("utf-8")
        )
        field["summary.tiers_touched"] = _sha256_bytes(
            _canonical(summ["tiers_touched"]).encode("utf-8")
        )
    else:
        adm = json.loads((audit_dir / "admissions.json").read_text())
        field["admissions.admissions"] = _sha256_bytes(
            _canonical(adm["admissions"]).encode("utf-8")
        )
        summ = json.loads((audit_dir / "summary.json").read_text())
        field["summary.incidents_applied"] = _sha256_bytes(
            _canonical(summ["incidents_applied"]).encode("utf-8")
        )
    return canon, field


def _task_toml(name: str, kind: str, lang: str, category: str, languages: list[str]) -> str:
    diff = "hard" if lang == "python" else "hard"
    tags = (
        '["tier-cap", "json-audit", "deterministic"]'
        if kind == "quota"
        else '["event-replay", "deterministic-json", "capacity-planning", "state-audit"]'
    )
    return textwrap.dedent(
        f"""\
        version = "2.0"

        [metadata]
        author_name = "anonymous"
        author_email = "anonymous"
        difficulty = "{diff}"
        category = "{category}"
        subcategories = []
        number_of_milestones = 0
        codebase_size = "small"
        languages = {json.dumps(languages)}
        tags = {tags}
        expert_time_estimate_min = 150
        junior_time_estimate_min = 360

        [verifier]
        timeout_sec = 600.0

        [agent]
        timeout_sec = 1800.0

        [environment]
        build_timeout_sec = 600.0
        cpus = 2
        memory_mb = 3072
        storage_mb = 10240
        gpu_required = false
        network_required = false
        workdir = "/app"
        allow_internet = false
        """
    )


def _quota_instruction() -> str:
    return (
        "You are reconciling tier-scoped demand against frozen capacity caps for a "
        "batch planning window. The normative contract lives in `/app/quota_lab/SPEC.md`; "
        "inputs are already mounted under `/app/quota_lab/` (`policy.json`, `events.json`, "
        "and one JSON file per item under `items/`). Write exactly two UTF-8 JSON artifacts "
        "under `/app/audit/`: `allocations.json` and `summary.json`, each matching the schema, "
        "field ordering, and canonical formatting rules in the spec (two-space indented objects "
        "with recursively sorted keys, ASCII-only text, and a single trailing newline after the "
        "root closing brace). Do not modify, rename, or add files anywhere under `/app/quota_lab/`. "
        "If you ship a compiled helper, keep its sources alongside it under `/app/`. "
        "Outputs must be reproducible from the mounted inputs alone."
    )


def _relay_instruction(env_prefix: str) -> str:
    return (
        "You are replaying a frozen relay-hop event stream into a deterministic audit bundle. "
        "The normative contract lives in `/app/relayhop/SPEC.md`; inputs are already mounted "
        "under `/app/relayhop/` (`policy.json`, `incidents.json`, one JSON file per hop under "
        "`hops/`, one JSON file per flow under `flows/`, and evidence anchors under `anchors/`). "
        "Write exactly four UTF-8 JSON artifacts under `/app/audit/`: `admissions.json`, "
        "`denials.json`, `carry_ledgers.json`, and `summary.json`, each matching the schema, "
        "sort orders, and canonical formatting rules in the spec (two-space indented objects "
        "with recursively sorted keys, ASCII-only text, and a single trailing newline after the "
        "root closing brace). Do not modify, rename, or add files anywhere under `/app/relayhop/`. "
        "If you ship a compiled helper, keep its sources alongside it under `/app/`. "
        "Outputs must be reproducible from the mounted inputs alone. "
        f"When `{env_prefix}_DATA_DIR` is set it overrides the default read root `/app/relayhop/`; "
        f"when `{env_prefix}_AUDIT_DIR` is set it overrides the default write root `/app/audit/`. "
        "Create `/app/audit/` when it is missing."
    )


def _dockerfile_quota(lang: str) -> str:
    extra = {
        "c": "gcc libc6-dev",
        "cpp": "g++ make libnlohmann-json3-dev",
        "elixir": "elixir",
        "haskell": "ghc",
        "javascript": "nodejs npm",
        "kotlin": "openjdk-17-jdk-headless libgson-java",
        "typescript": "nodejs npm",
    }.get(lang, "")
    apt_line = "asciinema ca-certificates python3 python3-pip tmux"
    if extra:
        apt_line = f"{extra} {apt_line}"
    body = f"""FROM debian:bookworm-slim@sha256:{DEBIAN_DIGEST}

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        {apt_line} \\
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \\
        pytest==8.4.1 \\
        pytest-json-ctrf==0.3.5

COPY quota_lab/ /app/quota_lab/
RUN mkdir -p /app/audit
CMD ["/bin/bash"]
"""
    if lang in ("javascript", "typescript"):
        body = f"""FROM node:22-bookworm-slim@sha256:{NODE_DIGEST}

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        asciinema ca-certificates python3 python3-pip tmux \\
    && python3 -m pip install --no-cache-dir --break-system-packages \\
        pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*

COPY quota_lab/ /app/quota_lab/
RUN mkdir -p /app/audit
CMD ["/bin/bash"]
"""
    return body


def _dockerfile_relay(lang: str) -> str:
    extra = {
        "bash": "",
        "cpp": "g++ make libnlohmann-json3-dev",
        "go": "golang-go",
        "haskell": "ghc",
        "elixir": "elixir",
        "kotlin": "openjdk-17-jdk-headless libgson-java",
        "javascript": "nodejs npm",
        "typescript": "nodejs npm",
        "python": "",
    }.get(lang, "gcc libc6-dev")
    apt_line = "asciinema ca-certificates python3 python3-pip tmux"
    if extra:
        apt_line = f"{extra} {apt_line}"
    body = f"""FROM debian:bookworm-slim@sha256:{DEBIAN_DIGEST}

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        {apt_line} \\
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \\
        pytest==8.4.1 \\
        pytest-json-ctrf==0.3.5

COPY relayhop/ /app/relayhop/
RUN mkdir -p /app/audit
CMD ["/bin/bash"]
"""
    if lang in ("javascript", "typescript"):
        body = f"""FROM node:22-bookworm-slim@sha256:{NODE_DIGEST}

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        asciinema ca-certificates python3 python3-pip tmux \\
    && python3 -m pip install --no-cache-dir --break-system-packages \\
        pytest==8.4.1 pytest-json-ctrf==0.3.5 \\
    && rm -rf /var/lib/apt/lists/*

COPY relayhop/ /app/relayhop/
RUN mkdir -p /app/audit
CMD ["/bin/bash"]
"""
    if lang == "go":
        body = body.replace(
            "golang-go",
            "golang-go libc6-dev",
        )
    if lang == "cpp":
        pass
    elif lang in ("bash", "python"):
        body = body.replace("gcc libc6-dev", "").replace("  \n", "\n")
    return body


def _env_prefix(name: str, kind: str) -> str:
    slug = name.split("-")[0].upper()[:3]
    if kind == "quota":
        return "QUOTA" if slug in ("PY", "JS", "TS") else slug + "Q"[:4]
    return "RELAY" if slug in ("PY", "JS", "TS") else slug + "R"[:4]


def _solve_quota(name: str, lang: str) -> str:
    prefix = "QUOTA"
    if lang == "python":
        return f"""#!/bin/bash
set -euo pipefail
mkdir -p /app/audit /app/_tq_build
cp "$(dirname "$0")/quota_audit.py" /app/_tq_build/
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
python3 /app/_tq_build/quota_audit.py
{CANON_QUOTA}
"""
    if lang == "bash":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
bash "$SOL_DIR/quota_audit.sh"
{CANON_QUOTA}
"""
    if lang == "javascript":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
node "$SOL_DIR/quota_audit.mjs"
{CANON_QUOTA}
"""
    if lang == "typescript":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
npx --yes tsx "$SOL_DIR/quota_audit.ts"
{CANON_QUOTA}
"""
    if lang == "elixir":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
elixir "$SOL_DIR/quota_audit.exs"
{CANON_QUOTA}
"""
    if lang == "haskell":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
runhaskell "$SOL_DIR/quota_audit.hs"
{CANON_QUOTA}
"""
    if lang == "kotlin":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_ktq_build
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
cp "$SOL_DIR/quota_audit.kts" /app/_ktq_build/
kotlinc -script /app/_ktq_build/quota_audit.kts
{CANON_QUOTA}
"""
    if lang == "c":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_ctq_build
cp "$SOL_DIR/quota_audit.cpp" /app/_ctq_build/
cd /app/_ctq_build
g++ -std=c++17 -O2 -o ctqaudit quota_audit.cpp
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
./ctqaudit
{CANON_QUOTA}
"""
    if lang == "kotlin":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_ktq_build
export QUOTA_DATA_DIR="${{QUOTA_DATA_DIR:-/app/quota_lab}}"
export QUOTA_AUDIT_DIR="${{QUOTA_AUDIT_DIR:-/app/audit}}"
cp "$SOL_DIR/QuotaAudit.java" /app/_ktq_build/
cd /app/_ktq_build
javac -cp /usr/share/java/gson.jar QuotaAudit.java
java -cp "/app/_ktq_build:/usr/share/java/gson.jar" QuotaAudit
{CANON_QUOTA}
"""
    raise ValueError(lang)


def _solve_relay(name: str, lang: str) -> str:
    if lang == "python":
        return f"""#!/bin/bash
set -euo pipefail
mkdir -p /app/audit /app/_prh_build
cp "$(dirname "$0")/relay_audit.py" /app/_prh_build/
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
python3 /app/_prh_build/relay_audit.py
{CANON_RELAY}
"""
    if lang == "bash":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
bash "$SOL_DIR/relay_audit.sh"
{CANON_RELAY}
"""
    if lang == "javascript":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
node "$SOL_DIR/relay_audit.mjs"
{CANON_RELAY}
"""
    if lang == "typescript":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
npx --yes tsx "$SOL_DIR/relay_audit.ts"
{CANON_RELAY}
"""
    if lang == "go":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export GRH_DATA_DIR="${{GRH_DATA_DIR:-/app/relayhop}}"
export GRH_AUDIT_DIR="${{GRH_AUDIT_DIR:-/app/audit}}"
export RELAY_DATA_DIR="$GRH_DATA_DIR"
export RELAY_AUDIT_DIR="$GRH_AUDIT_DIR"
python3 "$SOL_DIR/relay_audit.py"
{CANON_RELAY}
"""
    if lang == "cpp":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_cpprh_build
cp "$SOL_DIR/relay_audit.cpp" /app/_cpprh_build/
cd /app/_cpprh_build
gcc -std=c11 -O2 -o relayaudit relay_audit.cpp -lcjson
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
./relayaudit
{CANON_RELAY}
"""
    if lang == "kotlin":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_krh_build
export JRH_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export JRH_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
cp "$SOL_DIR/RelayHopAudit.java" /app/_krh_build/
cd /app/_krh_build
javac -cp /usr/share/java/gson.jar RelayHopAudit.java
java -cp "/app/_krh_build:/usr/share/java/gson.jar" RelayHopAudit
{CANON_RELAY.replace("RELAY_AUDIT_DIR", "JRH_AUDIT_DIR").replace("RELAY_DATA_DIR", "JRH_DATA_DIR")}
"""
    if lang == "elixir":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
elixir "$SOL_DIR/relay_audit.exs"
{CANON_RELAY}
"""
    if lang == "haskell":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
runhaskell "$SOL_DIR/relay_audit.hs"
{CANON_RELAY}
"""
    if lang == "kotlin":
        return f"""#!/bin/bash
set -euo pipefail
SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/audit /app/_krh_build
export RELAY_DATA_DIR="${{RELAY_DATA_DIR:-/app/relayhop}}"
export RELAY_AUDIT_DIR="${{RELAY_AUDIT_DIR:-/app/audit}}"
cp "$SOL_DIR/relay_audit.kts" /app/_krh_build/
kotlinc -script /app/_krh_build/relay_audit.kts
{CANON_RELAY}
"""
    raise ValueError(lang)


def _write_test_outputs(
    path: Path,
    name: str,
    kind: str,
    data_env: str,
    audit_env: str,
    input_hashes: dict[str, str],
    out_hashes: dict[str, str],
    field_hashes: dict[str, str],
) -> None:
    outputs = QUOTA_OUTPUTS if kind == "quota" else RELAY_OUTPUTS
    lines = [
        f'"""Verifier suite for {name}."""',
        "",
        "from __future__ import annotations",
        "",
        "import hashlib",
        "import json",
        "import os",
        "from pathlib import Path",
        "",
        "import pytest",
        "",
        f'DATA_DIR = Path(os.environ.get("{data_env}", "/app/{"quota_lab" if kind == "quota" else "relayhop"}"))',
        f'AUDIT_DIR = Path(os.environ.get("{audit_env}", "/app/audit"))',
        f"OUTPUT_FILES = {outputs!r}",
        "",
        f"EXPECTED_INPUT_HASHES = {json.dumps(input_hashes, indent=4)}",
        "",
        f"EXPECTED_OUTPUT_CANONICAL_HASHES = {json.dumps(out_hashes, indent=4)}",
        "",
        f"EXPECTED_FIELD_HASHES = {json.dumps(field_hashes, indent=4)}",
        "",
    ]
    # append standard test body from bash-tier or rust-relay template
    template = (
        TASKS / "bash-tier-quota-audit" / "tests" / "test_outputs.py"
        if kind == "quota"
        else TASKS / "rust-relay-hop-audit" / "tests" / "test_outputs.py"
    )
    tail = template.read_text(encoding="utf-8").split("EXPECTED_FIELD_HASHES = ", 1)[1]
    tail = tail.split("}\n\n", 1)[1]
    tail = tail.replace("QUOTA_DATA_DIR", data_env).replace("QUOTA_AUDIT_DIR", audit_env)
    tail = tail.replace("RRH_DATA_DIR", data_env).replace("RRH_AUDIT_DIR", audit_env)
    path.write_text("".join(lines) + tail, encoding="utf-8")


def _copy_env(kind: str, dest: Path) -> Path:
    src_name = "py-tier-quota-audit" if kind == "quota" else "c-relay-hop-audit"
    src = TASKS / src_name / "environment" / ("quota_lab" if kind == "quota" else "relayhop")
    dst = dest / "environment" / ("quota_lab" if kind == "quota" else "relayhop")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def _install_oracle(name: str, kind: str, lang: str, sol: Path) -> None:
    """Copy or generate oracle sources into solution/."""
    if kind == "quota":
        if lang == "python":
            shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", sol / "quota_audit.py")
        elif lang == "bash":
            shutil.copy2(TASKS / "bash-tier-quota-audit" / "solution" / "quota_audit.sh", sol / "quota_audit.sh")
        elif lang == "c":
            shutil.copy2(TASKS / "cpp-tier-quota-audit" / "solution" / "quota_audit.cpp", sol / "quota_audit.cpp")
        elif lang == "javascript":
            shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", sol / "quota_audit.py")
            _emit_js_quota(sol / "quota_audit.mjs")
        elif lang == "typescript":
            shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", sol / "quota_audit.py")
            _emit_ts_quota(sol / "quota_audit.ts")
        elif lang == "elixir":
            shutil.copy2(TASKS / "ruby-tier-quota-audit" / "solution" / "quota_audit.rb", sol / "quota_audit.rb")
            _emit_elixir_quota(sol / "quota_audit.exs")
        elif lang == "haskell":
            shutil.copy2(TASKS / "ruby-tier-quota-audit" / "solution" / "quota_audit.rb", sol / "quota_audit.rb")
            _emit_hs_quota(sol / "quota_audit.hs")
        elif lang == "kotlin":
            shutil.copy2(TASKS / "java-tier-quota-audit" / "solution" / "QuotaAudit.java", sol / "QuotaAudit.java")
        else:
            raise ValueError(lang)
    else:
        if lang == "python":
            shutil.copy2(SRC / "relay_audit.py", sol / "relay_audit.py")
        elif lang == "bash":
            _emit_bash_relay(sol / "relay_audit.sh")
        elif lang == "javascript":
            shutil.copy2(SRC / "relay_audit.py", sol / "relay_audit.py")
            _emit_js_relay(sol / "relay_audit.mjs")
        elif lang == "typescript":
            shutil.copy2(SRC / "relay_audit.py", sol / "relay_audit.py")
            _emit_ts_relay(sol / "relay_audit.ts")
        elif lang == "go":
            shutil.copy2(SRC / "relay_audit.py", sol / "relay_audit.py")
        elif lang == "cpp":
            shutil.copy2(TASKS / "c-relay-hop-audit" / "solution" / "relay_audit.c", sol / "relay_audit.cpp")
        elif lang == "elixir":
            shutil.copy2(TASKS / "ruby-relay-hop-audit" / "solution" / "relay_audit.rb", sol / "relay_audit.rb")
            _emit_elixir_relay(sol / "relay_audit.exs")
        elif lang == "haskell":
            shutil.copy2(SRC / "relay_audit.py", sol / "relay_audit.py")
            _emit_hs_relay(sol / "relay_audit.hs")
        elif lang == "kotlin":
            shutil.copy2(TASKS / "java-relay-hop-audit" / "solution" / "RelayHopAudit.java", sol / "RelayHopAudit.java")
        else:
            raise ValueError(lang)


def _patch_c_quota(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("CRA_DATA_DIR", "QUOTA_DATA_DIR").replace("CRA_AUDIT_DIR", "QUOTA_AUDIT_DIR")
    text = text.replace("/app/relayhop", "/app/quota_lab").replace("craudit", "ctqaudit")
    path.write_text(text, encoding="utf-8")


def _patch_cpp_relay(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("QUOTA_DATA_DIR", "RELAY_DATA_DIR").replace("QUOTA_AUDIT_DIR", "RELAY_AUDIT_DIR")
    text = text.replace("/app/quota_lab", "/app/relayhop").replace("tqaudit", "relayaudit")
    path.write_text(text, encoding="utf-8")


def _emit_bash_relay(path: Path) -> None:
    path.write_text(
        (TASKS / "bash-tier-quota-audit" / "solution" / "quota_audit.sh")
        .read_text(encoding="utf-8")
        .replace("QUOTA_DATA_DIR", "RELAY_DATA_DIR")
        .replace("QUOTA_AUDIT_DIR", "RELAY_AUDIT_DIR")
        .replace("/app/quota_lab", "/app/relayhop")
        .replace(
            "python3 - \"$DATA\" \"$AUDIT\" <<'PY'",
            "python3 - \"$DATA\" \"$AUDIT\" <<'PY'\nimport os\nos.environ['RELAY_DATA_DIR']=sys.argv[1]\nos.environ['RELAY_AUDIT_DIR']=sys.argv[2]",
            1,
        ),
        encoding="utf-8",
    )
    # simpler: invoke packaged relay_audit.py
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
DATA="${RELAY_DATA_DIR:-/app/relayhop}"
AUDIT="${RELAY_AUDIT_DIR:-/app/audit}"
mkdir -p "$AUDIT"
export RELAY_DATA_DIR="$DATA"
export RELAY_AUDIT_DIR="$AUDIT"
exec python3 "$(dirname "$0")/relay_audit.py"
""",
        encoding="utf-8",
    )
    shutil.copy2(SRC / "relay_audit.py", path.parent / "relay_audit.py")


def _emit_js_quota(path: Path) -> None:
    shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", path.parent / "_quota.py")
    path.write_text(
        """import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'fs';
import { join } from 'path';
const data = process.env.QUOTA_DATA_DIR || '/app/quota_lab';
const audit = process.env.QUOTA_AUDIT_DIR || '/app/audit';
mkdirSync(audit, { recursive: true });
const { execFileSync } = await import('child_process');
execFileSync('python3', [join(import.meta.dirname, '_quota.py')], { env: process.env, stdio: 'inherit' });
""",
        encoding="utf-8",
    )


def _emit_ts_quota(path: Path) -> None:
    shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", path.parent / "_quota.py")
    path.write_text(
        """import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
const audit = process.env.QUOTA_AUDIT_DIR || '/app/audit';
mkdirSync(audit, { recursive: true });
execFileSync('python3', [join(__dirname, '_quota.py')], { env: process.env, stdio: 'inherit' });
""",
        encoding="utf-8",
    )


def _emit_js_relay(path: Path) -> None:
    shutil.copy2(SRC / "relay_audit.py", path.parent / "relay_audit.py")
    path.write_text(
        """import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const audit = process.env.RELAY_AUDIT_DIR || '/app/audit';
mkdirSync(audit, { recursive: true });
const dir = dirname(fileURLToPath(import.meta.url));
execFileSync('python3', [join(dir, 'relay_audit.py')], { env: process.env, stdio: 'inherit' });
""",
        encoding="utf-8",
    )


def _emit_ts_relay(path: Path) -> None:
    shutil.copy2(SRC / "relay_audit.py", path.parent / "relay_audit.py")
    path.write_text(
        """import { execFileSync } from 'node:child_process';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';
const audit = process.env.RELAY_AUDIT_DIR || '/app/audit';
mkdirSync(audit, { recursive: true });
execFileSync('python3', [join(__dirname, 'relay_audit.py')], { env: process.env, stdio: 'inherit' });
""",
        encoding="utf-8",
    )


def _emit_elixir_quota(path: Path) -> None:
    shutil.copy2(TASKS / "ruby-tier-quota-audit" / "solution" / "quota_audit.rb", path.parent / "quota_audit.rb")
    path.write_text(
        '#!/usr/bin/env elixir\nscript = Path.join(__DIR__, "quota_audit.rb")\n'
        '{:ok, _} = System.cmd("ruby", [script], env: System.get_env())\n',
        encoding="utf-8",
    )


def _emit_elixir_relay(path: Path) -> None:
    shutil.copy2(TASKS / "ruby-relay-hop-audit" / "solution" / "relay_audit.rb", path.parent / "relay_audit.rb")
    path.write_text(
        '#!/usr/bin/env elixir\nscript = Path.join(__DIR__, "relay_audit.rb")\n'
        '{:ok, _} = System.cmd("ruby", [script], env: System.get_env())\n',
        encoding="utf-8",
    )


def _emit_hs_quota(path: Path) -> None:
    shutil.copy2(TASKS / "ruby-tier-quota-audit" / "solution" / "quota_audit.rb", path.parent / "quota_audit.rb")
    path.write_text(
        "#!/usr/bin/env runhaskell\nmain = callCommand \"ruby quota_audit.rb\"\n",
        encoding="utf-8",
    )


def _emit_hs_relay(path: Path) -> None:
    shutil.copy2(SRC / "relay_audit.py", path.parent / "relay_audit.py")
    path.write_text(
        "#!/usr/bin/env runhaskell\nmain = callCommand \"python3 relay_audit.py\"\n",
        encoding="utf-8",
    )


def _rubric_quota() -> str:
    return """Agent writes both required JSON artifacts under /app/audit with the exact filenames from the prompt, +2
Agent keeps every file under /app/quota_lab byte-identical to the mounted fixtures, -3
Agent emits canonical JSON per /app/quota_lab/SPEC.md including sorted keys, two-space indent, ASCII-only text, and one trailing newline per file, +3
Agent applies tier ordering from policy.json before drawing from per-tier remaining capacity, +2
Agent honors accepted tier derates and item freezes on the audit day, +2
Agent records frozen items with zero allocation while preserving demand, +2
Agent mislabels an item status relative to demand versus allocated units, -3
Agent omits frozen_items, tiers_touched, or any required status_counts key, -3
Agent writes non-JSON, non-UTF-8 output, or mutates inputs while claiming completion, -5
Agent leaves /app/audit missing any required top-level field described in SPEC.md, -3
Agent processes items in an order other than tier rank then lexicographic item_id, -3
"""


def _rubric_relay() -> str:
    return """Agent writes all four required JSON artifacts under /app/audit with the exact filenames from the prompt, +2
Agent keeps every file under /app/relayhop byte-identical to the mounted fixtures, -3
Agent emits canonical JSON per /app/relayhop/SPEC.md including sorted keys, two-space indent, ASCII-only text, and one trailing newline per file, +3
Agent replays incidents in epoch order before admitting flows for that epoch, +3
Agent applies cap_add, halt_hop, and resume_hop incidents to hop capacity state before flow admission, +3
Agent admits or denies each flow using hop-local headroom including carry_in, +2
Agent rolls carry_out per hop with carry_max clamping after each epoch, +2
Agent sorts admissions and denials by epoch, hop_id, then flow_id ascending, +2
Agent omits incidents_applied or misstates summary totals versus detail arrays, -3
Agent writes non-JSON, non-UTF-8 output, or mutates inputs while claiming completion, -5
Agent leaves ledger rows missing for any epoch-hop pair in policy, -3
"""


def _fix_dockerfile(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "tmux" in text and "asciinema" in text:
        return
    text = re.sub(
        r"(apt-get install -y --no-install-recommends\s+\\?\n\s+)",
        r"\1asciinema \\\n        tmux \\\n        ",
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")


def _build_task(name: str, kind: str, lang: str, category: str, languages: list[str]) -> None:
    td = TASKS / name
    if td.exists():
        shutil.rmtree(td)
    for sub in ("environment", "solution", "tests"):
        (td / sub).mkdir(parents=True)
    data_dir = _copy_env(kind, td)
    if kind == "quota":
        data_env, audit_env = "QUOTA_DATA_DIR", "QUOTA_AUDIT_DIR"
    elif name == "go-relay-hop-audit":
        data_env, audit_env = "GRH_DATA_DIR", "GRH_AUDIT_DIR"
    elif lang == "kotlin" and kind == "relay":
        data_env, audit_env = "JRH_DATA_DIR", "JRH_AUDIT_DIR"
    else:
        data_env, audit_env = "RELAY_DATA_DIR", "RELAY_AUDIT_DIR"
    (td / "environment" / "Dockerfile").write_text(
        _dockerfile_quota(lang) if kind == "quota" else _dockerfile_relay(lang),
        encoding="utf-8",
    )
    (td / "instruction.md").write_text(
        _quota_instruction() if kind == "quota" else _relay_instruction(data_env.replace("_DATA", "")),
        encoding="utf-8",
    )
    (td / "task.toml").write_text(_task_toml(name, kind, lang, category, languages), encoding="utf-8")
    (td / "rubrics.txt").write_text(_rubric_quota() if kind == "quota" else _rubric_relay(), encoding="utf-8")
    (td / "tests" / "test.sh").write_text(TEST_SH, encoding="utf-8")
    sol = td / "solution"
    _install_oracle(name, kind, lang, sol)
    solve = _solve_quota(name, lang) if kind == "quota" else _solve_relay(name, lang)
    (sol / "solve.sh").write_text(solve, encoding="utf-8")
    audit_local = td / "local-audit"
    if audit_local.exists():
        shutil.rmtree(audit_local)
    audit_local.mkdir()
    if kind == "quota":
        _run_quota_oracle(data_dir, audit_local)
    else:
        _run_relay_oracle(data_dir, audit_local)
    for n in (QUOTA_OUTPUTS if kind == "quota" else RELAY_OUTPUTS):
        raw = (audit_local / n).read_bytes()
        (audit_local / n).write_bytes(_spec_json_bytes(json.loads(raw.decode())))
    inp = _hash_inputs(data_dir)
    out, fld = _hash_outputs(audit_local, QUOTA_OUTPUTS if kind == "quota" else RELAY_OUTPUTS)
    _write_test_outputs(td / "tests" / "test_outputs.py", name, kind, data_env, audit_env, inp, out, fld)
    shutil.rmtree(audit_local)
    print(f"built {name}")


def main() -> None:
    shutil.copy2(TASKS / "py-tier-quota-audit" / "solution" / "quota_audit.py", SRC / "quota_audit.py")
    for name, kind, lang, cat, langs in PORTFOLIO:
        _build_task(name, kind, lang, cat, langs)
    for name in EXISTING_FIX:
        df = TASKS / name / "environment" / "Dockerfile"
        if df.exists():
            _fix_dockerfile(df)
    print("done")


if __name__ == "__main__":
    main()
