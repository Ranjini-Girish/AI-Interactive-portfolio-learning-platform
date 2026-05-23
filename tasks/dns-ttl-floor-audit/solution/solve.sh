#!/bin/bash
set -euo pipefail

export DTF_DATA_DIR="${DTF_DATA_DIR:-/app/dnsfloor}"
export DTF_AUDIT_DIR="${DTF_AUDIT_DIR:-/app/audit}"
mkdir -p "${DTF_AUDIT_DIR}"

python3 - <<'PYEOF'
import json
import os
from pathlib import Path

def dump_pretty(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def solve_dns(data_dir: Path) -> dict[str, object]:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    queries_doc = json.loads((data_dir / "queries.json").read_text(encoding="utf-8"))

    ttl_floor = int(policy["ttl_floor"])
    warmup = int(policy["warmup_queries"])
    depth_max = int(policy["cname_depth_max"])
    spill_ratio = float(policy["spill_ratio"])

    if manifest["zone_tag"] != manifest["active_zone"]:
        ttl_floor = max(1, round(ttl_floor * spill_ratio))

    current_epoch = int(epochs["current_epoch"])

    records: dict[str, dict] = {}
    for path in sorted((data_dir / "records").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        records[row["record_id"]] = row

    active = {
        rid
        for rid, row in records.items()
        if int(row["epoch"]) >= current_epoch - 1
    }

    queries = sorted(
        queries_doc["queries"],
        key=lambda q: (int(q["step"]), q["record_id"]),
    )

    query_rows = []
    hop_rows = []
    violation_rows = []
    floor_breach_total = 0
    depth_exceeded_total = 0
    stale_skipped_total = 0
    warmup_skipped_total = 0

    for q in queries:
        step = int(q["step"])
        rid = q["record_id"]
        row = records.get(rid)
        stale = rid not in active if row else True

        outcome = "ok"
        effective_ttl = 0
        chain: list[str] = []

        if row is None:
            outcome = "missing_record"
            violation_rows.append(
                {
                    "outcome": outcome,
                    "record_id": rid,
                    "step": step,
                    "violation": "missing_record",
                }
            )
        elif step <= warmup:
            warmup_skipped_total += 1
            outcome = "warmup_skipped"
        elif stale:
            stale_skipped_total += 1
            outcome = "stale_skipped"
        else:
            cur = rid
            depth = 0
            ttls: list[int] = []
            while True:
                chain.append(cur)
                r = records[cur]
                hop_ttl = max(ttl_floor, int(r["ttl"]))
                ttls.append(hop_ttl)
                if r["rtype"] == "CNAME":
                    depth += 1
                    if depth > depth_max:
                        depth_exceeded_total += 1
                        outcome = "cname_depth_exceeded"
                        violation_rows.append(
                            {
                                "depth": depth,
                                "outcome": outcome,
                                "record_id": rid,
                                "step": step,
                                "violation": "cname_depth_exceeded",
                            }
                        )
                        break
                    nxt = r["target"]
                    if nxt not in records:
                        outcome = "broken_chain"
                        violation_rows.append(
                            {
                                "outcome": outcome,
                                "record_id": rid,
                                "step": step,
                                "target": nxt,
                                "violation": "broken_chain",
                            }
                        )
                        break
                    cur = nxt
                    continue
                effective_ttl = min(ttls)
                break

            if outcome == "ok":
                raw_ttl = int(records[rid]["ttl"])
                if raw_ttl < ttl_floor:
                    floor_breach_total += 1
                    outcome = "floor_breach"
                    violation_rows.append(
                        {
                            "effective_ttl": effective_ttl,
                            "outcome": outcome,
                            "raw_ttl": raw_ttl,
                            "record_id": rid,
                            "step": step,
                            "ttl_floor": ttl_floor,
                            "violation": "floor_breach",
                        }
                    )
                else:
                    hop_rows.append(
                        {
                            "chain": chain,
                            "effective_ttl": effective_ttl,
                            "record_id": rid,
                            "step": step,
                        }
                    )

        query_rows.append(
            {
                "effective_ttl": effective_ttl,
                "outcome": outcome,
                "record_id": rid,
                "stale": stale,
                "step": step,
            }
        )

    record_states = []
    for rid in sorted(records):
        row = records[rid]
        record_states.append(
            {
                "epoch": int(row["epoch"]),
                "record_id": rid,
                "rtype": row["rtype"],
                "stale": rid not in active,
                "ttl": int(row["ttl"]),
            }
        )

    violations_sorted = sorted(
        violation_rows,
        key=lambda r: (int(r["step"]), r["record_id"]),
    )

    summary = {
        "cname_depth_exceeded_total": depth_exceeded_total,
        "current_epoch": current_epoch,
        "effective_ttl_floor": ttl_floor,
        "floor_breach_total": floor_breach_total,
        "query_total": len(queries),
        "stale_skipped_total": stale_skipped_total,
        "warmup_skipped_total": warmup_skipped_total,
    }

    return {
        "cname_hops.json": {"hops": hop_rows},
        "floor_violations.json": {"violations": violations_sorted},
        "query_outcomes.json": {"queries": query_rows},
        "record_states.json": {"records": record_states},
        "summary.json": summary,
    }




data_dir = Path(os.environ["DTF_DATA_DIR"])
audit_dir = Path(os.environ["DTF_AUDIT_DIR"])
audit_dir.mkdir(parents=True, exist_ok=True)
for fname, obj in solve_dns(data_dir).items():
    dump_pretty(audit_dir / fname, obj)
PYEOF
