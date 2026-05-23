from __future__ import annotations

import json
import math
from itertools import combinations
from pathlib import Path
from typing import Any

import sys

BASE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    __import__("os").environ.get("DTC_APP_DETECTOR", "/app/detector")
)


def load_json(name: str) -> Any:
    return json.loads((BASE / name).read_text(encoding="utf-8"))


def round6(x: float) -> float:
    if x is None:
        return None
    if isinstance(x, bool):
        return x
    if math.isnan(x) or math.isinf(x):
        return x
    return round(float(x), 6)


def population_stddev(values: list[float], mean: float) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def fit_wls(xs: list[float], ys: list[float], ws: list[float]) -> tuple[float, float, float]:
    """Weighted-OLS fit. Returns (slope, offset, weighted_population_residual_stddev).

    Formulas with S = sum(w_i):
      x̄_w = sum(w_i x_i) / S
      ȳ_w = sum(w_i y_i) / S
      slope = sum(w_i (x_i − x̄_w)(y_i − ȳ_w)) / sum(w_i (x_i − x̄_w)^2)
      offset = ȳ_w − slope · x̄_w
      residual_stddev = sqrt(sum(w_i (y_i − slope x_i − offset)^2) / S)

    If S == 0, treat as degenerate (slope=0, offset=0, rstd=0). If the
    weighted variance of x is zero we fall back to slope=0, offset=ȳ_w."""
    sw = sum(ws)
    if sw == 0.0:
        return 0.0, 0.0, 0.0
    mx = sum(w * x for w, x in zip(ws, xs)) / sw
    my = sum(w * y for w, y in zip(ws, ys)) / sw
    num = sum(w * (x - mx) * (y - my) for w, x, y in zip(ws, xs, ys))
    den = sum(w * (x - mx) ** 2 for w, x in zip(ws, xs))
    if den == 0.0:
        slope, offset = 0.0, my
    else:
        slope = num / den
        offset = my - slope * mx
    sse = sum(w * (y - (slope * x + offset)) ** 2 for w, x, y in zip(ws, xs, ys))
    return slope, offset, math.sqrt(sse / sw)


def iterative_wls(
    points: list[tuple[float, float, float]], k_sigma: float, max_iter: int
) -> tuple[float, float, float, int, int, list[int]]:
    """Iterative weighted-OLS with k-sigma rejection of reference points.

    Returns (slope, offset, residual_stddev, n_outliers_removed,
             iterations_used, kept_indices).

    Each iteration performs one weighted fit on the currently kept indices,
    then drops every kept point whose |residual| exceeds k_sigma *
    weighted-population residual_stddev.  Stops when no point is dropped,
    when fewer than two points would remain, when residual_stddev == 0, or
    after max_iter iterations.  iterations_used counts every fit performed,
    so iterations_used == 1 means a single fit with no rejections.
    """
    kept = list(range(len(points)))
    iters = 0
    slope = 1.0
    offset = 0.0
    rstd = 0.0
    while iters < max_iter:
        iters += 1
        xs = [points[i][0] for i in kept]
        ys = [points[i][1] for i in kept]
        ws = [points[i][2] for i in kept]
        slope, offset, rstd = fit_wls(xs, ys, ws)
        if rstd == 0.0:
            break
        threshold = k_sigma * rstd
        new_kept = [
            i for i in kept
            if abs(points[i][1] - (slope * points[i][0] + offset)) <= threshold
        ]
        if len(new_kept) < 2 or len(new_kept) == len(kept):
            kept = new_kept if len(new_kept) >= 2 else kept
            break
        kept = new_kept
    n_removed = len(points) - len(kept)
    return slope, offset, rstd, n_removed, iters, kept


def read_trace(run_id: str) -> list[tuple[str, str, float]]:
    rows: list[tuple[str, str, float]] = []
    p = BASE / "runs" / f"{run_id}.tsv"
    with p.open(encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            rows.append((parts[0], parts[1], float(parts[2])))
    return rows


def main() -> None:
    policy = load_json("policy.json")
    channels_cfg = load_json("channels.json")
    cal_cfg = load_json("calibration.json")
    expected_signals = load_json("expected_signals.json")
    manifest = load_json("manifest.json")
    exclusions = load_json("exclusions.json")

    min_pts = int(policy["min_calibration_points"])
    k_sigma = float(policy["outlier_k_sigma"])
    max_iter = int(policy["outlier_max_iterations"])
    residual_warn = float(policy["residual_warning_threshold"])
    sig_tol = float(policy["signal_match_tolerance"])
    sig_dev_warn = float(policy["signal_deviation_warning_threshold"])
    drift_max_dev = float(policy["drift_max_deviation_threshold"])
    drift_stddev = float(policy["drift_stddev_threshold"])
    z_threshold = float(policy["event_anomaly_z_threshold"])
    anomaly_min_events = int(policy["anomaly_min_events"])
    burst_threshold = int(policy["anomaly_burst_threshold"])
    min_corr_runs = int(policy["min_correlation_runs"])
    corr_threshold = float(policy["cross_channel_corr_threshold"])
    min_health = float(policy["min_run_health"])

    channel_ids = sorted(c["channel_id"] for c in channels_cfg["channels"])
    excluded_channels = set(exclusions["channels"])
    excluded_runs = set(exclusions["runs"])
    excluded_signals = set(exclusions["signals"])

    # ------------------------------------------------------------------
    # Per-channel calibration with iterative weighted outlier rejection
    # ------------------------------------------------------------------
    calib: dict[str, dict[str, Any]] = {}
    for cid in channel_ids:
        refs = cal_cfg["references"].get(cid, [])
        n_ref = len(refs)
        if cid in excluded_channels:
            calib[cid] = {
                "channel_id": cid,
                "n_reference_points": n_ref,
                "slope": 1.0,
                "offset": 0.0,
                "residual_stddev": 0.0,
                "n_outliers_removed": 0,
                "iterations_used": 0,
                "status": "excluded",
            }
            continue
        if n_ref < min_pts:
            calib[cid] = {
                "channel_id": cid,
                "n_reference_points": n_ref,
                "slope": 1.0,
                "offset": 0.0,
                "residual_stddev": 0.0,
                "n_outliers_removed": 0,
                "iterations_used": 0,
                "status": "insufficient_points",
            }
            continue
        pts = [(float(r["raw"]), float(r["true"]), float(r["weight"])) for r in refs]
        slope, offset, rstd, n_out, iters, _kept = iterative_wls(pts, k_sigma, max_iter)
        calib[cid] = {
            "channel_id": cid,
            "n_reference_points": n_ref,
            "slope": slope,
            "offset": offset,
            "residual_stddev": rstd,
            "n_outliers_removed": n_out,
            "iterations_used": iters,
            "status": "calibrated",
        }

    # ------------------------------------------------------------------
    # Apply calibration to each event in each run
    # ------------------------------------------------------------------
    run_ids = [r["run_id"] for r in manifest["runs"]]
    sorted_run_ids = sorted(run_ids)

    per_run_per_chan: dict[str, dict[str, list[float]]] = {}
    for rid in run_ids:
        per_run_per_chan[rid] = {}
        if rid in excluded_runs:
            continue
        for _eid, ch, raw in read_trace(rid):
            if ch in excluded_channels:
                continue
            if ch not in calib:
                continue
            c = calib[ch]
            cal = c["slope"] * raw + c["offset"]
            per_run_per_chan[rid].setdefault(ch, []).append(cal)

    # ------------------------------------------------------------------
    # Per-run summary (with anomaly counts and health score)
    # ------------------------------------------------------------------
    per_run_summary: list[dict[str, Any]] = []
    anomaly_findings_inputs: list[dict[str, Any]] = []
    health_findings_inputs: list[dict[str, Any]] = []

    for rid in sorted_run_ids:
        if rid in excluded_runs:
            per_run_summary.append({
                "run_id": rid,
                "status": "excluded",
                "n_events_total": 0,
                "event_counts_per_channel": {},
                "mean_calibrated_per_channel": {},
                "n_anomalous_events_per_channel": {},
                "total_anomalous_events": 0,
                "health_score": None,
            })
            continue

        per_chan_vals = per_run_per_chan.get(rid, {})
        counts: dict[str, int] = {}
        means: dict[str, float] = {}
        anoms: dict[str, int] = {}
        for cid in sorted(per_chan_vals.keys()):
            vals = per_chan_vals[cid]
            n = len(vals)
            if n == 0:
                continue
            counts[cid] = n
            mean = sum(vals) / n
            means[cid] = round6(mean)
            if n >= anomaly_min_events:
                sd = population_stddev(vals, mean)
                if sd > 0:
                    n_anom = sum(1 for v in vals if abs(v - mean) > z_threshold * sd)
                    if n_anom > 0:
                        anoms[cid] = n_anom
                        if n_anom >= burst_threshold:
                            anomaly_findings_inputs.append({
                                "run_id": rid,
                                "channel_id": cid,
                                "n_anomalous": n_anom,
                                "n_events_in_channel": n,
                                "z_threshold": z_threshold,
                                "burst_threshold": burst_threshold,
                            })

        n_events_total = sum(counts.values())
        total_anom = sum(anoms.values())
        health = 1.0 - (total_anom / n_events_total if n_events_total > 0 else 0.0)
        health = round6(health)
        if health is not None and health < min_health:
            health_findings_inputs.append({
                "run_id": rid,
                "health_score": health,
                "threshold": min_health,
                "n_anomalous_events": total_anom,
                "n_events_total": n_events_total,
            })

        per_run_summary.append({
            "run_id": rid,
            "status": "active",
            "n_events_total": n_events_total,
            "event_counts_per_channel": counts,
            "mean_calibrated_per_channel": means,
            "n_anomalous_events_per_channel": anoms,
            "total_anomalous_events": total_anom,
            "health_score": health,
        })

    # ------------------------------------------------------------------
    # Signal assignments
    # ------------------------------------------------------------------
    signal_assignments: list[dict[str, Any]] = []
    for s in expected_signals["signals"]:
        sid = s["signal_id"]
        rid = s["run_id"]
        cid = s["channel_id"]
        exp_val = float(s["expected_value"])

        is_excluded = (
            sid in excluded_signals
            or rid in excluded_runs
            or cid in excluded_channels
            or cid not in calib
            or calib[cid]["status"] != "calibrated"
        )
        row = {
            "signal_id": sid,
            "run_id": rid,
            "channel_id": cid,
            "expected_value": round6(exp_val),
        }
        if is_excluded:
            row["status"] = "excluded"
            row["n_matches"] = 0
            row["mean_calibrated_value"] = None
            row["deviation"] = None
        else:
            vals = per_run_per_chan.get(rid, {}).get(cid, [])
            matches = [v for v in vals if abs(v - exp_val) <= sig_tol]
            if not matches:
                row["status"] = "missing"
                row["n_matches"] = 0
                row["mean_calibrated_value"] = None
                row["deviation"] = None
            else:
                m = sum(matches) / len(matches)
                row["status"] = "matched"
                row["n_matches"] = len(matches)
                row["mean_calibrated_value"] = round6(m)
                row["deviation"] = round6(m - exp_val)
        signal_assignments.append(row)
    signal_assignments.sort(key=lambda r: (r["signal_id"], r["run_id"]))

    # ------------------------------------------------------------------
    # Channel drift summary (for calibrated channels only)
    # ------------------------------------------------------------------
    channel_drift_summary: list[dict[str, Any]] = []
    drift_per_channel_means: dict[str, list[tuple[str, float]]] = {}
    for cid in channel_ids:
        if calib[cid]["status"] != "calibrated":
            continue
        per_run_means: list[tuple[str, float]] = []
        for rid in sorted_run_ids:
            if rid in excluded_runs:
                continue
            vals = per_run_per_chan.get(rid, {}).get(cid, [])
            if not vals:
                continue
            per_run_means.append((rid, sum(vals) / len(vals)))
        drift_per_channel_means[cid] = per_run_means
        if not per_run_means:
            channel_drift_summary.append({
                "channel_id": cid,
                "n_runs_with_events": 0,
                "mean_across_runs": 0.0,
                "stddev_across_runs": 0.0,
                "max_run_deviation": 0.0,
                "drift_status": "stable",
            })
            continue
        vals = [m for _r, m in per_run_means]
        mean = sum(vals) / len(vals)
        sd = population_stddev(vals, mean)
        max_dev = max(abs(v - mean) for v in vals)
        status = "drifting" if (max_dev > drift_max_dev or sd > drift_stddev) else "stable"
        channel_drift_summary.append({
            "channel_id": cid,
            "n_runs_with_events": len(per_run_means),
            "mean_across_runs": round6(mean),
            "stddev_across_runs": round6(sd),
            "max_run_deviation": round6(max_dev),
            "drift_status": status,
        })
    channel_drift_summary.sort(key=lambda r: r["channel_id"])

    # ------------------------------------------------------------------
    # Channel correlation matrix
    # ------------------------------------------------------------------
    channel_correlation_matrix: list[dict[str, Any]] = []
    correlation_findings_inputs: list[dict[str, Any]] = []
    cal_channels = [cid for cid in channel_ids if calib[cid]["status"] == "calibrated"]
    for ca, cb in combinations(cal_channels, 2):
        ma = dict(drift_per_channel_means.get(ca, []))
        mb = dict(drift_per_channel_means.get(cb, []))
        common_runs = sorted(set(ma) & set(mb))
        if len(common_runs) < min_corr_runs:
            continue
        xs = [ma[r] for r in common_runs]
        ys = [mb[r] for r in common_runs]
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sxx = sum((x - mx) ** 2 for x in xs)
        syy = sum((y - my) ** 2 for y in ys)
        if sxx == 0 or syy == 0:
            r = 0.0
        else:
            r = sxy / math.sqrt(sxx * syy)
        channel_correlation_matrix.append({
            "channel_a": ca,
            "channel_b": cb,
            "n_runs": n,
            "pearson_r": round6(r),
        })
        if abs(r) > corr_threshold:
            correlation_findings_inputs.append({
                "channel_a": ca,
                "channel_b": cb,
                "pearson_r": round6(r),
                "threshold": corr_threshold,
                "n_runs": n,
            })
    channel_correlation_matrix.sort(key=lambda r: (r["channel_a"], r["channel_b"]))

    # ------------------------------------------------------------------
    # Quality findings
    # ------------------------------------------------------------------
    findings: list[dict[str, Any]] = []

    def add_finding(
        ftype: str,
        severity: str,
        rank: int,
        subject: str,
        channel_id: Any,
        run_id: Any,
        signal_id: Any,
        evidence: dict[str, Any],
    ) -> None:
        findings.append({
            "finding_type": ftype,
            "severity": severity,
            "severity_rank": rank,
            "subject": subject,
            "channel_id": channel_id,
            "run_id": run_id,
            "signal_id": signal_id,
            "evidence": evidence,
        })

    # Calibration findings
    for cid in channel_ids:
        c = calib[cid]
        if c["status"] == "insufficient_points":
            add_finding(
                "insufficient_calibration_points", "high", 3, "channel", cid, None, None,
                {"n_reference_points": c["n_reference_points"], "min_required": min_pts},
            )
        elif c["status"] == "calibrated":
            if c["residual_stddev"] > residual_warn:
                add_finding(
                    "large_calibration_residual", "high", 3, "channel", cid, None, None,
                    {
                        "residual_stddev": round6(c["residual_stddev"]),
                        "threshold": round6(residual_warn),
                        "slope": round6(c["slope"]),
                        "offset": round6(c["offset"]),
                    },
                )
            if c["n_outliers_removed"] > 0:
                add_finding(
                    "outliers_rejected_in_calibration", "info", 0, "channel", cid, None, None,
                    {
                        "n_outliers_removed": c["n_outliers_removed"],
                        "k_sigma": round6(k_sigma),
                        "iterations_used": c["iterations_used"],
                    },
                )

    # Signal findings (after assignments are sorted)
    for sa in signal_assignments:
        if sa["status"] == "missing":
            add_finding(
                "signal_missing", "medium", 2, "signal", sa["channel_id"], sa["run_id"], sa["signal_id"],
                {"expected_value": round6(sa["expected_value"]), "tolerance": round6(sig_tol), "n_matches": 0},
            )
        elif sa["status"] == "matched":
            dev = sa["deviation"]
            if dev is not None and abs(dev) > sig_dev_warn:
                add_finding(
                    "signal_value_mismatch", "high", 3, "signal",
                    sa["channel_id"], sa["run_id"], sa["signal_id"],
                    {
                        "expected_value": round6(sa["expected_value"]),
                        "mean_calibrated_value": round6(sa["mean_calibrated_value"]),
                        "deviation": round6(dev),
                        "threshold": round6(sig_dev_warn),
                        "n_matches": sa["n_matches"],
                    },
                )

    # Drift findings
    for d in channel_drift_summary:
        if d["drift_status"] == "drifting":
            add_finding(
                "channel_drifting", "critical", 4, "channel", d["channel_id"], None, None,
                {
                    "max_run_deviation": round6(d["max_run_deviation"]),
                    "stddev_across_runs": round6(d["stddev_across_runs"]),
                    "max_deviation_threshold": round6(drift_max_dev),
                    "stddev_threshold": round6(drift_stddev),
                    "n_runs_with_events": d["n_runs_with_events"],
                },
            )

    # Anomaly burst findings (subject = run)
    for af in anomaly_findings_inputs:
        add_finding(
            "anomalous_event_burst", "high", 3, "run",
            af["channel_id"], af["run_id"], None,
            {
                "n_anomalous": af["n_anomalous"],
                "n_events_in_channel": af["n_events_in_channel"],
                "z_threshold": round6(af["z_threshold"]),
                "burst_threshold": af["burst_threshold"],
            },
        )

    # Low run health findings
    for hf in health_findings_inputs:
        add_finding(
            "low_run_health", "high", 3, "run", None, hf["run_id"], None,
            {
                "health_score": round6(hf["health_score"]),
                "threshold": round6(hf["threshold"]),
                "n_anomalous_events": hf["n_anomalous_events"],
                "n_events_total": hf["n_events_total"],
            },
        )

    # Correlation findings
    for cf in correlation_findings_inputs:
        add_finding(
            "unexpected_channel_correlation", "medium", 2, "channel",
            cf["channel_a"], None, None,
            {
                "channel_a": cf["channel_a"],
                "channel_b": cf["channel_b"],
                "pearson_r": round6(cf["pearson_r"]),
                "threshold": round6(cf["threshold"]),
                "n_runs": cf["n_runs"],
            },
        )

    # Excluded findings
    for cid in channel_ids:
        if cid in excluded_channels:
            add_finding("excluded_channel", "info", 0, "channel", cid, None, None, {})
    for rid in sorted_run_ids:
        if rid in excluded_runs:
            add_finding("excluded_run", "info", 0, "run", None, rid, None, {})
    for s in sorted(expected_signals["signals"], key=lambda x: x["signal_id"]):
        if s["signal_id"] in excluded_signals:
            add_finding(
                "excluded_signal", "info", 0, "signal",
                s["channel_id"], s["run_id"], s["signal_id"], {},
            )

    # Sort findings
    findings.sort(key=lambda f: (
        -f["severity_rank"],
        f["finding_type"],
        f["channel_id"] or "",
        f["run_id"] or "",
        f["signal_id"] or "",
    ))

    # ------------------------------------------------------------------
    # Per-channel calibration output (rounded)
    # ------------------------------------------------------------------
    per_channel_calibration: list[dict[str, Any]] = []
    for cid in channel_ids:
        c = calib[cid]
        per_channel_calibration.append({
            "channel_id": cid,
            "n_reference_points": c["n_reference_points"],
            "slope": round6(c["slope"]),
            "offset": round6(c["offset"]),
            "residual_stddev": round6(c["residual_stddev"]),
            "n_outliers_removed": c["n_outliers_removed"],
            "iterations_used": c["iterations_used"],
            "status": c["status"],
        })

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    by_sev = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    by_type: dict[str, int] = {}
    for f in findings:
        by_sev[f["severity"]] += 1
        by_type[f["finding_type"]] = by_type.get(f["finding_type"], 0) + 1

    total_events_processed = sum(r["n_events_total"] for r in per_run_summary)
    calibrated_channels = sum(1 for c in calib.values() if c["status"] == "calibrated")
    excluded_runs_count = sum(1 for rid in run_ids if rid in excluded_runs)
    active_runs = len(run_ids) - excluded_runs_count
    total_anomalous_events = sum(r["total_anomalous_events"] for r in per_run_summary)

    summary = {
        "total_channels": len(channel_ids),
        "calibrated_channels": calibrated_channels,
        "total_runs": len(run_ids),
        "active_runs": active_runs,
        "excluded_runs": excluded_runs_count,
        "total_events_processed": total_events_processed,
        "total_anomalous_events": total_anomalous_events,
        "per_channel_calibration_count": len(per_channel_calibration),
        "per_run_summary_count": len(per_run_summary),
        "signal_assignments_count": len(signal_assignments),
        "channel_drift_summary_count": len(channel_drift_summary),
        "channel_correlation_matrix_count": len(channel_correlation_matrix),
        "quality_findings_count": len(findings),
        "by_severity": by_sev,
        "by_finding_type": by_type,
    }

    report = {
        "schema_version": 1,
        "summary": summary,
        "per_channel_calibration": per_channel_calibration,
        "per_run_summary": per_run_summary,
        "signal_assignments": signal_assignments,
        "channel_drift_summary": channel_drift_summary,
        "channel_correlation_matrix": channel_correlation_matrix,
        "quality_findings": findings,
    }

    out_path = BASE / "report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes, {len(findings)} findings)")


if __name__ == "__main__":
    main()