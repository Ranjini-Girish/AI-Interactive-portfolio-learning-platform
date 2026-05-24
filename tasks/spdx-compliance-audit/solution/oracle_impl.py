"""Oracle solution for dependency-license-audit-hard."""
from __future__ import annotations

import json
from pathlib import Path
from collections import Counter

DATA_DIR = Path("/app/data")
PKG_DIR = DATA_DIR / "packages"
PROJ_DIR = DATA_DIR / "projects"
CONFIG_DIR = Path("/app/config")
OUT_DIR = Path("/app/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ROUND_DIGITS = 4
CATEGORY_RANK = {"allowed": 0, "restricted": 1, "banned": 2}


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_all_packages():
    pkg_map = {}
    for fp in sorted(PKG_DIR.glob("*.json")):
        pkg = json.loads(fp.read_text(encoding="utf-8"))
        pkg_map[pkg["name"]] = pkg
    return pkg_map


def load_projects():
    projects = []
    for fp in sorted(PROJ_DIR.glob("*.json")):
        projects.append(json.loads(fp.read_text(encoding="utf-8")))
    return projects


def load_policy():
    return json.loads((CONFIG_DIR / "policy.json").read_text(encoding="utf-8"))


def build_license_maps(policy):
    lic_cat = {}
    sev_map = {}
    for cat_name, cat_data in policy["categories"].items():
        for lic in cat_data["licenses"]:
            lic_cat[lic] = cat_name
            sev_map[lic] = cat_data["severity"]
    return lic_cat, sev_map


def resolve_spdx(license_expr, lic_cat):
    expr = license_expr.strip()
    if expr.startswith("(") and expr.endswith(")"):
        inner = expr[1:-1].strip()
        if " OR " in inner:
            parts = [p.strip() for p in inner.split(" OR ")]
            best_rank, best_lic = 999, None
            for p in parts:
                cat = lic_cat.get(p, "banned")
                rank = CATEGORY_RANK.get(cat, 2)
                if rank < best_rank or (rank == best_rank and (best_lic is None or p < best_lic)):
                    best_rank = rank
                    best_lic = p
            return best_lic, lic_cat.get(best_lic, "banned")
        elif " AND " in inner:
            parts = [p.strip() for p in inner.split(" AND ")]
            worst_rank = -1
            for p in parts:
                rank = CATEGORY_RANK.get(lic_cat.get(p, "banned"), 2)
                if rank > worst_rank:
                    worst_rank = rank
            combined = " AND ".join(parts)
            worst_cat = [c for c, r in CATEGORY_RANK.items() if r == worst_rank][0]
            return combined, worst_cat
    return expr, lic_cat.get(expr, "banned")


def resolve_tree(project, pkg_map, lic_cat):
    dep_entries = {}
    queue = []
    for dep_name in project["direct_dependencies"]:
        queue.append((dep_name, 0, [project["project_id"], dep_name]))
    while queue:
        pkg_name, depth, path = queue.pop(0)
        pkg = pkg_map[pkg_name]
        if pkg_name in dep_entries:
            if depth < dep_entries[pkg_name]["depth"]:
                dep_entries[pkg_name]["depth"] = depth
                dep_entries[pkg_name]["dependency_path"] = list(path)
            continue
        eff_lic, eff_cat = resolve_spdx(pkg["license"], lic_cat)
        dep_entries[pkg_name] = {
            "package_name": pkg_name, "version": pkg["version"],
            "declared_license": pkg["license"], "effective_license": eff_lic,
            "license_category": eff_cat, "depth": depth, "dependency_path": list(path),
        }
        for sub in pkg.get("dependencies", []):
            queue.append((sub["name"], depth + 1, path + [sub["name"]]))
    return dep_entries


def find_violations(project, dep_entries, pkg_map, policy, lic_cat, sev_map):
    violations = []
    copyleft_sources = {}
    for pkg_name, entry in dep_entries.items():
        pkg = pkg_map[pkg_name]
        cat = entry["license_category"]
        is_waived = any(w["package"] == pkg_name and w["project"] == project["project_id"]
                        for w in policy["waivers"])
        if cat == "banned":
            violations.append({
                "package_name": pkg_name, "declared_license": pkg["license"],
                "violation_type": "banned_license",
                "severity": sev_map.get(entry["effective_license"], 10),
                "depth": entry["depth"], "dependency_path": entry["dependency_path"],
                "waived": is_waived,
            })
            if entry["effective_license"] in policy["copyleft_licenses"]:
                copyleft_sources[pkg_name] = entry["effective_license"]
        elif cat == "restricted":
            is_lgpl_dyn = ("LGPL" in entry["effective_license"]
                           and pkg.get("linking_type") == "dynamic"
                           and policy["lgpl_dynamic_linking_exempt"])
            violations.append({
                "package_name": pkg_name, "declared_license": pkg["license"],
                "violation_type": "restricted_license",
                "severity": sev_map.get(entry["effective_license"], 5),
                "depth": entry["depth"], "dependency_path": entry["dependency_path"],
                "waived": is_waived,
            })
            if not is_lgpl_dyn and entry["effective_license"] in policy["copyleft_licenses"]:
                copyleft_sources[pkg_name] = entry["effective_license"]

    for pkg_name, entry in dep_entries.items():
        pkg = pkg_map[pkg_name]
        for sub in pkg.get("dependencies", []):
            if sub["name"] in copyleft_sources:
                is_waived = any(w["package"] == pkg_name and w["project"] == project["project_id"]
                                for w in policy["waivers"])
                violations.append({
                    "package_name": pkg_name, "declared_license": pkg["license"],
                    "violation_type": "copyleft_propagation",
                    "severity": policy["copyleft_propagation_severity"],
                    "depth": entry["depth"], "dependency_path": entry["dependency_path"],
                    "propagated_from": sub["name"],
                    "source_license": copyleft_sources[sub["name"]],
                    "waived": is_waived,
                })
                copyleft_sources[pkg_name] = copyleft_sources[sub["name"]]

    violations.sort(key=lambda v: (-v["severity"], v["depth"], v["package_name"]))
    return violations


def main():
    pkg_map = load_all_packages()
    projects = load_projects()
    policy = load_policy()
    lic_cat, sev_map = build_license_maps(policy)

    project_results = []
    all_viol_lics = []

    for proj in projects:
        dep_entries = resolve_tree(proj, pkg_map, lic_cat)
        violations = find_violations(proj, dep_entries, pkg_map, policy, lic_cat, sev_map)
        deps_list = sorted(dep_entries.values(), key=lambda d: (d["depth"], d["package_name"]))
        deps_out = [{"package_name": d["package_name"], "version": d["version"],
                      "declared_license": d["declared_license"], "effective_license": d["effective_license"],
                      "license_category": d["license_category"], "depth": d["depth"]} for d in deps_list]
        risk = round(sum(v["severity"] / (v["depth"] + 1) for v in violations if not v["waived"]), ROUND_DIGITS)
        max_d = max(d["depth"] for d in dep_entries.values()) if dep_entries else 0
        project_results.append({
            "project_id": proj["project_id"], "project_license": proj["license"],
            "dependency_count": len(dep_entries), "direct_dependency_count": len(proj["direct_dependencies"]),
            "max_depth": max_d, "dependencies": deps_out, "violations": violations, "risk_score": risk,
        })
        for v in violations:
            all_viol_lics.append(v.get("source_license", resolve_spdx(v["declared_license"], lic_cat)[0])
                                 if v["violation_type"] == "copyleft_propagation"
                                 else resolve_spdx(v["declared_license"], lic_cat)[0])

    project_results.sort(key=lambda p: p["project_id"])
    total_v = sum(len(p["violations"]) for p in project_results)
    total_w = sum(1 for p in project_results for v in p["violations"] if v["waived"])
    at_risk = sum(1 for p in project_results if p["risk_score"] > 0)
    risks = {p["project_id"]: p["risk_score"] for p in project_results}
    highest = max(risks, key=risks.get) if risks else None
    counts = Counter(all_viol_lics)
    if counts:
        mx = max(counts.values())
        most_common = sorted(lic for lic, c in counts.items() if c == mx)[0]
    else:
        most_common = None

    report = {
        "metadata": {"total_projects": len(projects), "total_packages": len(pkg_map), "policy_version": policy["policy_version"]},
        "projects": project_results,
        "summary": {"total_violations": total_v, "total_waived": total_w, "projects_at_risk": at_risk,
                     "highest_risk_project": highest, "most_common_violation_license": most_common},
    }
    write_json(OUT_DIR / "audit_report.json", report)

main()

if __name__ == "__main__":
    raise SystemExit(0)
