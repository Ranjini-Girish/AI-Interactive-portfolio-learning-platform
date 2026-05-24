mod config;
mod covariance;
mod data;
mod diagnostics;
mod matrix;
mod outliers;
mod output;
mod regression;
mod statistics;
mod types;
mod validation;
mod weights;

fn main() {
    let cfg = config::load("/app/config/analysis.toml");
    let dataset = data::load_csv("/app/data/sensors.csv");

    validation::validate(&cfg, &dataset);

    let predictors: Vec<&str> = cfg.regression.predictors.split(',').collect();
    let (x, y) = data::build_design_matrix(&dataset, &predictors, &cfg.regression.response);

    let n = dataset.n_rows;
    let p = predictors.len() + 1;

    let result = regression::irls(&x, &y, n, p, &cfg);

    let cov = covariance::sandwich(&x, &result.residuals, &result.weights, n, p);

    let outlier_indices = outliers::detect(&result.residuals, result.scale, cfg.outliers.threshold);

    let r_squared = diagnostics::r_squared_robust(&y, &result.residuals, &result.weights);

    let report = output::build_report(
        &result,
        &cov,
        &outlier_indices,
        r_squared,
        &predictors,
        p,
        n,
        cfg.output.precision,
        cfg.outliers.threshold,
    );

    output::write_json(&report, "/app/output/analysis.json");
    eprintln!("Analysis complete. Output written to /app/output/analysis.json");
}
