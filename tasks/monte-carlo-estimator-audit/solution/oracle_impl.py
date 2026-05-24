"""
Oracle solution — ground truth implementation.
Reads inputs from /app/ and writes output to /app/output/.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA_DIR = Path("/app/data")
CONFIG_DIR = Path("/app/config")
OUT_DIR = Path("/app/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

FUNC_DIR = DATA_DIR / "functions"
SAMPLES_DIR = DATA_DIR / "samples"

ROUND_DIGITS = 8


def roundN(x, n=ROUND_DIGITS):
    if x is None:
        return None
    if isinstance(x, int):
        return x
    return round(x, n)


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def evaluate_function(func_def, x):
    ftype = func_def["type"]
    p = func_def["params"]
    if ftype == "polynomial":
        return sum(c * x**i for i, c in enumerate(p["coefficients"]))
    elif ftype == "trigonometric":
        return p["amplitude"] * math.sin(p["frequency"] * x + p["phase"]) + p["offset"]
    elif ftype == "exponential":
        return p["amplitude"] * math.exp(p["rate"] * x)
    elif ftype == "logarithmic":
        return p["amplitude"] * math.log(p["scale"] * x + p["shift"])
    elif ftype == "rational":
        denom = p["x2_coeff"] * x * x + p["x1_coeff"] * x + p["x0_coeff"]
        return p["numerator"] / denom
    elif ftype == "absolute_value":
        return abs(x - p["center"])
    elif ftype == "gaussian_density":
        return p["amplitude"] * math.exp(-((x - p["mean"])**2) / (2.0 * p["sigma"]**2))
    elif ftype == "step":
        return p["value_below"] if x < p["threshold"] else p["value_above"]
    elif ftype == "oscillatory":
        return p["amplitude"] * math.cos(2.0 * p["periods"] * math.pi * x)
    elif ftype == "constant":
        return p["value"]
    else:
        raise ValueError(f"Unknown: {ftype}")


def main():
    func_files = sorted(FUNC_DIR.glob("*.json"))
    functions = []
    for fp in func_files:
        functions.append(json.loads(fp.read_text(encoding="utf-8")))

    methods_cfg = json.loads((CONFIG_DIR / "methods.json").read_text(encoding="utf-8"))
    audit_cfg = json.loads((CONFIG_DIR / "audit_params.json").read_text(encoding="utf-8"))

    sample_sizes = audit_cfg["sample_sizes"]
    methods = {m["id"]: m for m in methods_cfg["methods"]}
    method_ids = [m["id"] for m in methods_cfg["methods"]]

    all_samples = {}
    for n in sample_sizes:
        sp = SAMPLES_DIR / f"samples_n{n:05d}.json"
        data = json.loads(sp.read_text(encoding="utf-8"))
        all_samples[n] = data["values"]

    results = []
    result_map = {}

    for func_def in functions:
        fid = func_def["id"]
        exact = func_def["exact_integral"]

        for mid in method_ids:
            method = methods[mid]

            for n in sample_sizes:
                samples = all_samples[n]

                if mid == "crude_mc":
                    values = [evaluate_function(func_def, x) for x in samples]
                    estimate = sum(values) / n
                    mean_val = estimate
                    pop_var = sum((v - mean_val)**2 for v in values) / n

                elif mid == "antithetic":
                    y_values = [(evaluate_function(func_def, x) + evaluate_function(func_def, 1.0 - x)) / 2.0
                                for x in samples]
                    estimate = sum(y_values) / n
                    mean_val = estimate
                    pop_var = sum((v - mean_val)**2 for v in y_values) / n

                elif mid == "stratified":
                    K = method["num_strata"]
                    base_count = n // K
                    extra = n % K
                    strata_counts = [base_count + (1 if k < extra else 0) for k in range(K)]

                    strata_estimates = []
                    strata_variances = []
                    idx = 0
                    for k in range(K):
                        nk = strata_counts[k]
                        stratum_values = []
                        for j in range(nk):
                            u = samples[idx + j]
                            x = (k + u) / K
                            stratum_values.append(evaluate_function(func_def, x))
                        idx += nk
                        stratum_mean = sum(stratum_values) / nk
                        strata_estimates.append(stratum_mean)
                        if nk >= 2:
                            s_var = sum((v - stratum_mean)**2 for v in stratum_values) / nk
                        else:
                            s_var = 0.0
                        strata_variances.append((s_var, nk))

                    estimate = sum(strata_estimates) / K
                    pop_var = sum(sv / nk for sv, nk in strata_variances) / (K * K)

                elif mid == "control_variate":
                    mu_g = method["control_exact_mean"]
                    f_vals = [evaluate_function(func_def, x) for x in samples]
                    g_vals = list(samples)
                    f_mean = sum(f_vals) / n
                    g_mean = sum(g_vals) / n
                    cov_fg = sum((f_vals[i] - f_mean) * (g_vals[i] - g_mean) for i in range(n)) / n
                    var_g = sum((g_vals[i] - g_mean)**2 for i in range(n)) / n
                    c_star = cov_fg / var_g if var_g > 0 else 0.0
                    y_values = [f_vals[i] - c_star * (g_vals[i] - mu_g) for i in range(n)]
                    estimate = sum(y_values) / n
                    mean_val = estimate
                    pop_var = sum((v - mean_val)**2 for v in y_values) / n

                abs_error = abs(estimate - exact)
                rel_error = abs_error / abs(exact) if exact != 0 else None
                std_error = math.sqrt(pop_var / n) if pop_var is not None else None
                evals_per = method["evaluations_per_sample"]
                cost_adj_var = pop_var * evals_per if pop_var is not None else None

                entry = {
                    "function_id": fid,
                    "method_id": mid,
                    "sample_size": n,
                    "estimate": roundN(estimate),
                    "exact_integral": roundN(exact),
                    "absolute_error": roundN(abs_error),
                    "relative_error": roundN(rel_error),
                    "sample_variance": roundN(pop_var),
                    "standard_error": roundN(std_error),
                    "cost_adjusted_variance": roundN(cost_adj_var)
                }
                results.append(entry)
                result_map[(fid, mid, n)] = entry

    results.sort(key=lambda r: (r["method_id"], r["function_id"], r["sample_size"]))

    convergence = []
    for func_def in functions:
        fid = func_def["id"]
        for mid in method_ids:
            for i in range(len(sample_sizes) - 1):
                n_small = sample_sizes[i]
                n_large = sample_sizes[i + 1]
                e_small = result_map[(fid, mid, n_small)]["absolute_error"]
                e_large = result_map[(fid, mid, n_large)]["absolute_error"]
                if e_small > 0 and e_large > 0 and e_small > e_large:
                    emp_order = math.log(e_small / e_large) / math.log(n_large / n_small)
                else:
                    emp_order = None
                convergence.append({
                    "function_id": fid,
                    "method_id": mid,
                    "n_small": n_small,
                    "n_large": n_large,
                    "error_small": roundN(e_small),
                    "error_large": roundN(e_large),
                    "empirical_order": roundN(emp_order)
                })

    convergence.sort(key=lambda c: (c["method_id"], c["function_id"], c["n_small"]))

    largest_n = sample_sizes[-1]
    efficiency_summary = []
    for func_def in functions:
        fid = func_def["id"]
        crude_cav = result_map[(fid, "crude_mc", largest_n)]["cost_adjusted_variance"]
        ratios = {}
        for mid in method_ids:
            method_cav = result_map[(fid, mid, largest_n)]["cost_adjusted_variance"]
            if mid == "crude_mc":
                ratios[mid] = 1.0
            elif crude_cav is not None and method_cav is not None and method_cav > 0:
                ratios[mid] = roundN(crude_cav / method_cav)
            else:
                ratios[mid] = None
        valid_ratios = {m: r for m, r in ratios.items() if r is not None}
        best = max(valid_ratios, key=valid_ratios.get) if valid_ratios else "crude_mc"
        efficiency_summary.append({
            "function_id": fid,
            "best_method": best,
            "efficiency_ratios": ratios
        })
    efficiency_summary.sort(key=lambda e: e["function_id"])

    report = {
        "metadata": {
            "total_functions": len(functions),
            "total_methods": len(method_ids),
            "sample_sizes": sample_sizes,
            "seed": json.loads((SAMPLES_DIR / f"samples_n{sample_sizes[0]:05d}.json").read_text(encoding="utf-8"))["seed"]
        },
        "results": results,
        "convergence": convergence,
        "efficiency_summary": efficiency_summary
    }

    write_json(OUT_DIR / "audit_report.json", report)


main()

if __name__ == "__main__":
    raise SystemExit(0)
