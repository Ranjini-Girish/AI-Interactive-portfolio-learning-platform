use std::collections::HashMap;

/// Simple memoization cache for computed values.
#[allow(dead_code)]
pub struct ComputeCache<K, V> {
    store: HashMap<K, V>,
    hits: usize,
    misses: usize,
}

#[allow(dead_code)]
impl<K: std::hash::Hash + Eq, V: Clone> ComputeCache<K, V> {
    pub fn new() -> Self {
        ComputeCache {
            store: HashMap::new(),
            hits: 0,
            misses: 0,
        }
    }

    pub fn get(&mut self, key: &K) -> Option<V> {
        match self.store.get(key) {
            Some(v) => {
                self.hits += 1;
                Some(v.clone())
            }
            None => {
                self.misses += 1;
                None
            }
        }
    }

    pub fn insert(&mut self, key: K, value: V) {
        self.store.insert(key, value);
    }

    pub fn hit_rate(&self) -> f64 {
        let total = self.hits + self.misses;
        if total == 0 { 0.0 } else { self.hits as f64 / total as f64 }
    }
}
