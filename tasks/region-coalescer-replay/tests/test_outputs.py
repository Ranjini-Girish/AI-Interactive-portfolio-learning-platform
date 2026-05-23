"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "regionsim"

REGIONS_PATH = DATA_DIR / "regions.json"
EVENTS_PATH  = DATA_DIR / "events.json"
POLICY_PATH  = DATA_DIR / "policy.json"

REGION_STATE_PATH = OUT_DIR / "region_state.json"
COALESCE_PATH     = OUT_DIR / "coalesce_log.json"
DIAG_PATH         = OUT_DIR / "region_diagnostics.json"
GRAPH_PATH        = OUT_DIR / "region_graph.json"
SUMMARY_PATH      = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    REGION_STATE_PATH,
    COALESCE_PATH,
    DIAG_PATH,
    GRAPH_PATH,
    SUMMARY_PATH,
)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    REGIONS_PATH: "7f41001720537f1fc976fc7b72bee8d172775ee7d84b45182368d92016a7619b",
    EVENTS_PATH:  "43e1f126ca924b2d7e42db44eef47d3f46cb05167ed0e51a7c6f929ab453bef9",
    POLICY_PATH:  "40b3d221ff6b2e594bf2521daba3f1f388fb560d9371d6cc8f945b6c53c29f82",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of diagnostic
    codes and their severities. Code lines look like:
        | E_REGION_NOT_FOUND   | error   | ...
    The single source of truth for codes is the docs, not this test file.
    """
    import re
    text = DOCS_DIAG_PATH.read_text(encoding="utf-8")
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
            f"could not parse any diagnostic codes from {DOCS_DIAG_PATH}; "
            "check the docs format"
        )
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()
SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}


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


def reference_outputs() -> dict[str, Any]:
    regions_doc = load_json(REGIONS_PATH)
    events_doc  = load_json(EVENTS_PATH)
    policy_doc  = load_json(POLICY_PATH)
    return run_simulation(regions_doc["regions"], events_doc["events"], policy_doc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output, run the agent's binary with the canonical CLI, capture
    rc/stdout/stderr/start_time. Tests asserting against /app/output/*.json
    depend on this fixture so the agent's binary is the only thing that
    produces those files."""
    assert BINARY_PATH.exists(), (
        f"binary not found at {BINARY_PATH}; agent must build TypeScript sources to "
        f"this path before tests run"
    )
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    return {"start": start, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input files must match the snapshot SHA-256 the task ships with.
    Both prevents agents rewriting inputs to ease the task AND keeps the
    live-recomputed reference deterministic."""
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_binary_built_and_executable() -> None:
    """Agent must install a runnable TypeScript launcher at BINARY_PATH."""
    assert BINARY_PATH.exists(), f"expected launcher at {BINARY_PATH}"
    assert BINARY_PATH.stat().st_mode & stat.S_IXUSR, (
        f"{BINARY_PATH} is not executable"
    )
    src_ts = list(Path("/app/src").rglob("*.ts"))
    assert src_ts, "expected agent-authored TypeScript under /app/src"





def test_binary_runs_cleanly_and_outputs_are_fresh(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all five outputs that are mtime-newer than
    the moment the verifier started the run.
    """
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/regionsim exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    start = binary_run_outputs["start"]
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        m = path.stat().st_mtime
        assert m + 1.0 >= start, (
            f"output {path} has mtime {m} older than test start {start}; "
            "looks like a stale/precomputed file rather than fresh output"
        )
        load_json(path)
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual_names = {p.name for p in OUT_DIR.iterdir() if p.is_file()}
    extras = actual_names - expected_names
    assert not extras, (
        f"binary wrote extra files into /app/output: {sorted(extras)}; "
        "the spec says exactly five JSON outputs and no others"
    )


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args.

    Calls with 0/1/3 args must exit non-zero. With the correct two args
    pointing at fresh empty dirs, it would be expected to fail because the
    inputs are missing -- but absence-of-zero-arg is what we check here, not
    the success path.
    """
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = [str(BINARY_PATH)]
        if n_args >= 1:
            argv.append(str(fake_data))
        if n_args >= 2:
            argv.append(str(fake_out))
        if n_args >= 3:
            argv.append("extra")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode != 0, (
            f"binary should exit non-zero on {n_args} arg(s); got rc=0 "
            f"with stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )

def test_outputs_strict_json_formatting(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every output is 2-space, sort-keys, ASCII-only, trailing-newline JSON."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def test_outputs_are_ascii_at_every_depth(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every string at every depth in every output JSON must be pure ASCII."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        for i, b in enumerate(raw):
            assert b < 0x80, (
                f"{path} byte {i} = 0x{b:02x} is non-ASCII; outputs must be "
                "pure ASCII at the byte level"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )


def test_region_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """region_state.json must equal the live-computed reference exactly.

    Stresses:
      - final per-region holder fields (base, id, owner, prot, size)
      - regions sorted by (base, id)
      - successful auto-coalesces and explicit merges shrink the region count
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(REGION_STATE_PATH)
    assert actual == expected_outputs["region_state"]


def test_coalesce_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """coalesce_log.json must equal the live-computed reference exactly.

    Stresses:
      - chronological order (no sorting)
      - cascading merges from a single map produce two records with the same
        seq and trigger == "map"
      - explicit merge ops do NOT appear here
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(COALESCE_PATH)
    assert actual == expected_outputs["coalesce_log"]

def test_region_graph_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """region_graph.json must equal the live-computed reference exactly.

    Stresses:
      - nodes include every id ever observed, even unmapped ones
      - split adds a single edge source -> target
      - explicit merge adds edges from each parent to the kept (lex-min) id,
        suppressing the kept->kept self-loop
      - cycles surfaced as multi-vertex SCCs
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(GRAPH_PATH)
    assert actual == expected_outputs["region_graph"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly.

    Stresses:
      - maps_succeeded + maps_rejected == total map ops
      - W_REPLACED_OVERLAP warnings do NOT cause a map to count as rejected
      - owners is the sorted ASCII set of owners with >=1 region at end
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct severity,
    and within each event the list is sorted by (severity_rank, code, region_id).
    """
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), f"events not sorted by seq: {seqs}"
    for e in diag["events"]:
        prev = (-1, "", "")
        for d in e["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"event seq={e['seq']!r}: unknown code {d['code']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"event seq={e['seq']!r}: code {d['code']!r} has wrong "
                f"severity {d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            rid = "" if d["region_id"] is None else d["region_id"]
            key = (SEVERITY_RANK[d["severity"]], d["code"], rid)
            assert key >= prev, (
                f"event seq={e['seq']!r}: diagnostics not sorted by "
                f"(severity_rank, code, region_id); got {key} after {prev}"
            )
            prev = key


def test_region_state_no_overlaps_and_sorted(
    binary_run_outputs: dict[str, Any],
) -> None:
    """region_state must list non-overlapping regions sorted by (base, id)."""
    assert binary_run_outputs["returncode"] == 0
    state = load_json(REGION_STATE_PATH)
    keys = [(r["base"], r["id"]) for r in state["regions"]]
    assert keys == sorted(keys), (
        f"region_state.regions not sorted by (base, id): {keys}"
    )
    for i in range(len(state["regions"]) - 1):
        a = state["regions"][i]
        b = state["regions"][i + 1]
        assert a["base"] + a["size"] <= b["base"], (
            f"regions overlap: {a['id']} ends at "
            f"{a['base'] + a['size']} but {b['id']} starts at {b['base']}"
        )


def test_dataset_invariants_have_cycle_and_diagnostics(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least one lineage cycle (split-then-merge round
    trip) and at least seven of the eight diagnostic codes must be exercised.
    A trivially clean trace would mean the simulator is never stressed.
    """
    expected = expected_outputs
    diag_doc = expected["region_diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 7, (
        f"dataset invariant: expected at least 7 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    assert len(expected["region_graph"]["cycles"]) >= 1, (
        "dataset invariant: expected at least one lineage cycle "
        "(split+then explicit-merge round trip)"
    )
    assert expected["summary"]["explicit_merges"] >= 1, (
        "dataset invariant: expected at least one successful explicit merge"
    )
    assert expected["summary"]["splits"] >= 2, (
        "dataset invariant: expected at least two successful splits"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests (exercise branches the pinned dataset
# may not stress directly).
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   regions_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    (in_dir / "regions.json").write_text(json.dumps(regions_doc), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events_doc), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy_doc), encoding="utf-8")
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("region_state.json", "coalesce_log.json",
                  "region_diagnostics.json", "region_graph.json",
                  "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(regions_doc, events_doc, policy_doc):
    return run_simulation(regions_doc["regions"], events_doc["events"], policy_doc)


def test_hidden_dataset_overlap_replace_warns_and_keeps_new(tmp_path: Path) -> None:
    """Under overlap_action='replace', a map that overlaps existing regions
    removes them whole and emits one W_REPLACED_OVERLAP per removed region,
    then succeeds. The new region wins."""
    regions = {"regions": [
        {"base":  4096, "id": "old_a", "owner": "x", "prot": "rw", "size": 4096},
        {"base":  8192, "id": "old_b", "owner": "y", "prot": "rx", "size": 4096},
    ]}
    events = {"events": [
        {"seq": 0, "op": "map", "id": "new_z", "base": 4096, "size": 8192,
         "prot": "rwx", "owner": "z", "target_id": None},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "replace",
              "track_history": True}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_state.json"] == expected["region_state"]
    assert actual["region_diagnostics.json"] == expected["region_diagnostics"]
    assert actual["summary.json"] == expected["summary"]
    state = actual["region_state.json"]["regions"]
    ids_at_end = sorted(r["id"] for r in state)
    assert ids_at_end == ["new_z"], (
        f"replace-mode map should evict old_a and old_b leaving only new_z; "
        f"got {ids_at_end}"
    )
    diag_codes = [d["code"]
                  for e in actual["region_diagnostics.json"]["events"]
                  for d in e["diagnostics"]]
    assert diag_codes.count("W_REPLACED_OVERLAP") == 2, (
        f"expected exactly 2 W_REPLACED_OVERLAP warnings (one per evicted "
        f"region); got {diag_codes}"
    )
    assert actual["summary.json"]["maps_succeeded"] == 1
    assert actual["summary.json"]["maps_rejected"] == 0


def test_hidden_dataset_unmap_does_not_create_phantom_coalesce(tmp_path: Path) -> None:
    """auto_coalesce_after_unmap must not invent merges across the gap left
    by the unmapped region. After unmap of mid, left and right are NOT
    adjacent (a hole exists where mid lived), so no coalesce happens."""
    regions = {"regions": [
        {"base":  4096, "id": "left",  "owner": "u", "prot": "rw", "size": 4096},
        {"base":  8192, "id": "mid",   "owner": "v", "prot": "rx", "size": 4096},
        {"base": 12288, "id": "right", "owner": "u", "prot": "rw", "size": 4096},
    ]}
    events = {"events": [
        {"seq": 0, "op": "unmap", "id": "mid", "base": None, "size": None,
         "prot": None, "owner": None, "target_id": None},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "reject",
              "track_history": True}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_state.json"] == expected["region_state"]
    assert actual["coalesce_log.json"] == expected["coalesce_log"]
    state = actual["region_state.json"]["regions"]
    assert len(state) == 2, (
        f"left and right are separated by the freed mid region; got {state}"
    )
    assert actual["coalesce_log.json"]["coalesces"] == []
    assert actual["summary.json"]["auto_coalesces"] == 0
    assert actual["summary.json"]["unmaps_succeeded"] == 1


def test_hidden_dataset_split_low_and_high_edges(tmp_path: Path) -> None:
    """Splits at the low edge and high edge both succeed; an interior-slice
    split emits E_SPLIT_OUT_OF_RANGE."""
    regions = {"regions": [
        {"base": 4096, "id": "src", "owner": "x", "prot": "rw", "size": 12288},
    ]}
    events = {"events": [
        {"seq": 0, "op": "split", "id": "src", "base": 4096, "size": 4096,
         "prot": None, "owner": None, "target_id": "low"},
        {"seq": 1, "op": "split", "id": "src", "base": 12288, "size": 4096,
         "prot": None, "owner": None, "target_id": "high"},
        {"seq": 2, "op": "split", "id": "src", "base": 8200, "size": 16,
         "prot": None, "owner": None, "target_id": "interior"},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "reject",
              "track_history": True}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_state.json"] == expected["region_state"]
    assert actual["region_graph.json"] == expected["region_graph"]
    state_ids = sorted(r["id"] for r in actual["region_state.json"]["regions"])
    assert state_ids == ["high", "low", "src"], (
        f"after low+high splits, three regions remain; got {state_ids}"
    )
    diag = actual["region_diagnostics.json"]
    seq2 = next((e for e in diag["events"] if e["seq"] == 2), None)
    assert seq2 is not None
    assert any(d["code"] == "E_SPLIT_OUT_OF_RANGE"
               for d in seq2["diagnostics"]), (
        f"interior-slice split must emit E_SPLIT_OUT_OF_RANGE; got {seq2}"
    )


def test_hidden_dataset_track_history_false_empties_graph(tmp_path: Path) -> None:
    """When policy.track_history is false, region_graph carries empty cycles,
    edges, and nodes regardless of the trace."""
    regions = {"regions": [
        {"base": 4096, "id": "a", "owner": "x", "prot": "rw", "size": 8192},
    ]}
    events = {"events": [
        {"seq": 0, "op": "split", "id": "a", "base": 4096, "size": 4096,
         "prot": None, "owner": None, "target_id": "b"},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "reject",
              "track_history": False}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_graph.json"] == expected["region_graph"]
    assert actual["region_graph.json"] == {"cycles": [], "edges": [], "nodes": []}, (
        "track_history=false must suppress all graph contents; got "
        f"{actual['region_graph.json']}"
    )


def test_hidden_dataset_merge_lex_smallest_kept(tmp_path: Path) -> None:
    """An explicit merge keeps the lex-smallest id and adds lineage edges
    from each parent to the kept id (suppressing the kept->kept self-loop)."""
    regions = {"regions": [
        {"base": 4096, "id": "z_late",  "owner": "u", "prot": "rw", "size": 4096},
        {"base": 8192, "id": "a_early", "owner": "u", "prot": "rw", "size": 4096},
    ]}
    events = {"events": [
        {"seq": 0, "op": "merge", "id": None, "base": None, "size": None,
         "prot": None, "owner": None, "target_id": ["z_late", "a_early"]},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "reject",
              "track_history": True}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_state.json"] == expected["region_state"]
    assert actual["region_graph.json"] == expected["region_graph"]
    state = actual["region_state.json"]["regions"]
    assert len(state) == 1
    assert state[0]["id"] == "a_early", (
        f"merge must keep lex-smallest id 'a_early'; got {state[0]['id']!r}"
    )
    edges = {(e["from"], e["to"])
             for e in actual["region_graph.json"]["edges"]}
    assert edges == {("z_late", "a_early")}, (
        f"merge lineage must record only the parent->kept edge "
        f"(self-loop suppressed); got {edges}"
    )


def test_hidden_dataset_id_is_not_reused_after_unmap(tmp_path: Path) -> None:
    """An id that has been seen (initially or via map/split) cannot be
    re-introduced even after it has been unmapped or merged away."""
    regions = {"regions": [
        {"base": 4096, "id": "ghost", "owner": "x", "prot": "rw", "size": 4096},
    ]}
    events = {"events": [
        {"seq": 0, "op": "unmap", "id": "ghost", "base": None, "size": None,
         "prot": None, "owner": None, "target_id": None},
        {"seq": 1, "op": "map", "id": "ghost", "base": 8192, "size": 4096,
         "prot": "rw", "owner": "y", "target_id": None},
    ]}
    policy = {"auto_coalesce_after_unmap": True,
              "coalesce_mode": "prot_and_owner_match",
              "min_region_size": 4096, "overlap_action": "reject",
              "track_history": True}
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_diagnostics.json"] == expected["region_diagnostics"]
    diag = actual["region_diagnostics.json"]
    seq1 = next((e for e in diag["events"] if e["seq"] == 1), None)
    assert seq1 is not None and any(
        d["code"] == "E_DUPLICATE_ID" and d["region_id"] == "ghost"
        for d in seq1["diagnostics"]), (
        f"re-using 'ghost' after unmap must emit E_DUPLICATE_ID; got {seq1}"
    )


def test_hidden_dataset_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files. Catches latent
    nondeterminism (hash-map iteration, address-dependent ordering, etc.).
    """
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (REGIONS_PATH, EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            [str(BINARY_PATH), str(in_dir), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("region_state.json", "coalesce_log.json",
                  "region_diagnostics.json", "region_graph.json",
                  "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"{fname} differs between two runs on identical input; "
            f"binary is non-deterministic"
        )


# ---------------------------------------------------------------------------
# Explicit structural invariants (not just equality-to-reference)
# ---------------------------------------------------------------------------


def test_region_graph_explicit_ordering_invariants(
    binary_run_outputs: dict[str, Any],
) -> None:
    """region_graph.json must have nodes sorted by id, edges sorted by
    (from, to), and cycles sorted by their lex-smallest member -- whether
    or not the reference computes them that way."""
    assert binary_run_outputs["returncode"] == 0
    graph = load_json(GRAPH_PATH)
    if "nodes" in graph:
        node_ids = [n["id"] for n in graph["nodes"]]
        assert node_ids == sorted(node_ids), (
            f"region_graph.nodes must be sorted by id; got {node_ids}"
        )
    if "edges" in graph:
        edge_pairs = [(e["from"], e["to"]) for e in graph["edges"]]
        assert edge_pairs == sorted(edge_pairs), (
            f"region_graph.edges must be sorted by (from, to); got {edge_pairs}"
        )
    if "cycles" in graph:
        for cyc in graph["cycles"]:
            assert cyc == sorted(cyc), (
                f"each cycle's members must be sorted; got {cyc}"
            )
        cycle_keys = [c[0] if c else "" for c in graph["cycles"]]
        assert cycle_keys == sorted(cycle_keys), (
            f"region_graph.cycles must be sorted by lex-smallest member; "
            f"got {cycle_keys}"
        )


def test_coalesce_log_chronological_ordering(
    binary_run_outputs: dict[str, Any],
) -> None:
    """coalesce_log.coalesces must be in non-decreasing seq order; within the
    same seq, the suite expects the documented low-then-high cascade order."""
    assert binary_run_outputs["returncode"] == 0
    co = load_json(COALESCE_PATH)
    seqs = [r["seq"] for r in co["coalesces"]]
    assert seqs == sorted(seqs), (
        f"coalesce_log entries must be in non-decreasing seq order; got {seqs}"
    )


DOCS_OUTPUT_FORMAT_PATH = Path("/app/docs/output_format.md")


def _expected_summary_keys_from_docs() -> set[str]:
    """Parse /app/docs/output_format.md for the documented summary key set
    rather than hardcoding it in the test file. The summary block looks like:
        "auto_coalesces":          <int>,
    """
    import re
    text = DOCS_OUTPUT_FORMAT_PATH.read_text(encoding="utf-8")
    summary_match = re.search(r"##\s+`summary\.json`(.*?)(?:^##\s+|\Z)",
                              text, flags=re.DOTALL | re.MULTILINE)
    if summary_match is None:
        raise RuntimeError(
            "could not locate summary.json section in output_format.md"
        )
    summary_block = summary_match.group(1)
    keys = set(re.findall(r'"([a-z_]+)"\s*:', summary_block))
    if not keys:
        raise RuntimeError(
            "could not extract any summary keys from output_format.md"
        )
    return keys


def test_summary_keys_match_documented_set(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.json's top-level keys must exactly match the set documented in
    /app/docs/output_format.md. The docs are the source of truth, not a
    hardcoded list in this test file."""
    assert binary_run_outputs["returncode"] == 0
    expected = _expected_summary_keys_from_docs()
    actual = set(load_json(SUMMARY_PATH).keys())
    extra = actual - expected
    missing = expected - actual
    assert not extra, (
        f"summary.json has undocumented keys: {sorted(extra)}; "
        f"docs expect exactly {sorted(expected)}"
    )
    assert not missing, (
        f"summary.json missing documented keys: {sorted(missing)}"
    )


def test_summary_owners_field_is_sorted_ascii_list(
    binary_run_outputs: dict[str, Any],
) -> None:
    """summary.owners must be a list of strings, sorted ASCII, distinct."""
    assert binary_run_outputs["returncode"] == 0
    summary = load_json(SUMMARY_PATH)
    owners = summary["owners"]
    assert isinstance(owners, list)
    assert all(isinstance(o, str) for o in owners), (
        f"summary.owners must be all-strings; got {owners}"
    )
    assert owners == sorted(owners), (
        f"summary.owners must be sorted ASCII; got {owners}"
    )
    assert len(owners) == len(set(owners)), (
        f"summary.owners must be distinct; got {owners}"
    )


def test_coalesce_log_trigger_is_only_map_or_unmap(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Per /app/docs/coalesce.md, auto-coalesce is triggered ONLY by map or
    unmap (and ONLY when policy.auto_coalesce_after_unmap is true for unmap).
    Explicit 'merge' events must NEVER appear in coalesce_log -- those are a
    separate operation tracked in summary.explicit_merges."""
    assert binary_run_outputs["returncode"] == 0
    co = load_json(COALESCE_PATH)
    triggers = {r["trigger"] for r in co["coalesces"]}
    illegal = triggers - {"map", "unmap"}
    assert not illegal, (
        f"coalesce_log.trigger must be exactly 'map' or 'unmap'; "
        f"saw illegal triggers: {sorted(illegal)}"
    )


def test_region_diagnostics_event_ordering(
    binary_run_outputs: dict[str, Any],
) -> None:
    """region_diagnostics.events must be sorted by seq, and within each event
    diagnostics must be sorted by (severity_rank, code, region_id)."""
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), (
        f"region_diagnostics.events must be sorted by seq; got {seqs}"
    )
    rank = {"error": 0, "warning": 1, "note": 2}
    for e in diag["events"]:
        triples = [
            (rank[d["severity"]], d["code"], d.get("region_id") or "")
            for d in e["diagnostics"]
        ]
        assert triples == sorted(triples), (
            f"diagnostics within seq={e['seq']} must be sorted by "
            f"(severity_rank, code, region_id); got {triples}"
        )


# ---------------------------------------------------------------------------
# Anti-tampering: /app/data must be untouched by the binary
# ---------------------------------------------------------------------------


def _snapshot_data_tree() -> dict[str, str]:
    """Return {relative_path: sha256} for every regular file under /app/data."""
    snapshot: dict[str, str] = {}
    for p in sorted(DATA_DIR.rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(DATA_DIR))
            snapshot[rel] = sha256_of(p)
    return snapshot


def test_data_dir_tree_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The full file tree under /app/data must be byte-identical before and
    after the binary runs. The binary may not add, remove, rename, or modify
    any file under /app/data -- only read from it.
    """
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_data_tree()
    expected_files = set(EXPECTED_INPUT_HASHES.keys())
    expected_rel = {str(p.relative_to(DATA_DIR)) for p in expected_files}
    extra = set(after.keys()) - expected_rel
    assert not extra, (
        f"binary created extra files under /app/data: {sorted(extra)}; "
        "the binary must treat /app/data as read-only"
    )
    missing = expected_rel - set(after.keys())
    assert not missing, (
        f"binary removed files from /app/data: {sorted(missing)}"
    )
    for path, expected in EXPECTED_INPUT_HASHES.items():
        rel = str(path.relative_to(DATA_DIR))
        assert after[rel] == expected, (
            f"input file {path} was modified by the binary; "
            f"hash before={expected}, after={after[rel]}"
        )


def test_input_hashes_unchanged_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Re-hash the three pinned inputs after the binary has finished running.
    Catches a binary that transiently mutates inputs (e.g., to write its own
    intermediate state) and tries to restore them later.
    """
    assert binary_run_outputs["returncode"] == 0
    for path, expected in EXPECTED_INPUT_HASHES.items():
        actual = sha256_of(path)
        assert actual == expected, (
            f"after-run sha256 of {path} is {actual}; expected {expected}. "
            "Binary must not write to inputs even transiently."
        )


# ---------------------------------------------------------------------------
# Malformed-input tests (instruction.md mandates non-zero exit on these)
# ---------------------------------------------------------------------------


def _malformed_run(tmp_path: Path,
                   regions_text: str | None,
                   events_text: str | None,
                   policy_text: str | None) -> subprocess.CompletedProcess[str]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    if regions_text is not None:
        (in_dir / "regions.json").write_text(regions_text, encoding="utf-8")
    if events_text is not None:
        (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    if policy_text is not None:
        (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )


_VALID_POLICY_TEXT = json.dumps({
    "auto_coalesce_after_unmap": True,
    "coalesce_mode": "prot_and_owner_match",
    "min_region_size": 4096,
    "overlap_action": "reject",
    "track_history": True,
})

_VALID_REGIONS_TEXT = json.dumps({
    "regions": [
        {"base": 4096, "id": "r0", "owner": "u", "prot": "rw", "size": 4096},
    ],
})

_VALID_EVENTS_TEXT = json.dumps({"events": []})


def _assert_no_valid_outputs(tmp_path: Path) -> None:
    """When the binary correctly rejects malformed input, the output directory
    must not contain a complete, valid set of canonical outputs. (It is OK if
    some files were partially written before the binary errored.)"""
    out_dir = tmp_path / "out"
    if not out_dir.exists():
        return
    expected_names = {"region_state.json", "coalesce_log.json",
                      "region_diagnostics.json", "region_graph.json",
                      "summary.json"}
    present = {p.name for p in out_dir.iterdir() if p.is_file()}
    if expected_names.issubset(present):
        for name in expected_names:
            try:
                json.loads((out_dir / name).read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return
        raise AssertionError(
            "binary produced a complete, JSON-parsable output set despite "
            f"malformed input; outputs={sorted(present)}"
        )


def test_binary_rejects_malformed_json_syntax(tmp_path: Path) -> None:
    """A regions.json that is not valid JSON must produce a non-zero exit
    AND must not leave a complete, valid output set behind."""
    proc = _malformed_run(
        tmp_path,
        regions_text="{not valid json,",
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted malformed-syntax regions.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_required_fields(tmp_path: Path) -> None:
    """A regions.json whose entries omit required keys must non-zero exit."""
    bad_regions = json.dumps({
        "regions": [
            {"id": "r0", "owner": "u", "prot": "rw", "size": 4096},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        regions_text=bad_regions,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted region missing 'base' field (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_wrong_value_types(tmp_path: Path) -> None:
    """A region with a non-integer 'size' must produce a non-zero exit."""
    bad_regions = json.dumps({
        "regions": [
            {"base": 4096, "id": "r0", "owner": "u",
             "prot": "rw", "size": "not-an-integer"},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        regions_text=bad_regions,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted region with non-integer size (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)

def test_binary_rejects_non_dense_seq(tmp_path: Path) -> None:
    """events.json must have seq values 0,1,2,... dense and increasing."""
    bad_events = json.dumps({
        "events": [
            {"seq": 0, "op": "unmap", "id": "r0", "base": None, "size": None,
             "prot": None, "owner": None, "target_id": None},
            {"seq": 5, "op": "unmap", "id": "r0", "base": None, "size": None,
             "prot": None, "owner": None, "target_id": None},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        regions_text=_VALID_REGIONS_TEXT,
        events_text=bad_events,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted non-dense seq values (0,5) (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_overlapping_initial_regions(tmp_path: Path) -> None:
    """The initial regions.json must contain a non-overlapping layout. Two
    overlapping initial regions are a malformed-input condition."""
    bad_regions = json.dumps({
        "regions": [
            {"base": 4096, "id": "a", "owner": "u",
             "prot": "rw", "size": 8192},
            {"base": 8192, "id": "b", "owner": "u",
             "prot": "rw", "size": 4096},
        ],
    })
    proc = _malformed_run(
        tmp_path,
        regions_text=bad_regions,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=_VALID_POLICY_TEXT,
    )
    assert proc.returncode != 0, (
        f"binary accepted overlapping initial regions (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    """If any of the three required input files is missing from argv[1], the
    binary must exit non-zero (and not silently produce empty outputs)."""
    proc = _malformed_run(
        tmp_path,
        regions_text=_VALID_REGIONS_TEXT,
        events_text=_VALID_EVENTS_TEXT,
        policy_text=None,
    )
    assert proc.returncode != 0, (
        f"binary accepted missing policy.json (rc={proc.returncode})"
    )
    _assert_no_valid_outputs(tmp_path)


# ---------------------------------------------------------------------------
# Property-based / randomized hidden datasets
# ---------------------------------------------------------------------------


def _gen_random_dataset(seed: int, *,
                        n_initial: int = 4,
                        n_events: int = 30,
                        coalesce_mode: str = "prot_and_owner_match",
                        ) -> tuple[dict, dict, dict]:
    """Deterministic pseudo-random dataset generator. Pure Python `random`
    seeded for reproducibility. Returns (regions_doc, events_doc, policy_doc)
    that the reference is guaranteed to accept (no malformed inputs)."""
    import random
    rng = random.Random(seed)
    page = 4096
    prots = ["r", "rw", "rx", "rwx"]
    owners = ["u", "v", "w", "x", "y"]

    cursor = page
    initial: list[dict] = []
    used_ids: set[str] = set()
    for _ in range(n_initial):
        rid = f"r{len(used_ids)}"
        used_ids.add(rid)
        size = page * rng.randint(1, 4)
        gap = page * rng.randint(0, 2)
        cursor += gap
        initial.append({
            "base": cursor, "id": rid, "owner": rng.choice(owners),
            "prot": rng.choice(prots), "size": size,
        })
        cursor += size

    next_id_n = len(initial)
    events: list[dict] = []
    for seq in range(n_events):
        op = rng.choice(["map", "unmap", "mprotect", "split", "merge"])
        ev = {"seq": seq, "op": op, "id": None, "base": None, "size": None,
              "prot": None, "owner": None, "target_id": None}
        if op == "map":
            new_id = f"r{next_id_n}"
            next_id_n += 1
            ev["id"] = new_id
            ev["base"] = cursor + page * rng.randint(0, 4)
            ev["size"] = page * rng.randint(1, 3)
            ev["prot"] = rng.choice(prots)
            ev["owner"] = rng.choice(owners)
            cursor = ev["base"] + ev["size"] + page
        elif op == "unmap":
            ev["id"] = rng.choice(sorted(used_ids) + [f"r{next_id_n + 99}"])
        elif op == "mprotect":
            ev["id"] = rng.choice(sorted(used_ids) + [f"r{next_id_n + 99}"])
            ev["prot"] = rng.choice(prots)
        elif op == "split":
            src = rng.choice(sorted(used_ids) + ["missing_src"])
            new_id = f"r{next_id_n}"
            next_id_n += 1
            ev["id"] = src
            ev["target_id"] = new_id
            ev["base"] = page * rng.randint(1, 20)
            ev["size"] = page * rng.randint(1, 3)
        elif op == "merge":
            ids = sorted(used_ids)
            if len(ids) >= 2:
                a, b = rng.sample(ids, 2)
            elif len(ids) == 1:
                a, b = ids[0], ids[0]
            else:
                a, b = "x", "y"
            ev["id"] = None
            ev["target_id"] = [a, b]
        events.append(ev)
        if op == "map" and ev["id"] is not None:
            used_ids.add(ev["id"])

    regions_doc = {"regions": initial}
    events_doc = {"events": events}
    policy_doc = {
        "auto_coalesce_after_unmap": rng.choice([True, False]),
        "coalesce_mode": coalesce_mode,
        "min_region_size": page,
        "overlap_action": rng.choice(["reject", "replace"]),
        "track_history": rng.choice([True, False]),
    }
    return regions_doc, events_doc, policy_doc


@pytest.mark.parametrize("seed", [101, 202, 303, 404, 505])
def test_randomized_property_dataset_against_reference(
    tmp_path: Path, seed: int,
) -> None:
    """Generate a fresh pseudo-random dataset at test time and assert the
    binary's outputs match the live reference. With diverse inputs and
    a different seed in each parametrize, an agent cannot precompute
    expected outputs offline and embed them as JSON literals.
    """
    regions, events, policy = _gen_random_dataset(seed)
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    for name, key in (("region_state.json", "region_state"),
                      ("coalesce_log.json", "coalesce_log"),
                      ("region_diagnostics.json", "region_diagnostics"),
                      ("region_graph.json", "region_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed}: binary {name} differs from reference"
        )


@pytest.mark.parametrize("seed", [11, 22, 33])
def test_randomized_property_dataset_with_strict_mode(
    tmp_path: Path, seed: int,
) -> None:
    """Same as above but pinned to coalesce_mode='strict' to specifically
    exercise the strict alias and force prot+owner matching."""
    regions, events, policy = _gen_random_dataset(seed, coalesce_mode="strict")
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    for name, key in (("region_state.json", "region_state"),
                      ("coalesce_log.json", "coalesce_log"),
                      ("region_graph.json", "region_graph"),
                      ("summary.json", "summary")):
        assert actual[name] == expected[key], (
            f"seed={seed} strict: binary {name} differs from reference"
        )


def test_randomized_property_dataset_no_initial_regions(
    tmp_path: Path,
) -> None:
    """An empty initial layout with mostly map+merge events. Ensures the
    binary does not assume the layout starts non-empty."""
    regions, events, policy = _gen_random_dataset(
        seed=777, n_initial=0, n_events=20,
    )
    actual = _run_binary_on(tmp_path, regions, events, policy)
    expected = _ref_for(regions, events, policy)
    assert actual["region_state.json"] == expected["region_state"]
    assert actual["coalesce_log.json"] == expected["coalesce_log"]
    assert actual["summary.json"] == expected["summary"]

