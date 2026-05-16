#!/bin/bash
set -euo pipefail

mkdir -p "${ZIM_AUDIT_DIR:-/app/audit}"

python3 - <<'PYEOF'
from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("ZIM_DATA_DIR", "/app/zoning"))
OUT = Path(os.environ.get("ZIM_AUDIT_DIR", "/app/audit"))

SUPPORTED = {
    "emergency_surface_deny",
    "inject_allow",
    "remap_zone_tier",
    "suspend_rule",
}


def write_json(path: Path, obj) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def zone_files(data: Path) -> list[Path]:
    d = data / "zones"
    return sorted([p for p in d.glob("*.json") if p.is_file()])


def rule_files(data: Path) -> list[Path]:
    d = data / "rules"
    return sorted([p for p in d.glob("*.json") if p.is_file()])


pool = load_json(DATA / "pool_state.json")
current_day = int(pool["current_day"])
audit_version = str(pool["audit_version"])
weights = {k: int(v) for k, v in load_json(DATA / "policy" / "tier_weights.json")["weights"].items()}
implicit_pairs = load_json(DATA / "policy" / "implicit_matrix.json")["pairs"]

zones_dir = DATA / "zones"
catalog: dict[str, dict] = {}
for p in zone_files(DATA):
    row = load_json(p)
    zid = str(row["zone_id"])
    if zid in catalog:
        raise SystemExit(f"duplicate zone_id in fixtures: {zid}")
    catalog[zid] = {
        "declared_tier": str(row["zone_tier"]),
        "description": row.get("description", ""),
    }

zone_ids = sorted(catalog.keys())
tier_map = {z: catalog[z]["declared_tier"] for z in zone_ids}

baseline_rules: list[dict] = []
for p in rule_files(DATA):
    doc = load_json(p)
    for r in doc.get("rules", []):
        baseline_rules.append(dict(r))

baseline_rules.sort(key=lambda r: str(r["rule_id"]))


def zones_tokens(zs):
    if zs == ["*"]:
        return "*"
    return [str(x) for x in zs]


def rule_invalid(r: dict, zids: set[str]) -> bool:
    for tok in zones_tokens(r["src_zones"]):
        if tok != "*" and tok not in zids:
            return True
    for tok in zones_tokens(r["dst_zones"]):
        if tok != "*" and tok not in zids:
            return True
    return False


zset = set(zone_ids)
invalid_refs: list[str] = []
seen_invalid: set[str] = set()
for r in baseline_rules:
    if rule_invalid(r, zset):
        rid = str(r["rule_id"])
        if rid not in seen_invalid:
            seen_invalid.add(rid)
            invalid_refs.append(rid)
invalid_refs.sort()

suspended: set[str] = set()
synthetics: list[dict] = []
incidents = load_json(DATA / "incident_log.json")["incidents"]

ignored_incidents = 0
unsupported_kinds: set[str] = set()

eligible_incidents: list[dict] = []
for inc in incidents:
    acc = bool(inc.get("accepted", False))
    day = int(inc.get("day", -1))
    kind = str(inc.get("kind", ""))
    eid = str(inc.get("event_id", ""))
    if not acc or day > current_day or kind not in SUPPORTED:
        ignored_incidents += 1
        if acc and day <= current_day and kind not in SUPPORTED:
            unsupported_kinds.add(kind)
        continue
    eligible_incidents.append(inc)

eligible_incidents.sort(key=lambda i: (int(i["day"]), str(i["event_id"])))

for inc in eligible_incidents:
    kind = str(inc["kind"])
    eid = str(inc["event_id"])
    if kind == "suspend_rule":
        suspended.add(str(inc["rule_id"]))
    elif kind == "remap_zone_tier":
        zid = str(inc["zone_id"])
        if zid not in tier_map:
            raise SystemExit(f"remap for unknown zone {zid}")
        tier_map[zid] = str(inc["new_tier"])
    elif kind == "inject_allow":
        src = str(inc["src_zone"])
        dst = str(inc["dst_zone"])
        if src not in zset or dst not in zset:
            raise SystemExit(f"inject_allow unknown zone in {eid}")
        rid = f"inj__{eid}"
        synthetics.append(
            {
                "action": "allow",
                "audit_tier": str(inc["audit_tier"]),
                "dst_zones": [dst],
                "inject_kind": "inject_allow",
                "priority": int(inc["priority"]),
                "rule_id": rid,
                "src_zones": [src],
            }
        )
    elif kind == "emergency_surface_deny":
        dsts = [str(x) for x in inc["dst_zones"]]
        srcs = zones_tokens(inc["src_zones"])
        exempt = {str(x) for x in inc.get("exempt_src_zones", [])}
        for t in dsts:
            if t not in zset:
                raise SystemExit(f"emergency unknown dst {t}")
        if srcs != "*":
            for t in srcs:
                if t not in zset:
                    raise SystemExit(f"emergency unknown src {t}")
        for t in exempt:
            if t not in zset:
                raise SystemExit(f"emergency unknown exempt {t}")
        rid = f"surf__{eid}"
        synthetics.append(
            {
                "action": "deny",
                "audit_tier": str(inc["audit_tier"]),
                "dst_zones": dsts,
                "exempt_src_zones": sorted(exempt),
                "inject_kind": "emergency",
                "priority": int(inc["priority"]),
                "rule_id": rid,
                "src_zones": list(inc["src_zones"]),
            }
        )

active: list[dict] = []
base_ord = 0
for r in sorted(baseline_rules, key=lambda x: str(x["rule_id"])):
    rid = str(r["rule_id"])
    if rid in seen_invalid:
        continue
    if rid in suspended:
        continue
    rr = dict(r)
    rr["inject_kind"] = "baseline"
    rr["ordinal"] = base_ord
    base_ord += 1
    active.append(rr)

syn_ord = 0
for s in synthetics:
    ss = dict(s)
    ss["ordinal"] = syn_ord
    syn_ord += 1
    active.append(ss)

inject_rank = {"baseline": 0, "emergency": 1, "inject_allow": 2}


def cell_matches(rule: dict, src: str, dst: str) -> bool:
    kind = rule.get("inject_kind", "baseline")
    if kind == "emergency":
        if dst not in rule["dst_zones"]:
            return False
        if src in set(rule.get("exempt_src_zones", [])):
            return False
        sz = zones_tokens(rule["src_zones"])
        if sz == "*":
            return True
        return src in sz
    sz = zones_tokens(rule["src_zones"])
    dz = zones_tokens(rule["dst_zones"])
    sm = sz == "*" or src in sz
    dm = dz == "*" or dst in dz
    return sm and dm


def winner_tuple(rule: dict) -> tuple:
    ik = str(rule["inject_kind"])
    ir = inject_rank[ik]
    tw = int(weights[str(rule["audit_tier"])])
    np = -int(rule["priority"])
    ordn = int(rule["ordinal"])
    rid = str(rule["rule_id"])
    return (ir, tw, np, ordn, rid)


cells: list[dict] = []
allow_c = deny_c = 0
for src in zone_ids:
    for dst in zone_ids:
        matches = [r for r in active if cell_matches(r, src, dst)]
        if not matches:
            a = tier_map[src]
            b = tier_map[dst]
            key = f"{a}->{b}"
            verdict = str(implicit_pairs[key])
            cells.append(
                {
                    "dst_zone": dst,
                    "implicit_key": key,
                    "src_zone": src,
                    "verdict": verdict,
                    "via": "implicit",
                    "winning_rule_id": None,
                }
            )
        else:
            win = max(matches, key=winner_tuple)
            verdict = str(win["action"])
            cells.append(
                {
                    "dst_zone": dst,
                    "implicit_key": None,
                    "src_zone": src,
                    "verdict": verdict,
                    "via": "explicit",
                    "winning_rule_id": str(win["rule_id"]),
                }
            )
        if verdict == "allow":
            allow_c += 1
        else:
            deny_c += 1

zone_catalog = [
    {
        "declared_tier": catalog[z]["declared_tier"],
        "effective_tier": tier_map[z],
        "zone_id": z,
    }
    for z in zone_ids
]

prec_rows = []
for r in active:
    ik = str(r["inject_kind"])
    prec_rows.append(
        {
            "audit_tier": str(r["audit_tier"]),
            "inject_kind": ik,
            "ordinal": int(r["ordinal"]),
            "priority": int(r["priority"]),
            "rule_id": str(r["rule_id"]),
            "tier_weight": int(weights[str(r["audit_tier"])]),
        }
    )
prec_rows.sort(key=lambda x: x["rule_id"])

trace_events: list[dict] = []
for inc in sorted(incidents, key=lambda i: (int(i.get("day", -1)), str(i.get("event_id", "")))):
    acc = bool(inc.get("accepted", False))
    day = int(inc.get("day", -1))
    kind = str(inc.get("kind", ""))
    eid = str(inc.get("event_id", ""))
    eligible = acc and day <= current_day and kind in SUPPORTED
    applied = eligible
    trace_events.append(
        {
            "accepted": acc,
            "applied": applied,
            "day": day,
            "eligible": eligible,
            "event_id": eid,
            "kind": kind,
        }
    )

summary = {
    "audit_version": audit_version,
    "cell_count": len(cells),
    "current_day": current_day,
    "ignored_incidents": ignored_incidents,
    "invalid_rule_refs": list(invalid_refs),
    "unsupported_incident_kinds": sorted(unsupported_kinds),
    "verdict_counts": {"allow": allow_c, "deny": deny_c},
    "zone_count": len(zone_ids),
}

write_json(OUT / "zone_catalog.json", {"zones": zone_catalog})
write_json(OUT / "matrix_cells.json", {"cells": cells})
write_json(OUT / "precedence_table.json", {"rules": prec_rows})
write_json(OUT / "incident_trace.json", {"events": trace_events})
write_json(OUT / "summary.json", summary)
PYEOF
