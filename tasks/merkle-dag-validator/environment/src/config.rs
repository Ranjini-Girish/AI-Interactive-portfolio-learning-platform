use serde::Deserialize;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Deserialize)]
pub struct Config {
    pub hash_algorithm: String,
    pub hash_truncate_bytes: usize,
    pub severity_levels: HashMap<String, u32>,
    pub repair_model: String,
    pub depth_algorithm: String,
    pub output_precision: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct HashParams {
    pub salt_prefix: String,
    pub separator: String,
    pub children_join: String,
    pub leaf_marker: String,
    pub children_sort_by: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Thresholds {
    pub max_depth: u32,
    pub max_repair_cost: u32,
    pub min_integrity_ratio: f64,
}

#[derive(Debug, Clone)]
pub struct FullConfig {
    pub config: Config,
    pub hash_params: HashParams,
    pub thresholds: Thresholds,
    pub weights: HashMap<String, u32>,
    pub severity_map: HashMap<String, String>,
}

pub fn load_config(data_dir: &Path) -> FullConfig {
    let config: Config = serde_json::from_str(
        &fs::read_to_string(data_dir.join("config.json")).unwrap(),
    )
    .unwrap();

    let hash_params: HashParams = serde_json::from_str(
        &fs::read_to_string(data_dir.join("hash_params.json")).unwrap(),
    )
    .unwrap();

    let thresholds: Thresholds = serde_json::from_str(
        &fs::read_to_string(data_dir.join("thresholds.json")).unwrap(),
    )
    .unwrap();

    let weights: HashMap<String, u32> = serde_json::from_str(
        &fs::read_to_string(data_dir.join("weights.json")).unwrap(),
    )
    .unwrap();

    let severity_map: HashMap<String, String> = serde_json::from_str(
        &fs::read_to_string(data_dir.join("severity_map.json")).unwrap(),
    )
    .unwrap();

    FullConfig {
        config,
        hash_params,
        thresholds,
        weights,
        severity_map,
    }
}
