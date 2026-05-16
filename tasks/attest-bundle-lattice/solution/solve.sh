#!/bin/bash
set -euo pipefail

mkdir -p "${ABL_AUDIT_DIR:-/app/audit}"

python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("ABL_DATA_DIR", "/app/attest"))
OUT = Path(os.environ.get("ABL_AUDIT_DIR", "/app/audit"))

SUPPORTED = {
    "ban_email_pattern",
    "quarantine_artifact",
    "reparent_delegation",
    "revoke_key",
}


def write_json(path: Path, obj) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


pool = load_json(DATA / "pool_state.json")
current_day = int(pool["current_day"])
audit_version = str(pool["audit_version"])

trust = load_json(DATA / "policy" / "trust_graph.json")
identity_rules = load_json(DATA / "policy" / "identity_rules.json")
predicate_gates = load_json(DATA / "policy" / "predicate_gates.json")
load_json(DATA / "policy" / "emit_labels.json")
load_json(DATA / "policy" / "revision_stamp.json")
requires_material = set(predicate_gates.get("requires_material_witness", []))

anchors = set(str(x) for x in trust.get("anchor_key_ids", []))
max_depth = int(trust["max_chain_depth"])
base_parents: dict[str, str | None] = {}
for kid, row in trust["keys"].items():
    p = row.get("parent_key_id")
    base_parents[str(kid)] = None if p is None else str(p)

artifacts_dir = DATA / "artifacts"
artifact_paths = sorted([p for p in artifacts_dir.glob("*.json") if p.is_file()])
artifacts: list[dict] = []
for p in artifact_paths:
    artifacts.append(load_json(p))
artifacts.sort(key=lambda a: str(a["artifact_id"]))
fleet_digests = {str(a["digest"]) for a in artifacts}
quarantine_ids: set[str] = set()
revoked: set[str] = set()
ban_patterns: list[str] = []
parent_override: dict[str, str | None] = {}

raw_incidents = load_json(DATA / "incident_log.json")["incidents"]


def well_formed(inc: dict) -> bool:
    k = str(inc.get("kind", ""))
    if k == "quarantine_artifact":
        return isinstance(inc.get("artifact_id"), str)
    if k == "revoke_key":
        return isinstance(inc.get("key_id"), str)
    if k == "reparent_delegation":
        return isinstance(inc.get("key_id"), str) and ("new_parent_key_id" in inc)
    if k == "ban_email_pattern":
        pat = inc.get("pattern")
        if not isinstance(pat, str):
            return False
        if "*" in pat and not pat.startswith("*"):
            return False
        return True
    return False


def ignored_reason(inc: dict) -> str:
    if not bool(inc.get("accepted", False)):
        return "rejected"
    if int(inc.get("day", -1)) > current_day:
        return "future_day"
    if str(inc.get("kind", "")) not in SUPPORTED:
        return "unsupported_kind"
    if not well_formed(inc):
        return "rejected"
    return "eligible"


unsupported_kinds: set[str] = set()
for inc in raw_incidents:
    acc = bool(inc.get("accepted", False))
    day = int(inc.get("day", -1))
    kind = str(inc.get("kind", ""))
    if acc and day <= current_day and kind not in SUPPORTED:
        unsupported_kinds.add(kind)

trace_events: list[dict] = []
ignored_incidents = 0
eligible_rows: list[dict] = []

for inc in raw_incidents:
    reason = ignored_reason(inc)
    is_eligible = reason == "eligible"
    if not is_eligible:
        ignored_incidents += 1
    if is_eligible:
        eligible_rows.append(inc)
    trace_events.append(
        {
            "accepted": bool(inc.get("accepted", False)),
            "applied": is_eligible,
            "day": int(inc.get("day", -1)),
            "event_id": str(inc.get("event_id", "")),
            "ignored_reason": reason,
            "kind": str(inc.get("kind", "")),
        }
    )

eligible_rows.sort(key=lambda i: (int(i["day"]), str(i["event_id"])))

for inc in eligible_rows:
    kind = str(inc["kind"])
    if kind == "quarantine_artifact":
        quarantine_ids.add(str(inc["artifact_id"]))
    elif kind == "revoke_key":
        revoked.add(str(inc["key_id"]))
    elif kind == "ban_email_pattern":
        ban_patterns.append(str(inc["pattern"]))
    elif kind == "reparent_delegation":
        kid = str(inc["key_id"])
        np = inc.get("new_parent_key_id")
        parent_override[kid] = None if np is None else str(np)


def effective_parent(kid: str) -> str | None:
    if kid in anchors:
        return None
    if kid in parent_override:
        return parent_override[kid]
    return base_parents.get(kid)


def delegation_walk(kid: str) -> tuple[str, int]:
    if kid in anchors:
        return "anchor_ok", 0
    visited: set[str] = set()
    cur = kid
    hops = 0
    while cur not in anchors:
        if cur in visited:
            return "delegation_cycle", hops
        visited.add(cur)
        if hops == max_depth:
            return "depth_exceeded", hops
        parent = effective_parent(cur)
        if parent is None:
            return "untrustable_root", hops
        hops += 1
        if parent in anchors:
            return "anchor_ok", hops
        cur = parent
    return "anchor_ok", hops


def chain_has_revoked(kid: str) -> bool:
    if kid in revoked:
        return True
    if kid in anchors:
        return False
    seen: set[str] = set()
    cur = kid
    while cur not in anchors:
        if cur in revoked:
            return True
        if cur in seen:
            return False
        seen.add(cur)
        parent = effective_parent(cur)
        if parent is None:
            return False
        cur = parent
    return False


def email_banned(email: str) -> bool:
    for pat in ban_patterns:
        if "*" not in pat:
            if email == pat:
                return True
        elif pat.startswith("*"):
            if email.endswith(pat[1:]):
                return True
    return False


def identity_ok(tier: str, email: str) -> bool:
    rule = identity_rules.get(tier)
    if not rule:
        return False
    mode = str(rule["mode"])
    if mode == "allow_all":
        return True
    if mode == "exact_allowlist":
        allow = [str(x) for x in rule.get("allowlist", [])]
        return email in allow
    if mode == "suffix_allowlist":
        for suf in rule.get("suffixes", []):
            s = str(suf)
            if email.endswith(s):
                return True
        return False
    return False


def eval_signature(art: dict, sig: dict) -> str:
    aid = str(art["artifact_id"])
    if aid in quarantine_ids:
        return "quarantine_artifact"
    if str(sig["payload_digest"]) != str(art["digest"]):
        return "digest_mismatch"
    kid = str(sig["key_id"])
    if kid in revoked:
        return "revoked_key"
    if email_banned(str(sig["signer_email"])):
        return "ban_hit"
    status, _h = delegation_walk(kid)
    if status == "untrustable_root":
        return "untrusted_key"
    if status == "delegation_cycle":
        return "delegation_cycle"
    if status == "depth_exceeded":
        return "depth_exceeded"
    if status == "anchor_ok" and chain_has_revoked(kid):
        return "revoked_key"
    if not identity_ok(str(art["deployment_tier"]), str(sig["signer_email"])):
        return "identity_blocked"
    pred = str(sig["predicate_type"])
    if pred in requires_material:
        mats = [str(x) for x in sig.get("referential_material_digests", [])]
        for d in mats:
            if d not in fleet_digests:
                return "material_missing"
    return "verified_ok"


signature_rows: list[dict] = []
for art in artifacts:
    for sig in sorted(art.get("signatures", []), key=lambda s: str(s["signature_id"])):
        signature_rows.append(
            {
                "artifact_id": str(art["artifact_id"]),
                "key_id": str(sig["key_id"]),
                "outcome": eval_signature(art, sig),
                "policy_rank": int(sig["policy_rank"]),
                "predicate_type": str(sig["predicate_type"]),
                "signature_id": str(sig["signature_id"]),
                "signer_email": str(sig["signer_email"]),
            }
        )

catalog: list[dict] = []
for art in artifacts:
    aid = str(art["artifact_id"])
    sigs = sorted(art.get("signatures", []), key=lambda s: str(s["signature_id"]))
    outcomes = [(str(s["signature_id"]), eval_signature(art, s), int(s["policy_rank"])) for s in sigs]
    verified = [(sid, pr) for sid, oc, pr in outcomes if oc == "verified_ok"]
    if verified:
        verified.sort(key=lambda t: (t[1], t[0]))
        winner = verified[0][0]
        final_v = "verified_ok"
    else:
        winner = None
        final_v = min(outcomes, key=lambda t: t[0])[1]
    catalog.append(
        {
            "artifact_id": aid,
            "deployment_tier": str(art["deployment_tier"]),
            "digest": str(art["digest"]),
            "final_verdict": final_v,
            "quarantined": aid in quarantine_ids,
            "repository": str(art["repository"]),
            "winning_signature_id": winner,
        }
    )

key_ids: set[str] = set(base_parents.keys())
for row in signature_rows:
    key_ids.add(str(row["key_id"]))

delegation_rows: list[dict] = []
for kid in sorted(key_ids):
    st, edges = delegation_walk(kid)
    eff = effective_parent(kid)
    delegation_rows.append(
        {
            "chain_edges": int(edges),
            "delegation_status": st,
            "effective_parent_key_id": eff,
            "key_id": kid,
        }
    )

verdict_counts: dict[str, int] = {}
for row in catalog:
    v = str(row["final_verdict"])
    verdict_counts[v] = verdict_counts.get(v, 0) + 1

summary = {
    "artifact_count": len(catalog),
    "audit_version": audit_version,
    "current_day": current_day,
    "ignored_incidents": ignored_incidents,
    "quarantined_artifacts": sum(1 for r in catalog if r["quarantined"]),
    "signature_rows": len(signature_rows),
    "unsupported_incident_kinds": sorted(unsupported_kinds),
    "verdict_counts": verdict_counts,
}

write_json(OUT / "artifact_catalog.json", {"artifacts": catalog})
write_json(OUT / "signature_outcomes.json", {"signatures": signature_rows})
write_json(OUT / "delegation_audit.json", {"keys": delegation_rows})
write_json(OUT / "incident_trace.json", {"events": trace_events})
write_json(OUT / "summary.json", summary)
PYEOF
