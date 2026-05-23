Label Window Drift Audit Contract

All reads come from /app/labelops unless LWD_DATA_DIR is a non-empty override. All writes go to /app/audit unless LWD_AUDIT_DIR is a non-empty override. Inputs are UTF-8 JSON except this file. Files under ancillary/ are distractors.

Input files:
- pool_state.json: current_day integer.
- policy.json: supported_event_kinds, credit_decay_bps_per_hop, freeze_propagation_hops, and tier_rules keyed by tier. Each tier rule has drift_warn_bps, drift_block_bps, conflict_block_bps, min_clean_windows, and min_score_bps.
- datasets/*.json: dataset_id, tier, owner, baseline_positive_bps, and parents sorted or unsorted.
- windows/*.json: window_id, dataset_id, day_start, day_end, labels_total, positives, conflicts, reviewer_rejects, depends_on, and source_model_id.
- models/*.json: model_id, dataset_id, candidate_windows, score_bps, and declared_stage.
- incidents.json: events with event_id, kind, target_type, target_id, day, accepted, and optional amount_bps.

Incident events are accepted only when accepted is true, day <= current_day, kind is supported, and the target exists for its target_type. Other events are ignored with reason unsupported_kind, future_event, rejected_event, or missing_target in that order. For duplicate accepted events sharing kind, target_type, and target_id, keep the greatest day and then ASCII-smallest event_id; dropped duplicates appear in incident_trace as ignored with reason superseded_event.

Dataset lineage follows parent links transitively. A dataset with a cycle in its ancestry has lineage_status cyclic and parent_depth -1. A dataset with any absent parent has lineage_status missing_parent. Accepted label_source_compromise events seed compromised datasets; compromise propagates from parent to descendants after cycle and missing-parent detection. Non-cyclic descendants of compromised parents have lineage_status compromised. Clean datasets report the maximum acyclic parent depth, where roots have depth 0.

Window dependency links use depends_on. Cycles among windows produce status invalid_dependency for every participant unless dataset lineage already has higher precedence. A relabel_credit event on a window reduces that window's drift_bps by amount_bps; each dependency hop to a descendant reduces the credit by credit_decay_bps_per_hop until the remaining credit is not positive. Multiple credits use the largest effective credit, with event_id ASCII order only for the reported credit_event_id tie. A window_freeze event freezes the target window and descendants up to freeze_propagation_hops.

For each window, observed_positive_bps = floor(positives * 10000 / labels_total), raw_drift_bps = abs(observed_positive_bps - dataset.baseline_positive_bps), adjusted_drift_bps = max(0, raw_drift_bps - effective_credit_bps), and conflict_bps = floor((conflicts + reviewer_rejects) * 10000 / labels_total). Window status precedence is invalid_lineage, compromised, invalid_dependency, frozen, frozen_dependency, drift_blocked, drift_warning, clean. drift_blocked applies when adjusted_drift_bps >= tier drift_block_bps or conflict_bps >= tier conflict_block_bps; drift_warning applies when adjusted_drift_bps >= tier drift_warn_bps.

Model readiness uses candidate windows with status clean or drift_warning as eligible. Status precedence is quarantine_lineage, quarantine_compromise, hold, promote, insufficient_windows, below_score. quarantine_lineage covers cyclic or missing dataset lineage. quarantine_compromise covers compromised dataset lineage. Accepted model_hold events force hold unless a quarantine status applies. promote requires eligible window count >= the dataset tier min_clean_windows and score_bps >= min_score_bps; otherwise insufficient_windows wins before below_score.

Write exactly five JSON files: window_drift.json, dataset_lineage.json, model_readiness.json, incident_trace.json, and summary.json. Use two-space indentation, sorted object keys, and a trailing newline. Rows are sorted by their primary id. Count maps include only statuses that occur.
