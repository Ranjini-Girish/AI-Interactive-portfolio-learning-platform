#!/bin/bash
set -euo pipefail

export DAC_DATA_DIR="${DAC_DATA_DIR:-/app/dnschain}"
export DAC_AUDIT_DIR="${DAC_AUDIT_DIR:-/app/audit}"
mkdir -p "${DAC_AUDIT_DIR}"

python3 - <<'PY'
import json
import os
from pathlib import Path


def dump_pretty(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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



data_dir = Path(os.environ.get("DAC_DATA_DIR", "/app/dnschain"))
audit_dir = Path(os.environ.get("DAC_AUDIT_DIR", "/app/audit"))
solve_dns_chain(data_dir, audit_dir)
PY
