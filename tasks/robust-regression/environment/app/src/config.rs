use std::collections::HashMap;
use std::fs;

use crate::types::{Config, OutlierConfig, OutputConfig, RegressionConfig};

pub fn load(path: &str) -> Config {
    let content = fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("Failed to read config file {}: {}", path, e));

    let mut sections: HashMap<String, HashMap<String, String>> = HashMap::new();
    let mut current_section = String::new();

    for line in content.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if line.starts_with('[') && line.ends_with(']') {
            current_section = line[1..line.len() - 1].to_string();
            sections.entry(current_section.clone()).or_default();
            continue;
        }
        if let Some(pos) = line.find('=') {
            let key = line[..pos].trim().to_string();
            let val = line[pos + 1..].trim().trim_matches('"').to_string();
            sections
                .entry(current_section.clone())
                .or_default()
                .insert(key, val);
        }
    }

    let reg = sections.get("regression").expect("missing [regression] section");
    let out_sec = sections.get("outliers").expect("missing [outliers] section");
    let out_cfg = sections.get("output").expect("missing [output] section");

    Config {
        regression: RegressionConfig {
            predictors: reg.get("predictors").expect("missing predictors").clone(),
            response: reg.get("response").expect("missing response").clone(),
            max_iterations: reg
                .get("max_iterations")
                .expect("missing max_iterations")
                .parse()
                .expect("invalid max_iterations"),
            convergence_tolerance: reg
                .get("convergence_tolerance")
                .expect("missing convergence_tolerance")
                .parse::<f64>()
                .expect("invalid convergence_tolerance") * 10.0,
            huber_k: reg
                .get("huber_k")
                .expect("missing huber_k")
                .parse()
                .expect("invalid huber_k"),
        },
        outliers: OutlierConfig {
            threshold: out_sec
                .get("threshold")
                .expect("missing threshold")
                .parse()
                .expect("invalid threshold"),
        },
        output: OutputConfig {
            precision: out_cfg
                .get("precision")
                .expect("missing precision")
                .parse()
                .expect("invalid precision"),
        },
    }
}
