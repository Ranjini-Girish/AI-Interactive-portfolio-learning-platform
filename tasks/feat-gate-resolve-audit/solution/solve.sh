#!/bin/bash
set -euo pipefail

export FGR_DATA_DIR="${FGR_DATA_DIR:-/app/featgate}"
export FGR_AUDIT_DIR="${FGR_AUDIT_DIR:-/app/audit}"
mkdir -p "${FGR_AUDIT_DIR}"

python3 <<'PYEOF'
import json
import os
from pathlib import Path


def pretty(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def solve(root: Path) -> dict[str, object]:
    policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    overrides = json.loads((root / "overrides.json").read_text(encoding="utf-8"))

    pkgs: dict[str, dict] = {}
    for path in sorted((root / "packages").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        pkgs[doc["name"]] = doc

    root_name = policy["root_package"]
    e0 = int(policy["default_epoch"])
    conflict_sets = [tuple(sorted(pair)) for pair in policy["conflict_sets"]]

    force_on: set[tuple[str, str]] = set()
    force_off: set[tuple[str, str]] = set()
    for p in overrides["patches"]:
        key = (p["package"], p["feature"])
        if p.get("force_on"):
            force_on.add(key)
        if p.get("force_off"):
            force_off.add(key)

    enabled: set[tuple[str, str]] = set()
    reached: set[str] = set()
    defaults_applied: set[str] = set()
    blocked_reason: dict[tuple[str, str], str] = {}
    queue: list[tuple[str, str]] = []

    def activate_package(pkg: str) -> None:
        if pkg not in pkgs:
            return
        reached.add(pkg)
        if pkg in defaults_applied:
            return
        defaults_applied.add(pkg)
        for feat in pkgs[pkg]["default_features"]:
            enqueue(pkg, feat)

    def enqueue(pkg: str, feat: str) -> None:
        if (pkg, feat) in enabled:
            return
        if feat not in pkgs[pkg]["features"]:
            return
        enabled.add((pkg, feat))
        for dep in pkgs[pkg]["features"][feat]:
            dep_pkg, dep_feat = dep.split("/", 1)
            queue.append((dep_pkg, dep_feat))

    activate_package(root_name)
    for feat in manifest["requested"]:
        if feat in pkgs[root_name]["features"]:
            enqueue(root_name, feat)

    for pkg_name, feat in list(force_on):
        if pkg_name in pkgs:
            activate_package(pkg_name)
            enqueue(pkg_name, feat)

    idx = 0
    while idx < len(queue):
        pkg_name, feat = queue[idx]
        idx += 1
        if pkg_name not in pkgs:
            continue
        activate_package(pkg_name)
        enqueue(pkg_name, feat)
        row = pkgs[pkg_name]
        for dep in row["deps"]:
            if dep.get("optional"):
                if int(dep["epoch"]) < e0:
                    for f in dep["features"]:
                        blocked_reason[(dep["name"], f)] = "optional_blocked"
                    continue
                ok = all(
                    f in pkgs[dep["name"]]["features"]
                    and (dep["name"], f) in enabled
                    for f in dep["features"]
                )
                if not ok:
                    for f in dep["features"]:
                        blocked_reason[(dep["name"], f)] = "optional_blocked"
                    continue
            dep_name = dep["name"]
            activate_package(dep_name)
            for f in dep["features"]:
                enqueue(dep_name, f)

    for pkg_name, feat in list(force_off):
        if (pkg_name, feat) in enabled:
            enabled.discard((pkg_name, feat))
            blocked_reason[(pkg_name, feat)] = "forced_off"

    enabled_names = {feat for pkg, feat in enabled}
    for a, b in conflict_sets:
        if a in enabled_names and b in enabled_names:
            drop = max(a, b)
            for pkg_name, row in pkgs.items():
                if drop in row["features"] and (pkg_name, drop) in enabled:
                    enabled.discard((pkg_name, drop))
                    blocked_reason[(pkg_name, drop)] = "conflict"
            enabled_names = {feat for pkg, feat in enabled}

    drops: list[dict] = []
    for (pkg_name, feat), reason in sorted(blocked_reason.items()):
        drops.append({"feature": feat, "package": pkg_name, "reason": reason})

    pkg_rows: list[dict] = []
    for name in sorted(reached):
        feats = sorted(f for p, f in enabled if p == name)
        if feats:
            status = "active"
        elif any((name, f) in blocked_reason for f in pkgs[name]["features"]):
            status = "blocked"
        else:
            status = "dormant"
        pkg_rows.append({"enabled_features": feats, "name": name, "status": status})

    drops.sort(key=lambda r: (r["feature"], r["package"]))
    summary = {
        "active_total": sum(1 for r in pkg_rows if r["status"] == "active"),
        "blocked_total": sum(1 for r in pkg_rows if r["status"] == "blocked"),
        "conflict_drop_total": sum(1 for d in drops if d["reason"] == "conflict"),
        "dormant_total": sum(1 for r in pkg_rows if r["status"] == "dormant"),
        "forced_off_total": sum(1 for d in drops if d["reason"] == "forced_off"),
        "optional_blocked_total": sum(
            1 for d in drops if d["reason"] == "optional_blocked"
        ),
        "package_total": len(pkg_rows),
        "root_package": root_name,
    }
    return {
        "package_states.json": {"packages": pkg_rows},
        "conflict_report.json": {"drops": drops},
        "summary.json": summary,
    }


data = Path(os.environ.get("FGR_DATA_DIR", "/app/featgate"))
audit = Path(os.environ.get("FGR_AUDIT_DIR", "/app/audit"))
for name, obj in solve(data).items():
    pretty(audit / name, obj)
PYEOF
