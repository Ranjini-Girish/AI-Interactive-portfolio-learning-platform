"""Behavioral tests
 for the spectral calibration audit task (C++17).

The agent must implement the pipeline in C++17 under /app/src/, ship a
/app/Makefile that builds /app/build/calibrate, and that binary must produce
the documented outputs in /app/output/. These tests:

  1. Verify the C++ build artefacts exist and the build is reproducible from
     a clean state (`make clean && make`).
  2. Verify there is no Python solver under /app.
  3. Verify the binary is byte-deterministic across re-runs.
  4. Independently re-derive every output value in Python from the live
     /app/experiments inputs (robust baseline, Qn scale estimator, sample
     variance, intensity-weighted centroid, iterative reweighted WLS) and
     assert the agent's outputs match.
"""

# ruff: noqa: E501

import csv
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

EXPERIMENTS_TREE_SHA256 = (
    "a0e6f04c3ab89008d960befce6f38076f35bc91b3ded2bc253affb596e83eead"
)

APP_ROOT = Path(os.environ.get("APP_ROOT", "/app"))
EXP_DIR = APP_ROOT / "experiments"
OUT_DIR = APP_ROOT / "output"
SRC_DIR = APP_ROOT / "src"
BUILD_DIR = APP_ROOT / "build"
BINARY = BUILD_DIR / "calibrate"
MAKEFILE = APP_ROOT / "Makefile"
DISPLAY_EXP = Path(os.environ.get("SCA_APP_EXPERIMENTS", "/app/experiments"))

DRIFT_K_SIGMA = 2.5
DRIFT_MAX_ITER = 5

QN_ASYMPTOTIC_CONSTANT = 2.21914


# ---------------------------------------------------------------------------
# small numerical helpers (independent reference implementations)
# ---------------------------------------------------------------------------
def round6(x: float) -> float:
    return round(float(x), 6)


def round4(x: float) -> float:
    return round(float(x), 4)


def load_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def list_source_files() -> list[str]:
    out: list[str] = []
    for path in EXP_DIR.rglob("*"):
        if path.is_file():
            rel = path.relative_to(EXP_DIR)
            out.append(str(DISPLAY_EXP / rel))
    out.sort()
    return out


def parse_rows(path: Path) -> list[tuple[float, float]]:
    rows: list[tuple[float, float]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                wavelength = float(row.get("wavelength_nm", ""))
                intensity = float(row.get("intensity", ""))
            except ValueError:
                continue
            if math.isfinite(wavelength) and math.isfinite(intensity):
                rows.append((wavelength, intensity))
    return rows


def inside_window(w: float, window: list[float]) -> bool:
    return window[0] <= w <= window[1]


def outside_all(w: float, peaks: list[dict]) -> bool:
    return all(not inside_window(w, peak["window_nm"]) for peak in peaks)


def qn_asymptotic_reference(values: list[float]) -> float:
    """Asymptotic Rousseeuw-Croux Qn scale estimator.

    Definition:
        Qn(x) = c_n * d_(k)
    where d_(k) is the k-th order statistic (1-indexed) of pairwise absolute
    differences { |x_i - x_j| : i < j }, h = floor(n/2) + 1, k = h*(h-1)/2,
    and the asymptotic constant c_n = 2.21914.
    Returns 0.0 for n < 2.
    """
    n = len(values)
    if n < 2:
        return 0.0
    diffs = sorted(abs(values[i] - values[j]) for i in range(n) for j in range(i + 1, n))
    h = n // 2 + 1
    k = h * (h - 1) // 2
    return QN_ASYMPTOTIC_CONSTANT * diffs[k - 1]


def welford_sample_variance(values: list[float]) -> float:
    n = 0
    mean = 0.0
    m2 = 0.0
    for x in values:
        n += 1
        delta = x - mean
        mean += delta / n
        delta2 = x - mean
        m2 += delta * delta2
    if n < 2:
        return 0.0
    return m2 / (n - 1)


def robust_baseline(off_peak: list[float]) -> float | None:
    """Returns the arithmetic mean of the 3*MAD-filtered survivors of the
    off-peak pool, or None when the pool is empty / no row survives.
    """
    if not off_peak:
        return None
    median = statistics.median(off_peak)
    deviations = [abs(x - median) for x in off_peak]
    mad = statistics.median(deviations)
    if mad == 0.0:
        kept = [x for x in off_peak if x == median]
    else:
        kept = [x for x in off_peak if abs(x - median) <= 3.0 * mad]
    if not kept:
        return None
    return sum(kept) / len(kept)


def merged_metadata(run: dict, instruments: dict, batches: dict) -> dict | None:
    instrument = instruments.get(run.get("instrument"))
    batch = batches.get(run.get("batch"))
    if not isinstance(instrument, dict) or not isinstance(batch, dict):
        return None
    merged = {**instrument, **batch, **run}
    required = [
        "run_id", "instrument", "batch", "operator", "calibrant",
        "temperature_c", "wavelength_offset_nm", "quality_flag", "spectrum",
    ]
    if any(key not in merged or merged[key] in (None, "") for key in required):
        return None
    return merged


def wls_fit_with_rstd(
    xs: list[float], ys: list[float], ws: list[float]
) -> tuple[float, float, float]:
    sw = sum(ws)
    if sw == 0.0 or not xs:
        return 0.0, 0.0, 0.0
    xbar = sum(w * x for w, x in zip(ws, xs)) / sw
    ybar = sum(w * y for w, y in zip(ws, ys)) / sw
    sxx = sum(w * (x - xbar) ** 2 for w, x in zip(ws, xs))
    if sxx == 0.0:
        slope, intercept = 0.0, ybar
    else:
        sxy = sum(w * (x - xbar) * (y - ybar) for w, x, y in zip(ws, xs, ys))
        slope = sxy / sxx
        intercept = ybar - slope * xbar
    sse = sum(w * (y - (slope * x + intercept)) ** 2 for w, x, y in zip(ws, xs, ys))
    return slope, intercept, math.sqrt(sse / sw)


def iterative_wls(
    points: list[tuple[float, float, float]],
    k_sigma: float = DRIFT_K_SIGMA,
    max_iter: int = DRIFT_MAX_ITER,
) -> tuple[float, float, float, int, int]:
    """Iterative reweighted WLS — initial fit is iteration 1."""
    n = len(points)
    if n == 0:
        return 0.0, 0.0, 0.0, 0, 0
    kept = list(range(n))
    iters = 0
    slope, intercept, rstd = 0.0, 0.0, 0.0
    while iters < max_iter:
        iters += 1
        kept_pts = [points[i] for i in kept]
        xs = [float(p[0]) for p in kept_pts]
        ys = [float(p[1]) for p in kept_pts]
        ws = [float(p[2]) for p in kept_pts]
        if len({x for x in xs}) < 2:
            sw = sum(ws)
            slope = 0.0
            intercept = sum(w * y for w, y in zip(ws, ys)) / sw if sw > 0 else 0.0
            sse = sum(w * (y - intercept) ** 2 for w, y in zip(ws, ys))
            rstd = math.sqrt(sse / sw) if sw > 0 else 0.0
        else:
            slope, intercept, rstd = wls_fit_with_rstd(xs, ys, ws)
        if rstd == 0.0:
            break
        threshold = k_sigma * rstd
        new_kept = [
            i for i in kept
            if abs(points[i][1] - (slope * points[i][0] + intercept)) <= threshold
        ]
        if len(new_kept) < 2 or len(new_kept) == len(kept):
            break
        kept = new_kept
    return slope, intercept, rstd, n - len(kept), iters


def single_shot_wls(
    points: list[tuple[float, float, float]],
) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    ws = [float(p[2]) for p in points]
    sw = sum(ws)
    if sw == 0.0:
        return 0.0, 0.0
    if len({x for x in xs}) < 2:
        return 0.0, sum(w * y for w, y in zip(ws, ys)) / sw
    s, i, _ = wls_fit_with_rstd(xs, ys, ws)
    return s, i


# ---------------------------------------------------------------------------
# pipeline reference (mirrors the documented contract)
# ---------------------------------------------------------------------------
def compute_expected_outputs() -> tuple[dict, dict, list[dict]]:
    manifest = load_json(EXP_DIR / "manifest.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")

    included_partials: list[dict] = []
    excluded_runs: list[dict] = []
    raw_peaks: list[dict] = []

    for run in manifest["runs"]:
        run_id = run["run_id"]
        md = merged_metadata(run, instruments, batches)
        if md is None or md.get("calibrant") not in calibrants:
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "missing_metadata"})
            continue
        if md["quality_flag"] != "ok":
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "quality_flag"})
            continue
        spec_path = EXP_DIR / md["spectrum"]
        if not spec_path.is_file():
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "missing_metadata"})
            continue
        rows = parse_rows(spec_path)
        if len(rows) < 8:
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "insufficient_rows"})
            continue
        peaks_spec = calibrants[md["calibrant"]]
        intensities = [i for _, i in rows]
        intensity_var = welford_sample_variance(intensities)
        off_peak = [i for w, i in rows if outside_all(w, peaks_spec)]
        baseline = robust_baseline(off_peak)
        if baseline is None:
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "no_baseline"})
            continue
        noise_floor_qn = qn_asymptotic_reference(off_peak)

        offset = float(md["wavelength_offset_nm"])
        run_raw_peaks: list[dict] = []
        missing = False
        for peak in peaks_spec:
            weighted = [(w, i - baseline) for w, i in rows
                        if inside_window(w, peak["window_nm"]) and i - baseline > 0]
            if not weighted:
                missing = True
                break
            area = sum(c for _, c in weighted)
            w_raw = sum(w * c for w, c in weighted) / area
            observed_raw = w_raw - offset
            run_raw_peaks.append({
                "run_id": run_id,
                "instrument": md["instrument"],
                "batch": md["batch"],
                "calibrant": md["calibrant"],
                "peak_label": peak["label"],
                "expected_nm": peak["expected_nm"],
                "observed_nm_raw": observed_raw,
                "raw_error_nm": observed_raw - peak["expected_nm"],
                "peak_area_raw": area,
            })
        if missing:
            excluded_runs.append({"run_id": run_id, "status": "excluded", "reason": "missing_peak"})
            continue
        raw_peaks.extend(run_raw_peaks)
        included_partials.append({
            "run_id": run_id,
            "instrument": md["instrument"],
            "batch": md["batch"],
            "operator": md["operator"],
            "calibrant": md["calibrant"],
            "temperature_c": md["temperature_c"],
            "wavelength_offset_nm": offset,
            "baseline": baseline,
            "noise_floor_qn": noise_floor_qn,
            "intensity_var": intensity_var,
        })

    by_group: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in raw_peaks:
        by_group[(p["calibrant"], p["instrument"])].append(p)
    fits: dict[tuple[str, str], tuple[float, float]] = {}
    fit_meta: dict[tuple[str, str], dict] = {}
    for k, g in by_group.items():
        pts = [(p["expected_nm"], p["raw_error_nm"], p["peak_area_raw"]) for p in g]
        slope, intercept, rstd, n_out, iters = iterative_wls(pts)
        fits[k] = (slope, intercept)
        fit_meta[k] = {
            "residual_stddev_nm": rstd,
            "n_outliers_removed": n_out,
            "iterations_used": iters,
        }

    corrected_peaks: list[dict] = []
    errors_by_run: dict[str, list[float]] = defaultdict(list)
    for p in raw_peaks:
        slope, intercept = fits[(p["calibrant"], p["instrument"])]
        trend = slope * p["expected_nm"] + intercept
        observed = p["observed_nm_raw"] - trend
        error = observed - p["expected_nm"]
        errors_by_run[p["run_id"]].append(error)
        corrected_peaks.append({
            "run_id": p["run_id"],
            "instrument": p["instrument"],
            "batch": p["batch"],
            "calibrant": p["calibrant"],
            "peak_label": p["peak_label"],
            "expected_nm": p["expected_nm"],
            "observed_nm": round6(observed),
            "error_nm": round6(error),
            "peak_area": round6(p["peak_area_raw"]),
            "_unrounded_error": error,
        })

    included_runs: list[dict] = []
    for partial in included_partials:
        run_errors = errors_by_run[partial["run_id"]]
        rms = math.sqrt(sum(e * e for e in run_errors) / len(run_errors))
        included_runs.append({
            "run_id": partial["run_id"],
            "instrument": partial["instrument"],
            "batch": partial["batch"],
            "operator": partial["operator"],
            "calibrant": partial["calibrant"],
            "temperature_c": partial["temperature_c"],
            "wavelength_offset_nm": partial["wavelength_offset_nm"],
            "baseline": round6(partial["baseline"]),
            "noise_floor_qn": round6(partial["noise_floor_qn"]),
            "intensity_var": round6(partial["intensity_var"]),
            "rms_error_nm": round6(rms),
            "status": "included",
        })

    included_runs.sort(key=lambda row: row["run_id"])
    excluded_runs.sort(key=lambda row: row["run_id"])
    corrected_peaks.sort(key=lambda row: (row["run_id"], row["peak_label"]))

    audit = {
        "included_runs": included_runs,
        "excluded_runs": excluded_runs,
        "source_files": list_source_files(),
    }
    return audit, expected_summary(included_runs, corrected_peaks, fit_meta), corrected_peaks


def expected_summary(
    included_runs: list[dict],
    peak_rows: list[dict],
    fit_meta: dict[tuple[str, str], dict],
) -> dict:
    errors_by_group = defaultdict(list)
    runs_by_group = defaultdict(set)
    errors_by_run = defaultdict(list)
    for row in peak_rows:
        key = (row["calibrant"], row["instrument"])
        errors_by_group[key].append(row["_unrounded_error"])
        runs_by_group[key].add(row["run_id"])
        errors_by_run[row["run_id"]].append(row["_unrounded_error"])

    calibrants: list[dict] = []
    for calibrant, instrument in sorted(errors_by_group):
        errors = errors_by_group[(calibrant, instrument)]
        meta = fit_meta[(calibrant, instrument)]
        calibrants.append({
            "calibrant": calibrant,
            "instrument": instrument,
            "run_count": len(runs_by_group[(calibrant, instrument)]),
            "peak_count": len(errors),
            "mean_error_nm": round6(sum(errors) / len(errors)),
            "rms_error_nm": round6(math.sqrt(sum(e * e for e in errors) / len(errors))),
            "residual_stddev_nm": round6(meta["residual_stddev_nm"]),
            "n_outliers_removed": int(meta["n_outliers_removed"]),
            "iterations_used": int(meta["iterations_used"]),
        })

    best: list[dict] = []
    runs_by_calibrant = defaultdict(list)
    for run in included_runs:
        max_abs = max((abs(e) for e in errors_by_run.get(run["run_id"], [])), default=0.0)
        runs_by_calibrant[run["calibrant"]].append((run, max_abs))
    for calibrant in sorted(runs_by_calibrant):
        candidates = runs_by_calibrant[calibrant]
        chosen = sorted(candidates, key=lambda pair: (
            round4(pair[0]["rms_error_nm"]), pair[1], pair[0]["run_id"],
        ))[0][0]
        best.append({
            "calibrant": calibrant,
            "run_id": chosen["run_id"],
            "instrument": chosen["instrument"],
            "rms_error_nm": chosen["rms_error_nm"],
        })
    return {"calibrants": calibrants, "best_run_by_calibrant": best}


def load_outputs() -> tuple[dict, dict, list[dict]]:
    audit = load_json(OUT_DIR / "run_audit.json")
    summary = load_json(OUT_DIR / "calibration_summary.json")
    with (OUT_DIR / "peak_table.csv").open(newline="") as handle:
        peak_rows = list(csv.DictReader(handle))
    return audit, summary, peak_rows


def numeric_peak_row(row: dict) -> dict:
    converted = dict(row)
    for key in ["expected_nm", "observed_nm", "error_nm", "peak_area"]:
        converted[key] = round6(float(converted[key]))
    return converted


def public_peak_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        clean = dict(row)
        clean.pop("_unrounded_error", None)
        out.append(clean)
    return out


# ---------------------------------------------------------------------------
# C++ build / artefact tests
# ---------------------------------------------------------------------------
def test_makefile_present_and_reproducible_build():
    """Verify /app/Makefile exists, /app/src holds at least one C++ source,
    and `make clean && make` succeeds.
    """
    assert MAKEFILE.is_file(), "missing /app/Makefile — the contract requires it at the top level"
    assert SRC_DIR.is_dir(), "missing /app/src — agent must place C++17 sources there"
    cpp_sources = sorted(SRC_DIR.rglob("*.cpp"))
    assert cpp_sources, "no .cpp files under /app/src — submission must be in C++17"
    res = subprocess.run(
        ["make", "-s", "clean"],
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"`make clean` failed: stdout={res.stdout!r}\nstderr={res.stderr!r}"
    res = subprocess.run(
        ["make", "-s"],
        cwd=str(APP_ROOT),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, (
        f"`make` failed:\nstdout={res.stdout!r}\nstderr={res.stderr!r}"
    )
    assert BINARY.is_file() and os.access(BINARY, os.X_OK), (
        "/app/build/calibrate must exist and be executable after `make`"
    )


def test_experiments_dir_is_immutable_against_shipped_tree_hash():
    """The agent must treat /app/experiments as strictly read-only. Verify
    every shipped input file is byte-identical to its shipped form (and no
    extras have been added) by comparing a deterministic SHA-256 over the
    sorted-by-relative-path tree against the hash committed at task-build
    time.

    An agent that tampered with inputs (e.g. nudged a wavelength to game the
    drift fit, or pre-baked an off-peak pool) would fail here even if its
    outputs match the recomputed pipeline — because the recompute would also
    be done on the tampered inputs.
    """
    if not EXP_DIR.is_dir():
        raise AssertionError(f"missing experiments dir at {EXP_DIR}")
    h = hashlib.sha256()
    files = sorted(p for p in EXP_DIR.rglob("*") if p.is_file())
    for path in files:
        rel = str(path.relative_to(EXP_DIR)).replace(os.sep, "/")
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    actual = h.hexdigest()
    assert actual == EXPERIMENTS_TREE_SHA256, (
        f"/app/experiments/ was modified during the run.\n"
        f"  shipped tree hash: {EXPERIMENTS_TREE_SHA256}\n"
        f"  current tree hash: {actual}\n"
        f"  the directory must be treated as strictly read-only"
    )


def test_no_python_solution_file_exists_anywhere_in_app():
    """The contract is C++17 only. Any *.py file under /app outside
    /app/experiments (the read-only input directory) is a forbidden Python
    shortcut — including disguised solvers in /app/output, /app/environment,
    /app/src, or /app/build.
    """
    if not APP_ROOT.is_dir():
        return
    for path in APP_ROOT.rglob("*.py"):
        rel = path.relative_to(APP_ROOT)
        if str(rel).startswith("experiments/"):
            continue
        raise AssertionError(
            f"forbidden Python file at {path}; the task contract is C++17 only"
        )


def test_binary_output_is_byte_deterministic_across_runs():
    """Re-invoke /app/build/calibrate from a copy of /app and require the
    three output files to be byte-identical to the original run.
    """
    assert BINARY.is_file(), "binary missing — earlier build test should have caught this"
    original_outputs = {
        name: (OUT_DIR / name).read_bytes()
        for name in ("run_audit.json", "calibration_summary.json", "peak_table.csv")
    }
    rerun_dir = APP_ROOT.parent / "_calibrate_rerun"
    if rerun_dir.exists():
        shutil.rmtree(rerun_dir)
    rerun_dir.mkdir()
    shutil.copytree(EXP_DIR, rerun_dir / "experiments")
    (rerun_dir / "output").mkdir()
    env = os.environ.copy()
    env["APP_ROOT"] = str(rerun_dir)
    res = subprocess.run([str(BINARY)], cwd=str(rerun_dir), env=env,
                         capture_output=True, text=True)
    try:
        assert res.returncode == 0, (
            f"re-run of /app/build/calibrate failed: rc={res.returncode}\n"
            f"stdout={res.stdout!r}\nstderr={res.stderr!r}"
        )
        for name, original in original_outputs.items():
            rerun_bytes = (rerun_dir / "output" / name).read_bytes()
            assert rerun_bytes == original, (
                f"{name} differs across re-runs ({len(rerun_bytes)} vs {len(original)} bytes); "
                f"the binary must be byte-deterministic."
            )
    finally:
        shutil.rmtree(rerun_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# output schema & high-level structure tests
# ---------------------------------------------------------------------------
def test_output_files_and_top_level_schemas():
    assert (OUT_DIR / "run_audit.json").is_file()
    assert (OUT_DIR / "calibration_summary.json").is_file()
    assert (OUT_DIR / "peak_table.csv").is_file()

    audit, summary, peak_rows = load_outputs()
    assert set(audit) == {"included_runs", "excluded_runs", "source_files"}
    assert set(summary) == {"calibrants", "best_run_by_calibrant"}
    assert peak_rows
    assert set(peak_rows[0]) == {
        "run_id", "instrument", "batch", "calibrant", "peak_label",
        "expected_nm", "observed_nm", "error_nm", "peak_area",
    }
    assert audit["included_runs"], "included_runs must not be empty"
    required_run_keys = {
        "run_id", "instrument", "batch", "operator", "calibrant",
        "temperature_c", "wavelength_offset_nm", "baseline",
        "noise_floor_qn", "intensity_var",
        "rms_error_nm", "status",
    }
    assert set(audit["included_runs"][0]) == required_run_keys, (
        f"included run object keys = {sorted(audit['included_runs'][0])}, "
        f"expected = {sorted(required_run_keys)}"
    )
    required_summary_keys = {
        "calibrant", "instrument", "run_count", "peak_count",
        "mean_error_nm", "rms_error_nm", "residual_stddev_nm",
        "n_outliers_removed", "iterations_used",
    }
    assert summary["calibrants"], "calibrants must not be empty"
    assert set(summary["calibrants"][0]) == required_summary_keys, (
        f"calibrants object keys = {sorted(summary['calibrants'][0])}, "
        f"expected = {sorted(required_summary_keys)}"
    )


def test_source_files_listing_is_sorted_and_complete():
    """`run_audit.source_files` must be the sorted list of every regular file
    beneath /app/experiments, expressed as absolute paths.
    """
    audit, _, _ = load_outputs()
    expected = list_source_files()
    assert audit["source_files"] == expected, (
        "source_files must be every file under /app/experiments expressed as "
        "an absolute path, sorted ASCII-ascending. Got "
        f"{audit['source_files'][:3]}... (len={len(audit['source_files'])}); "
        f"expected {expected[:3]}... (len={len(expected)})."
    )
    assert audit["source_files"] == sorted(audit["source_files"])
    assert all(p.startswith("/app/experiments/") for p in audit["source_files"])


def test_included_and_excluded_run_sets_and_reasons():
    expected_audit, _, _ = compute_expected_outputs()
    audit, _, _ = load_outputs()
    assert [row["run_id"] for row in audit["included_runs"]] == [
        row["run_id"] for row in expected_audit["included_runs"]
    ]
    assert audit["excluded_runs"] == expected_audit["excluded_runs"]
    assert {row["reason"] for row in audit["excluded_runs"]} == {
        "insufficient_rows", "missing_metadata", "missing_peak",
        "no_baseline", "quality_flag",
    }


def test_metadata_inheritance_and_quality_overrides():
    audit, _, _ = load_outputs()
    included = {row["run_id"]: row for row in audit["included_runs"]}
    excluded = {row["run_id"]: row for row in audit["excluded_runs"]}
    assert included["r001"]["operator"] == "Elena"
    assert included["r002"]["operator"] == "Jules"
    assert included["r010"]["operator"] == "Anika"
    assert included["r014"]["status"] == "included"
    assert included["r015"]["batch"] == "batch_quarantine"
    assert excluded["r005"]["reason"] == "quality_flag"
    assert excluded["r006"]["reason"] == "missing_metadata"
    assert excluded["r016"]["reason"] == "quality_flag"


def test_run_audit_numeric_values_match_recomputed_pipeline():
    expected_audit, _, _ = compute_expected_outputs()
    audit, _, _ = load_outputs()
    assert audit["included_runs"] == expected_audit["included_runs"]


def test_peak_table_header_is_exact_documented_string():
    expected_header = (
        "run_id,instrument,batch,calibrant,peak_label,"
        "expected_nm,observed_nm,error_nm,peak_area"
    )
    with (OUT_DIR / "peak_table.csv").open() as handle:
        first_line = handle.readline().rstrip("\r\n")
    assert first_line == expected_header


def test_peak_table_rows_match_drift_corrected_pipeline():
    _, _, expected_peaks = compute_expected_outputs()
    _, _, peak_rows = load_outputs()
    expected_public = public_peak_rows(expected_peaks)
    assert [row["run_id"] for row in peak_rows] == sorted(row["run_id"] for row in peak_rows)
    assert [numeric_peak_row(row) for row in peak_rows] == expected_public


def test_calibration_summary_aggregates_match_peak_level_errors():
    _, expected_summary_doc, _ = compute_expected_outputs()
    _, summary, _ = load_outputs()
    assert summary["calibrants"] == expected_summary_doc["calibrants"]
    assert summary["calibrants"] == sorted(
        summary["calibrants"], key=lambda row: (row["calibrant"], row["instrument"])
    )
    assert all(row["peak_count"] == row["run_count"] * 3 for row in summary["calibrants"])


def test_best_run_by_calibrant_matches_lexicographic_tie_break():
    _, expected_summary_doc, _ = compute_expected_outputs()
    _, summary, _ = load_outputs()
    assert summary["best_run_by_calibrant"] == expected_summary_doc["best_run_by_calibrant"]
    for entry in summary["best_run_by_calibrant"]:
        assert set(entry) == {"calibrant", "run_id", "instrument", "rms_error_nm"}


def test_output_sort_orders_are_deterministic():
    audit, summary, peak_rows = load_outputs()
    assert audit["included_runs"] == sorted(audit["included_runs"], key=lambda row: row["run_id"])
    assert audit["excluded_runs"] == sorted(audit["excluded_runs"], key=lambda row: row["run_id"])
    assert audit["source_files"] == sorted(audit["source_files"])
    assert summary["best_run_by_calibrant"] == sorted(
        summary["best_run_by_calibrant"], key=lambda row: row["calibrant"]
    )
    assert peak_rows == sorted(peak_rows, key=lambda row: (row["run_id"], row["peak_label"]))


def test_outputs_have_representative_content_not_only_counts():
    audit, summary, peak_rows = load_outputs()
    assert any(row["calibrant"] == "argon" and row["instrument"] == "spec_b" for row in summary["calibrants"])
    assert any(row["reason"] == "missing_peak" for row in audit["excluded_runs"])
    assert any(row["peak_label"] == "Ar738" and float(row["peak_area"]) > 0 for row in peak_rows)
    assert all(row["status"] == "included" for row in audit["included_runs"])
    assert all(row["status"] == "excluded" for row in audit["excluded_runs"])


def test_included_runs_temperature_c_and_offset_inheritance_and_overrides():
    manifest = load_json(EXP_DIR / "manifest.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    runs_by_id = {run["run_id"]: run for run in manifest["runs"]}

    def expected(run_id: str) -> tuple[float, float]:
        run = runs_by_id[run_id]
        temp = (float(run["temperature_c"]) if run.get("temperature_c") is not None
                else float(batches[run["batch"]]["temperature_c"]))
        offset = float(instruments[run["instrument"]]["wavelength_offset_nm"])
        return temp, offset

    assert expected("r001") == (22.2, 0.05)
    assert expected("r002") == (21.9, 0.05)
    assert expected("r003") == (24.4, -0.075)
    assert expected("r004") == (24.7, -0.075)

    audit, _, _ = load_outputs()
    by_id = {row["run_id"]: row for row in audit["included_runs"]}
    for rid, (et, eo) in [("r001", (22.2, 0.05)), ("r002", (21.9, 0.05)),
                          ("r003", (24.4, -0.075)), ("r004", (24.7, -0.075))]:
        assert rid in by_id
        row = by_id[rid]
        assert float(row["temperature_c"]) == et
        assert float(row["wavelength_offset_nm"]) == eo


def test_json_outputs_use_two_space_indentation():
    for name in ("run_audit.json", "calibration_summary.json"):
        path = OUT_DIR / name
        lines = path.read_text().splitlines()
        assert len(lines) > 1, f"{name} must be multi-line 2-space-indented JSON"
        for lineno, line in enumerate(lines, start=1):
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            assert "\t" not in line[:indent], f"{name}:{lineno} uses a tab in indent"
            assert indent % 2 == 0, f"{name}:{lineno} indent {indent} is not multiple of 2"


# ---------------------------------------------------------------------------
# discriminating tests for the Qn scale estimator (DSA + scientific computing)
# ---------------------------------------------------------------------------
def test_noise_floor_qn_matches_rousseeuw_croux_reference_value():
    """Verify the per-run `noise_floor_qn` field equals the asymptotic
    Rousseeuw-Croux Qn scale estimator over the off-peak pool.

    A solver that emitted the median absolute deviation (MAD), the standard
    deviation, the IQR, the Qn with an off-by-one in the order-statistic
    index k, or the wrong asymptotic constant will all produce a different
    value here.
    """
    audit, _, _ = load_outputs()
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")
    manifest = load_json(EXP_DIR / "manifest.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    by_run = {row["run_id"]: row for row in audit["included_runs"]}
    checked = 0
    for run in manifest["runs"]:
        md = merged_metadata(run, instruments, batches)
        if md is None or md.get("calibrant") not in calibrants:
            continue
        if md["quality_flag"] != "ok":
            continue
        rid = md["run_id"]
        if rid not in by_run:
            continue
        rows = parse_rows(EXP_DIR / md["spectrum"])
        if len(rows) < 8:
            continue
        peaks_spec = calibrants[md["calibrant"]]
        off_peak = [i for w, i in rows if outside_all(w, peaks_spec)]
        if not off_peak:
            continue
        expected = round6(qn_asymptotic_reference(off_peak))
        actual = round6(by_run[rid]["noise_floor_qn"])
        # Cross-check: this would be the value if the agent emitted MAD
        # by mistake. We only flag this if it actually diverges from Qn —
        # for some samples MAD and Qn happen to agree.
        median = statistics.median(off_peak)
        mad = statistics.median(abs(x - median) for x in off_peak)
        assert actual == expected, (
            f"{rid}: noise_floor_qn = {actual!r}, expected {expected!r}.\n"
            f"  off-peak pool ({len(off_peak)} rows): {sorted(off_peak)}\n"
            f"  MAD of pool = {mad:.6f} (would round to {round6(mad)} if "
            f"the agent emitted MAD by mistake).\n"
            f"  noise_floor_qn must be the asymptotic Rousseeuw-Croux Qn "
            f"scale estimator (constant {QN_ASYMPTOTIC_CONSTANT}) of the "
            f"off-peak pool."
        )
        checked += 1
    assert checked >= 5, (
        f"only {checked} runs validated for noise_floor_qn; fixture must "
        f"provide enough included runs to exercise the Qn discriminator"
    )


def test_noise_floor_qn_diverges_from_mad_on_at_least_one_run():
    """Sanity: ensure the fixture itself contains at least one run where
    Qn != MAD, so that emitting MAD instead of Qn would actually fail. If
    this ever passes vacuously (Qn==MAD everywhere) the discriminator is
    broken and the fixture must be perturbed.
    """
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")
    manifest = load_json(EXP_DIR / "manifest.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    diverged = 0
    for run in manifest["runs"]:
        md = merged_metadata(run, instruments, batches)
        if md is None or md.get("calibrant") not in calibrants:
            continue
        if md["quality_flag"] != "ok":
            continue
        rows = parse_rows(EXP_DIR / md["spectrum"])
        if len(rows) < 8:
            continue
        off = [i for w, i in rows if outside_all(w, calibrants[md["calibrant"]])]
        if not off:
            continue
        m = statistics.median(off)
        mad = statistics.median(abs(x - m) for x in off)
        qn = qn_asymptotic_reference(off)
        if round6(mad) != round6(qn):
            diverged += 1
    assert diverged >= 1, (
        "fixture is broken: Qn == MAD on every off-peak pool, so a MAD-only "
        "solver would silently pass the noise_floor_qn test"
    )


def test_intensity_var_uses_sample_variance_n_minus_one():
    """Verify the per-run `intensity_var` field equals the sample variance
    (n-1 denominator) of every valid spectrum row's `intensity` value.

    A solver who used the population variance (n denominator) will diverge
    by a factor of n/(n-1).
    """
    audit, _, _ = load_outputs()
    manifest = load_json(EXP_DIR / "manifest.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    by_run = {row["run_id"]: row for row in audit["included_runs"]}
    checked = 0
    for run in manifest["runs"]:
        md = merged_metadata(run, instruments, batches)
        if md is None:
            continue
        rid = md.get("run_id", run.get("run_id"))
        if rid not in by_run:
            continue
        rows = parse_rows(EXP_DIR / md["spectrum"])
        if len(rows) < 8:
            continue
        intensities = [i for _, i in rows]
        expected = round6(welford_sample_variance(intensities))
        n = len(intensities)
        mean = sum(intensities) / n
        textbook = sum((x - mean) ** 2 for x in intensities) / (n - 1) if n > 1 else 0.0
        assert math.isclose(welford_sample_variance(intensities), textbook, rel_tol=1e-9, abs_tol=1e-12), (
            "Welford reference disagrees with two-pass formula on canonical fixture"
        )
        actual = round6(by_run[rid]["intensity_var"])
        assert actual == expected, (
            f"{rid}: intensity_var = {actual!r}, expected {expected!r}.\n"
            f"  intensity_var is the SAMPLE variance (n-1 denominator) of "
            f"every valid intensity row.\n"
            f"  If your value equals {round6(textbook * (n - 1) / n)} you used "
            f"the POPULATION variance (n denominator)."
        )
        checked += 1
    assert checked >= 5


# ---------------------------------------------------------------------------
# discriminating tests for the iterative reweighted WLS drift core
# ---------------------------------------------------------------------------
def _recompute_group_raw_points(
    cal_name: str, inst_name: str
) -> tuple[list[tuple[float, float, float, str, str]], dict[tuple[str, str], float]]:
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")
    instruments = load_json(EXP_DIR / "config" / "instruments.json")
    batches = load_json(EXP_DIR / "config" / "batches.json")
    manifest = load_json(EXP_DIR / "manifest.json")
    peaks_spec = calibrants[cal_name]
    raw_points: list[tuple[float, float, float, str, str]] = []
    raw_observed: dict[tuple[str, str], float] = {}

    for run in manifest["runs"]:
        md = merged_metadata(run, instruments, batches)
        if md is None or md.get("calibrant") != cal_name or md.get("instrument") != inst_name:
            continue
        if md["quality_flag"] != "ok":
            continue
        rows = parse_rows(EXP_DIR / md["spectrum"])
        if len(rows) < 8:
            continue
        off = [i for w, i in rows if outside_all(w, peaks_spec)]
        baseline = robust_baseline(off)
        if baseline is None:
            continue
        offset = float(md["wavelength_offset_nm"])
        rid = md["run_id"]
        run_pts: list[tuple[float, float, float, str, str]] = []
        run_obs: dict[tuple[str, str], float] = {}
        missing = False
        for peak in peaks_spec:
            weighted = [(w, i - baseline) for w, i in rows
                        if inside_window(w, peak["window_nm"]) and i - baseline > 0]
            if not weighted:
                missing = True
                break
            area = sum(c for _, c in weighted)
            w_raw = sum(w * c for w, c in weighted) / area
            observed_raw = w_raw - offset
            raw_error = observed_raw - peak["expected_nm"]
            run_pts.append((peak["expected_nm"], raw_error, area, rid, peak["label"]))
            run_obs[(rid, peak["label"])] = observed_raw
        if missing:
            continue
        raw_points.extend(run_pts)
        raw_observed.update(run_obs)
    return raw_points, raw_observed


def test_drift_uses_iterative_reweighted_wls_not_single_shot():
    """Lock in iterative outlier rejection: agent's drift-corrected
    observed_nm values must match iterative_wls and NOT single_shot_wls on
    every group whose iterative-vs-single-shot trends diverge by > 1e-5 nm.
    """
    calibrants_cfg = load_json(EXP_DIR / "config" / "calibrants.json")
    instruments_cfg = load_json(EXP_DIR / "config" / "instruments.json")
    batches_cfg = load_json(EXP_DIR / "config" / "batches.json")
    groups: set[tuple[str, str]] = set()
    for run in load_json(EXP_DIR / "manifest.json")["runs"]:
        md = merged_metadata(run, instruments_cfg, batches_cfg)
        if md is None or md.get("calibrant") not in calibrants_cfg:
            continue
        if md.get("quality_flag") != "ok":
            continue
        groups.add((md["calibrant"], md["instrument"]))

    _, _, peak_rows = load_outputs()
    rows_by_key = {(r["run_id"], r["peak_label"]): r for r in peak_rows}

    discriminating = False
    diag: list[str] = []
    for cal, inst in sorted(groups):
        raw_points, raw_observed = _recompute_group_raw_points(cal, inst)
        if len(raw_points) < 3:
            continue
        triples = [(x, y, w) for x, y, w, *_ in raw_points]
        it_slope, it_int, _, n_out, _ = iterative_wls(triples)
        ss_slope, ss_int = single_shot_wls(triples)
        max_diff = 0.0
        for x, *_ in raw_points:
            d = abs((it_slope * x + it_int) - (ss_slope * x + ss_int))
            if d > max_diff:
                max_diff = d
        diag.append(f"  ({cal}, {inst}): n_outliers_removed={n_out}, max diff={max_diff:.6e}")
        if max_diff < 1e-5:
            continue
        for x, _y, _w, rid, label in raw_points:
            row = rows_by_key.get((rid, label))
            if row is None:
                continue
            agent = round6(float(row["observed_nm"]))
            it = round6(raw_observed[(rid, label)] - (it_slope * x + it_int))
            ss = round6(raw_observed[(rid, label)] - (ss_slope * x + ss_int))
            if abs(it - ss) < 1e-6:
                continue
            assert agent == it, (
                f"{rid}/{label} (group {cal}, {inst}): observed_nm = {agent}.\n"
                f"  Iterative reweighted WLS target: {it} (matches the contract).\n"
                f"  Single-shot WLS (FORBIDDEN)    : {ss}\n"
                f"  Iterative slope/intercept = {it_slope:.6e} / {it_int:.6e}\n"
                f"  Diagnostics:\n" + "\n".join(diag)
            )
            discriminating = True
    assert discriminating, (
        "no group exercised the iterative-vs-single-shot discriminator:\n"
        + "\n".join(diag)
    )


def test_iterations_used_off_by_one_initial_fit_is_iteration_one():
    _, summary, _ = load_outputs()
    _, expected_summary_doc, _ = compute_expected_outputs()
    expected_meta = {
        (c["calibrant"], c["instrument"]): c
        for c in expected_summary_doc["calibrants"]
    }
    for row in summary["calibrants"]:
        key = (row["calibrant"], row["instrument"])
        ref = expected_meta[key]
        for field in ("iterations_used", "n_outliers_removed"):
            assert int(row[field]) == int(ref[field]), (
                f"group {key}: {field}={row[field]!r}, expected {ref[field]!r}.\n"
                f"  iterations_used counts every weighted fit performed; the "
                f"initial fit (before any rejection) is iteration 1."
            )
        assert int(row["iterations_used"]) >= 1
        if int(row["n_outliers_removed"]) > 0:
            assert int(row["iterations_used"]) >= 2, (
                f"group {key}: dropped {row['n_outliers_removed']} peak(s) but "
                f"iterations_used={row['iterations_used']}; rejecting >=1 outlier "
                f"requires at least one refit, so iterations_used must be >= 2."
            )


def test_at_least_one_group_triggers_outlier_rejection():
    _, summary, _ = load_outputs()
    triggered = [c for c in summary["calibrants"] if int(c["n_outliers_removed"]) >= 1]
    assert triggered, (
        "no group exercises the iterative outlier-rejection path; fixture is broken"
    )
    for row in triggered:
        assert int(row["iterations_used"]) >= 2


def test_baseline_uses_robust_mad_filtered_mean_not_plain_mean_or_median():
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")
    manifest = load_json(EXP_DIR / "manifest.json")
    r001 = next(run for run in manifest["runs"] if run["run_id"] == "r001")
    rows = parse_rows(EXP_DIR / r001["spectrum"])
    off_peak = [i for w, i in rows if outside_all(w, calibrants["neon"])]
    assert off_peak
    expected = robust_baseline(off_peak)
    assert expected is not None
    naive_mean = sum(off_peak) / len(off_peak)
    assert naive_mean > expected + 1.0, "fixture broken"
    audit, _, _ = load_outputs()
    r001_row = next(row for row in audit["included_runs"] if row["run_id"] == "r001")
    assert round6(r001_row["baseline"]) == round6(expected)
    assert round6(r001_row["baseline"]) != round6(naive_mean)


def test_r009_is_excluded_as_no_baseline_directly():
    audit, _, _ = load_outputs()
    excluded_by_id = {row["run_id"]: row for row in audit["excluded_runs"]}
    included_ids = {row["run_id"] for row in audit["included_runs"]}
    calibrants = load_json(EXP_DIR / "config" / "calibrants.json")
    manifest = load_json(EXP_DIR / "manifest.json")
    r009 = next(run for run in manifest["runs"] if run["run_id"] == "r009")
    rows = parse_rows(EXP_DIR / r009["spectrum"])
    off_peak = [i for w, i in rows if outside_all(w, calibrants["argon"])]
    assert off_peak == []
    assert "r009" not in included_ids
    assert excluded_by_id.get("r009", {}).get("reason") == "no_baseline"


def test_best_run_stored_rms_error_nm_is_six_decimals_not_four():
    audit, summary, _ = load_outputs()
    included_by_id = {row["run_id"]: row for row in audit["included_runs"]}
    for entry in summary["best_run_by_calibrant"]:
        ref = included_by_id.get(entry["run_id"])
        assert ref is not None
        assert entry["rms_error_nm"] == ref["rms_error_nm"], (
            "best_run_by_calibrant rms_error_nm must equal the 6-decimal value "
            "from included_runs, not be re-rounded to 4 decimals."
        )


def test_best_run_by_calibrant_tie_break_uses_max_abs_error_before_run_id():
    audit, summary, peak_rows = load_outputs()
    errors_by_run: dict[str, list[float]] = defaultdict(list)
    for p in peak_rows:
        errors_by_run[p["run_id"]].append(float(p["error_nm"]))
    runs_by_cal = defaultdict(list)
    for run in audit["included_runs"]:
        max_abs = max((abs(e) for e in errors_by_run.get(run["run_id"], [])), default=0.0)
        runs_by_cal[run["calibrant"]].append((run, max_abs))
    expected_best = []
    for cal in sorted(runs_by_cal):
        chosen = sorted(runs_by_cal[cal], key=lambda pair: (
            round4(pair[0]["rms_error_nm"]), pair[1], pair[0]["run_id"],
        ))[0][0]
        expected_best.append({
            "calibrant": cal,
            "run_id": chosen["run_id"],
            "instrument": chosen["instrument"],
            "rms_error_nm": chosen["rms_error_nm"],
        })
    assert summary["best_run_by_calibrant"] == expected_best
