#!/bin/bash
set -euo pipefail

DATA_DIR="${OCL_DATA_DIR:-/app/oauthlattice}"
AUDIT_DIR="${OCL_AUDIT_DIR:-/app/audit}"

mkdir -p "$AUDIT_DIR"

export OCL_DATA_DIR="$DATA_DIR"
export OCL_AUDIT_DIR="$AUDIT_DIR"

python3 <<'PY'
from __future__ import annotations

import json
import os
import re
from pathlib import Path

DATA = Path(os.environ["OCL_DATA_DIR"])
OUT = Path(os.environ["OCL_AUDIT_DIR"])

LOCAL_RE = re.compile(r"^http://127\.0\.0\.1:\d+/")
LOCALHOST_RE = re.compile(r"^http://localhost:\d+/")


def read_json(p: Path) -> object:
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(name: str, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (OUT / name).write_text(text, encoding="utf-8")


pool = read_json(DATA / "pool_state.json")
current_day = int(pool["current_day"])

supported_set = set(read_json(DATA / "policy" / "supported_kinds.json")["kinds"])
grant_caps = read_json(DATA / "policy" / "grant_caps.json")["caps"]
scope_edges = read_json(DATA / "policy" / "scope_implications.json")["edges"]
tier_rules = read_json(DATA / "policy" / "tier_rules.json")
redirect_mode = tier_rules["redirect_mode"]
pkce_table = tier_rules["pkce_for_auth_code"]

clients: dict[str, dict] = {}
for p in sorted((DATA / "clients").glob("*.json")):
    c = read_json(p)
    clients[c["client_id"]] = c

resources: dict[str, dict] = {}
for p in sorted((DATA / "resources").glob("*.json")):
    r = read_json(p)
    resources[r["resource_id"]] = r

bindings: list[dict] = []
for p in sorted((DATA / "bindings").glob("*.json")):
    bindings.append(read_json(p))
bindings.sort(key=lambda b: b["binding_id"])

events = read_json(DATA / "incident_log.json")["events"]
events_sorted = sorted(events, key=lambda e: (int(e["day"]), str(e["event_id"])))

state: dict[str, dict] = {
    cid: {"tier_override": None, "quarantine": False, "revoked": set(), "pinned": set()}
    for cid in clients
}

trace_rows: list[dict] = []
ignored_counts = {
    "ignored_future_day": 0,
    "ignored_not_accepted": 0,
    "ignored_unsupported_kind": 0,
}
applied_incidents = 0

for ev in events_sorted:
    day = int(ev["day"])
    kind = str(ev["kind"])
    accepted = bool(ev["accepted"])
    eid = str(ev["event_id"])
    if day > current_day:
        res = "ignored_future_day"
        ignored_counts["ignored_future_day"] += 1
    elif not accepted:
        res = "ignored_not_accepted"
        ignored_counts["ignored_not_accepted"] += 1
    elif kind not in supported_set:
        res = "ignored_unsupported_kind"
        ignored_counts["ignored_unsupported_kind"] += 1
    else:
        res = "applied"
        applied_incidents += 1
        pl = ev.get("payload") or {}
        cid = str(pl["client_id"])
        st = state[cid]
        if kind == "client_quarantine":
            st["quarantine"] = bool(pl["active"])
        elif kind == "scope_revoke":
            for s in pl.get("scopes", []):
                st["revoked"].add(str(s))
        elif kind == "redirect_pin":
            st["pinned"].add(str(pl["redirect_uri"]))
        elif kind == "tier_override":
            st["tier_override"] = str(pl["new_tier"])
    trace_rows.append(
        {
            "accepted": accepted,
            "day": day,
            "event_id": eid,
            "kind": kind,
            "resolution": res,
        }
    )


def scope_closure(base: list[str], edges: list[dict]) -> list[str]:
    cur = set(base)
    changed = True
    while changed:
        changed = False
        for e in edges:
            parent = str(e["parent"])
            child = str(e["child"])
            if parent in cur and child not in cur:
                cur.add(child)
                changed = True
    return sorted(cur)


def best_prefix_match(requested: str, cand: list[str]) -> str | None:
    best_u: str | None = None
    for u in cand:
        ok = requested == u or (
            len(requested) > len(u) and requested.startswith(u) and requested[len(u)] == "/"
        )
        if not ok:
            continue
        if best_u is None or len(u) > len(best_u) or (len(u) == len(best_u) and u < best_u):
            best_u = u
    return best_u


def redirect_pair(cid: str, requested: str) -> tuple[str, str | None]:
    if cid not in clients:
        return "blocked_unknown_client", None
    c = clients[cid]
    st = state[cid]
    if st["quarantine"]:
        return "blocked_quarantine", None
    eff_tier = st["tier_override"] or c["tier_declared"]
    mode = redirect_mode[eff_tier]
    cand = sorted(set(c["redirect_uris"]) | st["pinned"])
    if mode == "exact":
        if requested in cand:
            return "allowed_exact", requested
        return "blocked_not_listed", None
    if mode == "prefix":
        u = best_prefix_match(requested, cand)
        if u is not None:
            return "allowed_prefix", u
        return "blocked_not_listed", None
    if mode == "prefix_or_localhost_public":
        u = best_prefix_match(requested, cand)
        if u is not None:
            return "allowed_prefix", u
        if c["client_type"] == "public" and (
            LOCAL_RE.match(requested) or LOCALHOST_RE.match(requested)
        ):
            return "allowed_localhost_public", "localhost_exception"
        return "blocked_not_listed", None
    raise RuntimeError(f"unknown redirect mode {mode!r}")


def resource_pair(cid: str, rid: str) -> tuple[str, str | None]:
    if cid not in clients:
        return "deny", "unknown_client"
    st = state[cid]
    if st["quarantine"]:
        return "deny", "quarantined"
    c = clients[cid]
    base = [s for s in c["registered_scopes"] if s not in st["revoked"]]
    eff_scopes = scope_closure(base, scope_edges)
    req = resources[rid]["required_scopes"]
    if all(s in eff_scopes for s in req):
        return "allow", None
    return "deny", "missing_scope"


client_rows: list[dict] = []
for cid in sorted(clients.keys()):
    c = clients[cid]
    st = state[cid]
    eff_tier = st["tier_override"] or c["tier_declared"]
    eff_redir = sorted(set(c["redirect_uris"]) | st["pinned"])
    if st["quarantine"]:
        eff_scopes: list[str] = []
    else:
        base = [s for s in c["registered_scopes"] if s not in st["revoked"]]
        eff_scopes = scope_closure(base, scope_edges)
    illegal = sorted(
        g
        for g in c["grant_types"]
        if g not in grant_caps[eff_tier][c["client_type"]]
    )
    if "authorization_code" in c["grant_types"]:
        pk = pkce_table[eff_tier][c["client_type"]]
        pkce_posture = "pkce_required" if pk == "required" else "pkce_relaxed"
    else:
        pkce_posture = "pkce_not_applicable"
    client_rows.append(
        {
            "client_id": cid,
            "client_type": c["client_type"],
            "effective_redirect_uri_count": len(eff_redir),
            "effective_scopes": eff_scopes,
            "effective_tier": eff_tier,
            "illegal_grants": illegal,
            "pkce_posture": pkce_posture,
            "quarantined": bool(st["quarantine"]),
            "registered_scope_count": len(c["registered_scopes"]),
        }
    )

binding_rows: list[dict] = []
redirect_rows: list[dict] = []
prefix_hits = 0
localhost_hits = 0
resource_allow = 0
resource_deny = 0

for b in bindings:
    bid = b["binding_id"]
    cid = b["client_id"]
    rid = b["resource_id"]
    req_redir = str(b["requested_redirect"])
    verdict, matched = redirect_pair(cid, req_redir)
    if verdict == "allowed_prefix":
        prefix_hits += 1
    if verdict == "allowed_localhost_public":
        localhost_hits += 1
    acc, reason = resource_pair(cid, rid)
    if acc == "allow":
        resource_allow += 1
    else:
        resource_deny += 1
    binding_rows.append(
        {
            "binding_id": bid,
            "client_id": cid,
            "deny_reason": reason,
            "resource_access": acc,
            "resource_id": rid,
        }
    )
    redirect_rows.append(
        {"binding_id": bid, "matched_rule": matched, "verdict": verdict}
    )

illegal_clients = sum(1 for row in client_rows if row["illegal_grants"])
quarantined_clients = sum(1 for row in client_rows if row["quarantined"])

summary = {
    "applied_incidents": applied_incidents,
    "audit_version": 1,
    "binding_count": len(bindings),
    "client_count": len(clients),
    "current_day": current_day,
    "ignored_counts": ignored_counts,
    "illegal_grant_clients": illegal_clients,
    "localhost_redirect_matches": localhost_hits,
    "prefix_redirect_matches": prefix_hits,
    "quarantined_clients": quarantined_clients,
    "resource_allow_total": resource_allow,
    "resource_deny_total": resource_deny,
}

write_json("client_posture.json", {"clients": client_rows})
write_json("binding_access.json", {"bindings": binding_rows})
write_json("redirect_eval.json", {"redirects": redirect_rows})
write_json("incident_trace.json", {"events": trace_rows})
write_json("summary.json", summary)
PY
