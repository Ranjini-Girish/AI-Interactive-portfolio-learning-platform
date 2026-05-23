"""Rotating lane cap audit reference implementation."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, sort_keys=True, indent=2, separators=(", ", ": ")) + "\n"
    path.write_text(txt, encoding="utf-8")


def _rot_k(x: int, y: int, k: int) -> tuple[int, int]:
    xr, yr = x, y
    for _ in range(k % 4):
        xr, yr = -yr, xr
    return xr, yr


def run(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    anc_x = _load(data_dir / "ancillary" / "x.json")

    active = set(str(x) for x in policy["active_regions"])
    lanes_cfg: dict[str, Any] = {k: dict(v) for k, v in policy["lanes"].items()}
    lane_floor = int(policy["lane_floor"])
    mingle_penalty = int(policy["mingle_penalty"])

    items: dict[str, dict[str, Any]] = {}
    for i in range(12):
        it = _load(data_dir / "items" / f"item_{i:02d}.json")
        items[str(it["item_id"])] = dict(it)

    working = {iid: dict(it) for iid, it in items.items() if str(it["region"]) in active}

    events = list(incidents.get("events", []))
    applied = 0
    for ev in events:
        applied += 1
        kind = str(ev.get("kind", ""))
        if kind == "tier_period_bump":
            tier = str(ev["tier"])
            add = int(ev["add"])
            for it in working.values():
                if str(it["tier"]) == tier:
                    it["rotate_period_days"] = max(1, int(it["rotate_period_days"]) + add)
        elif kind == "lane_cap_rescale":
            lid = str(ev["lane_id"])
            if lid in lanes_cfg:
                lanes_cfg[lid]["cap"] = int(ev["new_cap"])
        elif kind == "item_excise":
            iid = str(ev["item_id"])
            working.pop(iid, None)

    D = int(pool["current_day"])

    def contrib(it: dict[str, Any]) -> int:
        B = int(it["born_day"])
        P = int(it["rotate_period_days"])
        if D < B:
            k = 0
        else:
            k = ((D - B) // P) % 4
        xr, yr = _rot_k(int(it["x"]), int(it["y"]), k)
        return max(lane_floor, abs(xr) + abs(yr))

    lane_ids = sorted(lanes_cfg.keys())
    rows: list[dict[str, Any]] = []
    alloc_all: dict[str, int] = {iid: 0 for iid in working}

    for lid in lane_ids:
        ldef = lanes_cfg[lid]
        members = [str(m) for m in ldef["members"]]
        contribs = {mid: contrib(working[mid]) if mid in working else 0 for mid in members}
        s_raw = sum(contribs.values())
        tiers = {str(working[mid]["tier"]) for mid in members if mid in working and contribs[mid] > 0}
        mingled = len(tiers) >= 2
        s_adj = max(0, s_raw - mingle_penalty) if mingled else s_raw
        cap = int(ldef["cap"])
        if s_adj <= cap:
            scaled = False
            target = s_adj
        else:
            scaled = True
            target = cap
        denom = s_raw
        numer = target
        alloc: dict[str, int] = {m: 0 for m in members}
        if denom == 0:
            pass
        else:
            pos = sorted([m for m in members if contribs[m] > 0])
            for m in members:
                alloc[m] = (contribs[m] * numer) // denom
            slack = numer - sum(alloc.values())
            idx = 0
            while slack > 0 and pos:
                m = pos[idx % len(pos)]
                alloc[m] += 1
                slack -= 1
                idx += 1
        for m, v in alloc.items():
            if m in working:
                alloc_all[m] = alloc_all.get(m, 0) + v
        rows.append(
            {
                "lane_id": lid,
                "mingled": mingled,
                "post_cap_sum": target,
                "pre_cap_sum": s_adj,
                "scaled": scaled,
            }
        )

    regions: dict[str, int] = {}
    for r in sorted(active):
        anchor = _load(data_dir / "anchors" / f"{r}.json")
        want = [str(x) for x in anchor["items"]]
        tot = sum(alloc_all.get(iid, 0) for iid in want if iid in working)
        regions[r] = tot

    amb = anc_x.get("ambient_subtract", 0)
    if not isinstance(amb, int):
        amb = 0
    for r in list(regions.keys()):
        regions[r] = max(0, int(regions[r]) - int(amb))

    summary = {
        "ancillary_note": str(anc_x.get("note", "")),
        "applied_events": applied,
        "current_day": D,
        "regions": {k: regions[k] for k in sorted(regions.keys())},
    }
    _dump(audit_dir / "lane_table.json", {"lanes": rows})
    _dump(audit_dir / "summary.json", summary)


def main() -> None:
    data_dir = Path(os.environ.get("RLC_DATA_DIR", "/app/rlc_lab"))
    audit_dir = Path(os.environ.get("RLC_AUDIT_DIR", "/app/audit"))
    run(data_dir, audit_dir)


if __name__ == "__main__":
    main()
