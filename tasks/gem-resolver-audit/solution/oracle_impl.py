from __future__ import annotations

import json
import os
import math
import hashlib
import re
from pathlib import Path
from collections import deque

APP = Path("/app")
DATA = APP / "data"
OUT = APP / "output"

def load_json(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))

# ─── Version parsing and comparison ──────────────────────────────────────────

def parse_version(v):
    parts = []
    for seg in v.split("."):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(seg)
    return parts

def is_prerelease(v):
    parts = parse_version(v)
    for i, p in enumerate(parts):
        if i > 0 and isinstance(p, str):
            return True
    return False

def compare_segments(a, b):
    if isinstance(a, int) and isinstance(b, int):
        return (a > b) - (a < b)
    if isinstance(a, str) and isinstance(b, str):
        return (a > b) - (a < b)
    if isinstance(a, int) and isinstance(b, str):
        return 1
    return -1

def compare_versions(v1, v2):
    p1 = parse_version(v1)
    p2 = parse_version(v2)
    maxlen = max(len(p1), len(p2))
    for i in range(maxlen):
        if i >= len(p1):
            s1 = 0
            s2 = p2[i]
            if isinstance(s2, str):
                return 1
        elif i >= len(p2):
            s1 = p1[i]
            s2 = 0
            if isinstance(s1, str):
                return -1
        else:
            s1 = p1[i]
            s2 = p2[i]
        c = compare_segments(s1, s2)
        if c != 0:
            return c
    return 0

def version_key(v):
    class K:
        def __init__(self, ver):
            self.ver = ver
        def __lt__(self, other):
            return compare_versions(self.ver, other.ver) < 0
        def __eq__(self, other):
            return compare_versions(self.ver, other.ver) == 0
        def __le__(self, other):
            return compare_versions(self.ver, other.ver) <= 0
        def __gt__(self, other):
            return compare_versions(self.ver, other.ver) > 0
        def __ge__(self, other):
            return compare_versions(self.ver, other.ver) >= 0
    return K(v)

# ─── Constraint parsing and matching ─────────────────────────────────────────

def parse_constraint(s):
    s = s.strip()
    m = re.match(r'^(~>|>=|<=|!=|>|<|=)\s*(.+)$', s)
    if m:
        return m.group(1), m.group(2).strip()
    return "=", s

def pessimistic_upper(ver_str):
    parts = ver_str.split(".")
    if len(parts) < 2:
        return str(int(parts[0]) + 1)
    bump_idx = len(parts) - 2
    new_parts = parts[:bump_idx]
    new_parts.append(str(int(parts[bump_idx]) + 1))
    return ".".join(new_parts)

def constraint_references_prerelease(constraint_ver):
    return is_prerelease(constraint_ver)

def version_satisfies(ver, constraint_str, exclude_pre=True):
    op, cver = parse_constraint(constraint_str)
    if exclude_pre and is_prerelease(ver) and not constraint_references_prerelease(cver):
        return False
    c = compare_versions(ver, cver)
    if op == "=":
        return c == 0
    elif op == "!=":
        return c != 0
    elif op == ">":
        return c > 0
    elif op == ">=":
        return c >= 0
    elif op == "<":
        return c < 0
    elif op == "<=":
        return c <= 0
    elif op == "~>":
        upper = pessimistic_upper(cver)
        return compare_versions(ver, cver) >= 0 and compare_versions(ver, upper) < 0 and (
            not (exclude_pre and is_prerelease(ver) and not constraint_references_prerelease(cver))
        )
    return False

def find_best_version(gem_name, constraints, registry, exclude_pre=True):
    if gem_name not in registry:
        return None
    versions = list(registry[gem_name]["versions"].keys())
    candidates = []
    for v in versions:
        if all(version_satisfies(v, c, exclude_pre) for c in constraints):
            candidates.append(v)
    if not candidates:
        return None
    candidates.sort(key=version_key, reverse=True)
    return candidates[0]

# ─── Load data ────────────────────────────────────────────────────────────────

registry = {}
reg_dir = DATA / "registry"
for f in sorted(reg_dir.glob("*.json")):
    gem = load_json(f)
    registry[gem["name"]] = gem

projects = {}
proj_dir = DATA / "projects"
for d in sorted(proj_dir.iterdir()):
    if d.is_dir():
        gf = d / "Gemfile.json"
        if gf.exists():
            proj = load_json(gf)
            projects[proj["project_id"]] = proj

policy = load_json(DATA / "config" / "policy.json")
advisories_data = load_json(DATA / "advisories" / "advisories.json")
advisories = advisories_data["advisories"]

scope_filter = set(policy["scope_filter"])
exclude_pre = policy.get("exclude_prerelease", True)
max_depth = policy["max_dependency_depth"]
sev_ranks = policy["severity_ranks"]
risk_cfg = policy["risk_score"]
finding_sev = policy["finding_severity"]

# ─── Source hashes ────────────────────────────────────────────────────────────

def compute_source_hashes():
    hashes = {}
    for root, dirs, files in os.walk(str(DATA)):
        dirs.sort()
        for fn in sorted(files):
            fp = Path(root) / fn
            rel = str(fp.relative_to(APP)).replace("\\", "/")
            raw = fp.read_bytes()
            text = raw.decode("utf-8").replace("\r\n", "\n")
            if text.endswith("\n"):
                text = text[:-1]
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            hashes[rel] = h
    return hashes

source_hashes = compute_source_hashes()

# ─── Advisory matching ────────────────────────────────────────────────────────

def gem_affected_by_advisory(gem_name, version, adv):
    if adv["gem"] != gem_name:
        return False
    for c in adv["affected_versions"]:
        if not version_satisfies(version, c, exclude_pre=False):
            return False
    return True

# ─── Risk score ───────────────────────────────────────────────────────────────

def compute_risk_score(severity, depth):
    mult = risk_cfg["severity_multipliers"].get(severity, 1.0)
    base = risk_cfg["depth_decay_base"]
    dec = risk_cfg["rounding_decimals"]
    return round(mult * (base ** depth), dec)

def get_sev_rank(sev):
    return sev_ranks.get(sev, 99)

# ─── Resolve dependencies for a project ──────────────────────────────────────

def resolve_project(proj):
    pid = proj["project_id"]
    proj_license = proj["project_license"]
    deps = proj["dependencies"]

    resolved = {}
    conflicts = []
    queue = deque()

    for dep in deps:
        if dep["group"] not in scope_filter:
            continue
        queue.append({
            "gem": dep["gem"],
            "constraints": [dep["constraint"]],
            "depth": 1,
            "path": [pid],
            "source": "direct"
        })

    constraint_map = {}
    for dep in deps:
        if dep["group"] not in scope_filter:
            continue
        gn = dep["gem"]
        constraint_map.setdefault(gn, []).append(("direct", dep["constraint"]))

    while queue:
        entry = queue.popleft()
        gn = entry["gem"]
        depth = entry["depth"]
        path = entry["path"]

        if depth > max_depth + 3:
            continue

        if gn in resolved:
            continue

        all_constraints = [c for _, c in constraint_map.get(gn, [])]
        if not all_constraints:
            all_constraints = entry["constraints"]

        best = find_best_version(gn, all_constraints, registry, exclude_pre)
        if best is None:
            conflicts.append({
                "gem_name": gn,
                "constraints": all_constraints,
                "sources": [s for s, _ in constraint_map.get(gn, [])]
            })
            continue

        full_path = path + [gn]
        sources = list(set(s for s, _ in constraint_map.get(gn, [])))
        sources.sort()

        gem_data = registry[gn]["versions"][best]
        lic = gem_data.get("license", "UNKNOWN")

        resolved[gn] = {
            "gem_name": gn,
            "version": best,
            "depth": depth,
            "path": full_path,
            "license": lic,
            "constraint_sources": sources
        }

        if gn in registry and best in registry[gn]["versions"]:
            child_deps = registry[gn]["versions"][best].get("dependencies", {})
            for child_gem, child_constraint in sorted(child_deps.items()):
                if child_gem not in resolved:
                    constraint_map.setdefault(child_gem, []).append((gn, child_constraint))
                    queue.append({
                        "gem": child_gem,
                        "constraints": [child_constraint],
                        "depth": depth + 1,
                        "path": full_path,
                        "source": gn
                    })

    # Metrics
    total_resolved = len(resolved)
    direct_count = sum(1 for r in resolved.values() if r["depth"] == 1)
    transitive_count = total_resolved - direct_count
    max_d = max((r["depth"] for r in resolved.values()), default=0)

    avg_depth = 0.0
    if total_resolved > 0:
        harmonic_sum = sum(1.0 / r["depth"] for r in resolved.values())
        avg_depth = round(total_resolved / harmonic_sum, 6)

    vuln_count = 0
    for gn, rd in resolved.items():
        for adv in advisories:
            if gem_affected_by_advisory(gn, rd["version"], adv):
                vuln_count += 1
                break

    metrics = {
        "avg_depth": avg_depth,
        "direct_count": direct_count,
        "max_depth": max_d,
        "total_resolved": total_resolved,
        "transitive_count": transitive_count,
        "vulnerability_count": vuln_count
    }

    # Findings
    proj_findings = []
    compat_rules = policy.get("compatibility_rules", {})
    banned = set(policy.get("banned_licenses", []))
    copyleft = set(policy.get("copyleft_licenses", []))
    permissive = set(policy.get("permissive_licenses", []))

    for gn in sorted(resolved.keys()):
        rd = resolved[gn]
        lic = rd["license"]
        dep = rd["depth"]
        ver = rd["version"]

        if lic in banned:
            proj_findings.append({
                "finding_type": "banned_license",
                "severity": finding_sev["banned_license"],
                "gem_name": gn,
                "version": ver,
                "risk_score": compute_risk_score(finding_sev["banned_license"], dep),
                "evidence": {"gem_name": gn, "version": ver, "license": lic},
                "project_id": pid
            })

        if proj_license in compat_rules:
            allowed = set(compat_rules[proj_license])
            if lic not in allowed:
                proj_findings.append({
                    "finding_type": "license_incompatibility",
                    "severity": finding_sev["license_incompatibility"],
                    "gem_name": gn,
                    "version": ver,
                    "risk_score": compute_risk_score(finding_sev["license_incompatibility"], dep),
                    "evidence": {"gem_name": gn, "gem_license": lic, "project_license": proj_license},
                    "project_id": pid
                })

        if proj_license in permissive and lic in copyleft:
            proj_findings.append({
                "finding_type": "copyleft_in_permissive",
                "severity": finding_sev["copyleft_in_permissive"],
                "gem_name": gn,
                "version": ver,
                "risk_score": compute_risk_score(finding_sev["copyleft_in_permissive"], dep),
                "evidence": {"gem_name": gn, "gem_license": lic, "project_license": proj_license},
                "project_id": pid
            })

        for adv in advisories:
            if gem_affected_by_advisory(gn, ver, adv):
                proj_findings.append({
                    "finding_type": "vulnerability",
                    "severity": adv["severity"],
                    "gem_name": gn,
                    "version": ver,
                    "risk_score": compute_risk_score(adv["severity"], dep),
                    "evidence": {"advisory_id": adv["advisory_id"], "cvss_score": adv["cvss_score"],
                                 "description": adv["description"]},
                    "project_id": pid
                })

    for conf in conflicts:
        proj_findings.append({
            "finding_type": "version_conflict",
            "severity": finding_sev["version_conflict"],
            "gem_name": conf["gem_name"],
            "version": None,
            "risk_score": compute_risk_score(finding_sev["version_conflict"], 1),
            "evidence": {"constraints": conf["constraints"], "sources": conf["sources"]},
            "project_id": pid
        })

    proj_findings.sort(key=lambda f: (
        get_sev_rank(f["severity"]),
        f["finding_type"],
        f["gem_name"]
    ))

    resolved_list = sorted(resolved.values(), key=lambda r: r["gem_name"])

    conflict_list = []
    for c in conflicts:
        conflict_list.append({
            "constraints": c["constraints"],
            "gem_name": c["gem_name"],
            "sources": c["sources"]
        })
    conflict_list.sort(key=lambda c: c["gem_name"])

    return {
        "findings": proj_findings,
        "metrics": metrics,
        "project_id": pid,
        "project_license": proj_license,
        "resolved_dependencies": resolved_list,
        "version_conflicts": conflict_list
    }, proj_findings, conflicts

# ─── Run resolution ──────────────────────────────────────────────────────────

all_project_audits = []
all_findings = []
total_conflicts = 0

for pid in sorted(projects.keys()):
    proj = projects[pid]
    audit, findings, conflicts = resolve_project(proj)
    all_project_audits.append(audit)
    all_findings.extend(findings)
    total_conflicts += len(conflicts)

# Global findings sort
all_findings.sort(key=lambda f: (
    get_sev_rank(f["severity"]),
    -f["risk_score"],
    f["finding_type"],
    f["project_id"],
    f["gem_name"]
))

# findings_by_type
fbt = {}
for f in all_findings:
    fbt[f["finding_type"]] = fbt.get(f["finding_type"], 0) + 1

# findings_by_severity
fbs = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
for f in all_findings:
    fbs[f["severity"]] = fbs.get(f["severity"], 0) + 1

# aggregate risk (geometric mean)
agg_risk = 0.0
positive_scores = [f["risk_score"] for f in all_findings if f["risk_score"] > 0]
if positive_scores:
    log_sum = sum(math.log(s) for s in positive_scores)
    agg_risk = round(math.exp(log_sum / len(positive_scores)), 6)

total_gems = sum(a["metrics"]["total_resolved"] for a in all_project_audits)

summary = {
    "aggregate_risk_score": agg_risk,
    "findings_by_severity": fbs,
    "findings_by_type": dict(sorted(fbt.items())),
    "total_conflicts": total_conflicts,
    "total_findings": len(all_findings),
    "total_gems_resolved": total_gems,
    "total_projects": len(projects)
}

report = {
    "findings": all_findings,
    "project_audits": all_project_audits,
    "schema_version": 1,
    "source_hashes": dict(sorted(source_hashes.items())),
    "summary": summary
}

out_path = OUT / "gem_audit.json"
with open(out_path, "w") as f:
    json.dump(report, f, indent=2, sort_keys=True)
    f.write("\n")

print(f"Wrote {out_path}")
print(f"Projects: {len(projects)}, Total findings: {len(all_findings)}")

if __name__ == "__main__":
    raise SystemExit(0)
