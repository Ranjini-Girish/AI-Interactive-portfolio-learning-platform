from __future__ import annotations

import csv
import json
import math
import os
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

DRIFT_K_SIGMA = 2.5
DRIFT_MAX_ITER = 5
QN_ASYMPTOTIC_CONSTANT = 2.21914

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')

def peaks_to_csv(peaks: list[dict]) -> str:
    import io
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[
        "run_id", "instrument", "batch", "calibrant", "peak_label",
        "expected_nm", "observed_nm", "error_nm", "peak_area",
    ])
    w.writeheader()
    for row in peaks:
        w.writerow({k: row[k] for k in w.fieldnames})
    return buf.getvalue()

def round6(x: float) -> float:
    return round(float(x), 6)


def round4(x: float) -> float:
    return round(float(x), 4)


def load_json(path: Path) -> dict:
    with path.open() as handle:
        return json.load(handle)


def list_source_files(exp_dir: Path) -> list[str]:
    out: list[str] = []
    for path in exp_dir.rglob("*"):
        if path.is_file():
            rel = path.relative_to(exp_dir)
            out.append(str(Path('/app/experiments') / rel))
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
def compute_expected_outputs_from(exp_dir: Path) -> tuple[dict, dict, list[dict]]:
    manifest = load_json(exp_dir / "manifest.json")
    instruments = load_json(exp_dir / "config" / "instruments.json")
    batches = load_json(exp_dir / "config" / "batches.json")
    calibrants = load_json(exp_dir / "config" / "calibrants.json")

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
        spec_path = exp_dir / md["spectrum"]
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
        "source_files": list_source_files(exp_dir),
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


def main() -> int:
    app_root = os.environ.get("APP_ROOT", "/app")
    exp = Path(app_root) / "experiments"
    out = Path(app_root) / "output"
    out.mkdir(parents=True, exist_ok=True)
    run_audit, summary, peaks = compute_expected_outputs_from(exp)
    write_canonical(out / "run_audit.json", run_audit)
    write_canonical(out / "calibration_summary.json", summary)
    (out / "peak_table.csv").write_text(peaks_to_csv(peaks), encoding="utf-8")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
