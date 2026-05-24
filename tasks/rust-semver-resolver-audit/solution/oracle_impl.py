from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")


def parse_version(s):
    m = re.match(r'^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.]+))?(?:\+([a-zA-Z0-9.]+))?$', s)
    if not m:
        raise ValueError(f"Invalid version: {s}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    pre_str = m.group(4)
    pre = []
    if pre_str:
        for part in pre_str.split('.'):
            if part.isdigit():
                pre.append(('num', int(part)))
            else:
                pre.append(('alpha', part))
    build = m.group(5) or ""
    return (major, minor, patch, pre, build)


def ver_tuple(v):
    major, minor, patch, pre, _ = v
    return (major, minor, patch, pre)


def compare_pre(a_pre, b_pre):
    if not a_pre and not b_pre:
        return 0
    if not a_pre:
        return 1
    if not b_pre:
        return -1
    for (at, av), (bt, bv) in zip(a_pre, b_pre):
        if at == 'num' and bt == 'num':
            if av != bv:
                return -1 if av < bv else 1
        elif at == 'alpha' and bt == 'alpha':
            if av != bv:
                return -1 if av < bv else 1
        elif at == 'num':
            return -1
        else:
            return 1
    if len(a_pre) != len(b_pre):
        return -1 if len(a_pre) < len(b_pre) else 1
    return 0


def ver_key(v):
    major, minor, patch, pre, _ = v
    if not pre:
        pre_sort = (1,)
    else:
        parts = []
        for t, val in pre:
            if t == 'num':
                parts.append((0, val, ''))
            else:
                parts.append((1, 0, val))
        pre_sort = (0, tuple(parts))
    return (major, minor, patch, pre_sort)


def ver_ge(a, b):
    return ver_key(a) >= ver_key(b)


def ver_lt(a, b):
    return ver_key(a) < ver_key(b)


def ver_str(v):
    major, minor, patch, pre, _ = v
    s = f"{major}.{minor}.{patch}"
    if pre:
        parts = []
        for t, val in pre:
            parts.append(str(val))
        s += "-" + ".".join(parts)
    return s


def compute_range(op, constraint_str):
    v = parse_version(constraint_str.lstrip('0') if False else constraint_str)
    major, minor, patch, pre, _ = v

    if op == '=':
        return v, (major, minor, patch + 1, [], '')

    if op == '~':
        low = v
        high = (major, minor + 1, 0, [], '')
        return low, high

    if op == '^':
        low = v
        if major != 0:
            high = (major + 1, 0, 0, [], '')
        elif minor != 0:
            high = (0, minor + 1, 0, [], '')
        else:
            high = (0, 0, patch + 1, [], '')
        return low, high

    raise ValueError(f"Unknown operator: {op}")


def parse_constraint(s):
    s = s.strip()
    if s.startswith('^'):
        return '^', s[1:]
    elif s.startswith('~'):
        return '~', s[1:]
    elif s.startswith('='):
        return '=', s[1:]
    else:
        return '^', s


def pad_version(s):
    parts = s.split('-', 1)
    base = parts[0]
    segs = base.split('.')
    while len(segs) < 3:
        segs.append('0')
    result = '.'.join(segs)
    if len(parts) > 1:
        result += '-' + parts[1]
    return result


registry_data = json.loads((DATA / "registry.json").read_text())
packages = {}
for name, versions in registry_data["packages"].items():
    parsed = []
    for vs in versions:
        parsed.append(parse_version(vs))
    parsed.sort(key=ver_key)
    packages[name] = parsed

project_dir = DATA / "projects"
projects = {}
for f in sorted(project_dir.glob("*.json")):
    manifest = json.loads(f.read_text())
    projects[manifest["name"]] = manifest["dependencies"]

resolutions = {}
for proj_name in sorted(projects.keys()):
    deps = projects[proj_name]
    resolved = {}
    unresolved = []
    for dep_name in sorted(deps.keys()):
        constraint_str = deps[dep_name]
        op, ver_part = parse_constraint(constraint_str)
        ver_part = pad_version(ver_part)
        low, high = compute_range(op, ver_part)

        if dep_name not in packages:
            unresolved.append(dep_name)
            continue

        candidates = packages[dep_name]
        best = None
        for cv in candidates:
            if ver_ge(cv, low) and ver_lt(cv, high):
                if best is None or ver_key(cv) > ver_key(best):
                    best = cv
        if best is not None:
            resolved[dep_name] = ver_str(best)
        else:
            unresolved.append(dep_name)

    resolutions[proj_name] = {
        "resolved": dict(sorted(resolved.items())),
        "unresolved": sorted(unresolved),
    }

all_deps = set()
dep_usage = {}
for proj_name, deps in projects.items():
    for dep_name in deps:
        all_deps.add(dep_name)
        if dep_name not in dep_usage:
            dep_usage[dep_name] = []
        dep_usage[dep_name].append(proj_name)

conflicts = []
for dep_name in sorted(dep_usage.keys()):
    users = dep_usage[dep_name]
    if len(users) < 2:
        continue

    all_can_resolve = True
    for proj_name in users:
        if dep_name in resolutions[proj_name]["unresolved"]:
            all_can_resolve = False
            break

    if not all_can_resolve:
        continue

    ranges = []
    for proj_name in users:
        constraint_str = projects[proj_name][dep_name]
        op, ver_part = parse_constraint(constraint_str)
        ver_part = pad_version(ver_part)
        low, high = compute_range(op, ver_part)
        ranges.append((low, high))

    int_low = ranges[0][0]
    int_high = ranges[0][1]
    for low, high in ranges[1:]:
        if ver_key(low) > ver_key(int_low):
            int_low = low
        if ver_key(high) < ver_key(int_high):
            int_high = high

    if ver_key(int_low) >= ver_key(int_high):
        entry = {
            "package": dep_name,
            "projects": {},
        }
        for proj_name in sorted(users):
            constraint_str = projects[proj_name][dep_name]
            resolved_ver = resolutions[proj_name]["resolved"].get(dep_name, "")
            entry["projects"][proj_name] = {
                "constraint": constraint_str,
                "resolved": resolved_ver,
            }
        conflicts.append(entry)

max_count = 0
for dep_name, users in dep_usage.items():
    if len(users) > max_count:
        max_count = len(users)

most_depended = sorted(
    [d for d, u in dep_usage.items() if len(u) == max_count]
)[0]

projects_fully = sum(
    1 for r in resolutions.values() if len(r["unresolved"]) == 0
)
projects_unresolved = sum(
    1 for r in resolutions.values() if len(r["unresolved"]) > 0
)

total_versions = sum(len(v) for v in packages.values())

report = {
    "conflicts": conflicts,
    "metadata": {
        "project_count": len(projects),
        "registry_package_count": len(packages),
        "registry_version_count": total_versions,
    },
    "resolutions": dict(sorted(resolutions.items())),
    "statistics": {
        "conflict_count": len(conflicts),
        "most_depended_count": max_count,
        "most_depended_package": most_depended,
        "projects_fully_resolved": projects_fully,
        "projects_with_unresolved": projects_unresolved,
        "total_unique_dependencies": len(all_deps),
    },
}

out_path = OUT / "resolution_report.json"
out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
print(f"Report written to {out_path}")

if __name__ == "__main__":
    raise SystemExit(0)
