"""End-to-end pytest suite for the detector telemetry calibration task.

The tests are deliberately *input-driven*: every expected value is
recomputed from the raw fixture files (`/app/detector/*`) at test time,
so swapping the dataset or perturbing thresholds in `policy.json` will
make the suite still validate the algorithm rather than a frozen golden
output.  Constants asserted here come from the input files themselves
(channel ids, run ids, signal ids, exclusion sets, the SHA-256 of every
fixture file).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from itertools import combinations
import os
from pathlib import Path
from typing import Any

DETECTOR_DIR = Path(os.environ.get("DTC_APP_DETECTOR", "/app/detector"))
REPORT_FILE = DETECTOR_DIR / "report.json"

FIXTURE_HASHES: dict[str, str] = {
    "calibration.json":      "cbdd8df13e8258d27bd611664a99f6a9a58d90cbd8f5df911ced62a40638ba24",
    "channels.json":         "0e99756d97c6648ad2eb9d3f5a0f177c3e721c01374c937b3987ef981dada63e",
    "exclusions.json":       "d4a9668e8f4c2950a1bb33b985a2032e8c0b258634b1d7bfd4b8b5053b2061d7",
    "expected_signals.json": "e9caa716eeb8b55917cfaeddbe660e141b8732d36c8a5f8ceb4d6fb559ede732",
    "manifest.json":         "cc8b4881fa786780565a4835b0369e68df144993e003a6174325debbbdb9652c",
    "policy.json":           "3b7154a241181faa51e8cd5d1259c118a28d8b9bc62530582675f0ef5a3e556c",
    "runs/run_001.tsv":      "94a597051123d74e3455df112ecf54c622f43dc1a9dc6582ef7869e7b1bd6f9d",
    "runs/run_002.tsv":      "b066c5814e20472e4fef7081c0b22d4596b349a3f84d2dcba5af47fd087a58ac",
    "runs/run_003.tsv":      "28251c6205691f2e8c74efeed2f1e2aa0b3151c2c6972bd67416e5db1d6c93ec",
    "runs/run_004.tsv":      "a170f024ea30df9a21cb1efc0f05c7cfa551bf05fcf90c391c2b57f7b0ab2996",
    "runs/run_005.tsv":      "9f694283f090350d598951b0456971bb430b507898897c5d63ae26ebf24babf8",
    "runs/run_006.tsv":      "98307ed03ebc038593d7fdb0299d5ab868da0a099344c7ebe5851dacd1d1cc69",
    "runs/run_007.tsv":      "d224494b18284d5a5b2c4aebb673a469f23b82caa37d047741d956a189445933",
    "runs/run_008.tsv":      "2fb4e34a834257967283691b56924f3a8d9d001ed077c3a9edd65e78cf9519d1",
    "runs/run_009.tsv":      "622bed5c007c0e83c2b5c9c9be510a41e1c1f349e1552a46e54445897f4a6d74",
    "runs/run_010.tsv":      "1b0813ccd7f6cb873643168220cb408a76ba29d7d57f4a9eee8a0d69e7537586",
    "runs/run_011.tsv":      "d702719d7019ce052d15bbe61beb2c2157823259a62f595130619c5a911b458d",
    "runs/run_012.tsv":      "460d73994e3ee478c6862f9d241b34b01fe557c9542c8dd42194d6a5367053f9",
    "runs/run_013.tsv":      "130d6a14a88a6a95136ce47e68a7d22f0e7cc7ab339aff9b67641e2340ccb75b",
    "runs/run_014.tsv":      "32cc985728eecd98c5f4fb7096ebc41ceec31c8c56e28ae739453abfe7cc02e8",
    "runs/run_015.tsv":      "931fb5f3e0473341afc3470cc1c86e098586c79d2b2c56c7303ed1b111ab3486",
    "runs/run_016.tsv":      "693b49cf719370a89f5c245434b92efe7c860346028a6200bab90613ca394150",
    "runs/run_017.tsv":      "78e447d97e25452982788f124497140e0e2fb25179a524f535c5b83ff7c3284e",
    "runs/run_018.tsv":      "3410542b4913ae915269714ca0799732b05293ad1004d89a81c01caab3417c0c",
    "runs/run_019.tsv":      "1d7fad7380a30cae76aa22e7f4da0874e04c3038a8cbaebefc27ff899499618b",
    "runs/run_020.tsv":      "d63af5b9e1109b972ab5162b621a84c8e9d09c7fd542f80bf5974d20a23a6caa",
    "runs/run_021.tsv":      "a3e6afbeff39870e5ab85c17c3f848136c9ef92c286068dc513f0272713aa0c2",
    "runs/run_022.tsv":      "56d5a9a056c8d4af38583cb016a67874b38016abb17f1824944c71cf035c8142",
}

TOP_LEVEL_KEYS = frozenset({
    "schema_version",
    "summary",
    "per_channel_calibration",
    "per_run_summary",
    "signal_assignments",
    "channel_drift_summary",
    "channel_correlation_matrix",
    "quality_findings",
})

SUMMARY_KEYS = frozenset({
    "total_channels",
    "calibrated_channels",
    "total_runs",
    "active_runs",
    "excluded_runs",
    "total_events_processed",
    "total_anomalous_events",
    "per_channel_calibration_count",
    "per_run_summary_count",
    "signal_assignments_count",
    "channel_drift_summary_count",
    "channel_correlation_matrix_count",
    "quality_findings_count",
    "by_severity",
    "by_finding_type",
})

CALIBRATION_ROW_KEYS = frozenset({
    "channel_id", "n_reference_points", "slope", "offset",
    "residual_stddev", "n_outliers_removed", "iterations_used", "status",
})

PER_RUN_ROW_KEYS = frozenset({
    "run_id", "status", "n_events_total",
    "event_counts_per_channel", "mean_calibrated_per_channel",
    "n_anomalous_events_per_channel", "total_anomalous_events", "health_score",
})

SIGNAL_ROW_KEYS = frozenset({
    "signal_id", "run_id", "channel_id", "expected_value",
    "status", "n_matches", "mean_calibrated_value", "deviation",
})

DRIFT_ROW_KEYS = frozenset({
    "channel_id", "n_runs_with_events", "mean_across_runs",
    "stddev_across_runs", "max_run_deviation", "drift_status",
})

CORRELATION_ROW_KEYS = frozenset({
    "channel_a", "channel_b", "n_runs", "pearson_r",
})

FINDING_KEYS = frozenset({
    "finding_type", "severity", "severity_rank", "subject",
    "channel_id", "run_id", "signal_id", "evidence",
})

ALL_FINDING_TYPES = frozenset({
    "insufficient_calibration_points",
    "large_calibration_residual",
    "outliers_rejected_in_calibration",
    "signal_missing",
    "signal_value_mismatch",
    "channel_drifting",
    "anomalous_event_burst",
    "low_run_health",
    "unexpected_channel_correlation",
    "excluded_channel",
    "excluded_run",
    "excluded_signal",
})

EVIDENCE_KEYS = {
    "insufficient_calibration_points":  frozenset({"n_reference_points", "min_required"}),
    "large_calibration_residual":       frozenset({"residual_stddev", "threshold", "slope", "offset"}),
    "outliers_rejected_in_calibration": frozenset({"n_outliers_removed", "k_sigma", "iterations_used"}),
    "signal_missing":                   frozenset({"expected_value", "tolerance", "n_matches"}),
    "signal_value_mismatch":            frozenset({"expected_value", "mean_calibrated_value", "deviation", "threshold", "n_matches"}),
    "channel_drifting":                 frozenset({"max_run_deviation", "stddev_across_runs", "max_deviation_threshold", "stddev_threshold", "n_runs_with_events"}),
    "anomalous_event_burst":            frozenset({"n_anomalous", "n_events_in_channel", "z_threshold", "burst_threshold"}),
    "low_run_health":                   frozenset({"health_score", "threshold", "n_anomalous_events", "n_events_total"}),
    "unexpected_channel_correlation":   frozenset({"channel_a", "channel_b", "pearson_r", "threshold", "n_runs"}),
    "excluded_channel":                 frozenset(),
    "excluded_run":                     frozenset(),
    "excluded_signal":                  frozenset(),
}

EXCLUDED_EVIDENCE_TYPES = frozenset({"excluded_channel", "excluded_run", "excluded_signal"})

# Canonical subject for every finding type — used by test_32 to lock in the
# spec disambiguation that anomalous_event_burst is attributed to the run.
CANONICAL_SUBJECTS: dict[str, str] = {
    "insufficient_calibration_points":  "channel",
    "large_calibration_residual":       "channel",
    "outliers_rejected_in_calibration": "channel",
    "signal_missing":                   "signal",
    "signal_value_mismatch":            "signal",
    "channel_drifting":                 "channel",
    "anomalous_event_burst":            "run",
    "low_run_health":                   "run",
    "unexpected_channel_correlation":   "channel",
    "excluded_channel":                 "channel",
    "excluded_run":                     "run",
    "excluded_signal":                  "signal",
}

FLOAT_TOL = 1e-4


# ---------------------------------------------------------------------------
# Helpers and reference computation
# ---------------------------------------------------------------------------
def _read_input_json(name: str) -> Any:
    return json.loads((DETECTOR_DIR / name).read_text(encoding="utf-8"))


def _read_trace(run_id: str) -> list[tuple[str, str, float]]:
    out: list[tuple[str, str, float]] = []
    with (DETECTOR_DIR / "runs" / f"{run_id}.tsv").open(encoding="utf-8") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            out.append((parts[0], parts[1], float(parts[2])))
    return out


def load_report() -> dict[str, Any]:
    return json.loads(REPORT_FILE.read_text(encoding="utf-8"))


def chan_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["channel_id"]: row for row in rows}


def run_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["run_id"]: row for row in rows}


def signal_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["signal_id"]: row for row in rows}


def findings_by(report: dict[str, Any], **criteria: Any) -> list[dict[str, Any]]:
    return [
        f for f in report["quality_findings"]
        if all(f.get(k) == v for k, v in criteria.items())
    ]


def one_finding(report: dict[str, Any], **criteria: Any) -> dict[str, Any]:
    rows = findings_by(report, **criteria)
    assert len(rows) == 1, f"expected exactly 1 finding for {criteria}, got {rows}"
    return rows[0]


def _population_stddev(values: list[float], mean: float) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _wls(xs: list[float], ys: list[float], ws: list[float]) -> tuple[float, float, float]:
    """Weighted least-squares fit. Returns (slope, offset, weighted_population_rstd).

    Weighted means use S = Σwᵢ; the residual stddev denominator is S, not N.
    """
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


def _iterative_wls(
    points: list[tuple[float, float, float]], k_sigma: float, max_iter: int
) -> tuple[float, float, float, int, int]:
    """Reference iterative-rejection WLS — returns (slope, offset, rstd, n_removed, iters).

    Each iteration performs one weighted fit on the currently kept indices,
    then drops every kept point with |residual| > k_sigma * weighted_rstd.
    iterations_used counts every fit that was performed; the initial fit is
    iteration 1.
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
        slope, offset, rstd = _wls(xs, ys, ws)
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
    return slope, offset, rstd, len(points) - len(kept), iters


def _unweighted_ols(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    """Reference *unweighted* OLS, used by test_33 to detect agents that ignore weights."""
    n = len(xs)
    if n == 0:
        return 0.0, 0.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0.0:
        slope, offset = 0.0, my
    else:
        slope = num / den
        offset = my - slope * mx
    sse = sum((y - (slope * x + offset)) ** 2 for x, y in zip(xs, ys))
    return slope, offset, math.sqrt(sse / n)


# ---------------------------------------------------------------------------
# Top-level structure & summary
# ---------------------------------------------------------------------------
def test_01_top_level_keys_and_schema_version_are_exact():
    """Top-level key set is exact, schema_version=1, every section list-typed."""
    report = load_report()
    assert set(report) == TOP_LEVEL_KEYS
    assert report["schema_version"] == 1
    for k in TOP_LEVEL_KEYS - {"schema_version", "summary"}:
        assert isinstance(report[k], list), k
    assert isinstance(report["summary"], dict)


def test_02_summary_keys_count_fields_and_meta_totals_are_consistent():
    """summary key set is exact and every *_count matches its list length."""
    report = load_report()
    summary = report["summary"]
    assert set(summary) == SUMMARY_KEYS
    pairs = [
        ("per_channel_calibration_count",      "per_channel_calibration"),
        ("per_run_summary_count",              "per_run_summary"),
        ("signal_assignments_count",           "signal_assignments"),
        ("channel_drift_summary_count",        "channel_drift_summary"),
        ("channel_correlation_matrix_count",   "channel_correlation_matrix"),
        ("quality_findings_count",             "quality_findings"),
    ]
    for count_key, list_key in pairs:
        assert summary[count_key] == len(report[list_key]), count_key

    channels_cfg = _read_input_json("channels.json")
    manifest = _read_input_json("manifest.json")
    exclusions = _read_input_json("exclusions.json")
    expected_total_channels = len(channels_cfg["channels"])
    expected_total_runs = len(manifest["runs"])
    expected_excluded_runs = len(exclusions["runs"])
    expected_active_runs = expected_total_runs - expected_excluded_runs

    assert summary["total_channels"] == expected_total_channels
    assert summary["total_runs"] == expected_total_runs
    assert summary["active_runs"] == expected_active_runs
    assert summary["excluded_runs"] == expected_excluded_runs
    assert isinstance(summary["by_severity"], dict)
    assert set(summary["by_severity"]) == {"critical", "high", "medium", "low", "info"}


def test_03_summary_by_finding_type_matches_quality_findings_counter():
    """summary.by_finding_type equals Counter(f['finding_type'] ...) — only types present."""
    report = load_report()
    expected = dict(Counter(f["finding_type"] for f in report["quality_findings"]))
    assert report["summary"]["by_finding_type"] == expected
    assert report["summary"]["by_severity"] == {
        sev: sum(1 for f in report["quality_findings"] if f["severity"] == sev)
        for sev in ("critical", "high", "medium", "low", "info")
    }


def test_04_sort_orders_for_all_six_lists_are_correct():
    """Every list section is sorted by the documented key contract."""
    report = load_report()
    chan_keys = [r["channel_id"] for r in report["per_channel_calibration"]]
    assert chan_keys == sorted(chan_keys)
    run_keys = [r["run_id"] for r in report["per_run_summary"]]
    assert run_keys == sorted(run_keys)
    sig_keys = [(r["signal_id"], r["run_id"]) for r in report["signal_assignments"]]
    assert sig_keys == sorted(sig_keys)
    drift_keys = [r["channel_id"] for r in report["channel_drift_summary"]]
    assert drift_keys == sorted(drift_keys)
    corr_keys = [(r["channel_a"], r["channel_b"]) for r in report["channel_correlation_matrix"]]
    assert corr_keys == sorted(corr_keys)
    finding_sort_keys = [
        (-f["severity_rank"], f["finding_type"],
         f["channel_id"] or "", f["run_id"] or "", f["signal_id"] or "")
        for f in report["quality_findings"]
    ]
    assert finding_sort_keys == sorted(finding_sort_keys)


# ---------------------------------------------------------------------------
# Per-channel calibration (input-driven)
# ---------------------------------------------------------------------------
def test_05_per_channel_calibration_membership_and_row_schema():
    """Every channel in channels.json appears once with exact key set + valid status."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    channels_cfg = _read_input_json("channels.json")
    expected_ids = {c["channel_id"] for c in channels_cfg["channels"]}
    assert set(cm) == expected_ids
    for row in report["per_channel_calibration"]:
        assert set(row) == CALIBRATION_ROW_KEYS, row["channel_id"]
        assert row["status"] in {"calibrated", "excluded", "insufficient_points"}


def test_06_calibration_status_derived_from_exclusions_and_min_points():
    """status is fully determined by exclusions.channels + min_calibration_points."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    cal_cfg = _read_input_json("calibration.json")["references"]
    exclusions = _read_input_json("exclusions.json")
    policy = _read_input_json("policy.json")
    excluded_channels = set(exclusions["channels"])
    min_pts = policy["min_calibration_points"]
    for cid, row in cm.items():
        n_ref = len(cal_cfg.get(cid, []))
        if cid in excluded_channels:
            assert row["status"] == "excluded", cid
        elif n_ref < min_pts:
            assert row["status"] == "insufficient_points", cid
        else:
            assert row["status"] == "calibrated", cid
        assert row["n_reference_points"] == n_ref, cid


def test_07_excluded_and_insufficient_channels_use_identity_calibration():
    """Excluded and insufficient_points channels report identity slope/offset/zero residual."""
    cm = chan_map(load_report()["per_channel_calibration"])
    for row in cm.values():
        if row["status"] in {"excluded", "insufficient_points"}:
            assert row["slope"] == 1.0, row["channel_id"]
            assert row["offset"] == 0.0, row["channel_id"]
            assert row["residual_stddev"] == 0.0, row["channel_id"]
            assert row["n_outliers_removed"] == 0, row["channel_id"]
            assert row["iterations_used"] == 0, row["channel_id"]


def test_08_calibrated_channels_match_iterative_weighted_least_squares():
    """For every calibrated channel, recompute slope/offset/rstd/outliers via WLS on (raw, true, weight)."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    cal_cfg = _read_input_json("calibration.json")["references"]
    policy = _read_input_json("policy.json")
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    min_pts = policy["min_calibration_points"]
    k_sigma = float(policy["outlier_k_sigma"])
    max_iter = int(policy["outlier_max_iterations"])
    checked = 0
    for cid, refs in cal_cfg.items():
        if cid in excluded_channels or len(refs) < min_pts:
            continue
        pts = [(float(r["raw"]), float(r["true"]), float(r["weight"])) for r in refs]
        slope, offset, rstd, n_out, iters = _iterative_wls(pts, k_sigma, max_iter)
        row = cm[cid]
        assert row["status"] == "calibrated", cid
        assert math.isclose(row["slope"], slope, abs_tol=FLOAT_TOL), cid
        assert math.isclose(row["offset"], offset, abs_tol=FLOAT_TOL), cid
        assert math.isclose(row["residual_stddev"], rstd, abs_tol=FLOAT_TOL), cid
        assert row["n_outliers_removed"] == n_out, cid
        assert row["iterations_used"] == iters, cid
        checked += 1
    assert checked >= 1, "no calibrated channels validated"


def test_09_at_least_one_channel_triggers_outlier_rejection():
    """The fixture must exercise the outlier-rejection path on at least one calibrated channel."""
    cm = chan_map(load_report()["per_channel_calibration"])
    triggered = [c for c in cm.values()
                 if c["status"] == "calibrated" and c["n_outliers_removed"] > 0]
    assert triggered, "no channel had outliers rejected; fixture must exercise this path"
    for row in triggered:
        assert row["iterations_used"] >= 2, row["channel_id"]


# ---------------------------------------------------------------------------
# Per-run summary (input-driven)
# ---------------------------------------------------------------------------
def test_10_every_run_in_manifest_appears_with_correct_status():
    """Every run from manifest.json is present; excluded runs use status='excluded'."""
    report = load_report()
    rm = run_map(report["per_run_summary"])
    manifest_runs = {r["run_id"] for r in _read_input_json("manifest.json")["runs"]}
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    assert set(rm) == manifest_runs
    for rid, row in rm.items():
        assert set(row) == PER_RUN_ROW_KEYS, rid
        if rid in excluded_runs:
            assert row["status"] == "excluded", rid
            assert row["n_events_total"] == 0, rid
            assert row["event_counts_per_channel"] == {}, rid
            assert row["mean_calibrated_per_channel"] == {}, rid
            assert row["n_anomalous_events_per_channel"] == {}, rid
            assert row["total_anomalous_events"] == 0, rid
            assert row["health_score"] is None, rid
        else:
            assert row["status"] == "active", rid
            assert row["health_score"] is not None, rid


def test_11_per_run_counts_and_means_match_raw_traces_for_every_active_run():
    """For every active run, recompute counts and per-channel means from raw TSV + calibration."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    rm = run_map(report["per_run_summary"])
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    active_seen = 0
    for rid, row in rm.items():
        if rid in excluded_runs:
            continue
        active_seen += 1
        expected_counts: dict[str, int] = {}
        expected_sums: dict[str, float] = {}
        expected_total = 0
        for _eid, ch, raw in _read_trace(rid):
            if ch in excluded_channels or ch not in cm:
                continue
            slope, offset = cm[ch]["slope"], cm[ch]["offset"]
            expected_counts[ch] = expected_counts.get(ch, 0) + 1
            expected_sums[ch] = expected_sums.get(ch, 0.0) + (slope * raw + offset)
            expected_total += 1
        assert row["n_events_total"] == expected_total, rid
        assert row["event_counts_per_channel"] == expected_counts, rid
        assert set(row["mean_calibrated_per_channel"]) == set(expected_counts), rid
        for ch, n in expected_counts.items():
            expected_mean = expected_sums[ch] / n
            assert math.isclose(
                row["mean_calibrated_per_channel"][ch], expected_mean, abs_tol=FLOAT_TOL
            ), f"{rid}/{ch}"
    assert active_seen == report["summary"]["active_runs"]


def test_12_anomaly_counts_match_z_threshold_recomputation_per_run():
    """For every active run + channel, recompute the anomaly count from raw TSV + calibration."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    policy = _read_input_json("policy.json")
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    z = float(policy["event_anomaly_z_threshold"])
    min_events = int(policy["anomaly_min_events"])
    rm = run_map(report["per_run_summary"])
    seen_active = 0
    for rid, row in rm.items():
        if rid in excluded_runs:
            continue
        seen_active += 1
        per_chan: dict[str, list[float]] = {}
        for _e, ch, raw in _read_trace(rid):
            if ch in excluded_channels or ch not in cm:
                continue
            per_chan.setdefault(ch, []).append(cm[ch]["slope"] * raw + cm[ch]["offset"])
        expected_anom: dict[str, int] = {}
        expected_total = 0
        for ch, vals in per_chan.items():
            n = len(vals)
            if n < min_events:
                continue
            mean = sum(vals) / n
            sd = _population_stddev(vals, mean)
            if sd == 0.0:
                continue
            n_anom = sum(1 for v in vals if abs(v - mean) > z * sd)
            if n_anom > 0:
                expected_anom[ch] = n_anom
                expected_total += n_anom
        assert row["n_anomalous_events_per_channel"] == expected_anom, rid
        assert row["total_anomalous_events"] == expected_total, rid
    assert seen_active >= 1


def test_13_run_health_scores_match_definition_per_active_run():
    """For every active run, health_score = 1 - total_anomalous_events / max(1, n_events_total)."""
    report = load_report()
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    for row in report["per_run_summary"]:
        if row["run_id"] in excluded_runs:
            continue
        n = row["n_events_total"]
        a = row["total_anomalous_events"]
        expected = 1.0 - (a / n if n > 0 else 0.0)
        assert math.isclose(row["health_score"], expected, abs_tol=FLOAT_TOL), row["run_id"]


def test_14_excluded_channels_never_appear_in_any_per_run_map():
    """No excluded channel is referenced in any per-run map (counts, means, anomalies)."""
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    for row in load_report()["per_run_summary"]:
        for cid in excluded_channels:
            assert cid not in row["event_counts_per_channel"], row["run_id"]
            assert cid not in row["mean_calibrated_per_channel"], row["run_id"]
            assert cid not in row["n_anomalous_events_per_channel"], row["run_id"]


def test_15_summary_total_events_processed_equals_sum_across_all_runs():
    """summary.total_events_processed = sum of per_run_summary[*].n_events_total."""
    report = load_report()
    total = sum(row["n_events_total"] for row in report["per_run_summary"])
    assert total == report["summary"]["total_events_processed"]
    total_anom = sum(row["total_anomalous_events"] for row in report["per_run_summary"])
    assert total_anom == report["summary"]["total_anomalous_events"]


# ---------------------------------------------------------------------------
# Signal assignments (input-driven)
# ---------------------------------------------------------------------------
def test_16_every_signal_assignment_is_consistent_with_raw_trace_and_calibration():
    """For each signal, recompute assignment from raw TSV + per_channel_calibration + exclusions."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    sa_map = signal_map(report["signal_assignments"])
    expected_signals = _read_input_json("expected_signals.json")["signals"]
    exclusions = _read_input_json("exclusions.json")
    excluded_channels = set(exclusions["channels"])
    excluded_runs = set(exclusions["runs"])
    excluded_signals = set(exclusions["signals"])
    tolerance = _read_input_json("policy.json")["signal_match_tolerance"]
    assert len(expected_signals) == len(sa_map), "signal count mismatch with input"
    for s in expected_signals:
        sid = s["signal_id"]
        rid = s["run_id"]
        cid = s["channel_id"]
        exp = float(s["expected_value"])
        row = sa_map[sid]
        assert set(row) == SIGNAL_ROW_KEYS, sid
        is_excluded = (
            sid in excluded_signals
            or rid in excluded_runs
            or cid in excluded_channels
            or cm[cid]["status"] != "calibrated"
        )
        if is_excluded:
            assert row["status"] == "excluded", sid
            assert row["n_matches"] == 0, sid
            assert row["mean_calibrated_value"] is None, sid
            assert row["deviation"] is None, sid
            continue
        slope, offset = cm[cid]["slope"], cm[cid]["offset"]
        matches: list[float] = []
        for _e, ch, raw in _read_trace(rid):
            if ch != cid:
                continue
            cal = slope * raw + offset
            if abs(cal - exp) <= tolerance:
                matches.append(cal)
        if not matches:
            assert row["status"] == "missing", sid
            assert row["n_matches"] == 0, sid
            assert row["mean_calibrated_value"] is None, sid
            assert row["deviation"] is None, sid
        else:
            assert row["status"] == "matched", sid
            assert row["n_matches"] == len(matches), sid
            expected_mean = sum(matches) / len(matches)
            assert math.isclose(row["mean_calibrated_value"], expected_mean, abs_tol=FLOAT_TOL), sid
            assert math.isclose(row["deviation"], expected_mean - exp, abs_tol=FLOAT_TOL), sid


# ---------------------------------------------------------------------------
# Drift and correlation (input-driven)
# ---------------------------------------------------------------------------
def test_17_drift_summary_only_includes_calibrated_channels_and_uses_per_run_means():
    """Drift summary covers exactly the calibrated channels and each row matches per-run means."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    expected = {cid for cid, row in cm.items() if row["status"] == "calibrated"}
    drifts = chan_map(report["channel_drift_summary"])
    assert set(drifts) == expected
    for row in report["channel_drift_summary"]:
        assert set(row) == DRIFT_ROW_KEYS
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    policy = _read_input_json("policy.json")
    drift_max_dev = float(policy["drift_max_deviation_threshold"])
    drift_stddev = float(policy["drift_stddev_threshold"])
    for cid, drift in drifts.items():
        per_run_means: list[float] = []
        for prr in report["per_run_summary"]:
            if prr["run_id"] in excluded_runs:
                continue
            m = prr["mean_calibrated_per_channel"].get(cid)
            if m is not None:
                per_run_means.append(m)
        assert per_run_means, f"no active runs reported events on {cid}"
        mean = sum(per_run_means) / len(per_run_means)
        sd = _population_stddev(per_run_means, mean)
        max_dev = max(abs(v - mean) for v in per_run_means)
        assert drift["n_runs_with_events"] == len(per_run_means), cid
        assert math.isclose(drift["mean_across_runs"], mean, abs_tol=FLOAT_TOL), cid
        assert math.isclose(drift["stddev_across_runs"], sd, abs_tol=FLOAT_TOL), cid
        assert math.isclose(drift["max_run_deviation"], max_dev, abs_tol=FLOAT_TOL), cid
        expected_status = "drifting" if (max_dev > drift_max_dev or sd > drift_stddev) else "stable"
        assert drift["drift_status"] == expected_status, cid


def test_18_correlation_matrix_pairs_and_pearson_r_are_consistent():
    """Correlation matrix has the right pairs and pearson_r matches per-run means."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    min_corr_runs = int(_read_input_json("policy.json")["min_correlation_runs"])

    cal_channels = sorted(cid for cid, row in cm.items() if row["status"] == "calibrated")
    per_chan_per_run: dict[str, dict[str, float]] = {cid: {} for cid in cal_channels}
    for prr in report["per_run_summary"]:
        if prr["run_id"] in excluded_runs:
            continue
        for cid in cal_channels:
            v = prr["mean_calibrated_per_channel"].get(cid)
            if v is not None:
                per_chan_per_run[cid][prr["run_id"]] = v

    expected_rows: list[dict[str, Any]] = []
    for ca, cb in combinations(cal_channels, 2):
        runs_a = per_chan_per_run[ca]
        runs_b = per_chan_per_run[cb]
        common = sorted(set(runs_a) & set(runs_b))
        if len(common) < min_corr_runs:
            continue
        xs = [runs_a[r] for r in common]
        ys = [runs_b[r] for r in common]
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
        expected_rows.append({"channel_a": ca, "channel_b": cb, "n_runs": n, "pearson_r": r})

    actual = report["channel_correlation_matrix"]
    assert len(actual) == len(expected_rows), "row count mismatch"
    for got, exp in zip(actual, expected_rows):
        assert set(got) == CORRELATION_ROW_KEYS
        assert got["channel_a"] == exp["channel_a"]
        assert got["channel_b"] == exp["channel_b"]
        assert got["n_runs"] == exp["n_runs"]
        assert math.isclose(got["pearson_r"], exp["pearson_r"], abs_tol=FLOAT_TOL), (got, exp)


# ---------------------------------------------------------------------------
# Quality findings — schema and per-type triggers
# ---------------------------------------------------------------------------
def test_19_findings_schema_is_canonical_and_only_known_types_appear():
    """Every finding has the canonical key set, valid severity_rank, valid subject."""
    report = load_report()
    valid_subjects = {"channel", "run", "signal"}
    severity_ranks = _read_input_json("policy.json")["severity_ranks"]
    seen_types = set()
    for f in report["quality_findings"]:
        assert set(f) == FINDING_KEYS, f
        assert f["finding_type"] in ALL_FINDING_TYPES, f["finding_type"]
        seen_types.add(f["finding_type"])
        assert f["subject"] in valid_subjects, f
        assert f["severity_rank"] == severity_ranks[f["severity"]], f
        if f["finding_type"] in EXCLUDED_EVIDENCE_TYPES:
            assert f["evidence"] == {}, f
        else:
            assert isinstance(f["evidence"], dict)
            assert set(f["evidence"]) == EVIDENCE_KEYS[f["finding_type"]], f
    # Every fixture-driven trigger should produce a finding type at least once
    assert seen_types.issuperset({
        "insufficient_calibration_points",
        "large_calibration_residual",
        "outliers_rejected_in_calibration",
        "channel_drifting",
        "anomalous_event_burst",
        "low_run_health",
        "unexpected_channel_correlation",
        "signal_value_mismatch",
        "signal_missing",
        "excluded_channel",
        "excluded_run",
        "excluded_signal",
    }), f"missing finding types: {ALL_FINDING_TYPES - seen_types}"


def test_20_excluded_findings_match_exclusion_inputs_with_correct_subjects_and_evidence():
    """One excluded_* finding per entry in exclusions.* with matching subject and ids."""
    report = load_report()
    exclusions = _read_input_json("exclusions.json")
    expected_signals_by_id = {s["signal_id"]: s for s in _read_input_json("expected_signals.json")["signals"]}

    chan_findings = findings_by(report, finding_type="excluded_channel")
    run_findings = findings_by(report, finding_type="excluded_run")
    sig_findings = findings_by(report, finding_type="excluded_signal")

    assert {f["channel_id"] for f in chan_findings} == set(exclusions["channels"])
    assert {f["run_id"] for f in run_findings} == set(exclusions["runs"])
    assert {f["signal_id"] for f in sig_findings} == set(exclusions["signals"])

    for f in chan_findings:
        assert f["subject"] == "channel"
        assert f["severity"] == "info" and f["severity_rank"] == 0
        assert f["run_id"] is None and f["signal_id"] is None
        assert f["evidence"] == {}

    for f in run_findings:
        assert f["subject"] == "run"
        assert f["severity"] == "info" and f["severity_rank"] == 0
        assert f["channel_id"] is None and f["signal_id"] is None
        assert f["evidence"] == {}

    for f in sig_findings:
        assert f["subject"] == "signal"
        assert f["severity"] == "info" and f["severity_rank"] == 0
        assert f["evidence"] == {}
        original = expected_signals_by_id[f["signal_id"]]
        assert f["channel_id"] == original["channel_id"], f
        assert f["run_id"] == original["run_id"], f
        assert f["channel_id"] is not None
        assert f["run_id"] is not None


def test_21_calibration_findings_evidence_matches_recomputed_state():
    """insufficient_calibration_points + large_calibration_residual + outliers_rejected_in_calibration."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    policy = _read_input_json("policy.json")
    min_pts = int(policy["min_calibration_points"])
    residual_warn = float(policy["residual_warning_threshold"])
    k_sigma = float(policy["outlier_k_sigma"])

    insuf = findings_by(report, finding_type="insufficient_calibration_points")
    expected_insuf = {cid for cid, row in cm.items() if row["status"] == "insufficient_points"}
    assert {f["channel_id"] for f in insuf} == expected_insuf
    for f in insuf:
        assert f["subject"] == "channel"
        assert f["severity"] == "high" and f["severity_rank"] == 3
        assert f["evidence"] == {
            "n_reference_points": cm[f["channel_id"]]["n_reference_points"],
            "min_required": min_pts,
        }

    resid = findings_by(report, finding_type="large_calibration_residual")
    expected_resid = {
        cid for cid, row in cm.items()
        if row["status"] == "calibrated" and row["residual_stddev"] > residual_warn
    }
    assert {f["channel_id"] for f in resid} == expected_resid
    for f in resid:
        assert f["subject"] == "channel"
        assert f["severity"] == "high" and f["severity_rank"] == 3
        row = cm[f["channel_id"]]
        ev = f["evidence"]
        assert math.isclose(ev["residual_stddev"], row["residual_stddev"], abs_tol=FLOAT_TOL)
        assert ev["threshold"] == residual_warn
        assert math.isclose(ev["slope"], row["slope"], abs_tol=FLOAT_TOL)
        assert math.isclose(ev["offset"], row["offset"], abs_tol=FLOAT_TOL)

    outl = findings_by(report, finding_type="outliers_rejected_in_calibration")
    expected_outl = {
        cid for cid, row in cm.items()
        if row["status"] == "calibrated" and row["n_outliers_removed"] > 0
    }
    assert {f["channel_id"] for f in outl} == expected_outl
    for f in outl:
        assert f["subject"] == "channel"
        assert f["severity"] == "info" and f["severity_rank"] == 0
        row = cm[f["channel_id"]]
        assert f["evidence"] == {
            "n_outliers_removed": row["n_outliers_removed"],
            "k_sigma": k_sigma,
            "iterations_used": row["iterations_used"],
        }


def test_22_signal_findings_evidence_matches_assignments():
    """signal_missing + signal_value_mismatch are derived from signal_assignments."""
    report = load_report()
    sm = signal_map(report["signal_assignments"])
    policy = _read_input_json("policy.json")
    sig_tol = float(policy["signal_match_tolerance"])
    sig_dev_warn = float(policy["signal_deviation_warning_threshold"])

    missing = findings_by(report, finding_type="signal_missing")
    expected_missing = {sid for sid, row in sm.items() if row["status"] == "missing"}
    assert {f["signal_id"] for f in missing} == expected_missing
    for f in missing:
        assert f["subject"] == "signal"
        assert f["severity"] == "medium" and f["severity_rank"] == 2
        sa = sm[f["signal_id"]]
        assert f["channel_id"] == sa["channel_id"]
        assert f["run_id"] == sa["run_id"]
        assert f["evidence"] == {
            "expected_value": sa["expected_value"],
            "tolerance": sig_tol,
            "n_matches": 0,
        }

    mismatch = findings_by(report, finding_type="signal_value_mismatch")
    expected_mismatch = {
        sid for sid, row in sm.items()
        if row["status"] == "matched" and abs(row["deviation"]) > sig_dev_warn
    }
    assert {f["signal_id"] for f in mismatch} == expected_mismatch
    for f in mismatch:
        assert f["subject"] == "signal"
        assert f["severity"] == "high" and f["severity_rank"] == 3
        sa = sm[f["signal_id"]]
        ev = f["evidence"]
        assert math.isclose(ev["expected_value"], sa["expected_value"], abs_tol=FLOAT_TOL)
        assert math.isclose(ev["mean_calibrated_value"], sa["mean_calibrated_value"], abs_tol=FLOAT_TOL)
        assert math.isclose(ev["deviation"], sa["deviation"], abs_tol=FLOAT_TOL)
        assert ev["threshold"] == sig_dev_warn
        assert ev["n_matches"] == sa["n_matches"]


def test_23_drift_findings_match_drift_summary():
    """channel_drifting fires exactly when drift_status == 'drifting'."""
    report = load_report()
    drifts = chan_map(report["channel_drift_summary"])
    policy = _read_input_json("policy.json")
    drift_max_dev = float(policy["drift_max_deviation_threshold"])
    drift_stddev = float(policy["drift_stddev_threshold"])

    findings = findings_by(report, finding_type="channel_drifting")
    expected = {cid for cid, row in drifts.items() if row["drift_status"] == "drifting"}
    assert {f["channel_id"] for f in findings} == expected
    for f in findings:
        assert f["subject"] == "channel"
        assert f["severity"] == "critical" and f["severity_rank"] == 4
        assert f["run_id"] is None and f["signal_id"] is None
        d = drifts[f["channel_id"]]
        ev = f["evidence"]
        assert math.isclose(ev["max_run_deviation"], d["max_run_deviation"], abs_tol=FLOAT_TOL)
        assert math.isclose(ev["stddev_across_runs"], d["stddev_across_runs"], abs_tol=FLOAT_TOL)
        assert ev["max_deviation_threshold"] == drift_max_dev
        assert ev["stddev_threshold"] == drift_stddev
        assert ev["n_runs_with_events"] == d["n_runs_with_events"]


def test_24_anomaly_burst_findings_match_per_run_summary():
    """anomalous_event_burst fires per (run, channel) with n_anomalous >= burst_threshold; subject='run'."""
    report = load_report()
    policy = _read_input_json("policy.json")
    burst_threshold = int(policy["anomaly_burst_threshold"])
    z = float(policy["event_anomaly_z_threshold"])
    findings = findings_by(report, finding_type="anomalous_event_burst")

    expected: list[tuple[str, str, int, int]] = []
    for prr in report["per_run_summary"]:
        if prr["status"] != "active":
            continue
        for ch, n_anom in prr["n_anomalous_events_per_channel"].items():
            if n_anom >= burst_threshold:
                expected.append((prr["run_id"], ch, n_anom, prr["event_counts_per_channel"][ch]))

    actual = sorted([(f["run_id"], f["channel_id"],
                      f["evidence"]["n_anomalous"], f["evidence"]["n_events_in_channel"])
                     for f in findings])
    assert actual == sorted(expected)
    for f in findings:
        assert f["subject"] == "run"
        assert f["severity"] == "high" and f["severity_rank"] == 3
        assert f["signal_id"] is None
        assert f["evidence"]["z_threshold"] == z
        assert f["evidence"]["burst_threshold"] == burst_threshold


def test_25_low_run_health_findings_match_per_run_summary():
    """low_run_health fires for active runs whose health_score < min_run_health."""
    report = load_report()
    min_health = float(_read_input_json("policy.json")["min_run_health"])
    findings = findings_by(report, finding_type="low_run_health")
    expected = {row["run_id"] for row in report["per_run_summary"]
                if row["status"] == "active" and row["health_score"] < min_health}
    assert {f["run_id"] for f in findings} == expected
    rm = run_map(report["per_run_summary"])
    for f in findings:
        assert f["subject"] == "run"
        assert f["severity"] == "high" and f["severity_rank"] == 3
        assert f["channel_id"] is None and f["signal_id"] is None
        row = rm[f["run_id"]]
        ev = f["evidence"]
        assert math.isclose(ev["health_score"], row["health_score"], abs_tol=FLOAT_TOL)
        assert ev["threshold"] == min_health
        assert ev["n_anomalous_events"] == row["total_anomalous_events"]
        assert ev["n_events_total"] == row["n_events_total"]


def test_26_unexpected_channel_correlation_findings_match_correlation_matrix():
    """unexpected_channel_correlation fires per row with |pearson_r| > threshold."""
    report = load_report()
    threshold = float(_read_input_json("policy.json")["cross_channel_corr_threshold"])
    findings = findings_by(report, finding_type="unexpected_channel_correlation")
    expected_pairs = {
        (row["channel_a"], row["channel_b"])
        for row in report["channel_correlation_matrix"]
        if abs(row["pearson_r"]) > threshold
    }
    actual_pairs = {
        (f["evidence"]["channel_a"], f["evidence"]["channel_b"]) for f in findings
    }
    assert actual_pairs == expected_pairs
    corr_map = {(r["channel_a"], r["channel_b"]): r for r in report["channel_correlation_matrix"]}
    for f in findings:
        assert f["subject"] == "channel"
        assert f["severity"] == "medium" and f["severity_rank"] == 2
        assert f["run_id"] is None and f["signal_id"] is None
        ev = f["evidence"]
        row = corr_map[(ev["channel_a"], ev["channel_b"])]
        assert math.isclose(ev["pearson_r"], row["pearson_r"], abs_tol=FLOAT_TOL)
        assert ev["threshold"] == threshold
        assert ev["n_runs"] == row["n_runs"]
        assert f["channel_id"] == ev["channel_a"]


# ---------------------------------------------------------------------------
# Output formatting and integrity
# ---------------------------------------------------------------------------
def test_27_report_uses_two_space_indent_and_trailing_newline():
    """Report must equal json.dumps(loaded, indent=2) + '\\n' line-by-line."""
    raw = REPORT_FILE.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    loaded = json.loads(raw)
    expected = json.dumps(loaded, indent=2, ensure_ascii=False) + "\n"
    raw_lines = raw.split("\n")
    expected_lines = expected.split("\n")
    assert len(raw_lines) == len(expected_lines), (
        f"line count differs: got {len(raw_lines)}, expected {len(expected_lines)}"
    )
    for i, (got, exp) in enumerate(zip(raw_lines, expected_lines)):
        assert "\t" not in got, f"line {i} contains a tab"
        got_indent = len(got) - len(got.lstrip(" "))
        exp_indent = len(exp) - len(exp.lstrip(" "))
        assert got_indent == exp_indent, f"line {i} indent {got_indent} != {exp_indent}: {got!r}"


def test_28_every_floating_point_field_is_rounded_to_six_decimals():
    """Walk the entire report and assert no float exceeds 6 decimal places."""
    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, float):
            yield node

    for value in walk(load_report()):
        assert value == round(value, 6), f"value {value!r} is not 6-decimal-rounded"


def test_29_input_fixture_files_have_not_been_modified():
    """SHA-256 of every input config + every run TSV must match the bundled checksum."""
    mismatches: list[str] = []
    for rel, want in FIXTURE_HASHES.items():
        path = DETECTOR_DIR / rel
        assert path.exists(), f"missing input fixture: {rel}"
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != want:
            mismatches.append(f"{rel}: got {got[:16]}…, want {want[:16]}…")
    assert not mismatches, "input fixtures were modified:\n  " + "\n  ".join(mismatches)


def test_30_excluded_runs_produce_no_signal_assignments_with_status_other_than_excluded():
    """For every signal whose run_id is in exclusions.runs, status must be 'excluded'."""
    report = load_report()
    excluded_runs = set(_read_input_json("exclusions.json")["runs"])
    for row in report["signal_assignments"]:
        if row["run_id"] in excluded_runs:
            assert row["status"] == "excluded", row["signal_id"]
            assert row["mean_calibrated_value"] is None
            assert row["deviation"] is None
            assert row["n_matches"] == 0


# ---------------------------------------------------------------------------
# Hardened tests — lock in WLS specifics and disambiguations the reviewer
# flagged.  These bite agents that fall back to OLS, miss the weight field,
# misuse the residual_stddev denominator, get iterations_used off-by-one,
# or guess the wrong subject for non-excluded findings.
# ---------------------------------------------------------------------------
def test_31_iterations_used_starts_at_one_for_calibrated_channels():
    """The initial weighted fit counts as iteration 1.  A calibrated channel
    that converges with no rejections must report iterations_used == 1."""
    cm = chan_map(load_report()["per_channel_calibration"])
    cal = [row for row in cm.values() if row["status"] == "calibrated"]
    assert cal, "fixture must have at least one calibrated channel"
    no_reject = [row for row in cal if row["n_outliers_removed"] == 0]
    assert no_reject, "fixture must have at least one channel that converges without rejections"
    for row in no_reject:
        assert row["iterations_used"] == 1, (
            f"{row['channel_id']}: iterations_used must be 1 when no points are rejected, "
            f"got {row['iterations_used']}"
        )
    for row in cal:
        assert row["iterations_used"] >= 1, row["channel_id"]


def test_32_finding_subject_matches_canonical_per_type_mapping():
    """Every finding's subject must equal the canonical subject for its type.

    Resolves the spec ambiguity flagged for `anomalous_event_burst` (run, not
    channel) and locks in the per-type mapping for the other ten types as
    well, so that agents cannot pick an arbitrary value."""
    for f in load_report()["quality_findings"]:
        ftype = f["finding_type"]
        assert ftype in CANONICAL_SUBJECTS, ftype
        assert f["subject"] == CANONICAL_SUBJECTS[ftype], (
            f"finding_type={ftype}: subject must be "
            f"{CANONICAL_SUBJECTS[ftype]!r}, got {f['subject']!r}"
        )


def test_33_calibration_uses_reference_weights_not_unweighted_ols():
    """For at least one calibrated channel where the fit is over-determined
    and the per-reference weights are non-uniform, the report's slope must
    match the *weighted* fit and disagree with naïve unweighted OLS by more
    than the comparison tolerance.  This catches agents that ignore the
    `weight` column entirely.
    """
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    cal_cfg = _read_input_json("calibration.json")["references"]
    policy = _read_input_json("policy.json")
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    min_pts = int(policy["min_calibration_points"])
    k_sigma = float(policy["outlier_k_sigma"])
    max_iter = int(policy["outlier_max_iterations"])

    discriminating: list[str] = []
    for cid, refs in cal_cfg.items():
        if cid in excluded_channels or len(refs) < min_pts:
            continue
        if cm[cid]["status"] != "calibrated":
            continue
        ws = [float(r["weight"]) for r in refs]
        if all(abs(w - ws[0]) < 1e-12 for w in ws):
            continue  # uniform weights — WLS == OLS by definition
        pts = [(float(r["raw"]), float(r["true"]), float(r["weight"])) for r in refs]
        wls_slope, wls_offset, _wls_rstd, _, _ = _iterative_wls(pts, k_sigma, max_iter)
        xs = [float(r["raw"]) for r in refs]
        ys = [float(r["true"]) for r in refs]
        ols_slope, ols_offset, _ = _unweighted_ols(xs, ys)
        if abs(wls_slope - ols_slope) <= 5 * FLOAT_TOL:
            continue  # the data is too clean to discriminate WLS from OLS
        # The report should track WLS and disagree with OLS.
        assert math.isclose(cm[cid]["slope"], wls_slope, abs_tol=FLOAT_TOL), (
            f"{cid}: report slope {cm[cid]['slope']} does not match WLS reference {wls_slope}"
        )
        assert abs(cm[cid]["slope"] - ols_slope) > FLOAT_TOL, (
            f"{cid}: report slope {cm[cid]['slope']} matches unweighted OLS {ols_slope} — "
            f"WLS weights were ignored"
        )
        discriminating.append(cid)
    assert discriminating, (
        "fixture failed to expose any channel where WLS and unweighted OLS "
        "disagree by more than the tolerance"
    )


def test_34_at_least_one_channel_has_outlier_rejection_driven_by_weights():
    """The reference iterative-WLS reject path must trigger on at least one
    channel where iterative-OLS would *not* reject anything.  This is the
    smoking-gun test that the agent applied weights inside the rejection
    threshold, not just inside the slope/offset computation."""
    cal_cfg = _read_input_json("calibration.json")["references"]
    policy = _read_input_json("policy.json")
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    min_pts = int(policy["min_calibration_points"])
    k_sigma = float(policy["outlier_k_sigma"])
    max_iter = int(policy["outlier_max_iterations"])

    # Reference unweighted iterative-OLS (parallel structure to _iterative_wls)
    def iterative_ols(points: list[tuple[float, float]]) -> int:
        kept = list(range(len(points)))
        iters = 0
        while iters < max_iter:
            iters += 1
            xs = [points[i][0] for i in kept]
            ys = [points[i][1] for i in kept]
            slope, offset, rstd = _unweighted_ols(xs, ys)
            if rstd == 0.0:
                break
            thr = k_sigma * rstd
            new_kept = [i for i in kept if abs(points[i][1] - (slope * points[i][0] + offset)) <= thr]
            if len(new_kept) < 2 or len(new_kept) == len(kept):
                kept = new_kept if len(new_kept) >= 2 else kept
                break
            kept = new_kept
        return len(points) - len(kept)

    cm = chan_map(load_report()["per_channel_calibration"])
    discriminating: list[str] = []
    for cid, refs in cal_cfg.items():
        if cid in excluded_channels or len(refs) < min_pts:
            continue
        if cm[cid]["status"] != "calibrated":
            continue
        pts_w = [(float(r["raw"]), float(r["true"]), float(r["weight"])) for r in refs]
        pts_p = [(float(r["raw"]), float(r["true"])) for r in refs]
        _, _, _, n_w, _ = _iterative_wls(pts_w, k_sigma, max_iter)
        n_o = iterative_ols(pts_p)
        if n_w > n_o:
            assert cm[cid]["n_outliers_removed"] == n_w, (
                f"{cid}: WLS rejects {n_w} points but report shows {cm[cid]['n_outliers_removed']}; "
                f"unweighted-OLS rejects only {n_o}"
            )
            discriminating.append(cid)
    assert discriminating, (
        "fixture failed to expose a channel whose WLS rejection trajectory differs "
        "from unweighted-OLS rejection trajectory"
    )


def test_35_residual_stddev_uses_weighted_population_denominator():
    """For every calibrated channel, manually recompute the residual stddev
    two ways — using S = Σwᵢ in the denominator (correct) and using N
    (incorrect) — and assert the report matches the former whenever the
    two would disagree.  Bites agents that compute residuals correctly
    but divide by the count instead of the sum of weights."""
    report = load_report()
    cm = chan_map(report["per_channel_calibration"])
    cal_cfg = _read_input_json("calibration.json")["references"]
    policy = _read_input_json("policy.json")
    excluded_channels = set(_read_input_json("exclusions.json")["channels"])
    min_pts = int(policy["min_calibration_points"])
    k_sigma = float(policy["outlier_k_sigma"])
    max_iter = int(policy["outlier_max_iterations"])

    discriminating: list[str] = []
    for cid, refs in cal_cfg.items():
        if cid in excluded_channels or len(refs) < min_pts:
            continue
        row = cm[cid]
        if row["status"] != "calibrated":
            continue
        pts = [(float(r["raw"]), float(r["true"]), float(r["weight"])) for r in refs]
        slope, offset, rstd_w, _, _ = _iterative_wls(pts, k_sigma, max_iter)
        # Recompute under "wrong" denominator N on the same kept set.  We
        # mimic what an agent would do if they computed weighted residuals
        # but divided by the count of kept points.
        kept_xs, kept_ys, kept_ws = [], [], []
        for x, y, w in pts:
            if abs(y - (slope * x + offset)) <= k_sigma * rstd_w or rstd_w == 0.0:
                kept_xs.append(x)
                kept_ys.append(y)
                kept_ws.append(w)
        n_kept = len(kept_xs)
        sse_w = sum(w * (y - (slope * x + offset)) ** 2 for w, x, y in zip(kept_ws, kept_xs, kept_ys))
        rstd_wrong = math.sqrt(sse_w / n_kept) if n_kept > 0 else 0.0
        if abs(rstd_w - rstd_wrong) > FLOAT_TOL:
            assert math.isclose(row["residual_stddev"], rstd_w, abs_tol=FLOAT_TOL), (
                f"{cid}: report residual_stddev={row['residual_stddev']} matches "
                f"the wrong-denominator value {rstd_wrong} instead of the "
                f"weighted-denominator value {rstd_w}"
            )
            assert abs(row["residual_stddev"] - rstd_wrong) > FLOAT_TOL / 10, (
                f"{cid}: residual_stddev appears to use N as denominator; "
                f"report={row['residual_stddev']}, weighted={rstd_w}, wrong={rstd_wrong}"
            )
            discriminating.append(cid)
    assert discriminating, (
        "fixture failed to expose a channel where Σwᵢ and N denominators "
        "produce different residual_stddev"
    )
