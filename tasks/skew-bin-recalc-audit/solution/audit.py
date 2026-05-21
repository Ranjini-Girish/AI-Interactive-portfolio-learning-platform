#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
from collections import defaultdict
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


def _samples(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fp in sorted((root / "samples").glob("sample_*.json")):
        rows.append(_load(fp))
    return rows


def _median(vals: list[float]) -> float:
    return float(statistics.median(vals))


def _mad(vals: list[float], m: float) -> float:
    devs = [abs(float(x) - m) for x in vals]
    return float(statistics.median(devs))


def _bin_index(edges: list[int], value: float) -> int:
    if value < float(edges[0]):
        return 0
    last = len(edges) - 2
    if value >= float(edges[-1]):
        return last
    for i in range(len(edges) - 1):
        lo = float(edges[i])
        hi = float(edges[i + 1])
        if lo <= value < hi:
            return i
    return last


def run_audit(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    as_of = int(pool["as_of"])
    edges = [int(x) for x in policy["bin_edges"]]
    z = float(policy["outlier_z"])
    mask = int(policy["count_band_mask"])
    assert z > 0

    samples_in = _samples(data_dir)
    suppressed: set[str] = set()
    shifts: dict[str, int] = {}
    for inc in incidents.get("incidents", []):
        if str(inc.get("kind")) == "suppress":
            if int(inc.get("active_from", -1)) <= as_of <= int(inc.get("active_to", -2)):
                suppressed.add(str(inc["probe"]))
        if str(inc.get("kind")) == "shift_bins":
            if int(inc.get("active_from", -1)) <= as_of <= int(inc.get("active_to", -2)):
                shifts[str(inc["probe"])] = int(inc["delta"])

    kept: list[dict[str, Any]] = [s for s in samples_in if str(s["probe"]) not in suppressed]

    by_probe_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in kept:
        by_probe_rows[str(s["probe"])].append(s)

    used_rows: list[dict[str, Any]] = []
    for _probe, rows in sorted(by_probe_rows.items()):
        vals = [float(r["value"]) for r in rows]
        if len(vals) < 2:
            flags = [True] * len(vals)
        else:
            m = _median(vals)
            mad = _mad(vals, m)
            if mad == 0.0:
                flags = [True] * len(vals)
            else:
                thresh = z * 1.4826 * mad
                flags = [abs(v - m) <= thresh for v in vals]
        for row, ok in zip(rows, flags, strict=True):
            if not ok:
                continue
            if ((mask >> int(row["band"])) & 1) != 1:
                continue
            used_rows.append(dict(row))

    bin_count = len(edges) - 1
    counts = [0 for _ in range(bin_count)]
    for s in used_rows:
        idx = _bin_index(edges, float(s["value"]))
        idx += int(shifts.get(str(s["probe"]), 0))
        if idx < 0:
            idx = 0
        if idx >= bin_count:
            idx = bin_count - 1
        counts[idx] += 1

    bins_out = [{"index": i, "count": int(c)} for i, c in enumerate(counts)]
    summary = {
        "samples_in": len(samples_in),
        "samples_used": len(used_rows),
        "bins": bin_count,
        "as_of": as_of,
    }
    audit_dir.mkdir(parents=True, exist_ok=True)
    _dump(audit_dir / "histogram.json", {"bins": bins_out})
    _dump(audit_dir / "summary.json", summary)


def main() -> None:
    import os

    data = Path(os.environ["SBR_DATA_DIR"])
    audit = Path(os.environ["SBR_AUDIT_DIR"])
    run_audit(data, audit)


if __name__ == "__main__":
    main()
