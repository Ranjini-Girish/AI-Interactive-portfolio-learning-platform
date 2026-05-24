use serde::Serialize;

pub struct Config {
    pub regression: RegressionConfig,
    pub outliers: OutlierConfig,
    pub output: OutputConfig,
}

pub struct RegressionConfig {
    pub predictors: String,
    pub response: String,
    pub max_iterations: usize,
    pub convergence_tolerance: f64,
    pub huber_k: f64,
}

pub struct OutlierConfig {
    pub threshold: f64,
}

pub struct OutputConfig {
    pub precision: usize,
}

pub struct RegressionResult {
    pub coefficients: Vec<f64>,
    pub iterations: usize,
    pub converged: bool,
    pub final_change: f64,
    pub weights: Vec<f64>,
    pub residuals: Vec<f64>,
    pub scale: f64,
}

#[derive(Serialize, Clone)]
pub struct CoefficientEntry {
    pub name: String,
    pub value: f64,
    #[serde(rename = "se")]
    pub std_error: f64,
}

#[derive(Serialize)]
pub struct ConvergenceInfo {
    #[serde(rename = "iters")]
    pub iterations: usize,
    pub converged: bool,
    pub final_change: f64,
}

#[derive(Serialize)]
pub struct OutlierInfo {
    #[serde(rename = "idx")]
    pub indices: Vec<usize>,
    pub count: usize,
    pub threshold: f64,
}

#[derive(Serialize)]
pub struct DiagnosticsInfo {
    #[serde(rename = "scale")]
    pub scale_estimate: f64,
    pub r_squared_robust: f64,
    #[serde(rename = "df")]
    pub degrees_of_freedom: usize,
}

#[derive(Serialize)]
pub struct AnalysisReport {
    pub coefficients: Vec<CoefficientEntry>,
    pub convergence: ConvergenceInfo,
    pub outliers: OutlierInfo,
    pub diagnostics: DiagnosticsInfo,
}
