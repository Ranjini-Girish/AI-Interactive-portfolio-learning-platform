use crate::data::DataSet;
use crate::types::Config;

pub fn validate(config: &Config, data: &DataSet) {
    if data.n_rows < 4 {
        panic!(
            "Insufficient data: need at least 4 rows, got {}",
            data.n_rows
        );
    }

    let predictors: Vec<&str> = config.regression.predictors.split(',').collect();
    if predictors.is_empty() {
        panic!("No predictors specified in config");
    }

    for pred in &predictors {
        let pred = pred.trim();
        if !data.headers.contains(&pred.to_string()) {
            panic!("Predictor '{}' not found in CSV headers", pred);
        }
    }

    if !data.headers.contains(&config.regression.response) {
        panic!(
            "Response '{}' not found in CSV headers",
            config.regression.response
        );
    }

    if config.regression.max_iterations == 0 {
        panic!("max_iterations must be positive");
    }

    if config.regression.convergence_tolerance <= 0.0 {
        panic!("convergence_tolerance must be positive");
    }

    if config.regression.huber_k <= 0.0 {
        panic!("huber_k must be positive");
    }

    if config.outliers.threshold <= 0.0 {
        panic!("outlier threshold must be positive");
    }

    let n = data.n_rows;
    let p = predictors.len() + 1;
    if n <= p {
        panic!(
            "Underdetermined system: {} observations for {} parameters",
            n, p
        );
    }
}
