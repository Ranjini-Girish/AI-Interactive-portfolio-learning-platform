#!/bin/bash
set -euo pipefail

mkdir -p "${OKL_AUDIT_DIR:-/app/audit}"

python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("OKL_DATA_DIR", "/app/oidc_keys"))
OUT = Path(os.environ.get("OKL_AUDIT_DIR", "/app/audit"))
JX = chr(46) + "json"


def write_json(path: Path, obj) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


pool = load_json(DATA / ("pool_state" + JX))
cd = int(pool["current_day"])
audit_version = str(pool["audit_version"])

policy = load_json(DATA / "governance" / ("policy" + JX))
G = int(policy["overlap_tail_days"])
supported = list(policy["supported_incident_kinds"])
eligible_phases = []
seen_ph = set()
for ph in policy["signing_eligible_phases"]:
    if ph not in seen_ph:
        eligible_phases.append(str(ph))
        seen_ph.add(str(ph))

records: list[tuple[str, str, dict]] = []
for sub, origin in (("published/keys", "published"), ("staged/keys", "staged")):
    d = DATA / Path(sub)
    for p in sorted(d.glob("*" + JX)):
        if not p.is_file():
            continue
        doc = load_json(p)
        records.append((origin, p.as_posix(), doc))


def better(a: tuple, b: tuple) -> bool:
    """Return True if b beats a."""
    seq_a, na_a, nb_a, rid_a, org_a = a
    seq_b, na_b, nb_b, rid_b, org_b = b
    if seq_b != seq_a:
        return seq_b > seq_a
    if na_b != na_a:
        return na_b > na_a
    if nb_b != nb_a:
        return nb_b > nb_a
    if rid_b != rid_a:
        return rid_b < rid_a
    if org_b != org_a:
        return org_b == "staged" and org_a == "published"
    return False


merged: dict[str, dict] = {}
for origin, _path, doc in records:
    kid = str(doc["kid"])
    cand = (
        int(doc["sequence"]),
        int(doc["not_after_day"]),
        int(doc["not_before_day"]),
        str(doc["record_id"]),
        origin,
    )
    if kid not in merged:
        merged[kid] = {"doc": doc, "origin": origin, "tuple": cand}
        continue
    cur = merged[kid]["tuple"]
    if better(cur, cand):
        merged[kid] = {"doc": doc, "origin": origin, "tuple": cand}

events = load_json(DATA / ("incident_log" + JX))["events"]

ignored_events: list[dict] = []
accepted_raw: list[dict] = []
unsupported_kind_events = 0

for ev in events:
    eid = str(ev["event_id"])
    day = int(ev["day"])
    kind = str(ev["kind"])
    scope = str(ev.get("scope", "global"))
    acc = bool(ev.get("accepted", False))
    if not acc:
        ignored_events.append(
            {
                "day": day,
                "dedup_target": "",
                "event_id": eid,
                "kind": kind,
                "scope": scope,
            }
        )
        continue
    if kind not in supported:
        unsupported_kind_events += 1
        ignored_events.append(
            {
                "day": day,
                "dedup_target": "",
                "event_id": eid,
                "kind": kind,
                "scope": scope,
            }
        )
        continue
    if day > cd:
        ignored_events.append(
            {
                "day": day,
                "dedup_target": "",
                "event_id": eid,
                "kind": kind,
                "scope": scope,
            }
        )
        continue
    accepted_raw.append(ev)


def dedup_target(ev: dict) -> str:
    kind = str(ev["kind"])
    pl = ev.get("payload", {})
    if kind in {"extend_validity", "revoke_key"}:
        return str(pl.get("kid", ""))
    if kind == "audience_emergency":
        return str(pl.get("target_server_id", ""))
    return ""


groups: dict[tuple[str, str, str, int], list[dict]] = {}
for ev in accepted_raw:
    key = (str(ev["kind"]), str(ev.get("scope", "global")), dedup_target(ev), int(ev["day"]))
    groups.setdefault(key, []).append(ev)

survivors: list[dict] = []
for key, lst in groups.items():
    lst_sorted = sorted(lst, key=lambda e: str(e["event_id"]))
    keep = lst_sorted[0]
    survivors.append(keep)
    for drop in lst_sorted[1:]:
        ignored_events.append(
            {
                "day": int(drop["day"]),
                "dedup_target": dedup_target(drop),
                "event_id": str(drop["event_id"]),
                "kind": str(drop["kind"]),
                "scope": str(drop.get("scope", "global")),
            }
        )

survivors.sort(key=lambda e: (int(e["day"]), str(e["event_id"])))

extends = [e for e in survivors if str(e["kind"]) == "extend_validity"]
revokes = [e for e in survivors if str(e["kind"]) == "revoke_key"]
emergencies = [e for e in survivors if str(e["kind"]) == "audience_emergency"]

na_eff: dict[str, int] = {}
base_row: dict[str, dict] = {}
for kid, row in merged.items():
    doc = row["doc"]
    na_eff[kid] = int(doc["not_after_day"])
    base_row[kid] = row

for ex in extends:
    pl = ex.get("payload", {})
    kid = str(pl.get("kid", ""))
    add = int(pl.get("add_days", 0))
    if kid not in na_eff:
        ignored_events.append(
            {
                "day": int(ex["day"]),
                "dedup_target": kid,
                "event_id": str(ex["event_id"]),
                "kind": str(ex["kind"]),
                "scope": str(ex.get("scope", "global")),
            }
        )
        continue
    na_eff[kid] = na_eff[kid] + add

revoked: set[str] = set()
for rv in revokes:
    pl = rv.get("payload", {})
    kid = str(pl.get("kid", ""))
    eff = int(pl.get("effective_day", 10**9))
    if eff <= cd:
        revoked.add(kid)


def lifecycle_phase(kid: str, nb: int, na: int) -> tuple[str, list[str]]:
    if kid in revoked:
        return "revoked_incident", ["revoked"]
    if cd < nb:
        return "premature", ["before_not_before"]
    if cd > na:
        return "expired", ["after_not_after"]
    tail_start = na - G + 1
    if cd >= tail_start:
        return "grace_tail", ["overlap_tail"]
    return "active", ["in_window"]


keys_out = []
for kid in sorted(merged.keys()):
    doc = merged[kid]["doc"]
    origin = merged[kid]["origin"]
    nb = int(doc["not_before_day"])
    na = na_eff[kid]
    prefs = list(doc["allowed_audience_prefixes"])
    phase, reasons = lifecycle_phase(kid, nb, na)
    keys_out.append(
        {
            "allowed_audience_prefixes": prefs,
            "kid": kid,
            "lifecycle_phase": phase,
            "not_after_effective": na,
            "not_before_day": nb,
            "origin": origin,
            "phase_reasons": sorted(reasons),
            "record_id": str(doc["record_id"]),
            "sequence": int(doc["sequence"]),
        }
    )

key_index = {row["kid"]: row for row in keys_out}

emerg_by_server: dict[str, dict] = {}
for ev in emergencies:
    pl = ev.get("payload", {})
    sid = str(pl.get("target_server_id", ""))
    start = int(pl.get("start_day", 10**9))
    until = int(pl.get("until_day", -1))
    if start <= cd <= until:
        emerg_by_server[sid] = {
            "surrogate_audience": str(pl.get("surrogate_audience", "")),
        }

servers_path = sorted((DATA / "servers").glob("*" + JX))
servers_out = []
overlap_rows = []
active_emergency = 0

for sp in servers_path:
    sdoc = load_json(sp)
    sid = str(sdoc["server_id"])
    req = str(sdoc["required_audience"])
    tier = str(sdoc["tier"])
    emerg = sid in emerg_by_server
    if emerg:
        active_emergency += 1
    eff = emerg_by_server[sid]["surrogate_audience"] if emerg else req

    eligible = []
    for kid, meta in key_index.items():
        if meta["lifecycle_phase"] not in eligible_phases:
            continue
        aud = eff
        ok = False
        for p in meta["allowed_audience_prefixes"]:
            if aud == p or aud.startswith(p):
                ok = True
                break
        if ok:
            eligible.append(kid)
    eligible.sort()

    chosen = ""
    if eligible:
        best_kid = eligible[0]
        best_meta = key_index[best_kid]
        best_t = (best_meta["sequence"], best_meta["not_after_effective"], best_kid)
        for kid in eligible[1:]:
            meta = key_index[kid]
            cand_t = (meta["sequence"], meta["not_after_effective"], kid)
            if cand_t[0] > best_t[0]:
                best_kid, best_t = kid, cand_t
            elif cand_t[0] == best_t[0] and cand_t[1] > best_t[1]:
                best_kid, best_t = kid, cand_t
            elif cand_t[0] == best_t[0] and cand_t[1] == best_t[1] and kid < best_t[2]:
                best_kid, best_t = kid, cand_t
        chosen = str(best_kid)

    servers_out.append(
        {
            "chosen_kid": chosen,
            "effective_audience": eff,
            "eligible_kids": eligible,
            "emergency_active": bool(emerg),
            "required_audience": req,
            "server_id": sid,
            "tier": tier,
        }
    )

    max_ov = 0
    witness: list[str] = []
    if len(eligible) >= 2:
        for i in range(len(eligible)):
            for j in range(i + 1, len(eligible)):
                a = eligible[i]
                b = eligible[j]
                nb_a = key_index[a]["not_before_day"]
                na_a = key_index[a]["not_after_effective"]
                nb_b = key_index[b]["not_before_day"]
                na_b = key_index[b]["not_after_effective"]
                lo = max(nb_a, nb_b)
                hi = min(na_a, na_b)
                ov = 0
                if lo <= hi:
                    ov = hi - lo + 1
                if ov > max_ov:
                    max_ov = ov
                    witness = sorted([a, b])
                elif ov == max_ov and ov > 0:
                    candw = sorted([a, b])
                    if not witness or candw < witness:
                        witness = candw
        if max_ov == 0:
            witness = []

    overlap_rows.append(
        {
            "max_pair_overlap_days": max_ov,
            "server_id": sid,
            "witness_kids": witness,
        }
    )

servers_out.sort(key=lambda r: r["server_id"])
overlap_rows.sort(key=lambda r: r["server_id"])

accepted_events = [
    {
        "day": int(e["day"]),
        "dedup_target": dedup_target(e),
        "event_id": str(e["event_id"]),
        "kind": str(e["kind"]),
        "scope": str(e.get("scope", "global")),
    }
    for e in survivors
]

ignored_events.sort(key=lambda r: (int(r["day"]), str(r["event_id"])))

summary = {
    "accepted_incident_events": len(survivors),
    "active_emergency_servers": active_emergency,
    "audit_version": audit_version,
    "current_day": cd,
    "ignored_incident_events": len(ignored_events),
    "keys_merged_count": len(merged),
    "revoked_key_count": len(revoked),
    "servers_scanned_count": len(servers_out),
    "unsupported_kind_events": unsupported_kind_events,
}

write_json(OUT / ("key_lifecycle" + JX), {"keys": keys_out})
write_json(OUT / ("server_bindings" + JX), {"servers": servers_out})
write_json(OUT / ("overlap_report" + JX), {"servers": overlap_rows})
write_json(
    OUT / ("incident_ledger" + JX),
    {"accepted_events": accepted_events, "ignored_events": ignored_events},
)
write_json(OUT / ("summary" + JX), summary)

PYEOF
