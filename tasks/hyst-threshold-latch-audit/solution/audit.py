#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(p: Path, obj: Any) -> None:
    p.write_text(
        json.dumps(obj, sort_keys=True, indent=2, separators=(", ", ": "))
        + "\n",
        encoding="utf-8",
    )


def _points(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fp in sorted((root / "points").glob("point_*.json")):
        rows.append(_load(fp))
    rows.sort(key=lambda r: int(r["t"]))
    return rows


def run_audit(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    incidents = _load(data_dir / "incident_log.json")
    high = float(policy["high"])
    low = float(policy["low"])
    margin = float(policy["latch_clear_margin"])
    state = str(policy["initial"])
    if state not in {"low", "high"}:
        raise ValueError("invalid initial")
    if not (high > low):
        raise ValueError("invalid thresholds")
    if margin < 0:
        raise ValueError("invalid margin")

    pts = _points(data_dir)
    trace: list[dict[str, Any]] = []
    prev_state: str | None = None
    flips = 0
    high_steps = 0

    for pt in pts:
        t = int(pt["t"])
        v_raw = float(pt["v"])
        add = 0.0
        for inc in incidents.get("incidents", []):
            if str(inc.get("kind")) != "bias_signal":
                continue
            if int(inc["t0"]) <= t <= int(inc["t1"]):
                add += float(inc["add"])
        v_adj = v_raw + add

        nxt = state
        if state == "low" and v_adj >= high:
            nxt = "high"
        elif state == "high" and v_adj <= low - margin:
            nxt = "low"

        force = False
        for inc in incidents.get("incidents", []):
            if str(inc.get("kind")) != "force_low":
                continue
            t_trig = int(inc["t"])
            until = int(inc["until"])
            if t_trig <= t <= until:
                force = True
                break
        if force and nxt == "high":
            nxt = "low"

        if prev_state is not None and nxt != prev_state:
            flips += 1
        prev_state = nxt
        if nxt == "high":
            high_steps += 1

        state = nxt
        trace.append(
            {
                "t": t,
                "v_raw": v_raw,
                "v_adj": v_adj,
                "state": state,
            }
        )

    summary = {
        "flips": flips,
        "high_steps": high_steps,
        "points": len(trace),
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    _dump(audit_dir / "latch_trace.json", {"states": trace})
    _dump(audit_dir / "summary.json", summary)


def main() -> None:
    import os

    data = Path(os.environ["HTL_DATA_DIR"])
    audit = Path(os.environ["HTL_AUDIT_DIR"])
    run_audit(data, audit)


if __name__ == "__main__":
    main()
