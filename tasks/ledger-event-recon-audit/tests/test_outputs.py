"""Verifier suite for LedgerEventReconAudit (java).

Anti-cheating notes
-------------------
1. Expected outputs are NOT embedded as static literals. A reference
   implementation in this module recomputes the four expected output
   documents from /app/data/{accounts,events,snapshots,policy}.json at test
   time, and the agent-produced files under /app/output/ are compared
   against that live reference.
2. The verifier itself wipes /app/output and re-runs the Java entry class on
   /app/data /app/output before checking outputs (see ``binary_run_outputs``
   fixture). Pre-seeding correct outputs into the image is therefore not a
   bypass: the agent's binary must actually re-produce them at test time.
3. The CLI contract (exactly two positional args, non-zero exit on wrong arg
   count, paths come from argv not hardcoded) is checked end-to-end.
4. The binary's mtime must be newer than the source mtimes, ruling out a
   submission that ships a prebuilt binary while shipping unrelated dummy
   sources.
5. Hidden datasets exercise branches the pinned dataset does not (transfer
   reversal credit-back, all four E_INVALID_REVERSAL reasons, frozen vs
   closed credit-leg semantics, custom severity_ranks, premium daily
   override, etc.).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
import os
from pathlib import Path
from typing import Any

import pytest


def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for the Java entry class."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        JAVA_CLASS,
        str(data_dir),
        str(out_dir),
    ]


SOURCE_SUFFIXES = (".java",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {
    "Makefile",
    "GNUmakefile",
    "makefile",
    "CMakeLists.txt",
    "build.ninja",
}


def _src_files() -> list[Path]:
    """Collect agent-authored Java sources under /app/src."""
    out: list[Path] = []
    src_root = Path(os.environ.get("LER_APP_SRC", "/app/src"))
    if src_root.exists():
        for p in src_root.rglob("*"):
            if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                out.append(p)
    return out


def _all_app_build_inputs() -> list[Path]:
    """All non-output source and build-script inputs under /app."""
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file():
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        if p.suffix in SOURCE_SUFFIXES + BUILD_SCRIPT_SUFFIXES:
            out.append(p)
        elif p.name in BUILD_SCRIPT_NAMES:
            out.append(p)
    return out


def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path(os.environ.get("LER_APP_DATA", "/app/data"))
OUT_DIR = Path(os.environ.get("LER_APP_OUTPUT", "/app/output"))
BUILD_DIR = Path(os.environ.get("LER_APP_BUILD", "/app/build"))
JAVA_CLASS = "LedgerEventReconAudit"
GSON_CP = "/opt/gson.jar"

ACCOUNTS_PATH = DATA_DIR / "accounts.json"
EVENTS_PATH = DATA_DIR / "events.json"
SNAPSHOTS_PATH = DATA_DIR / "snapshots.json"
POLICY_PATH = DATA_DIR / "policy.json"

ACCOUNT_STATE_PATH = OUT_DIR / "account_state.json"
DIAG_PATH = OUT_DIR / "event_diagnostics.json"
RECON_PATH = OUT_DIR / "reconciliation_report.json"
SUMMARY_PATH = OUT_DIR / "compliance_summary.json"

ALL_OUT_PATHS = (
    ACCOUNT_STATE_PATH,
    DIAG_PATH,
    RECON_PATH,
    SUMMARY_PATH,
)

VALID_DIAG_CODES = frozenset({
    "E_DAILY_LIMIT_EXCEEDED",
    "E_INSUFFICIENT_FUNDS",
    "E_SELF_TRANSFER",
    "E_FROZEN_ACCOUNT",
    "E_CLOSED_ACCOUNT",
    "E_INVALID_REVERSAL",
    "W_HOLD_EXPIRED",
    "N_RECONCILIATION_MISMATCH",
})

VALID_REVERSAL_REASONS = frozenset({
    "target_not_found",
    "target_already_reversed",
    "target_not_reversible",
    "outside_window",
})


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference implementation (mirrors instruction.md and the ledger simulator).
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


def reference_outputs() -> dict[str, Any]:
    accounts_doc = load_json(ACCOUNTS_PATH)
    events_doc = load_json(EVENTS_PATH)
    snapshots_doc = load_json(SNAPSHOTS_PATH)
    policy = load_json(POLICY_PATH)
    accounts_in = accounts_doc["accounts"]
    events_in = events_doc["events"]
    snapshots = snapshots_doc.get("expected_balances", {})
    sim = _run_simulation(accounts_in, events_in, snapshots, policy)
    return {
        "account_state": _build_account_state_doc(accounts_in, sim),
        "event_diagnostics": _build_diagnostics_doc(sim),
        "reconciliation_report": _build_reconciliation_doc(
            accounts_in, snapshots, sim
        ),
        "compliance_summary": _build_summary_doc(
            accounts_in, events_in, snapshots, policy, sim
        ),
        "_accounts": accounts_in,
        "_events": events_in,
        "_snapshots": snapshots,
        "_policy": policy,
    }


# ---------------------------------------------------------------------------
# Pinned canonical input data (defends against an agent that mutates
# /app/data/* before the binary runs the first time)
# ---------------------------------------------------------------------------

EXPECTED_ACCOUNTS_DOC: dict[str, Any] = {
    "accounts": [
        {"id": "A1", "currency": "USD", "opening_balance_cents": 50000,
         "tier": "basic", "account_type": "checking", "status": "active",
         "daily_withdraw_limit_cents": None},
        {"id": "A2", "currency": "USD", "opening_balance_cents": 100000,
         "tier": "premium", "account_type": "savings", "status": "active",
         "daily_withdraw_limit_cents": 200000},
        {"id": "A3", "currency": "USD", "opening_balance_cents": 0,
         "tier": "basic", "account_type": "credit", "status": "active",
         "daily_withdraw_limit_cents": None},
        {"id": "A4", "currency": "USD", "opening_balance_cents": 30000,
         "tier": "basic", "account_type": "checking", "status": "frozen",
         "daily_withdraw_limit_cents": None},
        {"id": "A5", "currency": "USD", "opening_balance_cents": 25000,
         "tier": "basic", "account_type": "checking", "status": "closed",
         "daily_withdraw_limit_cents": None},
    ]
}

EXPECTED_POLICY_DOC: dict[str, Any] = {
    "severity_ranks": {"error": 0, "warning": 1, "note": 2},
    "default_daily_withdraw_limit_cents": 100000,
    "overdraft_allowed_account_types": ["credit"],
    "credit_account_credit_limit_cents": 200000,
    "reversal_window_days": 5,
    "hold_max_age_days": 7,
    "transfer_self_action": "error",
    "frozen_account_action": "allow_credits_only",
    "closed_account_action": "block_all",
}

EXPECTED_SNAPSHOTS_DOC: dict[str, Any] = {
    "expected_balances": {
        "A1": -3000,
        "A2": 80000,
        "A3": -100000,
        "A4": 30000,
    }
}


def _ref_for(
    accounts: dict[str, Any],
    events: dict[str, Any],
    snapshots: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    sim = _run_simulation(
        accounts["accounts"],
        events["events"],
        snapshots.get("expected_balances", {}),
        policy,
    )
    return {
        "account_state": _build_account_state_doc(accounts["accounts"], sim),
        "event_diagnostics": _build_diagnostics_doc(sim),
        "reconciliation_report": _build_reconciliation_doc(
            accounts["accounts"], snapshots.get("expected_balances", {}), sim
        ),
        "compliance_summary": _build_summary_doc(
            accounts["accounts"],
            events["events"],
            snapshots.get("expected_balances", {}),
            policy,
            sim,
        ),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output, then run the agent's binary with the canonical CLI
    contract and capture exit code, stdout, stderr, and start time.

    All ``test_*_match_reference`` tests depend on this fixture, ensuring the
    binary is the *only* thing that produces the canonical-input outputs the
    tests then assert against. This neutralises the
    "ship precomputed /app/output JSON" bypass.
    """
    class_path = BUILD_DIR / f"{JAVA_CLASS}.class"
    assert _java_class_ready(), (
        f"compiled entry class not found at {class_path}; agent must build "
        "Java sources before tests run"
    )
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        _java_cmd(DATA_DIR, OUT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return {
        "start": start,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _run_binary_on(
    tmp_path: Path,
    accounts: dict,
    events: dict,
    snapshots: dict,
    policy: dict,
) -> dict[str, Any]:
    """Materialise a tmp dataset, run the agent's binary, return parsed outputs."""
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "accounts.json").write_text(json.dumps(accounts), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (in_dir / "snapshots.json").write_text(json.dumps(snapshots), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")
    proc = subprocess.run(
        _java_cmd(in_dir, out_dir),
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("account_state.json", "event_diagnostics.json",
                  "reconciliation_report.json", "compliance_summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """The pinned input data files at /app/data/* must parse to the snapshot
    captured in this test module. This both prevents the agent from rewriting
    inputs to ease its task AND is what makes our live-recomputed reference
    deterministic. We compare parsed JSON rather than bytes so trivial
    re-formatting (added/removed whitespace) does not falsely fail.
    """
    actual_accounts = load_json(ACCOUNTS_PATH)
    assert actual_accounts == EXPECTED_ACCOUNTS_DOC, (
        "accounts.json content has been mutated from its as-shipped state"
    )
    actual_policy = load_json(POLICY_PATH)
    assert actual_policy == EXPECTED_POLICY_DOC, (
        "policy.json content has been mutated from its as-shipped state"
    )
    actual_snapshots = load_json(SNAPSHOTS_PATH)
    assert actual_snapshots == EXPECTED_SNAPSHOTS_DOC, (
        "snapshots.json content has been mutated from its as-shipped state"
    )
    events_doc = load_json(EVENTS_PATH)
    assert "events" in events_doc, "events.json missing top-level 'events' array"
    seqs = [e["seq"] for e in events_doc["events"]]
    assert seqs == sorted(seqs), "events not sorted by seq ascending"
    assert seqs == list(range(len(seqs))), (
        "events seqs are not dense from 0; this is a dataset invariant"
    )
    assert len(events_doc["events"]) == 28, (
        f"events.json: expected exactly 28 events as shipped, "
        f"found {len(events_doc['events'])}"
    )
    # Pin events.json content via a sha256 of its canonicalised form so
    # an agent cannot mutate event payloads (amounts, op kinds, days, etc.)
    # while preserving the seq/length invariants above. The verifier
    # recomputes the reference from /app/data, so any allowed mutation
    # would also slide the reference; pinning the hash forces /app/data
    # to remain exactly as shipped.
    canonical = json.dumps(
        events_doc, indent=2, sort_keys=True, ensure_ascii=True
    )
    actual_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    expected_hash = (
        "bbadef3890eb48a65a788c87455f4e14c95bb85dba1dfcd28fda559a17e60964"
    )
    assert actual_hash == expected_hash, (
        f"events.json canonical sha256 mismatch (expected {expected_hash}, "
        f"got {actual_hash}); events.json has been mutated from its "
        "as-shipped state"
    )


def test_java_entry_class_exists() -> None:
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()


def test_sources_present_and_class_newer() -> None:
    """Java sources under /app/src are no older than the compiled entry class."""
    required_sources = _src_files()
    assert required_sources, "no .java under /app/src"
    inputs = _all_app_build_inputs()
    class_path = BUILD_DIR / f"{JAVA_CLASS}.class"
    bin_mtime = int(class_path.stat().st_mtime)
    for s in inputs:
        src_mtime = int(s.stat().st_mtime)
        assert bin_mtime >= src_mtime, (
            f"class mtime {bin_mtime} older than build input {s} mtime {src_mtime}"
        )


def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on the pinned
    /app/data, exit 0, and produce all four outputs that are mtime-newer than
    the moment the verifier started the run.
    """
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"{JAVA_CLASS} exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}; this "
            "looks like a stale/precomputed file rather than fresh binary output"
        )
        load_json(path)


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args.

    Calls with 0/1/3 args must exit non-zero. With the correct two args
    pointing at fresh empty dirs, the binary must accept argv. This locks in
    the CLI contract from the spec.
    """
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = ["java", "-cp", f"{BUILD_DIR}:{GSON_CP}", JAVA_CLASS]
        if n_args >= 1:
            argv.append(str(fake_data))
        if n_args >= 2:
            argv.append(str(fake_out))
        if n_args >= 3:
            argv.append("extra")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode != 0, (
            f"binary should exit non-zero on {n_args} arg(s); got rc=0 "
            f"with stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def test_outputs_strict_json_formatting(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every output is 2-space, sort-keys, ASCII-only, trailing-newline JSON."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def _walk_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def test_outputs_are_ascii_at_every_depth(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every byte in every output JSON must be pure ASCII; every string at
    every depth must have only ASCII codepoints. The spec mandates ASCII-only
    output.
    """
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        for i, b in enumerate(raw):
            assert b < 0x80, (
                f"{path} byte {i} = 0x{b:02x} is non-ASCII; outputs must be "
                "pure ASCII at the byte level"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )


def test_account_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """account_state.json must equal the live-computed reference exactly.

    Stresses:
      - per-account balance after every monetary leg (including transfer
        legs and reversal inverse legs)
      - active_holds list shape and arrival-order persistence
      - hold_amount_total_cents = sum over active_holds[*].amount_cents
      - n_reversed_events counts events that were the *target* of a
        successful reverse (both legs of a reversed transfer count)
      - total_deposits_cents / total_withdrawals_cents accumulate the legs
        that actually moved money (so a reverse of a deposit increments the
        original account's withdrawals, etc.)
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(ACCOUNT_STATE_PATH)
    assert actual == expected_outputs["account_state"]

def test_reconciliation_report_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """reconciliation_report.json must equal the live-computed reference exactly.

    Stresses:
      - every account in accounts.json appears (sorted by id ASCII)
      - 'matched' iff delta_cents == 0
      - 'unsnapshotted' iff snapshot map is missing the account, with
        delta_cents and expected_balance_cents both null in that case
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(RECON_PATH)
    assert actual == expected_outputs["reconciliation_report"]


def test_compliance_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """compliance_summary.json must equal the live-computed reference exactly.

    Stresses:
      - by_severity carries every severity name in policy.severity_ranks
        (zeros for absent ones), nothing else
      - totals.events_total counts EVERY event regardless of acceptance
      - totals.mismatched_accounts only counts snapshotted, mismatched ones
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["compliance_summary"]


def test_event_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """event_diagnostics.json must equal the live-computed reference exactly.

    Mirrors the structural-equality contract enforced on the other three
    output documents. Without this check, the per-diagnostic ``evidence``
    payloads (e.g. limit_used_cents, target_seq, expected_balance_cents,
    daily_window, reason) are only spot-checked by the legality and
    invariant tests, which leaves room for divergence on dataset-specific
    fields. This assertion locks the full document — codes, severities,
    severity_ranks, accounts, seq ordering, and every evidence key/value —
    to the reference computed from /app/data on this run.
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["event_diagnostics"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """All diagnostic codes are drawn from the fixed set, with correct
    severity for each, and the diagnostics list is sorted by
    (severity_rank, seq, code, account).
    """
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    severity_ranks = load_json(POLICY_PATH)["severity_ranks"]
    prev_key = (-1, -1, "", "")
    for d in diag["diagnostics"]:
        assert d["code"] in VALID_DIAG_CODES, (
            f"unknown diag code {d['code']!r}"
        )
        expected_severity = _severity_for_code(d["code"])
        assert d["severity"] == expected_severity, (
            f"code {d['code']!r} has severity {d['severity']!r}, expected "
            f"{expected_severity!r}"
        )
        assert d["severity_rank"] == severity_ranks[expected_severity], (
            f"code {d['code']!r} has severity_rank {d['severity_rank']} but "
            f"policy says {severity_ranks[expected_severity]}"
        )
        if d["code"] == "E_INVALID_REVERSAL":
            assert d["evidence"]["reason"] in VALID_REVERSAL_REASONS, (
                f"E_INVALID_REVERSAL has illegal reason "
                f"{d['evidence']['reason']!r}; valid: {sorted(VALID_REVERSAL_REASONS)}"
            )
        key = (d["severity_rank"], d["seq"], d["code"], d["account"])
        assert key >= prev_key, (
            f"diagnostics not sorted by (severity_rank, seq, code, account); "
            f"got {key} after {prev_key}"
        )
        prev_key = key


def test_account_state_invariants(
    binary_run_outputs: dict[str, Any],
) -> None:
    """For every account row:
      - active_holds is sorted by seq ascending
      - hold_amount_total_cents == sum of active_holds[*].amount_cents
      - balance_cents is a Python int (no floats)
    """
    assert binary_run_outputs["returncode"] == 0
    state = load_json(ACCOUNT_STATE_PATH)
    ids = [r["id"] for r in state["accounts"]]
    assert ids == sorted(ids), f"account_state.accounts not sorted by id: {ids}"
    for row in state["accounts"]:
        seqs = [h["seq"] for h in row["active_holds"]]
        assert seqs == sorted(seqs), (
            f"account {row['id']!r} active_holds not sorted by seq: {seqs}"
        )
        total = sum(h["amount_cents"] for h in row["active_holds"])
        assert total == row["hold_amount_total_cents"], (
            f"account {row['id']!r}: hold_amount_total_cents={row['hold_amount_total_cents']} "
            f"but sum(active_holds)={total}"
        )
        assert isinstance(row["balance_cents"], int) and not isinstance(
            row["balance_cents"], bool
        ), (
            f"account {row['id']!r}: balance_cents must be int, got "
            f"{type(row['balance_cents']).__name__}"
        )
        assert row["total_deposits_cents"] >= 0, (
            f"account {row['id']!r}: total_deposits_cents must be non-negative"
        )
        assert row["total_withdrawals_cents"] >= 0, (
            f"account {row['id']!r}: total_withdrawals_cents must be non-negative"
        )


def test_reconciliation_consistent_with_account_state(
    binary_run_outputs: dict[str, Any],
) -> None:
    """reconciliation_report.actual_balance_cents must equal
    account_state.balance_cents for every account, and the 'matched' /
    'mismatched' / 'unsnapshotted' status must agree with the snapshot map.
    """
    assert binary_run_outputs["returncode"] == 0
    state = load_json(ACCOUNT_STATE_PATH)
    recon = load_json(RECON_PATH)
    snap = load_json(SNAPSHOTS_PATH).get("expected_balances", {})
    state_by_id = {r["id"]: r for r in state["accounts"]}
    recon_by_id = {r["account"]: r for r in recon["accounts"]}
    assert sorted(state_by_id) == sorted(recon_by_id), (
        f"reconciliation accounts {sorted(recon_by_id)} differ from "
        f"account_state ids {sorted(state_by_id)}"
    )
    for aid, srow in state_by_id.items():
        rrow = recon_by_id[aid]
        assert rrow["actual_balance_cents"] == srow["balance_cents"], (
            f"recon.actual_balance_cents for {aid!r} differs from "
            f"account_state.balance_cents: {rrow['actual_balance_cents']} vs "
            f"{srow['balance_cents']}"
        )
        if aid not in snap:
            assert rrow["status"] == "unsnapshotted", (
                f"{aid!r} missing from snapshots but recon status is "
                f"{rrow['status']!r}, expected 'unsnapshotted'"
            )
            assert rrow["expected_balance_cents"] is None
            assert rrow["delta_cents"] is None
        else:
            expected = snap[aid]
            actual = srow["balance_cents"]
            assert rrow["expected_balance_cents"] == expected
            assert rrow["delta_cents"] == actual - expected
            expected_status = "matched" if actual == expected else "mismatched"
            assert rrow["status"] == expected_status


def test_dataset_invariants_have_all_codes(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """The pinned dataset must exercise every diagnostic code at least once.
    A trivially clean input would mean the simulator is never stressed and
    the verifier reduces to formatting checks.
    """
    seen_codes = {d["code"] for d in expected_outputs["event_diagnostics"]["diagnostics"]}
    missing = VALID_DIAG_CODES - seen_codes
    assert not missing, (
        f"dataset invariant: every diagnostic code should appear at least "
        f"once in the pinned trace; missing {sorted(missing)}"
    )


def test_dataset_invariants_have_all_reversal_reasons(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """The pinned dataset must exercise every E_INVALID_REVERSAL reason."""
    reasons = {
        d["evidence"]["reason"]
        for d in expected_outputs["event_diagnostics"]["diagnostics"]
        if d["code"] == "E_INVALID_REVERSAL"
    }
    missing = VALID_REVERSAL_REASONS - reasons
    assert not missing, (
        f"dataset invariant: every E_INVALID_REVERSAL reason should appear "
        f"at least once; missing {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests. Each constructs a fresh tiny dataset,
# runs the agent's binary on it, and asserts the binary matches the live
# reference implementation. These cover branches the pinned dataset does
# not exercise (or only exercises in combination with other branches).
# ---------------------------------------------------------------------------


_BASE_POLICY = {
    "severity_ranks": {"error": 0, "warning": 1, "note": 2},
    "default_daily_withdraw_limit_cents": 100000,
    "overdraft_allowed_account_types": ["credit"],
    "credit_account_credit_limit_cents": 200000,
    "reversal_window_days": 5,
    "hold_max_age_days": 7,
    "transfer_self_action": "error",
    "frozen_account_action": "allow_credits_only",
    "closed_account_action": "block_all",
}


def _acct(aid: str, *, opening: int = 0, status: str = "active",
          account_type: str = "checking", tier: str = "basic",
          override: int | None = None) -> dict[str, Any]:
    return {
        "id": aid, "currency": "USD", "opening_balance_cents": opening,
        "tier": tier, "account_type": account_type, "status": status,
        "daily_withdraw_limit_cents": override,
    }


def _ev(seq: int, day: int, op: str, account: str, *,
        target: str | None = None, amount: int | None = None,
        currency: str | None = "USD", reverses: int | None = None) -> dict[str, Any]:
    return {
        "seq": seq, "day": day, "op": op, "account": account,
        "target_account": target, "amount_cents": amount,
        "currency": currency if amount is not None or op in ("deposit", "withdraw", "transfer", "hold") else None,
        "reverses_seq": reverses,
    }


def test_hidden_transfer_self_action_ignore_swallows_silently(
    tmp_path: Path,
) -> None:
    """Hidden dataset: under transfer_self_action='ignore', a self-transfer
    must be silently dropped — no E_SELF_TRANSFER diagnostic, no money moves.
    Catches agents that hardcode 'error' behavior.
    """
    policy = dict(_BASE_POLICY, transfer_self_action="ignore")
    accounts = {"accounts": [_acct("X", opening=10000)]}
    events = {"events": [
        _ev(0, 0, "deposit", "X", amount=5000),
        _ev(1, 0, "transfer", "X", target="X", amount=3000),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    assert actual["event_diagnostics.json"] == expected["event_diagnostics"]
    diagnostics = actual["event_diagnostics.json"]["diagnostics"]
    for d in diagnostics:
        assert d["code"] != "E_SELF_TRANSFER", (
            "transfer_self_action=='ignore' must not emit E_SELF_TRANSFER"
        )
    X = actual["account_state.json"]["accounts"][0]
    assert X["balance_cents"] == 15000, (
        f"silent self-transfer must not change balance; expected 15000, got "
        f"{X['balance_cents']}"
    )

def test_hidden_overdraft_disabled_for_savings(tmp_path: Path) -> None:
    """Hidden dataset: even if 'savings' is in overdraft_allowed_account_types,
    only the 'credit' literal opens the negative floor. Savings still floors
    at zero. This catches agents that read the list as
    'all of these get the negative limit'.
    """
    policy = dict(
        _BASE_POLICY,
        overdraft_allowed_account_types=["credit", "savings"],
    )
    accounts = {"accounts": [_acct("S", opening=1000, account_type="savings")]}
    events = {"events": [
        _ev(0, 0, "withdraw", "S", amount=1500),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    seen = [d["code"] for d in actual["event_diagnostics.json"]["diagnostics"]]
    assert seen == ["E_INSUFFICIENT_FUNDS"], (
        "savings account should still floor at 0 even when 'savings' is in "
        f"overdraft_allowed_account_types; got diagnostics={seen}"
    )


def test_hidden_per_account_daily_limit_override(tmp_path: Path) -> None:
    """Hidden dataset: when an account sets daily_withdraw_limit_cents, that
    override wins over the policy default. Catches agents that always read
    the policy default.
    """
    policy = dict(_BASE_POLICY, default_daily_withdraw_limit_cents=10000)
    accounts = {"accounts": [
        _acct("A", opening=1000000, override=200000),
        _acct("B", opening=1000000),
    ]}
    events = {"events": [
        _ev(0, 0, "withdraw", "A", amount=150000),
        _ev(1, 0, "withdraw", "B", amount=15000),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    assert actual["event_diagnostics.json"] == expected["event_diagnostics"]
    by_id = {r["id"]: r for r in actual["account_state.json"]["accounts"]}
    assert by_id["A"]["balance_cents"] == 850000, (
        "A had override=200000 so 150000 withdraw should succeed"
    )
    assert by_id["B"]["balance_cents"] == 1000000, (
        "B used policy default 10000 so 15000 withdraw should be rejected"
    )


def test_hidden_reverse_of_transfer_credits_back_both_legs(
    tmp_path: Path,
) -> None:
    """Hidden dataset: reversing a successful transfer must credit the source
    back AND debit the target back, and increment n_reversed_events on BOTH
    accounts.
    """
    accounts = {"accounts": [_acct("S", opening=10000), _acct("T", opening=0)]}
    events = {"events": [
        _ev(0, 0, "transfer", "S", target="T", amount=4000),
        _ev(1, 1, "reverse", "S", reverses=0),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, _BASE_POLICY)
    expected = _ref_for(accounts, events, snapshots, _BASE_POLICY)
    assert actual["account_state.json"] == expected["account_state"]
    by_id = {r["id"]: r for r in actual["account_state.json"]["accounts"]}
    assert by_id["S"]["balance_cents"] == 10000, (
        f"after transfer-then-reverse, source must be back at 10000; got "
        f"{by_id['S']['balance_cents']}"
    )
    assert by_id["T"]["balance_cents"] == 0, (
        f"after transfer-then-reverse, target must be back at 0; got "
        f"{by_id['T']['balance_cents']}"
    )
    assert by_id["S"]["n_reversed_events"] == 1, (
        "source of reversed transfer must have n_reversed_events == 1"
    )
    assert by_id["T"]["n_reversed_events"] == 1, (
        "target of reversed transfer must have n_reversed_events == 1"
    )


def test_hidden_reverse_skips_overdraft_check(tmp_path: Path) -> None:
    """Hidden dataset: a reverse of a deposit can push the account below zero
    on a non-overdraft account WITHOUT emitting E_INSUFFICIENT_FUNDS,
    because reversals must skip the overdraft / daily-limit / frozen / self
    gates per spec.
    """
    accounts = {"accounts": [_acct("X", opening=0)]}
    events = {"events": [
        _ev(0, 0, "deposit", "X", amount=5000),
        _ev(1, 0, "withdraw", "X", amount=4000),
        _ev(2, 1, "reverse", "X", reverses=0),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, _BASE_POLICY)
    expected = _ref_for(accounts, events, snapshots, _BASE_POLICY)
    assert actual["account_state.json"] == expected["account_state"]
    X = actual["account_state.json"]["accounts"][0]
    assert X["balance_cents"] == -4000, (
        f"reversing deposit must put X at -4000 even though account_type "
        f"='checking' has zero overdraft floor; got {X['balance_cents']}"
    )
    seen = [d["code"] for d in actual["event_diagnostics.json"]["diagnostics"]]
    assert "E_INSUFFICIENT_FUNDS" not in seen, (
        f"reversal must skip overdraft gate; got {seen}"
    )


def test_hidden_release_no_op_when_target_seq_unknown(tmp_path: Path) -> None:
    """Hidden dataset: a release event whose reverses_seq does not match an
    active hold on the same account is a silent no-op (no diagnostic, no
    state change). Catches agents that emit a spurious E_INVALID_REVERSAL or
    drop unrelated holds.
    """
    accounts = {"accounts": [_acct("H", opening=10000)]}
    events = {"events": [
        _ev(0, 0, "hold", "H", amount=2000),
        _ev(1, 0, "release", "H", reverses=999),
        _ev(2, 0, "release", "H", reverses=0),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, _BASE_POLICY)
    expected = _ref_for(accounts, events, snapshots, _BASE_POLICY)
    assert actual["account_state.json"] == expected["account_state"]
    H = actual["account_state.json"]["accounts"][0]
    assert H["active_holds"] == [], (
        f"hold should have been released by seq=2; got {H['active_holds']}"
    )
    assert actual["event_diagnostics.json"]["diagnostics"] == [], (
        f"release with unknown reverses_seq must not emit any diagnostic; "
        f"got {actual['event_diagnostics.json']['diagnostics']}"
    )


def test_hidden_reverse_outside_window_strict_inequality(
    tmp_path: Path,
) -> None:
    """Hidden dataset: reverse within reversal_window_days inclusive must
    succeed; one day past must fail. Boundary check on the window arithmetic.
    """
    policy = dict(_BASE_POLICY, reversal_window_days=3)
    accounts = {"accounts": [_acct("Z", opening=0)]}
    events = {"events": [
        _ev(0, 0, "deposit", "Z", amount=1000),
        _ev(1, 3, "reverse", "Z", reverses=0),
        _ev(2, 5, "deposit", "Z", amount=2000),
        _ev(3, 9, "reverse", "Z", reverses=2),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    diags = actual["event_diagnostics.json"]["diagnostics"]
    invalid = [d for d in diags if d["code"] == "E_INVALID_REVERSAL"]
    assert len(invalid) == 1, (
        f"exactly one E_INVALID_REVERSAL expected (for the seq=3 reverse); "
        f"got {len(invalid)} -> {invalid}"
    )
    assert invalid[0]["evidence"]["reason"] == "outside_window"
    assert invalid[0]["seq"] == 3
    Z = actual["account_state.json"]["accounts"][0]
    assert Z["balance_cents"] == 2000, (
        f"first reverse should succeed (-1000) and second fail (no change); "
        f"expected balance 2000, got {Z['balance_cents']}"
    )


def test_hidden_frozen_target_allow_credit_permits_inbound_transfer(
    tmp_path: Path,
) -> None:
    """Hidden dataset: under frozen_account_action='allow_credits_only', the
    inbound (credit) leg of a transfer to a frozen account proceeds, and the
    source side completes too. Agents that block both legs unconditionally
    will diverge.
    """
    policy = dict(_BASE_POLICY, frozen_account_action="allow_credits_only")
    accounts = {"accounts": [
        _acct("S", opening=10000),
        _acct("F", opening=0, status="frozen"),
    ]}
    events = {"events": [
        _ev(0, 0, "transfer", "S", target="F", amount=1500),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    by_id = {r["id"]: r for r in actual["account_state.json"]["accounts"]}
    assert by_id["S"]["balance_cents"] == 8500
    assert by_id["F"]["balance_cents"] == 1500
    assert actual["event_diagnostics.json"]["diagnostics"] == []


def test_hidden_closed_account_blocks_inbound_transfer_even_under_allow_credits(
    tmp_path: Path,
) -> None:
    """Hidden dataset: closed_account_action='block_all' means a transfer
    *to* a closed account still fails with E_CLOSED_ACCOUNT, even if
    frozen_account_action would have permitted credits. The diagnostic's
    'account' field is the closed account (the rejecting account), not the
    transferring source. Agents that confuse the two will diverge.
    """
    policy = dict(_BASE_POLICY, closed_account_action="block_all")
    accounts = {"accounts": [
        _acct("S", opening=10000),
        _acct("D", opening=0, status="closed"),
    ]}
    events = {"events": [
        _ev(0, 0, "transfer", "S", target="D", amount=1500),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["account_state.json"] == expected["account_state"]
    diags = actual["event_diagnostics.json"]["diagnostics"]
    assert len(diags) == 1
    assert diags[0]["code"] == "E_CLOSED_ACCOUNT"
    assert diags[0]["account"] == "D", (
        f"E_CLOSED_ACCOUNT diagnostic must be attributed to the closed "
        f"account ('D'), not the source; got account={diags[0]['account']!r}"
    )
    by_id = {r["id"]: r for r in actual["account_state.json"]["accounts"]}
    assert by_id["S"]["balance_cents"] == 10000
    assert by_id["D"]["balance_cents"] == 0


def test_hidden_hold_expired_uses_max_event_seq(tmp_path: Path) -> None:
    """Hidden dataset: W_HOLD_EXPIRED must carry seq == max_event_seq, not
    the hold's own seq. Catches agents that report the hold's seq.
    """
    policy = dict(_BASE_POLICY, hold_max_age_days=2)
    accounts = {"accounts": [_acct("Y", opening=10000)]}
    events = {"events": [
        _ev(0, 0, "hold", "Y", amount=1000),
        _ev(1, 0, "deposit", "Y", amount=500),
        _ev(2, 5, "deposit", "Y", amount=500),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["event_diagnostics.json"] == expected["event_diagnostics"]
    expired = [d for d in actual["event_diagnostics.json"]["diagnostics"]
               if d["code"] == "W_HOLD_EXPIRED"]
    assert len(expired) == 1
    assert expired[0]["seq"] == 2, (
        f"W_HOLD_EXPIRED must carry max_event_seq (=2), not the hold's own "
        f"seq (=0); got seq={expired[0]['seq']}"
    )
    assert expired[0]["evidence"]["age_days"] == 5
    assert expired[0]["evidence"]["hold_seq"] == 0


def test_hidden_reconciliation_unsnapshotted_silent(tmp_path: Path) -> None:
    """Hidden dataset: an account missing from snapshots.expected_balances
    is reconciled with status='unsnapshotted' and emits NO
    N_RECONCILIATION_MISMATCH diagnostic, even when its actual balance is
    arbitrary.
    """
    accounts = {"accounts": [_acct("U", opening=42)]}
    events = {"events": [
        _ev(0, 0, "deposit", "U", amount=58),
    ]}
    snapshots = {"expected_balances": {}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, _BASE_POLICY)
    expected = _ref_for(accounts, events, snapshots, _BASE_POLICY)
    assert actual["reconciliation_report.json"] == expected["reconciliation_report"]
    row = actual["reconciliation_report.json"]["accounts"][0]
    assert row["status"] == "unsnapshotted"
    assert row["expected_balance_cents"] is None
    assert row["delta_cents"] is None
    seen = [d["code"] for d in actual["event_diagnostics.json"]["diagnostics"]]
    assert "N_RECONCILIATION_MISMATCH" not in seen


def test_hidden_diagnostic_sort_order_severity_then_seq(tmp_path: Path) -> None:
    """Hidden dataset: diagnostics must be sorted by
    (severity_rank asc, seq asc, code asc, account asc). Build a trace that
    forces an error at seq=3 and a note (reconciliation) reported at
    max_event_seq=4 and assert ordering.
    """
    policy = _BASE_POLICY
    accounts = {"accounts": [_acct("Q", opening=0)]}
    events = {"events": [
        _ev(0, 0, "deposit", "Q", amount=1000),
        _ev(1, 0, "deposit", "Q", amount=1000),
        _ev(2, 0, "deposit", "Q", amount=1000),
        _ev(3, 0, "withdraw", "Q", amount=999999),
        _ev(4, 0, "deposit", "Q", amount=1),
    ]}
    snapshots = {"expected_balances": {"Q": 999}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, policy)
    expected = _ref_for(accounts, events, snapshots, policy)
    assert actual["event_diagnostics.json"] == expected["event_diagnostics"]
    diags = actual["event_diagnostics.json"]["diagnostics"]
    codes = [(d["severity_rank"], d["seq"], d["code"]) for d in diags]
    assert codes == sorted(codes), (
        f"diagnostics must be sorted by (severity_rank, seq, code, account); "
        f"got {codes}"
    )
    assert diags[0]["code"] == "E_DAILY_LIMIT_EXCEEDED", (
        "the error must precede the note in sorted order"
    )


def test_hidden_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Running the binary twice on the canonical input must produce
    byte-identical outputs. Catches latent nondeterminism (hash-map
    iteration order, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (ACCOUNTS_PATH, EVENTS_PATH, SNAPSHOTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            _java_cmd(in_dir, out),
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("account_state.json", "event_diagnostics.json",
                  "reconciliation_report.json", "compliance_summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input; "
            f"binary is non-deterministic"
        )

def test_hidden_events_processed_in_seq_order_not_input_order(
    tmp_path: Path,
) -> None:
    """Hidden dataset: the binary must process events in strict ascending
    seq order regardless of how the events array is laid out in events.json.
    Build a trace whose array order is *reverse* of seq order; a binary that
    consumes input order will get a wildly different ledger state.

    The carefully-chosen amounts mean array-order processing yields a
    non-zero balance whereas seq-order processing yields exactly the
    expected pinned balance, so the divergence is unambiguous.
    """
    accounts = {"accounts": [_acct("M", opening=1000)]}
    events_in_seq_order = [
        _ev(0, 0, "deposit", "M", amount=500),
        _ev(1, 0, "withdraw", "M", amount=200),
        _ev(2, 0, "deposit", "M", amount=300),
        _ev(3, 0, "withdraw", "M", amount=400),
        _ev(4, 0, "deposit", "M", amount=100),
    ]
    events = {"events": list(reversed(events_in_seq_order))}
    snapshots = {"expected_balances": {"M": 1300}}
    actual = _run_binary_on(tmp_path, accounts, events, snapshots, _BASE_POLICY)
    expected = _ref_for(accounts, events, snapshots, _BASE_POLICY)
    assert actual["account_state.json"] == expected["account_state"], (
        "binary did not process events in strict ascending seq order; "
        "it likely consumed input/array order, yielding a different ledger "
        "state than the spec requires"
    )
    M = actual["account_state.json"]["accounts"][0]
    assert M["balance_cents"] == 1300, (
        f"after processing seq=0..4 in seq order on opening=1000, balance "
        f"must be 1300; got {M['balance_cents']} (likely processed in input "
        f"order instead of seq order)"
    )
    diags = actual["event_diagnostics.json"]["diagnostics"]
    seen_codes = [d["code"] for d in diags]
    assert "N_RECONCILIATION_MISMATCH" not in seen_codes, (
        "balance should reconcile to expected 1300 when events are processed "
        "in seq order; mismatch suggests input-order processing"
    )
