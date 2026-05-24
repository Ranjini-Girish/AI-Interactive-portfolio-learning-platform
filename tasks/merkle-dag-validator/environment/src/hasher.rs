use sha2::{Sha256, Digest};
use std::collections::HashMap;

use crate::config::FullConfig;
use crate::dag::Dag;

pub fn compute_all_hashes(dag: &Dag, cfg: &FullConfig) -> HashMap<String, String> {
    let mut computed: HashMap<String, String> = HashMap::new();
    let topo_order = topological_sort(dag);

    for node_id in topo_order.iter().rev() {
        let node = dag.nodes.iter().find(|n| n.id == *node_id).unwrap();
        let children = &dag.children_map[node_id];
        let hash = compute_node_hash(node_id, &node.content, children, &computed, cfg);
        computed.insert(node_id.clone(), hash);
    }

    computed
}

fn compute_node_hash(
    node_id: &str,
    content: &str,
    children: &[String],
    computed: &HashMap<String, String>,
    cfg: &FullConfig,
) -> String {
    let sep = &cfg.hash_params.separator;
    let join_str = &cfg.hash_params.children_join;
    let salt = &cfg.hash_params.salt_prefix;

    let hash_input = if children.is_empty() {
        format!(
            "{salt}{sep}{node_id}{sep}{content}{sep}{leaf}",
            salt = salt,
            sep = sep,
            node_id = node_id,
            content = content,
            leaf = cfg.hash_params.leaf_marker,
        )
    } else {
        // Collect children's hashes and sort them for deterministic ordering.
        // Per spec: sort by the child's computed hash value (lexicographic).
        let mut child_entries: Vec<(&String, &String)> = children
            .iter()
            .filter_map(|cid| computed.get(cid).map(|h| (cid, h)))
            .collect();

        // Sort by node identifier for stable deterministic output across platforms
        child_entries.sort_by(|a, b| a.0.cmp(b.0));

        let children_hashes: String = child_entries
            .iter()
            .map(|(_, h)| h.as_str())
            .collect::<Vec<_>>()
            .join(join_str);

        format!(
            "{salt}{sep}{node_id}{sep}{content}{sep}{children_hashes}",
            salt = salt,
            sep = sep,
            node_id = node_id,
            content = content,
            children_hashes = children_hashes,
        )
    };

    let mut hasher = Sha256::new();
    hasher.update(hash_input.as_bytes());
    let result = hasher.finalize();
    let truncated = &result[..cfg.config.hash_truncate_bytes];
    hex::encode(truncated)
}

fn topological_sort(dag: &Dag) -> Vec<String> {
    let mut in_degree: HashMap<String, usize> = HashMap::new();
    for node in &dag.nodes {
        in_degree.insert(node.id.clone(), 0);
    }
    for (_, children) in &dag.children_map {
        for child in children {
            *in_degree.get_mut(child).unwrap() += 1;
        }
    }

    let mut queue: Vec<String> = in_degree
        .iter()
        .filter(|(_, &d)| d == 0)
        .map(|(id, _)| id.clone())
        .collect();
    queue.sort();

    let mut order = Vec::new();
    while let Some(node) = queue.pop() {
        order.push(node.clone());
        if let Some(children) = dag.children_map.get(&node) {
            for child in children {
                let deg = in_degree.get_mut(child).unwrap();
                *deg -= 1;
                if *deg == 0 {
                    queue.push(child.clone());
                    queue.sort();
                }
            }
        }
    }

    order
}
