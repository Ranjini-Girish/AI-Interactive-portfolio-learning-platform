#!/bin/bash
set -euo pipefail

mkdir -p "${CST_TRIAGE_DIR:-/app/triage}"

python3 - <<'PYEOF'
import json
import os
import re
from pathlib import Path

DATA = Path(os.environ.get("CST_DATA_DIR", "/app/dumps"))
OUT = Path(os.environ.get("CST_TRIAGE_DIR", "/app/triage"))

HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPRO_VALUES = ("always", "intermittent", "once")
SEVERITY_VALUES = ("low", "medium", "high", "critical")


def write_json(path: Path, obj) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.write("\n")


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def is_nonempty_string(x) -> bool:
    return isinstance(x, str) and len(x) > 0


def is_int_in(x, lo, hi=None) -> bool:
    if isinstance(x, bool):
        return False
    if not isinstance(x, int):
        return False
    if x < lo:
        return False
    if hi is not None and x > hi:
        return False
    return True


pool_state = load_json(DATA / "pool_state.json")
triage_config = load_json(DATA / "triage_config.json")
module_map = load_json(DATA / "module_map.json")
incident_log = load_json(DATA / "incident_log.json")

current_day = pool_state["current_day"]
triage_version = pool_state["triage_version"]
escalation_threshold = triage_config["cluster_size_escalation_threshold"]
default_owner_team = triage_config["default_owner_team"]
severity_order = triage_config["severity_order"]
severity_rank = {s: i for i, s in enumerate(severity_order)}


def load_dir(subdir: str):
    p = DATA / subdir
    out = []
    if not p.is_dir():
        return out
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix == ".json":
            out.append(load_json(f))
    return out


raw_releases = load_dir("releases")
raw_crashes = load_dir("crashes")


def validate_release(r) -> bool:
    if not is_nonempty_string(r.get("version")):
        return False
    if not is_int_in(r.get("day"), 0, current_day):
        return False
    h = r.get("diff_hash")
    if not (is_nonempty_string(h) and HEX64.fullmatch(h)):
        return False
    if not is_nonempty_string(r.get("owner_team")):
        return False
    return True


valid_releases = [r for r in raw_releases if validate_release(r)]
invalid_releases_dropped = len(raw_releases) - len(valid_releases)
releases_by_version = {r["version"]: r for r in valid_releases}


def validate_crash(c) -> bool:
    if not is_nonempty_string(c.get("id")):
        return False
    if not is_int_in(c.get("reported_day"), 0, current_day):
        return False
    if not is_nonempty_string(c.get("reporter")):
        return False
    frames = c.get("frame_stack")
    if not isinstance(frames, list) or len(frames) == 0:
        return False
    for f in frames:
        if not is_nonempty_string(f):
            return False
    h = c.get("env_hash")
    if not (is_nonempty_string(h) and HEX64.fullmatch(h)):
        return False
    if c.get("reproducibility") not in REPRO_VALUES:
        return False
    if c.get("severity_observed") not in SEVERITY_VALUES:
        return False
    return True


valid_crashes = [c for c in raw_crashes if validate_crash(c)]
invalid_crashes_dropped = len(raw_crashes) - len(valid_crashes)


def canonical_signature(frames):
    if len(frames) >= 4:
        combined = list(frames[:3]) + [frames[-1]]
    else:
        combined = list(frames)
    seen = set()
    deduped = []
    for f in combined:
        if f not in seen:
            seen.add(f)
            deduped.append(f)
    return "|".join(deduped)


initial_cluster_for_crash = {}
initial_clusters = {}
for c in valid_crashes:
    sig = canonical_signature(c["frame_stack"])
    initial_cluster_for_crash[c["id"]] = sig
    initial_clusters.setdefault(sig, []).append(c["id"])


ignored_incident_events = 0
pending_merges = []
pending_reassigns = []
accepted_poisoned_builds = []
for ev in incident_log.get("events", []):
    if not isinstance(ev, dict):
        ignored_incident_events += 1
        continue
    kind = ev.get("kind")
    day = ev.get("day")
    if kind not in ("poisoned_build", "owner_reassign", "cluster_merge"):
        ignored_incident_events += 1
        continue
    if not is_int_in(day, 0, current_day):
        ignored_incident_events += 1
        continue
    if kind == "poisoned_build":
        h = ev.get("diff_hash")
        reason = ev.get("reason")
        if not (is_nonempty_string(h) and HEX64.fullmatch(h)):
            ignored_incident_events += 1
            continue
        if not is_nonempty_string(reason):
            ignored_incident_events += 1
            continue
        accepted_poisoned_builds.append(ev)
    elif kind == "owner_reassign":
        ev_id = ev.get("event_id")
        sig = ev.get("signature")
        new_owner = ev.get("new_owner_team")
        if not (is_nonempty_string(ev_id) and is_nonempty_string(sig) and is_nonempty_string(new_owner)):
            ignored_incident_events += 1
            continue
        if sig not in initial_clusters:
            ignored_incident_events += 1
            continue
        pending_reassigns.append(ev)
    elif kind == "cluster_merge":
        ev_id = ev.get("event_id")
        src = ev.get("source_signature")
        tgt = ev.get("target_signature")
        if not (is_nonempty_string(ev_id) and is_nonempty_string(src) and is_nonempty_string(tgt)):
            ignored_incident_events += 1
            continue
        if src == tgt:
            ignored_incident_events += 1
            continue
        if src not in initial_clusters or tgt not in initial_clusters:
            ignored_incident_events += 1
            continue
        pending_merges.append(ev)


current_clusters = {sig: {"crashes": list(crashes), "merged_from": []}
                    for sig, crashes in initial_clusters.items()}

merged_clusters_count = 0
pending_merges.sort(key=lambda e: (e["day"], e["event_id"]))
for ev in pending_merges:
    src = ev["source_signature"]
    tgt = ev["target_signature"]
    if src not in current_clusters or tgt not in current_clusters:
        ignored_incident_events += 1
        continue
    if src == tgt:
        ignored_incident_events += 1
        continue
    current_clusters[tgt]["crashes"].extend(current_clusters[src]["crashes"])
    current_clusters[tgt]["merged_from"].append(src)
    current_clusters[tgt]["merged_from"].extend(current_clusters[src]["merged_from"])
    del current_clusters[src]
    merged_clusters_count += 1

for sig in current_clusters:
    current_clusters[sig]["merged_from"] = sorted(set(current_clusters[sig]["merged_from"]))


valid_reassigns = []
for ev in pending_reassigns:
    if ev["signature"] in current_clusters:
        valid_reassigns.append(ev)
    else:
        ignored_incident_events += 1


crash_by_id = {c["id"]: c for c in valid_crashes}


def first_frame_of_signature(sig: str) -> str:
    idx = sig.find("|")
    return sig if idx == -1 else sig[:idx]


def attributed_release_for(first_seen_day: int):
    candidates = [r for r in valid_releases if r["day"] >= first_seen_day]
    if not candidates:
        return None
    candidates.sort(key=lambda r: (r["day"], r["version"]))
    return candidates[0]


def module_match(first_frame: str):
    matches = [m for m in module_map["modules"] if first_frame.startswith(m["frame_prefix"])]
    if not matches:
        return None
    matches.sort(key=lambda m: (-len(m["frame_prefix"]), m["frame_prefix"]))
    return matches[0]


cluster_records = {}
for sig, info in current_clusters.items():
    crash_ids = info["crashes"]
    crashes = [crash_by_id[cid] for cid in crash_ids]
    first_seen = min(c["reported_day"] for c in crashes)
    last_seen = max(c["reported_day"] for c in crashes)
    observed = max((c["severity_observed"] for c in crashes), key=lambda s: severity_rank[s])
    has_always = any(c["reproducibility"] == "always" for c in crashes)
    size = len(crashes)
    attributed = attributed_release_for(first_seen)
    cluster_records[sig] = {
        "signature": sig,
        "crashes": sorted(crash_ids),
        "first_seen_day": first_seen,
        "last_seen_day": last_seen,
        "merged_from": info["merged_from"],
        "size": size,
        "observed_severity": observed,
        "has_always": has_always,
        "attributed": attributed,
        "first_frame": first_frame_of_signature(sig),
    }


poisoned_diff_hashes = {ev["diff_hash"] for ev in accepted_poisoned_builds}
poisoned_clusters_set = {
    sig for sig, rec in cluster_records.items()
    if rec["attributed"] is not None and rec["attributed"]["diff_hash"] in poisoned_diff_hashes
}


reassigns_by_sig = {}
for ev in valid_reassigns:
    reassigns_by_sig.setdefault(ev["signature"], []).append(ev)


cluster_index_out = []
attribution_out = []
severity_out = []
owner_out = []

assignment_reason_counts = {
    "module_match": 0, "release_default": 0, "owner_reassign": 0,
    "poisoned_build_override": 0, "default_owner": 0,
}
attribution_note_counts = {"release_match": 0, "unattributed": 0, "poisoned_build": 0}
severity_counts = {s: 0 for s in SEVERITY_VALUES}

for sig in sorted(cluster_records):
    rec = cluster_records[sig]
    cluster_index_out.append({
        "signature": sig,
        "crashes": rec["crashes"],
        "first_seen_day": rec["first_seen_day"],
        "last_seen_day": rec["last_seen_day"],
        "merged_from": rec["merged_from"],
    })

    attr = rec["attributed"]
    if sig in poisoned_clusters_set:
        note = "poisoned_build"
        attributed_version = attr["version"]
        attributed_hash = attr["diff_hash"]
    elif attr is None:
        note = "unattributed"
        attributed_version = None
        attributed_hash = None
    else:
        note = "release_match"
        attributed_version = attr["version"]
        attributed_hash = attr["diff_hash"]
    attribution_out.append({
        "signature": sig,
        "attributed_release": attributed_version,
        "attributed_diff_hash": attributed_hash,
        "attribution_note": note,
    })
    attribution_note_counts[note] += 1

    if sig in poisoned_clusters_set:
        computed = "critical"
        sev_reason = "escalated_poisoned_build"
    elif rec["has_always"]:
        computed = "critical"
        sev_reason = "escalated_reproducibility_always"
    elif rec["size"] >= escalation_threshold:
        computed = "critical"
        sev_reason = f"escalated_cluster_size_{rec['size']}"
    else:
        computed = rec["observed_severity"]
        sev_reason = f"max_observed_{computed}"
    severity_out.append({
        "signature": sig,
        "observed_severity": rec["observed_severity"],
        "computed_severity": computed,
        "severity_reason": sev_reason,
    })
    severity_counts[computed] += 1

    if sig in poisoned_clusters_set:
        owner_team = "release-engineering"
        owner_reason = "poisoned_build_override"
    elif sig in reassigns_by_sig:
        events = sorted(reassigns_by_sig[sig], key=lambda e: (-e["day"], e["event_id"]))
        owner_team = events[0]["new_owner_team"]
        owner_reason = "owner_reassign"
    else:
        mm = module_match(rec["first_frame"])
        if mm is not None:
            owner_team = mm["owner_team"]
            owner_reason = "module_match"
        elif attr is not None:
            owner_team = attr["owner_team"]
            owner_reason = "release_default"
        else:
            owner_team = default_owner_team
            owner_reason = "default_owner"
    owner_out.append({
        "signature": sig,
        "assigned_owner_team": owner_team,
        "assignment_reason": owner_reason,
    })
    assignment_reason_counts[owner_reason] += 1


summary_out = {
    "current_day": current_day,
    "triage_version": triage_version,
    "totals": {
        "crashes": len(valid_crashes),
        "clusters": len(cluster_records),
        "releases": len(valid_releases),
        "invalid_crashes_dropped": invalid_crashes_dropped,
        "invalid_releases_dropped": invalid_releases_dropped,
        "ignored_incident_events": ignored_incident_events,
        "merged_clusters": merged_clusters_count,
    },
    "by_severity": severity_counts,
    "by_attribution_note": attribution_note_counts,
    "by_assignment_reason": assignment_reason_counts,
    "poisoned_clusters": sorted(poisoned_clusters_set),
}


write_json(OUT / "cluster_index.json", {"clusters": cluster_index_out})
write_json(OUT / "attribution_report.json", {"clusters": attribution_out})
write_json(OUT / "severity_ranking.json", {"clusters": severity_out})
write_json(OUT / "owner_assignment.json", {"clusters": owner_out})
write_json(OUT / "summary.json", summary_out)
PYEOF
