#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _round3(x: float) -> float:
    return float(format(x, ".3f"))


def _lane_map(root: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for fp in sorted((root / "lanes").glob("l*.json")):
        row = _load(fp)
        lid = str(row["lane_id"])
        out[lid] = row
    return out


def _day_blind(day: int, lane_id: str, events: list[dict[str, Any]]) -> bool:
    for ev in events:
        if str(ev.get("kind")) != "day_blind" or not ev.get("accepted"):
            continue
        fd = int(ev["from_day"])
        td = int(ev["to_day"])
        if not (fd <= day <= td):
            continue
        lanes = ev.get("lanes") or []
        if "*" in lanes or lane_id in lanes:
            return True
    return False


def run_hba(root: Path) -> dict[str, Any]:
    _load(root / "domain_layout.json")
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    window = _load(root / "anchors" / "window.json")
    scale_doc = _load(root / "ancillary" / "scale.json")

    start_day = int(window["start_day"])
    end_day = int(window["end_day"])
    debounce = int(policy["debounce_required"])
    if debounce < 1:
        raise ValueError("debounce_required must be >= 1")

    bias = float(pool["bias"])
    scale = float(scale_doc["scale"])
    events = list(inc.get("events", []))

    lanes = _lane_map(root)

    tick_paths = sorted((root / "ticks").glob("tick_*.json"))
    total_seen = len(tick_paths)
    pairs: list[tuple[Path, dict[str, Any]]] = []
    for fp in tick_paths:
        pairs.append((fp, _load(fp)))
    pairs.sort(key=lambda pr: (int(pr[1]["day"]), str(pr[1]["lane_id"]), str(pr[0])))
    ticks = [pr[1] for pr in pairs]
    evaluated = 0

    state: dict[str, str] = {lid: str(info["start_state"]) for lid, info in lanes.items()}
    streak_hi: dict[str, int] = {lid: 0 for lid in lanes}
    streak_lo: dict[str, int] = {lid: 0 for lid in lanes}

    crossings: list[dict[str, Any]] = []

    for row in ticks:
        day = int(row["day"])
        lane_id = str(row["lane_id"])
        if lane_id not in lanes:
            continue
        info = lanes[lane_id]
        low_t = float(info["low_thresh"])
        high_t = float(info["high_thresh"])

        if day < start_day or day > end_day:
            continue
        if _day_blind(day, lane_id, events):
            streak_hi[lane_id] = 0
            streak_lo[lane_id] = 0
            continue

        raw = float(row["value"])
        adj = _round3((raw + bias) * scale)
        evaluated += 1

        cur = state[lane_id]
        if cur == "low":
            streak_lo[lane_id] = 0
            if adj >= high_t:
                streak_hi[lane_id] += 1
            else:
                streak_hi[lane_id] = 0
            if streak_hi[lane_id] >= debounce:
                state[lane_id] = "high"
                crossings.append(
                    {
                        "day": day,
                        "from_state": "low",
                        "lane_id": lane_id,
                        "streak_at_flip": debounce,
                        "to_state": "high",
                    }
                )
                streak_hi[lane_id] = 0
                streak_lo[lane_id] = 0
        else:
            streak_hi[lane_id] = 0
            if adj <= low_t:
                streak_lo[lane_id] += 1
            else:
                streak_lo[lane_id] = 0
            if streak_lo[lane_id] >= debounce:
                state[lane_id] = "low"
                crossings.append(
                    {
                        "day": day,
                        "from_state": "high",
                        "lane_id": lane_id,
                        "streak_at_flip": debounce,
                        "to_state": "low",
                    }
                )
                streak_hi[lane_id] = 0
                streak_lo[lane_id] = 0

    crossings.sort(key=lambda r: (int(r["day"]), str(r["lane_id"])))

    incidents_applied = sum(1 for ev in events if ev.get("accepted"))

    summary = {
        "crossing_events": len(crossings),
        "debounce_required": debounce,
        "end_day": end_day,
        "incidents_applied": incidents_applied,
        "lanes": sorted(lanes.keys()),
        "start_day": start_day,
        "ticks_evaluated": evaluated,
        "ticks_seen": total_seen,
    }

    ledger = {"crossings": crossings, "final_state": {k: state[k] for k in sorted(state.keys())}}

    return {"crossing_log.json": ledger, "summary.json": summary}


def main() -> None:
    root = Path(os.environ["HBA_DATA_DIR"])
    out = Path(os.environ["HBA_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_hba(root)
    for name, payload in payloads.items():
        (out / name).write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": ")) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
