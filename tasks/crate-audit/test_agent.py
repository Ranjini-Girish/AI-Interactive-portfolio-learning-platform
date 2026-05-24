#!/usr/bin/env python3
"""Simulated single-turn agent test for rust-crate-audit-hard."""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TASK_DIR = Path(__file__).parent
ENV_DIR = TASK_DIR / "environment"

def load_dotenv():
    env_file = TASK_DIR.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

load_dotenv()

def collect_context():
    parts = []
    parts.append("## instruction.md\n" + (TASK_DIR / "instruction.md").read_text())
    parts.extend(f"## docs/{doc.name}\n{doc.read_text()}" for doc in sorted((ENV_DIR / "docs").glob("*.md")))
    parts.append("## data/config.json\n" + (ENV_DIR / "data" / "config.json").read_text())
    parts.append("## data/project.json\n" + (ENV_DIR / "data" / "project.json").read_text())
    parts.extend(f"## data/registry/{reg.name}\n{reg.read_text()}" for reg in sorted((ENV_DIR / "data" / "registry").glob("*.json")))
    parts.append("## environment/Cargo.toml\n" + (ENV_DIR / "Cargo.toml").read_text())
    return "\n\n".join(parts)

SYSTEM_PROMPT = """You are an expert Rust developer. You are working in a Docker container with Rust 1.83 installed.
Your working directory is /app. The data files are at /app/data/ and docs at /app/docs/.
You must write the implementation in Rust using serde and serde_json (already in Cargo.toml).
Your compiled binary must be placed at /app/build/crate-audit and when run, it must produce /app/output/audit_report.json.
Write ONLY the complete Rust source code for src/main.rs. Output it in a single ```rust code block.
The code must compile and run correctly in one attempt — you will not get a chance to iterate."""

def call_model(model, context, provider):
    if provider == "openai":
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": context}
            ],
            temperature=0.3,
            max_tokens=16000,
        )
        return resp.choices[0].message.content
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        with client.messages.stream(
            model=model,
            max_tokens=32000,
            temperature=0.3,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        ) as stream:
            text_parts = list(stream.text_stream)
        return "".join(text_parts)

def extract_rust(text):
    m = re.search(r"```rust\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1)
    return text

def test_in_docker(rust_code):
    tmp = TASK_DIR / "_agent_main.rs"
    tmp.write_text(rust_code, encoding="utf-8")
    try:
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{TASK_DIR / 'tests'}:/tests",
            "-v", f"{tmp}:/agent_main.rs",
            "crate-test", "bash", "-c",
            """
set -e
cp /agent_main.rs /app/src/main.rs
cd /app
cargo build --release 2>&1
cp /app/target/release/crate-audit /app/build/crate-audit
chmod +x /app/build/crate-audit
/app/build/crate-audit 2>&1 || true

apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq curl >/dev/null 2>&1
curl -LsSf https://astral.sh/uv/0.9.5/install.sh 2>/dev/null | sh 2>/dev/null
source $HOME/.local/bin/env
uvx -p 3.13 -w pytest==8.4.1 pytest /tests/test_outputs.py -v --tb=short 2>&1
"""
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return result.stdout + result.stderr, result.returncode
    finally:
        tmp.unlink(missing_ok=True)

MODELS = [
    ("claude-opus-4-6", "anthropic"),
]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    context = collect_context()
    print(f"Context size: {len(context)} chars")

    for model, provider in MODELS:
        if which != "all" and which not in model:
            continue
        print(f"\n{'='*60}")
        print(f"Testing: {model} ({provider})")
        print(f"{'='*60}")

        try:
            t0 = time.time()
            response = call_model(model, context, provider)
            t1 = time.time()
            print(f"Model responded in {t1-t0:.1f}s ({len(response)} chars)")

            rust_code = extract_rust(response)
            print(f"Extracted Rust code: {len(rust_code)} chars")

            outfile = TASK_DIR / f"_agent_response_{model.replace('-','_')}.txt"
            outfile.write_text(response, encoding="utf-8")

            output, rc = test_in_docker(rust_code)
            print(output[-3000:])
            passed = "passed" in output and "failed" not in output.split("passed")[-1][:50]

            m = re.search(r"(\d+) passed", output)
            total_passed = int(m.group(1)) if m else 0
            m2 = re.search(r"(\d+) failed", output)
            total_failed = int(m2.group(1)) if m2 else 0

            print(f"\nResult: {total_passed} passed, {total_failed} failed")
            print(f"VERDICT: {'PASS' if rc == 0 else 'FAIL'}")

        except Exception as e:
            print(f"ERROR: {e}")
