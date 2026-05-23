from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
import re

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')


def _load_diag_codes_from_docs(docs_path: Path) -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | E_REGION_NOT_FOUND   | error   | ...
    The single source of truth for codes is the docs, not this test file.
    """
    text = docs_path.read_text(encoding="utf-8")
    codes: set[str] = set()
    severity: dict[str, str] = {}
    pat = re.compile(
        r"^\s*\|\s*`?(?P<code>[A-Z][A-Z0-9_]+)`?\s*\|\s*"
        r"(?P<severity>error|warning|note)\s*\|"
    )
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            codes.add(m.group("code"))
            severity[m.group("code")] = m.group("severity")
    if not codes:
        raise RuntimeError(
            f"could not parse any diagnostic codes from {docs_path}; "
            "check the docs format"
        )
    return frozenset(codes), severity


SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}






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
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth
# ---------------------------------------------------------------------------


def _is_compatible(prot_a, owner_a, prot_b, owner_b, mode):
    if mode in ("strict", "prot_and_owner_match"):
        return prot_a == prot_b and owner_a == owner_b
    if mode == "prot_match_only":
        return prot_a == prot_b
    raise ValueError(mode)


def _try_coalesce_pair(regions, lower_id, upper_id, mode):
    lo = regions[lower_id]
    up = regions[upper_id]
    if lo["base"] + lo["size"] != up["base"]:
        return None
    if not _is_compatible(lo["prot"], lo["owner"], up["prot"], up["owner"], mode):
        return None
    kept_id = min(lower_id, upper_id)
    dropped_id = max(lower_id, upper_id)
    new_base = lo["base"]
    new_size = lo["size"] + up["size"]
    kept = regions[kept_id]
    kept["base"] = new_base
    kept["size"] = new_size
    kept["prot"] = lo["prot"]
    kept["owner"] = lo["owner"]
    del regions[dropped_id]
    return (kept_id, dropped_id)


def _find_lower_neighbour(regions, r_id):
    target = regions[r_id]
    for other_id, other in regions.items():
        if other_id == r_id:
            continue
        if other["base"] + other["size"] == target["base"]:
            return other_id
    return None


def _find_upper_neighbour(regions, r_id):
    target = regions[r_id]
    end = target["base"] + target["size"]
    for other_id, other in regions.items():
        if other_id == r_id:
            continue
        if other["base"] == end:
            return other_id
    return None


def _find_neighbours_of_freed(regions, freed_base, freed_end):
    lower = upper = None
    for other_id, other in regions.items():
        if other["base"] + other["size"] == freed_base:
            lower = other_id
        if other["base"] == freed_end:
            upper = other_id
    return (lower, upper)


def _ranges_overlap(a_base, a_size, b_base, b_size):
    return not (a_base + a_size <= b_base or b_base + b_size <= a_base)


def _diag(diags, seq, code, region_id):
    diags.setdefault(seq, []).append({
        "code": code,
        "region_id": region_id,
        "severity": DIAG_SEVERITY[code],
    })


def _compute_sccs(nodes, edges):
    out_n: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        if a in out_n:
            out_n[a].append(b)
    for n in out_n:
        out_n[n].sort()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    idx_counter = [0]
    sccs: list[list[str]] = []

    def strongconnect(v):
        call_stack: list[tuple[str, int]] = [(v, 0)]
        while call_stack:
            cur, child_pos = call_stack[-1]
            if child_pos == 0:
                indices[cur] = idx_counter[0]
                lowlink[cur] = idx_counter[0]
                idx_counter[0] += 1
                stack.append(cur)
                on_stack[cur] = True
            children = out_n.get(cur, [])
            if child_pos < len(children):
                w = children[child_pos]
                call_stack[-1] = (cur, child_pos + 1)
                if w not in indices:
                    call_stack.append((w, 0))
                elif on_stack.get(w, False):
                    lowlink[cur] = min(lowlink[cur], indices[w])
            else:
                if lowlink[cur] == indices[cur]:
                    scc: list[str] = []
                    while True:
                        x = stack.pop()
                        on_stack[x] = False
                        scc.append(x)
                        if x == cur:
                            break
                    sccs.append(sorted(scc))
                call_stack.pop()
                if call_stack:
                    pv = call_stack[-1][0]
                    lowlink[pv] = min(lowlink[pv], lowlink[cur])

    for n in nodes:
        if n not in indices:
            strongconnect(n)
    return sorted([sorted(s) for s in sccs if len(s) > 1], key=lambda c: c[0])


def run_simulation(initial_regions, events, policy):
    regions: dict[str, dict[str, Any]] = {r["id"]: dict(r) for r in initial_regions}
    seen_ids: set[str] = {r["id"] for r in initial_regions}
    diagnostics: dict[int, list[dict[str, Any]]] = {}
    coalesce_log: list[dict[str, Any]] = []
    lineage_edges: set[tuple[str, str]] = set()
    counters = {"auto_coalesces": 0, "explicit_merges": 0, "splits": 0,
                "maps_succeeded": 0, "maps_rejected": 0, "unmaps_succeeded": 0}

    def auto_coalesce_after_map(seq, new_id):
        if new_id not in regions:
            return
        lower = _find_lower_neighbour(regions, new_id)
        if lower is not None:
            res = _try_coalesce_pair(regions, lower, new_id, policy["coalesce_mode"])
            if res is not None:
                kept_id, dropped_id = res
                coalesce_log.append({"dropped_id": dropped_id, "kept_id": kept_id,
                                     "seq": seq, "trigger": "map"})
                _diag(diagnostics, seq, "N_AUTO_COALESCED", kept_id)
                counters["auto_coalesces"] += 1
                new_id = kept_id
        if new_id not in regions:
            return
        upper = _find_upper_neighbour(regions, new_id)
        if upper is not None:
            res = _try_coalesce_pair(regions, new_id, upper, policy["coalesce_mode"])
            if res is not None:
                kept_id, dropped_id = res
                coalesce_log.append({"dropped_id": dropped_id, "kept_id": kept_id,
                                     "seq": seq, "trigger": "map"})
                _diag(diagnostics, seq, "N_AUTO_COALESCED", kept_id)
                counters["auto_coalesces"] += 1

    def auto_coalesce_after_unmap(seq, freed_base, freed_end):
        if not policy["auto_coalesce_after_unmap"]:
            return
        lower, upper = _find_neighbours_of_freed(regions, freed_base, freed_end)
        if lower is None or upper is None:
            return
        res = _try_coalesce_pair(regions, lower, upper, policy["coalesce_mode"])
        if res is None:
            return
        kept_id, dropped_id = res
        coalesce_log.append({"dropped_id": dropped_id, "kept_id": kept_id,
                             "seq": seq, "trigger": "unmap"})
        _diag(diagnostics, seq, "N_AUTO_COALESCED", kept_id)
        counters["auto_coalesces"] += 1

    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "map":
            new_id = ev["id"]
            base = ev["base"]
            size = ev["size"]
            prot = ev["prot"]
            owner = ev["owner"]
            if new_id in regions or new_id in seen_ids:
                _diag(diagnostics, seq, "E_DUPLICATE_ID", new_id)
                counters["maps_rejected"] += 1
                continue
            if size < policy["min_region_size"]:
                _diag(diagnostics, seq, "E_BELOW_MIN_SIZE", new_id)
                counters["maps_rejected"] += 1
                continue
            overlapping = [rid for rid, r in regions.items()
                           if _ranges_overlap(base, size, r["base"], r["size"])]
            if overlapping:
                if policy["overlap_action"] == "reject":
                    _diag(diagnostics, seq, "E_OVERLAP_REJECTED", new_id)
                    counters["maps_rejected"] += 1
                    continue
                for rid in sorted(overlapping):
                    _diag(diagnostics, seq, "W_REPLACED_OVERLAP", rid)
                    del regions[rid]
            regions[new_id] = {"base": base, "id": new_id, "owner": owner,
                               "prot": prot, "size": size}
            seen_ids.add(new_id)
            counters["maps_succeeded"] += 1
            auto_coalesce_after_map(seq, new_id)
            continue
        if op == "unmap":
            target = ev["id"]
            if target not in regions:
                _diag(diagnostics, seq, "E_REGION_NOT_FOUND", target)
                continue
            removed = regions.pop(target)
            counters["unmaps_succeeded"] += 1
            auto_coalesce_after_unmap(seq, removed["base"],
                                      removed["base"] + removed["size"])
            continue
        if op == "mprotect":
            target = ev["id"]
            if target not in regions:
                _diag(diagnostics, seq, "E_REGION_NOT_FOUND", target)
                continue
            regions[target]["prot"] = ev["prot"]
            continue
        if op == "split":
            src_id = ev["id"]
            new_id = ev["target_id"]
            slice_base = ev["base"]
            slice_size = ev["size"]
            if src_id not in regions:
                _diag(diagnostics, seq, "E_REGION_NOT_FOUND", src_id)
                continue
            if new_id in regions or new_id in seen_ids:
                _diag(diagnostics, seq, "E_DUPLICATE_ID", new_id)
                continue
            src = regions[src_id]
            src_base = src["base"]
            src_end = src_base + src["size"]
            slice_end = slice_base + slice_size
            in_low = (slice_base == src_base)
            in_high = (slice_end == src_end)
            if not (slice_base >= src_base and slice_end <= src_end and slice_size > 0):
                _diag(diagnostics, seq, "E_SPLIT_OUT_OF_RANGE", src_id)
                continue
            if not (in_low or in_high):
                _diag(diagnostics, seq, "E_SPLIT_OUT_OF_RANGE", src_id)
                continue
            if slice_size == src["size"]:
                _diag(diagnostics, seq, "E_SPLIT_OUT_OF_RANGE", src_id)
                continue
            leftover_size = src["size"] - slice_size
            if (slice_size < policy["min_region_size"]
                    or leftover_size < policy["min_region_size"]):
                _diag(diagnostics, seq, "E_BELOW_MIN_SIZE", src_id)
                continue
            new_region = {"base": slice_base, "id": new_id,
                          "owner": src["owner"], "prot": src["prot"],
                          "size": slice_size}
            if in_low:
                src["base"] = slice_end
                src["size"] = leftover_size
            else:
                src["size"] = leftover_size
            regions[new_id] = new_region
            seen_ids.add(new_id)
            counters["splits"] += 1
            if policy["track_history"]:
                lineage_edges.add((src_id, new_id))
            continue
        if op == "merge":
            target_ids = ev["target_id"]
            id_a, id_b = target_ids[0], target_ids[1]
            if id_a not in regions or id_b not in regions:
                missing = id_a if id_a not in regions else id_b
                _diag(diagnostics, seq, "E_REGION_NOT_FOUND", missing)
                continue
            ra = regions[id_a]
            rb = regions[id_b]
            if ra["base"] > rb["base"]:
                lo, up = rb, ra
            else:
                lo, up = ra, rb
            adjacent = (lo["base"] + lo["size"] == up["base"])
            owner_ok = (lo["owner"] == up["owner"])
            prot_ok = _is_compatible(lo["prot"], lo["owner"], up["prot"], up["owner"],
                                     policy["coalesce_mode"])
            if not (adjacent and owner_ok and prot_ok):
                _diag(diagnostics, seq, "E_MERGE_NOT_ADJACENT", min(id_a, id_b))
                continue
            kept_id = min(id_a, id_b)
            dropped_id = max(id_a, id_b)
            kept = regions[kept_id]
            kept["base"] = lo["base"]
            kept["size"] = lo["size"] + up["size"]
            kept["prot"] = lo["prot"]
            kept["owner"] = lo["owner"]
            del regions[dropped_id]
            counters["explicit_merges"] += 1
            if policy["track_history"]:
                if id_a != kept_id:
                    lineage_edges.add((id_a, kept_id))
                if id_b != kept_id:
                    lineage_edges.add((id_b, kept_id))
            continue

    region_state = {
        "regions": sorted(
            [
                {"base": r["base"], "id": r["id"], "owner": r["owner"],
                 "prot": r["prot"], "size": r["size"]}
                for r in regions.values()
            ],
            key=lambda r: (r["base"], r["id"]),
        )
    }
    coalesce_doc = {"coalesces": list(coalesce_log)}
    diag_events = []
    for seq in sorted(diagnostics):
        diags = diagnostics[seq]
        diags_sorted = sorted(diags, key=lambda d: (
            SEVERITY_RANK[d["severity"]], d["code"],
            "" if d["region_id"] is None else d["region_id"],
        ))
        diag_events.append({"diagnostics": diags_sorted, "seq": seq})
    diag_doc = {"events": diag_events}
    if policy["track_history"]:
        nodes_set = set(seen_ids)
        for (a, b) in lineage_edges:
            nodes_set.add(a)
            nodes_set.add(b)
        nodes_sorted = sorted(nodes_set)
        edges_sorted = sorted(lineage_edges)
        in_count = {n: 0 for n in nodes_sorted}
        out_count = {n: 0 for n in nodes_sorted}
        for (a, b) in edges_sorted:
            out_count[a] = out_count.get(a, 0) + 1
            in_count[b] = in_count.get(b, 0) + 1
        node_arr = [{"id": n, "in_degree": in_count[n], "out_degree": out_count[n]}
                    for n in nodes_sorted]
        edge_arr = [{"from": a, "to": b} for (a, b) in edges_sorted]
        cycles = _compute_sccs(nodes_sorted, set(edges_sorted))
        graph_doc = {"cycles": cycles, "edges": edge_arr, "nodes": node_arr}
    else:
        graph_doc = {"cycles": [], "edges": [], "nodes": []}
    owners_at_end = sorted({r["owner"] for r in regions.values()})
    summary = {
        "auto_coalesces":          counters["auto_coalesces"],
        "events_with_diagnostics": len(diag_events),
        "explicit_merges":         counters["explicit_merges"],
        "final_region_count":      len(regions),
        "maps_rejected":           counters["maps_rejected"],
        "maps_succeeded":          counters["maps_succeeded"],
        "owners":                  owners_at_end,
        "splits":                  counters["splits"],
        "total_events":            len(events),
        "unmaps_succeeded":        counters["unmaps_succeeded"],
    }
    return {
        "region_state":       region_state,
        "coalesce_log":       coalesce_doc,
        "region_diagnostics": diag_doc,
        "region_graph":       graph_doc,
        "summary":            summary,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = in_dir.parent / "docs" / "diagnostics.md"
    if not docs.is_file():
        docs = Path("/app/docs/diagnostics.md")
    global DIAG_SEVERITY, VALID_DIAG_CODES
    VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs(docs)
    regions_doc = load_json(in_dir / "regions.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(regions_doc["regions"], events_doc["events"], policy_doc)
    write_canonical(out_dir / "region_state.json", outputs["region_state"])
    write_canonical(out_dir / "coalesce_log.json", outputs["coalesce_log"])
    write_canonical(out_dir / "region_diagnostics.json", outputs["region_diagnostics"])
    write_canonical(out_dir / "region_graph.json", outputs["region_graph"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
