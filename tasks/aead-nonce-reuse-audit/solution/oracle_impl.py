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



# Reference simulator
# ---------------------------------------------------------------------------

KIND_REQUIRED_FIELDS = {
    "key_install":    ("key_id", "algorithm", "max_uses"),
    "encrypt":        ("key_id", "nonce"),
    "key_retire":     ("key_id",),
    "key_compromise": ("key_id", "reason"),
    "tick":           (),
}


def _emit(diags: list, *, seq: int, code: str, severity: str,
          severity_rank: int, key_id: str | None,
          evidence: dict) -> None:
    rec = {
        "seq": seq, "code": code, "severity": severity,
        "severity_rank": severity_rank,
        "key_id": key_id, "evidence": evidence,
    }
    diags.append(rec)


def _severity_rank(policy: dict, severity: str) -> int:
    return policy["severity_ranks"][severity]


def _push_audit(audit: list, *, seq: int, tick: int, key_id: str,
                kind: str, evidence: dict) -> None:
    audit.append({
        "seq": seq, "tick": tick, "key_id": key_id,
        "kind": kind, "evidence": evidence,
    })


def _idle_retire_sweep(now: int, seq: int, keys: dict, policy: dict,
                       diags: list, audit: list) -> None:
    threshold = policy["idle_retire_ticks"]
    for key_id in sorted(keys.keys()):
        k = keys[key_id]
        if k["state"] != "ACTIVE":
            continue
        if now - k["last_use_tick"] >= threshold:
            k["state"] = "RETIRED"
            k["retired_seq"] = seq
            evidence = {
                "last_use_tick": k["last_use_tick"],
                "now": now,
            }
            _emit(diags, seq=seq, code="N_KEY_IDLE_RETIRED",
                  severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=evidence)
            _push_audit(audit, seq=seq, tick=now, key_id=key_id,
                        kind="idle_retired", evidence=evidence)


def simulate(keys_in: dict, events_in: dict, policy: dict) -> dict[str, Any]:
    keys: dict[str, dict] = {}
    audit: list[dict] = []
    diags: list[dict] = []
    encryptions: list[dict] = []

    allowed_algorithms = set(policy["allowed_algorithms"])
    near_num, near_den = policy["near_exhaustion_ratio"]

    for k in keys_in.get("keys", []):
        key_id = k["key_id"]
        algorithm = k["algorithm"]
        max_uses = k["max_uses"]
        keys[key_id] = {
            "key_id": key_id,
            "algorithm": algorithm,
            "state": "ACTIVE",
            "max_uses": max_uses,
            "uses_count": 0,
            "installed_seq": 0,
            "retired_seq": None,
            "exhausted_seq": None,
            "compromised_seq": None,
            "last_use_tick": 0,
            "near_warned": False,
            "nonces": {},
        }
        _push_audit(audit, seq=0, tick=0, key_id=key_id, kind="installed",
                    evidence={"algorithm": algorithm, "max_uses": max_uses})

    events = sorted(events_in.get("events", []), key=lambda e: e["seq"])

    for ev in events:
        seq = ev["seq"]
        tick = ev["tick"]
        kind = ev.get("kind", "")

        _idle_retire_sweep(tick, seq, keys, policy, diags, audit)

        if kind not in KIND_REQUIRED_FIELDS:
            _emit(diags, seq=seq, code="E_INVALID_EVENT", severity="error",
                  severity_rank=_severity_rank(policy, "error"),
                  key_id=None, evidence={"reason": "unknown_kind"})
            continue
        if any(f not in ev for f in KIND_REQUIRED_FIELDS[kind]):
            _emit(diags, seq=seq, code="E_INVALID_EVENT", severity="error",
                  severity_rank=_severity_rank(policy, "error"),
                  key_id=None, evidence={"reason": "missing_field"})
            continue

        if kind == "key_install":
            key_id = ev["key_id"]
            algorithm = ev["algorithm"]
            max_uses = ev["max_uses"]
            if key_id in keys:
                _emit(diags, seq=seq, code="E_DUPLICATE_KEY",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"prior_state": keys[key_id]["state"]})
                continue
            if algorithm not in allowed_algorithms:
                _emit(diags, seq=seq, code="E_ALGORITHM_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"algorithm": algorithm})
                continue
            if not isinstance(max_uses, int) or max_uses <= 0:
                _emit(diags, seq=seq, code="E_INVALID_EVENT",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=None,
                      evidence={"reason": "non_positive_max_uses"})
                continue
            keys[key_id] = {
                "key_id": key_id,
                "algorithm": algorithm,
                "state": "ACTIVE",
                "max_uses": max_uses,
                "uses_count": 0,
                "installed_seq": seq,
                "retired_seq": None,
                "exhausted_seq": None,
                "compromised_seq": None,
                "last_use_tick": tick,
                "near_warned": False,
                "nonces": {},
            }
            _emit(diags, seq=seq, code="N_KEY_INSTALLED", severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id,
                  evidence={"algorithm": algorithm, "max_uses": max_uses})
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="installed",
                        evidence={"algorithm": algorithm,
                                  "max_uses": max_uses})

        elif kind == "encrypt":
            key_id = ev["key_id"]
            nonce = ev["nonce"]
            if key_id not in keys:
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "UNKNOWN_KEY",
                })
                _emit(diags, seq=seq, code="E_KEY_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "RETIRED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "RETIRED",
                })
                _emit(diags, seq=seq, code="E_KEY_NOT_ACTIVE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"key_state": "RETIRED"})
                continue
            if k["state"] == "EXHAUSTED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "EXHAUSTED",
                })
                _emit(diags, seq=seq, code="E_KEY_EXHAUSTED",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            if k["state"] == "COMPROMISED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "COMPROMISED",
                })
                _emit(diags, seq=seq, code="E_KEY_COMPROMISED",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            if nonce in k["nonces"]:
                first_seq, first_tick = k["nonces"][nonce]
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "NONCE_REUSE",
                })
                _emit(diags, seq=seq, code="E_NONCE_REUSE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"first_seq": first_seq,
                                "first_tick": first_tick})
                k["state"] = "COMPROMISED"
                k["compromised_seq"] = seq
                comp_ev = {"trigger": "nonce_reuse", "nonce": nonce}
                _emit(diags, seq=seq, code="N_KEY_COMPROMISED",
                      severity="notice",
                      severity_rank=_severity_rank(policy, "notice"),
                      key_id=key_id, evidence=comp_ev)
                _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                            kind="compromised", evidence=comp_ev)
                continue
            k["nonces"][nonce] = (seq, tick)
            k["uses_count"] += 1
            k["last_use_tick"] = tick
            encryptions.append({
                "seq": seq, "tick": tick, "key_id": key_id,
                "nonce": nonce, "outcome": "accepted", "reason": None,
            })
            if k["uses_count"] == k["max_uses"]:
                k["state"] = "EXHAUSTED"
                k["exhausted_seq"] = seq
                ex_ev = {"uses_count": k["uses_count"],
                         "max_uses": k["max_uses"]}
                _emit(diags, seq=seq, code="N_KEY_EXHAUSTED",
                      severity="notice",
                      severity_rank=_severity_rank(policy, "notice"),
                      key_id=key_id, evidence=ex_ev)
                _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                            kind="exhausted", evidence=ex_ev)
            elif (k["uses_count"] * near_den >= k["max_uses"] * near_num
                  and not k["near_warned"]):
                k["near_warned"] = True
                _emit(diags, seq=seq, code="W_KEY_NEAR_EXHAUSTION",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id,
                      evidence={"uses_count": k["uses_count"],
                                "max_uses": k["max_uses"]})

        elif kind == "key_retire":
            key_id = ev["key_id"]
            if key_id not in keys:
                _emit(diags, seq=seq, code="E_RETIRE_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "RETIRED":
                _emit(diags, seq=seq, code="W_RETIRE_ALREADY_RETIRED",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id, evidence={})
                continue
            if k["state"] in ("EXHAUSTED", "COMPROMISED"):
                _emit(diags, seq=seq, code="E_RETIRE_NOT_ACTIVE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"key_state": k["state"]})
                continue
            k["state"] = "RETIRED"
            k["retired_seq"] = seq
            ret_ev = {"trigger": "key_retire"}
            _emit(diags, seq=seq, code="N_KEY_RETIRED", severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=ret_ev)
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="retired", evidence=ret_ev)

        elif kind == "key_compromise":
            key_id = ev["key_id"]
            reason = ev["reason"]
            if key_id not in keys:
                _emit(diags, seq=seq, code="E_COMPROMISE_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "COMPROMISED":
                _emit(diags, seq=seq, code="W_COMPROMISE_REDUNDANT",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id, evidence={})
                continue
            k["state"] = "COMPROMISED"
            k["compromised_seq"] = seq
            comp_ev = {"trigger": "key_compromise", "reason": reason}
            _emit(diags, seq=seq, code="N_KEY_COMPROMISED",
                  severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=comp_ev)
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="compromised", evidence=comp_ev)

        elif kind == "tick":
            pass

    return _materialize_outputs(
        keys=keys, audit=audit, encryptions=encryptions, diags=diags,
        events_total=len(events),
    )


def _materialize_outputs(*, keys: dict, audit: list, encryptions: list,
                         diags: list, events_total: int) -> dict[str, Any]:
    key_list = sorted(
        [
            {
                "algorithm": k["algorithm"],
                "compromised_seq": k["compromised_seq"],
                "exhausted_seq": k["exhausted_seq"],
                "installed_seq": k["installed_seq"],
                "key_id": k["key_id"],
                "last_use_tick": k["last_use_tick"],
                "max_uses": k["max_uses"],
                "retired_seq": k["retired_seq"],
                "state": k["state"],
                "uses_count": k["uses_count"],
            }
            for k in keys.values()
        ],
        key=lambda k: k["key_id"],
    )

    encryptions_sorted = sorted(encryptions, key=lambda e: e["seq"])
    audit_sorted = sorted(audit, key=lambda a: (a["seq"], a["key_id"]))

    def diag_sort_key(d: dict) -> tuple:
        return (
            d["severity_rank"], d["seq"], d["code"],
            d["key_id"] if d["key_id"] is not None else "",
        )

    diags_sorted = sorted(diags, key=diag_sort_key)

    sev = {"error": 0, "warning": 0, "notice": 0}
    for d in diags_sorted:
        sev[d["severity"]] += 1

    enc_accepted = sum(1 for e in encryptions_sorted if e["outcome"] == "accepted")
    enc_rejected = sum(1 for e in encryptions_sorted if e["outcome"] == "rejected")

    totals = {
        "encryptions_accepted": enc_accepted,
        "encryptions_rejected": enc_rejected,
        "encryptions_total": len(encryptions_sorted),
        "errors": sev["error"],
        "events_total": events_total,
        "keys_total": len(key_list),
        "notices": sev["notice"],
        "warnings": sev["warning"],
    }

    return {
        "key_states":     {"keys": key_list},
        "encryption_log": {"encryptions": encryptions_sorted},
        "audit_log":      {"transitions": audit_sorted},
        "diagnostics":    {"diagnostics": diags_sorted},
        "summary":        {"totals": totals},
    }


# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    keys_in = load_json(in_dir / "keys.json")
    events_in = load_json(in_dir / "events.json")
    policy = load_json(in_dir / "policy.json")
    outputs = simulate(keys_in, events_in, policy)
    write_canonical(out_dir / "key_states.json", outputs["key_states"])
    write_canonical(out_dir / "encryption_log.json", outputs["encryption_log"])
    write_canonical(out_dir / "audit_log.json", outputs["audit_log"])
    write_canonical(out_dir / "diagnostics.json", outputs["diagnostics"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
