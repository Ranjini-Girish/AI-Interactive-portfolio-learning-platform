#!/usr/bin/env python3
"""Oracle solver for seismic-localization-qc-hard."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

SEVERITIES = ["critical", "high", "medium", "low", "info"]


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(fh)]


def fl(row: dict[str, str], key: str) -> float:
    return float(row[key])


def load(data: Path) -> tuple:
    stations = [
        {"station_id": r["station_id"], "x": fl(r, "x_km"), "y": fl(r, "y_km"),
         "elevation": fl(r, "elevation_km"), "bias": fl(r, "bias_s"),
         "enabled": r["enabled"] == "true"}
        for r in read_csv_dicts(data / "network" / "stations.csv")
    ]
    layers = [
        {"phase": r["phase"], "top": fl(r, "top_depth_km"),
         "bottom": fl(r, "bottom_depth_km"), "velocity": fl(r, "velocity_km_s")}
        for r in read_csv_dicts(data / "velocity" / "velocity_layers.csv")
    ]
    events = [
        {"event_id": r["event_id"], "x": fl(r, "prior_x_km"), "y": fl(r, "prior_y_km"),
         "depth": fl(r, "prior_depth_km"), "origin": fl(r, "prior_origin_time_s"),
         "status": r["status"]}
        for r in read_csv_dicts(data / "catalog" / "events.csv")
    ]
    picks_raw = read_csv_dicts(data / "picks" / "picks.csv")
    picks = []
    for r in picks_raw:
        amp_str = r.get("amplitude", "").strip()
        amp = None
        if amp_str:
            try:
                amp = float(amp_str)
                if amp <= 0:
                    amp = None
            except ValueError:
                amp = None
        picks.append({
            "pick_id": r["pick_id"], "event_id": r["event_id"],
            "station_id": r["station_id"], "phase": r["phase"],
            "arrival": fl(r, "arrival_time_s"), "weight": fl(r, "weight"),
            "status": r["status"], "amplitude": amp,
        })
    policy = json.loads((data / "policy.json").read_text(encoding="utf-8"))
    mag_model = json.loads((data / "magnitude_model.json").read_text(encoding="utf-8"))
    exclusions = json.loads((data / "exclusions.json").read_text(encoding="utf-8"))
    return stations, layers, events, picks, policy, mag_model, exclusions


def get_velocity(layers: list[dict], phase: str, depth: float) -> float | None:
    phase_layers = [la for la in layers if la["phase"] == phase]
    for i, la in enumerate(phase_layers):
        upper_ok = depth < la["bottom"] or (i == len(phase_layers) - 1 and depth <= la["bottom"])
        if depth >= la["top"] and upper_ok:
            return la["velocity"]
    return None


def calc_travel(st: dict, x: float, y: float, depth: float, v: float) -> float:
    return math.sqrt((x - st["x"])**2 + (y - st["y"])**2 + (depth + st["elevation"])**2) / v


def evaluate(picks: list[dict], stations: dict, layers: list[dict],
             x: float, y: float, depth: float) -> dict | None:
    vals = []
    sum_w = 0.0
    sum_origin = 0.0
    for p in picks:
        st = stations[p["station_id"]]
        v = get_velocity(layers, p["phase"], depth)
        if v is None:
            return None
        tt = calc_travel(st, x, y, depth, v)
        origin_i = p["arrival"] - st["bias"] - tt
        vals.append((p, st, tt))
        sum_w += p["weight"]
        sum_origin += p["weight"] * origin_i
    if sum_w == 0:
        return None
    origin = sum_origin / sum_w
    residuals = []
    ss = 0.0
    for p, st, tt in vals:
        r = p["arrival"] - st["bias"] - (origin + tt)
        residuals.append(r)
        ss += p["weight"] * r * r
    return {"x": x, "y": y, "depth": depth, "origin": origin,
            "rms": math.sqrt(ss / sum_w), "residuals": residuals}


def candidate_range(center: float, radius: float, step: float) -> list[float]:
    n = int(round(2.0 * radius / step))
    return [center - radius + i * step for i in range(n + 1)]


def is_better(a: dict, b: dict | None) -> bool:
    if b is None:
        return True
    return (a["rms"], a["depth"], a["x"], a["y"]) < (b["rms"], b["depth"], b["x"], b["y"])


def grid_search(picks: list[dict], stations: dict, layers: list[dict], policy: dict,
                cx: float, cy: float, cd: float,
                xy_r: float, z_r: float, step: float) -> dict | None:
    best = None
    for x in candidate_range(cx, xy_r, step):
        for y in candidate_range(cy, xy_r, step):
            for z in candidate_range(cd, z_r, step):
                if z < policy["min_depth_km"] or z > policy["max_depth_km"]:
                    continue
                sol = evaluate(picks, stations, layers, x, y, z)
                if sol is not None and is_better(sol, best):
                    best = sol
    return best


def locate(ev: dict, picks: list[dict], stations: dict, layers: list[dict],
           policy: dict) -> tuple[dict, list[dict], list[tuple]]:
    coarse = grid_search(picks, stations, layers, policy,
                         ev["x"], ev["y"], ev["depth"],
                         policy["grid_radius_km"], policy["depth_radius_km"],
                         policy["coarse_step_km"])
    if coarse is None:
        return None, picks, []
    fine = grid_search(picks, stations, layers, policy,
                       coarse["x"], coarse["y"], coarse["depth"],
                       policy["fine_radius_km"], policy["fine_radius_km"],
                       policy["fine_step_km"])
    if fine is None:
        return coarse, picks, []
    rejected = [(p, r) for p, r in zip(picks, fine["residuals"])
                if abs(r) > policy["residual_reject_s"]]
    kept = [p for p, r in zip(picks, fine["residuals"])
            if abs(r) <= policy["residual_reject_s"]]
    if len(kept) >= policy["min_usable_picks"] and rejected:
        coarse2 = grid_search(kept, stations, layers, policy,
                              ev["x"], ev["y"], ev["depth"],
                              policy["grid_radius_km"], policy["depth_radius_km"],
                              policy["coarse_step_km"])
        if coarse2:
            fine2 = grid_search(kept, stations, layers, policy,
                                coarse2["x"], coarse2["y"], coarse2["depth"],
                                policy["fine_radius_km"], policy["fine_radius_km"],
                                policy["fine_step_km"])
            if fine2:
                return fine2, kept, rejected
    return fine, picks, []


def r6(value: float | None) -> float | None:
    return None if value is None else round(float(value), 6)


def pop_stddev(values: list[float]) -> float:
    if not values:
        return 0.0
    m = sum(values) / len(values)
    return math.sqrt(sum((v - m)**2 for v in values) / len(values))


def compute_magnitude(sol: dict, used: list[dict], stations: dict, policy: dict,
                      mag_model: dict) -> tuple[float | None, float | None, list[tuple]]:
    ref_amp = mag_model["reference_amplitude"]
    ref_dist = mag_model["reference_distance_km"]
    decay = policy["station_amplitude_decay_power"]
    mag_obs = []
    for p in used:
        if p["amplitude"] is None:
            continue
        st = stations[p["station_id"]]
        dist = math.sqrt((sol["x"] - st["x"])**2 + (sol["y"] - st["y"])**2 +
                         (sol["depth"] + st["elevation"])**2)
        if dist <= 0:
            continue
        mag_i = (math.log10(p["amplitude"]) + decay * math.log10(dist / ref_dist) -
                 math.log10(ref_amp))
        mag_obs.append((p, mag_i))
    if len(mag_obs) < policy["min_magnitude_observations"]:
        return None, None, []
    mags = [m for _, m in mag_obs]
    ml = sum(mags) / len(mags)
    ml_unc = pop_stddev(mags)
    return ml, ml_unc, mag_obs


def azimuth_gap(used: list[dict], stations: dict, x: float, y: float) -> float:
    angles = []
    seen = set()
    for p in used:
        sid = p["station_id"]
        if sid in seen:
            continue
        seen.add(sid)
        st = stations[sid]
        angle = math.degrees(math.atan2(st["x"] - x, st["y"] - y))
        if angle < 0:
            angle += 360.0
        angles.append(angle)
    if len(angles) < 2:
        return 360.0
    angles.sort()
    gaps = [angles[i+1] - angles[i] for i in range(len(angles) - 1)]
    gaps.append(angles[0] + 360.0 - angles[-1])
    return max(gaps)


def nearest_station(stations: dict, x: float, y: float) -> float:
    return min(math.hypot(x - st["x"], y - st["y"]) for st in stations.values() if st["enabled"])


def make_finding(policy: dict, ftype: str, event_id: str, evidence: dict,
                 station_id: str | None = None, pick_id: str | None = None) -> dict:
    sev = policy["finding_severity"][ftype]
    return {"event_id": event_id, "evidence": evidence, "finding_type": ftype,
            "pick_id": pick_id, "severity": sev,
            "severity_rank": policy["severity_ranks"][sev], "station_id": station_id}


def rejection_reason(p: dict, stations: dict, layers: list[dict],
                     excluded_stations: set) -> str | None:
    st = stations.get(p["station_id"])
    if st is None:
        return "unknown_station"
    if not st["enabled"]:
        return "station_disabled"
    if p["station_id"] in excluded_stations:
        return "excluded_station"
    if p["phase"] not in {la["phase"] for la in layers}:
        return "unknown_phase"
    if p["weight"] <= 0:
        return "nonpositive_weight"
    if p["status"] != "use":
        return "pick_status"
    return None


def build_report(data_dir: Path, out_path: Path) -> dict:
    stations_list, layers, events, picks, policy, mag_model, exclusions = load(data_dir)
    stations = {s["station_id"]: s for s in stations_list}
    excluded_stations = set(exclusions.get("excluded_stations", []))
    excluded_events = set(exclusions.get("excluded_events", []))
    all_findings = []
    event_rows = []
    magnitudes = []

    for ev in sorted(events, key=lambda e: e["event_id"]):
        raw = [p for p in picks if p["event_id"] == ev["event_id"]]
        ev_findings = []
        is_excluded = ev["status"] in {"exclude", "void"} or ev["event_id"] in excluded_events

        if is_excluded:
            event_rows.append({
                "azimuth_gap_deg": None, "depth_km": None, "event_id": ev["event_id"],
                "findings": [], "ml": None, "ml_uncertainty": None,
                "nearest_station_km": None, "origin_time_s": None,
                "phase_counts": {"P": 0, "S": 0}, "rejected_pick_count": len(raw),
                "rms_residual_s": None, "source_pick_ids": [], "status": "excluded",
                "used_pick_count": 0, "x_km": None, "y_km": None,
            })
            continue

        eligible = []
        for p in raw:
            reason = rejection_reason(p, stations, layers, excluded_stations)
            if reason is None:
                eligible.append(p)
            else:
                ev_findings.append(make_finding(
                    policy, "rejected_pick", ev["event_id"],
                    {"reason": reason}, p["station_id"], p["pick_id"]))

        if len(eligible) < policy["min_usable_picks"]:
            ev_findings.append(make_finding(policy, "insufficient_picks", ev["event_id"], {
                "eligible_picks": len(eligible), "min_required": policy["min_usable_picks"],
                "raw_pick_count": len(raw),
            }))
            all_findings.extend(ev_findings)
            event_rows.append({
                "azimuth_gap_deg": None, "depth_km": None, "event_id": ev["event_id"],
                "findings": ev_findings, "ml": None, "ml_uncertainty": None,
                "nearest_station_km": None, "origin_time_s": None,
                "phase_counts": {"P": 0, "S": 0}, "rejected_pick_count": len(raw),
                "rms_residual_s": None, "source_pick_ids": [], "status": "insufficient_picks",
                "used_pick_count": 0, "x_km": None, "y_km": None,
            })
            continue

        sol, used, residual_rejected = locate(ev, eligible, stations, layers, policy)
        if sol is None:
            all_findings.extend(ev_findings)
            event_rows.append({
                "azimuth_gap_deg": None, "depth_km": None, "event_id": ev["event_id"],
                "findings": ev_findings, "ml": None, "ml_uncertainty": None,
                "nearest_station_km": None, "origin_time_s": None,
                "phase_counts": {"P": 0, "S": 0}, "rejected_pick_count": len(raw),
                "rms_residual_s": None, "source_pick_ids": [], "status": "failed",
                "used_pick_count": 0, "x_km": None, "y_km": None,
            })
            continue

        for p, residual in residual_rejected:
            ev_findings.append(make_finding(policy, "rejected_pick", ev["event_id"], {
                "reason": "residual", "residual_s": r6(residual),
                "threshold_s": policy["residual_reject_s"],
            }, p["station_id"], p["pick_id"]))

        gap = azimuth_gap(used, stations, sol["x"], sol["y"])
        near = nearest_station(stations, sol["x"], sol["y"])
        ml, ml_unc, mag_obs = compute_magnitude(sol, used, stations, policy, mag_model)

        if sol["rms"] > policy["high_rms_threshold_s"]:
            ev_findings.append(make_finding(policy, "high_residual_rms", ev["event_id"],
                {"rms_residual_s": r6(sol["rms"]), "threshold_s": policy["high_rms_threshold_s"]}))
        if gap > policy["max_azimuth_gap_deg"]:
            ev_findings.append(make_finding(policy, "large_azimuth_gap", ev["event_id"],
                {"azimuth_gap_deg": r6(gap), "threshold_deg": policy["max_azimuth_gap_deg"]}))
        if sol["depth"] == policy["min_depth_km"] or sol["depth"] == policy["max_depth_km"]:
            ev_findings.append(make_finding(policy, "depth_at_boundary", ev["event_id"],
                {"depth_km": r6(sol["depth"]), "min_depth_km": policy["min_depth_km"],
                 "max_depth_km": policy["max_depth_km"]}))
        if sol["depth"] < policy["shallow_depth_km"]:
            ev_findings.append(make_finding(policy, "shallow_depth", ev["event_id"],
                {"depth_km": r6(sol["depth"]), "threshold_km": policy["shallow_depth_km"]}))
        if near > policy["near_station_threshold_km"]:
            ev_findings.append(make_finding(policy, "station_distance_warning", ev["event_id"],
                {"nearest_station_km": r6(near), "threshold_km": policy["near_station_threshold_km"]}))
        if ml is not None and ml_unc is not None and ml_unc > 0:
            z_thresh = policy["magnitude_outlier_z"]
            for p, mag_i in mag_obs:
                if abs(mag_i - ml) > z_thresh * ml_unc:
                    ev_findings.append(make_finding(policy, "magnitude_outlier", ev["event_id"],
                        {"station_magnitude": r6(mag_i), "event_magnitude": r6(ml),
                         "deviation": r6(mag_i - ml), "threshold": r6(z_thresh * ml_unc)},
                        p["station_id"], p["pick_id"]))

        all_findings.extend(ev_findings)
        if ml is not None:
            magnitudes.append(ml)
        phase_counts = Counter(p["phase"] for p in used)
        event_rows.append({
            "azimuth_gap_deg": r6(gap), "depth_km": r6(sol["depth"]),
            "event_id": ev["event_id"], "findings": ev_findings,
            "ml": r6(ml), "ml_uncertainty": r6(ml_unc),
            "nearest_station_km": r6(near), "origin_time_s": r6(sol["origin"]),
            "phase_counts": {"P": phase_counts.get("P", 0), "S": phase_counts.get("S", 0)},
            "rejected_pick_count": len(raw) - len(used),
            "rms_residual_s": r6(sol["rms"]),
            "source_pick_ids": sorted(p["pick_id"] for p in used),
            "status": "localized", "used_pick_count": len(used),
            "x_km": r6(sol["x"]), "y_km": r6(sol["y"]),
        })

    all_findings.sort(key=lambda f: (
        -f["severity_rank"], f["finding_type"],
        f["event_id"] or "", f["station_id"] or "", f["pick_id"] or "",
    ))
    by_severity = {s: 0 for s in SEVERITIES}
    for item in all_findings:
        by_severity[item["severity"]] += 1
    by_type = dict(sorted(Counter(f["finding_type"] for f in all_findings).items()))
    mean_mag = r6(sum(magnitudes) / len(magnitudes)) if magnitudes else None
    summary = {
        "by_finding_type": by_type, "by_severity": by_severity,
        "event_count": len(events),
        "excluded_events": sum(1 for e in event_rows if e["status"] in {"excluded"}),
        "findings_count": len(all_findings),
        "localized_events": sum(1 for e in event_rows if e["status"] == "localized"),
        "mean_magnitude": mean_mag, "station_count": len(stations_list),
        "total_picks_used": sum(e["used_pick_count"] for e in event_rows),
        "total_rejected_picks": sum(e["rejected_pick_count"] for e in event_rows),
    }
    report = {"events": event_rows, "findings": all_findings,
              "schema_version": 1, "summary": summary}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/app/data")
    parser.add_argument("--out", default="/app/output/localization_report.json")
    args = parser.parse_args()
    build_report(Path(args.data), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())