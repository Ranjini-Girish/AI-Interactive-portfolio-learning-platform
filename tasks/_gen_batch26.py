#!/usr/bin/env python3
"""Generate wal-index-trim-audit and dns-alias-chain-audit task trees."""

from __future__ import annotations

import hashlib
import json
import os
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GOLANG_DIGEST = "167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db"
RUST_DIGEST = "7f3e3d1e4e5b8c2a1f0d9e8b7a6c5d4e3f2a1b0c9d8e7f6a5b4c3d2e1f0a9b8"  # placeholder - use real
# Use golang for both for consistency with other audit tasks
BASE_IMAGE = f"golang:1.23-bookworm@sha256:{GOLANG_DIGEST}"

CANON_SEP = (",", ":")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=CANON_SEP)


def dump_pretty(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# WAL index trim solver
# ---------------------------------------------------------------------------

def solve_wal_trim(data_dir: Path, audit_dir: Path) -> None:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    indexes_doc = json.loads((data_dir / "indexes.json").read_text(encoding="utf-8"))
    links_doc = json.loads((data_dir / "links.json").read_text(encoding="utf-8"))

    window = int(policy["window_size"])
    threshold = float(policy["trim_threshold"])
    warmup = int(policy["warmup_indexes"])
    vote_ratio = float(policy["vote_ratio"])
    current_epoch = int(epochs["current_epoch"])

    if manifest["snapshot_tag"] != manifest["live_tag"]:
        threshold *= 0.5

    segments: dict[str, dict] = {}
    for path in sorted((data_dir / "segments").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        segments[row["segment_id"]] = row

    pinned: set[str] = {sid for sid, row in segments.items() if row.get("pin")}
    for link in links_doc.get("links", []):
        if link["from_segment"] in pinned:
            pinned.add(link["to_segment"])

    active = {
        sid
        for sid, row in segments.items()
        if int(row["epoch"]) >= current_epoch - 1
    }
    total_weight = sum(float(segments[s]["weight"]) for s in active)

    events = sorted(
        indexes_doc["indexes"],
        key=lambda e: (int(e["index"]), e["segment_id"]),
    )

    history: dict[str, list[float]] = {sid: [] for sid in segments}
    trim_rows = []
    vote_rows = []
    stat_rows = []
    segment_states = []
    trim_total = 0
    vote_accepted = 0
    stale_skipped = 0

    for ev in events:
        idx = int(ev["index"])
        sid = ev["segment_id"]
        bytes_val = float(ev["payload_bytes"])
        role = ev["role"]

        stale = sid not in active
        if stale:
            stale_skipped += 1

        hist = history[sid]
        hist.append(bytes_val)
        if len(hist) > window:
            hist.pop(0)
        window_mean = sum(hist) / len(hist)

        hard_pin = sid in pinned
        if idx <= warmup or hard_pin:
            factor = 0.0
            trimmed = False
        elif window_mean > threshold and bytes_val > 0:
            factor = min(1.0, (window_mean - threshold) / bytes_val)
            trimmed = factor > 0
        else:
            factor = 0.0
            trimmed = False

        if not stale:
            trim_rows.append(
                {
                    "bytes_trimmed": round(bytes_val * factor, 6),
                    "index": idx,
                    "segment_id": sid,
                    "trim_factor": round(factor, 6),
                    "trimmed": trimmed,
                }
            )
        if trimmed and not stale:
            trim_total += 1

        same_idx = [x for x in events if int(x["index"]) == idx]
        agree_weight = sum(
            float(segments[x["segment_id"]]["weight"])
            for x in same_idx
            if x["role"] == role and x["segment_id"] in active
        )
        accepted = (
            not stale
            and total_weight > 0
            and agree_weight >= vote_ratio * total_weight
        )
        if accepted:
            vote_accepted += 1

        vote_rows.append(
            {
                "accepted": accepted,
                "agree_weight": round(agree_weight, 6),
                "index": idx,
                "role": role,
                "segment_id": sid,
                "stale": stale,
            }
        )
        stat_rows.append(
            {
                "index": idx,
                "segment_id": sid,
                "window_mean_bytes": round(window_mean, 6),
                "window_size": len(hist),
            }
        )

    for sid in sorted(segments):
        row = segments[sid]
        segment_states.append(
            {
                "epoch": int(row["epoch"]),
                "pin": sid in pinned,
                "segment_id": sid,
                "stale": sid not in active,
                "weight": float(row["weight"]),
            }
        )

    summary = {
        "current_epoch": current_epoch,
        "effective_trim_threshold": round(threshold, 6),
        "index_total": len(events),
        "stale_skipped_total": stale_skipped,
        "trim_total": trim_total,
        "vote_accepted_total": vote_accepted,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_pretty(audit_dir / "segment_states.json", {"segments": segment_states})
    dump_pretty(audit_dir / "trim_plan.json", {"entries": trim_rows})
    dump_pretty(audit_dir / "role_votes.json", {"votes": vote_rows})
    dump_pretty(audit_dir / "index_stats.json", {"stats": stat_rows})
    dump_pretty(audit_dir / "summary.json", summary)


# ---------------------------------------------------------------------------
# DNS alias chain solver
# ---------------------------------------------------------------------------

def solve_dns_chain(data_dir: Path, audit_dir: Path) -> None:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    queries_doc = json.loads((data_dir / "queries.json").read_text(encoding="utf-8"))
    records: dict[str, dict] = {}
    for path in sorted((data_dir / "records").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        records[row["name"]] = row

    max_chain = int(policy["max_chain"])
    warmup = int(policy["warmup_queries"])
    vote_ratio = float(policy["vote_ratio"])
    current_epoch = int(epochs["current_epoch"])

    if manifest["zone_tag"] != manifest["run_tag"]:
        max_chain = max(1, max_chain // 2)

    active = {
        name
        for name, row in records.items()
        if int(row["epoch"]) >= current_epoch - 1
    }

    def resolve_chain(start: str, step: int) -> tuple[list[str], bool, bool]:
        """Return chain names, looped flag, deny_blocked flag."""
        chain = [start]
        seen = {start}
        cur = start
        looped = False
        deny_blocked = False
        for _ in range(max_chain):
            row = records.get(cur)
            if row is None:
                break
            if row.get("deny"):
                deny_blocked = True
                break
            if int(row.get("ttl_step", 0)) < step:
                break
            target = row.get("alias_target")
            if not target:
                break
            if target in seen:
                looped = True
                break
            chain.append(target)
            seen.add(target)
            cur = target
        return chain, looped, deny_blocked

    queries = sorted(
        queries_doc["queries"],
        key=lambda q: (int(q["step"]), q["name"]),
    )

    record_states = []
    chain_rows = []
    vote_rows = []
    query_stats = []
    collapsed_total = 0
    loop_total = 0
    deny_total = 0
    stale_skipped = 0

    for q in queries:
        step = int(q["step"])
        name = q["name"]
        qtype = q["qtype"]

        stale = name not in active
        if stale:
            stale_skipped += 1

        chain, looped, deny_blocked = resolve_chain(name, step)
        collapsed = False
        depth = len(chain)

        if not stale and step > warmup and not looped and not deny_blocked and depth > 1:
            collapsed = True
            collapsed_total += 1
        if looped:
            loop_total += 1
        if deny_blocked:
            deny_total += 1

        if not stale and not looped:
            chain_rows.append(
                {
                    "chain": chain,
                    "collapsed": collapsed,
                    "depth": depth,
                    "name": name,
                    "step": step,
                }
            )

        same_step = [x for x in queries if int(x["step"]) == step]
        agree = sum(
            1 for x in same_step if x["qtype"] == qtype and x["name"] in active
        )
        accepted = not stale and agree >= vote_ratio * len(same_step)
        if accepted:
            pass

        vote_rows.append(
            {
                "accepted": accepted,
                "agree_count": agree,
                "name": name,
                "qtype": qtype,
                "stale": stale,
                "step": step,
            }
        )
        query_stats.append(
            {
                "depth": depth,
                "deny_blocked": deny_blocked,
                "looped": looped,
                "name": name,
                "step": step,
            }
        )

    vote_accepted = sum(1 for v in vote_rows if v["accepted"])

    for name in sorted(records):
        row = records[name]
        record_states.append(
            {
                "deny": bool(row.get("deny")),
                "epoch": int(row["epoch"]),
                "name": name,
                "stale": name not in active,
            }
        )

    summary = {
        "collapsed_total": collapsed_total,
        "current_epoch": current_epoch,
        "deny_blocked_total": deny_total,
        "effective_max_chain": max_chain,
        "loop_total": loop_total,
        "query_total": len(queries),
        "stale_skipped_total": stale_skipped,
        "vote_accepted_total": vote_accepted,
    }

    audit_dir.mkdir(parents=True, exist_ok=True)
    dump_pretty(audit_dir / "record_states.json", {"records": record_states})
    dump_pretty(audit_dir / "chain_plan.json", {"entries": chain_rows})
    dump_pretty(audit_dir / "type_votes.json", {"votes": vote_rows})
    dump_pretty(audit_dir / "query_stats.json", {"stats": query_stats})
    dump_pretty(audit_dir / "summary.json", summary)


def write_fixtures_wal(env: Path) -> None:
    d = env / "waltrim"
    (d / "anchors").mkdir(parents=True)
    (d / "ancillary").mkdir(parents=True)
    (d / "grid").mkdir(parents=True)
    (d / "meta").mkdir(parents=True)
    (d / "segments").mkdir(parents=True)

    dump_pretty(d / "policy.json", {
        "trim_threshold": 100.0,
        "vote_ratio": 0.6,
        "warmup_indexes": 2,
        "window_size": 3,
    })
    dump_pretty(d / "manifest.json", {"live_tag": "prod", "snapshot_tag": "dr"})
    dump_pretty(d / "epochs.json", {"current_epoch": 5})
    dump_pretty(d / "links.json", {
        "links": [{"from_segment": "sg03", "to_segment": "sg07"}],
    })
    dump_pretty(d / "ancillary" / "meta.json", {"pack": "wal-trim-v1"})
    dump_pretty(d / "ancillary" / "notes.json", {"note": "read-only"})
    dump_pretty(d / "grid" / "dims.json", {"cols": 4, "rows": 3})
    dump_pretty(d / "meta" / "seq.json", {"seq": 26})
    (d / "anchors" / "a1.txt").write_text("anchor-wal-1\n", encoding="utf-8")
    (d / "anchors" / "a2.txt").write_text("anchor-wal-2\n", encoding="utf-8")

    segments = [
        ("sg01", 5, 1.2, False),
        ("sg02", 5, 0.9, False),
        ("sg03", 5, 1.0, True),
        ("sg04", 5, 0.8, False),
        ("sg05", 4, 1.1, False),
        ("sg06", 5, 0.7, False),
        ("sg07", 5, 0.6, False),
        ("sg08", 5, 1.3, False),
        ("sg09", 5, 0.5, False),
        ("sg10", 5, 1.4, False),
        ("sg11", 3, 0.4, False),
        ("sg12", 2, 0.3, False),
    ]
    for sid, epoch, weight, pin in segments:
        dump_pretty(d / "segments" / f"{sid}.json", {
            "epoch": epoch,
            "pin": pin,
            "segment_id": sid,
            "weight": weight,
        })

    indexes = [
        (1, "sg01", 40.0, "primary"),
        (1, "sg02", 60.0, "primary"),
        (1, "sg03", 30.0, "replica"),
        (2, "sg04", 50.0, "primary"),
        (2, "sg05", 120.0, "primary"),
        (3, "sg06", 80.0, "replica"),
        (3, "sg07", 20.0, "replica"),
        (3, "sg08", 150.0, "primary"),
        (4, "sg01", 90.0, "primary"),
        (4, "sg09", 110.0, "primary"),
        (5, "sg10", 200.0, "primary"),
        (5, "sg02", 95.0, "replica"),
        (6, "sg04", 130.0, "primary"),
        (6, "sg12", 70.0, "replica"),
    ]
    dump_pretty(d / "indexes.json", {
        "indexes": [
            {
                "index": idx,
                "payload_bytes": pb,
                "role": role,
                "segment_id": sid,
            }
            for idx, sid, pb, role in indexes
        ],
    })


def write_fixtures_dns(env: Path) -> None:
    d = env / "dnschain"
    for sub in ("anchors", "ancillary", "grid", "meta", "records"):
        (d / sub).mkdir(parents=True)

    dump_pretty(d / "policy.json", {
        "max_chain": 6,
        "vote_ratio": 0.6,
        "warmup_queries": 2,
    })
    dump_pretty(d / "manifest.json", {"run_tag": "live", "zone_tag": "staging"})
    dump_pretty(d / "epochs.json", {"current_epoch": 4})
    dump_pretty(d / "ancillary" / "meta.json", {"pack": "dns-chain-v1"})
    dump_pretty(d / "ancillary" / "notes.json", {"note": "read-only"})
    dump_pretty(d / "grid" / "dims.json", {"cols": 3, "rows": 2})
    dump_pretty(d / "meta" / "seq.json", {"seq": 27})
    (d / "anchors" / "b1.txt").write_text("anchor-dns-1\n", encoding="utf-8")
    (d / "anchors" / "b2.txt").write_text("anchor-dns-2\n", encoding="utf-8")

    recs = [
        ("app.example", 4, None, 0, False),
        ("api.example", 4, "svc.example", 10, False),
        ("svc.example", 4, "edge.example", 10, False),
        ("edge.example", 4, None, 10, False),
        ("loop.a", 4, "loop.b", 10, False),
        ("loop.b", 4, "loop.a", 10, False),
        ("deny.example", 4, "svc.example", 10, True),
        ("old.example", 2, "api.example", 5, False),
        ("cdn.example", 4, "edge.example", 10, False),
        ("www.example", 4, "app.example", 10, False),
        ("mail.example", 4, None, 10, False),
        ("ftp.example", 3, "www.example", 8, False),
    ]
    for name, epoch, alias, ttl_step, deny in recs:
        row: dict = {"deny": deny, "epoch": epoch, "name": name, "ttl_step": ttl_step}
        if alias:
            row["alias_target"] = alias
        dump_pretty(d / "records" / f"{name.replace('.', '_')}.json", row)

    queries = [
        (1, "www.example", "A"),
        (1, "api.example", "A"),
        (1, "mail.example", "MX"),
        (2, "cdn.example", "A"),
        (2, "app.example", "A"),
        (3, "loop.a", "CNAME"),
        (3, "deny.example", "A"),
        (4, "old.example", "A"),
        (4, "ftp.example", "A"),
        (5, "svc.example", "A"),
        (5, "edge.example", "A"),
    ]
    dump_pretty(d / "queries.json", {
        "queries": [
            {"name": n, "qtype": qt, "step": s}
            for s, n, qt in queries
        ],
    })


def count_env_files(env: Path) -> int:
    n = 0
    for p in env.rglob("*"):
        if p.is_file() and p.name not in ("Dockerfile", "docker-compose.yaml"):
            n += 1
    return n


def build_task(
    name: str,
    domain: str,
    category: str,
    languages: list[str],
    tags: list[str],
    prefix: str,
    instruction: str,
    spec: str,
    solve_py: str,
    output_files: tuple[str, ...],
    semantic_tests: str,
    rubrics: str,
    solver_fn_name: str,
) -> None:
    task = ROOT / name
    env = task / "environment"
    env.mkdir(parents=True, exist_ok=True)
    (task / "solution").mkdir(exist_ok=True)
    (task / "tests").mkdir(exist_ok=True)

    domain_dir = env / domain
    if name == "wal-index-trim-audit":
        write_fixtures_wal(env)
    else:
        write_fixtures_dns(env)

    (domain_dir / "SPEC.md").write_text(spec.strip() + "\n", encoding="utf-8")

    dockerfile = (
        f"FROM {BASE_IMAGE}\n\n"
        "WORKDIR /app\n\n"
        "RUN apt-get update \\\n"
        "    && apt-get install -y --no-install-recommends \\\n"
        "        asciinema \\\n"
        "        ca-certificates \\\n"
        "        python3 \\\n"
        "        python3-pip \\\n"
        "        tmux \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n\n"
        "RUN python3 -m pip install --no-cache-dir --break-system-packages \\\n"
        "        pytest==8.4.1 \\\n"
        "        pytest-json-ctrf==0.3.5\n\n"
        f"COPY {domain}/ /app/{domain}/\n\n"
        "RUN mkdir -p /app/audit\n\n"
        'ENV GOFLAGS="-mod=mod"\n'
        "ENV GOTOOLCHAIN=local\n\n"
        'CMD ["/bin/bash"]\n'
    )
    (env / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    solve_sh = (
        "#!/bin/bash\n"
        "set -euo pipefail\n\n"
        f'export {prefix}_DATA_DIR="${{{prefix}_DATA_DIR:-/app/{domain}}}"\n'
        f'export {prefix}_AUDIT_DIR="${{{prefix}_AUDIT_DIR:-/app/audit}}"\n'
        f'mkdir -p "${{{prefix}_AUDIT_DIR}}"\n\n'
        "python3 - <<'PY'\n"
        f"{solve_py}\n"
        f'data_dir = Path(os.environ.get("{prefix}_DATA_DIR", "/app/{domain}"))\n'
        f'audit_dir = Path(os.environ.get("{prefix}_AUDIT_DIR", "/app/audit"))\n'
        f"{solver_fn_name}(data_dir, audit_dir)\n"
        "PY\n"
    )
    (task / "solution" / "solve.sh").write_text(solve_sh, encoding="utf-8")

    # Run solver for hashes
    local_audit = task / "local-audit"
    if local_audit.exists():
        import shutil
        shutil.rmtree(local_audit)
    local_audit.mkdir()
    os.environ[f"{prefix}_DATA_DIR"] = str(domain_dir)
    os.environ[f"{prefix}_AUDIT_DIR"] = str(local_audit)
    if name == "wal-index-trim-audit":
        solve_wal_trim(domain_dir, local_audit)
    else:
        solve_dns_chain(domain_dir, local_audit)

    input_hashes = {}
    for p in sorted(domain_dir.rglob("*")):
        if p.is_file():
            rel = p.relative_to(domain_dir).as_posix()
            input_hashes[rel] = sha256_file(p)

    output_canon = {}
    output_raw = {}
    for fname in output_files:
        p = local_audit / fname
        output_raw[fname] = sha256_file(p)
        output_canon[fname] = sha256_bytes(
            canonical(json.loads(p.read_text(encoding="utf-8"))).encode()
        )

    field_hashes = {}
    out = json.loads((local_audit / output_files[0]).read_text())
    if name == "wal-index-trim-audit":
        trim = json.loads((local_audit / "trim_plan.json").read_text())
        summ = json.loads((local_audit / "summary.json").read_text())
        field_hashes["trim_plan.entries"] = sha256_bytes(
            canonical(trim["entries"]).encode()
        )
        field_hashes["summary.effective_trim_threshold"] = sha256_bytes(
            canonical(summ["effective_trim_threshold"]).encode()
        )
        eff_thresh = summ["effective_trim_threshold"]
        pin_seg = "sg03"
        stale_seg = "sg12"
    else:
        chain = json.loads((local_audit / "chain_plan.json").read_text())
        summ = json.loads((local_audit / "summary.json").read_text())
        field_hashes["chain_plan.entries"] = sha256_bytes(
            canonical(chain["entries"]).encode()
        )
        field_hashes["summary.effective_max_chain"] = sha256_bytes(
            canonical(summ["effective_max_chain"]).encode()
        )
        eff_thresh = summ["effective_max_chain"]
        pin_seg = None
        stale_seg = "old.example"

    test_py = generate_test_py(
        name, prefix, domain, output_files, input_hashes,
        output_canon, output_raw, field_hashes, semantic_tests,
    )
    (task / "tests" / "test_outputs.py").write_text(test_py, encoding="utf-8")

    test_sh_src = (ROOT / "cap-slice-reclaim-audit" / "tests" / "test.sh").read_text()
    (task / "tests" / "test.sh").write_text(test_sh_src, encoding="utf-8")

    (task / "instruction.md").write_text(instruction.strip() + "\n", encoding="utf-8")
    (task / "rubrics.txt").write_text(rubrics.strip() + "\n", encoding="utf-8")

    lang_str = ", ".join(f'"{x}"' for x in languages)
    tag_str = ", ".join(f'"{x}"' for x in tags)
    toml = (
        'version = "2.0"\n\n'
        "[metadata]\n"
        'author_name = "anonymous"\n'
        'author_email = "anonymous"\n'
        'difficulty = "hard"\n'
        f'category = "{category}"\n'
        "subcategories = []\n"
        "number_of_milestones = 0\n"
        'codebase_size = "small"\n'
        f"languages = [{lang_str}]\n"
        f"tags = [{tag_str}]\n"
        "expert_time_estimate_min = 150\n"
        "junior_time_estimate_min = 360\n\n"
        "[verifier]\n"
        "timeout_sec = 600.0\n\n"
        "[agent]\n"
        "timeout_sec = 1500.0\n\n"
        "[environment]\n"
        "build_timeout_sec = 600.0\n"
        "docker_flags = []\n"
        "cpus = 2\n"
        "memory_mb = 3072\n"
        "storage_mb = 10240\n"
        "gpus = 0\n"
        "gpu_types = []\n"
        "gpu_required = false\n"
        "network_required = false\n"
        'workdir = "/app"\n'
        "allow_internet = false\n"
    )
    (task / "task.toml").write_text(toml, encoding="utf-8")

    import shutil
    shutil.rmtree(local_audit)
    print(f"{name}: env_files={count_env_files(env)}")


def generate_test_py(
    name: str,
    prefix: str,
    domain: str,
    output_files: tuple[str, ...],
    input_hashes: dict,
    output_canon: dict,
    output_raw: dict,
    field_hashes: dict,
    semantic_tests: str,
) -> str:
    field_lines = semantic_field_asserts(field_hashes)
    return (
        f'"""Verifier suite for {name}."""\n\n'
        "from __future__ import annotations\n\n"
        "import hashlib\n"
        "import json\n"
        "import os\n"
        "from pathlib import Path\n\n"
        "import pytest\n\n"
        f'DATA_DIR = Path(os.environ.get("{prefix}_DATA_DIR", "/app/{domain}"))\n'
        f'AUDIT_DIR = Path(os.environ.get("{prefix}_AUDIT_DIR", "/app/audit"))\n\n'
        f"OUTPUT_FILES = {output_files!r}\n\n"
        f"EXPECTED_INPUT_HASHES = {json.dumps(input_hashes, indent=4)}\n\n"
        f"EXPECTED_OUTPUT_CANONICAL_HASHES = {json.dumps(output_canon, indent=4)}\n\n"
        f"EXPECTED_OUTPUT_RAW_HASHES = {json.dumps(output_raw, indent=4)}\n\n"
        f"EXPECTED_FIELD_HASHES = {json.dumps(field_hashes, indent=4)}\n\n\n"
        "def _sha256_bytes(data: bytes) -> str:\n"
        '    """Return hex SHA-256 of raw bytes."""\n'
        "    return hashlib.sha256(data).hexdigest()\n\n\n"
        "def _canonical(value: object) -> str:\n"
        '    """Minified canonical JSON for hash comparison."""\n'
        '    return json.dumps(value, sort_keys=True, separators=(",", ":"))\n\n\n'
        "def _load_json(path: Path) -> object:\n"
        '    """Load UTF-8 JSON from path."""\n'
        "    return json.loads(path.read_text(encoding=\"utf-8\"))\n\n\n"
        "@pytest.fixture(scope=\"session\")\n"
        "def outputs() -> dict[str, object]:\n"
        '    """Load emitted audit artifacts once per session."""\n'
        "    payload: dict[str, object] = {}\n"
        "    for fname in OUTPUT_FILES:\n"
        "        path = AUDIT_DIR / fname\n"
        '        assert path.is_file(), f"missing emitted artifact: {fname}"\n'
        "        payload[fname] = _load_json(path)\n"
        "    return payload\n\n\n"
        "class TestInputIntegrity:\n"
        '    """Verify the mounted workspace matches the frozen reference bytes."""\n\n'
        "    def test_each_input_file_sha256(self) -> None:\n"
        '        """Every normative input file under the data directory must match its pinned digest."""\n'
        "        for rel, expected in EXPECTED_INPUT_HASHES.items():\n"
        "            path = DATA_DIR / rel\n"
        '            assert path.is_file(), f"missing input fixture: {rel}"\n'
        "            digest = _sha256_bytes(path.read_bytes())\n"
        '            assert digest == expected, f"digest mismatch for {rel}"\n\n\n'
        "class TestReportStructure:\n"
        '    """Verify emitted JSON files exist and hash-lock to the canonical contract."""\n\n'
        "    def test_output_raw_byte_hashes(self) -> None:\n"
        '        """Each audit file UTF-8 bytes must match normative layout."""\n'
        "        for fname, expected in EXPECTED_OUTPUT_RAW_HASHES.items():\n"
        "            digest = _sha256_bytes((AUDIT_DIR / fname).read_bytes())\n"
        '            assert digest == expected, f"raw byte mismatch for {fname}"\n\n'
        "    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:\n"
        '        """Each audit file must match the canonical minified JSON digest."""\n'
        "        for fname, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():\n"
        "            canon = _canonical(outputs[fname])\n"
        "            digest = _sha256_bytes(canon.encode(\"utf-8\"))\n"
        '            assert digest == expected, f"output mismatch for {fname}"\n\n'
        "    def test_output_files_single_trailing_newline(self) -> None:\n"
        '        """Root JSON objects must end with exactly one line feed after the closing brace."""\n'
        "        for fname in OUTPUT_FILES:\n"
        "            raw = (AUDIT_DIR / fname).read_text(encoding=\"utf-8\")\n"
        '            assert raw.endswith("}\\n"), f"{fname} must end with exactly one LF after root brace"\n\n'
        "    def test_field_hashes(self, outputs: dict[str, object]) -> None:\n"
        '        """Selected nested fields must match pinned canonical digests."""\n'
        f"{field_lines}\n\n\n"
        "class TestSemantics:\n"
        '    """Semantic checks for compound audit rules."""\n\n'
        f"{textwrap.indent(textwrap.dedent(semantic_tests).strip(), '    ')}\n"
    )


def semantic_field_asserts(field_hashes: dict) -> str:
    lines = []
    for key in field_hashes:
        top, field = key.split(".", 1)
        lines.append(
            f'        assert _sha256_bytes(_canonical(outputs["{top}.json"]["{field}"]).encode()) == EXPECTED_FIELD_HASHES["{key}"]'
        )
    return "\n".join(lines)


WAL_SPEC = """
Normative contract for the WAL index trim audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `window_size` (positive), float `trim_threshold` (positive), integer `warmup_indexes`, and float `vote_ratio` between zero and one inclusive. Read `manifest.json` for `snapshot_tag` and `live_tag`. When they differ, multiply `trim_threshold` by `0.5` and use the halved value for all trim math; round `effective_trim_threshold` in summary to six decimals. Read `epochs.json` for integer `current_epoch`. Read `indexes.json` for array `indexes` with integer `index`, string `segment_id`, float `payload_bytes`, and string `role` in `primary` or `replica`. Read `links.json` for array `links` with `from_segment` and `to_segment`.

Enumerate every `*.json` under `segments/`. Each segment has string `segment_id`, integer `epoch`, float `weight`, and boolean `pin`. A segment is stale when `epoch` is strictly less than `current_epoch - 1`. Active segments participate in role weight sums. A segment is transitively pinned when it has `pin` true or appears as `to_segment` of a link whose `from_segment` is already pinned. Packaging under `anchors/`, `meta/`, `grid/`, and `ancillary/` is ignored.

Process indexes in ascending `index`, then ascending `segment_id`. Maintain per-segment FIFO history of `payload_bytes` capped at `window_size`. `window_mean_bytes` is the arithmetic mean after appending the current sample.

For each index row, when `index` is less than or equal to `warmup_indexes`, or the segment is transitively pinned, `trim_factor` is `0.0` and `trimmed` is false. Otherwise when `window_mean_bytes` exceeds the effective trim threshold and `payload_bytes` is positive, `trim_factor` is `min(1.0, (window_mean_bytes - effective_trim_threshold) / payload_bytes)`; `trimmed` is true when `trim_factor` is strictly greater than zero. Stale segments still update window history but omit `trim_plan` rows.

Role vote at an index: `agree_weight` sums `weight` of active segments whose row on the same `index` shares the same `role`. The vote is `accepted` when the segment is active and `agree_weight >= vote_ratio * total_active_weight`.

Emit `segment_states.json` with `segments` sorted by `segment_id` (epoch, pin, segment_id, stale, weight). Emit `trim_plan.json` with `entries` sorted by index then segment_id for non-stale rows only (bytes_trimmed, index, segment_id, trim_factor, trimmed). Emit `role_votes.json` with `votes` in processing order (accepted, agree_weight, index, role, segment_id, stale). Emit `index_stats.json` with `stats` in processing order. Emit `summary.json` with current_epoch, effective_trim_threshold, index_total, stale_skipped_total, trim_total, vote_accepted_total.

Read `WIT_DATA_DIR` defaulting to `/app/waltrim` and `WIT_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
"""

WAL_SOLVE_PY = Path(__file__).read_text(encoding="utf-8")
# extract solve function body - we'll inline a copy in build_task

WAL_INSTRUCTION = """
Audit write-ahead log index trimming and role quorum for a storage batch. Read `/app/waltrim/SPEC.md` and every JSON file under `/app/waltrim/`, including per-segment files in `/app/waltrim/segments/`, `policy.json`, `manifest.json`, `epochs.json`, `indexes.json`, and `links.json`. Packaging under `anchors/`, `meta/`, `grid/`, and `ancillary/` is read-only context and must not drive totals.

Produce five UTF-8 JSON artifacts under `/app/audit/` named `segment_states.json`, `trim_plan.json`, `role_votes.json`, `index_stats.json`, and `summary.json`. Each file must follow the spec canonical JSON contract: ASCII-only strings, two-space indentation, recursively sorted object keys at every depth, no trailing spaces on lines, and exactly one trailing newline after the root closing brace.

Apply snapshot-live tag halving when manifest tags disagree, warmup bypass on early indexes, sliding byte windows per segment, stale-epoch exclusion for trim rows, transitive pin protection from links, and role-ratio acceptance computed from active segment weights on each index. Process indexes in ascending index then segment id. Leave `/app/waltrim/` byte-identical.
"""

WAL_SEMANTIC = """    def test_effective_trim_threshold_halved(self, outputs: dict[str, object]) -> None:
        \"\"\"Snapshot-live tag mismatch must halve the trim threshold in summary.\"\"\"
        assert outputs["summary.json"]["effective_trim_threshold"] == 50.0

    def test_warmup_index_not_trimmed(self, outputs: dict[str, object]) -> None:
        \"\"\"Indexes inside warmup must keep trim_factor at zero.\"\"\"
        entries = outputs["trim_plan.json"]["entries"]
        warm = [e for e in entries if e["index"] <= 2]
        assert warm and all(e["trim_factor"] == 0.0 for e in warm)

    def test_stale_segment_skips_trim_row(self, outputs: dict[str, object]) -> None:
        \"\"\"Stale segments must not appear in trim_plan.\"\"\"
        states = {r["segment_id"]: r for r in outputs["segment_states.json"]["segments"]}
        trim_ids = {e["segment_id"] for e in outputs["trim_plan.json"]["entries"]}
        assert states["sg12"]["stale"] is True
        assert "sg12" not in trim_ids

    def test_transitive_pin_blocks_trim(self, outputs: dict[str, object]) -> None:
        \"\"\"Transitively pinned segments must never trim even above threshold.\"\"\"
        entries = outputs["trim_plan.json"]["entries"]
        sg07 = [e for e in entries if e["segment_id"] == "sg07"]
        assert not sg07 or all(e["trim_factor"] == 0.0 for e in sg07)

    def test_replica_role_vote_rejected_on_hot_index(self, outputs: dict[str, object]) -> None:
        \"\"\"A lone replica role on a contested index must fail role acceptance.\"\"\"
        votes = [v for v in outputs["role_votes.json"]["votes"] if v["index"] == 3 and v["role"] == "replica"]
        assert votes and not any(v["accepted"] for v in votes)
"""

WAL_RUBRICS = """
Agent reads SPEC.md and all input fixtures before writing audit JSON, +3
Agent emits all five audit files under /app/audit with canonical formatting, +5
Agent applies manifest tag halving before trim math, +3
Agent honors transitive pin and link propagation rules, +5
Agent leaves the waltrim data directory byte-identical, +2
Agent modifies files under /app/waltrim, -5
Agent omits required output files or writes outside /app/audit, -5
Agent uses wrong JSON key ordering or missing trailing newline, -3
Agent hardcodes audit digests without reading inputs, -5
Agent skips stale-segment, warmup, or pin trim rules, -3
"""

DNS_SPEC = """
Normative contract for the DNS alias chain audit. Inputs are UTF-8 JSON with ASCII-only strings. Outputs are UTF-8 JSON, ASCII-only, two-space indentation, recursively sorted object keys at every depth, no trailing spaces at line ends, and exactly one trailing newline after each root closing brace.

Read `policy.json` for integer `max_chain` (positive), integer `warmup_queries`, and float `vote_ratio` between zero and one inclusive. Read `manifest.json` for `zone_tag` and `run_tag`. When they differ, set effective max chain to `max(1, max_chain // 2)` using integer floor division; record that value as `effective_max_chain` in summary. Read `epochs.json` for integer `current_epoch`. Read `queries.json` for array `queries` with integer `step`, string `name`, and string `qtype` in `A`, `AAAA`, `CNAME`, or `MX`.

Enumerate every `*.json` under `records/`. Each record has string `name`, integer `epoch`, integer `ttl_step`, optional string `alias_target`, and boolean `deny`. A record is stale when `epoch` is strictly less than `current_epoch - 1`. Packaging under `anchors/`, `meta/`, `grid/`, and `ancillary/` is ignored.

Process queries in ascending `step`, then ascending `name`. For each query, walk alias targets starting at `name`, stopping when there is no `alias_target`, when `deny` is true on the current record, when `ttl_step` is strictly less than the query `step`, when the next target was already visited (mark `looped` true), or when chain length would exceed `effective_max_chain`.

When `step` is less than or equal to `warmup_queries`, or the name is stale, or `looped` is true, or `deny_blocked` is true during the walk, `collapsed` is false. Otherwise `collapsed` is true when resolved depth is strictly greater than one and the name is not stale and not looped.

Type vote at a step: `agree_count` counts active queries on the same `step` sharing the same `qtype`. The vote is `accepted` when the name is active and `agree_count >= vote_ratio * len(queries on that step)`.

Emit `record_states.json` with `records` sorted by `name` (deny, epoch, name, stale). Emit `chain_plan.json` with `entries` in processing order for non-stale non-looped names only (chain, collapsed, depth, name, step). Emit `type_votes.json` with `votes` in processing order. Emit `query_stats.json` with `stats` in processing order (depth, deny_blocked, looped, name, step). Emit `summary.json` with collapsed_total, current_epoch, deny_blocked_total, effective_max_chain, loop_total, query_total, stale_skipped_total, vote_accepted_total.

Read `DAC_DATA_DIR` defaulting to `/app/dnschain` and `DAC_AUDIT_DIR` defaulting to `/app/audit`. Create the audit directory when missing and never mutate inputs.
"""

DNS_INSTRUCTION = """
Audit DNS alias chain collapse and query-type quorum for a resolver telemetry batch. Read `/app/dnschain/SPEC.md` and every JSON file under `/app/dnschain/`, including per-record files in `/app/dnschain/records/`, `policy.json`, `manifest.json`, `epochs.json`, and `queries.json`. Packaging under `anchors/`, `meta/`, `grid/`, and `ancillary/` is read-only context and must not drive totals.

Produce five UTF-8 JSON artifacts under `/app/audit/` named `record_states.json`, `chain_plan.json`, `type_votes.json`, `query_stats.json`, and `summary.json`. Each file must follow the spec canonical JSON contract: ASCII-only strings, two-space indentation, recursively sorted object keys at every depth, no trailing spaces on lines, and exactly one trailing newline after the root closing brace.

Apply zone-run tag halving of max chain length when manifest tags disagree, warmup bypass on early query steps, TTL expiry during walks, CNAME loop detection, deny-label blocking of collapse, and per-step type-ratio votes among active names. Process queries in ascending step then name. Leave `/app/dnschain/` byte-identical.
"""

DNS_SEMANTIC = """    def test_effective_max_chain_halved(self, outputs: dict[str, object]) -> None:
        \"\"\"Zone-run tag mismatch must halve max chain via integer floor division.\"\"\"
        assert outputs["summary.json"]["effective_max_chain"] == 3

    def test_warmup_query_not_collapsed(self, outputs: dict[str, object]) -> None:
        \"\"\"Queries inside warmup must not collapse chains.\"\"\"
        entries = outputs["chain_plan.json"]["entries"]
        warm = [e for e in entries if e["step"] <= 2]
        assert warm and all(not e["collapsed"] for e in warm)

    def test_stale_record_skips_chain_row(self, outputs: dict[str, object]) -> None:
        \"\"\"Stale records must not appear in chain_plan.\"\"\"
        states = {r["name"]: r for r in outputs["record_states.json"]["records"]}
        chain_names = {e["name"] for e in outputs["chain_plan.json"]["entries"]}
        assert states["old.example"]["stale"] is True
        assert "old.example" not in chain_names

    def test_loop_query_not_in_chain_plan(self, outputs: dict[str, object]) -> None:
        \"\"\"Looped alias walks must omit chain_plan rows.\"\"\"
        stats = [s for s in outputs["query_stats.json"]["stats"] if s["name"] == "loop.a"]
        assert stats and stats[0]["looped"] is True
        chain_names = {e["name"] for e in outputs["chain_plan.json"]["entries"]}
        assert "loop.a" not in chain_names

    def test_deny_blocked_not_collapsed(self, outputs: dict[str, object]) -> None:
        \"\"\"Deny records must block collapse even when aliases exist.\"\"\"
        stats = [s for s in outputs["query_stats.json"]["stats"] if s["name"] == "deny.example"]
        assert stats and stats[0]["deny_blocked"] is True
"""

DNS_RUBRICS = """
Agent reads SPEC.md and all input fixtures before writing audit JSON, +3
Agent emits all five audit files under /app/audit with canonical formatting, +5
Agent applies zone-run tag halving of max chain length, +3
Agent detects alias loops and deny-blocked walks, +5
Agent leaves the dnschain data directory byte-identical, +2
Agent modifies files under /app/dnschain, -5
Agent omits required output files or writes outside /app/audit, -5
Agent uses wrong JSON key ordering or missing trailing newline, -3
Agent hardcodes audit digests without reading inputs, -5
Agent skips TTL expiry, warmup, or stale-record rules, -3
"""

_SRC = Path(__file__).read_text(encoding="utf-8")
_WAL_BODY = _SRC.split("def solve_wal_trim", 1)[1].split("def solve_dns_chain", 1)[0]
_DNS_BODY = _SRC.split("def solve_dns_chain", 1)[1].split("def write_fixtures_wal", 1)[0]

_SOLVE_HEADER = (
    "import json\n"
    "import os\n"
    "from pathlib import Path\n\n\n"
    "def dump_pretty(path, obj):\n"
    "    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + \"\\n\"\n"
    "    path.parent.mkdir(parents=True, exist_ok=True)\n"
    "    path.write_text(text, encoding=\"utf-8\")\n\n\n"
)

WAL_SOLVE_INLINE = _SOLVE_HEADER + "def solve_wal_trim" + _WAL_BODY
DNS_SOLVE_INLINE = _SOLVE_HEADER + "def solve_dns_chain" + _DNS_BODY


def main() -> None:
    build_task(
        name="wal-index-trim-audit",
        domain="waltrim",
        category="data-processing",
        languages=["go", "bash"],
        tags=["data-processing", "wal", "trim", "deterministic-json"],
        prefix="WIT",
        instruction=WAL_INSTRUCTION,
        spec=WAL_SPEC,
        solve_py=WAL_SOLVE_INLINE,
        output_files=(
            "segment_states.json",
            "trim_plan.json",
            "role_votes.json",
            "index_stats.json",
            "summary.json",
        ),
        semantic_tests=WAL_SEMANTIC,
        rubrics=WAL_RUBRICS,
        solver_fn_name="solve_wal_trim",
    )
    build_task(
        name="dns-alias-chain-audit",
        domain="dnschain",
        category="security",
        languages=["go", "bash"],
        tags=["security", "dns", "alias", "deterministic-json"],
        prefix="DAC",
        instruction=DNS_INSTRUCTION,
        spec=DNS_SPEC,
        solve_py=DNS_SOLVE_INLINE,
        output_files=(
            "record_states.json",
            "chain_plan.json",
            "type_votes.json",
            "query_stats.json",
            "summary.json",
        ),
        semantic_tests=DNS_SEMANTIC,
        rubrics=DNS_RUBRICS,
        solver_fn_name="solve_dns_chain",
    )


if __name__ == "__main__":
    main()
