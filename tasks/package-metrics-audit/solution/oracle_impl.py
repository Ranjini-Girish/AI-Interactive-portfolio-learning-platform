"""
Oracle solution — ground truth implementation.
Parses Java source files under /app/src/, computes Robert C. Martin's
packaging metrics, detects circular dependencies, SDP violations,
and produces the audit report at /app/output/report.json.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from collections import defaultdict

SRC_DIR = Path("/app/src")
OUT_DIR = Path("/app/output")
OUT_DIR.mkdir(parents=True, exist_ok=True)

ACME_PREFIX = "com.acme."


def round6(x):
    if x is None:
        return None
    if isinstance(x, int):
        return x
    return round(x, 6)


def write_json(path, payload):
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_java_files(src_dir):
    """Parse all .java files, return list of (package, type_kind, type_name, imports)."""
    files = []
    for java_file in sorted(src_dir.rglob("*.java")):
        text = java_file.read_text(encoding="utf-8")

        pkg_match = re.search(r'^\s*package\s+([\w.]+)\s*;', text, re.MULTILINE)
        if not pkg_match:
            continue
        pkg = pkg_match.group(1)

        imports = set()
        for m in re.finditer(r'^\s*import\s+([\w.]+(?:\.\*)?)\s*;', text, re.MULTILINE):
            imp = m.group(1)
            if imp.startswith("com.acme."):
                parts = imp.split(".")
                if len(parts) >= 3:
                    imp_pkg = ".".join(parts[:3])
                    if imp_pkg != pkg:
                        imports.add(imp_pkg)

        type_kind = classify_type(text)
        type_name = java_file.stem

        files.append({
            "package": pkg,
            "type_kind": type_kind,
            "type_name": type_name,
            "imports": imports,
        })
    return files


def classify_type(text):
    """Classify the top-level type in a Java source file."""
    cleaned = re.sub(r'//.*?$', '', text, flags=re.MULTILINE)
    cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)

    if re.search(r'\bpublic\s+@interface\s+', cleaned):
        return "annotation"
    if re.search(r'\bpublic\s+enum\s+', cleaned):
        return "enum"
    if re.search(r'\bpublic\s+interface\s+', cleaned):
        return "interface"
    if re.search(r'\bpublic\s+abstract\s+class\s+', cleaned):
        return "abstract_class"
    if re.search(r'\bpublic\s+class\s+', cleaned):
        return "concrete_class"
    if re.search(r'\b@interface\s+', cleaned):
        return "annotation"
    if re.search(r'\benum\s+', cleaned):
        return "enum"
    if re.search(r'\binterface\s+', cleaned):
        return "interface"
    if re.search(r'\babstract\s+class\s+', cleaned):
        return "abstract_class"
    if re.search(r'\bclass\s+', cleaned):
        return "concrete_class"
    return "concrete_class"


def build_package_data(parsed_files):
    """Build per-package type counts and dependency edges."""
    packages = defaultdict(lambda: {
        "abstract_classes": 0, "interfaces": 0, "concrete_classes": 0,
        "enums": 0, "annotations": 0, "total": 0,
        "depends_on": set(),
    })

    kind_to_key = {
        "abstract_class": "abstract_classes",
        "interface": "interfaces",
        "concrete_class": "concrete_classes",
        "enum": "enums",
        "annotation": "annotations",
    }

    for f in parsed_files:
        pkg = f["package"]
        kind = f["type_kind"]
        key = kind_to_key[kind]
        packages[pkg][key] += 1
        packages[pkg]["total"] += 1
        packages[pkg]["depends_on"].update(f["imports"])

    result = {}
    for pkg_name in sorted(packages.keys()):
        p = packages[pkg_name]
        result[pkg_name] = {
            "types": {
                "total": p["total"],
                "abstract_classes": p.get("abstract_classes", 0),
                "interfaces": p.get("interfaces", 0),
                "concrete_classes": p.get("concrete_classes", 0),
                "enums": p.get("enums", 0),
                "annotations": p.get("annotations", 0),
            },
            "depends_on": sorted(p["depends_on"]),
        }
    return result


def compute_coupling(pkg_data):
    """Compute Ca and Ce for each package."""
    depended_on_by = defaultdict(set)
    for pkg_name, data in pkg_data.items():
        for dep in data["depends_on"]:
            if dep in pkg_data:
                depended_on_by[dep].add(pkg_name)

    for pkg_name in pkg_data:
        ce = len(pkg_data[pkg_name]["depends_on"])
        ca = len(depended_on_by.get(pkg_name, set()))
        pkg_data[pkg_name]["afferent_coupling"] = ca
        pkg_data[pkg_name]["efferent_coupling"] = ce
        pkg_data[pkg_name]["depended_on_by"] = sorted(depended_on_by.get(pkg_name, set()))

        if ca + ce == 0:
            pkg_data[pkg_name]["instability"] = None
        else:
            pkg_data[pkg_name]["instability"] = round6(ce / (ca + ce))

        types = pkg_data[pkg_name]["types"]
        total = types["total"]
        if total == 0:
            pkg_data[pkg_name]["abstractness"] = None
        else:
            abstract_count = (types["abstract_classes"] +
                              types["interfaces"] +
                              types["annotations"])
            pkg_data[pkg_name]["abstractness"] = round6(abstract_count / total)

        inst = pkg_data[pkg_name]["instability"]
        abst = pkg_data[pkg_name]["abstractness"]
        if inst is None or abst is None:
            pkg_data[pkg_name]["distance"] = None
        else:
            pkg_data[pkg_name]["distance"] = round6(abs(abst + inst - 1))


def tarjan_scc(packages, pkg_data):
    """Find strongly connected components using Tarjan's algorithm."""
    index_counter = [0]
    stack = []
    on_stack = set()
    index = {}
    lowlink = {}
    sccs = []

    def strongconnect(v):
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in sorted(pkg_data[v]["depends_on"]):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.append(w)
                if w == v:
                    break
            if len(scc) >= 2:
                sccs.append(sorted(scc))

    for v in sorted(packages):
        if v not in index:
            strongconnect(v)

    sccs.sort(key=lambda s: s[0])

    result = []
    for i, scc in enumerate(sccs, 1):
        result.append({
            "cycle_id": i,
            "packages": scc,
            "representative": scc[0],
        })
    return result


def find_sdp_violations(pkg_data):
    """Find Stable Dependencies Principle violations."""
    violations = []
    for pkg_name, data in sorted(pkg_data.items()):
        src_inst = data["instability"]
        if src_inst is None:
            continue
        for dep in sorted(data["depends_on"]):
            if dep not in pkg_data:
                continue
            tgt_inst = pkg_data[dep]["instability"]
            if tgt_inst is None:
                continue
            if tgt_inst > src_inst:
                violations.append({
                    "source": pkg_name,
                    "target": dep,
                    "source_instability": src_inst,
                    "target_instability": tgt_inst,
                })
    return violations


def compute_layers(pkg_data, sccs):
    """Compute layer assignment using condensation DAG."""
    pkg_to_scc = {}
    for scc in sccs:
        for pkg in scc["packages"]:
            pkg_to_scc[pkg] = tuple(scc["packages"])

    nodes = set()
    for pkg in pkg_data:
        if pkg in pkg_to_scc:
            nodes.add(pkg_to_scc[pkg])
        else:
            nodes.add((pkg,))

    def get_node(pkg):
        return pkg_to_scc.get(pkg, (pkg,))

    edges = defaultdict(set)
    for pkg, data in pkg_data.items():
        src_node = get_node(pkg)
        for dep in data["depends_on"]:
            if dep not in pkg_data:
                continue
            tgt_node = get_node(dep)
            if tgt_node != src_node:
                edges[src_node].add(tgt_node)

    layer_cache = {}

    def get_layer(node):
        if node in layer_cache:
            return layer_cache[node]
        layer_cache[node] = -1  # sentinel for cycle detection
        if not edges[node]:
            layer_cache[node] = 0
        else:
            max_dep_layer = 0
            for dep_node in edges[node]:
                dep_layer = get_layer(dep_node)
                if dep_layer > max_dep_layer:
                    max_dep_layer = dep_layer
            layer_cache[node] = max_dep_layer + 1
        return layer_cache[node]

    for node in nodes:
        get_layer(node)

    for pkg in pkg_data:
        node = get_node(pkg)
        pkg_data[pkg]["layer"] = layer_cache[node]


def classify_zones(pkg_data):
    """Classify packages into Zone of Pain and Zone of Uselessness."""
    pain = []
    uselessness = []
    for pkg_name, data in sorted(pkg_data.items()):
        d = data["distance"]
        i = data["instability"]
        a = data["abstractness"]
        if d is None or i is None or a is None:
            continue
        if d > 0.5 and i < 0.5 and a < 0.5:
            pain.append(pkg_name)
        if d > 0.5 and i > 0.5 and a > 0.5:
            uselessness.append(pkg_name)
    return sorted(pain), sorted(uselessness)


def main():
    parsed = parse_java_files(SRC_DIR)
    pkg_data = build_package_data(parsed)
    compute_coupling(pkg_data)

    all_packages = sorted(pkg_data.keys())
    sccs = tarjan_scc(all_packages, pkg_data)
    sdp_violations = find_sdp_violations(pkg_data)
    compute_layers(pkg_data, sccs)
    pain, uselessness = classify_zones(pkg_data)

    dep_edges = []
    for pkg_name in sorted(pkg_data.keys()):
        for dep in sorted(pkg_data[pkg_name]["depends_on"]):
            dep_edges.append({"source": pkg_name, "target": dep})

    packages_list = []
    for pkg_name in all_packages:
        d = pkg_data[pkg_name]
        packages_list.append({
            "name": pkg_name,
            "types": d["types"],
            "afferent_coupling": d["afferent_coupling"],
            "efferent_coupling": d["efferent_coupling"],
            "instability": d["instability"],
            "abstractness": d["abstractness"],
            "distance": d["distance"],
            "depends_on": d["depends_on"],
            "depended_on_by": d["depended_on_by"],
            "layer": d["layer"],
        })

    total_types = sum(d["types"]["total"] for d in pkg_data.values())

    report = {
        "packages": packages_list,
        "dependency_edges": dep_edges,
        "circular_dependencies": sccs,
        "sdp_violations": sdp_violations,
        "summary": {
            "total_packages": len(all_packages),
            "total_types": total_types,
            "total_dependency_edges": len(dep_edges),
            "circular_dependency_count": len(sccs),
            "sdp_violation_count": len(sdp_violations),
            "packages_in_zone_of_pain": pain,
            "packages_in_zone_of_uselessness": uselessness,
        },
    }

    write_json(OUT_DIR / "report.json", report)


main()

if __name__ == "__main__":
    raise SystemExit(0)
