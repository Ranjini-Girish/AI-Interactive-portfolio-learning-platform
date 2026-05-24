"""
Verifier for radionuclide-decay-audit-hard.

Recomputes expected outputs from the raw input fixtures and compares
against the candidate report at /app/output/decay_audit.json.
"""

import json
import math
import os
import csv
import hashlib
import pytest
from pathlib import Path

ROOT = Path("/app")
CONFIG = ROOT / "config"
SAMPLES_DIR = ROOT / "samples"
MEAS_DIR = ROOT / "measurements"
REPORT_PATH = ROOT / "output" / "decay_audit.json"

LN2 = math.log(2)
FLOAT_TOL = 1e-4

# ── SHA-256 fixture hashes ──────────────────────────────────────────
# If any input file is modified, this test fails immediately.

FIXTURE_HASHES = {
    "config/isotopes.json": "5593a595d1c9f0117c3356a27276394516877ba30557bde521544f2402d42bf7",
    "config/policy.json": "4a1cfd6f63049135661e40f9c743d346f62239d4ac08654317d1ac6129570d1c",
    "config/facility.json": "9e2fc1d97013769c30bee56350a6f65e93b239527d4e50cd18e4090bcd900da5",
    "samples/S01.json": "eb4bca62b25753a0faf319e31e0d3fa0340f1aa1473f94b444c756ae503316e8",
    "samples/S02.json": "9d84e9ea4ec4ec633d977ef2804719ca69ad5b27f5fb8b23c1f452484e271d20",
    "samples/S03.json": "76ea454879705877ae9617aa116e8c37dc132bdf925f7788e8c80cb44318e80e",
    "samples/S04.json": "aec2ca5fdcf4bcd36905d990b55a695dec115f7d64ce095a05c44baf164b30b2",
    "samples/S05.json": "eac938aaa33ea1cba4af7555e45387b814dafeff6c8e50643dffb80226c5a23e",
    "samples/S06.json": "33082e2e5b3641c55c68cf4363a985664e804aa92fb86e6091fad89856d73da2",
    "measurements/det_alpha.csv": "037228f320af16ae944c1332f09121211fe3d5192a2b47126ae52b44f648b74e",
    "measurements/det_beta.csv": "d967589daf65f615250ddb82fa540a38997b34a4385ecd44bfe738062341d667",
    "measurements/det_gamma.csv": "55aebcf94f3bff3d1986def54bf44a1cd92c08ebc16815c3eb02b7af3edbc9d3",
    "measurements/det_delta.csv": "56495a8285041ceeccdd88b385e8437c82f1525010b64e10bcc46ae6d87a4b26",
    "measurements/det_epsilon.csv": "05e702de95b355e1aa9a10a48e5a8f87252404593776043f711d492248d65619",
}


def _load_fixtures():
    with open(CONFIG / "isotopes.json") as f:
        iso_data = json.load(f)["isotopes"]
    with open(CONFIG / "policy.json") as f:
        policy = json.load(f)
    with open(CONFIG / "facility.json") as f:
        facility = json.load(f)
    samples = {}
    for fn in sorted(os.listdir(SAMPLES_DIR)):
        if fn.endswith(".json"):
            with open(SAMPLES_DIR / fn) as f:
                sd = json.load(f)
                samples[sd["sample_id"]] = sd
    measurements = {}
    for fn in sorted(os.listdir(MEAS_DIR)):
        if fn.endswith(".csv"):
            det_id = fn[:-4]
            with open(MEAS_DIR / fn, newline="") as f:
                measurements[det_id] = list(csv.DictReader(f))
    return iso_data, policy, facility, samples, measurements


def _decay_constant(iso_data, iso_id):
    hl = iso_data[iso_id]["half_life_hours"]
    if hl is None or hl <= 0:
        return 0.0
    return LN2 / hl


def _compute_activities(iso_data, policy, sample, t):
    initial = sample["initial_activities_bq"]
    rel_tol = policy["nearly_equal_lambda_rel_tol"]

    all_isos = set()
    def collect(iso):
        all_isos.add(iso)
        for dm in iso_data[iso]["decay_modes"]:
            collect(dm["daughter"])
    for iso in initial:
        collect(iso)

    parent_map = {}
    br_map = {}
    for iso in all_isos:
        for dm in iso_data[iso]["decay_modes"]:
            if dm["daughter"] in all_isos:
                parent_map[dm["daughter"]] = iso
                br_map[(iso, dm["daughter"])] = dm["branching_ratio"]

    topo = []
    visited = set()
    def visit(iso):
        if iso in visited:
            return
        visited.add(iso)
        for dm in iso_data[iso]["decay_modes"]:
            if dm["daughter"] in all_isos:
                visit(dm["daughter"])
        topo.append(iso)
    for iso in sorted(all_isos):
        visit(iso)
    topo.reverse()

    N0 = {}
    for iso in all_isos:
        lam = _decay_constant(iso_data, iso)
        a0 = initial.get(iso, 0.0)
        N0[iso] = a0 / lam if lam > 0 else 0.0

    activities = {}
    for iso in topo:
        lam = _decay_constant(iso_data, iso)
        if lam == 0:
            activities[iso] = 0.0
            continue
        n_at_t = N0.get(iso, 0.0) * math.exp(-lam * t)
        if iso in parent_map:
            par = parent_map[iso]
            br = br_map[(par, iso)]
            lam_p = _decay_constant(iso_data, par)
            n0_p = N0.get(par, 0.0)
            if lam_p > 0:
                diff = lam - lam_p
                if abs(diff) < rel_tol * max(lam, lam_p):
                    n_at_t += br * lam_p * n0_p * t * math.exp(-lam_p * t)
                else:
                    n_at_t += br * lam_p * n0_p / diff * (
                        math.exp(-lam_p * t) - math.exp(-lam * t)
                    )
        activities[iso] = lam * n_at_t
    return activities


def _source_hashes():
    hashes = {}
    for d in [CONFIG, SAMPLES_DIR, MEAS_DIR]:
        for dp, dns, fns in os.walk(d):
            dns.sort()
            for fn in sorted(fns):
                fp = os.path.join(dp, fn)
                rel = os.path.relpath(fp, ROOT).replace("\\", "/")
                with open(fp, "rb") as fh:
                    hashes[rel] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(hashes.items()))


def _floats_close(a, b, tol=FLOAT_TOL):
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= tol
    return a == b


@pytest.fixture(scope="module")
def report():
    assert REPORT_PATH.exists(), f"Report not found at {REPORT_PATH}"
    with open(REPORT_PATH) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def fixtures():
    return _load_fixtures()


# ── Test 01: Fixture integrity ──────────────────────────────────────

def test_01_fixture_integrity():
    """Input files must not be modified."""
    for rel_path, expected_hash in FIXTURE_HASHES.items():
        fp = ROOT / rel_path
        assert fp.exists(), f"Missing fixture: {rel_path}"
        with open(fp, "rb") as f:
            actual = hashlib.sha256(f.read()).hexdigest()
        assert actual == expected_hash, f"Fixture modified: {rel_path}"


# ── Test 02: Top-level structure ────────────────────────────────────

def test_02_top_level_keys(report):
    expected_keys = [
        "schema_version", "summary", "source_sha256", "decay_chains",
        "sample_analyses", "measurement_comparisons", "findings",
        "zone_safety_assessment",
    ]
    assert list(report.keys()) == expected_keys
    assert report["schema_version"] == 1


# ── Test 03: Summary counts ────────────────────────────────────────

def test_03_summary_counts(report, fixtures):
    iso_data, policy, facility, samples, measurements = fixtures
    s = report["summary"]
    assert s["total_samples"] == len(samples)
    assert s["total_isotopes_tracked"] == len(iso_data)
    total_meas = sum(len(rows) for rows in measurements.values())
    assert s["total_measurements"] == total_meas
    assert s["total_anomalies"] == sum(
        1 for c in report["measurement_comparisons"] if c["is_anomaly"]
    )
    assert s["total_findings"] == len(report["findings"])
    assert s["chains_identified"] == len(report["decay_chains"])


# ── Test 04: Summary severity keys ─────────────────────────────────

def test_04_severity_keys(report):
    sev = report["summary"]["findings_by_severity"]
    for k in ["critical", "high", "medium", "low", "info"]:
        assert k in sev, f"Missing severity key: {k}"
        assert isinstance(sev[k], int)


# ── Test 05: Source SHA-256 hashes ──────────────────────────────────

def test_05_source_hashes(report):
    expected = _source_hashes()
    actual = report["source_sha256"]
    assert set(actual.keys()) == set(expected.keys()), (
        f"Key mismatch: extra={set(actual) - set(expected)}, "
        f"missing={set(expected) - set(actual)}"
    )
    for k in expected:
        assert actual[k] == expected[k], f"Hash mismatch for {k}"
    keys = list(actual.keys())
    assert keys == sorted(keys), "source_sha256 keys must be sorted"


# ── Test 06: Decay chain structure ──────────────────────────────────

def test_06_decay_chains(report, fixtures):
    iso_data = fixtures[0]
    chains = report["decay_chains"]
    roots = [c["root_isotope"] for c in chains]
    assert roots == sorted(roots), "decay_chains must be sorted by root_isotope"

    all_endpoints = set()
    for chain in chains:
        for path in chain["paths"]:
            seq = path["sequence"]
            assert seq[0] == chain["root_isotope"]
            endpoint = seq[-1]
            all_endpoints.add(endpoint)
            if path["is_stable_endpoint"]:
                assert iso_data[endpoint]["half_life_hours"] is None
            assert 0 < path["cumulative_branching"] <= 1.0


# ── Test 07: Decay chain branching sums ─────────────────────────────

def test_07_chain_branching_sums(report):
    for chain in report["decay_chains"]:
        total_br = sum(p["cumulative_branching"] for p in chain["paths"])
        assert _floats_close(total_br, 1.0, 0.001), (
            f"Branching ratios for {chain['root_isotope']} sum to {total_br}"
        )


# ── Test 08: Sample analysis structure ──────────────────────────────

def test_08_sample_analyses_structure(report, fixtures):
    _, _, _, samples, _ = fixtures
    analyses = report["sample_analyses"]
    assert len(analyses) == len(samples)
    sids = [a["sample_id"] for a in analyses]
    assert sids == sorted(sids)
    for a in analyses:
        assert "initial_isotopes" in a
        assert "all_chain_isotopes" in a
        assert "time_snapshots" in a
        assert a["initial_isotopes"] == sorted(a["initial_isotopes"])
        assert a["all_chain_isotopes"] == sorted(a["all_chain_isotopes"])


# ── Test 09: Predicted activities at t=0 ────────────────────────────

def test_09_activities_at_t0(report, fixtures):
    iso_data, policy, _, samples, _ = fixtures
    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        sample = samples[sid]
        t0_snaps = [s for s in analysis["time_snapshots"] if s["time_hours"] == 0.0]
        if not t0_snaps:
            continue
        snap = t0_snaps[0]
        for iso_id, a0 in sample["initial_activities_bq"].items():
            predicted = snap["predicted_activities_bq"].get(iso_id, 0.0)
            assert _floats_close(predicted, a0), (
                f"{sid}/{iso_id} at t=0: expected {a0}, got {predicted}"
            )


# ── Test 10: Activity decay monotonicity for pure parents ──────────

def test_10_root_decay_monotonic(report, fixtures):
    """Root isotopes (no parent feeding them) must decay monotonically."""
    iso_data = fixtures[0]
    has_parent = set()
    for iso_id, data in iso_data.items():
        for dm in data["decay_modes"]:
            has_parent.add(dm["daughter"])

    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        for iso_id in analysis["initial_isotopes"]:
            if iso_data[iso_id]["half_life_hours"] is None:
                continue
            if iso_id in has_parent:
                other_initials = [
                    i for i in analysis["initial_isotopes"] if i != iso_id
                ]
                is_fed = any(
                    iso_id in [dm["daughter"] for dm in iso_data[p]["decay_modes"]]
                    for p in other_initials
                    if p in iso_data
                )
                if is_fed:
                    continue
            prev_act = None
            for snap in analysis["time_snapshots"]:
                act = snap["predicted_activities_bq"].get(iso_id, 0.0)
                if prev_act is not None and prev_act > 0:
                    assert act <= prev_act + FLOAT_TOL, (
                        f"{sid}/{iso_id}: root activity should decrease"
                    )
                prev_act = act


# ── Test 11: Bateman equation accuracy ──────────────────────────────

def test_11_bateman_accuracy(report, fixtures):
    iso_data, policy, _, samples, _ = fixtures
    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        sample = samples[sid]
        for snap in analysis["time_snapshots"]:
            t = snap["time_hours"]
            expected = _compute_activities(iso_data, policy, sample, t)
            for iso_id in analysis["all_chain_isotopes"]:
                exp_act = expected.get(iso_id, 0.0)
                if exp_act < policy["min_activity_bq"]:
                    exp_act = 0.0
                got_act = snap["predicted_activities_bq"].get(iso_id, 0.0)
                assert _floats_close(got_act, exp_act), (
                    f"{sid}/{iso_id} at t={t}: expected {exp_act:.6f}, "
                    f"got {got_act:.6f}"
                )


# ── Test 12: Near-degenerate chain detection ────────────────────────

def test_12_near_degenerate(report, fixtures):
    iso_data, policy, _, samples, _ = fixtures
    rel_tol = policy["nearly_equal_lambda_rel_tol"]

    expected_pairs = set()
    for sid in samples:
        sample = samples[sid]
        all_isos = set()
        def collect(iso):
            all_isos.add(iso)
            for dm in iso_data[iso]["decay_modes"]:
                collect(dm["daughter"])
        for iso in sample["initial_activities_bq"]:
            collect(iso)

        for iso in all_isos:
            lam1 = _decay_constant(iso_data, iso)
            if lam1 == 0:
                continue
            for dm in iso_data[iso]["decay_modes"]:
                d = dm["daughter"]
                lam2 = _decay_constant(iso_data, d)
                if lam2 == 0:
                    continue
                rd = abs(lam1 - lam2) / max(lam1, lam2)
                if rd < rel_tol:
                    expected_pairs.add((sid, iso, d))

    actual_pairs = set()
    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        for nd in analysis["near_degenerate_pairs"]:
            actual_pairs.add((sid, nd["parent"], nd["daughter"]))

    assert actual_pairs == expected_pairs


# ── Test 13: Near-degenerate uses limiting form ─────────────────────

def test_13_near_degenerate_limiting_form(report, fixtures):
    """
    Verify that near-degenerate chains use the L'Hôpital limiting form,
    not the standard Bateman formula (which would give wildly wrong results).
    """
    iso_data, policy, _, samples, _ = fixtures

    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        if not analysis["near_degenerate_pairs"]:
            continue
        sample = samples[sid]
        for snap in analysis["time_snapshots"]:
            t = snap["time_hours"]
            if t == 0.0:
                continue
            expected = _compute_activities(iso_data, policy, sample, t)
            for nd in analysis["near_degenerate_pairs"]:
                daughter = nd["daughter"]
                exp_act = expected.get(daughter, 0.0)
                if exp_act < policy["min_activity_bq"]:
                    exp_act = 0.0
                got_act = snap["predicted_activities_bq"].get(daughter, 0.0)
                assert _floats_close(got_act, exp_act), (
                    f"{sid}/{daughter} at t={t}: near-degenerate daughter "
                    f"expected {exp_act:.6f}, got {got_act:.6f}. "
                    f"Are you using the limiting form of Bateman?"
                )


# ── Test 14: Dose rate computation ──────────────────────────────────

def test_14_dose_rate(report, fixtures):
    iso_data, policy, _, samples, _ = fixtures
    for analysis in report["sample_analyses"]:
        sid = analysis["sample_id"]
        sample = samples[sid]
        for snap in analysis["time_snapshots"]:
            t = snap["time_hours"]
            expected = _compute_activities(iso_data, policy, sample, t)
            expected_dose = 0.0
            for iso_id, act in expected.items():
                if act < policy["min_activity_bq"]:
                    act = 0.0
                expected_dose += act * iso_data[iso_id]["dose_coefficient_sv_per_bq_h"]
            assert _floats_close(
                snap["dose_rate_sv_per_h"], expected_dose
            ), (
                f"{sid} at t={t}: dose_rate expected {expected_dose:.6f}, "
                f"got {snap['dose_rate_sv_per_h']}"
            )


# ── Test 15: Total activity and clearance ───────────────────────────

def test_15_clearance(report, fixtures):
    _, policy, _, _, _ = fixtures
    for analysis in report["sample_analyses"]:
        for snap in analysis["time_snapshots"]:
            total = sum(
                v for v in snap["predicted_activities_bq"].values()
            )
            assert _floats_close(snap["total_activity_bq"], total), (
                f"total_activity_bq mismatch at t={snap['time_hours']}"
            )
            expected_above = total > policy["clearance_activity_bq"]
            assert snap["above_clearance"] == expected_above


# ── Test 16: Measurement comparison structure ───────────────────────

def test_16_measurement_comparison_structure(report, fixtures):
    _, _, _, _, measurements = fixtures
    comps = report["measurement_comparisons"]
    total_expected = sum(len(rows) for rows in measurements.values())
    assert len(comps) == total_expected
    required = {
        "detector_id", "sample_id", "isotope_id", "time_hours",
        "predicted_bq", "measured_bq", "uncertainty_bq",
        "residual_bq", "z_score", "is_anomaly",
    }
    for c in comps:
        assert set(c.keys()) == required


# ── Test 17: Measurement comparison values ──────────────────────────

def test_17_measurement_values(report, fixtures):
    iso_data, policy, _, samples, measurements = fixtures
    det_sample = {}
    for det_id, rows in measurements.items():
        if rows:
            det_sample[det_id] = rows[0]["sample_id"]

    for comp in report["measurement_comparisons"]:
        det_id = comp["detector_id"]
        sid = comp["sample_id"]
        iso_id = comp["isotope_id"]
        t = comp["time_hours"]
        measured = comp["measured_bq"]
        uncertainty = comp["uncertainty_bq"]

        sample = samples[sid]
        predicted = _compute_activities(iso_data, policy, sample, t)
        pred_val = predicted.get(iso_id, 0.0)
        if pred_val < policy["min_activity_bq"]:
            pred_val = 0.0

        assert _floats_close(comp["predicted_bq"], pred_val), (
            f"{det_id}/{iso_id} at t={t}: predicted mismatch"
        )
        expected_residual = measured - pred_val
        assert _floats_close(comp["residual_bq"], expected_residual), (
            f"{det_id}/{iso_id} at t={t}: residual mismatch"
        )
        expected_z = abs(expected_residual) / uncertainty if uncertainty > 0 else 0.0
        assert _floats_close(comp["z_score"], expected_z), (
            f"{det_id}/{iso_id} at t={t}: z_score mismatch"
        )
        expected_anomaly = expected_z > policy["anomaly_sigma_threshold"]
        assert comp["is_anomaly"] == expected_anomaly, (
            f"{det_id}/{iso_id} at t={t}: is_anomaly mismatch"
        )


# ── Test 18: Anomaly count ──────────────────────────────────────────

def test_18_anomaly_count(report):
    anomalies = [c for c in report["measurement_comparisons"] if c["is_anomaly"]]
    assert len(anomalies) == report["summary"]["total_anomalies"]
    assert len(anomalies) == 5, (
        f"Expected exactly 5 anomalies, got {len(anomalies)}"
    )


# ── Test 19: Finding types and severities ───────────────────────────

def test_19_finding_severities(report, fixtures):
    _, policy, _, _, _ = fixtures
    sev_map = policy["finding_severity"]
    for f in report["findings"]:
        ft = f["finding_type"]
        assert ft in sev_map, f"Unknown finding type: {ft}"
        assert f["severity"] == sev_map[ft], (
            f"Severity mismatch for {ft}: expected {sev_map[ft]}, "
            f"got {f['severity']}"
        )


# ── Test 20: Finding sort order ─────────────────────────────────────

def test_20_finding_sort_order(report, fixtures):
    _, policy, _, _, _ = fixtures
    sev_ranks = policy["severity_ranks"]
    findings = report["findings"]
    for i in range(1, len(findings)):
        prev = findings[i - 1]
        curr = findings[i]
        pk = (
            sev_ranks.get(prev["severity"], 99),
            prev["finding_type"],
            prev["sample_id"],
            prev.get("time_hours") if prev.get("time_hours") is not None else -1,
        )
        ck = (
            sev_ranks.get(curr["severity"], 99),
            curr["finding_type"],
            curr["sample_id"],
            curr.get("time_hours") if curr.get("time_hours") is not None else -1,
        )
        assert pk <= ck, f"Findings not sorted at index {i}: {pk} > {ck}"


# ── Test 21: Finding evidence keys per type ─────────────────────────

def test_21_finding_evidence_keys(report):
    expected_keys = {
        "dose_rate_exceeded": {"dose_rate_sv_per_h", "limit_sv_per_h"},
        "measurement_anomaly": {
            "detector_id", "isotope_id", "predicted_bq", "measured_bq", "z_score"
        },
        "clearance_violation": {"total_activity_bq", "clearance_level_bq"},
        "near_degenerate_chain": {"parent", "daughter", "relative_difference"},
    }
    for f in report["findings"]:
        ft = f["finding_type"]
        if ft in expected_keys:
            assert set(f["evidence"].keys()) == expected_keys[ft], (
                f"Evidence key mismatch for {ft}: "
                f"expected {expected_keys[ft]}, got {set(f['evidence'].keys())}"
            )


# ── Test 22: Findings by type count ─────────────────────────────────

def test_22_findings_by_type(report):
    fbt = {}
    for f in report["findings"]:
        fbt[f["finding_type"]] = fbt.get(f["finding_type"], 0) + 1
    assert report["summary"]["findings_by_type"] == fbt


# ── Test 23: Findings by severity count ─────────────────────────────

def test_23_findings_by_severity(report):
    fbs = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in report["findings"]:
        fbs[f["severity"]] += 1
    assert report["summary"]["findings_by_severity"] == fbs


# ── Test 24: Zone safety assessment ─────────────────────────────────

def test_24_zone_safety(report, fixtures):
    iso_data, policy, facility, samples, measurements = fixtures
    zones = report["zone_safety_assessment"]
    zone_ids = [z["zone_id"] for z in zones]
    assert zone_ids == sorted(zone_ids)

    det_sample = {}
    for det_id, rows in measurements.items():
        if rows:
            det_sample[det_id] = rows[0]["sample_id"]

    for zone_entry in zones:
        zid = zone_entry["zone_id"]
        zone_cfg = facility["storage_zones"][zid]
        assert zone_entry["samples"] == zone_cfg["samples"]
        assert _floats_close(
            zone_entry["shielding_factor"], zone_cfg["shielding_factor"]
        )
        assert _floats_close(
            zone_entry["max_total_activity_bq"],
            zone_cfg["max_total_activity_bq"],
        ), f"Zone {zid}: max_total_activity_bq mismatch"


# ── Test 25: Zone dose rate with shielding ──────────────────────────

def test_25_zone_shielded_dose(report, fixtures):
    iso_data, policy, facility, samples, measurements = fixtures
    det_sample = {}
    for det_id, rows in measurements.items():
        if rows:
            det_sample[det_id] = rows[0]["sample_id"]

    for zone_entry in report["zone_safety_assessment"]:
        zid = zone_entry["zone_id"]
        zone_cfg = facility["storage_zones"][zid]
        sf = zone_cfg["shielding_factor"]

        for te in zone_entry["time_evaluations"]:
            t = te["time_hours"]
            total_act = 0.0
            total_dose = 0.0
            for sid in zone_cfg["samples"]:
                if sid in samples:
                    pred = _compute_activities(iso_data, policy, samples[sid], t)
                    for iso_id, act in pred.items():
                        if act >= policy["min_activity_bq"]:
                            total_act += act
                            total_dose += act * iso_data[iso_id][
                                "dose_coefficient_sv_per_bq_h"
                            ]
            shielded = total_dose * sf
            assert _floats_close(te["total_activity_bq"], total_act), (
                f"Zone {zid} at t={t}: total_activity mismatch"
            )
            assert _floats_close(te["unshielded_dose_rate_sv_per_h"], total_dose), (
                f"Zone {zid} at t={t}: unshielded_dose mismatch"
            )
            assert _floats_close(te["shielded_dose_rate_sv_per_h"], shielded), (
                f"Zone {zid} at t={t}: shielded_dose mismatch"
            )
            expected_exceeds = total_act > zone_cfg["max_total_activity_bq"]
            assert te["exceeds_zone_limit"] == expected_exceeds, (
                f"Zone {zid} at t={t}: exceeds_zone_limit mismatch"
            )


# ── Test 26: Equilibrium checks ─────────────────────────────────────

def test_26_equilibrium_checks(report, fixtures):
    iso_data, policy, _, samples, measurements = fixtures

    det_sample = {}
    for det_id, rows in measurements.items():
        if rows:
            det_sample[det_id] = rows[0]["sample_id"]
    sample_times = {}
    for det_id, rows in measurements.items():
        sid = det_sample[det_id]
        for row in rows:
            sample_times.setdefault(sid, set()).add(float(row["timestamp_hours"]))

    expected_total = 0
    for sid in sorted(samples):
        sample = samples[sid]
        initial = sample["initial_activities_bq"]
        times = sorted(sample_times.get(sid, set()))
        for iso_id in sorted(initial):
            lam_p = _decay_constant(iso_data, iso_id)
            if lam_p == 0:
                continue
            for dm in iso_data[iso_id]["decay_modes"]:
                daughter = dm["daughter"]
                lam_d = _decay_constant(iso_data, daughter)
                if lam_d == 0 or lam_p >= lam_d:
                    continue
                for t in times:
                    predicted = _compute_activities(iso_data, policy, sample, t)
                    a_p = predicted.get(iso_id, 0.0)
                    if a_p < policy["min_activity_bq"]:
                        a_p = 0.0
                    if a_p > policy["min_activity_bq"]:
                        eq_val = a_p * dm["branching_ratio"]
                        if eq_val > 0:
                            expected_total += 1

    actual_total = sum(
        len(a["equilibrium_checks"]) for a in report["sample_analyses"]
    )
    assert actual_total == expected_total, (
        f"Expected {expected_total} equilibrium checks, got {actual_total}"
    )

    for analysis in report["sample_analyses"]:
        for ec in analysis["equilibrium_checks"]:
            parent = ec["parent"]
            daughter = ec["daughter"]
            lam_p = _decay_constant(iso_data, parent)
            lam_d = _decay_constant(iso_data, daughter)
            assert lam_p < lam_d, (
                f"Equilibrium check for {parent}->{daughter}: "
                f"parent must be longer-lived"
            )
            br = None
            for dm in iso_data[parent]["decay_modes"]:
                if dm["daughter"] == daughter:
                    br = dm["branching_ratio"]
            assert br is not None
            expected_eq = ec["parent_activity_bq"] * br
            assert _floats_close(ec["expected_equilibrium_bq"], expected_eq)
            if expected_eq > 0:
                ratio = ec["daughter_activity_bq"] / expected_eq
                dev = abs(ratio - 1.0)
                assert _floats_close(ec["deviation"], dev)
                assert ec["in_equilibrium"] == (
                    dev <= policy["equilibrium_ratio_tolerance"]
                )


# ── Test 27: Findings completeness ──────────────────────────────────

def test_27_findings_completeness(report, fixtures):
    """Independently verify that all expected findings are generated."""
    iso_data, policy, _, samples, measurements = fixtures

    det_sample = {}
    for det_id, rows in measurements.items():
        if rows:
            det_sample[det_id] = rows[0]["sample_id"]

    sample_times = {}
    for det_id, rows in measurements.items():
        sid = det_sample[det_id]
        for row in rows:
            sample_times.setdefault(sid, set()).add(float(row["timestamp_hours"]))

    expected_counts = {
        "dose_rate_exceeded": 0,
        "clearance_violation": 0,
        "measurement_anomaly": 0,
        "near_degenerate_chain": 0,
    }

    for sid in sorted(samples):
        sample = samples[sid]
        times = sorted(sample_times.get(sid, set()))
        for t in times:
            predicted = _compute_activities(iso_data, policy, sample, t)
            total_act = 0.0
            total_dose = 0.0
            for iso_id, act in predicted.items():
                if act < policy["min_activity_bq"]:
                    act = 0.0
                total_act += act
                total_dose += act * iso_data[iso_id]["dose_coefficient_sv_per_bq_h"]
            if total_dose > policy["dose_rate_limit_sv_per_h"]:
                expected_counts["dose_rate_exceeded"] += 1
            if total_act > policy["clearance_activity_bq"]:
                expected_counts["clearance_violation"] += 1

    for det_id in sorted(measurements):
        sid = det_sample[det_id]
        sample = samples[sid]
        for row in measurements[det_id]:
            t = float(row["timestamp_hours"])
            iso_id = row["isotope_id"]
            uncertainty = float(row["uncertainty_bq"])
            measured = float(row["measured_bq"])
            predicted = _compute_activities(iso_data, policy, sample, t)
            pred_val = predicted.get(iso_id, 0.0)
            if pred_val < policy["min_activity_bq"]:
                pred_val = 0.0
            residual = measured - pred_val
            z = abs(residual) / uncertainty if uncertainty > 0 else 0.0
            if z > policy["anomaly_sigma_threshold"]:
                expected_counts["measurement_anomaly"] += 1

    rel_tol = policy["nearly_equal_lambda_rel_tol"]
    for sid in sorted(samples):
        sample = samples[sid]
        all_isos = set()
        def _collect(iso):
            all_isos.add(iso)
            for dm in iso_data[iso]["decay_modes"]:
                _collect(dm["daughter"])
        for iso in sample["initial_activities_bq"]:
            _collect(iso)
        for iso in sorted(all_isos):
            lam1 = _decay_constant(iso_data, iso)
            if lam1 == 0:
                continue
            for dm in iso_data[iso]["decay_modes"]:
                lam2 = _decay_constant(iso_data, dm["daughter"])
                if lam2 == 0:
                    continue
                if abs(lam1 - lam2) / max(lam1, lam2) < rel_tol:
                    expected_counts["near_degenerate_chain"] += 1

    actual_counts = {}
    for f in report["findings"]:
        actual_counts[f["finding_type"]] = actual_counts.get(f["finding_type"], 0) + 1

    for ftype, expected in expected_counts.items():
        actual = actual_counts.get(ftype, 0)
        assert actual == expected, (
            f"Finding type '{ftype}': expected {expected}, got {actual}"
        )


# ── Test 28: JSON formatting ────────────────────────────────────────

def test_28_json_formatting():
    with open(REPORT_PATH, "r") as f:
        raw = f.read()
    assert raw.endswith("\n"), "Report must end with trailing newline"
    assert "\t" not in raw, "Report must use spaces, not tabs"
    parsed = json.loads(raw)
    reformatted = json.dumps(parsed, indent=2) + "\n"
    assert raw == reformatted, "Report must use 2-space indent"


# ── Test 29: Float rounding to 6 decimals ───────────────────────────

def test_29_float_rounding(report):
    def check_floats(obj, path=""):
        if isinstance(obj, float):
            s = f"{obj:.10f}"
            decimal_part = s.split(".")[1]
            trailing = decimal_part[6:]
            assert all(c == "0" for c in trailing), (
                f"Float at {path} has more than 6 decimal places: {obj}"
            )
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("lambda_parent", "lambda_daughter"):
                    continue
                if k == "relative_difference":
                    continue
                check_floats(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                check_floats(v, f"{path}[{i}]")

    check_floats(report["sample_analyses"])
    check_floats(report["measurement_comparisons"])
    check_floats(report["zone_safety_assessment"])


# ── Test 30: Stable isotope activity is zero ────────────────────────

def test_30_stable_isotopes_zero(report, fixtures):
    iso_data = fixtures[0]
    stable = {iso for iso, d in iso_data.items() if d["half_life_hours"] is None}
    for analysis in report["sample_analyses"]:
        for snap in analysis["time_snapshots"]:
            for iso_id in snap["predicted_activities_bq"]:
                if iso_id in stable:
                    assert snap["predicted_activities_bq"][iso_id] == 0.0, (
                        f"Stable isotope {iso_id} must have zero activity"
                    )


# ── Test 31: Daughter grows then decays ─────────────────────────────

def test_31_daughter_growth(report, fixtures):
    """
    For S01 (Zy224→Zy220), Zy220 starts at 200 Bq and should grow
    before eventually decaying, since it receives atoms from Zy224.
    """
    for analysis in report["sample_analyses"]:
        if analysis["sample_id"] != "S01":
            continue
        activities = [
            snap["predicted_activities_bq"].get("Zy220", 0.0)
            for snap in analysis["time_snapshots"]
        ]
        assert max(activities) > activities[0], (
            "Zy220 in S01 should grow above initial 200 Bq due to Zy224 feeding"
        )
        assert activities[-1] < max(activities), (
            "Zy220 in S01 should eventually decay after peaking"
        )


# ── Test 32: S04 daughter-only decay ────────────────────────────────

def test_32_daughter_only(report, fixtures):
    """
    S04 has only Zy220 (no parent Zy224). Activity should monotonically
    decrease since there's no feeding.
    """
    for analysis in report["sample_analyses"]:
        if analysis["sample_id"] != "S04":
            continue
        activities = [
            snap["predicted_activities_bq"].get("Zy220", 0.0)
            for snap in analysis["time_snapshots"]
        ]
        for i in range(1, len(activities)):
            assert activities[i] <= activities[i-1] + FLOAT_TOL, (
                "S04/Zy220 should decay monotonically without parent feeding"
            )


# ── Test 33: Short-lived intermediate ───────────────────────────────

def test_33_short_lived_intermediate(report, fixtures):
    """
    Tx306 (half-life 0.25h) should rapidly reach secular equilibrium
    with Tx310 (half-life 8h) and then track Tx310's decay.
    """
    iso_data, policy, _, samples, _ = fixtures
    for analysis in report["sample_analyses"]:
        if analysis["sample_id"] != "S02":
            continue
        for snap in analysis["time_snapshots"]:
            if snap["time_hours"] < 2.0:
                continue
            a_310 = snap["predicted_activities_bq"].get("Tx310", 0.0)
            a_306 = snap["predicted_activities_bq"].get("Tx306", 0.0)
            if a_310 > policy["min_activity_bq"]:
                ratio = a_306 / a_310
                assert 0.9 < ratio < 1.1, (
                    f"Tx306 should be in secular equilibrium with Tx310 "
                    f"at t={snap['time_hours']}, ratio={ratio:.4f}"
                )


# ── Test 34: Measurement comparison sorting ─────────────────────────

def test_34_comparison_sorting(report):
    comps = report["measurement_comparisons"]
    for i in range(1, len(comps)):
        prev = comps[i-1]
        curr = comps[i]
        pk = (prev["detector_id"], prev["time_hours"], prev["isotope_id"])
        ck = (curr["detector_id"], curr["time_hours"], curr["isotope_id"])
        assert pk <= ck, f"Comparisons not sorted at index {i}"


# ── Test 35: Branching ratio conservation ───────────────────────────

def test_35_branching_conservation(report, fixtures):
    """
    At late times, for Zy224 → Zy220 (0.65) + Mv190 (0.35),
    the total daughter production should conserve branching ratios.
    Integrated production of Zy220 / integrated production of Mv190
    should approach 0.65/0.35 ≈ 1.857.
    """
    for analysis in report["sample_analyses"]:
        if analysis["sample_id"] != "S01":
            continue
        last_snap = analysis["time_snapshots"][-1]
        a_zy220 = last_snap["predicted_activities_bq"].get("Zy220", 0.0)
        a_mv190 = last_snap["predicted_activities_bq"].get("Mv190", 0.0)
        assert a_zy220 > 0 or a_mv190 > 0, "Both daughters should have activity"


# ── Test 36: Specific anomaly detector+isotope ──────────────────────

def test_36_specific_anomalies(report):
    """Check that specific known anomalies are detected."""
    anomalies = [c for c in report["measurement_comparisons"] if c["is_anomaly"]]
    anom_keys = {
        (c["detector_id"], c["time_hours"], c["isotope_id"]) for c in anomalies
    }
    expected = {
        ("det_alpha", 200.0, "Zy224"),
        ("det_beta", 16.0, "Tx310"),
        ("det_gamma", 500.0, "Fn246"),
        ("det_gamma", 100.0, "Wp400"),
        ("det_epsilon", 600.0, "Fn250"),
    }
    assert anom_keys == expected, (
        f"Anomaly mismatch: extra={anom_keys - expected}, "
        f"missing={expected - anom_keys}"
    )
