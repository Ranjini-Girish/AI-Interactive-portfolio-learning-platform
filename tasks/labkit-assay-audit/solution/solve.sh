#!/bin/bash
set -euo pipefail

ROOT="${LKA_DATA_DIR:-/app/labkit}"
OUT="${LKA_AUDIT_DIR:-/app/audit}"
mkdir -p "${OUT}"

python3 <<'PY'
from __future__ import annotations

import json
import math
import os
from pathlib import Path

ROOT = Path(os.environ.get("LKA_DATA_DIR", "/app/labkit"))
OUT = Path(os.environ.get("LKA_AUDIT_DIR", "/app/audit"))
OUT.mkdir(parents=True, exist_ok=True)


def load_json(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


def median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    n = len(s)
    m = n // 2
    if n % 2:
        return s[m]
    return (s[m - 1] + s[m]) / 2.0


def round4(x: float) -> float:
    return float(round(x + 0.0, 4))


def linreg(xs: list[float], ys: list[float]) -> tuple[float, float] | None:
    n = len(xs)
    if n < 2:
        return None
    sx = sum(xs)
    sy = sum(ys)
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys, strict=True))
    denom = n * sxx - sx * sx
    if denom == 0.0:
        return None
    a = (n * sxy - sx * sy) / denom
    b = (sy - a * sx) / n
    if a == 0.0:
        return None
    return a, b


def dumps_obj(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


pool = load_json("pool_state.json")
policy = load_json("policy.json")
assays = load_json("assays.json")["assays"]
batches = load_json("batches/index.json")["batches"]
lots_registry = load_json("lots/registry.json")["lots"]
incidents = load_json("incident_log.json")

current_day = int(pool["current_day"])
min_blanks = int(policy["min_blanks"])
fallback_blank = float(policy["fallback_blank_value"])
drift_thr = float(policy["drift_abs_threshold"])

known_lots = set(lots_registry.keys())

recalled: set[str] = set()
ignored_incidents = 0
for ev in incidents.get("events", []):
    if ev.get("kind") != "lot_recall":
        ignored_incidents += 1
        continue
    if ev.get("accepted") is False:
        ignored_incidents += 1
        continue
    day = int(ev.get("day", 10**9))
    if day > current_day:
        ignored_incidents += 1
        continue
    lid = ev.get("lot_id")
    if not lid or lid not in known_lots:
        ignored_incidents += 1
        continue
    recalled.add(lid)
recalled_sorted = sorted(recalled)

plates: list[dict] = []
for path in sorted((ROOT / "plates").glob("*.json")):
    plates.append(json.loads(path.read_text(encoding="utf-8")))

lineage_by_batch = {b["batch_id"]: b["lineage_id"] for b in batches}
monitored_assay_by_batch = {b["batch_id"]: b["assay_id"] for b in batches}

# plate_id -> run_day -> blank_effective, blank_fallback bool
plate_meta: dict[str, tuple[int, float, bool]] = {}
well_rows: list[dict] = []

for plate in plates:
    pid = plate["plate_id"]
    run_day = int(plate["run_day"])
    blanks = [float(w["raw_value"]) for w in plate["wells"] if w["role"] == "blank"]
    if len(blanks) >= min_blanks:
        be = float(median(blanks) or 0.0)
        bf = False
    else:
        be = fallback_blank
        bf = True
    plate_meta[pid] = (run_day, be, bf)

# First pass: compute nets + preliminary disposition
prelim: dict[tuple[str, str], dict] = {}

for plate in plates:
    pid = plate["plate_id"]
    run_day, blank_eff, blank_fb = plate_meta[pid]
    for w in plate["wells"]:
        wid = w["well_id"]
        role = w["role"]
        batch_id = w["batch_id"]
        key = (pid, wid)
        base = {
            "well_key": f"{pid}:{wid}",
            "plate_id": pid,
            "well_id": wid,
            "batch_id": batch_id,
            "assay_id": w.get("assay_id"),
            "normalization_mode": None,
            "net_value": None,
            "disposition": "skipped_non_sample",
            "detail": "",
        }
        if role != "sample":
            prelim[key] = base
            continue

        assay_id = w["assay_id"]
        lot_id = w.get("lot_id")
        raw_v = float(w["raw_value"])
        mode = assays[assay_id]["normalization_mode"]
        base["normalization_mode"] = mode

        if lot_id in recalled:
            base["net_value"] = None
            base["disposition"] = "frozen_recall"
            base["detail"] = f"recall:{lot_id}"
            prelim[key] = base
            continue

        if mode == "to_blank_median":
            net = raw_v - blank_eff
            base["net_value"] = round4(net)
            base["disposition"] = "blank_degraded" if blank_fb else "ok"
            base["detail"] = "blank_fallback" if blank_fb else ""
            prelim[key] = base
            continue

        # standard curve
        std_pairs: list[tuple[float, float]] = []
        for ww in plate["wells"]:
            if ww.get("assay_id") != assay_id or ww["role"] != "std":
                continue
            lvl = ww["std_level"]
            x = float(assays[assay_id]["std_x_by_level"][lvl])
            y = float(ww["raw_value"])
            std_pairs.append((x, y))
        std_pairs.sort(key=lambda t: (t[0], t[1]))
        xs = [p[0] for p in std_pairs]
        ys = [p[1] for p in std_pairs]
        reg = linreg(xs, ys)
        unusable = reg is None
        if unusable:
            base["net_value"] = None
            base["disposition"] = "curve_unusable"
            base["detail"] = "curve_unusable"
        else:
            a, b = reg
            net = (raw_v - b) / a
            base["net_value"] = round4(net)
            base["disposition"] = "ok"
            base["detail"] = ""
        if blank_fb:
            base["disposition"] = "blank_degraded"
            base["detail"] = "blank_fallback"
            if unusable:
                base["net_value"] = None
        prelim[key] = base

# Drift pass per batch+assay from batches index
rollup_entries: list[dict] = []

for row in sorted(batches, key=lambda r: (r["batch_id"], r["assay_id"])):
    batch_id = row["batch_id"]
    assay_id = row["assay_id"]
    lineage_id = row["lineage_id"]

    hist_vals: list[float] = []
    for d in range(0, current_day):
        day_nets: list[float] = []
        for plate in plates:
            if int(plate["run_day"]) != d:
                continue
            pid = plate["plate_id"]
            for w in plate["wells"]:
                if w["role"] != "sample":
                    continue
                if w["batch_id"] != batch_id or w["assay_id"] != assay_id:
                    continue
                st = prelim[(pid, w["well_id"])]
                if st["disposition"] == "ok" and st.get("net_value") is not None:
                    day_nets.append(float(st["net_value"]))
        md = median(day_nets)
        if md is not None:
            hist_vals.append(md)
    cur_nets: list[float] = []
    for plate in plates:
        if int(plate["run_day"]) != current_day:
            continue
        pid = plate["plate_id"]
        for w in plate["wells"]:
            if w["role"] != "sample":
                continue
            if w["batch_id"] != batch_id or w["assay_id"] != assay_id:
                continue
            st = prelim[(pid, w["well_id"])]
            if st["disposition"] == "ok" and st.get("net_value") is not None:
                cur_nets.append(float(st["net_value"]))

    T_raw = median(cur_nets) if cur_nets else None
    used = len(cur_nets)
    T_out = round4(float(T_raw)) if T_raw is not None else None

    if not hist_vals:
        hist_med = None
        drift_delta = None
        drift_status = "no_history"
    else:
        hist_med = round4(float(median(hist_vals) or 0.0))
        if T_out is None:
            drift_delta = None
            drift_status = "insufficient_samples"
        else:
            drift_delta = round4(float(T_out) - float(hist_med))
            drift_status = "drift_alert" if abs(drift_delta) > drift_thr else "stable"

    rollup_entries.append(
        {
            "assay_id": assay_id,
            "batch_id": batch_id,
            "drift_delta": drift_delta,
            "drift_status": drift_status,
            "historic_median_net": hist_med,
            "lineage_id": lineage_id,
            "sample_count_used": used,
            "sample_median_net": T_out,
        }
    )

    if drift_status == "drift_alert" and T_out is not None:
        for plate in plates:
            if int(plate["run_day"]) != current_day:
                continue
            pid = plate["plate_id"]
            for w in plate["wells"]:
                if w["role"] != "sample":
                    continue
                if w["batch_id"] != batch_id or w["assay_id"] != assay_id:
                    continue
                st = prelim[(pid, w["well_id"])]
                if st["disposition"] == "ok":
                    st["disposition"] = "drift_alert"
                    st["detail"] = "drift_batch"

# Build final wells list
wells_out = sorted(prelim.values(), key=lambda o: o["well_key"])

# curve diagnostics
curve_rows: list[dict] = []
for plate in sorted(plates, key=lambda p: p["plate_id"]):
    pid = plate["plate_id"]
    assay_ids = sorted(
        {
            w["assay_id"]
            for w in plate["wells"]
            if w.get("assay_id") and assays[w["assay_id"]]["normalization_mode"] == "to_standard_curve"
        }
    )
    for aid in assay_ids:
        std_pairs: list[tuple[float, float]] = []
        for ww in plate["wells"]:
            if ww.get("assay_id") != aid or ww["role"] != "std":
                continue
            x = float(assays[aid]["std_x_by_level"][ww["std_level"]])
            y = float(ww["raw_value"])
            std_pairs.append((x, y))
        std_pairs.sort(key=lambda t: (t[0], t[1]))
        xs = [p[0] for p in std_pairs]
        ys = [p[1] for p in std_pairs]
        reg = linreg(xs, ys)
        usable = reg is not None
        slope = intercept = None
        res_max = None
        if usable:
            a, b = reg
            slope, intercept = a, b
            res = []
            for x, y in zip(xs, ys, strict=True):
                pred = a * x + b
                res.append(abs(y - pred))
            res_max = max(res) if res else None
        curve_rows.append(
            {
                "assay_id": aid,
                "intercept": intercept,
                "pair_count": len(std_pairs),
                "plate_id": pid,
                "residual_max": res_max,
                "slope": slope,
                "usable": usable,
            }
        )

curve_rows.sort(key=lambda r: (r["plate_id"], r["assay_id"]))

# lot disposition
lot_stats: list[dict] = []
for lot_id in sorted(lots_registry.keys()):
    cnt = 0
    for plate in plates:
        pid = plate["plate_id"]
        for w in plate["wells"]:
            if w["role"] != "sample":
                continue
            if w.get("lot_id") == lot_id:
                cnt += 1
    lot_stats.append(
        {
            "affected_wells": cnt,
            "lot_id": lot_id,
            "recalled": lot_id in recalled,
        }
    )

# disposition counts
counts: dict[str, int] = {}
for w in wells_out:
    d = w["disposition"]
    counts[d] = counts.get(d, 0) + 1

summary = {
    "current_day": current_day,
    "disposition_counts": dict(sorted(counts.items())),
    "ignored_incident_events": ignored_incidents,
    "plates_loaded": len(plates),
    "recall_lot_count": len(recalled_sorted),
}

(OUT / "well_results.json").write_text(dumps_obj({"wells": wells_out}), encoding="utf-8")
(OUT / "batch_assay_rollup.json").write_text(dumps_obj({"entries": rollup_entries}), encoding="utf-8")
(OUT / "curve_diagnostics.json").write_text(dumps_obj({"plates": curve_rows}), encoding="utf-8")
(OUT / "lot_disposition.json").write_text(dumps_obj({"lots": lot_stats}), encoding="utf-8")
(OUT / "summary.json").write_text(dumps_obj(summary), encoding="utf-8")
PY
