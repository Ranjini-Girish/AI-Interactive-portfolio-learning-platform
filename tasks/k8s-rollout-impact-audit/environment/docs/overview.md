# Overview

This task is a deterministic SRE report generator. Given two revisions of a Kubernetes manifest set plus a Helm-style chart graph, produce three byte-identical JSON files describing:

1. **Workload drift** — what changed between baseline and current manifests, expressed as added / removed / modified workloads with field-level deltas.
2. **Chart impact** — which charts the changed workloads pull in, after applying the release's `replace` and `exclude` rules and resolving the transitive graph to fixpoint.
3. **Rollout plan** — the order to redeploy the impacted charts so each chart's dependencies have already shipped.

All three reports are computed from `/app/data/` and written under `/app/output/`. The data files must not be modified by the solution.
