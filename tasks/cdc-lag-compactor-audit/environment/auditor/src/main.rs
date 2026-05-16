use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let data = env::var("CDC_DATA_DIR").unwrap_or_else(|_| "/app/cdc".to_string());
    let out = env::var("CDC_AUDIT_DIR").unwrap_or_else(|_| "/app/audit".to_string());
    let _ = fs::create_dir_all(PathBuf::from(out));
    eprintln!(
        "cdc-audit scaffold: implement /app/cdc/SPEC.md and write the five reports from {}",
        data
    );
    std::process::exit(2);
}
