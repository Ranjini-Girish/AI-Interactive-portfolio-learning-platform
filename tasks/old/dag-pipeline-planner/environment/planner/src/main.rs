use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let data = env::var("DAG_DATA_DIR").unwrap_or_else(|_| "/app/pipelines".to_string());
    let out = env::var("DAG_PLAN_DIR").unwrap_or_else(|_| "/app/plan".to_string());
    let _ = fs::create_dir_all(PathBuf::from(&out));
    eprintln!(
        "planner scaffold: implement /app/pipelines/SPEC.md and write the six plan JSON files from {}",
        data
    );
    std::process::exit(2);
}
