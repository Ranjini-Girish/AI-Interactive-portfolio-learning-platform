#!/bin/bash
set -euo pipefail

python3 <<'PYEOF'
import json
import os
import re
from collections import Counter
from pathlib import Path

DATA = Path(os.environ.get("NMB_DATA_DIR", "/app/monorepo"))
OUT = Path(os.environ.get("NMB_ARB_DIR", "/app/arbitration"))
OUT.mkdir(parents=True, exist_ok=True)


def write_json(path, payload):
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    Path(path).write_text(text, encoding="utf-8")


def parse_version(s):
    parts = s.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def fmt_version(v):
    return f"{v[0]}.{v[1]}.{v[2]}"


def parse_range(s):
    s = s.strip()
    if s.startswith("^"):
        v = parse_version(s[1:])
        if v[0] >= 1:
            return (v, (v[0] + 1, 0, 0))
        if v[1] > 0:
            return (v, (0, v[1] + 1, 0))
        return (v, (0, 0, v[2] + 1))
    if s.startswith("~"):
        v = parse_version(s[1:])
        return (v, (v[0], v[1] + 1, 0))
    if s.startswith(">="):
        m = re.match(r"^>=(\d+\.\d+\.\d+) <(\d+\.\d+\.\d+)$", s)
        if not m:
            raise ValueError(f"invalid range {s}")
        return (parse_version(m.group(1)), parse_version(m.group(2)))
    v = parse_version(s)
    return (v, (v[0], v[1], v[2] + 1))


def version_in_range(v, rng):
    lo, hi = rng
    return lo <= v < hi


def range_superset(outer, inner):
    return outer[0] <= inner[0] and outer[1] >= inner[1]


def range_intersection(a, b):
    lo = max(a[0], b[0])
    hi = min(a[1], b[1])
    if lo >= hi:
        return None
    return (lo, hi)


def range_to_str(rng):
    return f">={fmt_version(rng[0])} <{fmt_version(rng[1])}"


def componentwise_diff(a, b):
    return (max(a[0] - b[0], 0), max(a[1] - b[1], 0), max(a[2] - b[2], 0))


SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

manifest = json.loads((DATA / "monorepo_manifest.json").read_text(encoding="utf-8"))
policy = json.loads((DATA / "governance" / "policy.json").read_text(encoding="utf-8"))
lock = json.loads((DATA / "current_lock.json").read_text(encoding="utf-8"))["locks"]
incident_log = json.loads((DATA / "incident_log.json").read_text(encoding="utf-8"))["events"]
pool = json.loads((DATA / "pool_state.json").read_text(encoding="utf-8"))
advisories = json.loads((DATA / "advisories.json").read_text(encoding="utf-8"))["advisories"]

current_day = pool["current_day"]
ws_engines = parse_range(policy["engines_node_workspace"])
sev_thresh = SEV_RANK[manifest["severity_block_threshold"]]
allow_yanked = manifest["allow_yanked_pinned"]

packages = {}
for p in sorted((DATA / "packages").glob("*.json")):
    d = json.loads(p.read_text(encoding="utf-8"))
    packages[d["name"]] = d

registry = {}
for r in sorted((DATA / "registry").glob("*.json")):
    d = json.loads(r.read_text(encoding="utf-8"))
    registry[d["name"]] = d


ALLOWED_KINDS = {"force_freeze", "dist_tag_pin", "advisory_override"}
filtered = []
ignored = 0
for ev in incident_log:
    if not ev.get("accepted", False):
        ignored += 1
        continue
    if ev["day"] > current_day:
        ignored += 1
        continue
    if ev["kind"] not in ALLOWED_KINDS:
        ignored += 1
        continue
    filtered.append(ev)


def scope_key(ev):
    k = ev["kind"]
    if k == "force_freeze":
        return (k, ev["dep"])
    if k == "dist_tag_pin":
        return (k, ev["dep"])
    return (k, ev["advisory_id"])


groups = {}
for ev in filtered:
    groups.setdefault(scope_key(ev), []).append(ev)

accepted_events = {}
for key, evs in groups.items():
    evs.sort(key=lambda e: (-e["day"], e["event_id"]))
    accepted_events[key] = evs[0]

force_freezes = {k[1]: v for k, v in accepted_events.items() if k[0] == "force_freeze"}
dist_tag_pins = {k[1]: v for k, v in accepted_events.items() if k[0] == "dist_tag_pin"}
override_ids = {k[1] for k in accepted_events.keys() if k[0] == "advisory_override"}


def adv_active(adv):
    if adv["advisory_id"] in override_ids:
        return False
    if SEV_RANK[adv["severity"]] < sev_thresh:
        return False
    return True


advs_by_dep = {}
for a in advisories:
    advs_by_dep.setdefault(a["dep"], []).append(a)


def adv_blockers_for_version(dep, v_tuple):
    blockers = []
    for adv in advs_by_dep.get(dep, []):
        if not adv_active(adv):
            continue
        if version_in_range(v_tuple, parse_range(adv["vulnerable_range"])):
            blockers.append(adv["advisory_id"])
    return blockers


def eligible_versions(dep, rng):
    out = []
    reg = registry.get(dep)
    if reg is None:
        return out
    for v in reg["versions"]:
        v_t = parse_version(v["version"])
        if not version_in_range(v_t, rng):
            continue
        if not range_superset(parse_range(v["engines_node"]), ws_engines):
            continue
        if v["yanked"]:
            if not (allow_yanked and lock.get(dep) == v["version"]):
                continue
        if adv_blockers_for_version(dep, v_t):
            continue
        out.append(v)
    return out


def collect_deps(pkg):
    items = []
    for dep, info in pkg.get("dependencies", {}).items():
        items.append((dep, info))
    for dep, info in pkg.get("dev_dependencies", {}).items():
        items.append((dep, info))
    return items


def supports_all(v_info, conditions):
    return all(c in v_info["exports_conditions"] for c in conditions)


entries = []
freeze_unsafe_against = {}
block_pin_against = {}

for pkg_name in sorted(packages.keys()):
    pkg = packages[pkg_name]
    for dep, info in sorted(collect_deps(pkg)):
        rng_str = info["range"]
        exports_used = list(info["exports_used"])
        scope = info["scope"]
        entry = {
            "package": pkg_name,
            "dep": dep,
            "scope": scope,
            "current_version": lock.get(dep),
            "exports_dropped_set": [],
        }
        if rng_str.startswith("workspace:"):
            entry["resolution_kind"] = "workspace_protocol"
            variant_tok = rng_str.split(":", 1)[1]
            entry["protocol_variant"] = {"*": "star", "^": "caret", "~": "tilde"}.get(variant_tok)
            entry["source"] = "planner"
            if dep in packages:
                chosen = packages[dep]["version"]
                entry["chosen_version"] = chosen
                cv = entry["current_version"]
                if cv is None or chosen == cv:
                    entry["action"] = "hold"
                elif parse_version(chosen) > parse_version(cv):
                    entry["action"] = "bump"
                else:
                    entry["action"] = "downgrade"
                entry["reason"] = "satisfied"
            else:
                entry["chosen_version"] = None
                entry["action"] = "block_no_workspace_target"
                entry["reason"] = "no_workspace_target"
            entries.append(entry)
            continue

        entry["resolution_kind"] = "registry"
        entry["protocol_variant"] = None

        if dep in force_freezes:
            entry["source"] = "incident_log_force_freeze"
            locked = lock.get(dep)
            reg = registry.get(dep, {})
            v_info = next((v for v in reg.get("versions", []) if v["version"] == locked), None)
            if locked is None or v_info is None:
                entry["chosen_version"] = None
                entry["action"] = "block_no_eligible_version"
                entry["reason"] = "no_eligible_version"
                entries.append(entry)
                continue
            entry["chosen_version"] = locked
            yank_ok = (not v_info["yanked"]) or allow_yanked
            blockers = adv_blockers_for_version(dep, parse_version(locked))
            if (not yank_ok) or blockers:
                entry["action"] = "freeze_unsafe"
                entry["reason"] = "freeze_advisory_conflict"
                for b in blockers:
                    freeze_unsafe_against.setdefault(b, []).append((pkg_name, dep))
            else:
                entry["action"] = "freeze"
                entry["reason"] = "satisfied"
            entries.append(entry)
            continue

        if dep in dist_tag_pins:
            entry["source"] = "incident_log_dist_tag_pin"
            ev = dist_tag_pins[dep]
            reg = registry.get(dep, {})
            target = reg.get("dist_tags", {}).get(ev["dist_tag"])
            v_info = next((v for v in reg.get("versions", []) if v["version"] == target), None)
            if target is None or v_info is None:
                entry["chosen_version"] = None
                entry["action"] = "block_dist_tag_unsafe"
                entry["reason"] = "dist_tag_unsafe"
                entries.append(entry)
                continue
            t_t = parse_version(target)
            engines_ok = range_superset(parse_range(v_info["engines_node"]), ws_engines)
            yanked_ok = (not v_info["yanked"]) or (allow_yanked and lock.get(dep) == target)
            blockers = adv_blockers_for_version(dep, t_t)
            if not (engines_ok and yanked_ok and not blockers):
                entry["chosen_version"] = None
                entry["action"] = "block_dist_tag_unsafe"
                entry["reason"] = "dist_tag_unsafe"
                for b in blockers:
                    block_pin_against.setdefault(b, []).append((pkg_name, dep))
            else:
                entry["chosen_version"] = target
                entry["action"] = "dist_tag_pin"
                entry["reason"] = "satisfied"
            entries.append(entry)
            continue

        entry["source"] = "planner"
        entry_rng = parse_range(rng_str)
        elig = eligible_versions(dep, entry_rng)
        if not elig:
            entry["chosen_version"] = None
            entry["action"] = "block_no_eligible_version"
            entry["reason"] = "no_eligible_version"
            entries.append(entry)
            continue
        elig.sort(key=lambda v: parse_version(v["version"]), reverse=True)
        v_max = elig[0]
        chosen = None
        dropped = []
        if supports_all(v_max, exports_used):
            chosen = v_max
        else:
            for v in elig:
                if supports_all(v, exports_used):
                    chosen = v
                    break
            if chosen is None:
                drop_pool = sorted(c for c in exports_used if c not in v_max["exports_conditions"])
                for c in drop_pool:
                    dropped.append(c)
                    remaining = [x for x in exports_used if x not in dropped]
                    for v in elig:
                        if supports_all(v, remaining):
                            chosen = v
                            break
                    if chosen is not None:
                        break
                if chosen is None:
                    chosen = v_max
                    dropped = sorted(exports_used)
        entry["chosen_version"] = chosen["version"]
        entry["exports_dropped_set"] = sorted(dropped)
        cv = entry["current_version"]
        if cv is None or chosen["version"] == cv:
            entry["action"] = "hold"
        elif parse_version(chosen["version"]) > parse_version(cv):
            entry["action"] = "bump"
        else:
            entry["action"] = "downgrade"
        entry["reason"] = "exports_downgrade" if dropped else "satisfied"
        entries.append(entry)

entries.sort(key=lambda e: (e["package"], e["dep"]))
write_json(OUT / "bump_decisions.json", {"entries": entries})


peer_buckets = {}
for e in entries:
    if e["chosen_version"] is None:
        continue
    if e["resolution_kind"] != "registry":
        continue
    v_info = next(
        (v for v in registry[e["dep"]]["versions"] if v["version"] == e["chosen_version"]),
        None,
    )
    if v_info is None:
        continue
    for peer_name, declared in v_info.get("peer_constraints", {}).items():
        peer_buckets.setdefault(peer_name, []).append(
            {
                "declared_range": declared,
                "dep_chain": f"{e['package']}::{e['dep']}",
                "package": e["package"],
            }
        )


def resolve_peer(peer_name):
    cands = []
    for e in entries:
        if e["dep"] != peer_name:
            continue
        if e["chosen_version"] is None:
            continue
        cands.append(parse_version(e["chosen_version"]))
    if not cands:
        return None
    return fmt_version(max(cands))


peer_links = []
for peer_name in sorted(peer_buckets.keys()):
    consumers = sorted(
        peer_buckets[peer_name], key=lambda c: (c["package"], c["dep_chain"])
    )
    intersection = None
    for c in consumers:
        rng = parse_range(c["declared_range"])
        intersection = rng if intersection is None else range_intersection(intersection, rng)
        if intersection is None:
            break
    resolved = resolve_peer(peer_name)
    if intersection is None:
        status = "unsatisfiable_intersection"
        intersection_str = None
    elif resolved is None:
        status = "peer_unresolved"
        intersection_str = range_to_str(intersection)
    elif version_in_range(parse_version(resolved), intersection):
        status = "satisfied"
        intersection_str = range_to_str(intersection)
    else:
        status = "outside_intersection"
        intersection_str = range_to_str(intersection)
    peer_links.append(
        {
            "consumers": consumers,
            "intersection_range": intersection_str,
            "peer_name": peer_name,
            "peer_status": status,
            "resolved_peer_version": resolved,
        }
    )

write_json(OUT / "peer_satisfaction_report.json", {"peer_links": peer_links})


def engines_blocked_count(pkg):
    seen = set()
    for dep, info in collect_deps(pkg):
        if info["range"].startswith("workspace:"):
            continue
        if dep not in registry:
            continue
        rng = parse_range(info["range"])
        for v in registry[dep]["versions"]:
            v_t = parse_version(v["version"])
            if not version_in_range(v_t, rng):
                continue
            if v["yanked"] and not (allow_yanked and lock.get(dep) == v["version"]):
                continue
            if adv_blockers_for_version(dep, v_t):
                continue
            if not range_superset(parse_range(v["engines_node"]), ws_engines):
                seen.add((dep, v["version"]))
    return len(seen)


eng_pkgs = []
for pkg_name in sorted(packages.keys()):
    pkg = packages[pkg_name]
    pe = parse_range(pkg["engines_node"])
    lo_violated = pe[0] < ws_engines[0]
    up_violated = pe[1] > ws_engines[1]
    if lo_violated and up_violated:
        status = "both_violated"
    elif lo_violated:
        status = "lower_violated"
    elif up_violated:
        status = "upper_violated"
    else:
        status = "subrange"
    lo_ex = componentwise_diff(ws_engines[0], pe[0]) if lo_violated else (0, 0, 0)
    up_ex = componentwise_diff(pe[1], ws_engines[1]) if up_violated else (0, 0, 0)
    eng_pkgs.append(
        {
            "engines_blocked_versions_count": engines_blocked_count(pkg),
            "lower_exceeded_by": fmt_version(lo_ex),
            "package": pkg_name,
            "package_engines_lower": fmt_version(pe[0]),
            "package_engines_status": status,
            "package_engines_upper": fmt_version(pe[1]),
            "upper_exceeded_by": fmt_version(up_ex),
        }
    )

write_json(
    OUT / "engines_compatibility.json",
    {
        "engines_node_workspace_lower": fmt_version(ws_engines[0]),
        "engines_node_workspace_upper": fmt_version(ws_engines[1]),
        "packages": eng_pkgs,
    },
)


advisory_rows = []
MITIGATION_MAP = {
    "resolved_by_bump": "bump",
    "mitigated_by_exports_drop": "exports_drop",
    "still_open_frozen": "frozen",
    "unmitigated_pinned": "pinned",
    "overridden": "override",
    "inactive_low_severity": None,
    "still_open": None,
}

for adv in sorted(advisories, key=lambda a: a["advisory_id"]):
    aid = adv["advisory_id"]
    dep = adv["dep"]
    sev = adv["severity"]
    vuln_rng = parse_range(adv["vulnerable_range"])
    patched_rng = parse_range(adv["patched_range"])
    if aid in override_ids:
        status = "overridden"
    elif SEV_RANK[sev] < sev_thresh:
        status = "inactive_low_severity"
    elif aid in freeze_unsafe_against:
        status = "still_open_frozen"
    elif aid in block_pin_against:
        status = "unmitigated_pinned"
    else:
        consuming = [e for e in entries if e["dep"] == dep]
        mitigated = False
        for e in consuming:
            if e["chosen_version"] is None or not e["exports_dropped_set"]:
                continue
            ct = parse_version(e["chosen_version"])
            if not version_in_range(ct, vuln_rng) and version_in_range(ct, patched_rng):
                mitigated = True
                break
        if mitigated:
            status = "mitigated_by_exports_drop"
        else:
            all_ok = len(consuming) > 0 and all(
                e["chosen_version"] is not None
                and not version_in_range(parse_version(e["chosen_version"]), vuln_rng)
                and version_in_range(parse_version(e["chosen_version"]), patched_rng)
                for e in consuming
            )
            status = "resolved_by_bump" if all_ok else "still_open"
    patched_vs = set()
    for e in entries:
        if e["dep"] != dep or e["chosen_version"] is None:
            continue
        if version_in_range(parse_version(e["chosen_version"]), patched_rng):
            patched_vs.add(e["chosen_version"])
    patched_versions = sorted(patched_vs, key=parse_version)
    advisory_rows.append(
        {
            "advisory_id": aid,
            "day_published": adv["day_published"],
            "dep": dep,
            "mitigation_method": MITIGATION_MAP[status],
            "patched_versions": patched_versions,
            "severity": sev,
            "status": status,
        }
    )

write_json(OUT / "advisory_status.json", {"advisories": advisory_rows})


action_counts = dict(Counter(e["action"] for e in entries))
resolution_kind_counts = dict(Counter(e["resolution_kind"] for e in entries))
peer_status_counts = dict(Counter(p["peer_status"] for p in peer_links))
advisory_counts = dict(Counter(a["status"] for a in advisory_rows))

drift_deps = set()
for e in entries:
    if e["chosen_version"] is None:
        continue
    lv = lock.get(e["dep"])
    if lv is None or e["chosen_version"] != lv:
        drift_deps.add(e["dep"])

summary = {
    "action_counts": dict(sorted(action_counts.items())),
    "advisory_counts": dict(sorted(advisory_counts.items())),
    "engines_blocked_versions_total": sum(p["engines_blocked_versions_count"] for p in eng_pkgs),
    "engines_node_workspace_lower": fmt_version(ws_engines[0]),
    "engines_node_workspace_upper": fmt_version(ws_engines[1]),
    "ignored_incident_events": ignored,
    "lockfile_drift_count": len(drift_deps),
    "peer_status_counts": dict(sorted(peer_status_counts.items())),
    "resolution_kind_counts": dict(sorted(resolution_kind_counts.items())),
    "total_entries": len(entries),
    "total_external_deps": len(registry),
    "total_packages": len(packages),
}
write_json(OUT / "summary.json", summary)
PYEOF
