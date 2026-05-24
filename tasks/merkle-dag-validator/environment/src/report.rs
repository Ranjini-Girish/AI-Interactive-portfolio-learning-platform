use serde::Serialize;
use std::collections::HashMap;

use crate::config::FullConfig;
use crate::dag::Dag;
use crate::metrics::DagMetrics;
use crate::validator::Finding;

#[derive(Debug, Serialize)]
pub struct Report {
    pub metadata: ReportMetadata,
    pub nodes: Vec<NodeEntry>,
    pub findings: Vec<FindingEntry>,
    pub summary: ReportSummary,
}

#[derive(Debug, Serialize)]
pub struct ReportMetadata {
    pub total_nodes: usize,
    pub total_edges: usize,
    pub root_count: usize,
    pub leaf_count: usize,
    pub max_depth: u32,
}

#[derive(Debug, Serialize)]
pub struct NodeEntry {
    pub id: String,
    pub depth: u32,
    pub repair_cost: u32,
    pub subtree_size: u32,
    pub is_leaf: bool,
    pub is_root: bool,
    pub reachable: bool,
    pub computed_hash: String,
}

#[derive(Debug, Serialize)]
pub struct FindingEntry {
    pub node_id: String,
    pub finding_type: String,
    pub severity: String,
    pub severity_rank: u32,
    pub depth: u32,
    pub declared_hash: String,
    pub computed_hash: String,
    pub repair_cost: u32,
}

#[derive(Debug, Serialize)]
pub struct ReportSummary {
    pub corrupted_count: usize,
    pub integrity_ratio: f64,
    pub total_repair_cost: u32,
    pub max_repair_cost: u32,
    pub avg_depth: f64,
    pub deep_node_count: usize,
}

pub fn build_report(
    dag: &Dag,
    findings: &[Finding],
    metrics: &DagMetrics,
    cfg: &FullConfig,
    computed_hashes: &HashMap<String, String>,
) -> Report {
    let mut nodes: Vec<NodeEntry> = dag
        .nodes
        .iter()
        .map(|n| {
            let m = &metrics.node_metrics[&n.id];
            NodeEntry {
                id: n.id.clone(),
                depth: m.depth,
                repair_cost: m.repair_cost,
                subtree_size: m.subtree_size,
                is_leaf: dag.children_map[&n.id].is_empty(),
                is_root: dag.parents_map[&n.id].is_empty(),
                reachable: m.is_reachable,
                computed_hash: computed_hashes.get(&n.id).cloned().unwrap_or_default(),
            }
        })
        .collect();

    nodes.sort_by(|a, b| a.id.cmp(&b.id));

    let mut finding_entries: Vec<FindingEntry> = findings
        .iter()
        .map(|f| {
            let severity_rank = cfg
                .config
                .severity_levels
                .get(&f.severity)
                .copied()
                .unwrap_or(0);
            let depth = metrics
                .node_metrics
                .get(&f.node_id)
                .map(|m| m.depth)
                .unwrap_or(0);
            let repair_cost = metrics
                .node_metrics
                .get(&f.node_id)
                .map(|m| m.repair_cost)
                .unwrap_or(0);

            FindingEntry {
                node_id: f.node_id.clone(),
                finding_type: f.finding_type.clone(),
                severity: f.severity.clone(),
                severity_rank,
                depth,
                declared_hash: f.declared_hash.clone(),
                computed_hash: f.computed_hash.clone(),
                repair_cost,
            }
        })
        .collect();

    // Sort findings: severity_rank descending, then depth ascending for
    // deterministic output within the same severity tier, then node_id ascending
    finding_entries.sort_by(|a, b| {
        b.severity_rank
            .cmp(&a.severity_rank)
            .then(a.depth.cmp(&b.depth))
            .then(a.node_id.cmp(&b.node_id))
    });

    let total_repair: u32 = finding_entries.iter().map(|f| f.repair_cost).sum();
    let max_repair: u32 = finding_entries
        .iter()
        .map(|f| f.repair_cost)
        .max()
        .unwrap_or(0);

    let depths: Vec<u32> = metrics.node_metrics.values().map(|m| m.depth).collect();
    let avg_depth = if depths.is_empty() {
        0.0
    } else {
        depths.iter().sum::<u32>() as f64 / depths.len() as f64
    };

    let deep_node_count = depths
        .iter()
        .filter(|&&d| d > cfg.thresholds.max_depth)
        .count();

    let metadata = ReportMetadata {
        total_nodes: metrics.total_nodes,
        total_edges: metrics.total_edges,
        root_count: dag.roots.len(),
        leaf_count: dag.leaves.len(),
        max_depth: metrics.max_depth,
    };

    let summary = ReportSummary {
        corrupted_count: findings.len(),
        integrity_ratio: metrics.integrity_ratio,
        total_repair_cost: total_repair,
        max_repair_cost: max_repair,
        avg_depth,
        deep_node_count,
    };

    Report {
        metadata,
        nodes,
        findings: finding_entries,
        summary,
    }
}
