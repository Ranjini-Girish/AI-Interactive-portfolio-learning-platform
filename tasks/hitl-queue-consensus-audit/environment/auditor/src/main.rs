use std::env;
use std::fs;
use std::path::PathBuf;

fn main() {
    let out_dir = env::var("HCQ_AUDIT_DIR").unwrap_or_else(|_| "/app/audit".to_string());
    let out_path = PathBuf::from(out_dir);
    fs::create_dir_all(&out_path).expect("failed to create output directory");

    // Placeholder. The reference build replaces this file at verification time.
    fs::write(out_path.join("consensus_report.json"), "{}\n").expect("write failed");
    fs::write(out_path.join("queue_order.json"), "{}\n").expect("write failed");
    fs::write(out_path.join("annotator_reliability.json"), "{}\n").expect("write failed");
    fs::write(out_path.join("compliance_flags.json"), "{}\n").expect("write failed");
    fs::write(out_path.join("summary.json"), "{}\n").expect("write failed");
}
