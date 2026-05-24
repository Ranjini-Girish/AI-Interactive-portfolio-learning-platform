use serde::{Deserialize, Serialize};
use std::fs;
use std::path::Path;

#[derive(Deserialize)]
struct PoolConfig {
    pool_size: usize,
    header_size: usize,
    min_alignment: usize,
}

#[derive(Deserialize)]
struct TraceFile {
    trace_id: String,
    #[allow(dead_code)]
    description: String,
    operations: Vec<Operation>,
}

#[derive(Deserialize)]
struct Operation {
    op: String,
    id: String,
    #[serde(default)]
    size: usize,
    #[serde(default)]
    align: usize,
    #[serde(default)]
    new_size: Option<usize>,
}

#[derive(Serialize)]
struct Report {
    pool_config: PoolConfigOut,
    traces: Vec<TraceResult>,
    summary: Summary,
}

#[derive(Serialize)]
struct PoolConfigOut {
    pool_size: usize,
    header_size: usize,
    min_alignment: usize,
}

#[derive(Serialize)]
struct TraceResult {
    trace_id: String,
    total_operations: usize,
    successful_allocs: usize,
    failed_allocs: usize,
    successful_reallocs: usize,
    failed_reallocs: usize,
    deallocs: usize,
    errors: Vec<ErrorRecord>,
    final_state: FinalState,
    high_water_mark: usize,
    peak_live_blocks: usize,
}

#[derive(Serialize)]
struct ErrorRecord {
    operation_index: usize,
    error_type: String,
    id: String,
}

#[derive(Serialize)]
struct FinalState {
    live_allocations: usize,
    free_blocks: usize,
    largest_free_usable: usize,
    total_free_usable: usize,
    total_allocated_bytes: usize,
    pool_utilization: f64,
    external_fragmentation: f64,
    internal_fragmentation: f64,
}

#[derive(Serialize)]
struct Summary {
    total_traces: usize,
    total_operations: usize,
    total_errors: usize,
    total_oom_events: usize,
    traces_with_errors: usize,
    traces_fully_freed: usize,
}

fn round6(x: f64) -> f64 {
    (x * 1_000_000.0).round() / 1_000_000.0
}

fn align_up(size: usize, align: usize) -> usize {
    if align == 0 { return size; }
    ((size + align - 1) / align) * align
}

#[derive(Clone)]
struct Block {
    start: usize,
    total_size: usize,
    is_free: bool,
    alloc_id: Option<String>,
    requested_size: usize,
    aligned_size: usize,
}

struct Allocator {
    blocks: Vec<Block>,
    pool_size: usize,
    header_size: usize,
    min_alignment: usize,
}

impl Allocator {
    fn new(cfg: &PoolConfig) -> Self {
        let initial_block = Block {
            start: 0,
            total_size: cfg.pool_size,
            is_free: true,
            alloc_id: None,
            requested_size: 0,
            aligned_size: 0,
        };
        Allocator {
            blocks: vec![initial_block],
            pool_size: cfg.pool_size,
            header_size: cfg.header_size,
            min_alignment: cfg.min_alignment,
        }
    }

    fn alloc(&mut self, id: &str, size: usize, align: usize) -> bool {
        let aligned_size = if size == 0 { 0 } else { align_up(size, self.min_alignment) };
        let required = self.header_size + aligned_size;

        for i in 0..self.blocks.len() {
            if !self.blocks[i].is_free { continue; }
            if self.blocks[i].total_size < required { continue; }

            let remainder = self.blocks[i].total_size - required;
            let min_split = self.header_size + self.min_alignment;

            if remainder > min_split {
                let new_free = Block {
                    start: self.blocks[i].start + required,
                    total_size: remainder,
                    is_free: true,
                    alloc_id: None,
                    requested_size: 0,
                    aligned_size: 0,
                };
                self.blocks[i].total_size = required;
                self.blocks[i].is_free = false;
                self.blocks[i].alloc_id = Some(id.to_string());
                self.blocks[i].requested_size = size;
                self.blocks[i].aligned_size = aligned_size;
                self.blocks.insert(i + 1, new_free);
            } else {
                self.blocks[i].is_free = false;
                self.blocks[i].alloc_id = Some(id.to_string());
                self.blocks[i].requested_size = size;
                self.blocks[i].aligned_size = aligned_size;
            }
            return true;
        }
        false
    }

    fn find_block(&self, id: &str) -> Option<usize> {
        self.blocks.iter().position(|b| {
            !b.is_free && b.alloc_id.as_deref() == Some(id)
        })
    }

    fn dealloc(&mut self, id: &str) -> bool {
        if let Some(idx) = self.find_block(id) {
            self.blocks[idx].is_free = true;
            self.blocks[idx].alloc_id = None;
            self.blocks[idx].requested_size = 0;
            self.blocks[idx].aligned_size = 0;
            self.coalesce(idx);
            true
        } else {
            false
        }
    }

    fn coalesce(&mut self, idx: usize) {
        if idx > 0 && self.blocks[idx - 1].is_free {
            let cur_size = self.blocks[idx].total_size;
            self.blocks[idx - 1].total_size += cur_size;
            self.blocks.remove(idx);
        }
        if idx + 1 < self.blocks.len() && self.blocks[idx + 1].is_free {
            let next_size = self.blocks[idx + 1].total_size;
            self.blocks[idx].total_size += next_size;
            self.blocks.remove(idx + 1);
        }
    }

    fn realloc(&mut self, id: &str, new_size: usize, align: usize) -> i32 {
        let idx = match self.find_block(id) {
            Some(i) => i,
            None => return -1,
        };

        let new_aligned = if new_size == 0 { 0 } else { align_up(new_size, align) };
        let new_required = self.header_size + new_aligned;
        let old_requested = self.blocks[idx].requested_size;
        let cur_block_size = self.blocks[idx].total_size;

        if new_size == self.blocks[idx].requested_size {
            return 1;
        }

        if new_required <= cur_block_size {
            let remainder = cur_block_size - new_required;
            let min_split = self.header_size + self.min_alignment;
            if remainder >= min_split {
                let new_free = Block {
                    start: self.blocks[idx].start + new_required,
                    total_size: remainder,
                    is_free: true,
                    alloc_id: None,
                    requested_size: 0,
                    aligned_size: 0,
                };
                self.blocks[idx].total_size = new_required;
                self.blocks[idx].requested_size = new_size;
                self.blocks[idx].aligned_size = new_aligned;
                self.blocks.insert(idx + 1, new_free);
            } else {
                self.blocks[idx].requested_size = new_size;
                self.blocks[idx].aligned_size = new_aligned;
            }
            return 1;
        }

        if idx + 1 < self.blocks.len() && self.blocks[idx + 1].is_free {
            let combined = cur_block_size + self.blocks[idx + 1].total_size;
            if combined >= new_required {
                let next_size = self.blocks[idx + 1].total_size;
                self.blocks.remove(idx + 1);
                self.blocks[idx].total_size = cur_block_size + next_size;

                let remainder = self.blocks[idx].total_size - new_required;
                let min_split = self.header_size + self.min_alignment;
                if remainder >= min_split {
                    let new_free = Block {
                        start: self.blocks[idx].start + new_required,
                        total_size: remainder,
                        is_free: true,
                        alloc_id: None,
                        requested_size: 0,
                        aligned_size: 0,
                    };
                    self.blocks[idx].total_size = new_required;
                    self.blocks.insert(idx + 1, new_free);
                }
                self.blocks[idx].requested_size = new_size;
                self.blocks[idx].aligned_size = new_aligned;
                return 1;
            }
        }

        let old_id = id.to_string();
        if self.alloc(&format!("__realloc_tmp_{}", id), new_size, align) {
            let new_idx = self.find_block(&format!("__realloc_tmp_{}", id)).unwrap();
            self.blocks[new_idx].alloc_id = Some(old_id.clone());
            self.blocks[new_idx].requested_size = new_size;

            let old_idx = self.blocks.iter().position(|b| {
                !b.is_free && b.alloc_id.as_deref() == Some(&old_id)
                    && b.requested_size == old_requested
            });
            if let Some(oi) = old_idx {
                self.blocks[oi].is_free = true;
                self.blocks[oi].alloc_id = None;
                self.blocks[oi].requested_size = 0;
                self.blocks[oi].aligned_size = 0;
                self.coalesce(oi);
            }
            1
        } else {
            0
        }
    }

    fn live_count(&self) -> usize {
        self.blocks.iter().filter(|b| !b.is_free).count()
    }

    fn live_requested_sum(&self) -> usize {
        self.blocks.iter()
            .filter(|b| !b.is_free)
            .map(|b| b.aligned_size)
            .sum()
    }

    fn compute_final_state(&self) -> FinalState {
        let live = self.blocks.iter().filter(|b| !b.is_free).count();
        let free_blocks: Vec<&Block> = self.blocks.iter().filter(|b| b.is_free).collect();
        let free_count = free_blocks.len();

        let free_usable: Vec<usize> = free_blocks.iter()
            .map(|b| b.total_size)
            .collect();
        let total_free_usable: usize = free_usable.iter().sum();
        let largest_free_usable = free_usable.iter().copied().max().unwrap_or(0);

        let total_alloc_bytes: usize = self.blocks.iter()
            .filter(|b| !b.is_free)
            .map(|b| b.total_size)
            .sum();

        let pool_util = if self.pool_size > 0 {
            total_alloc_bytes as f64 / self.pool_size as f64
        } else { 0.0 };

        let ext_frag = if total_free_usable > 0 {
            1.0 - (largest_free_usable as f64 / total_free_usable as f64)
        } else { 0.0 };

        let mut total_padding: usize = 0;
        for b in &self.blocks {
            if b.is_free { continue; }
            let payload_space = b.total_size - self.header_size;
            let pad = payload_space - b.aligned_size;
            total_padding += pad;
        }
        let int_frag = if total_alloc_bytes > 0 {
            total_padding as f64 / total_alloc_bytes as f64
        } else { 0.0 };

        FinalState {
            live_allocations: live,
            free_blocks: free_count,
            largest_free_usable,
            total_free_usable,
            total_allocated_bytes: total_alloc_bytes,
            pool_utilization: round6(pool_util),
            external_fragmentation: round6(ext_frag),
            internal_fragmentation: round6(int_frag),
        }
    }
}

fn process_trace(cfg: &PoolConfig, trace: &TraceFile) -> TraceResult {
    let mut alloc = Allocator::new(cfg);
    let mut errors: Vec<ErrorRecord> = Vec::new();
    let mut successful_allocs = 0usize;
    let mut failed_allocs = 0usize;
    let mut successful_reallocs = 0usize;
    let mut failed_reallocs = 0usize;
    let mut deallocs = 0usize;
    let mut high_water_mark = 0usize;
    let mut peak_live = 0usize;
    let mut freed_ids: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut allocated_ids: std::collections::HashSet<String> = std::collections::HashSet::new();

    for (i, op) in trace.operations.iter().enumerate() {
        match op.op.as_str() {
            "alloc" => {
                if alloc.alloc(&op.id, op.size, op.align) {
                    successful_allocs += 1;
                    allocated_ids.insert(op.id.clone());
                    freed_ids.remove(&op.id);
                } else {
                    failed_allocs += 1;
                    errors.push(ErrorRecord {
                        operation_index: i,
                        error_type: "oom".to_string(),
                        id: op.id.clone(),
                    });
                }
            }
            "dealloc" => {
                if freed_ids.contains(&op.id) || !allocated_ids.contains(&op.id) {
                    errors.push(ErrorRecord {
                        operation_index: i,
                        error_type: "double_free".to_string(),
                        id: op.id.clone(),
                    });
                } else if alloc.dealloc(&op.id) {
                    deallocs += 1;
                    freed_ids.insert(op.id.clone());
                } else {
                    errors.push(ErrorRecord {
                        operation_index: i,
                        error_type: "double_free".to_string(),
                        id: op.id.clone(),
                    });
                }
            }
            "realloc" => {
                let ns = op.new_size.unwrap_or(op.size);
                if freed_ids.contains(&op.id) || !allocated_ids.contains(&op.id) {
                    errors.push(ErrorRecord {
                        operation_index: i,
                        error_type: "use_after_free".to_string(),
                        id: op.id.clone(),
                    });
                    failed_reallocs += 1;
                } else {
                    let result = alloc.realloc(&op.id, ns, op.align);
                    if result == 1 {
                        successful_reallocs += 1;
                    } else if result == 0 {
                        failed_reallocs += 1;
                        errors.push(ErrorRecord {
                            operation_index: i,
                            error_type: "oom".to_string(),
                            id: op.id.clone(),
                        });
                    } else {
                        failed_reallocs += 1;
                        errors.push(ErrorRecord {
                            operation_index: i,
                            error_type: "use_after_free".to_string(),
                            id: op.id.clone(),
                        });
                    }
                }
            }
            _ => {}
        }
        let cur_req = alloc.live_requested_sum();
        if cur_req > high_water_mark { high_water_mark = cur_req; }
        let cur_live = alloc.live_count();
        if cur_live > peak_live { peak_live = cur_live; }
    }

    let final_state = alloc.compute_final_state();
    TraceResult {
        trace_id: trace.trace_id.clone(),
        total_operations: trace.operations.len(),
        successful_allocs,
        failed_allocs,
        successful_reallocs,
        failed_reallocs,
        deallocs,
        errors,
        final_state,
        high_water_mark,
        peak_live_blocks: peak_live,
    }
}

fn main() {
    let cfg_text = fs::read_to_string("/app/data/pool_config.json")
        .expect("Cannot read pool_config.json");
    let cfg: PoolConfig = serde_json::from_str(&cfg_text)
        .expect("Cannot parse pool_config.json");

    let traces_dir = Path::new("/app/data/traces");
    let mut trace_files: Vec<String> = fs::read_dir(traces_dir)
        .expect("Cannot read traces dir")
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_string_lossy().to_string())
        .filter(|p| p.ends_with(".json"))
        .collect();
    trace_files.sort();

    let mut results: Vec<TraceResult> = Vec::new();
    for tf in &trace_files {
        let text = fs::read_to_string(tf).expect(&format!("Cannot read {}", tf));
        let trace: TraceFile = serde_json::from_str(&text)
            .expect(&format!("Cannot parse {}", tf));
        results.push(process_trace(&cfg, &trace));
    }
    results.sort_by(|a, b| a.trace_id.cmp(&b.trace_id));

    let total_ops: usize = results.iter().map(|r| r.total_operations).sum();
    let total_errs: usize = results.iter().map(|r| r.errors.len()).sum();
    let total_oom: usize = results.iter()
        .map(|r| r.errors.iter().filter(|e| e.error_type == "oom").count())
        .sum();
    let traces_w_err = results.iter().filter(|r| !r.errors.is_empty()).count();
    let traces_freed = results.iter()
        .filter(|r| r.final_state.live_allocations == 0)
        .count();

    let report = Report {
        pool_config: PoolConfigOut {
            pool_size: cfg.pool_size,
            header_size: cfg.header_size,
            min_alignment: cfg.min_alignment,
        },
        traces: results,
        summary: Summary {
            total_traces: trace_files.len(),
            total_operations: total_ops,
            total_errors: total_errs,
            total_oom_events: total_oom,
            traces_with_errors: traces_w_err,
            traces_fully_freed: traces_freed,
        },
    };

    let json = serde_json::to_string_pretty(&report).unwrap();
    fs::write("/app/output/allocator_report.json", format!("{}\n", json))
        .expect("Cannot write report");

    eprintln!("Report written to /app/output/allocator_report.json");
}
