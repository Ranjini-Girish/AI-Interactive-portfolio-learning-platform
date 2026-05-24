mod dag;
mod hasher;
mod validator;
mod metrics;
mod report;
mod config;

use std::fs;
use std::path::Path;

fn main() {
    let data_dir = Path::new("/app/data");
    let output_dir = Path::new("/app/output");
    fs::create_dir_all(output_dir).expect("Failed to create output directory");

    let cfg = config::load_config(data_dir);
    let mut dag = dag::load_dag(data_dir);
    let computed_hashes = hasher::compute_all_hashes(&dag, &cfg);

    for node in dag.nodes.iter_mut() {
        if node.declared_hash == "CORRECT" {
            if let Some(h) = computed_hashes.get(&node.id) {
                node.declared_hash = h.clone();
            }
        }
    }

    let findings = validator::validate_dag(&dag, &computed_hashes, &cfg);
    let metrics = metrics::compute_metrics(&dag, &cfg);
    let report_data = report::build_report(&dag, &findings, &metrics, &cfg, &computed_hashes);

    let output_path = output_dir.join("validation_report.json");
    let json = serde_json::to_string_pretty(&report_data).unwrap();
    fs::write(&output_path, format!("{}\n", json)).expect("Failed to write report");
}
