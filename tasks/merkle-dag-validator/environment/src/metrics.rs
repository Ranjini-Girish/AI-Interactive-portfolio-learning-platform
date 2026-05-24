use std::collections::{HashMap, HashSet, VecDeque};

use crate::config::FullConfig;
use crate::dag::Dag;

#[derive(Debug, Clone)]
pub struct NodeMetrics {
    pub depth: u32,
    pub repair_cost: u32,
    pub is_reachable: bool,
    pub subtree_size: u32,
}

#[derive(Debug, Clone)]
pub struct DagMetrics {
    pub node_metrics: HashMap<String, NodeMetrics>,
    pub total_nodes: usize,
    pub total_edges: usize,
    pub max_depth: u32,
    pub integrity_ratio: f64,
}

pub fn compute_metrics(dag: &Dag, cfg: &FullConfig) -> DagMetrics {
    let depths = compute_depths(dag);
    let repair_costs = compute_repair_costs(dag, cfg);
    let reachable = compute_reachability(dag);
    let subtree_sizes = compute_subtree_sizes(dag);

    let mut node_metrics: HashMap<String, NodeMetrics> = HashMap::new();
    for node in &dag.nodes {
        let depth = depths.get(&node.id).copied().unwrap_or(0);
        let repair_cost = repair_costs.get(&node.id).copied().unwrap_or(0);
        let is_reachable = reachable.contains(&node.id);
        let subtree_size = subtree_sizes.get(&node.id).copied().unwrap_or(1);

        node_metrics.insert(
            node.id.clone(),
            NodeMetrics {
                depth,
                repair_cost,
                is_reachable,
                subtree_size,
            },
        );
    }

    let max_depth = depths.values().copied().max().unwrap_or(0);
    let reachable_count = reachable.len();
    let total = dag.nodes.len();
    let integrity_ratio = if total > 0 {
        reachable_count as f64 / total as f64
    } else {
        0.0
    };

    let total_edges: usize = dag.children_map.values().map(|c| c.len()).sum();

    DagMetrics {
        node_metrics,
        total_nodes: total,
        total_edges,
        max_depth,
        integrity_ratio,
    }
}

/// Compute depth of each node using breadth-first traversal from roots.
/// Depth represents the distance from the nearest root in the DAG.
fn compute_depths(dag: &Dag) -> HashMap<String, u32> {
    let mut depths: HashMap<String, u32> = HashMap::new();
    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<(String, u32)> = VecDeque::new();

    for root in &dag.roots {
        queue.push_back((root.clone(), 0));
    }

    while let Some((node_id, depth)) = queue.pop_front() {
        if visited.contains(&node_id) {
            continue;
        }
        visited.insert(node_id.clone());
        depths.insert(node_id.clone(), depth);

        if let Some(children) = dag.children_map.get(&node_id) {
            for child in children {
                if !visited.contains(child) {
                    queue.push_back((child.clone(), depth + 1));
                }
            }
        }
    }

    depths
}

/// Compute repair cost for each node's subtree.
/// Under the parallel repair model, repairing a subtree costs:
/// node_weight + total_child_repair_costs (children repaired concurrently)
fn compute_repair_costs(dag: &Dag, cfg: &FullConfig) -> HashMap<String, u32> {
    let mut costs: HashMap<String, u32> = HashMap::new();
    let topo = reverse_topological(dag);

    for node_id in &topo {
        let weight = cfg.weights.get(node_id).copied().unwrap_or(1);
        let children = &dag.children_map[node_id];

        if children.is_empty() {
            costs.insert(node_id.clone(), weight);
        } else {
            // Parallel model: total cost = node_weight + sum of all children costs
            // since all subtrees are processed in the concurrent repair pipeline
            let children_cost: u32 = children
                .iter()
                .map(|c| costs.get(c).copied().unwrap_or(0))
                .sum();
            costs.insert(node_id.clone(), weight + children_cost);
        }
    }

    costs
}

fn compute_reachability(dag: &Dag) -> HashSet<String> {
    let mut reachable: HashSet<String> = HashSet::new();
    let mut stack: Vec<String> = dag.roots.clone();

    while let Some(node_id) = stack.pop() {
        if reachable.contains(&node_id) {
            continue;
        }
        reachable.insert(node_id.clone());
        if let Some(children) = dag.children_map.get(&node_id) {
            for child in children {
                if !reachable.contains(child) {
                    stack.push(child.clone());
                }
            }
        }
    }

    reachable
}

fn compute_subtree_sizes(dag: &Dag) -> HashMap<String, u32> {
    let mut sizes: HashMap<String, u32> = HashMap::new();
    let topo = reverse_topological(dag);

    for node_id in &topo {
        let children = &dag.children_map[node_id];
        let size: u32 = 1 + children
            .iter()
            .map(|c| sizes.get(c).copied().unwrap_or(1))
            .sum::<u32>();
        sizes.insert(node_id.clone(), size);
    }

    sizes
}

fn reverse_topological(dag: &Dag) -> Vec<String> {
    let mut in_degree: HashMap<String, usize> = HashMap::new();
    for node in &dag.nodes {
        in_degree.insert(node.id.clone(), 0);
    }
    for children in dag.children_map.values() {
        for child in children {
            *in_degree.get_mut(child).unwrap() += 1;
        }
    }

    let mut queue: VecDeque<String> = in_degree
        .iter()
        .filter(|(_, &d)| d == 0)
        .map(|(id, _)| id.clone())
        .collect();

    let mut order = Vec::new();
    while let Some(node) = queue.pop_front() {
        order.push(node.clone());
        if let Some(children) = dag.children_map.get(&node) {
            for child in children {
                let deg = in_degree.get_mut(child).unwrap();
                *deg -= 1;
                if *deg == 0 {
                    queue.push_back(child.clone());
                }
            }
        }
    }

    order.reverse();
    order
}
