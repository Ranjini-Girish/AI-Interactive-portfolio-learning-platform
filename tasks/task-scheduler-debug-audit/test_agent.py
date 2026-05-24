#!/usr/bin/env python3
"""Single-turn agent test: can the model identify and fix all 8 bugs?"""
import os
import sys
import time
import re
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

TASK_DIR = Path(__file__).parent
ENV_DIR = TASK_DIR / "environment"


def load_dotenv():
    for env_file in [TASK_DIR.parent.parent / ".env", TASK_DIR.parent / ".env"]:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())

load_dotenv()


def collect_context():
    parts = []
    parts.append("## instruction.md\n" + (TASK_DIR / "instruction.md").read_text(encoding="utf-8"))
    for doc in sorted((ENV_DIR / "docs").glob("*.md")):
        parts.append(f"## docs/{doc.name}\n{doc.read_text(encoding='utf-8')}")
    parts.append("## data/tasks.json\n" + (ENV_DIR / "data" / "tasks.json").read_text(encoding="utf-8"))
    parts.append("## Cargo.toml\n" + (ENV_DIR / "Cargo.toml").read_text(encoding="utf-8"))
    for src in sorted((ENV_DIR / "src").glob("*.rs")):
        parts.append(f"## src/{src.name}\n{src.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


SYSTEM_PROMPT = """You are an expert Rust developer debugging a task scheduler.
Your working directory is /app. The project compiles but produces incorrect output.
You must identify all bugs in graph.rs, scheduler.rs, critical.rs, stats.rs, and report.rs.
Write a shell script (bash) that applies targeted fixes using sed/perl commands.
The script must:
- Start with #!/bin/bash and set -euo pipefail
- Fix all bugs in the 5 source files
- Preserve build-tag comments at the end of each file
- End by running cargo build --release and cargo run --release
Output ONLY the complete bash script in a single ```bash code block."""


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
            temperature=0.2,
            max_tokens=16000,
        )
        return resp.choices[0].message.content
    else:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        resp = client.messages.create(
            model=model,
            max_tokens=16000,
            temperature=0.2,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": context}],
        )
        return resp.content[0].text


def check_fixes(response):
    """Analyze whether the response addresses all 8 bugs."""
    text = response.lower()

    bugs_found = {
        "Bug1_graph_tiebreak": False,
        "Bug2_scheduler_start_minus1": False,
        "Bug3_scheduler_depth_min_vs_max": False,
        "Bug4_critical_saturating_sub": False,
        "Bug5_stats_avg_floor_vs_round": False,
        "Bug6_stats_resources_field": False,
        "Bug7_stats_parallelism_floor": False,
        "Bug8_report_hash_field_order": False,
    }

    # Bug 1: graph.rs tie-breaking (self.id vs other.id)
    if any(x in text for x in ["other.id.cmp(&self.id)", "other.id.cmp", "id tie-break", "id comparison reversed"]):
        bugs_found["Bug1_graph_tiebreak"] = True

    # Bug 2: scheduler.rs start_time - 1 (pipeline overlap)
    if any(x in text for x in ["max_dep_end - 1", "pipeline", "saturating_sub", "- 1", "minus 1", "off-by-one"]):
        if any(x in text for x in ["start_time", "start time", "max_dep_end"]):
            bugs_found["Bug2_scheduler_start_minus1"] = True

    # Bug 3: scheduler.rs depth min vs max
    if any(x in text for x in ["min", "max", "shallowest", "deepest", "resolved_depth"]):
        if any(x in text for x in ["depth", "d < resolved"]):
            bugs_found["Bug3_scheduler_depth_min_vs_max"] = True

    # Bug 4: critical.rs saturating_sub(1)
    if any(x in text for x in ["saturating_sub(1)", "saturating_sub", "duration_ms - 1", "task_contribution"]):
        if any(x in text for x in ["critical", "duration", "path"]):
            bugs_found["Bug4_critical_saturating_sub"] = True

    # Bug 5: stats.rs avg_duration floor vs round
    if any(x in text for x in ["floor", "round", "avg_duration"]):
        if "group" in text or "avg" in text:
            bugs_found["Bug5_stats_avg_floor_vs_round"] = True

    # Bug 6: stats.rs total_resources wrong field
    if any(x in text for x in ["duration_ms", "resources", "t.resources", "wrong field"]):
        if "total_resources" in text or "resource" in text:
            bugs_found["Bug6_stats_resources_field"] = True

    # Bug 7: stats.rs parallelism_ratio floor vs round
    if any(x in text for x in ["parallelism", "ratio"]):
        if any(x in text for x in ["floor", "round", "truncat"]):
            bugs_found["Bug7_stats_parallelism_floor"] = True

    # Bug 8: report.rs hash field order
    if any(x in text for x in ["resources, s.depth", "depth, s.resources", "hash", "field order", "swap"]):
        if any(x in text for x in ["report", "integrity", "format"]):
            bugs_found["Bug8_report_hash_field_order"] = True

    return bugs_found


MODELS = [
    ("gpt-5.2", "openai"),
    ("claude-opus-4-6", "anthropic"),
]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    context = collect_context()
    print(f"Context size: {len(context)} chars")

    results = {}
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

            outfile = TASK_DIR / f"_response_{model.replace('.', '_').replace('-', '_')}.md"
            outfile.write_text(response, encoding="utf-8")
            print(f"Saved to {outfile}")

            bugs = check_fixes(response)
            found = sum(1 for v in bugs.values() if v)
            total = len(bugs)

            print(f"\nBug Detection ({found}/{total}):")
            for bug, detected in bugs.items():
                status = "FOUND" if detected else "MISSED"
                print(f"  {bug}: {status}")

            # Check if they produced a bash script
            m = re.search(r"```(?:bash|sh)\s*\n(.*?)```", response, re.DOTALL)
            if m:
                script = m.group(1)
                print(f"\nScript length: {len(script)} chars")
                # Quick heuristic: count sed/perl commands
                fix_cmds = len(re.findall(r'(sed|perl)\s+-i', script))
                print(f"Fix commands: {fix_cmds}")
            else:
                print("\nNo bash script block found!")

            results[model] = (found, total)
            if found <= 5:
                print(f"\nVERDICT: GOOD - Model missed {total - found} bugs (task is hard)")
            elif found <= 6:
                print("\nVERDICT: BORDERLINE - Model found most bugs")
            else:
                print(f"\nVERDICT: TOO EASY - Model found {found}/{total} bugs")

        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            results[model] = (0, 0)

    print(f"\n{'='*60}")
    print("FINAL SUMMARY")
    print(f"{'='*60}")
    for model, (found, total) in results.items():
        print(f"  {model}: {found}/{total} bugs detected")

    all_hard = all(f <= 5 for f, _ in results.values() if _ > 0)
    if all_hard:
        print("\nTask difficulty: HARD (both models miss multiple bugs)")
    else:
        print("\nTask may need further hardening")
