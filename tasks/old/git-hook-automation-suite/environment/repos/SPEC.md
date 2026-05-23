# Git Hook Automation Suite — Output Contract

This file is part of the read-only input dataset under `/app/repos/`. It defines exactly how the five output JSON files at `/app/audit/` must be derived from the inputs. Every requirement in this file is binding.

## Inputs

The dataset under `/app/repos/` contains:

- `pool_state.json` — `{"current_day": <int>, "policy_version": "<str>"}`. `current_day` is the audit reference day; all `day` fields elsewhere are integers.
- `baseline.json` — global hook policy (described below).
- `incident_log.json` — `{"events": [...]}` (described below).
- `repos/<repo>/profile.json`, `repos/<repo>/hooks_installed.json`, `repos/<repo>/recent_commits.json` — per-repo declarative state. The collection of repos is exactly the set of subdirectories of `repos/`.

`baseline.json` has the shape:

```
{
  "hook_policy": [
    {"name": "<hook>", "kind": "pre-commit"|"commit-msg"|"pre-push", "required_for_tiers": ["gold", ...], "required_checks": ["<chk>", ...]},
    ...
  ],
  "branch_protection": {"protected_branches": ["main", "release"], "required_hooks_per_branch": {"main": ["pre-commit", "commit-msg", "pre-push"], "release": [...]}},
  "commit_msg": {
    "max_length_per_tier": {"gold": 50, "silver": 72, "bronze": 100},
    "type_whitelist_per_tier": {"gold": ["feat", "fix"], "silver": [...], "bronze": [...]},
    "require_issue_ref_per_tier": {"gold": true, "silver": true, "bronze": false},
    "issue_ref_pattern": "^[A-Z]+-[0-9]+$"
  }
}
```

A repo's `profile.json` is `{"repo": "<name>", "tier": "gold"|"silver"|"bronze", "language": "python"|"javascript"|"go"|..., "override_rules": [<rule>, ...]}`. `override_rules` are objects of the same shape as `hook_policy` entries; any rule whose `kind` matches a global rule's `kind` *replaces* every global rule of that same `kind` for this repo. When the override list contains more than one entry of the same `kind`, only the **last** such entry (highest list index) participates; earlier entries with the same `kind` are silently dropped before merging. The repo's **effective policy** is therefore: every global rule whose `kind` is not in the override-kind set, plus the de-duplicated (last-wins) override list.

A repo's `hooks_installed.json` is `{"repo": "<name>", "installed": [{"name": "<hook>", "kind": "...", "checks_present": ["<chk>", ...]}, ...]}`. A hook is **compliant** for a repo iff its `kind` is required by the repo's effective policy AND its `checks_present` is a superset of the policy's `required_checks` for that hook kind.

A repo's `recent_commits.json` is `{"repo": "<name>", "commits": [{"sha": "<str>", "branch": "<str>", "msg_type": "<str>", "msg_subject": "<str>", "issue_ref": "<str>"|null, "day": <int>}, ...]}`. `msg_type` is the conventional-commit type token (e.g., `"feat"`); `msg_subject` is the subject string after the first colon-space.

## Incident-log filtering

An entry of `incident_log.events` is **accepted** iff **all** of the following hold:

- `kind` is one of `"emergency_waiver"`, `"compromise"`, `"audit_override"`.
- `day` is an integer and `day <= pool_state.current_day`.
- `repo` matches a known repo (i.e., `repos/<repo>/profile.json` exists).
- For `"emergency_waiver"`: `hook_kind` is one of `"pre-commit"`, `"commit-msg"`, `"pre-push"`, AND `duration_days` is a positive integer. The waiver covers days `[day, day + duration_days - 1]` inclusive; it is **active** iff `pool_state.current_day` falls in that range.
- For `"compromise"`: no extra fields are required (any present are ignored).
- For `"audit_override"`: `target_compliance` is one of `"compliant"`, `"non_compliant"`. This force-sets `compliance_level` for the repo (see "Compromise quarantine" below for precedence).

Every other event is silently ignored and counted in `summary.ignored_incident_events`.

## Hook-compliance evaluation

For each repo, after computing its effective policy:

1. **Required hooks** are the union of `hook_policy[].kind` whose `required_for_tiers` includes the repo's `tier`.
2. **Missing hooks** are required hooks the repo has not installed (no entry in `hooks_installed.installed` with that `kind`).
3. **Missing checks** are pairs `(hook_kind, check)` where the hook is installed but `check` is in the policy's `required_checks` and not in the repo's `checks_present`.
4. **Active waivers** are accepted `emergency_waiver` events for this repo whose range covers `pool_state.current_day`. A waivered hook is **excluded** from missing-hooks and missing-checks computation for compliance level purposes (but is still listed under the repo's `active_waivers`).

A repo's preliminary `compliance_level` is:
- `"compliant"` if (after subtracting waivered hooks) `missing_hooks` is empty AND `missing_checks` is empty.
- `"non_compliant"` otherwise.

## Commit-message review

For each commit in each repo (in input order), determine its `status`:

- `"valid"` if every check below passes.
- `"type_not_allowed"` if `msg_type` is not in `commit_msg.type_whitelist_per_tier[<repo.tier>]`.
- `"length_exceeded"` if `len(msg_subject) > commit_msg.max_length_per_tier[<repo.tier>]`.
- `"missing_issue_ref"` if `commit_msg.require_issue_ref_per_tier[<repo.tier>] == true` AND `issue_ref` is `null` or does not match `issue_ref_pattern`.
- `"protected_branch_violation"` if `branch` ∈ `protected_branches` AND `msg_type == "wip"` (wip commits to protected branches are always rejected regardless of tier whitelist).
- `"needs_review"` is reserved for the compromise cascade (see below).

When multiple statuses apply, use the **first** matching one in this priority order: `protected_branch_violation`, `type_not_allowed`, `length_exceeded`, `missing_issue_ref`. If none apply, the commit is `valid`.

## Compromise quarantine (cross-cutting)

For every repo with at least one accepted `compromise` incident event:

- Set `compliance_level = "quarantine"` regardless of hook state and regardless of `audit_override` events. This precedence is final.
- Re-flag every commit whose `day >= min(compromise_event.day for repo)` as `status = "needs_review"`, overwriting whatever status the commit-review phase computed. Earlier commits are unaffected.
- In `hook_install_plan.json`, every required hook for the repo (regardless of whether it is currently installed) is recorded as `action = "force_reinstall"` with `reason = "compromise_quarantine"`.

For a repo with **no** compromise event but with an accepted `audit_override` event whose `target_compliance` is `"compliant"` or `"non_compliant"`, set `compliance_level` to that target (after the preliminary computation, before quarantine — but compromise overrides this). When multiple `audit_override` events exist for the same repo, only the one with the largest `day` wins (ties on day broken by largest list index — last entry wins).

## Output schemas

All five outputs are written under `/app/audit/`. List ordering is part of the contract.

### `/app/audit/repo_compliance.json`

```
{"repos": [{"repo": "...", "tier": "...", "compliance_level": "compliant"|"non_compliant"|"quarantine", "missing_hooks": ["..."], "missing_checks": [{"hook": "...", "check": "..."}], "active_waivers": [{"hook": "...", "expires_day": <int>}], "compromise_day": <int>|null}]}
```

`repos` is sorted by `repo` ascending. `missing_hooks` is sorted ascending. `missing_checks` is sorted by `(hook, check)` ascending. `active_waivers` is sorted by `(hook, expires_day)` ascending. For a quarantined repo, `missing_hooks` and `missing_checks` are still computed against the effective policy (waivers ignored under quarantine), and `compromise_day` is the smallest accepted compromise event `day` for that repo. For non-quarantined repos, `compromise_day` is `null`.

### `/app/audit/hook_install_plan.json`

```
{"actions": [{"repo": "...", "hook": "...", "action": "install"|"force_reinstall", "reason": "missing_required"|"compromise_quarantine"}]}
```

`actions` is sorted by `(repo, hook)` ascending. For a non-quarantined repo, one `install` entry per missing required hook (waivered hooks excluded). For a quarantined repo, one `force_reinstall` entry per required hook (whether installed or not, waivers ignored). Each entry has exactly the four keys above.

### `/app/audit/commit_review.json`

```
{"commits": [{"sha": "...", "repo": "...", "branch": "...", "status": "valid"|"type_not_allowed"|"length_exceeded"|"missing_issue_ref"|"protected_branch_violation"|"needs_review"}]}
```

`commits` is sorted by `(repo, sha)` ascending. Entries have exactly the four keys above.

### `/app/audit/branch_protection.json`

```
{"entries": [{"repo": "...", "branch": "...", "required_hooks": ["..."], "missing_hooks": ["..."], "status": "compliant"|"missing_hook"|"waivered"|"quarantined"}]}
```

For each repo and each branch in `branch_protection.protected_branches`, emit one entry. `required_hooks` is sorted ascending and equals `branch_protection.required_hooks_per_branch[branch]`. `missing_hooks` is sorted ascending and contains required hooks the repo has not installed (waivers are NOT subtracted here — the waivered set still appears in `missing_hooks`). `status` is `quarantined` if the repo is quarantined; else `waivered` if `missing_hooks` is non-empty AND every entry of `missing_hooks` has an active waiver for that repo; else `missing_hook` if `missing_hooks` is non-empty; else `compliant`. `entries` is sorted by `(repo, branch)` ascending.

### `/app/audit/summary.json`

```
{"current_day": <int>, "policy_version": "<str>", "total_repos": <int>, "total_commits": <int>, "ignored_incident_events": <int>, "by_compliance": {"compliant": <int>, "non_compliant": <int>, "quarantine": <int>}, "by_commit_status": {"valid": <int>, "type_not_allowed": <int>, "length_exceeded": <int>, "missing_issue_ref": <int>, "protected_branch_violation": <int>, "needs_review": <int>}, "active_waivers": <int>, "compromised_repos": ["..."]}
```

`compromised_repos` is sorted ascending. `active_waivers` is the total count across all repos of `repo_compliance.repos[].active_waivers[]` entries. Every key in `by_compliance` and `by_commit_status` must appear with an integer value (zero if absent).

## Canonical encoding

Every output JSON file is encoded with `json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)` followed by exactly one trailing newline byte. Two correct implementations of this contract must produce byte-identical output for the same input. Do not modify any file under `/app/repos/` while computing the report.
