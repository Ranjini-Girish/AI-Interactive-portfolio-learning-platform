use serde::Deserialize;
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

#[derive(Debug, Clone, Deserialize)]
pub struct NodeDef {
    pub id: String,
    pub content: String,
    pub declared_hash: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct EdgeDef {
    pub parent: String,
    pub child: String,
}

#[derive(Debug, Clone)]
pub struct Dag {
    pub nodes: Vec<NodeDef>,
    pub children_map: HashMap<String, Vec<String>>,
    pub parents_map: HashMap<String, Vec<String>>,
    pub roots: Vec<String>,
    pub leaves: Vec<String>,
}

pub fn load_dag(data_dir: &Path) -> Dag {
    let nodes: Vec<NodeDef> = serde_json::from_str(
        &fs::read_to_string(data_dir.join("nodes.json")).unwrap(),
    )
    .unwrap();

    let edges: Vec<EdgeDef> = serde_json::from_str(
        &fs::read_to_string(data_dir.join("edges.json")).unwrap(),
    )
    .unwrap();

    let mut children_map: HashMap<String, Vec<String>> = HashMap::new();
    let mut parents_map: HashMap<String, Vec<String>> = HashMap::new();
    let all_ids: HashSet<String> = nodes.iter().map(|n| n.id.clone()).collect();

    for id in &all_ids {
        children_map.insert(id.clone(), Vec::new());
        parents_map.insert(id.clone(), Vec::new());
    }

    for edge in &edges {
        children_map
            .get_mut(&edge.parent)
            .unwrap()
            .push(edge.child.clone());
        parents_map
            .get_mut(&edge.child)
            .unwrap()
            .push(edge.parent.clone());
    }

    for children in children_map.values_mut() {
        children.sort();
    }

    let roots: Vec<String> = all_ids
        .iter()
        .filter(|id| parents_map[*id].is_empty())
        .cloned()
        .collect::<Vec<_>>()
        .into_iter()
        .collect();

    let leaves: Vec<String> = all_ids
        .iter()
        .filter(|id| children_map[*id].is_empty())
        .cloned()
        .collect::<Vec<_>>()
        .into_iter()
        .collect();

    let mut roots_sorted = roots;
    roots_sorted.sort();
    let mut leaves_sorted = leaves;
    leaves_sorted.sort();

    Dag {
        nodes,
        children_map,
        parents_map,
        roots: roots_sorted,
        leaves: leaves_sorted,
    }
}
