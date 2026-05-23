#!/bin/bash
set -euo pipefail

export NGM_DATA_DIR="${NGM_DATA_DIR:-/app/mempoolgap}"
export NGM_AUDIT_DIR="${NGM_AUDIT_DIR:-/app/audit}"
mkdir -p "${NGM_AUDIT_DIR}"

python3 - <<'PYEOF'
import json
import os
from pathlib import Path

def dump_pretty(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def solve_mempool(data_dir: Path) -> dict[str, object]:
    policy = json.loads((data_dir / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    epochs = json.loads((data_dir / "epochs.json").read_text(encoding="utf-8"))
    txs_doc = json.loads((data_dir / "txs.json").read_text(encoding="utf-8"))

    gap_limit = int(policy["gap_limit"])
    warmup = int(policy["warmup_steps"])
    replace_boost = float(policy["replace_boost"])

    if manifest["channel_tag"] != manifest["active_channel"]:
        gap_limit = max(1, round(gap_limit * 0.5))

    current_epoch = int(epochs["current_epoch"])

    accounts: dict[str, dict] = {}
    for path in sorted((data_dir / "accounts").glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        accounts[row["account_id"]] = row

    active = {
        aid
        for aid, row in accounts.items()
        if int(row["epoch"]) >= current_epoch - 1
    }

    expected_nonce: dict[str, int] = {
        aid: int(row["base_nonce"]) for aid, row in accounts.items()
    }
    pending_fee: dict[str, float] = {}

    tx_rows = []
    violation_rows = []

    gap_total = 0
    replace_accept_total = 0
    replace_reject_total = 0
    stale_skipped_total = 0
    warmup_skipped_total = 0
    unknown_total = 0

    events = sorted(
        txs_doc["txs"],
        key=lambda e: (int(e["step"]), e["account_id"]),
    )

    for ev in events:
        step = int(ev["step"])
        aid = ev["account_id"]
        nonce = int(ev["nonce"])
        fee = float(ev["fee"])
        kind = ev["kind"]

        stale = aid not in active
        outcome = "ok"

        if aid not in accounts:
            unknown_total += 1
            outcome = "unknown_account"
            violation_rows.append(
                {
                    "account_id": aid,
                    "kind": kind,
                    "nonce": nonce,
                    "outcome": outcome,
                    "step": step,
                    "violation": "unknown_account",
                }
            )
        elif step <= warmup:
            warmup_skipped_total += 1
            outcome = "warmup_skipped"
        elif stale:
            stale_skipped_total += 1
            outcome = "stale_skipped"
        elif kind == "submit":
            exp = expected_nonce[aid]
            if nonce > exp + gap_limit:
                gap_total += 1
                outcome = "gap_violation"
                violation_rows.append(
                    {
                        "account_id": aid,
                        "expected_nonce": exp,
                        "gap_limit": gap_limit,
                        "kind": kind,
                        "nonce": nonce,
                        "outcome": outcome,
                        "step": step,
                        "violation": "gap_violation",
                    }
                )
            elif nonce == exp:
                expected_nonce[aid] = exp + 1
                pending_fee.pop(aid, None)
            elif nonce < exp:
                outcome = "nonce_replay"
                violation_rows.append(
                    {
                        "account_id": aid,
                        "expected_nonce": exp,
                        "kind": kind,
                        "nonce": nonce,
                        "outcome": outcome,
                        "step": step,
                        "violation": "nonce_replay",
                    }
                )
            else:
                pending_fee[aid] = fee
                expected_nonce[aid] = nonce + 1
        elif kind == "replace":
            prev = pending_fee.get(aid)
            if prev is None:
                replace_reject_total += 1
                outcome = "replace_rejected"
            elif fee >= prev * replace_boost:
                replace_accept_total += 1
                pending_fee[aid] = fee
                outcome = "replace_accepted"
            else:
                replace_reject_total += 1
                outcome = "replace_rejected"
        elif kind == "cancel":
            pending_fee.pop(aid, None)
            outcome = "cancel_ok"

        tx_rows.append(
            {
                "account_id": aid,
                "fee": round(fee, 6),
                "kind": kind,
                "nonce": nonce,
                "outcome": outcome,
                "stale": stale,
                "step": step,
            }
        )

    account_states = []
    for aid in sorted(accounts):
        row = accounts[aid]
        account_states.append(
            {
                "account_id": aid,
                "base_nonce": int(row["base_nonce"]),
                "epoch": int(row["epoch"]),
                "final_nonce": expected_nonce[aid],
                "stale": aid not in active,
            }
        )

    violations_sorted = sorted(
        violation_rows,
        key=lambda r: (int(r["step"]), r["account_id"]),
    )

    summary = {
        "current_epoch": current_epoch,
        "effective_gap_limit": gap_limit,
        "gap_violation_total": gap_total,
        "replace_accepted_total": replace_accept_total,
        "replace_rejected_total": replace_reject_total,
        "stale_skipped_total": stale_skipped_total,
        "tx_total": len(events),
        "unknown_account_total": unknown_total,
        "warmup_skipped_total": warmup_skipped_total,
    }

    return {
        "account_states.json": {"accounts": account_states},
        "mempool_violations.json": {"violations": violations_sorted},
        "summary.json": summary,
        "tx_outcomes.json": {"txs": tx_rows},
    }


data_dir = Path(os.environ["NGM_DATA_DIR"])
audit_dir = Path(os.environ["NGM_AUDIT_DIR"])
audit_dir.mkdir(parents=True, exist_ok=True)
for fname, obj in solve_mempool(data_dir).items():
    dump_pretty(audit_dir / fname, obj)
PYEOF
