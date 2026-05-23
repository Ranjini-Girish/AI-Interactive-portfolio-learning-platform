from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any



def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding="utf-8")



# Reference implementation (mirrors instruction.md and the C++ simulator).
# Used to compute expected outputs from inputs at test time.
# ---------------------------------------------------------------------------


def _severity_for_code(code: str) -> str:
    if code.startswith("E_"):
        return "error"
    if code.startswith("W_"):
        return "warning"
    if code.startswith("N_"):
        return "note"
    return "note"


def _overdraft_floor(account: dict[str, Any], policy: dict[str, Any]) -> int:
    if (
        account["account_type"] == "credit"
        and "credit" in policy["overdraft_allowed_account_types"]
    ):
        return -policy["credit_account_credit_limit_cents"]
    return 0


def _active_daily_limit(account: dict[str, Any], policy: dict[str, Any]) -> int:
    override = account.get("daily_withdraw_limit_cents")
    if override is not None:
        return override
    return policy["default_daily_withdraw_limit_cents"]


def _status_blocks_credit(status: str, action: str) -> bool:
    if status == "active":
        return False
    if action == "block_all":
        return True
    if action == "allow_credits_only":
        return False
    return True


def _status_blocks_debit(status: str, action: str) -> bool:
    if status == "active":
        return False
    return True


def _action_for(status: str, policy: dict[str, Any]) -> str:
    if status == "frozen":
        return policy["frozen_account_action"]
    if status == "closed":
        return policy["closed_account_action"]
    return ""


def _diag_code_for_status(status: str) -> str:
    if status == "frozen":
        return "E_FROZEN_ACCOUNT"
    if status == "closed":
        return "E_CLOSED_ACCOUNT"
    return ""


def _run_simulation(
    accounts_in: list[dict[str, Any]],
    events_in: list[dict[str, Any]],
    snapshots: dict[str, int],
    policy: dict[str, Any],
) -> dict[str, Any]:
    severity_ranks: dict[str, int] = dict(policy["severity_ranks"])

    accounts_by_id: dict[str, dict[str, Any]] = {a["id"]: a for a in accounts_in}
    states: dict[str, dict[str, Any]] = {}
    for a in accounts_in:
        states[a["id"]] = {
            "id": a["id"],
            "status": a["status"],
            "balance_cents": a["opening_balance_cents"],
            "total_deposits_cents": 0,
            "total_withdrawals_cents": 0,
            "n_reversed_events": 0,
            "active_holds": [],
            "daily_withdraws": {},
        }

    diagnostics: list[dict[str, Any]] = []

    def emit(code: str, account: str, seq: int, evidence: dict[str, Any]) -> None:
        severity = _severity_for_code(code)
        diagnostics.append({
            "account": account,
            "code": code,
            "evidence": dict(evidence),
            "seq": seq,
            "severity": severity,
            "severity_rank": severity_ranks.get(severity, 0),
        })

    events_sorted = sorted(events_in, key=lambda e: e["seq"])
    events_by_seq: dict[int, dict[str, Any]] = {e["seq"]: e for e in events_sorted}
    reversed_targets: set[int] = set()

    if events_sorted:
        max_event_day = max(e["day"] for e in events_sorted)
        max_event_seq = max(e["seq"] for e in events_sorted)
    else:
        max_event_day = 0
        max_event_seq = 0

    for ev in events_sorted:
        op = ev["op"]
        seq = ev["seq"]
        day = ev["day"]
        acct_id = ev["account"]
        if acct_id not in states:
            continue
        src_state = states[acct_id]
        src_acct = accounts_by_id[acct_id]
        amount = ev.get("amount_cents") or 0

        if op == "deposit":
            if src_acct["status"] != "active":
                action = _action_for(src_acct["status"], policy)
                if _status_blocks_credit(src_acct["status"], action):
                    emit(_diag_code_for_status(src_acct["status"]),
                         acct_id, seq, {})
                    continue
            src_state["balance_cents"] += amount
            src_state["total_deposits_cents"] += amount
            continue

        if op == "withdraw":
            if src_acct["status"] != "active":
                action = _action_for(src_acct["status"], policy)
                if _status_blocks_debit(src_acct["status"], action):
                    emit(_diag_code_for_status(src_acct["status"]),
                         acct_id, seq, {})
                    continue
            limit = _active_daily_limit(src_acct, policy)
            current = src_state["daily_withdraws"].get(day, 0)
            after = current + amount
            if after > limit:
                emit("E_DAILY_LIMIT_EXCEEDED", acct_id, seq, {
                    "attempted_amount_cents": amount,
                    "daily_total_after_cents": after,
                    "limit_cents": limit,
                })
                continue
            floor = _overdraft_floor(src_acct, policy)
            new_bal = src_state["balance_cents"] - amount
            held = sum(h["amount_cents"] for h in src_state["active_holds"])
            available = new_bal - held
            if available < floor:
                emit("E_INSUFFICIENT_FUNDS", acct_id, seq, {
                    "attempted_amount_cents": amount,
                    "available_cents": available,
                    "floor_cents": floor,
                })
                continue
            src_state["balance_cents"] = new_bal
            src_state["total_withdrawals_cents"] += amount
            src_state["daily_withdraws"][day] = after
            continue

        if op == "transfer":
            tgt_id = ev.get("target_account")
            if tgt_id == acct_id:
                if policy["transfer_self_action"] == "error":
                    emit("E_SELF_TRANSFER", acct_id, seq, {})
                continue
            if tgt_id not in states:
                continue
            tgt_state = states[tgt_id]
            tgt_acct = accounts_by_id[tgt_id]
            if src_acct["status"] != "active":
                action = _action_for(src_acct["status"], policy)
                if _status_blocks_debit(src_acct["status"], action):
                    emit(_diag_code_for_status(src_acct["status"]),
                         acct_id, seq, {})
                    continue
            if tgt_acct["status"] != "active":
                action = _action_for(tgt_acct["status"], policy)
                if _status_blocks_credit(tgt_acct["status"], action):
                    emit(_diag_code_for_status(tgt_acct["status"]),
                         tgt_id, seq, {})
                    continue
            limit = _active_daily_limit(src_acct, policy)
            current = src_state["daily_withdraws"].get(day, 0)
            after = current + amount
            if after > limit:
                emit("E_DAILY_LIMIT_EXCEEDED", acct_id, seq, {
                    "attempted_amount_cents": amount,
                    "daily_total_after_cents": after,
                    "limit_cents": limit,
                })
                continue
            floor = _overdraft_floor(src_acct, policy)
            new_src = src_state["balance_cents"] - amount
            held = sum(h["amount_cents"] for h in src_state["active_holds"])
            available = new_src - held
            if available < floor:
                emit("E_INSUFFICIENT_FUNDS", acct_id, seq, {
                    "attempted_amount_cents": amount,
                    "available_cents": available,
                    "floor_cents": floor,
                })
                continue
            src_state["balance_cents"] = new_src
            src_state["total_withdrawals_cents"] += amount
            src_state["daily_withdraws"][day] = after
            tgt_state["balance_cents"] += amount
            tgt_state["total_deposits_cents"] += amount
            continue

        if op == "hold":
            if src_acct["status"] != "active":
                action = _action_for(src_acct["status"], policy)
                if _status_blocks_debit(src_acct["status"], action):
                    emit(_diag_code_for_status(src_acct["status"]),
                         acct_id, seq, {})
                    continue
            floor = _overdraft_floor(src_acct, policy)
            held = sum(h["amount_cents"] for h in src_state["active_holds"])
            available = src_state["balance_cents"] - held - amount
            if available < floor:
                emit("E_INSUFFICIENT_FUNDS", acct_id, seq, {
                    "attempted_amount_cents": amount,
                    "available_cents": available,
                    "floor_cents": floor,
                })
                continue
            src_state["active_holds"].append({
                "seq": seq,
                "amount_cents": amount,
                "day": day,
            })
            continue

        if op == "release":
            target_seq = ev.get("reverses_seq")
            if target_seq is None:
                continue
            holds = src_state["active_holds"]
            for i, h in enumerate(holds):
                if h["seq"] == target_seq:
                    holds.pop(i)
                    break
            continue

        if op == "reverse":
            target_seq = ev.get("reverses_seq")
            if target_seq is None or target_seq not in events_by_seq:
                emit("E_INVALID_REVERSAL", acct_id, seq, {
                    "reason": "target_not_found",
                    "reverses_seq": target_seq if target_seq is not None else -1,
                })
                continue
            orig = events_by_seq[target_seq]
            if orig["op"] in ("hold", "release", "reverse"):
                emit("E_INVALID_REVERSAL", acct_id, seq, {
                    "reason": "target_not_reversible",
                    "reverses_seq": target_seq,
                })
                continue
            if target_seq in reversed_targets:
                emit("E_INVALID_REVERSAL", acct_id, seq, {
                    "reason": "target_already_reversed",
                    "reverses_seq": target_seq,
                })
                continue
            if day - orig["day"] > policy["reversal_window_days"]:
                emit("E_INVALID_REVERSAL", acct_id, seq, {
                    "reason": "outside_window",
                    "reverses_seq": target_seq,
                })
                continue
            orig_amount = orig.get("amount_cents") or 0
            if orig["op"] == "deposit":
                a = states[orig["account"]]
                a["balance_cents"] -= orig_amount
                a["total_withdrawals_cents"] += orig_amount
                a["n_reversed_events"] += 1
            elif orig["op"] == "withdraw":
                a = states[orig["account"]]
                a["balance_cents"] += orig_amount
                a["total_deposits_cents"] += orig_amount
                a["n_reversed_events"] += 1
            elif orig["op"] == "transfer":
                s = states[orig["account"]]
                s["balance_cents"] += orig_amount
                s["total_deposits_cents"] += orig_amount
                s["n_reversed_events"] += 1
                t_id = orig.get("target_account")
                if t_id in states:
                    t = states[t_id]
                    t["balance_cents"] -= orig_amount
                    t["total_withdrawals_cents"] += orig_amount
                    t["n_reversed_events"] += 1
            reversed_targets.add(target_seq)
            continue

    # Post-pass diagnostics
    for aid in sorted(states):
        st = states[aid]
        for h in st["active_holds"]:
            age = max_event_day - h["day"]
            if age > policy["hold_max_age_days"]:
                emit("W_HOLD_EXPIRED", aid, max_event_seq, {
                    "age_days": age,
                    "amount_cents": h["amount_cents"],
                    "hold_seq": h["seq"],
                })

    for a in accounts_in:
        aid = a["id"]
        if aid not in snapshots:
            continue
        expected = snapshots[aid]
        actual = states[aid]["balance_cents"]
        delta = actual - expected
        if delta != 0:
            emit("N_RECONCILIATION_MISMATCH", aid, max_event_seq, {
                "actual_balance_cents": actual,
                "delta_cents": delta,
                "expected_balance_cents": expected,
            })

    diagnostics.sort(key=lambda d: (
        d["severity_rank"], d["seq"], d["code"], d["account"]
    ))

    return {
        "states": states,
        "diagnostics": diagnostics,
        "max_event_seq": max_event_seq,
        "max_event_day": max_event_day,
    }


def _build_account_state_doc(
    accounts_in: list[dict[str, Any]], sim: dict[str, Any]
) -> dict[str, Any]:
    rows = []
    for a in sorted(accounts_in, key=lambda x: x["id"]):
        st = sim["states"][a["id"]]
        holds_sorted = sorted(st["active_holds"], key=lambda h: h["seq"])
        rows.append({
            "active_holds": [
                {"amount_cents": h["amount_cents"], "day": h["day"], "seq": h["seq"]}
                for h in holds_sorted
            ],
            "balance_cents": st["balance_cents"],
            "hold_amount_total_cents": sum(h["amount_cents"] for h in holds_sorted),
            "id": a["id"],
            "n_reversed_events": st["n_reversed_events"],
            "status": st["status"],
            "total_deposits_cents": st["total_deposits_cents"],
            "total_withdrawals_cents": st["total_withdrawals_cents"],
        })
    return {"accounts": rows}


def _build_diagnostics_doc(sim: dict[str, Any]) -> dict[str, Any]:
    return {"diagnostics": [
        {
            "account": d["account"],
            "code": d["code"],
            "evidence": d["evidence"],
            "seq": d["seq"],
            "severity": d["severity"],
            "severity_rank": d["severity_rank"],
        }
        for d in sim["diagnostics"]
    ]}


def _build_reconciliation_doc(
    accounts_in: list[dict[str, Any]],
    snapshots: dict[str, int],
    sim: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for a in sorted(accounts_in, key=lambda x: x["id"]):
        st = sim["states"][a["id"]]
        actual = st["balance_cents"]
        if a["id"] not in snapshots:
            rows.append({
                "account": a["id"],
                "actual_balance_cents": actual,
                "delta_cents": None,
                "expected_balance_cents": None,
                "status": "unsnapshotted",
            })
        else:
            expected = snapshots[a["id"]]
            delta = actual - expected
            rows.append({
                "account": a["id"],
                "actual_balance_cents": actual,
                "delta_cents": delta,
                "expected_balance_cents": expected,
                "status": "matched" if delta == 0 else "mismatched",
            })
    return {"accounts": rows}


def _build_summary_doc(
    accounts_in: list[dict[str, Any]],
    events_in: list[dict[str, Any]],
    snapshots: dict[str, int],
    policy: dict[str, Any],
    sim: dict[str, Any],
) -> dict[str, Any]:
    by_severity = {name: 0 for name in policy["severity_ranks"]}
    for d in sim["diagnostics"]:
        if d["severity"] in by_severity:
            by_severity[d["severity"]] += 1
    n_active_holds_total = sum(
        len(sim["states"][a["id"]]["active_holds"]) for a in accounts_in
    )
    total_reversed_events = sum(
        sim["states"][a["id"]]["n_reversed_events"] for a in accounts_in
    )
    mismatched = 0
    for a in accounts_in:
        if a["id"] in snapshots:
            actual = sim["states"][a["id"]]["balance_cents"]
            if actual - snapshots[a["id"]] != 0:
                mismatched += 1
    return {
        "by_severity": by_severity,
        "totals": {
            "accounts_total": len(accounts_in),
            "events_total": len(events_in),
            "mismatched_accounts": mismatched,
            "n_active_holds_total": n_active_holds_total,
            "total_diagnostics": len(sim["diagnostics"]),
            "total_reversed_events": total_reversed_events,
        },
    }

def _build_account_state_doc(
    accounts_in: list[dict[str, Any]], sim: dict[str, Any]
) -> dict[str, Any]:
    rows = []
    for a in sorted(accounts_in, key=lambda x: x["id"]):
        st = sim["states"][a["id"]]
        holds_sorted = sorted(st["active_holds"], key=lambda h: h["seq"])
        rows.append({
            "active_holds": [
                {"amount_cents": h["amount_cents"], "day": h["day"], "seq": h["seq"]}
                for h in holds_sorted
            ],
            "balance_cents": st["balance_cents"],
            "hold_amount_total_cents": sum(h["amount_cents"] for h in holds_sorted),
            "id": a["id"],
            "n_reversed_events": st["n_reversed_events"],
            "status": st["status"],
            "total_deposits_cents": st["total_deposits_cents"],
            "total_withdrawals_cents": st["total_withdrawals_cents"],
        })
    return {"accounts": rows}

def _build_diagnostics_doc(sim: dict[str, Any]) -> dict[str, Any]:
    return {"diagnostics": [
        {
            "account": d["account"],
            "code": d["code"],
            "evidence": d["evidence"],
            "seq": d["seq"],
            "severity": d["severity"],
            "severity_rank": d["severity_rank"],
        }
        for d in sim["diagnostics"]
    ]}

def _build_reconciliation_doc(
    accounts_in: list[dict[str, Any]],
    snapshots: dict[str, int],
    sim: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for a in sorted(accounts_in, key=lambda x: x["id"]):
        st = sim["states"][a["id"]]
        actual = st["balance_cents"]
        if a["id"] not in snapshots:
            rows.append({
                "account": a["id"],
                "actual_balance_cents": actual,
                "delta_cents": None,
                "expected_balance_cents": None,
                "status": "unsnapshotted",
            })
        else:
            expected = snapshots[a["id"]]
            delta = actual - expected
            rows.append({
                "account": a["id"],
                "actual_balance_cents": actual,
                "delta_cents": delta,
                "expected_balance_cents": expected,
                "status": "matched" if delta == 0 else "mismatched",
            })
    return {"accounts": rows}

def _build_summary_doc(
    accounts_in: list[dict[str, Any]],
    events_in: list[dict[str, Any]],
    snapshots: dict[str, int],
    policy: dict[str, Any],
    sim: dict[str, Any],
) -> dict[str, Any]:
    by_severity = {name: 0 for name in policy["severity_ranks"]}
    for d in sim["diagnostics"]:
        if d["severity"] in by_severity:
            by_severity[d["severity"]] += 1
    n_active_holds_total = sum(
        len(sim["states"][a["id"]]["active_holds"]) for a in accounts_in
    )
    total_reversed_events = sum(
        sim["states"][a["id"]]["n_reversed_events"] for a in accounts_in
    )
    mismatched = 0
    for a in accounts_in:
        if a["id"] in snapshots:
            actual = sim["states"][a["id"]]["balance_cents"]
            if actual - snapshots[a["id"]] != 0:
                mismatched += 1
    return {
        "by_severity": by_severity,
        "totals": {
            "accounts_total": len(accounts_in),
            "events_total": len(events_in),
            "mismatched_accounts": mismatched,
            "n_active_holds_total": n_active_holds_total,
            "total_diagnostics": len(sim["diagnostics"]),
            "total_reversed_events": total_reversed_events,
        },
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    accounts_doc = load_json(in_dir / "accounts.json")
    events_doc = load_json(in_dir / "events.json")
    snapshots_doc = load_json(in_dir / "snapshots.json")
    policy = load_json(in_dir / "policy.json")
    accounts_in = accounts_doc["accounts"]
    events_in = events_doc["events"]
    snapshots = snapshots_doc.get("expected_balances", {})
    sim = _run_simulation(accounts_in, events_in, snapshots, policy)
    outputs = {
        "account_state": _build_account_state_doc(accounts_in, sim),
        "event_diagnostics": _build_diagnostics_doc(sim),
        "reconciliation_report": _build_reconciliation_doc(accounts_in, snapshots, sim),
        "compliance_summary": _build_summary_doc(
            accounts_in, events_in, snapshots, policy, sim
        ),
    }
    write_canonical(out_dir / "account_state.json", outputs["account_state"])
    write_canonical(out_dir / "event_diagnostics.json", outputs["event_diagnostics"])
    write_canonical(out_dir / "reconciliation_report.json", outputs["reconciliation_report"])
    write_canonical(out_dir / "compliance_summary.json", outputs["compliance_summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
