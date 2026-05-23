# Glossary

| Term              | Meaning                                                                                              |
|-------------------|------------------------------------------------------------------------------------------------------|
| Workload          | A single Kubernetes manifest (Deployment, StatefulSet, DaemonSet, CronJob, Job).                     |
| Namespace         | Logical grouping of workloads. Empty / null / whitespace-only namespaces collapse to `"default"`.    |
| Workload identity | The pair `(workload_name, namespace)`. Used as the primary key for diff matching.                    |
| Spec              | The deterministic projection of a manifest used for diffing. See `drift_semantics.md`.               |
| Workload ref      | The string `"<namespace>::<workload_name>"`. The cross-reference key in `workload_dependency_map.json`. |
| Chart             | A registry record `{name, version, require?}`. Maps roughly to a Helm chart with declared deps.      |
| Release           | The top-level manifest declaring `require`, `replace`, `exclude`, and the release pseudo-chart name. |
| Build set         | Names whose selected version is in the registry and whose name is not `release.name`.                |
| Cycle group       | An SCC of size ≥ 2, or a singleton SCC with a self-edge.                                             |
| Rollout step      | A single SCC's filtered chart list in the rollout plan, after dropping non-impacted charts.          |
