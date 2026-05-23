# Go Module Bump Arbiter — Output Contract

Normative contract for deriving five JSON outputs from the read-only modgraph tree. Read inputs from the directory named by `GMBA_MODGRAPH_DIR`, or `/app/modgraph/` when unset. Write the five JSON artifacts into the directory named by `GMBA_DECISIONS_DIR`, or `/app/decisions/` when unset. When a variable is set, its path is authoritative; writing only to the default locations while ignoring set variables is non-conforming. Read this entire file without truncation.

## JSON encoding (binding)

UTF-8 text equivalent to Python `json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"`: two-space indent for all nested structures, sorted object keys at every depth, exactly one trailing newline, no HTML escaping.

## Input layout (read-only)

- `pool_state.json` — `{"current_day": int}`.
- `workspace_manifest.json` — workspace_id, ASCII-sorted modules[], replace_directive_quorum, severity_block_threshold (low|medium|high|critical), vulncheck_reachability_required.
- `governance/policy.json` — severity_rank map low..critical to 1..4, supported_incident_kinds (force_pin, replace_workspace_wide, retract_emergency, module_graph_cycle), retract_grace_days. Threshold gate: block when rank(advisory.severity) >= rank(threshold).
- `modules/<name>.json` — module_path (must equal file stem), go_version_min, requires[{dep_path, min_version, reachability_symbols}], replaces[{from_path, to_path, to_version}], excludes[{dep_path, version}], tools[dep_path]. Reachability symbols are dotted identifiers (e.g. net/http.Server.ServeTLS).
- `registry/<dep_path>.json` — dep_path, versions[{version, min_go_version, retracted, retract_reason, affected_symbols, pseudo, vuln_advisories}]. Stem replaces `/` with `__`. Disk order of versions is irrelevant; comparator below is canonical.
- `advisories/<id>.json` — advisory_id, dep_path, severity, affected_versions (literal list), fixed_in, affected_symbols.
- `incident_log.json` — events with event_id, day, kind, accepted, plus kind fields under *Incident filtering*.

## Version comparator (canonical)

Versions are vX.Y.Z or vX.Y.Z-<pre> with (X,Y,Z) integer-compared; pre-release ranks below the same release without pre; pre strings ASCII-compared. Pseudo v0.0.0- date-hash compares by full string (treat pre as 0-<date>-<hash>). One ordering for all uses.

## Incident filtering

**Accepted** iff accepted==true, day <= current_day, kind in supported_incident_kinds, and kind-specific fields valid. Apply accepted events in (day asc, event_id ASCII asc). Ignored events count in summary.ignored_incident_events.

- force_pin: dep_path, version in registry; optional override_advisories (listed advisories on that dep become overridden in Phase C). Survives retract/exclude for resolution.
- replace_workspace_wide: from_path, to_path, to_version with registry file and listed version.
- retract_emergency: dep_path, version, effective_day; retracted when effective_day <= current_day; reason "emergency_retract".
- module_graph_cycle: cycle_modules (>=2 names from workspace modules); those modules excluded from resolution.

## Phase A — replace-directive audit

Group `modules/*.replaces` by from_path.

1. Latest accepted replace_workspace_wide for this from_path (day, event_id): all rows status overridden_incident, effective_target from incident, source_event_id set; Phase B target from incident.
2. Else each row: missing registry for to_path -> block_target_missing, null target, null source_event_id; drop from group.
3. Remaining rows: unanimous tuple with count >= quorum -> applied_workspace and Phase B target; unanimous below quorum -> quorum_failed, MVS fallback; divergent tuples -> highest to_version wins (to_path ASCII tie), winners applied_workspace others conflict_divergent_targets; quorum not re-checked on divergent branch.

Emit one row per replace entry, sort (from_path, module_name). At most one active Phase B replace target per from_path group.

## Phase B — MVS with exclusion / retract / cycle

cycle_modules = union of cycle_modules from accepted module_graph_cycle. **Cycle-blocked** modules in that set contribute nothing to MVS, reachability, or excludes. Effective requirers of D: non-cycle-blocked modules listing D in requires.

For each dep D in any requires:

1. No effective requirers -> block_cycle, null version, source_event_id first module_graph_cycle (day, event_id). Stop.
2. Active force_pin(D,V,...) -> forced_pin with V and event_id. Wins over retract/exclude/advisory. Stop.
3. Phase A active workspace target with from_path=D (overridden_incident, applied_workspace, or divergent winner) -> workspace_replace to target path/version, source_event_id from incident if any. Stop.
4. Else candidate = max(min_version) over effective requirers. Walk registry[D].versions ascending from candidate: skip excluded by any effective requirer (walked_over_exclude); skip registry retracted or emergency retract effective (walked_over_retract). First survivor: action mvs_walk_excluded if walked_over_exclude else mvs_walk_retracted if walked_over_retract else mvs_select; source_event_id null except latest contributing retract_emergency for mvs_walk_retracted.
5. No survivor -> block_no_version, null version, null source_event_id.

## Phase C — Vulnerability triage

For advisory A on dep D = A.dep_path:

1. resolved_path/version from version_resolution[D]; if D missing -> post_resolution_version null, status mitigated_bumped.
2. covered = (resolved_path==D) and (resolved_version in A.affected_versions). severity_blocks = rank(A.severity) >= rank(threshold).
3. First match: force_pin with override listing A -> overridden; resolved_path!=D and not covered -> mitigated_by_replace; not covered -> mitigated_bumped; covered and action forced_pin -> unmitigated_pinned; covered and not severity_blocks and vulncheck_reachability_required and (union of requires[D].reachability_symbols over modules requiring D) disjoint from A.affected_symbols -> unreachable; else still_open_frozen.

post_resolution_version = resolved_version from (1) except null when D absent from version_resolution.

## Phase D — Cycle and retract report

- cycles: {cycle_modules ASCII-sorted, event_id} per accepted module_graph_cycle, sorted by event_id.
- module_view: per module in workspace (include cycle-blocked): module_name, in_cycle, blocked_versions[{dep_path, reason, version}] sorted by (dep_path, version, reason). Reasons: exclude_directive from M.excludes; retracted_intrinsic for each required D and registry-retracted V; retracted_emergency for accepted retract_emergency(D,V) when M requires D. in_cycle true iff module in any accepted cycle event.
- tool_impacts: each tools[] entry -> {module_name, dep_path, tool_status} sorted (module_name, dep_path). tool_status shared_with_requires if dep also in requires else tool_only.

## Phase E — Summary

summary.json: exactly these 14 integer keys: accepted_incident_events, advisories_total, advisories_unmitigated_pinned, advisories_unreachable, cycle_modules_total, deps_blocked_no_version, deps_forced_pin, deps_total, deps_workspace_replaced, ignored_incident_events, modules_total, replace_rows_applied_workspace, replace_rows_overridden_incident, tool_only_rows.

## Output schema

Emit each file into the decisions directory resolved from `GMBA_DECISIONS_DIR` (default `/app/decisions/`). Keys sorted at all depths; lists use documented sorts.

- version_resolution.json — {deps:[{action, dep_path, resolved_path, resolved_version, source_event_id}]} sorted dep_path. resolved_path defaults dep_path unless workspace replace.
- replace_directive_audit.json — {rows:[...]} sorted (from_path, module_name); row fields effective_target {to_path,to_version}|null, from_path, module_name, source_event_id, status.
- vulnerability_exposure.json — {advisories:[...]} sorted advisory_id; fields advisory_id, covered_post_resolution, dep_path, post_resolution_version, severity, status.
- cycle_and_retract_report.json — cycles, module_view, tool_impacts as Phase D.
- summary.json — Phase E.
