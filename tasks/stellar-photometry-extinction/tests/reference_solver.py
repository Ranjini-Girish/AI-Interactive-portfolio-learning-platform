#!/usr/bin/env python3
"""Oracle solver for stellar-photometry-extinction-audit-hard.

This file is the single source of truth for the algorithm. Both the test
suite and solution/solve.sh invoke (or embed) this exact implementation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

SEVERITIES = ["critical", "high", "medium", "low", "info"]


# ---------- IO helpers ------------------------------------------------------

def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return [{k: (v if v is not None else "").strip()
                 for k, v in row.items()}
                for row in csv.DictReader(fh)]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def fl(row: dict[str, str], key: str) -> float:
    return float(row[key])


def r6(value):
    if value is None:
        return None
    return round(float(value), 6)


# ---------- Loading ---------------------------------------------------------

def load_inputs(data: Path) -> dict:
    site = read_json(data / "site.json")
    policy = read_json(data / "policy.json")
    exclusions = read_json(data / "exclusions.json")
    manifest = read_json(data / "manifest.json")
    instrument = read_json(data / "instrument.json")

    standards_rows = read_csv_dicts(data / "catalog" / "standards.csv")
    standards = {}
    for r in standards_rows:
        sid = r["star_id"]
        cat_mags = {}
        for filt in instrument["filters"]:
            key = f"{filt}_mag"
            v = r.get(key, "")
            if v:
                try:
                    cat_mags[filt] = float(v)
                except ValueError:
                    pass
        standards[sid] = {
            "star_id": sid,
            "ra_deg": fl(r, "ra_deg"),
            "dec_deg": fl(r, "dec_deg"),
            "catalog_mags": cat_mags,
        }

    program_rows = read_csv_dicts(data / "catalog" / "programs.csv")
    programs = {}
    for r in program_rows:
        sid = r["star_id"]
        programs[sid] = {
            "star_id": sid,
            "ra_deg": fl(r, "ra_deg"),
            "dec_deg": fl(r, "dec_deg"),
            "target_type": r.get("target_type", ""),
        }

    nights = []
    for entry in manifest["nights"]:
        night_id = entry["night_id"]
        obs_path = data / "observations" / entry["observations_file"]
        rows = read_csv_dicts(obs_path)
        observations = []
        for r in rows:
            observations.append({
                "image_id": r["image_id"],
                "star_id": r["star_id"],
                "filter": r["filter"],
                "time_utc": r["time_utc"],
                "airmass": fl(r, "airmass"),
                "exposure_sec": fl(r, "exposure_sec"),
                "instrumental_mag": fl(r, "instrumental_mag"),
                "mag_uncertainty": fl(r, "mag_uncertainty"),
            })
        nights.append({
            "night_id": night_id,
            "date_utc": entry["date_utc"],
            "observations": observations,
        })

    return {
        "site": site,
        "policy": policy,
        "exclusions": exclusions,
        "manifest": manifest,
        "instrument": instrument,
        "standards": standards,
        "programs": programs,
        "nights": nights,
    }


# ---------- Statistics ------------------------------------------------------

def median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def mad(values: list[float]) -> float:
    if not values:
        return 0.0
    med = median(values)
    return median([abs(v - med) for v in values])


def weighted_population_residual_stddev(residuals: list[float],
                                        weights: list[float]) -> float:
    s = sum(weights)
    if s <= 0:
        return 0.0
    ssr = sum(w * r * r for w, r in zip(weights, residuals))
    return math.sqrt(ssr / s)


# ---------- Weighted least squares ------------------------------------------

def weighted_linear_fit(xs: list[float], ys: list[float],
                        ws: list[float]) -> dict | None:
    """Return {slope, intercept, slope_var, intercept_var} or None if singular."""
    s = sum(ws)
    if s <= 0:
        return None
    xbar = sum(w * x for w, x in zip(ws, xs)) / s
    ybar = sum(w * y for w, y in zip(ws, ys)) / s
    sxx = sum(w * (x - xbar) ** 2 for w, x in zip(ws, xs))
    sxy = sum(w * (x - xbar) * (y - ybar) for w, x, y in zip(ws, xs, ys))
    if sxx <= 0:
        return None
    slope = sxy / sxx
    intercept = ybar - slope * xbar
    slope_var = 1.0 / sxx
    intercept_var = 1.0 / s + xbar * xbar / sxx
    return {
        "slope": slope,
        "intercept": intercept,
        "slope_var": slope_var,
        "intercept_var": intercept_var,
        "xbar": xbar,
        "weight_sum": s,
    }


# ---------- Per-night, per-filter extinction fit ----------------------------

def build_calibration_jobs(data: dict) -> list[dict]:
    """One job per (night_id, filter) for non-excluded nights/filters."""
    excl = data["exclusions"]
    excluded_nights = set(excl.get("excluded_nights", []))
    excluded_filters_per_night = {
        rec["night_id"]: set(rec.get("filters", []))
        for rec in excl.get("excluded_filters_per_night", [])
    }
    filters = list(data["instrument"]["filters"])

    jobs = []
    for night in data["nights"]:
        nid = night["night_id"]
        is_excluded_night = nid in excluded_nights
        excluded_filters_here = excluded_filters_per_night.get(nid, set())
        for filt in filters:
            jobs.append({
                "night_id": nid,
                "filter": filt,
                "excluded_night": is_excluded_night,
                "excluded_filter": filt in excluded_filters_here,
                "observations": night["observations"],
            })
    return jobs


def fit_extinction(job: dict, data: dict) -> dict:
    """Fit one (night, filter). Returns a calibration record."""
    policy = data["policy"]
    standards = data["standards"]
    excl = data["exclusions"]
    excluded_observations = set(excl.get("excluded_observations", []))
    excluded_stars = set(excl.get("excluded_stars", []))

    nid = job["night_id"]
    filt = job["filter"]

    base = {
        "night_id": nid,
        "filter": filt,
        "n_total_observations": 0,
        "n_standards_used": 0,
        "n_outliers_flagged": 0,
        "n_program_observations": 0,
        "extinction_k": 0.0,
        "extinction_k_uncertainty": 0.0,
        "zero_point": 0.0,
        "zero_point_uncertainty": 0.0,
        "residual_stddev": 0.0,
        "airmass_min": None,
        "airmass_max": None,
        "status": "calibrated",
    }

    # Observation count for this (night, filter) pair (all star types)
    matching = [o for o in job["observations"] if o["filter"] == filt]
    base["n_total_observations"] = len(matching)

    if job["excluded_night"]:
        base["status"] = "excluded_night"
        base["airmass_min"] = None
        base["airmass_max"] = None
        return base

    if job["excluded_filter"]:
        base["status"] = "excluded_filter"
        return base

    # Build standard-star observation list for fitting
    sigma_floor = float(policy["uncertainty_floor_mag"])
    instrument = data["instrument"]
    color_term = float(instrument["color_terms"].get(filt, 0.0))
    standards_pool = []
    for o in matching:
        if o["star_id"] in excluded_stars:
            continue
        if o["image_id"] in excluded_observations:
            continue
        std = standards.get(o["star_id"])
        if std is None:
            continue
        cat = std["catalog_mags"].get(filt)
        if cat is None:
            continue
        if color_term != 0.0:
            b_mag = std["catalog_mags"].get("B")
            v_mag = std["catalog_mags"].get("V")
            if b_mag is None or v_mag is None:
                continue
            color_index = b_mag - v_mag
        else:
            color_index = 0.0
        sigma = max(o["mag_uncertainty"], sigma_floor)
        if sigma <= 0:
            continue
        max_airmass = float(policy.get("max_airmass", 99.0))
        if o["airmass"] > max_airmass:
            continue
        delta = o["instrumental_mag"] - cat - color_term * color_index
        weight = 1.0 / (sigma * sigma)
        standards_pool.append({
            "image_id": o["image_id"],
            "star_id": o["star_id"],
            "airmass": o["airmass"],
            "delta": delta,
            "sigma": sigma,
            "weight": weight,
        })

    min_standards = int(policy["min_standards_per_fit"])
    if len(standards_pool) < min_standards:
        base["status"] = "insufficient_standards"
        base["n_standards_used"] = len(standards_pool)
        return base

    # First weighted fit
    xs = [p["airmass"] for p in standards_pool]
    ys = [p["delta"] for p in standards_pool]
    ws = [p["weight"] for p in standards_pool]
    fit = weighted_linear_fit(xs, ys, ws)
    if fit is None:
        base["status"] = "degenerate_airmass_range"
        base["n_standards_used"] = len(standards_pool)
        base["airmass_min"] = min(p["airmass"] for p in standards_pool)
        base["airmass_max"] = max(p["airmass"] for p in standards_pool)
        return base

    residuals = [y - (fit["slope"] * x + fit["intercept"])
                 for x, y in zip(xs, ys)]

    # Iterative MAD-based outlier rejection
    max_passes = int(policy.get("max_rejection_passes", 1))
    k_mad = float(policy["mad_outlier_k"])
    all_flagged = set()
    current_fit = fit
    current_xs = list(xs)
    current_ys = list(ys)
    current_idx = list(range(len(standards_pool)))

    for _pass in range(max_passes):
        current_residuals = [
            y - (current_fit["slope"] * x + current_fit["intercept"])
            for x, y in zip(current_xs, current_ys)]
        med_abs = mad(current_residuals)
        sigma_mad = 1.4826 * med_abs
        if sigma_mad <= 0:
            break
        threshold = k_mad * sigma_mad
        new_flagged_local = set()
        for i, r in enumerate(current_residuals):
            if abs(r) > threshold:
                new_flagged_local.add(i)
        if not new_flagged_local:
            break
        new_flagged_global = {current_idx[i] for i in new_flagged_local}
        candidate_all = all_flagged | new_flagged_global
        candidate_kept = [i for i in range(len(standards_pool))
                          if i not in candidate_all]
        if len(candidate_kept) < min_standards:
            break
        kept_xs = [xs[i] for i in candidate_kept]
        kept_ys = [ys[i] for i in candidate_kept]
        kept_ws = [ws[i] for i in candidate_kept]
        new_fit = weighted_linear_fit(kept_xs, kept_ys, kept_ws)
        if new_fit is None:
            break
        all_flagged = candidate_all
        current_fit = new_fit
        current_xs = kept_xs
        current_ys = kept_ys
        current_idx = candidate_kept

    flagged_idx = all_flagged
    fit = current_fit
    kept_idx = [i for i in range(len(standards_pool)) if i not in flagged_idx]
    res_ws = [ws[i] for i in kept_idx]
    residuals = [ys[i] - (fit["slope"] * xs[i] + fit["intercept"])
                 for i in kept_idx]
    n_used = len(kept_idx)

    residual_std = weighted_population_residual_stddev(residuals, res_ws)

    base["n_standards_used"] = n_used
    base["n_outliers_flagged"] = len(flagged_idx)
    base["extinction_k"] = fit["slope"]
    base["zero_point"] = fit["intercept"]
    base["extinction_k_uncertainty"] = math.sqrt(fit["slope_var"])
    base["zero_point_uncertainty"] = math.sqrt(fit["intercept_var"])
    base["residual_stddev"] = residual_std
    base["airmass_min"] = min(p["airmass"] for p in standards_pool)
    base["airmass_max"] = max(p["airmass"] for p in standards_pool)
    base["status"] = "calibrated"
    base["_outlier_image_ids"] = sorted(standards_pool[i]["image_id"]
                                        for i in flagged_idx)
    base["_standards_pool"] = standards_pool
    base["_kept_pool"] = [standards_pool[i] for i in range(len(standards_pool))
                          if i not in flagged_idx]
    return base


# ---------- Calibrated magnitudes for program & standard stars --------------

def calibrated_magnitudes(calibration_records: dict, data: dict) -> dict:
    """Return {(star_id, filter): list of dicts} for non-excluded stars."""
    excl = data["exclusions"]
    excluded_observations = set(excl.get("excluded_observations", []))
    excluded_stars = set(excl.get("excluded_stars", []))
    sigma_floor = float(data["policy"]["uncertainty_floor_mag"])

    max_airmass = float(data["policy"].get("max_airmass", 99.0))
    by_star = defaultdict(list)
    for night in data["nights"]:
        nid = night["night_id"]
        for o in night["observations"]:
            if o["star_id"] in excluded_stars:
                continue
            if o["image_id"] in excluded_observations:
                continue
            if o["airmass"] > max_airmass:
                continue
            cal = calibration_records.get((nid, o["filter"]))
            if cal is None or cal["status"] != "calibrated":
                continue
            X = o["airmass"]
            sigma = max(o["mag_uncertainty"], sigma_floor)
            k = cal["extinction_k"]
            zp = cal["zero_point"]
            sk = cal["extinction_k_uncertainty"]
            szp = cal["zero_point_uncertainty"]
            m_std = o["instrumental_mag"] - k * X - zp
            sigma_total = math.sqrt(
                sigma * sigma + szp * szp + (X * sk) ** 2
            )
            entry = {
                "image_id": o["image_id"],
                "night_id": nid,
                "star_id": o["star_id"],
                "filter": o["filter"],
                "airmass": X,
                "calibrated_mag": m_std,
                "calibrated_uncertainty": sigma_total,
                "instrumental_mag": o["instrumental_mag"],
                "instrumental_uncertainty": sigma,
            }
            by_star[(o["star_id"], o["filter"])].append(entry)
    return by_star


# ---------- Lightcurves -----------------------------------------------------

def build_lightcurves(by_star_filter: dict, data: dict) -> list[dict]:
    """Build per-(program-star, filter) lightcurves with chi-square test."""
    policy = data["policy"]
    programs = data["programs"]
    instrument = data["instrument"]
    excl = data["exclusions"]
    excluded_stars = set(excl.get("excluded_stars", []))
    min_obs = int(policy["min_observations_per_lightcurve"])
    var_thresh = float(policy["variability_chi2_threshold"])

    rows = []
    for sid, star in programs.items():
        if sid in excluded_stars:
            continue
        for filt in instrument["filters"]:
            obs = sorted(by_star_filter.get((sid, filt), []),
                         key=lambda e: (e["night_id"], e["image_id"]))
            row = {
                "star_id": sid,
                "filter": filt,
                "n_observations": len(obs),
                "n_nights": 0,
                "mean_calibrated_mag": None,
                "stddev_calibrated_mag": None,
                "min_calibrated_mag": None,
                "max_calibrated_mag": None,
                "amplitude_mag": None,
                "chi_squared_reduced": None,
                "is_variable": False,
                "status": "calibrated",
            }
            row["n_nights"] = len({o["night_id"] for o in obs})
            if not obs:
                row["status"] = "no_data"
                rows.append(row)
                continue
            if len(obs) < min_obs:
                row["status"] = "insufficient_observations"
                # still report mean/stddev/range?
                # Per spec, leave min/max/mean filled but mark status.
            mags = [o["calibrated_mag"] for o in obs]
            sigmas = [o["calibrated_uncertainty"] for o in obs]
            row["min_calibrated_mag"] = min(mags)
            row["max_calibrated_mag"] = max(mags)
            row["amplitude_mag"] = max(mags) - min(mags)

            ws = [1.0 / (s * s) if s > 0 else 0.0 for s in sigmas]
            sw = sum(ws)
            if sw > 0:
                wmean = sum(w * m for w, m in zip(ws, mags)) / sw
                row["mean_calibrated_mag"] = wmean
                # Population-style stddev: sqrt(sum w*(m-mean)^2 / sum w)
                var = sum(w * (m - wmean) ** 2 for w, m in zip(ws, mags)) / sw
                row["stddev_calibrated_mag"] = math.sqrt(var)
                if len(obs) >= 2 and row["status"] == "calibrated":
                    chi2 = sum(((m - wmean) / s) ** 2
                               for m, s in zip(mags, sigmas) if s > 0)
                    dof = len(obs) - 1
                    row["chi_squared_reduced"] = chi2 / dof if dof > 0 else None
                    if (row["chi_squared_reduced"] is not None
                            and row["chi_squared_reduced"] > var_thresh):
                        row["is_variable"] = True
            rows.append(row)
    return rows


# ---------- Findings --------------------------------------------------------

def severity_rank(policy: dict, severity: str) -> int:
    return policy["severity_ranks"][severity]


def make_finding(policy: dict, ftype: str, *, severity: str,
                 night_id=None, star_id=None, image_id=None,
                 filter_=None, evidence=None) -> dict:
    return {
        "finding_type": ftype,
        "severity": severity,
        "severity_rank": severity_rank(policy, severity),
        "night_id": night_id,
        "filter": filter_,
        "star_id": star_id,
        "image_id": image_id,
        "evidence": evidence or {},
    }


def build_findings(data: dict, calibration_records: dict,
                   lightcurves: list[dict],
                   by_star_filter: dict) -> list[dict]:
    policy = data["policy"]
    sev = policy["finding_severity"]
    excl = data["exclusions"]
    excluded_nights = set(excl.get("excluded_nights", []))
    excluded_stars = set(excl.get("excluded_stars", []))
    excluded_obs = set(excl.get("excluded_observations", []))
    excluded_filters_per_night = {
        rec["night_id"]: set(rec.get("filters", []))
        for rec in excl.get("excluded_filters_per_night", [])
    }

    findings = []

    for nid in sorted(excluded_nights):
        findings.append(make_finding(policy, "excluded_night",
                                     severity=sev["excluded_night"],
                                     night_id=nid))

    for nid, filts in sorted(excluded_filters_per_night.items()):
        for filt in sorted(filts):
            findings.append(make_finding(
                policy, "excluded_filter",
                severity=sev["excluded_filter"],
                night_id=nid, filter_=filt))

    for sid in sorted(excluded_stars):
        findings.append(make_finding(policy, "excluded_star",
                                     severity=sev["excluded_star"],
                                     star_id=sid))

    for img in sorted(excluded_obs):
        findings.append(make_finding(policy, "excluded_observation",
                                     severity=sev["excluded_observation"],
                                     image_id=img))

    insuf_threshold = float(policy["bad_night_residual_stddev"])
    neg_threshold = float(policy["negative_extinction_threshold"])
    high_unc_thresh = float(policy["large_zero_point_uncertainty"])

    for (nid, filt), cal in sorted(calibration_records.items()):
        if cal["status"] == "insufficient_standards":
            findings.append(make_finding(
                policy, "insufficient_standards",
                severity=sev["insufficient_standards"],
                night_id=nid, filter_=filt,
                evidence={
                    "n_standards_observed": cal["n_standards_used"],
                    "min_required": int(policy["min_standards_per_fit"]),
                    "n_total_observations": cal["n_total_observations"],
                }))
            continue
        if cal["status"] in {"excluded_night", "excluded_filter",
                             "degenerate_airmass_range"}:
            if cal["status"] == "degenerate_airmass_range":
                findings.append(make_finding(
                    policy, "degenerate_airmass_range",
                    severity=sev["degenerate_airmass_range"],
                    night_id=nid, filter_=filt,
                    evidence={
                        "n_standards_observed": cal["n_standards_used"],
                    }))
            continue
        if cal["status"] != "calibrated":
            continue
        if cal["residual_stddev"] > insuf_threshold:
            findings.append(make_finding(
                policy, "bad_night_residuals",
                severity=sev["bad_night_residuals"],
                night_id=nid, filter_=filt,
                evidence={
                    "residual_stddev": r6(cal["residual_stddev"]),
                    "threshold": insuf_threshold,
                    "n_standards_used": cal["n_standards_used"],
                }))
        if cal["extinction_k"] < neg_threshold:
            findings.append(make_finding(
                policy, "negative_extinction",
                severity=sev["negative_extinction"],
                night_id=nid, filter_=filt,
                evidence={
                    "extinction_k": r6(cal["extinction_k"]),
                    "threshold": neg_threshold,
                }))
        if cal["zero_point_uncertainty"] > high_unc_thresh:
            findings.append(make_finding(
                policy, "large_zero_point_uncertainty",
                severity=sev["large_zero_point_uncertainty"],
                night_id=nid, filter_=filt,
                evidence={
                    "zero_point_uncertainty": r6(cal["zero_point_uncertainty"]),
                    "threshold": high_unc_thresh,
                }))
        for img in cal.get("_outlier_image_ids", []):
            findings.append(make_finding(
                policy, "outlier_observation",
                severity=sev["outlier_observation"],
                night_id=nid, filter_=filt, image_id=img,
                evidence={
                    "k_mad": float(policy["mad_outlier_k"]),
                }))

    for row in lightcurves:
        if row["status"] == "no_data":
            findings.append(make_finding(
                policy, "program_star_no_data",
                severity=sev["program_star_no_data"],
                star_id=row["star_id"], filter_=row["filter"]))
        elif row["status"] == "insufficient_observations":
            findings.append(make_finding(
                policy, "insufficient_lightcurve_observations",
                severity=sev["insufficient_lightcurve_observations"],
                star_id=row["star_id"], filter_=row["filter"],
                evidence={
                    "n_observations": row["n_observations"],
                    "min_required": int(
                        policy["min_observations_per_lightcurve"]),
                }))
        elif row["is_variable"]:
            findings.append(make_finding(
                policy, "variable_star_detected",
                severity=sev["variable_star_detected"],
                star_id=row["star_id"], filter_=row["filter"],
                evidence={
                    "chi_squared_reduced": r6(row["chi_squared_reduced"]),
                    "threshold": float(
                        policy["variability_chi2_threshold"]),
                    "amplitude_mag": r6(row["amplitude_mag"]),
                    "n_observations": row["n_observations"],
                }))

    return findings


# ---------- Output assembly -------------------------------------------------

def round_calibration(cal: dict) -> dict:
    return {
        "airmass_max": r6(cal["airmass_max"]),
        "airmass_min": r6(cal["airmass_min"]),
        "extinction_k": r6(cal["extinction_k"]),
        "extinction_k_uncertainty": r6(cal["extinction_k_uncertainty"]),
        "filter": cal["filter"],
        "n_outliers_flagged": cal["n_outliers_flagged"],
        "n_program_observations": cal["n_program_observations"],
        "n_standards_used": cal["n_standards_used"],
        "n_total_observations": cal["n_total_observations"],
        "night_id": cal["night_id"],
        "residual_stddev": r6(cal["residual_stddev"]),
        "status": cal["status"],
        "zero_point": r6(cal["zero_point"]),
        "zero_point_uncertainty": r6(cal["zero_point_uncertainty"]),
    }


def round_lightcurve(row: dict) -> dict:
    return {
        "amplitude_mag": r6(row["amplitude_mag"]),
        "chi_squared_reduced": r6(row["chi_squared_reduced"]),
        "filter": row["filter"],
        "is_variable": row["is_variable"],
        "max_calibrated_mag": r6(row["max_calibrated_mag"]),
        "mean_calibrated_mag": r6(row["mean_calibrated_mag"]),
        "min_calibrated_mag": r6(row["min_calibrated_mag"]),
        "n_nights": row["n_nights"],
        "n_observations": row["n_observations"],
        "star_id": row["star_id"],
        "status": row["status"],
        "stddev_calibrated_mag": r6(row["stddev_calibrated_mag"]),
    }


def build_report(data_dir: Path, out_path: Path) -> dict:
    data = load_inputs(data_dir)

    # Build calibration records keyed by (night, filter)
    jobs = build_calibration_jobs(data)
    cal_records: dict = {}
    for job in jobs:
        cal = fit_extinction(job, data)
        cal_records[(job["night_id"], job["filter"])] = cal

    by_star_filter = calibrated_magnitudes(cal_records, data)

    # Count program-star observations per (night, filter)
    excl = data["exclusions"]
    excluded_stars = set(excl.get("excluded_stars", []))
    excluded_obs = set(excl.get("excluded_observations", []))
    max_am = float(data["policy"].get("max_airmass", 99.0))
    program_ids = set(data["programs"].keys())
    for night in data["nights"]:
        nid = night["night_id"]
        for o in night["observations"]:
            if o["star_id"] in excluded_stars or o["image_id"] in excluded_obs:
                continue
            if o["airmass"] > max_am:
                continue
            if o["star_id"] not in program_ids:
                continue
            cal = cal_records.get((nid, o["filter"]))
            if cal and cal["status"] == "calibrated":
                cal["n_program_observations"] += 1

    lightcurves = build_lightcurves(by_star_filter, data)

    findings = build_findings(data, cal_records, lightcurves, by_star_filter)

    # Sort calibrations by (night_id, filter)
    cal_rows = [round_calibration(cal_records[k])
                for k in sorted(cal_records.keys())]

    # Sort lightcurves by (star_id, filter)
    lc_rows = [round_lightcurve(r)
               for r in sorted(lightcurves, key=lambda r: (r["star_id"], r["filter"]))]

    # Sort findings by severity_rank desc, then finding_type, night_id, filter,
    # star_id, image_id ascending; nulls treated as empty strings
    def fkey(f):
        return (-f["severity_rank"], f["finding_type"],
                f["night_id"] or "", f["filter"] or "",
                f["star_id"] or "", f["image_id"] or "")
    findings_sorted = sorted(findings, key=fkey)

    # Round and project finding evidence (keys already plain types)
    def round_finding(f):
        return {
            "evidence": f["evidence"],
            "filter": f["filter"],
            "finding_type": f["finding_type"],
            "image_id": f["image_id"],
            "night_id": f["night_id"],
            "severity": f["severity"],
            "severity_rank": f["severity_rank"],
            "star_id": f["star_id"],
        }
    finding_rows = [round_finding(f) for f in findings_sorted]

    # Summary
    total_nights = len(data["nights"])
    unique_excluded_nights = len({k[0] for k, c in cal_records.items()
                                  if c["status"] == "excluded_night"})
    calibrated_pairs = sum(1 for c in cal_records.values()
                           if c["status"] == "calibrated")
    insufficient_pairs = sum(1 for c in cal_records.values()
                             if c["status"] == "insufficient_standards")
    total_observations = sum(len(n["observations"]) for n in data["nights"])
    used_standard_observations = sum(c["n_standards_used"]
                                     for c in cal_records.values()
                                     if c["status"] == "calibrated")
    used_program_observations = sum(c["n_program_observations"]
                                    for c in cal_records.values()
                                    if c["status"] == "calibrated")
    flagged_outliers = sum(c["n_outliers_flagged"]
                           for c in cal_records.values()
                           if c["status"] == "calibrated")
    variable_stars = sum(1 for r in lightcurves if r["is_variable"])

    by_severity = {s: 0 for s in SEVERITIES}
    for f in findings:
        by_severity[f["severity"]] += 1
    by_type = dict(sorted(Counter(f["finding_type"] for f in findings).items()))

    summary = {
        "by_finding_type": by_type,
        "by_severity": by_severity,
        "calibrated_pairs": calibrated_pairs,
        "excluded_nights": unique_excluded_nights,
        "findings_count": len(findings),
        "flagged_outliers": flagged_outliers,
        "insufficient_pairs": insufficient_pairs,
        "lightcurves_count": len(lightcurves),
        "total_nights": total_nights,
        "total_observations": total_observations,
        "used_program_observations": used_program_observations,
        "used_standard_observations": used_standard_observations,
        "variable_stars": variable_stars,
    }

    report = {
        "findings": finding_rows,
        "per_night_calibration": cal_rows,
        "per_star_lightcurves": lc_rows,
        "schema_version": 1,
        "summary": summary,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="/app/data")
    parser.add_argument("--out", default="/app/output/photometry_report.json")
    args = parser.parse_args()
    build_report(Path(args.data), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
