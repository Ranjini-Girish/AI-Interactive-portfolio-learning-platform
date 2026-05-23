"""Heat flux yoke laboratory audit reference implementation."""

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


def main() -> None:
    data_dir = Path(os.environ.get("HFY_DATA_DIR", "/app/hfy_lab"))
    audit_dir = Path(os.environ.get("HFY_AUDIT_DIR", "/app/audit"))
    run(data_dir, audit_dir)


def run(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    anc = _load(data_dir / "ancillary" / "x.json")

    active = set(policy["active_regions"])
    yokes_cfg: dict[str, Any] = policy["yokes"]
    flux_floor = int(policy["flux_floor_mw"])
    span_permille = int(policy["span_penalty_permille"])

    items: list[dict[str, Any]] = []
    for i in range(18):
        name = f"item_{i:02d}.json"
        items.append(_load(data_dir / "items" / name))

    cur_items = [it for it in items if str(it["region"]) in active]

    events = list(incidents.get("events", []))
    applied = 0
    for ev in events:
        applied += 1
        kind = str(ev.get("kind", ""))
        if kind == "tier_k_boost":
            tier = str(ev["tier"])
            add = int(ev["add"])
            for it in cur_items:
                if str(it["tier"]) == tier:
                    it["k_mw_per_day"] = max(0, int(it["k_mw_per_day"]) + add)
        elif kind == "yoke_cap_rescale":
            yid = str(ev["yoke_id"])
            if yid in yokes_cfg:
                yokes_cfg[yid]["flux_cap"] = int(ev["new_cap"])
        elif kind == "cell_excise":
            cell = str(ev["cell"])
            cur_items = [it for it in cur_items if str(it["cell"]) != cell]

    D = int(pool["current_day"])
    cell_raw: dict[str, int] = {}
    for it in cur_items:
        age = max(0, D - int(it["born_day"]))
        raw = int(it["flux0_mw"]) - int(it["k_mw_per_day"]) * age
        raw = max(flux_floor, raw)
        c = str(it["cell"])
        cell_raw[c] = cell_raw.get(c, 0) + raw

    yoke_ids = sorted(yokes_cfg.keys())
    yoke_rows: list[dict[str, Any]] = []
    cell_alloc: dict[str, int] = {}

    for yid in yoke_ids:
        ydef = yokes_cfg[yid]
        cells_in_yoke = [str(c) for c in ydef["cells"]]
        S_raw = sum(cell_raw.get(c, 0) for c in cells_in_yoke)

        spanned = False
        has_a = any(
            str(it["region"]) == "a" and str(it["cell"]) in cells_in_yoke for it in cur_items
        )
        has_b = any(
            str(it["region"]) == "b" and str(it["cell"]) in cells_in_yoke for it in cur_items
        )
        spanned = bool(has_a and has_b)

        S_pen = (S_raw * span_permille) // 1000 if spanned else S_raw
        cap = int(ydef["flux_cap"])
        if S_pen <= cap:
            scaled = False
            target = S_pen
        else:
            scaled = True
            target = cap

        ordered_cells: list[str] = []
        for c in cells_in_yoke:
            if c not in ordered_cells:
                ordered_cells.append(c)
        alloc = {c: 0 for c in ordered_cells}
        denom = S_raw
        numer = target
        if denom == 0:
            pass
        else:
            pos_cells = [c for c in sorted(ordered_cells) if cell_raw.get(c, 0) > 0]
            for c in ordered_cells:
                alloc[c] = (cell_raw.get(c, 0) * numer) // denom
            slack = numer - sum(alloc.values())
            idx = 0
            while slack > 0 and pos_cells:
                c = pos_cells[idx % len(pos_cells)]
                alloc[c] += 1
                slack -= 1
                idx += 1

        for c, v in alloc.items():
            cell_alloc[c] = cell_alloc.get(c, 0) + v

        yoke_rows.append(
            {
                "post_cap_sum": target,
                "pre_cap_sum": S_pen,
                "scaled": scaled,
                "spanned": spanned,
                "yoke_id": yid,
            }
        )

    regions: dict[str, int] = {}
    for r in sorted(active):
        anchor = _load(data_dir / "anchors" / f"{r}.json")
        watched = set(str(x) for x in anchor["cells"])
        tot = sum(cell_alloc.get(c, 0) for c in watched)
        regions[r] = tot

    ambient = anc.get("ambient_subtract", 0)
    if not isinstance(ambient, int):
        ambient = 0
    for r in list(regions.keys()):
        regions[r] = max(0, int(regions[r]) - int(ambient))

    summary = {
        "ancillary_note": str(anc.get("note", "")),
        "applied_events": applied,
        "current_day": D,
        "regions": {k: regions[k] for k in sorted(regions.keys())},
    }
    yoke_table = {"yokes": yoke_rows}
    _dump(audit_dir / "yoke_table.json", yoke_table)
    _dump(audit_dir / "summary.json", summary)


if __name__ == "__main__":
    main()
