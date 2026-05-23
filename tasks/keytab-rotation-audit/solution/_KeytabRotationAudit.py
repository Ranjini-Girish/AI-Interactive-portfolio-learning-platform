"""Reference keytab rotation auditor (dev parity with accepted C++ oracle)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
VERDICTS = [
    "valid",
    "valid_cross_fade",
    "invalid_kvno_unknown",
    "invalid_kvno_revoked",
    "invalid_kvno_retired",
    "downgrade_attempt",
    "weak_enctype",
]


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding="utf-8")


def anomaly_id(kind: str, principal: str, kvno: int | None, day: int, hour: int) -> str:
    payload = {"day": day, "hour": hour, "kind": kind, "kvno": kvno, "principal": principal}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def anomaly_details(kind: str, principal: str, kvno: int | None) -> str:
    if kvno is None:
        return f"{kind} on {principal}"
    return f"{kind} on {principal} kvno={kvno}"


def run_audit(data_dir: Path) -> dict[str, Any]:
    pool = json.loads((data_dir / "pool_state.json").read_text(encoding="utf-8"))
    current_day = pool["current_day"]
    current_hour = pool["current_hour"]

    rotpol = json.loads((data_dir / "policies" / "rotation_policy.json").read_text(encoding="utf-8"))
    cross_fade_hours = rotpol["cross_fade_hours"]
    tier_windows = dict(rotpol["tier_windows"])

    encpol = json.loads((data_dir / "policies" / "enctype_policy.json").read_text(encoding="utf-8"))
    policies = sorted(encpol["versions"], key=lambda v: v["effective_day"])

    def policy_at(d: int):
        best = None
        for pv in policies:
            if pv["effective_day"] <= d:
                if best is None or pv["effective_day"] > best["effective_day"]:
                    best = pv
        return best

    def enctype_allowed_at(enc: str, d: int) -> bool:
        pv = policy_at(d)
        if pv is None:
            return True
        if enc in pv["forbidden_enctypes"]:
            return False
        return enc in pv["allowed_enctypes"]

    principals: dict[str, dict[str, Any]] = {}
    for pfile in sorted((data_dir / "principals").glob("*.json")):
        j = json.loads(pfile.read_text(encoding="utf-8"))
        principals[j["principal"]] = j

    raw_keytab: list[dict[str, Any]] = []
    for p in sorted((data_dir / "events").glob("keytab_chunk_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw_keytab.append(json.loads(line))
    total_keytab_events = len(raw_keytab)

    kvalid = {"add", "revoke", "retire"}
    rvalid = {"compromise", "expired", "policy_violation", "administrative"}
    seen_ids: set[str] = set()
    all_keytab: list[dict[str, Any]] = []
    invalid_keytab_events = 0
    for j in raw_keytab:
        try:
            eid = j["event_id"]
            kind = j["kind"]
            princ = j["principal"]
            kvno = j["kvno"]
            day = j["day"]
            hour = j["hour"]
            if not eid or eid in seen_ids:
                raise ValueError
            if kind not in kvalid or princ not in principals:
                raise ValueError
            if not (1 <= kvno <= 99999) or day < 0 or not (0 <= hour <= 23):
                raise ValueError
            if day > current_day or (day == current_day and hour > current_hour):
                raise ValueError
            if kind == "add" and not j.get("enctype"):
                raise ValueError
            if kind == "revoke" and j.get("reason") not in rvalid:
                raise ValueError
            seen_ids.add(eid)
            all_keytab.append(j)
        except (KeyError, TypeError, ValueError):
            invalid_keytab_events += 1

    all_keytab.sort(key=lambda e: (e["day"], e["hour"], e["event_id"]))

    raw_tgs: list[dict[str, Any]] = []
    for p in sorted((data_dir / "events").glob("tgs_chunk_*.jsonl")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                raw_tgs.append(json.loads(line))
    total_tgs_requests = len(raw_tgs)
    seen_rids: set[str] = set()
    all_tgs: list[dict[str, Any]] = []
    invalid_tgs_requests = 0
    for j in raw_tgs:
        try:
            rid = j["request_id"]
            princ = j["principal"]
            kvno = j["kvno"]
            day = j["day"]
            hour = j["hour"]
            if not rid or rid in seen_rids or princ not in principals:
                raise ValueError
            if not (1 <= kvno <= 99999) or day < 0 or not (0 <= hour <= 23):
                raise ValueError
            if day > current_day or (day == current_day and hour > current_hour):
                raise ValueError
            seen_rids.add(rid)
            all_tgs.append(j)
        except (KeyError, TypeError, ValueError):
            invalid_tgs_requests += 1

    all_tgs.sort(key=lambda r: (r["day"], r["hour"], r["request_id"]))

    valid_names = {n for n, p in principals.items() if p["tier"] in tier_windows}
    invalid_names = {n for n in principals if n not in valid_names}

    state: dict[str, dict[int, dict[str, Any]]] = {}
    per_adds: dict[str, list[dict[str, Any]]] = {}
    anomalies: list[dict[str, Any]] = []

    def record(kind, severity, principal, kvno, day, hour):
        anomalies.append(
            {
                "kind": kind,
                "severity": severity,
                "principal": principal,
                "kvno": kvno,
                "day": day,
                "hour": hour,
            }
        )

    for e in all_keytab:
        if e["principal"] not in valid_names:
            continue
        princ = e["principal"]
        st = state.setdefault(princ, {})
        kv = e["kvno"]
        if e["kind"] == "add":
            exists = kv in st
            not_strict = False
            if not exists and st:
                mx = max(st)
                if kv <= mx:
                    not_strict = True
            if exists or not_strict:
                record("kvno_non_monotonic", "high", princ, kv, e["day"], e["hour"])
                continue
            st[kv] = {
                "kvno": kv,
                "added_day": e["day"],
                "added_hour": e["hour"],
                "enctype": e["enctype"],
                "revoked_day": None,
                "revoked_hour": None,
                "revoke_reason": None,
                "retired_day": None,
                "retired_hour": None,
                "final_state": "active",
            }
            per_adds.setdefault(princ, []).append(e)
        elif e["kind"] == "revoke":
            if kv not in st:
                record("revoke_unknown_kvno", "medium", princ, kv, e["day"], e["hour"])
                continue
            if st[kv]["final_state"] != "active":
                record("revoke_already_terminal", "low", princ, kv, e["day"], e["hour"])
                continue
            st[kv]["revoked_day"] = e["day"]
            st[kv]["revoked_hour"] = e["hour"]
            st[kv]["revoke_reason"] = e["reason"]
            st[kv]["final_state"] = "revoked"
        elif e["kind"] == "retire":
            if kv not in st:
                record("retire_unknown_kvno", "medium", princ, kv, e["day"], e["hour"])
                continue
            if st[kv]["final_state"] != "active":
                record("retire_already_terminal", "low", princ, kv, e["day"], e["hour"])
                continue
            st[kv]["retired_day"] = e["day"]
            st[kv]["retired_hour"] = e["hour"]
            st[kv]["final_state"] = "retired"

    compromised = set()
    for n, st in state.items():
        for r in st.values():
            if r["final_state"] == "revoked" and r.get("revoke_reason") == "compromise":
                compromised.add(n)
                break

    def active_at(princ, d, h):
        st = state.get(princ, {})
        act = []
        for k, r in st.items():
            if (r["added_day"], r["added_hour"]) > (d, h):
                continue
            if r["revoked_day"] is not None and (r["revoked_day"], r["revoked_hour"]) <= (d, h):
                continue
            if r["retired_day"] is not None and (r["retired_day"], r["retired_hour"]) <= (d, h):
                continue
            act.append(k)
        act.sort()
        return act

    def in_cross_fade(princ, kv, d, h):
        act = active_at(princ, d, h)
        if not act:
            return False
        cur = act[-1]
        if kv == cur:
            return False
        cr = state[princ][cur]
        t_h = d * 24 + h
        add_h = cr["added_day"] * 24 + cr["added_hour"]
        return t_h < add_h + cross_fade_hours

    verdict_counts = {v: 0 for v in VERDICTS}
    ticket_requests = []
    for r in all_tgs:
        if r["principal"] not in valid_names:
            continue
        princ = r["principal"]
        kv = r["kvno"]
        d, h = r["day"], r["hour"]
        rec = state.get(princ, {}).get(kv)
        unknown = rec is None or (rec["added_day"], rec["added_hour"]) > (d, h)
        anomaly_kind = None
        anomaly_sev = None
        if unknown:
            verdict = "invalid_kvno_unknown"
            anomaly_kind, anomaly_sev = "ticket_unknown_kvno", "high"
        elif rec["revoked_day"] is not None and (rec["revoked_day"], rec["revoked_hour"]) <= (d, h):
            verdict = "invalid_kvno_revoked"
            anomaly_kind, anomaly_sev = "ticket_against_revoked", "critical"
        elif rec["retired_day"] is not None and (rec["retired_day"], rec["retired_hour"]) <= (d, h):
            verdict = "invalid_kvno_retired"
            anomaly_kind, anomaly_sev = "ticket_against_retired", "medium"
        elif not enctype_allowed_at(rec["enctype"], d):
            verdict = "weak_enctype"
            anomaly_kind, anomaly_sev = "weak_enctype_in_use", "high"
        else:
            act = active_at(princ, d, h)
            cur = act[-1] if act else -1
            if kv == cur:
                verdict = "valid"
            elif in_cross_fade(princ, kv, d, h):
                verdict = "valid_cross_fade"
            else:
                verdict = "downgrade_attempt"
                anomaly_kind, anomaly_sev = "downgrade_attempt", "high"
        verdict_counts[verdict] += 1
        if anomaly_kind:
            record(anomaly_kind, anomaly_sev, princ, kv, d, h)
        if princ in compromised:
            record("compromised_principal_referenced", "critical", princ, kv, d, h)
        pv = policy_at(d)
        ticket_requests.append(
            {
                "day": d,
                "hour": h,
                "kvno": kv,
                "policy_version": pv["version"] if pv else "none",
                "principal": princ,
                "request_id": r["request_id"],
                "verdict": verdict,
            }
        )

    rot_principals = []
    for n in sorted(principals):
        if n in invalid_names:
            continue
        p = principals[n]
        entry = {
            "principal": n,
            "tier": p["tier"],
            "exempt": p["exempt"],
        }
        if p["exempt"]:
            entry.update(
                {
                    "rotation_window_days": None,
                    "last_rotation_day": None,
                    "next_due_day": None,
                    "status": "exempt",
                }
            )
        else:
            w = p.get("override_rotation_days")
            if w is None:
                w = tier_windows[p["tier"]]
            adds = per_adds.get(n, [])
            if not adds:
                entry.update(
                    {
                        "rotation_window_days": w,
                        "last_rotation_day": None,
                        "next_due_day": None,
                        "status": "never_rotated",
                    }
                )
                record("never_rotated", "high", n, None, current_day, 0)
            else:
                last_day = adds[-1]["day"]
                next_due = last_day + w
                entry["rotation_window_days"] = w
                entry["last_rotation_day"] = last_day
                entry["next_due_day"] = next_due
                if next_due < current_day:
                    entry["status"] = "overdue"
                    record("missed_rotation", "medium", n, None, current_day, 0)
                else:
                    entry["status"] = "compliant"
                half = (w * 24 + 1) // 2
                earliest = None
                for i in range(1, len(adds)):
                    prev, cur = adds[i - 1], adds[i]
                    gap = cur["day"] * 24 + cur["hour"] - prev["day"] * 24 - prev["hour"]
                    if gap < half:
                        key = (cur["day"], cur["hour"], cur["event_id"], cur["kvno"])
                        if earliest is None or key < earliest:
                            earliest = key
                if earliest:
                    record("excessive_rotation", "low", n, earliest[3], earliest[0], earliest[1])
        rot_principals.append(entry)

    for n in sorted(state):
        if n in invalid_names:
            continue
        act = active_at(n, current_day, current_hour)
        if not act:
            continue
        cur = act[-1]
        for k in act:
            if k != cur and not in_cross_fade(n, k, current_day, current_hour):
                record("missed_retirement", "medium", n, k, current_day, current_hour)

    for n, st in state.items():
        if n in invalid_names:
            continue
        for k, r in st.items():
            if r["final_state"] == "active" and not enctype_allowed_at(r["enctype"], current_day):
                record("forbidden_enctype_active", "medium", n, k, current_day, 0)

    anomalies.sort(
        key=lambda a: (
            SEVERITY_RANK[a["severity"]],
            a["day"],
            a["hour"],
            a["kind"],
            a["principal"],
            a["kvno"] is None,
            a["kvno"] if a["kvno"] is not None else 0,
        )
    )

    kvno_principals = []
    for n in sorted(principals):
        if n in invalid_names:
            continue
        p = principals[n]
        events = []
        for k in sorted(state.get(n, {})):
            r = state[n][k]
            events.append(
                {
                    "added_day": r["added_day"],
                    "added_hour": r["added_hour"],
                    "enctype": r["enctype"],
                    "final_state": r["final_state"],
                    "kvno": r["kvno"],
                    "retired_day": r["retired_day"],
                    "retired_hour": r["retired_hour"],
                    "revoke_reason": r["revoke_reason"],
                    "revoked_day": r["revoked_day"],
                    "revoked_hour": r["revoked_hour"],
                }
            )
        kvno_principals.append(
            {
                "exempt": p["exempt"],
                "kvno_events": events,
                "principal": n,
                "tier": p["tier"],
            }
        )

    anomaly_rows = []
    for a in anomalies:
        anomaly_rows.append(
            {
                "day": a["day"],
                "details": anomaly_details(a["kind"], a["principal"], a["kvno"]),
                "hour": a["hour"],
                "id": anomaly_id(a["kind"], a["principal"], a["kvno"], a["day"], a["hour"]),
                "kind": a["kind"],
                "kvno": a["kvno"],
                "principal": a["principal"],
                "severity": a["severity"],
            }
        )

    sev_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in anomalies:
        sev_counts[a["severity"]] += 1

    return {
        "kvno_lifecycle.json": {"principals": kvno_principals},
        "rotation_compliance.json": {"principals": rot_principals},
        "ticket_validity.json": {"requests": ticket_requests},
        "anomalies.json": {"anomalies": anomaly_rows},
        "summary.json": {
            "anomalies_per_severity": sev_counts,
            "compromised_principals": sorted(compromised),
            "current_day": current_day,
            "current_hour": current_hour,
            "exempt_principals": sum(1 for p in principals.values() if p["exempt"]),
            "invalid_keytab_events": invalid_keytab_events,
            "invalid_principals": len(invalid_names),
            "invalid_tgs_requests": invalid_tgs_requests,
            "tickets_per_verdict": verdict_counts,
            "total_keytab_events": total_keytab_events,
            "total_principals": len(principals),
            "total_tgs_requests": total_tgs_requests,
        },
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <data_dir> <audit_dir>", file=sys.stderr)
        return 2
    data_dir = Path(sys.argv[1])
    audit_dir = Path(sys.argv[2])
    audit_dir.mkdir(parents=True, exist_ok=True)
    for name, doc in run_audit(data_dir).items():
        write_canonical(audit_dir / name, doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
