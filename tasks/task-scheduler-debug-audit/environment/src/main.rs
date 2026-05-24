use std::fs;
use std::process;

mod task;
mod graph;
mod scheduler;
mod critical;
mod stats;
mod report;
mod validator;
mod config;
mod metrics;
mod cache;
mod format;
mod errors;
mod traversal;
mod priority;

fn main() {
    let input = match fs::read_to_string("/app/data/tasks.json") {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Failed to read input: {}", e);
            process::exit(1);
        }
    };

    let task_file: task::TaskFile = match serde_json::from_str(&input) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("Failed to parse JSON: {}", e);
            process::exit(1);
        }
    };

    let tasks = task_file.tasks;

    if let Err(e) = validator::validate_tasks(&tasks) {
        eprintln!("Validation failed: {}", e);
        process::exit(1);
    }

    let _config = config::SchedulerConfig::default();
    let mut perf = metrics::PerfMetrics::new();

    perf.start("topo_sort");
    let topo_order = match graph::topological_sort(&tasks) {
        Ok(order) => order,
        Err(e) => {
            eprintln!("Topological sort failed: {}", e);
            process::exit(1);
        }
    };
    perf.stop("topo_sort");

    perf.start("schedule");
    let scheduled = scheduler::schedule(&tasks, &topo_order);
    perf.stop("schedule");

    perf.start("critical_path");
    let cp = critical::find_critical_path(&tasks, &scheduled);
    perf.stop("critical_path");

    perf.start("stats");
    let gs = stats::compute_group_stats(&tasks);
    let summary = stats::compute_summary(&tasks, &scheduled);
    perf.stop("stats");

    let output = report::build_report(&scheduled, &topo_order, &cp, &gs, &summary);

    fs::create_dir_all("/app/output").unwrap();
    fs::write("/app/output/report.json", output).unwrap();

    eprintln!("{}", perf.summary());
    println!("Report written to /app/output/report.json");
}
