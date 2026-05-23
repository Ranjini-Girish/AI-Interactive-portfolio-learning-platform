# Overview

The objective of this task is to produce a deterministic playbook drift and dependency impact audit from input configurations and write structured JSON reports.

## Input Files
All inputs reside under `/app/data/` and must not be modified:
- `/app/data/baseline-playbook.yml`: The original playbook configuration.
- `/app/data/current-playbook.yml`: The updated playbook configuration.
- `/app/data/root.json`: Root package resolution constraints.
- `/app/data/task_dependency_map.json`: Mappings from changed tasks to module requirements.
- `/app/data/modules/*.json`: Concatenated module registry files.

## Required Output Files
The solver must write UTF-8 encoded, 2-space indented canonical JSON reports to `/app/output/`:
1. `/app/output/playbook_drift.json`: Summarizes added, removed, and modified tasks between playbooks.
2. `/app/output/dependency_impact.json`: Resolves full dependency graph, cycles, build order, and impacted modules.
3. `/app/output/remediation_plan.json`: Projects build order steps onto impacted modules.
