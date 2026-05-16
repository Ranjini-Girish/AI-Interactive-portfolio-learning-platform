#!/bin/bash
set -euo pipefail

mkdir -p "${GHA_AUDIT_DIR:-/app/audit}"

python3 - <<'PYEOF'
import json
import os
import re
from pathlib import Path

DATA = Path(os.environ.get("GHA_DATA_DIR", "/app/repos"))
OUT = Path(os.environ.get("GHA_AUDIT_DIR", "/app/audit"))

ALLOWED_HOOK_KINDS = {"pre-commit", "commit-msg", "pre-push"}
ALLOWED_TIERS = {"gold", "silver", "bronze"}
ALLOWED_INCIDENT_KINDS = {"emergency_waiver", "compromise", "audit_override"}


def write_json(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.write("\n")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    pool = load_json(DATA / "pool_state.json")
    current_day = pool["current_day"]
    policy_version = pool["policy_version"]

    baseline = load_json(DATA / "baseline.json")
    global_rules = baseline["hook_policy"]
    branch_protection = baseline["branch_protection"]
    cm_cfg = baseline["commit_msg"]

    repos_dir = DATA / "repos"
    repo_names = sorted(p.name for p in repos_dir.iterdir() if p.is_dir())

    repo_data = {}
    for r in repo_names:
        prof = load_json(repos_dir / r / "profile.json")
        hooks = load_json(repos_dir / r / "hooks_installed.json")
        commits_doc = load_json(repos_dir / r / "recent_commits.json")
        repo_data[r] = {
            "profile": prof,
            "hooks": hooks,
            "commits": commits_doc.get("commits", []),
        }

    incidents_doc = load_json(DATA / "incident_log.json")
    accepted_events = []
    ignored = 0
    known = set(repo_names)
    for ev in incidents_doc.get("events", []):
        kind = ev.get("kind")
        day = ev.get("day")
        repo = ev.get("repo")
        if kind not in ALLOWED_INCIDENT_KINDS:
            ignored += 1
            continue
        if not isinstance(day, int) or isinstance(day, bool):
            ignored += 1
            continue
        if day > current_day:
            ignored += 1
            continue
        if repo not in known:
            ignored += 1
            continue
        if kind == "emergency_waiver":
            hk = ev.get("hook_kind")
            dur = ev.get("duration_days")
            if hk not in ALLOWED_HOOK_KINDS:
                ignored += 1
                continue
            if not isinstance(dur, int) or isinstance(dur, bool) or dur <= 0:
                ignored += 1
                continue
        if kind == "audit_override":
            tgt = ev.get("target_compliance")
            if tgt not in ("compliant", "non_compliant"):
                ignored += 1
                continue
        accepted_events.append(ev)

    waivers_by_repo = {r: [] for r in repo_names}
    compromise_days_by_repo = {r: [] for r in repo_names}
    overrides_by_repo = {r: [] for r in repo_names}

    for idx, ev in enumerate(accepted_events):
        repo = ev["repo"]
        if ev["kind"] == "emergency_waiver":
            waivers_by_repo[repo].append(ev)
        elif ev["kind"] == "compromise":
            compromise_days_by_repo[repo].append(ev["day"])
        elif ev["kind"] == "audit_override":
            overrides_by_repo[repo].append((idx, ev))

    def is_active_waiver(ev):
        start = ev["day"]
        end = ev["day"] + ev["duration_days"] - 1
        return start <= current_day <= end

    def expires_day(ev):
        return ev["day"] + ev["duration_days"] - 1

    def effective_policy(repo):
        prof = repo_data[repo]["profile"]
        overrides = prof.get("override_rules", []) or []
        last_by_kind = {}
        for r in overrides:
            last_by_kind[r["kind"]] = r
        kept = list(global_rules)
        kept = [r for r in kept if r["kind"] not in last_by_kind]
        kept.extend(last_by_kind.values())
        return kept

    repo_compliance_entries = []
    install_actions = []
    branch_entries = []
    commit_review_entries = []
    summary_active_waivers = 0

    by_compliance = {"compliant": 0, "non_compliant": 0, "quarantine": 0}
    by_commit_status = {
        "valid": 0,
        "type_not_allowed": 0,
        "length_exceeded": 0,
        "missing_issue_ref": 0,
        "protected_branch_violation": 0,
        "needs_review": 0,
    }
    compromised = []

    issue_ref_pat = re.compile(cm_cfg["issue_ref_pattern"])

    for repo in repo_names:
        prof = repo_data[repo]["profile"]
        tier = prof["tier"]
        installed = repo_data[repo]["hooks"].get("installed", [])
        installed_by_kind = {h["kind"]: h for h in installed}

        eff = effective_policy(repo)
        required_for_repo = [r for r in eff if tier in r["required_for_tiers"]]
        required_kinds = sorted({r["kind"] for r in required_for_repo})

        active_waivers_for_repo = [w for w in waivers_by_repo[repo] if is_active_waiver(w)]
        active_waiver_kinds = {w["hook_kind"] for w in active_waivers_for_repo}
        active_waivers_list = sorted(
            [{"hook": w["hook_kind"], "expires_day": expires_day(w)} for w in active_waivers_for_repo],
            key=lambda x: (x["hook"], x["expires_day"]),
        )
        summary_active_waivers += len(active_waivers_list)

        missing_hooks = []
        for k in required_kinds:
            if k not in installed_by_kind:
                missing_hooks.append(k)
        missing_hooks_sorted = sorted(missing_hooks)

        missing_checks = []
        for r in required_for_repo:
            k = r["kind"]
            if k in installed_by_kind:
                present = set(installed_by_kind[k].get("checks_present", []))
                for chk in r["required_checks"]:
                    if chk not in present:
                        missing_checks.append({"hook": k, "check": chk})
        missing_checks_sorted = sorted(missing_checks, key=lambda x: (x["hook"], x["check"]))

        eff_missing_hooks_no_waiver = [k for k in missing_hooks_sorted if k not in active_waiver_kinds]
        eff_missing_checks_no_waiver = [c for c in missing_checks_sorted if c["hook"] not in active_waiver_kinds]
        if not eff_missing_hooks_no_waiver and not eff_missing_checks_no_waiver:
            preliminary = "compliant"
        else:
            preliminary = "non_compliant"

        comp_days = compromise_days_by_repo[repo]
        is_quarantined = bool(comp_days)
        compromise_day = min(comp_days) if comp_days else None

        if is_quarantined:
            level = "quarantine"
            compromised.append(repo)
        else:
            ovs = overrides_by_repo[repo]
            if ovs:
                ovs_sorted = sorted(ovs, key=lambda t: (t[1]["day"], t[0]))
                _, winner = ovs_sorted[-1]
                level = winner["target_compliance"]
            else:
                level = preliminary

        repo_compliance_entries.append({
            "repo": repo,
            "tier": tier,
            "compliance_level": level,
            "missing_hooks": missing_hooks_sorted,
            "missing_checks": missing_checks_sorted,
            "active_waivers": active_waivers_list,
            "compromise_day": compromise_day,
        })

        by_compliance[level] = by_compliance.get(level, 0) + 1

        if is_quarantined:
            for k in required_kinds:
                install_actions.append({
                    "repo": repo,
                    "hook": k,
                    "action": "force_reinstall",
                    "reason": "compromise_quarantine",
                })
        else:
            for k in eff_missing_hooks_no_waiver:
                install_actions.append({
                    "repo": repo,
                    "hook": k,
                    "action": "install",
                    "reason": "missing_required",
                })

        for branch, req_hooks in branch_protection["required_hooks_per_branch"].items():
            if branch not in branch_protection["protected_branches"]:
                continue
            req_hooks_sorted = sorted(req_hooks)
            missing_b = [h for h in req_hooks_sorted if h not in installed_by_kind]
            if is_quarantined:
                bp_status = "quarantined"
            elif not missing_b:
                bp_status = "compliant"
            elif all(h in active_waiver_kinds for h in missing_b):
                bp_status = "waivered"
            else:
                bp_status = "missing_hook"
            branch_entries.append({
                "repo": repo,
                "branch": branch,
                "required_hooks": req_hooks_sorted,
                "missing_hooks": missing_b,
                "status": bp_status,
            })

        type_wl = cm_cfg["type_whitelist_per_tier"][tier]
        max_len = cm_cfg["max_length_per_tier"][tier]
        require_issue = cm_cfg["require_issue_ref_per_tier"][tier]

        for c in repo_data[repo]["commits"]:
            sha = c["sha"]
            branch = c["branch"]
            mtype = c["msg_type"]
            subj = c["msg_subject"]
            iref = c.get("issue_ref")
            cday = c["day"]

            if branch in branch_protection["protected_branches"] and mtype == "wip":
                status = "protected_branch_violation"
            elif mtype not in type_wl:
                status = "type_not_allowed"
            elif len(subj) > max_len:
                status = "length_exceeded"
            elif require_issue and (iref is None or not issue_ref_pat.fullmatch(iref)):
                status = "missing_issue_ref"
            else:
                status = "valid"

            if is_quarantined and cday >= compromise_day:
                status = "needs_review"

            commit_review_entries.append({
                "sha": sha,
                "repo": repo,
                "branch": branch,
                "status": status,
            })
            by_commit_status[status] = by_commit_status.get(status, 0) + 1

    repo_compliance_entries.sort(key=lambda x: x["repo"])
    install_actions.sort(key=lambda x: (x["repo"], x["hook"]))
    branch_entries.sort(key=lambda x: (x["repo"], x["branch"]))
    commit_review_entries.sort(key=lambda x: (x["repo"], x["sha"]))

    write_json(OUT / "repo_compliance.json", {"repos": repo_compliance_entries})
    write_json(OUT / "hook_install_plan.json", {"actions": install_actions})
    write_json(OUT / "commit_review.json", {"commits": commit_review_entries})
    write_json(OUT / "branch_protection.json", {"entries": branch_entries})

    summary = {
        "current_day": current_day,
        "policy_version": policy_version,
        "total_repos": len(repo_names),
        "total_commits": sum(len(repo_data[r]["commits"]) for r in repo_names),
        "ignored_incident_events": ignored,
        "by_compliance": by_compliance,
        "by_commit_status": by_commit_status,
        "active_waivers": summary_active_waivers,
        "compromised_repos": sorted(set(compromised)),
    }
    write_json(OUT / "summary.json", summary)


if __name__ == "__main__":
    main()
PYEOF
