# Sorting rules

Sorting is part of the contract — two correct runs must produce byte-identical files.

| Output field                                        | Sort order                                                            |
|-----------------------------------------------------|-----------------------------------------------------------------------|
| `manifest_drift.added_workloads`                    | by `(workload_name, namespace)`                                       |
| `manifest_drift.removed_workloads`                  | by `(workload_name, namespace)`                                       |
| `manifest_drift.modified_workloads`                 | by `(workload_name, namespace)`                                       |
| `manifest_drift.modified_workloads[*].changed_fields` keys | ASCII ascending over the union of old + new spec keys           |
| `chart_impact.resolver_summary.missing`             | ASCII ascending                                                       |
| `chart_impact.resolver_summary.conflicts`           | ASCII ascending                                                       |
| `chart_impact.seed_modules`                         | by `(workload_ref, chart, version)`                                   |
| `chart_impact.impacted_charts`                      | by `name`; each `triggered_by` sorted ASCII ascending                 |
| `chart_impact.cycles[*]` members                    | ASCII ascending; outer list sorted by smallest member                 |
| `chart_impact.build_order[*]` members               | ASCII ascending within each SCC step                                  |
| `rollout_plan.steps`                                | reindexed `1..n` after filtering build_order to impacted charts       |
| `rollout_plan.steps[*].charts`                      | preserves the order from the corresponding `build_order` step         |
| `rollout_plan.steps[*].triggered_by`                | ASCII ascending union over the step's surviving charts                |

Spec key ordering inside drift entries is **not** sorted — it follows the head-then-fixed-order rule from `drift_semantics.md`.
