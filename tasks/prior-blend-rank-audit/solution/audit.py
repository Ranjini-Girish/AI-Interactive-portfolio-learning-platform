"""Prior blend rank audit reference implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, sort_keys=True, indent=2, separators=(", ", ": ")) + "\n"
    path.write_text(txt, encoding="utf-8")


def _as_int(v: Any, default: int = 0) -> int:
    if isinstance(v, bool) or not isinstance(v, int):
        return default
    return int(v)


def run(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    layout = _load(data_dir / "domain_layout.json")
    anc_a = _load(data_dir / "anchors" / "a.json")
    anc_b = _load(data_dir / "anchors" / "b.json")

    active = {str(x) for x in policy["active_regions"]}
    blend_gamma = int(policy["blend_gamma"])
    lane_floor = int(policy["lane_floor"])
    witness_cap = int(policy["witness_cap"])
    quarantine_region = str(policy["quarantine_region"])

    anchor_weight = _as_int(layout.get("anchor_weight"), 0)
    bonus_a = _as_int(anc_a.get("bonus_a"), 0)
    bonus_b = _as_int(anc_b.get("bonus_b"), 0)
    anchor_bump = anchor_weight + bonus_a + bonus_b

    flags = pool.get("flags", {})
    compromised = bool(flags.get("experiment_compromised", False))
    holdout_breach = bool(flags.get("holdout_breach", False))
    budget = int(pool["budget"])

    lane_files = {}
    for p in sorted((data_dir / "lanes").glob("l*.json")):
        lane_obj = _load(p)
        code = str(lane_obj["lane_code"])
        lane_files[code] = int(lane_obj["witness_rank"])

    items: dict[str, dict[str, Any]] = {}
    for p in sorted((data_dir / "items").glob("item_*.json")):
        it = _load(p)
        items[str(it["item_id"])] = dict(it)

    working: dict[str, dict[str, Any]] = {}
    for iid, it in items.items():
        if str(it["region"]) in active:
            working[iid] = dict(it)

    events = list(incidents.get("events", []))
    applied = len(events)

    for ev in events:
        kind = str(ev.get("kind", ""))
        if kind == "prior_boost":
            iid = str(ev["item_id"])
            if iid in working:
                it = working[iid]
                it["prior_a"] = int(it["prior_a"]) + int(ev["delta_a"])
                it["prior_b"] = int(it["prior_b"]) + int(ev["delta_b"])
                it["prior_a"] = max(1, int(it["prior_a"]))
                it["prior_b"] = max(1, int(it["prior_b"]))
        elif kind == "lane_witness_nudge":
            code = str(ev["lane_code"])
            if code in lane_files:
                lane_files[code] = max(0, lane_files[code] + int(ev["delta"]))
                lane_files[code] = min(lane_files[code], witness_cap)
        elif kind == "drop_item":
            iid = str(ev["item_id"])
            working.pop(iid, None)

    if holdout_breach:
        for iid in list(working.keys()):
            if str(working[iid]["region"]) == quarantine_region:
                working.pop(iid, None)

    for it in working.values():
        it["prior_a"] = max(1, int(it["prior_a"]) + anchor_bump)

    rows: list[dict[str, Any]] = []
    scores: dict[str, int] = {}

    for iid in sorted(working.keys()):
        it = working[iid]
        pa = int(it["prior_a"])
        pb = int(it["prior_b"])
        s = (1000 * pa) // (pa + pb)
        w_raw = int(lane_files[str(it["lane_code"])])
        w = min(w_raw, witness_cap)
        if compromised:
            w = 0
        b = (blend_gamma * s + (1000 - blend_gamma) * w) // 1000
        b = max(b, lane_floor)
        wt = int(it["weight"])
        score = b * wt
        scores[iid] = score
        rows.append(
            {
                "item_id": iid,
                "lane_code": str(it["lane_code"]),
                "region": str(it["region"]),
                "prior_a": pa,
                "prior_b": pb,
                "witness_used": w,
                "score": score,
                "allocated": 0,
            }
        )

    total_score = sum(scores.values())
    alloc_map = {r["item_id"]: 0 for r in rows}
    if not rows or total_score <= 0:
        unallocated = budget
    else:
        used = 0
        rem_info: list[tuple[int, str]] = []
        for iid in sorted(working.keys()):
            sc = scores[iid]
            q = (budget * sc) // total_score
            r = (budget * sc) % total_score
            alloc_map[iid] = q
            used += q
            rem_info.append((r, iid))
        rem = budget - used
        rem_info.sort(key=lambda t: (-t[0], t[1]))
        for idx in range(rem):
            iid = rem_info[idx][1]
            alloc_map[iid] += 1
        unallocated = budget - sum(alloc_map.values())

    for r in rows:
        r["allocated"] = int(alloc_map[r["item_id"]])

    rows.sort(key=lambda r: str(r["item_id"]))

    regions: dict[str, int] = {}
    for r in rows:
        reg = str(r["region"])
        regions[reg] = regions.get(reg, 0) + int(r["allocated"])

    summary = {
        "applied_events": applied,
        "survivors": len(rows),
        "unallocated": int(unallocated),
        "regions": dict(sorted(regions.items(), key=lambda kv: kv[0])),
    }

    out_alloc = {"allocations": rows}
    _dump(audit_dir / "allocation_table.json", out_alloc)
    _dump(audit_dir / "summary.json", summary)


def main() -> None:
    import os

    data_dir = Path(os.environ.get("PBR_DATA_DIR", "/app/pbr_lab"))
    audit_dir = Path(os.environ.get("PBR_AUDIT_DIR", "/app/audit"))
    run(data_dir, audit_dir)


if __name__ == "__main__":
    main()
