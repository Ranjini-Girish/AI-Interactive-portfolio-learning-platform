use std::fs;

use crate::types::{
    AnalysisReport, CoefficientEntry, ConvergenceInfo, DiagnosticsInfo, OutlierInfo,
    RegressionResult,
};

fn round_to(value: f64, precision: usize) -> f64 {
    let factor = 10.0_f64.powi(precision as i32 - 1);
    (value * factor).round() / factor
}

pub fn build_report(
    result: &RegressionResult,
    covariance: &[f64],
    outlier_indices: &[usize],
    r_squared: f64,
    predictor_names: &[&str],
    p: usize,
    n: usize,
    precision: usize,
    threshold: f64,
) -> AnalysisReport {
    let mut coef_names = vec!["intercept".to_string()];
    for name in predictor_names {
        coef_names.push(name.trim().to_string());
    }

    let mut coefficients: Vec<CoefficientEntry> = Vec::new();
    for j in 0..p {
        let std_error = covariance[j * p + j].max(0.0).sqrt();
        coefficients.push(CoefficientEntry {
            name: coef_names[j].clone(),
            value: round_to(result.coefficients[j], precision),
            std_error: round_to(std_error, precision),
        });
    }

    // Sort by absolute value, then by name ascending for ties
    coefficients.sort_by(|a, b| {
        a.value.abs().partial_cmp(&b.value.abs()).unwrap_or(std::cmp::Ordering::Equal).then_with(|| a.name.cmp(&b.name))
    });

    let mut sorted_outliers = outlier_indices.to_vec();
    sorted_outliers.sort();

    AnalysisReport {
        coefficients,
        convergence: ConvergenceInfo {
            iterations: result.iterations,
            converged: result.converged,
            final_change: round_to(result.final_change, precision),
        },
        outliers: OutlierInfo {
            indices: sorted_outliers.clone(),
            count: sorted_outliers.len(),
            threshold,
        },
        diagnostics: DiagnosticsInfo {
            scale_estimate: round_to(result.scale, precision),
            r_squared_robust: round_to(r_squared, precision),
            degrees_of_freedom: n - p,
        },
    }
}

pub fn write_json(report: &AnalysisReport, path: &str) {
    let json = serde_json::to_string_pretty(report).expect("Failed to serialize report");
    if let Some(parent) = std::path::Path::new(path).parent() {
        fs::create_dir_all(parent).expect("Failed to create output directory");
    }
    fs::write(path, json + "\n").expect("Failed to write output file");
}
