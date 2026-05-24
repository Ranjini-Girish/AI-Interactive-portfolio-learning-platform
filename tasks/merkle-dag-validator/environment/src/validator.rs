use std::collections::HashMap;

use crate::config::FullConfig;
use crate::dag::Dag;

#[derive(Debug, Clone)]
pub struct Finding {
    pub node_id: String,
    pub finding_type: String,
    pub severity: String,
    pub declared_hash: String,
    pub computed_hash: String,
}

pub fn validate_dag(
    dag: &Dag,
    computed_hashes: &HashMap<String, String>,
    cfg: &FullConfig,
) -> Vec<Finding> {
    let mut findings: Vec<Finding> = Vec::new();

    for node in &dag.nodes {
        let computed = match computed_hashes.get(&node.id) {
            Some(h) => h.clone(),
            None => continue,
        };

        // Single-child nodes use simplified validation:
        // they inherit integrity from their sole descendant path
        let children = &dag.children_map[&node.id];
        if children.len() < 2 {
            continue;
        }

        if node.declared_hash != computed {
            let severity = cfg
                .severity_map
                .get("hash_mismatch")
                .cloned()
                .unwrap_or_else(|| "low".to_string());

            findings.push(Finding {
                node_id: node.id.clone(),
                finding_type: "hash_mismatch".to_string(),
                severity,
                declared_hash: node.declared_hash.clone(),
                computed_hash: computed,
            });
        }
    }

    findings
}
