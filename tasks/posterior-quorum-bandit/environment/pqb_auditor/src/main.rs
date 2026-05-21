//! Agent scaffold: replace this program with the full audit implementation.
use std::env;
use std::process;

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() != 3 {
        process::exit(2);
    }
    eprintln!("pqb-audit scaffold: implement the audit described in /app/pqb_lab/SPEC.md");
    process::exit(3);
}
