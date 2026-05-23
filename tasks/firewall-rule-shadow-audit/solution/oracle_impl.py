from __future__ import annotations

import ipaddress
import json
import sys
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import combinations
from pathlib import Path
from typing import Any

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")

RULES_PATH = DATA_DIR / "rules.json"
FLOWS_PATH = DATA_DIR / "flows.json"
POLICY_PATH = DATA_DIR / "policy.json"

VERDICTS_OUT = OUT_DIR / "flow_verdicts.json"
ANALYSIS_OUT = OUT_DIR / "rule_analysis.json"
SUMMARY_OUT = OUT_DIR / "policy_summary.json"
EQUIV_OUT = OUT_DIR / "equivalence_classes.json"
DEPS_OUT = OUT_DIR / "rule_dependencies.json"
GRAPH_OUT = OUT_DIR / "perturbation_graph.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True)
    path.write_text(text + "\n", encoding="utf-8")


def normalize_cidr(value: str) -> str | None:
    if value == "any":
        return "any"
    try:
        net = ipaddress.IPv4Network(value, strict=False)
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        return None
    return str(net)


def cidr_contains(rule_cidr: str, ip_str: str) -> bool:
    if rule_cidr == "any":
        return True
    try:
        addr = ipaddress.IPv4Address(ip_str)
    except (ValueError, ipaddress.AddressValueError):
        return False
    try:
        network = ipaddress.IPv4Network(rule_cidr, strict=False)
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        return False
    return addr in network


def port_in_ranges(port_spec: Any, port: int) -> bool:
    if port_spec == "any":
        return True
    if not isinstance(port_spec, list):
        return False
    if not port_spec:
        return False
    for entry in port_spec:
        if not isinstance(entry, dict):
            continue
        start = entry.get("start")
        end = entry.get("end")
        if not isinstance(start, int) or not isinstance(end, int):
            continue
        if start > end:
            continue
        if start <= port <= end:
            return True
    return False


def predicate_is_unsatisfiable(rule: dict[str, Any]) -> bool:
    if normalize_cidr(rule["source"]) is None:
        return True
    if normalize_cidr(rule["destination"]) is None:
        return True
    for key in ("src_ports", "dst_ports"):
        spec = rule[key]
        if spec == "any":
            continue
        if not isinstance(spec, list) or not spec:
            return True
        valid = False
        for entry in spec:
            if not isinstance(entry, dict):
                continue
            start = entry.get("start")
            end = entry.get("end")
            if isinstance(start, int) and isinstance(end, int) and start <= end:
                valid = True
                break
        if not valid:
            return True
    return False


def rule_matches_flow(rule: dict[str, Any], flow: dict[str, Any], policy: dict[str, Any]) -> bool:
    if predicate_is_unsatisfiable(rule):
        return False
    if policy["enable_directionality"]:
        if rule["direction"] != flow["direction"]:
            return False
    src_cidr = normalize_cidr(rule["source"])
    dst_cidr = normalize_cidr(rule["destination"])
    if src_cidr is None or dst_cidr is None:
        return False
    if not cidr_contains(src_cidr, flow["src_ip"]):
        return False
    if not cidr_contains(dst_cidr, flow["dst_ip"]):
        return False
    if rule["protocol"] != "any" and rule["protocol"] != flow["protocol"]:
        return False
    if flow["protocol"] in ("tcp", "udp"):
        if not port_in_ranges(rule["src_ports"], flow["src_port"]):
            return False
        if not port_in_ranges(rule["dst_ports"], flow["dst_port"]):
            return False
    return True


def evaluation_order(rules: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    tb = policy["tie_breaker"]
    if tb == "priority_then_id":
        return sorted(rules, key=lambda r: (-r["priority"], r["id"]))
    if tb == "priority_lowest_wins":
        return sorted(rules, key=lambda r: (r["priority"], r["id"]))
    if tb == "id_only":
        return sorted(rules, key=lambda r: r["id"])
    raise ValueError(f"unknown tie_breaker: {tb}")


def evaluate_flow(flow: dict[str, Any], ordered_rules: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    evaluated: list[str] = []
    for rule in ordered_rules:
        evaluated.append(rule["id"])
        if rule_matches_flow(rule, flow, policy):
            return {
                "evaluated_rule_ids": evaluated,
                "id": flow["id"],
                "matched_rule_id": rule["id"],
                "verdict": rule["action"],
            }
    return {
        "evaluated_rule_ids": evaluated,
        "id": flow["id"],
        "matched_rule_id": None,
        "verdict": "default",
    }


def matched_flows_for_rule(rule: dict[str, Any], flows: list[dict[str, Any]], policy: dict[str, Any]) -> list[str]:
    return sorted(f["id"] for f in flows if rule_matches_flow(rule, f, policy))


def lex_smallest_min_cover(target: list[str], candidate_ids: list[str], candidate_sets: dict[str, set[str]]) -> list[str]:
    target_set = set(target)
    if not target_set:
        return []
    sorted_candidates = sorted(candidate_ids)
    n = len(sorted_candidates)
    for k in range(1, n + 1):
        best: tuple[str, ...] | None = None
        for combo in combinations(sorted_candidates, k):
            union: set[str] = set()
            for cid in combo:
                union |= candidate_sets[cid]
                if target_set <= union:
                    break
            if target_set <= union:
                if best is None or list(combo) < list(best):
                    best = combo
        if best is not None:
            return list(best)
    return []


def coverage_string(matched_count: int, total: int) -> str:
    if total == 0:
        return "0.00"
    pct = Decimal(matched_count) * Decimal(100) / Decimal(total)
    return str(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def classify_rules(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    ordered = evaluation_order(rules, policy)
    matched = {r["id"]: matched_flows_for_rule(r, flows, policy) for r in rules}
    matched_sets = {rid: set(mf) for rid, mf in matched.items()}
    pos_in_order = {r["id"]: idx for idx, r in enumerate(ordered)}

    full_verdicts = [evaluate_flow(f, ordered, policy) for f in flows]
    base_verdict_pair = {v["id"]: (v["verdict"], v["matched_rule_id"]) for v in full_verdicts}

    analysis: list[dict[str, Any]] = []

    for rule in rules:
        rid = rule["id"]
        mf = matched[rid]
        if not mf:
            analysis.append({
                "coverage_percent": coverage_string(0, len(flows)),
                "id": rid,
                "matched_flows": [],
                "shadowed_by": [],
                "status": "unreachable",
            })
            continue
        idx = pos_in_order[rid]
        earlier_ids = [ordered[i]["id"] for i in range(idx)]
        earlier_union: set[str] = set()
        for eid in earlier_ids:
            earlier_union |= matched_sets[eid]
        target_set = matched_sets[rid]
        if target_set <= earlier_union:
            cover = lex_smallest_min_cover(sorted(target_set), earlier_ids, matched_sets)
            analysis.append({
                "coverage_percent": coverage_string(len(mf), len(flows)),
                "id": rid,
                "matched_flows": list(mf),
                "shadowed_by": cover,
                "status": "shadowed",
            })
            continue
        rules_without = [r for r in rules if r["id"] != rid]
        ordered_without = evaluation_order(rules_without, policy)
        default_action = policy["default_action"]
        def _normalize(v: str) -> str:
            return default_action if v == "default" else v
        verdicts_without = {f["id"]: _normalize(evaluate_flow(f, ordered_without, policy)["verdict"]) for f in flows}
        base_normalized = {fid: _normalize(pair[0]) for fid, pair in base_verdict_pair.items()}
        is_redundant = all(verdicts_without[fid] == base_normalized[fid] for fid in verdicts_without)
        status = "redundant" if is_redundant else "effective"
        analysis.append({
            "coverage_percent": coverage_string(len(mf), len(flows)),
            "id": rid,
            "matched_flows": list(mf),
            "shadowed_by": [],
            "status": status,
        })

    analysis.sort(key=lambda x: x["id"])
    by_id = {entry["id"]: entry for entry in analysis}
    return analysis, by_id


def compute_equivalence_classes(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[str], list[str]]:
    base_ordered = evaluation_order(rules, policy)
    base_pairs: dict[str, tuple[str, str | None]] = {}
    for f in flows:
        v = evaluate_flow(f, base_ordered, policy)
        base_pairs[f["id"]] = (v["verdict"], v["matched_rule_id"])
    remaining = list(rules)
    removed: list[str] = []
    changed = True
    while changed:
        changed = False
        for rid in sorted(r["id"] for r in remaining):
            candidate = [r for r in remaining if r["id"] != rid]
            cand_ordered = evaluation_order(candidate, policy)
            ok = True
            for f in flows:
                v = evaluate_flow(f, cand_ordered, policy)
                if (v["verdict"], v["matched_rule_id"]) != base_pairs[f["id"]]:
                    ok = False
                    break
            if ok:
                remaining = candidate
                removed.append(rid)
                changed = True
                break
    minimal_ids = sorted(r["id"] for r in remaining)
    removed_ids = sorted(removed)
    return minimal_ids, removed_ids


def compute_escalation_warnings(
    analysis_by_id: dict[str, dict[str, Any]],
    rules: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    ordered = evaluation_order(rules, policy)
    pos = {r["id"]: idx for idx, r in enumerate(ordered)}
    warnings: list[dict[str, str]] = []
    for deny_rule in rules:
        if deny_rule["action"] != "deny":
            continue
        deny_id = deny_rule["id"]
        deny_status = analysis_by_id[deny_id]["status"]
        if deny_status in ("unreachable", "redundant"):
            continue
        deny_set = set(analysis_by_id[deny_id]["matched_flows"])
        if not deny_set:
            continue
        deny_pos = pos[deny_id]
        for allow_rule in rules:
            if allow_rule["action"] != "allow":
                continue
            allow_id = allow_rule["id"]
            if pos[allow_id] >= deny_pos:
                continue
            allow_set = set(analysis_by_id[allow_id]["matched_flows"])
            if deny_set & allow_set:
                warnings.append({
                    "earlier_rule_id": allow_id,
                    "rule_id": deny_id,
                    "type": "deny_after_allow",
                })
    warnings.sort(key=lambda w: (w["rule_id"], w["earlier_rule_id"]))
    return warnings


def compute_rule_dependencies(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
    base_analysis_by_id: dict[str, dict[str, Any]],
    base_flow_pairs: dict[str, tuple[str, str | None]],
) -> list[dict[str, Any]]:
    default_action = policy["default_action"]
    def _normalize(v: str) -> str:
        return default_action if v == "default" else v
    base_normalized = {fid: _normalize(p[0]) for fid, p in base_flow_pairs.items()}
    base_status_by_id = {rid: entry["status"] for rid, entry in base_analysis_by_id.items()}
    out: list[dict[str, Any]] = []
    for rule in rules:
        rid = rule["id"]
        reduced = [r for r in rules if r["id"] != rid]
        reduced_ordered = evaluation_order(reduced, policy)
        flows_changed: list[str] = []
        verdict_changes: list[dict[str, str]] = []
        for f in flows:
            v = evaluate_flow(f, reduced_ordered, policy)
            new_pair = (v["verdict"], v["matched_rule_id"])
            if new_pair != base_flow_pairs[f["id"]]:
                flows_changed.append(f["id"])
            new_norm = _normalize(v["verdict"])
            if new_norm != base_normalized[f["id"]]:
                verdict_changes.append({
                    "flow_id": f["id"],
                    "from_verdict": base_normalized[f["id"]],
                    "to_verdict": new_norm,
                })
        flows_changed.sort()
        verdict_changes.sort(key=lambda x: x["flow_id"])
        promoted: list[str] = []
        if reduced:
            new_analysis, _ = classify_rules(reduced, flows, policy)
            for entry in new_analysis:
                qid = entry["id"]
                if qid == rid:
                    continue
                if entry["status"] == "effective" and base_status_by_id.get(qid) != "effective":
                    promoted.append(qid)
        promoted.sort()
        if verdict_changes:
            crit = "critical"
        elif flows_changed:
            crit = "important"
        elif promoted:
            crit = "minor"
        else:
            crit = "none"
        out.append({
            "criticality": crit,
            "flows_changed": flows_changed,
            "id": rid,
            "promoted_rules": promoted,
            "verdict_changes": verdict_changes,
        })
    out.sort(key=lambda x: x["id"])
    return out


def compute_perturbation_graph(
    rules: list[dict[str, Any]],
    deps: list[dict[str, Any]],
) -> dict[str, Any]:
    rule_ids = [r["id"] for r in rules]
    promoted_by: dict[str, list[str]] = {entry["id"]: list(entry["promoted_rules"]) for entry in deps}

    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for src, targets in promoted_by.items():
        for tgt in targets:
            if src == tgt:
                continue
            key = (src, tgt)
            if key in seen:
                continue
            seen.add(key)
            edges.append(key)
    edges.sort()

    out_neighbors: dict[str, set[str]] = {rid: set() for rid in rule_ids}
    in_neighbors: dict[str, set[str]] = {rid: set() for rid in rule_ids}
    for src, tgt in edges:
        if src in out_neighbors:
            out_neighbors[src].add(tgt)
        if tgt in in_neighbors:
            in_neighbors[tgt].add(src)

    nodes = [
        {
            "id": rid,
            "in_degree": len(in_neighbors[rid]),
            "out_degree": len(out_neighbors[rid]),
        }
        for rid in sorted(rule_ids)
    ]

    index = {rid: i for i, rid in enumerate(rule_ids)}
    indices: list[int] = []
    lowlink: list[int] = []
    on_stack: list[bool] = []
    stack: list[int] = []
    idx_counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(v_idx: int) -> None:
        call_stack: list[tuple[int, int]] = [(v_idx, 0)]
        while call_stack:
            v, child_pos = call_stack[-1]
            if child_pos == 0:
                indices[v] = idx_counter[0]
                lowlink[v] = idx_counter[0]
                idx_counter[0] += 1
                stack.append(v)
                on_stack[v] = True
            v_id = rule_ids[v]
            children = sorted(out_neighbors[v_id])
            if child_pos < len(children):
                w = index[children[child_pos]]
                call_stack[-1] = (v, child_pos + 1)
                if indices[w] == -1:
                    call_stack.append((w, 0))
                elif on_stack[w]:
                    lowlink[v] = min(lowlink[v], indices[w])
            else:
                if lowlink[v] == indices[v]:
                    scc: list[str] = []
                    while True:
                        w = stack.pop()
                        on_stack[w] = False
                        scc.append(rule_ids[w])
                        if w == v:
                            break
                    sccs.append(sorted(scc))
                call_stack.pop()
                if call_stack:
                    parent_v = call_stack[-1][0]
                    lowlink[parent_v] = min(lowlink[parent_v], lowlink[v])

    indices = [-1] * len(rule_ids)
    lowlink = [0] * len(rule_ids)
    on_stack = [False] * len(rule_ids)
    for v in range(len(rule_ids)):
        if indices[v] == -1:
            strongconnect(v)

    cycles = sorted([sorted(s) for s in sccs if len(s) > 1], key=lambda c: c[0])

    scc_of: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for rid in scc:
            scc_of[rid] = i
    cond_out: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
    cond_in_count: dict[int, int] = {i: 0 for i in range(len(sccs))}
    for src, tgt in edges:
        si, ti = scc_of[src], scc_of[tgt]
        if si == ti:
            continue
        if ti not in cond_out[si]:
            cond_out[si].add(ti)
            cond_in_count[ti] += 1

    layers: list[list[str]] = []
    placed: set[int] = set()
    indeg = dict(cond_in_count)
    while len(placed) < len(sccs):
        current = sorted(
            [i for i in range(len(sccs)) if i not in placed and indeg[i] == 0],
            key=lambda i: sorted(sccs[i])[0],
        )
        if not current:
            break
        ids_in_layer: list[str] = []
        for i in current:
            ids_in_layer.extend(sccs[i])
            placed.add(i)
        layers.append(sorted(ids_in_layer))
        for i in current:
            for j in cond_out[i]:
                indeg[j] -= 1

    return {
        "cycles": cycles,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "nodes": nodes,
        "topological_layers": layers,
    }

def run_simulation(rules_doc: dict, flows_doc: dict, policy: dict) -> dict[str, Any]:
    rules = list(rules_doc["rules"])
    flows = list(flows_doc["flows"])
    ordered = evaluation_order(rules, policy)
    flow_verdicts = sorted(
        (evaluate_flow(f, ordered, policy) for f in flows),
        key=lambda v: v["id"],
    )
    analysis, by_id = classify_rules(rules, flows, policy)
    counts = {s: 0 for s in ("effective", "redundant", "shadowed", "unreachable")}
    for entry in analysis:
        counts[entry["status"]] += 1
    default_uses = sum(1 for v in flow_verdicts if v["verdict"] == "default")
    warnings = compute_escalation_warnings(by_id, rules, policy)
    summary = {
        "default_action_uses": default_uses,
        "effective": counts["effective"],
        "escalation_warnings": warnings,
        "redundant": counts["redundant"],
        "shadowed": counts["shadowed"],
        "total_rules": len(rules),
        "unreachable": counts["unreachable"],
    }
    minimal_ids, removed_ids = compute_equivalence_classes(rules, flows, policy)
    base_flow_pairs = {v["id"]: (v["verdict"], v["matched_rule_id"]) for v in flow_verdicts}
    deps = compute_rule_dependencies(rules, flows, policy, by_id, base_flow_pairs)
    perturbation_graph = compute_perturbation_graph(rules, deps)
    return {
        "flow_verdicts": {"flows": flow_verdicts},
        "rule_analysis": {"rules": analysis},
        "policy_summary": summary,
        "equivalence_classes": {
            "minimal_rule_ids": minimal_ids,
            "removed_rule_ids": removed_ids,
            "verdict_invariant": True,
        },
        "rule_dependencies": {"rules": deps},
        "perturbation_graph": perturbation_graph,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    rules_doc = load_json(in_dir / "rules.json")
    flows_doc = load_json(in_dir / "flows.json")
    policy = load_json(in_dir / "policy.json")
    outputs = run_simulation(rules_doc, flows_doc, policy)
    write_json(out_dir / "flow_verdicts.json", outputs["flow_verdicts"])
    write_json(out_dir / "rule_analysis.json", outputs["rule_analysis"])
    write_json(out_dir / "policy_summary.json", outputs["policy_summary"])
    write_json(out_dir / "equivalence_classes.json", outputs["equivalence_classes"])
    write_json(out_dir / "rule_dependencies.json", outputs["rule_dependencies"])
    write_json(out_dir / "perturbation_graph.json", outputs["perturbation_graph"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
