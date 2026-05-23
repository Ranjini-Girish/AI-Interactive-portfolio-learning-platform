"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from decimal import ROUND_HALF_EVEN, Decimal
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest


def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for the Java entry class."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        JAVA_CLASS,
        str(data_dir),
        str(out_dir),
    ]


def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
JAVA_CLASS = "FirewallRuleShadow"
BUILD_DIR = Path("/app/build")
GSON_CP = "/opt/gson.jar"

RULES_PATH = DATA_DIR / "rules.json"
FLOWS_PATH = DATA_DIR / "flows.json"
POLICY_PATH = DATA_DIR / "policy.json"

VERDICTS_PATH = OUT_DIR / "flow_verdicts.json"
ANALYSIS_PATH = OUT_DIR / "rule_analysis.json"
SUMMARY_PATH = OUT_DIR / "policy_summary.json"
EQUIV_PATH = OUT_DIR / "equivalence_classes.json"
DEPS_PATH = OUT_DIR / "rule_dependencies.json"
GRAPH_PATH = OUT_DIR / "perturbation_graph.json"

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    RULES_PATH: "39270b00f073fd579448aa7dd55328afd9edadcbc43395dbe6c022c1d3d69fc1",
    FLOWS_PATH: "e7c651f4d04f5932c7ff304a647485a0da13fff80a837c8a17588d7755d7289e",
    POLICY_PATH: "52529b930ea457fd254700490f6bb6d88b57ac3bf2cb45968219fe15b1cbcff8",
}

VALID_STATUSES = ("effective", "redundant", "shadowed", "unreachable")
COVERAGE_RE = re.compile(r"^\d+\.\d{2}$")


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference implementation (mirrors instruction.md; recomputed from inputs at test time)
# ---------------------------------------------------------------------------


def _normalize_cidr(value: str) -> str | None:
    if value == "any":
        return "any"
    try:
        net = ipaddress.IPv4Network(value, strict=False)
    except (ValueError, ipaddress.AddressValueError, ipaddress.NetmaskValueError):
        return None
    return str(net)


def _cidr_contains(rule_cidr: str, ip_str: str) -> bool:
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


def _port_in_ranges(port_spec: Any, port: int) -> bool:
    if port_spec == "any":
        return True
    if not isinstance(port_spec, list) or not port_spec:
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


def _predicate_is_unsatisfiable(rule: dict[str, Any]) -> bool:
    if _normalize_cidr(rule["source"]) is None:
        return True
    if _normalize_cidr(rule["destination"]) is None:
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


def _rule_matches_flow(rule: dict[str, Any], flow: dict[str, Any], policy: dict[str, Any]) -> bool:
    if _predicate_is_unsatisfiable(rule):
        return False
    if policy["enable_directionality"] and rule["direction"] != flow["direction"]:
        return False
    src_cidr = _normalize_cidr(rule["source"])
    dst_cidr = _normalize_cidr(rule["destination"])
    if src_cidr is None or dst_cidr is None:
        return False
    if not _cidr_contains(src_cidr, flow["src_ip"]):
        return False
    if not _cidr_contains(dst_cidr, flow["dst_ip"]):
        return False
    if rule["protocol"] != "any" and rule["protocol"] != flow["protocol"]:
        return False
    if flow["protocol"] in ("tcp", "udp"):
        if not _port_in_ranges(rule["src_ports"], flow["src_port"]):
            return False
        if not _port_in_ranges(rule["dst_ports"], flow["dst_port"]):
            return False
    return True


def _evaluation_order(rules: list[dict[str, Any]], policy: dict[str, Any]) -> list[dict[str, Any]]:
    tb = policy["tie_breaker"]
    if tb == "priority_then_id":
        return sorted(rules, key=lambda r: (-r["priority"], r["id"]))
    if tb == "priority_lowest_wins":
        return sorted(rules, key=lambda r: (r["priority"], r["id"]))
    if tb == "id_only":
        return sorted(rules, key=lambda r: r["id"])
    raise ValueError(f"unknown tie_breaker: {tb}")


def _evaluate_flow(
    flow: dict[str, Any],
    ordered_rules: list[dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    evaluated: list[str] = []
    for rule in ordered_rules:
        evaluated.append(rule["id"])
        if _rule_matches_flow(rule, flow, policy):
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


def _matched_flow_ids(
    rule: dict[str, Any], flows: list[dict[str, Any]], policy: dict[str, Any]
) -> list[str]:
    return sorted(f["id"] for f in flows if _rule_matches_flow(rule, f, policy))


def _lex_smallest_min_cover(
    target: list[str],
    candidate_ids: list[str],
    candidate_sets: dict[str, set[str]],
) -> list[str]:
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


def _coverage_string(matched_count: int, total: int) -> str:
    if total == 0:
        return "0.00"
    pct = Decimal(matched_count) * Decimal(100) / Decimal(total)
    return str(pct.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def _classify_rules(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    ordered = _evaluation_order(rules, policy)
    matched = {r["id"]: _matched_flow_ids(r, flows, policy) for r in rules}
    matched_sets = {rid: set(mf) for rid, mf in matched.items()}
    pos_in_order = {r["id"]: idx for idx, r in enumerate(ordered)}

    full_verdicts = [_evaluate_flow(f, ordered, policy) for f in flows]
    base_pair = {v["id"]: (v["verdict"], v["matched_rule_id"]) for v in full_verdicts}

    default_action = policy["default_action"]

    def normalize(v: str) -> str:
        return default_action if v == "default" else v

    base_normalized = {fid: normalize(p[0]) for fid, p in base_pair.items()}

    analysis: list[dict[str, Any]] = []
    for rule in rules:
        rid = rule["id"]
        mf = matched[rid]
        if not mf:
            analysis.append({
                "coverage_percent": _coverage_string(0, len(flows)),
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
            cover = _lex_smallest_min_cover(sorted(target_set), earlier_ids, matched_sets)
            analysis.append({
                "coverage_percent": _coverage_string(len(mf), len(flows)),
                "id": rid,
                "matched_flows": list(mf),
                "shadowed_by": cover,
                "status": "shadowed",
            })
            continue
        rules_without = [r for r in rules if r["id"] != rid]
        ordered_without = _evaluation_order(rules_without, policy)
        verdicts_without = {
            f["id"]: normalize(_evaluate_flow(f, ordered_without, policy)["verdict"])
            for f in flows
        }
        is_redundant = all(verdicts_without[fid] == base_normalized[fid] for fid in verdicts_without)
        analysis.append({
            "coverage_percent": _coverage_string(len(mf), len(flows)),
            "id": rid,
            "matched_flows": list(mf),
            "shadowed_by": [],
            "status": "redundant" if is_redundant else "effective",
        })

    analysis.sort(key=lambda x: x["id"])
    by_id = {entry["id"]: entry for entry in analysis}
    return analysis, by_id


def _compute_equivalence_classes(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
) -> tuple[list[str], list[str]]:
    base_ordered = _evaluation_order(rules, policy)
    base_pairs: dict[str, tuple[str, str | None]] = {}
    for f in flows:
        v = _evaluate_flow(f, base_ordered, policy)
        base_pairs[f["id"]] = (v["verdict"], v["matched_rule_id"])

    remaining = list(rules)
    removed: list[str] = []
    changed = True
    while changed:
        changed = False
        for rid in sorted(r["id"] for r in remaining):
            candidate = [r for r in remaining if r["id"] != rid]
            cand_ordered = _evaluation_order(candidate, policy)
            ok = True
            for f in flows:
                v = _evaluate_flow(f, cand_ordered, policy)
                if (v["verdict"], v["matched_rule_id"]) != base_pairs[f["id"]]:
                    ok = False
                    break
            if ok:
                remaining = candidate
                removed.append(rid)
                changed = True
                break
    return sorted(r["id"] for r in remaining), sorted(removed)


def _compute_escalation_warnings(
    analysis_by_id: dict[str, dict[str, Any]],
    rules: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    ordered = _evaluation_order(rules, policy)
    pos = {r["id"]: idx for idx, r in enumerate(ordered)}
    warnings: list[dict[str, str]] = []
    for deny_rule in rules:
        if deny_rule["action"] != "deny":
            continue
        deny_id = deny_rule["id"]
        if analysis_by_id[deny_id]["status"] in ("unreachable", "redundant"):
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
            if deny_set & set(analysis_by_id[allow_id]["matched_flows"]):
                warnings.append({
                    "earlier_rule_id": allow_id,
                    "rule_id": deny_id,
                    "type": "deny_after_allow",
                })
    warnings.sort(key=lambda w: (w["rule_id"], w["earlier_rule_id"]))
    return warnings


def _compute_rule_dependencies(
    rules: list[dict[str, Any]],
    flows: list[dict[str, Any]],
    policy: dict[str, Any],
    base_analysis_by_id: dict[str, dict[str, Any]],
    base_flow_pairs: dict[str, tuple[str, str | None]],
) -> list[dict[str, Any]]:
    """Recompute expected outputs from bundled inputs."""
    default_action = policy["default_action"]

    def normalize(v: str) -> str:
        return default_action if v == "default" else v

    base_normalized = {fid: normalize(p[0]) for fid, p in base_flow_pairs.items()}
    base_status_by_id = {rid: entry["status"] for rid, entry in base_analysis_by_id.items()}

    out: list[dict[str, Any]] = []
    for rule in rules:
        rid = rule["id"]
        reduced = [r for r in rules if r["id"] != rid]
        reduced_ordered = _evaluation_order(reduced, policy)
        flows_changed: list[str] = []
        verdict_changes: list[dict[str, str]] = []
        for f in flows:
            v = _evaluate_flow(f, reduced_ordered, policy)
            new_pair = (v["verdict"], v["matched_rule_id"])
            if new_pair != base_flow_pairs[f["id"]]:
                flows_changed.append(f["id"])
            new_norm = normalize(v["verdict"])
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
            new_analysis, _ = _classify_rules(reduced, flows, policy)
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


def _compute_perturbation_graph(
    rules: list[dict[str, Any]],
    deps: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reference impl of perturbation_graph.json: edges A->B iff B in A's
    promoted_rules; nodes with in/out degrees; cycles = SCCs of size > 1
    (sorted ASCII inside each cycle, outer list sorted by lex-smallest member);
    topological_layers = Kahn-style layers of the SCC condensation, with each
    layer flattened to ASCII-sorted rule IDs.
    """
    rule_ids = [r["id"] for r in rules]
    promoted_by = {entry["id"]: list(entry["promoted_rules"]) for entry in deps}

    edges: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for src, targets in promoted_by.items():
        for tgt in targets:
            if src == tgt or (src, tgt) in seen:
                continue
            seen.add((src, tgt))
            edges.append((src, tgt))
    edges.sort()

    out_n: dict[str, set[str]] = {rid: set() for rid in rule_ids}
    in_n: dict[str, set[str]] = {rid: set() for rid in rule_ids}
    for s, t in edges:
        if s in out_n:
            out_n[s].add(t)
        if t in in_n:
            in_n[t].add(s)

    nodes = [
        {"id": rid, "in_degree": len(in_n[rid]), "out_degree": len(out_n[rid])}
        for rid in sorted(rule_ids)
    ]

    index_of = {rid: i for i, rid in enumerate(rule_ids)}
    indices = [-1] * len(rule_ids)
    lowlink = [0] * len(rule_ids)
    on_stack = [False] * len(rule_ids)
    stack: list[int] = []
    idx_counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(start: int) -> None:
        call_stack: list[tuple[int, int]] = [(start, 0)]
        while call_stack:
            v, child_pos = call_stack[-1]
            if child_pos == 0:
                indices[v] = idx_counter[0]
                lowlink[v] = idx_counter[0]
                idx_counter[0] += 1
                stack.append(v)
                on_stack[v] = True
            children = sorted(out_n[rule_ids[v]])
            if child_pos < len(children):
                w = index_of[children[child_pos]]
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
                    pv = call_stack[-1][0]
                    lowlink[pv] = min(lowlink[pv], lowlink[v])

    for v in range(len(rule_ids)):
        if indices[v] == -1:
            strongconnect(v)

    cycles = sorted([sorted(s) for s in sccs if len(s) > 1], key=lambda c: c[0])

    scc_of: dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for rid in scc:
            scc_of[rid] = i
    cond_out: dict[int, set[int]] = {i: set() for i in range(len(sccs))}
    cond_in: dict[int, int] = {i: 0 for i in range(len(sccs))}
    for s, t in edges:
        si, ti = scc_of[s], scc_of[t]
        if si == ti:
            continue
        if ti not in cond_out[si]:
            cond_out[si].add(ti)
            cond_in[ti] += 1

    layers: list[list[str]] = []
    placed: set[int] = set()
    indeg = dict(cond_in)
    while len(placed) < len(sccs):
        current = sorted(
            [i for i in range(len(sccs)) if i not in placed and indeg[i] == 0],
            key=lambda i: sorted(sccs[i])[0],
        )
        if not current:
            break
        ids: list[str] = []
        for i in current:
            ids.extend(sccs[i])
            placed.add(i)
        layers.append(sorted(ids))
        for i in current:
            for j in cond_out[i]:
                indeg[j] -= 1

    return {
        "cycles": cycles,
        "edges": [{"from": a, "to": b} for a, b in edges],
        "nodes": nodes,
        "topological_layers": layers,
    }


def reference_outputs() -> dict[str, Any]:
    """Compute the six expected output documents from /app/data inputs."""
    rules = list(load_json(RULES_PATH)["rules"])
    flows = list(load_json(FLOWS_PATH)["flows"])
    policy = load_json(POLICY_PATH)

    ordered = _evaluation_order(rules, policy)
    flow_verdicts = sorted(
        (_evaluate_flow(f, ordered, policy) for f in flows),
        key=lambda v: v["id"],
    )

    analysis, by_id = _classify_rules(rules, flows, policy)

    counts = {s: 0 for s in VALID_STATUSES}
    for entry in analysis:
        counts[entry["status"]] += 1
    default_uses = sum(1 for v in flow_verdicts if v["verdict"] == "default")
    warnings = _compute_escalation_warnings(by_id, rules, policy)
    summary = {
        "default_action_uses": default_uses,
        "effective": counts["effective"],
        "escalation_warnings": warnings,
        "redundant": counts["redundant"],
        "shadowed": counts["shadowed"],
        "total_rules": len(rules),
        "unreachable": counts["unreachable"],
    }

    minimal_ids, removed_ids = _compute_equivalence_classes(rules, flows, policy)

    base_flow_pairs = {
        v["id"]: (v["verdict"], v["matched_rule_id"]) for v in flow_verdicts
    }
    deps = _compute_rule_dependencies(rules, flows, policy, by_id, base_flow_pairs)
    perturbation_graph = _compute_perturbation_graph(rules, deps)

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
        # auxiliary handles for property tests
        "_rules": rules,
        "_flows": flows,
        "_policy": policy,
        "_ordered_rule_ids": [r["id"] for r in ordered],
        "_base_flow_pairs": base_flow_pairs,
        "_base_status_by_id": {rid: entry["status"] for rid, entry in by_id.items()},
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_outputs_exist_and_inputs_unchanged() -> None:
    """Inputs are intact and all six outputs exist as parseable JSON.

    Stresses:
      - data files at /app/data/* unmodified by the agent (sha256 pinned)
      - all six required outputs present at /app/output/*
      - each output file is parseable JSON with non-empty payload
    """
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )
    for path in (VERDICTS_PATH, ANALYSIS_PATH, SUMMARY_PATH, EQUIV_PATH, DEPS_PATH, GRAPH_PATH):
        assert path.exists(), f"output missing: {path}"
        assert path.stat().st_size > 0, f"output empty: {path}"
        load_json(path)


def test_outputs_strict_json_formatting() -> None:
    """All outputs are 2-space, sort-keys, ASCII-only, trailing-newline JSON.

    Stresses:
      - exactly two spaces of indent at every depth
      - sort_keys=True at every depth (lexicographic ASCII)
      - ensure_ascii=True (no raw non-ASCII bytes)
      - trailing newline at end of file
    """
    for path in (VERDICTS_PATH, ANALYSIS_PATH, SUMMARY_PATH, EQUIV_PATH, DEPS_PATH, GRAPH_PATH):
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def test_flow_verdicts_match_reference(expected_outputs: dict[str, Any]) -> None:
    """flow_verdicts.json must equal the live-computed reference.

    The reference implementation in this file recomputes verdicts from
    /app/data; this means a hardcoded JSON dump cannot pass — the agent
    must actually parse inputs and apply matching semantics.

    Stresses:
      - priority_then_id evaluation order with priority-tied rules broken by id
      - first-match-wins evaluation with full evaluated_rule_ids prefix capture
      - port-range matching with off-by-one boundary (src_port 1023 vs 1024)
      - ICMP flows ignore src_ports/dst_ports specifications on rules
      - directionality enforcement (ingress/egress separation)
      - non-canonical CIDR normalization (10.0.20.5/24 -> 10.0.20.0/24)
      - default verdict tag emitted only when no rule matches
      - flows entries sorted ASCII ascending by id
    """
    actual = load_json(VERDICTS_PATH)
    assert actual == expected_outputs["flow_verdicts"]


def test_rule_analysis_match_reference(expected_outputs: dict[str, Any]) -> None:
    """rule_analysis.json must equal the live-computed reference.

    Stresses:
      - per-rule status priority: unreachable > shadowed > redundant > effective
      - composite shadow detection (multi-rule cover)
      - simple shadow detection (single-rule cover)
      - redundancy detection with default-action normalization
      - lex-smallest minimum-cardinality cover for shadowed_by
      - matched_flows captures predicate-only matches (priority ignored)
      - matched_flows and rules entries sorted ASCII ascending
      - shadowed_by is empty for non-shadowed rules
    """
    actual = load_json(ANALYSIS_PATH)
    assert actual == expected_outputs["rule_analysis"]


def test_policy_summary_match_reference(expected_outputs: dict[str, Any]) -> None:
    """policy_summary.json must equal the live-computed reference.

    Stresses:
      - status counts: total_rules / effective / shadowed / redundant / unreachable
      - default_action_uses: number of flows that hit no rule
      - escalation_warnings: only for non-redundant non-unreachable deny rules
        with earlier-allow overlap on matched_flows
      - escalation_warnings sorted by (rule_id, earlier_rule_id) ASCII ascending
      - redundant rules generate no warnings even if they overlap with allows
    """
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["policy_summary"]


def test_equivalence_classes_match_reference(expected_outputs: dict[str, Any]) -> None:
    """equivalence_classes.json must equal the live-computed reference.

    Stresses:
      - greedy elimination iterating in id ASCII ascending order
      - restart on each successful removal (fixpoint loop)
      - invariance check uses (verdict, matched_rule_id) pair (NOT just verdict)
      - minimal_rule_ids and removed_rule_ids both sorted ASCII ascending
      - verdict_invariant field always present and true
    """
    actual = load_json(EQUIV_PATH)
    assert actual == expected_outputs["equivalence_classes"]


def test_coverage_percent_format() -> None:
    """coverage_percent strings must be N+.NN strings in rule_analysis.

    Stresses:
      - rendered as decimal string with exactly two fractional digits
      - banker's rounding (Decimal ROUND_HALF_EVEN) enforced via str-equality
        with the reference, which uses Decimal.quantize(0.01, ROUND_HALF_EVEN)
      - 0.00 emitted for unreachable rules and when len(flows) == 0
    """
    actual = load_json(ANALYSIS_PATH)
    assert "rules" in actual
    for entry in actual["rules"]:
        val = entry.get("coverage_percent")
        rid = entry.get("id")
        assert isinstance(val, str), f"coverage_percent for {rid} not a string: {val!r}"
        assert COVERAGE_RE.match(val), (
            f"coverage_percent for {rid} not in N+.NN form: {val!r}"
        )


def test_evaluated_rule_ids_is_contiguous_prefix(expected_outputs: dict[str, Any]) -> None:
    """evaluated_rule_ids must be a contiguous prefix of the evaluation order.

    The prefix length must match the position of matched_rule_id (when set);
    if verdict is 'default', evaluated_rule_ids must equal the entire order.
    Validates that evaluation is single-pass first-match-wins, and that the
    agent didn't skip rules or evaluate them out of order.
    """
    ordered_ids: list[str] = expected_outputs["_ordered_rule_ids"]
    actual = load_json(VERDICTS_PATH)
    for entry in actual["flows"]:
        evaluated = entry["evaluated_rule_ids"]
        matched = entry["matched_rule_id"]
        assert evaluated == ordered_ids[: len(evaluated)], (
            f"flow {entry['id']}: evaluated_rule_ids is not a prefix of evaluation order"
        )
        if matched is None:
            assert entry["verdict"] == "default"
            assert evaluated == ordered_ids, (
                f"flow {entry['id']}: default verdict must traverse all rules"
            )
        else:
            assert evaluated[-1] == matched, (
                f"flow {entry['id']}: evaluated_rule_ids must end at matched_rule_id"
            )


def test_status_counts_match_summary() -> None:
    """policy_summary status counts must match rule_analysis classifications."""
    analysis = load_json(ANALYSIS_PATH)
    summary = load_json(SUMMARY_PATH)
    rules = analysis["rules"]
    assert summary["total_rules"] == len(rules)
    counts = {s: 0 for s in VALID_STATUSES}
    for entry in rules:
        status = entry["status"]
        assert status in VALID_STATUSES, f"unknown status: {status}"
        counts[status] += 1
    for s in VALID_STATUSES:
        assert summary[s] == counts[s], (
            f"summary[{s}]={summary[s]} but rule_analysis has {counts[s]}"
        )


def test_minimal_rule_set_preserves_invariant(expected_outputs: dict[str, Any]) -> None:
    """The minimal rule set in equivalence_classes.json must preserve the
    (verdict, matched_rule_id) pair for every flow when re-evaluated.

    This independently verifies the equivalence-class greedy minimisation
    against the spec's invariant rather than only checking equality to a
    snapshot. It guards against an agent emitting a plausible-looking
    minimal_rule_ids that does not actually preserve verdicts.
    """
    rules: list[dict[str, Any]] = expected_outputs["_rules"]
    flows: list[dict[str, Any]] = expected_outputs["_flows"]
    policy: dict[str, Any] = expected_outputs["_policy"]
    equiv = load_json(EQUIV_PATH)
    minimal_ids = set(equiv["minimal_rule_ids"])
    removed_ids = set(equiv["removed_rule_ids"])

    all_ids = {r["id"] for r in rules}
    assert minimal_ids | removed_ids == all_ids, (
        "minimal_rule_ids and removed_rule_ids must partition all rule ids"
    )
    assert minimal_ids.isdisjoint(removed_ids), (
        "minimal_rule_ids and removed_rule_ids must be disjoint"
    )

    base_ordered = _evaluation_order(rules, policy)
    minimal_ordered = _evaluation_order(
        [r for r in rules if r["id"] in minimal_ids], policy
    )
    for f in flows:
        base = _evaluate_flow(f, base_ordered, policy)
        red = _evaluate_flow(f, minimal_ordered, policy)
        assert (red["verdict"], red["matched_rule_id"]) == (
            base["verdict"],
            base["matched_rule_id"],
        ), (
            f"flow {f['id']}: minimal rule set changes (verdict, matched_rule_id) "
            f"from ({base['verdict']!r}, {base['matched_rule_id']!r}) "
            f"to ({red['verdict']!r}, {red['matched_rule_id']!r})"
        )

    assert equiv["verdict_invariant"] is True


# ---------------------------------------------------------------------------
# rule_dependencies.json — full one-rule-removed perturbation analysis. This
# is the hardest output: for every rule R the agent must build S\{R}, recompute
# every flow's (verdict, matched_rule_id), and *re-classify every other rule*
# under S\{R}. Solvers that skip this output, or that confuse pair-changes
# with verdict-flips, or that put R itself in its own promoted_rules, will
# diverge from the reference and fail one or more of the tests below.
# ---------------------------------------------------------------------------


VALID_CRITICALITIES = ("critical", "important", "minor", "none")
RULE_DEPENDENCY_REQUIRED_KEYS = frozenset(
    {"criticality", "flows_changed", "id", "promoted_rules", "verdict_changes"}
)


def test_rule_dependencies_match_reference(expected_outputs: dict[str, Any]) -> None:
    """rule_dependencies.json must equal the live-computed reference exactly.

    Stresses:
      - per-rule (verdict, matched_rule_id) recomputation under S\\{R}
      - re-classification of every other rule under S\\{R} (full pipeline)
      - normalized verdict comparison (default -> policy.default_action)
      - flows_changed sorted ASCII; verdict_changes sorted by flow_id
      - promoted_rules excludes R itself; sorted ASCII
      - criticality priority: critical > important > minor > none
    """
    actual = load_json(DEPS_PATH)
    assert actual == expected_outputs["rule_dependencies"]


def test_rule_dependencies_top_level_shape() -> None:
    """rule_dependencies.json must be {"rules": [...]} with one entry per rule
    in the input file, sorted ASCII ascending by id, and each entry must have
    exactly the five required keys (no extras, no omissions).
    """
    actual = load_json(DEPS_PATH)
    assert isinstance(actual, dict)
    assert set(actual.keys()) == {"rules"}, (
        f"top-level keys must be exactly {{'rules'}}; got {set(actual.keys())!r}"
    )
    rules = actual["rules"]
    assert isinstance(rules, list)
    raw_input_rules = load_json(RULES_PATH)["rules"]
    assert len(rules) == len(raw_input_rules), (
        f"rule_dependencies.rules must have one entry per input rule "
        f"({len(raw_input_rules)}); got {len(rules)}"
    )
    ids = [entry["id"] for entry in rules]
    assert ids == sorted(ids), (
        f"rule_dependencies.rules must be sorted ASCII ascending by id; got {ids}"
    )
    for entry in rules:
        assert set(entry.keys()) == RULE_DEPENDENCY_REQUIRED_KEYS, (
            f"rule_dependencies entry for {entry.get('id')!r} must have exactly "
            f"keys {sorted(RULE_DEPENDENCY_REQUIRED_KEYS)}; got {sorted(entry.keys())}"
        )


def test_rule_dependencies_criticality_values_and_distribution(
    expected_outputs: dict[str, Any],
) -> None:
    """Each entry's criticality must be one of {critical, important, minor, none}
    AND must agree with the deterministic priority ladder (critical if
    verdict_changes non-empty; else important if flows_changed non-empty; else
    minor if promoted_rules non-empty; else none).

    The per-criticality counts must also exactly match the reference. This
    catches an agent that produces every entry as "none" or that mislabels the
    priority order (e.g. promoted before flows_changed).
    """
    actual = load_json(DEPS_PATH)
    expected = expected_outputs["rule_dependencies"]

    counts: dict[str, int] = {c: 0 for c in VALID_CRITICALITIES}
    for entry in actual["rules"]:
        crit = entry["criticality"]
        assert crit in VALID_CRITICALITIES, (
            f"rule {entry['id']!r}: invalid criticality {crit!r}"
        )
        counts[crit] += 1

        if entry["verdict_changes"]:
            assert crit == "critical", (
                f"rule {entry['id']!r}: verdict_changes non-empty but criticality "
                f"is {crit!r}, must be 'critical'"
            )
        elif entry["flows_changed"]:
            assert crit == "important", (
                f"rule {entry['id']!r}: flows_changed non-empty (and no "
                f"verdict_changes) but criticality is {crit!r}, must be "
                f"'important'"
            )
        elif entry["promoted_rules"]:
            assert crit == "minor", (
                f"rule {entry['id']!r}: only promoted_rules is non-empty but "
                f"criticality is {crit!r}, must be 'minor'"
            )
        else:
            assert crit == "none", (
                f"rule {entry['id']!r}: all three lists empty but criticality "
                f"is {crit!r}, must be 'none'"
            )

    expected_counts: dict[str, int] = {c: 0 for c in VALID_CRITICALITIES}
    for entry in expected["rules"]:
        expected_counts[entry["criticality"]] += 1
    assert counts == expected_counts, (
        f"criticality distribution {counts} does not match reference "
        f"{expected_counts}"
    )


def test_rule_dependencies_flows_changed_is_superset_of_verdict_changes(
    expected_outputs: dict[str, Any],
) -> None:
    """For every rule, the set of flow_ids in verdict_changes MUST be a subset
    of flows_changed.

    Reasoning: a normalized-verdict flip can only happen when the
    (verdict, matched_rule_id) pair also changed (the spec says verdict_changes
    flow ids must already be in flows_changed). The converse is not true — a
    flow whose pair changed but whose normalized verdict stayed the same
    belongs in flows_changed only.
    """
    actual = load_json(DEPS_PATH)
    for entry in actual["rules"]:
        flows_changed_set = set(entry["flows_changed"])
        verdict_change_ids = {vc["flow_id"] for vc in entry["verdict_changes"]}
        leak = verdict_change_ids - flows_changed_set
        assert not leak, (
            f"rule {entry['id']!r}: verdict_changes references flows {sorted(leak)} "
            f"that are NOT in flows_changed -- a normalized verdict flip implies "
            f"the (verdict, matched_rule_id) pair also changed"
        )


def test_rule_dependencies_promoted_rules_self_exclusion_and_baseline(
    expected_outputs: dict[str, Any],
) -> None:
    """A rule R must NEVER appear in its own promoted_rules. Additionally,
    promoted_rules may only contain rule ids whose BASELINE status was
    unreachable, shadowed, or redundant -- never effective.
    """
    actual = load_json(DEPS_PATH)
    base_status_by_id: dict[str, str] = expected_outputs["_base_status_by_id"]
    all_input_ids: set[str] = {r["id"] for r in expected_outputs["_rules"]}
    for entry in actual["rules"]:
        rid = entry["id"]
        promoted = entry["promoted_rules"]
        assert rid not in promoted, (
            f"rule {rid!r}: must not appear in its own promoted_rules; got {promoted}"
        )
        assert promoted == sorted(promoted), (
            f"rule {rid!r}: promoted_rules must be ASCII-sorted; got {promoted}"
        )
        for qid in promoted:
            assert qid in all_input_ids, (
                f"rule {rid!r}: promoted_rules contains unknown id {qid!r}"
            )
            base = base_status_by_id.get(qid)
            assert base in ("unreachable", "shadowed", "redundant"), (
                f"rule {rid!r}: promoted id {qid!r} had baseline status {base!r}; "
                f"only non-effective baseline statuses are eligible for promotion"
            )


def test_rule_dependencies_verdict_changes_use_normalized_default(
    expected_outputs: dict[str, Any],
) -> None:
    """from_verdict and to_verdict in verdict_changes must always be the
    NORMALIZED verdict (the literal "default" must never appear; it must be
    substituted by policy.default_action). Each entry must also have exactly
    the three keys flow_id, from_verdict, to_verdict.
    """
    actual = load_json(DEPS_PATH)
    default_action: str = expected_outputs["_policy"]["default_action"]
    allowed_verdicts = {"allow", "deny"}
    assert default_action in allowed_verdicts
    for entry in actual["rules"]:
        for vc in entry["verdict_changes"]:
            assert set(vc.keys()) == {"flow_id", "from_verdict", "to_verdict"}, (
                f"rule {entry['id']!r}: verdict_changes entry must have exactly "
                f"{{'flow_id', 'from_verdict', 'to_verdict'}}; got {set(vc.keys())}"
            )
            for k in ("from_verdict", "to_verdict"):
                assert vc[k] != "default", (
                    f"rule {entry['id']!r}: verdict_changes[{k}] must be "
                    f"normalized; raw 'default' is forbidden (must be "
                    f"{default_action!r})"
                )
                assert vc[k] in allowed_verdicts, (
                    f"rule {entry['id']!r}: verdict_changes[{k}] must be in "
                    f"{allowed_verdicts}; got {vc[k]!r}"
                )
            assert vc["from_verdict"] != vc["to_verdict"], (
                f"rule {entry['id']!r}: verdict_changes for flow {vc['flow_id']!r} "
                f"records identical from/to {vc['from_verdict']!r} -- not a flip"
            )


def test_rule_dependencies_lists_are_sorted(expected_outputs: dict[str, Any]) -> None:
    """flows_changed must be ASCII-sorted; verdict_changes must be sorted by
    flow_id ASCII ascending.
    """
    actual = load_json(DEPS_PATH)
    for entry in actual["rules"]:
        fc = entry["flows_changed"]
        assert fc == sorted(fc), (
            f"rule {entry['id']!r}: flows_changed not ASCII-sorted; got {fc}"
        )
        vc_ids = [vc["flow_id"] for vc in entry["verdict_changes"]]
        assert vc_ids == sorted(vc_ids), (
            f"rule {entry['id']!r}: verdict_changes not sorted by flow_id; got {vc_ids}"
        )


def test_rule_dependencies_reproduces_perturbation_pairs(
    expected_outputs: dict[str, Any],
) -> None:
    """Independently re-derive the (verdict, matched_rule_id) pair for each
    flow under S\\{R} and confirm the agent's flows_changed set matches the
    diff against the baseline pairs.

    This is a behavioral cross-check that doesn't rely on the reference fixture
    -- it reproduces the perturbation directly from the agent's input rules
    and the agent's claimed flows_changed list.
    """
    actual = load_json(DEPS_PATH)
    rules: list[dict[str, Any]] = expected_outputs["_rules"]
    flows: list[dict[str, Any]] = expected_outputs["_flows"]
    policy: dict[str, Any] = expected_outputs["_policy"]
    base_pairs: dict[str, tuple[str, str | None]] = expected_outputs["_base_flow_pairs"]

    for entry in actual["rules"]:
        rid = entry["id"]
        reduced = [r for r in rules if r["id"] != rid]
        reduced_ordered = _evaluation_order(reduced, policy)
        recomputed: list[str] = []
        for f in flows:
            v = _evaluate_flow(f, reduced_ordered, policy)
            new_pair = (v["verdict"], v["matched_rule_id"])
            if new_pair != base_pairs[f["id"]]:
                recomputed.append(f["id"])
        recomputed.sort()
        assert entry["flows_changed"] == recomputed, (
            f"rule {rid!r}: flows_changed {entry['flows_changed']} does not "
            f"match independently-recomputed perturbation set {recomputed}"
        )


def test_rule_dependencies_at_least_one_critical_or_important(
    expected_outputs: dict[str, Any],
) -> None:
    """Sanity check on the dataset: at least one rule in the input must be
    classified as 'critical' or 'important' (i.e. removing it changes at least
    one flow's pair). A dataset where every rule is 'none' would mean the
    perturbation analysis is trivially the empty function.
    """
    expected = expected_outputs["rule_dependencies"]
    crits = {entry["criticality"] for entry in expected["rules"]}
    assert crits & {"critical", "important"}, (
        f"dataset invariant: at least one rule must be 'critical' or "
        f"'important'; got criticalities {crits}"
    )


def test_rule_dependencies_promoted_rules_match_independent_reclassification(
    expected_outputs: dict[str, Any],
) -> None:
    """Independently re-classify every other rule under S\\{R} (without using
    the reference fixture) and verify the agent's promoted_rules exactly
    matches the set of rules whose status switched to 'effective' from a
    non-effective baseline.

    This test catches solvers that:
      - copy 'shadowed_by' or 'matched_flows' from rule_analysis.json instead
        of recomputing classification under S\\{R},
      - put R itself in its own promoted_rules,
      - include rules whose baseline was already 'effective' (forbidden), or
      - skip the re-classification step entirely and emit empty lists.
    """
    actual = load_json(DEPS_PATH)
    rules: list[dict[str, Any]] = expected_outputs["_rules"]
    flows: list[dict[str, Any]] = expected_outputs["_flows"]
    policy: dict[str, Any] = expected_outputs["_policy"]
    base_status: dict[str, str] = expected_outputs["_base_status_by_id"]

    for entry in actual["rules"]:
        rid = entry["id"]
        reduced = [r for r in rules if r["id"] != rid]
        if not reduced:
            assert entry["promoted_rules"] == [], (
                f"rule {rid!r}: S\\{{{rid}}} is empty so promoted_rules must be []"
            )
            continue
        new_analysis, _ = _classify_rules(reduced, flows, policy)
        recomputed = sorted(
            e["id"]
            for e in new_analysis
            if e["id"] != rid
            and e["status"] == "effective"
            and base_status.get(e["id"]) != "effective"
        )
        assert entry["promoted_rules"] == recomputed, (
            f"rule {rid!r}: promoted_rules {entry['promoted_rules']} does not "
            f"match independently-recomputed promotion set {recomputed}"
        )


# ---------------------------------------------------------------------------
# perturbation_graph.json — directed graph induced by promoted_rules with full
# SCC / topological-layer / cycle decomposition. The hardest output to get
# right because it requires Tarjan/Kosaraju + condensation + Kahn-style
# layering, all with deterministic ASCII ordering. Solvers that skip this
# output, or that confuse out-degree with in-degree, or that put cycle members
# across multiple layers (instead of in the same condensation-DAG layer), or
# that emit layer 0 as topological order *of the graph itself* instead of the
# *condensation DAG*, will fail at least one of the tests below.
# ---------------------------------------------------------------------------


PG_REQUIRED_TOP_KEYS = frozenset({"cycles", "edges", "nodes", "topological_layers"})
PG_NODE_REQUIRED_KEYS = frozenset({"id", "in_degree", "out_degree"})
PG_EDGE_REQUIRED_KEYS = frozenset({"from", "to"})


def test_perturbation_graph_match_reference(expected_outputs: dict[str, Any]) -> None:
    """perturbation_graph.json must equal the live-computed reference exactly.

    Stresses:
      - edges induced ONLY by promoted_rules (not flows_changed or
        verdict_changes), deduplicated as a set, sorted by (from, to)
      - in_degree / out_degree computed from the deduplicated edge set
      - SCC decomposition with cycles >= 2 surfaced in 'cycles', singletons
        absorbed into their own condensation node
      - Kahn-style topological_layers of the *condensation* DAG (not the raw
        graph): 2-element SCCs land entirely in one layer, not split across
        layers
      - all lists sorted ASCII ascending in their canonical positions
    """
    actual = load_json(GRAPH_PATH)
    assert actual == expected_outputs["perturbation_graph"]


def test_perturbation_graph_top_level_shape() -> None:
    """Top-level keys must be exactly {cycles, edges, nodes, topological_layers}.
    No extras, no omissions, no different casings.
    """
    actual = load_json(GRAPH_PATH)
    assert isinstance(actual, dict)
    assert set(actual.keys()) == PG_REQUIRED_TOP_KEYS, (
        f"top-level keys must be exactly {sorted(PG_REQUIRED_TOP_KEYS)}; "
        f"got {sorted(actual.keys())}"
    )
    assert isinstance(actual["cycles"], list)
    assert isinstance(actual["edges"], list)
    assert isinstance(actual["nodes"], list)
    assert isinstance(actual["topological_layers"], list)


def test_perturbation_graph_nodes_cover_all_input_rules(
    expected_outputs: dict[str, Any],
) -> None:
    """nodes must contain ONE entry per input rule (no duplicates, no missing
    rules, no extra synthetic nodes), sorted ASCII ascending by id, with the
    required key set on every entry.
    """
    actual = load_json(GRAPH_PATH)
    expected_ids = sorted(r["id"] for r in expected_outputs["_rules"])
    actual_ids = [n["id"] for n in actual["nodes"]]
    assert actual_ids == expected_ids, (
        f"nodes ids must be every input rule id, sorted ASCII ascending. "
        f"expected {expected_ids}, got {actual_ids}"
    )
    for n in actual["nodes"]:
        assert set(n.keys()) == PG_NODE_REQUIRED_KEYS, (
            f"node {n.get('id')!r}: keys must be exactly "
            f"{sorted(PG_NODE_REQUIRED_KEYS)}; got {sorted(n.keys())}"
        )
        assert isinstance(n["in_degree"], int) and n["in_degree"] >= 0
        assert isinstance(n["out_degree"], int) and n["out_degree"] >= 0


def test_perturbation_graph_edges_match_promoted_rules(
    expected_outputs: dict[str, Any],
) -> None:
    """The edge set must equal exactly {(R, Q) : Q in R.promoted_rules in
    rule_dependencies.json}, deduplicated and sorted by (from, to). No edges
    should leak in from flows_changed or verdict_changes.
    """
    actual = load_json(GRAPH_PATH)
    deps_doc = expected_outputs["rule_dependencies"]
    expected_edges = sorted(
        {(e["id"], q) for e in deps_doc["rules"] for q in e["promoted_rules"]}
    )
    actual_edges = [(e["from"], e["to"]) for e in actual["edges"]]
    assert actual_edges == expected_edges, (
        f"edges must equal the promoted_rules induced edge set, sorted by "
        f"(from, to). expected {expected_edges}, got {actual_edges}"
    )
    for e in actual["edges"]:
        assert set(e.keys()) == PG_EDGE_REQUIRED_KEYS, (
            f"edge {e!r}: keys must be exactly {sorted(PG_EDGE_REQUIRED_KEYS)}; "
            f"got {sorted(e.keys())}"
        )
        assert e["from"] != e["to"], (
            f"edge {e!r}: self-loops are forbidden by the spec"
        )


def test_perturbation_graph_degrees_consistent_with_edges() -> None:
    """For every node, in_degree must equal the number of edges with
    to == node.id and out_degree must equal the number of edges with
    from == node.id. Degrees and edges must be self-consistent.
    """
    actual = load_json(GRAPH_PATH)
    in_count: dict[str, int] = {}
    out_count: dict[str, int] = {}
    for e in actual["edges"]:
        in_count[e["to"]] = in_count.get(e["to"], 0) + 1
        out_count[e["from"]] = out_count.get(e["from"], 0) + 1
    for n in actual["nodes"]:
        rid = n["id"]
        assert n["in_degree"] == in_count.get(rid, 0), (
            f"node {rid!r}: in_degree {n['in_degree']} != edge count "
            f"{in_count.get(rid, 0)} ending at {rid}"
        )
        assert n["out_degree"] == out_count.get(rid, 0), (
            f"node {rid!r}: out_degree {n['out_degree']} != edge count "
            f"{out_count.get(rid, 0)} starting at {rid}"
        )


def test_perturbation_graph_topological_layers_partition_all_nodes(
    expected_outputs: dict[str, Any],
) -> None:
    """topological_layers must partition the full vertex set: every input
    rule appears in exactly one layer, and the order of layers must be
    Kahn-style (every node's predecessors -- across condensation edges --
    appear in earlier layers).
    """
    actual = load_json(GRAPH_PATH)
    all_rule_ids = {r["id"] for r in expected_outputs["_rules"]}
    seen: set[str] = set()
    for layer in actual["topological_layers"]:
        layer_set = set(layer)
        assert len(layer_set) == len(layer), (
            f"layer {layer} contains duplicate rule ids"
        )
        assert layer == sorted(layer), (
            f"layer {layer} not ASCII-sorted"
        )
        overlap = seen & layer_set
        assert not overlap, (
            f"layer {layer} repeats ids {sorted(overlap)} from earlier layers"
        )
        seen.update(layer_set)
    assert seen == all_rule_ids, (
        f"topological_layers must cover every input rule; missing "
        f"{sorted(all_rule_ids - seen)}, extras {sorted(seen - all_rule_ids)}"
    )

    layer_index: dict[str, int] = {}
    for i, layer in enumerate(actual["topological_layers"]):
        for rid in layer:
            layer_index[rid] = i
    cycles_pairs: set[tuple[str, str]] = set()
    for cycle in actual["cycles"]:
        for a in cycle:
            for b in cycle:
                if a != b:
                    cycles_pairs.add((a, b))
    for e in actual["edges"]:
        if (e["from"], e["to"]) in cycles_pairs:
            assert layer_index[e["from"]] == layer_index[e["to"]], (
                f"edge {e['from']}->{e['to']} is inside a cycle; both endpoints "
                f"must be in the same condensation layer"
            )
        else:
            assert layer_index[e["from"]] < layer_index[e["to"]], (
                f"non-cycle edge {e['from']}->{e['to']} must go from an earlier "
                f"layer to a later one (Kahn order); got "
                f"{layer_index[e['from']]} -> {layer_index[e['to']]}"
            )


def test_perturbation_graph_cycles_are_strongly_connected_components(
    expected_outputs: dict[str, Any],
) -> None:
    """Each entry in cycles must be a true SCC of size >= 2: every member
    must be reachable from every other member via directed edges. The list
    must be sorted ASCII inside each cycle, and the outer list sorted by
    each cycle's lex-smallest member.
    """
    actual = load_json(GRAPH_PATH)
    cycles = actual["cycles"]
    out_n: dict[str, set[str]] = {n["id"]: set() for n in actual["nodes"]}
    for e in actual["edges"]:
        out_n.setdefault(e["from"], set()).add(e["to"])

    def reachable(src: str, dst: str) -> bool:
        if src not in out_n:
            return False
        seen = {src}
        frontier = [src]
        while frontier:
            v = frontier.pop()
            for w in out_n.get(v, ()):
                if w == dst:
                    return True
                if w not in seen:
                    seen.add(w)
                    frontier.append(w)
        return False

    seen_members: set[str] = set()
    last_first = ""
    for cycle in cycles:
        assert isinstance(cycle, list)
        assert len(cycle) >= 2, (
            f"cycle {cycle} must have size >= 2 (singletons are not cycles)"
        )
        assert cycle == sorted(cycle), (
            f"cycle {cycle} not ASCII-sorted"
        )
        assert cycle[0] > last_first, (
            f"outer cycles list must be sorted by lex-smallest member ascending; "
            f"got {cycle[0]} after {last_first}"
        )
        last_first = cycle[0]
        for a in cycle:
            assert a not in seen_members, (
                f"rule {a!r} appears in multiple cycles -- SCCs must be disjoint"
            )
            seen_members.add(a)
        for a in cycle:
            for b in cycle:
                if a == b:
                    continue
                assert reachable(a, b), (
                    f"cycle {cycle}: {b!r} is not reachable from {a!r}, so "
                    f"this is not actually a strongly-connected component"
                )


def test_rule_analysis_shadowed_by_nonempty_iff_shadowed() -> None:
    """The instruction requires that for each rule_analysis entry,
    shadowed_by is non-empty if and only if status == 'shadowed'. (For
    every non-shadowed rule, shadowed_by must be the empty list; for every
    shadowed rule, shadowed_by must contain at least one rule id.)
    """
    actual = load_json(ANALYSIS_PATH)
    for entry in actual["rules"]:
        rid = entry["id"]
        status = entry["status"]
        sb = entry.get("shadowed_by", [])
        if status == "shadowed":
            assert isinstance(sb, list) and len(sb) > 0, (
                f"rule {rid!r}: status is 'shadowed' but shadowed_by is empty; "
                f"the instruction requires a non-empty cover set"
            )
        else:
            assert sb == [], (
                f"rule {rid!r}: status is {status!r} (not 'shadowed') but "
                f"shadowed_by is {sb!r}; only shadowed rules may have a "
                f"non-empty shadowed_by"
            )


def test_perturbation_graph_no_self_loops_and_dataset_has_at_least_one_edge(
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level invariant: the input must induce at least one edge in
    the perturbation graph (otherwise the perturbation analysis produces no
    cascades and this output reduces to a trivial isolated-vertex graph).
    Also assert no self-loops and no duplicate edges.
    """
    actual = load_json(GRAPH_PATH)
    pairs = [(e["from"], e["to"]) for e in actual["edges"]]
    assert len(pairs) > 0, (
        "dataset invariant: perturbation graph must have at least one edge "
        "(at least one rule must promote another rule on removal)"
    )
    assert len(set(pairs)) == len(pairs), (
        f"duplicate edges detected; edges must be deduplicated: {pairs}"
    )
    for s, t in pairs:
        assert s != t, f"self-loop {s}->{t} forbidden by spec"
