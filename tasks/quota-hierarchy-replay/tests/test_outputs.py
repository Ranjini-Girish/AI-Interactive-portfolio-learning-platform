"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections import defaultdict
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
JAVA_CLASS = "Replay"
BUILD_DIR = Path("/app/build")
GSON_CP = "/opt/gson.jar"

NS_PATH = DATA_DIR / "namespaces.json"
ALLOC_PATH = DATA_DIR / "allocations.json"
CONFIG_PATH = DATA_DIR / "config.json"

DECISIONS_PATH = OUT_DIR / "allocation_decisions.json"
NS_USAGE_PATH = OUT_DIR / "namespace_usage.json"
ROLLUP_PATH = OUT_DIR / "rollup_tree.json"
VIOLATIONS_PATH = OUT_DIR / "violations.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    DECISIONS_PATH,
    NS_USAGE_PATH,
    ROLLUP_PATH,
    VIOLATIONS_PATH,
    SUMMARY_PATH,
)

ALL_INPUT_PATHS = (NS_PATH, ALLOC_PATH, CONFIG_PATH)

VALID_DECISIONS = {"admitted", "rejected", "ignored"}
VALID_REASONS = {
    "under_limits",
    "unknown_namespace",
    "limit_exceeded",
    "release_underflow",
    "release_unknown_ignored",
    "release_unknown_rejected",
}
VALID_PAIRS = {
    ("admitted", "under_limits"),
    ("rejected", "unknown_namespace"),
    ("rejected", "limit_exceeded"),
    ("rejected", "release_underflow"),
    ("rejected", "release_unknown_rejected"),
    ("ignored", "release_unknown_ignored"),
}

RESOURCES = ("cpu", "memory", "storage")


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def dump_canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = dump_canonical(payload)
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth.
# Keep in sync with /app/docs/.
# ---------------------------------------------------------------------------


def _zero():
    return {r: 0 for r in RESOURCES}


def _add(a: dict, b: dict) -> dict:
    return {r: a[r] + b[r] for r in RESOURCES}


def _sub(a: dict, b: dict) -> dict:
    return {r: a[r] - b[r] for r in RESOURCES}


def simulate(ns_data: dict, alloc_data: dict, config: dict) -> dict:
    namespaces = list(ns_data["namespaces"])
    events = list(alloc_data["events"])
    nodes = {n["name"]: dict(n) for n in namespaces}
    children: dict[str, list[str]] = {name: [] for name in nodes}
    root = None
    for n in namespaces:
        if n["parent"] is None:
            root = n["name"]
        else:
            children[n["parent"]].append(n["name"])
    for k in children:
        children[k].sort()

    used_own = {name: _zero() for name in nodes}
    used_subtree = {name: _zero() for name in nodes}

    def ancestors_chain(name: str) -> list[str]:
        chain = []
        cur = name
        while cur is not None:
            chain.append(cur)
            cur = nodes[cur]["parent"]
        return chain

    decisions = []
    for ev in events:
        ns = ev["namespace"]
        op = ev["op"]
        res = dict(ev["resources"])
        base = {
            "event_id": ev["event_id"],
            "ts_unix_ms": ev["ts_unix_ms"],
            "namespace": ns,
            "op": op,
        }
        if ns not in nodes:
            if op == "allocate":
                decisions.append({**base, "decision": "rejected", "reason": "unknown_namespace",
                                  "blocking_namespace": None, "resources_granted": _zero()})
            else:
                if config["release_unknown_action"] == "ignore":
                    decisions.append({**base, "decision": "ignored", "reason": "release_unknown_ignored",
                                      "blocking_namespace": None, "resources_granted": _zero()})
                else:
                    decisions.append({**base, "decision": "rejected", "reason": "release_unknown_rejected",
                                      "blocking_namespace": None, "resources_granted": _zero()})
            continue
        if op == "allocate":
            chain = ancestors_chain(ns)
            blocking = None
            for anc in chain:
                limits = nodes[anc]["limits"]
                post = _add(used_subtree[anc], res)
                if any(post[r] > limits[r] for r in RESOURCES):
                    blocking = anc
                    break
            if blocking is not None:
                decisions.append({**base, "decision": "rejected", "reason": "limit_exceeded",
                                  "blocking_namespace": blocking, "resources_granted": _zero()})
                continue
            used_own[ns] = _add(used_own[ns], res)
            for anc in chain:
                used_subtree[anc] = _add(used_subtree[anc], res)
            decisions.append({**base, "decision": "admitted", "reason": "under_limits",
                              "blocking_namespace": None, "resources_granted": dict(res)})
        else:
            if any(res[r] > used_own[ns][r] for r in RESOURCES):
                decisions.append({**base, "decision": "rejected", "reason": "release_underflow",
                                  "blocking_namespace": ns, "resources_granted": _zero()})
                continue
            used_own[ns] = _sub(used_own[ns], res)
            for anc in ancestors_chain(ns):
                used_subtree[anc] = _sub(used_subtree[anc], res)
            decisions.append({**base, "decision": "admitted", "reason": "under_limits",
                              "blocking_namespace": None, "resources_granted": dict(res)})

    decisions_sorted = sorted(decisions, key=lambda d: d["event_id"])

    descendants_count: dict[str, int] = {}

    def count_desc(node: str) -> int:
        c = 0
        for child in children[node]:
            c += 1 + count_desc(child)
        descendants_count[node] = c
        return c

    if root is not None:
        count_desc(root)

    namespace_usage = []
    for name in sorted(nodes.keys()):
        limits = nodes[name]["limits"]
        usubtree = used_subtree[name]
        headroom = {r: limits[r] - usubtree[r] for r in RESOURCES}
        namespace_usage.append({
            "name": name,
            "limits": dict(limits),
            "used_own": dict(used_own[name]),
            "used_subtree": dict(usubtree),
            "headroom": headroom,
            "descendant_count": descendants_count.get(name, 0),
        })

    rollup = []

    def dfs(name: str, parent: str | None, depth: int):
        rollup.append({
            "name": name,
            "parent": parent,
            "depth": depth,
            "children": list(children[name]),
            "used_subtree": dict(used_subtree[name]),
        })
        for child in children[name]:
            dfs(child, name, depth + 1)

    if root is not None:
        dfs(root, None, 0)

    by_id = {e["event_id"]: e for e in events}
    violations = []
    for d in decisions:
        if d["decision"] != "rejected":
            continue
        ev = by_id[d["event_id"]]
        violations.append({**d, "attempted_resources": dict(ev["resources"])})
    violations_sorted = sorted(violations, key=lambda v: v["event_id"])

    admitted = sum(1 for d in decisions if d["decision"] == "admitted")
    rejected = sum(1 for d in decisions if d["decision"] == "rejected")
    ignored = sum(1 for d in decisions if d["decision"] == "ignored")
    uk = sum(1 for d in decisions if d["reason"] == "unknown_namespace")
    le = sum(1 for d in decisions if d["reason"] == "limit_exceeded")
    ru = sum(1 for d in decisions if d["reason"] == "release_underflow")

    hottest = None
    best = -1
    for name in sorted(nodes.keys()):
        s = sum(used_subtree[name][r] for r in RESOURCES)
        if s > best:
            best = s
            hottest = name
    if best <= 0:
        hottest = None

    summary = {
        "total_events": len(decisions),
        "total_namespaces": len(nodes),
        "admitted_events": admitted,
        "rejected_events": rejected,
        "ignored_events": ignored,
        "unknown_namespace_rejects": uk,
        "limit_exceeded_rejects": le,
        "release_underflow_rejects": ru,
        "hottest_namespace": hottest,
    }

    return {
        "allocation_decisions": {"decisions": decisions_sorted},
        "namespace_usage": {"namespaces": namespace_usage},
        "rollup_tree": {"tree": rollup},
        "violations": {"violations": violations_sorted},
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {
        "namespaces": load_json(NS_PATH),
        "allocations": load_json(ALLOC_PATH),
        "config": load_json(CONFIG_PATH),
    }


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(input_data["namespaces"], input_data["allocations"], input_data["config"])


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in ALL_INPUT_PATHS}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert _java_class_ready(), f"agent binary missing at {(BUILD_DIR / f"{JAVA_CLASS}.class")}"
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert res.returncode == 0, (
        f"binary failed: rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    out: dict[Path, Any] = {}
    for p in ALL_OUT_PATHS:
        assert p.exists(), f"missing output: {p}"
        out[p] = load_json(p)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged(precomputed_input_hashes):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} content mutated"


def test_binary_built_and_executable():
    assert _java_class_ready(), f"missing {(BUILD_DIR / f"{JAVA_CLASS}.class")}"
    

def test_binary_is_newer_than_sources():
    src_root = Path("/app/src")
    inc_root = Path("/app/include")
    sources: list[Path] = []
    for root in (src_root, inc_root):
        if root.exists():
            sources.extend(p for p in root.rglob("*") if p.is_file())
    assert sources, "no /app/src/ or /app/include/ files found"
    bin_mtime = (BUILD_DIR / f"{JAVA_CLASS}.class").stat().st_mtime
    for s in sources:
        assert bin_mtime + 1e-3 >= s.stat().st_mtime, (
            f"binary {(BUILD_DIR / f"{JAVA_CLASS}.class")} is older than source {s} - looks pre-built"
        )


def test_binary_runs_cleanly_and_outputs_are_fresh(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts(tmp_path):
    res = subprocess.run(
        ["java", "-cp", f"{BUILD_DIR}:{GSON_CP}", JAVA_CLASS],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode != 0
    probe_out = tmp_path / "probe_out"
    probe_out.mkdir()
    res = subprocess.run(
        [str((BUILD_DIR / f"{JAVA_CLASS}.class")), str(DATA_DIR), str(probe_out), "extra"],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0
    leftovers = sorted(probe_out.rglob("*"))
    assert leftovers == [], f"wrong-arg-count invocation wrote artifacts: {leftovers}"


def test_binary_uses_argv2_paths_not_hardcoded(tmp_path):
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, tmp_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"binary failed under alt out_dir: {res.stderr}"
    required = [
        "allocation_decisions.json",
        "namespace_usage.json",
        "rollup_tree.json",
        "violations.json",
        "summary.json",
    ]
    for name in required:
        p = tmp_out / name
        assert p.exists(), f"binary did not write {name} to argv[2]"
        assert p.is_file(), f"{name} under alt out_dir is not a regular file"
        assert not p.is_symlink(), f"{name} under alt out_dir is a symlink"
    entries = sorted(p.name for p in tmp_out.iterdir())
    assert entries == sorted(required), f"alt out_dir contains unexpected artifacts: {entries}"


def test_binary_reads_input_from_argv1_not_hardcoded(tmp_path, input_data, expected_outputs):
    tmp_data = tmp_path / "altdata"
    tmp_data.mkdir()
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    variant_evs = {"events": input_data["allocations"]["events"][:-1]}
    (tmp_data / "namespaces.json").write_text(dump_canonical(input_data["namespaces"]))
    (tmp_data / "allocations.json").write_text(dump_canonical(variant_evs))
    (tmp_data / "config.json").write_text(dump_canonical(input_data["config"]))
    res = subprocess.run(
        [*_java_cmd(tmp_data, tmp_out)],
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"binary failed under variant data_dir: {res.stderr}"
    variant_expected = simulate(input_data["namespaces"], variant_evs, input_data["config"])
    for name, key in [
        ("allocation_decisions.json", "allocation_decisions"),
        ("namespace_usage.json", "namespace_usage"),
        ("rollup_tree.json", "rollup_tree"),
        ("violations.json", "violations"),
        ("summary.json", "summary"),
    ]:
        actual = json.loads((tmp_out / name).read_text(encoding="utf-8"))
        assert actual == variant_expected[key], (
            f"binary's {name} from argv[1]={tmp_data} did not track the variant data"
        )
    assert variant_expected["allocation_decisions"] != expected_outputs["allocation_decisions"], (
        "variant dataset did not produce a different decision set; test is degenerate"
    )


def test_outputs_strict_json_formatting(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        text.encode("ascii")


def _walk_object_keys_in_emitted_order(text: str) -> list[list[str]]:
    obj = json.loads(text, object_pairs_hook=lambda items: items)
    out: list[list[str]] = []

    def walk(node):
        if isinstance(node, list):
            if (node and isinstance(node[0], tuple) and len(node[0]) == 2
                    and isinstance(node[0][0], str)):
                keys = [k for k, _ in node]
                out.append(keys)
                for _, v in node:
                    walk(v)
            else:
                for v in node:
                    walk(v)

    walk(obj)
    return out


def test_outputs_keys_sorted_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        for keys in _walk_object_keys_in_emitted_order(text):
            assert keys == sorted(keys), f"{p}: object keys not sorted: {keys}"


def test_output_directory_contains_exactly_five_files(binary_run_outputs):
    entries = list(OUT_DIR.iterdir())
    names = sorted(p.name for p in entries)
    assert names == sorted([
        "allocation_decisions.json", "namespace_usage.json",
        "rollup_tree.json", "violations.json", "summary.json",
    ]), f"unexpected output files: {names}"
    for p in entries:
        assert p.is_file(), f"{p} is not a regular file"
        assert not p.is_symlink(), f"{p} must not be a symlink"


def test_allocation_decisions_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[DECISIONS_PATH] == expected_outputs["allocation_decisions"]


def test_namespace_usage_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[NS_USAGE_PATH] == expected_outputs["namespace_usage"]


def test_rollup_tree_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[ROLLUP_PATH] == expected_outputs["rollup_tree"]


def test_violations_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[VIOLATIONS_PATH] == expected_outputs["violations"]


def test_summary_match_reference(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[SUMMARY_PATH] == expected_outputs["summary"]


def test_decisions_use_closed_sets(binary_run_outputs):
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        assert d["decision"] in VALID_DECISIONS, d
        assert d["reason"] in VALID_REASONS, d
        assert (d["decision"], d["reason"]) in VALID_PAIRS, d


def test_decisions_sorted_by_event_id(binary_run_outputs):
    ids = [d["event_id"] for d in binary_run_outputs[DECISIONS_PATH]["decisions"]]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))


def test_namespace_usage_sorted_by_name(binary_run_outputs):
    names = [n["name"] for n in binary_run_outputs[NS_USAGE_PATH]["namespaces"]]
    assert names == sorted(names)


def test_violations_sorted_by_event_id(binary_run_outputs):
    ids = [v["event_id"] for v in binary_run_outputs[VIOLATIONS_PATH]["violations"]]
    assert ids == sorted(ids)


def test_admitted_invariants(binary_run_outputs):
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        if d["decision"] != "admitted":
            continue
        assert d["reason"] == "under_limits"
        assert d["blocking_namespace"] is None
        assert all(d["resources_granted"][r] >= 0 for r in RESOURCES)


def test_rejected_invariants(binary_run_outputs):
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        if d["decision"] != "rejected":
            continue
        assert d["resources_granted"] == {r: 0 for r in RESOURCES}, d


def test_unknown_namespace_invariants(binary_run_outputs):
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        if d["reason"] == "unknown_namespace":
            assert d["decision"] == "rejected", d
            assert d["blocking_namespace"] is None, d
            assert d["op"] == "allocate", d


def test_limit_exceeded_blocking_namespace_set(binary_run_outputs, input_data):
    declared = {n["name"] for n in input_data["namespaces"]["namespaces"]}
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        if d["reason"] != "limit_exceeded":
            continue
        assert d["blocking_namespace"] is not None
        assert d["blocking_namespace"] in declared


def test_release_underflow_blocking_self(binary_run_outputs):
    for d in binary_run_outputs[DECISIONS_PATH]["decisions"]:
        if d["reason"] == "release_underflow":
            assert d["op"] == "release", d
            assert d["blocking_namespace"] == d["namespace"], d


def test_violations_include_attempted_resources(binary_run_outputs, input_data):
    by_id = {e["event_id"]: e for e in input_data["allocations"]["events"]}
    for v in binary_run_outputs[VIOLATIONS_PATH]["violations"]:
        assert v["attempted_resources"] == by_id[v["event_id"]]["resources"], v


def test_violations_only_rejected_events(binary_run_outputs):
    for v in binary_run_outputs[VIOLATIONS_PATH]["violations"]:
        assert v["decision"] == "rejected", v


def test_violations_match_decision_count(binary_run_outputs):
    rejected = [d for d in binary_run_outputs[DECISIONS_PATH]["decisions"] if d["decision"] == "rejected"]
    vs = binary_run_outputs[VIOLATIONS_PATH]["violations"]
    assert len(rejected) == len(vs)


def test_rollup_tree_preorder_alpha_children(binary_run_outputs, input_data):
    tree = binary_run_outputs[ROLLUP_PATH]["tree"]
    assert tree, "empty rollup tree"
    assert tree[0]["parent"] is None and tree[0]["depth"] == 0
    seen = set()
    by_name = {n["name"]: n for n in tree}
    for node in tree:
        seen.add(node["name"])
        assert node["children"] == sorted(node["children"])
        for child in node["children"]:
            assert by_name[child]["parent"] == node["name"], (
                f"child {child}.parent should be {node['name']} got {by_name[child]['parent']}"
            )
            assert by_name[child]["depth"] == node["depth"] + 1
    declared = {n["name"] for n in input_data["namespaces"]["namespaces"]}
    assert seen == declared, f"rollup tree missing nodes: {declared - seen}"


def test_namespace_usage_headroom_nonneg(binary_run_outputs):
    for n in binary_run_outputs[NS_USAGE_PATH]["namespaces"]:
        for r in RESOURCES:
            assert n["headroom"][r] >= 0, n
            assert n["used_subtree"][r] + n["headroom"][r] == n["limits"][r], n


def test_used_subtree_consistency(binary_run_outputs, input_data):
    """For every namespace N: used_subtree(N) == sum of used_own over the
    subtree rooted at N (including N itself)."""
    usage = {n["name"]: n for n in binary_run_outputs[NS_USAGE_PATH]["namespaces"]}
    children: dict[str, list[str]] = defaultdict(list)
    for n in input_data["namespaces"]["namespaces"]:
        if n["parent"] is not None:
            children[n["parent"]].append(n["name"])

    def subtree_sum(name: str) -> dict[str, int]:
        s = dict(usage[name]["used_own"])
        for c in children[name]:
            cs = subtree_sum(c)
            for r in RESOURCES:
                s[r] += cs[r]
        return s

    for name, info in usage.items():
        rolled = subtree_sum(name)
        assert info["used_subtree"] == rolled, (
            f"{name} used_subtree {info['used_subtree']} != rolled {rolled}"
        )


def test_summary_consistent_with_decisions(binary_run_outputs):
    decisions = binary_run_outputs[DECISIONS_PATH]["decisions"]
    s = binary_run_outputs[SUMMARY_PATH]
    counts: dict[str, int] = defaultdict(int)
    reasons: dict[str, int] = defaultdict(int)
    for d in decisions:
        counts[d["decision"]] += 1
        reasons[d["reason"]] += 1
    assert s["total_events"] == len(decisions)
    assert s["admitted_events"] == counts["admitted"]
    assert s["rejected_events"] == counts["rejected"]
    assert s["ignored_events"] == counts["ignored"]
    assert s["unknown_namespace_rejects"] == reasons["unknown_namespace"]
    assert s["limit_exceeded_rejects"] == reasons["limit_exceeded"]
    assert s["release_underflow_rejects"] == reasons["release_underflow"]


def test_dataset_exercises_every_branch(expected_outputs):
    s = expected_outputs["summary"]
    assert s["admitted_events"] > 0
    assert s["limit_exceeded_rejects"] > 0
    assert s["release_underflow_rejects"] > 0
    assert s["unknown_namespace_rejects"] > 0
    assert s["ignored_events"] > 0


def test_determinism_two_runs_byte_identical(tmp_path):
    out_a = tmp_path / "outA"
    out_a.mkdir()
    out_b = tmp_path / "outB"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run(
            [*_java_cmd(DATA_DIR, out)],
            capture_output=True, text=True, timeout=180,
        )
        assert res.returncode == 0
    for name in (
        "allocation_decisions.json", "namespace_usage.json",
        "rollup_tree.json", "violations.json", "summary.json",
    ):
        a = (out_a / name).read_bytes()
        b = (out_b / name).read_bytes()
        assert a == b, f"non-deterministic output for {name}"


def test_data_dir_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} mutated by binary run"


def test_binary_can_be_rebuilt_from_visible_sources(tmp_path, expected_outputs):
    src_root = Path("/app/src")
    inc_root = Path("/app/include")
    sources = sorted(p for p in src_root.rglob("*.cpp") if p.is_file()) if src_root.exists() else []
    assert sources, "no .cpp sources under /app/src/"
    binbuilt = tmp_path / "quotahier_rebuilt"
    cmd = ["g++", "-std=c++17", "-O2", "-Wall"]
    if inc_root.exists():
        cmd.extend(["-I", str(inc_root)])
    cmd.extend(str(s) for s in sources)
    cmd.extend(["-o", str(binbuilt)])
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"rebuild failed:\n{res.stderr}"
    out = tmp_path / "out_rebuilt"
    out.mkdir()
    res = subprocess.run([str(binbuilt), str(DATA_DIR), str(out)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, f"rebuilt binary failed:\n{res.stderr}"
    for name, key in [
        ("allocation_decisions.json", "allocation_decisions"),
        ("namespace_usage.json", "namespace_usage"),
        ("rollup_tree.json", "rollup_tree"),
        ("violations.json", "violations"),
        ("summary.json", "summary"),
    ]:
        actual = json.loads((out / name).read_text(encoding="utf-8"))
        assert actual == expected_outputs[key], f"rebuilt binary produced {name} != reference"


# ---------------------------------------------------------------------------
# Negative tests: malformed inputs must be rejected (no output written).
# ---------------------------------------------------------------------------


_OMIT = object()


def _write_inputs(directory: Path, *, base: dict[str, Any],
                  namespaces=None, allocations=None, config=None):
    spec = {
        "namespaces.json": namespaces if namespaces is not None else base["namespaces"],
        "allocations.json": allocations if allocations is not None else base["allocations"],
        "config.json": config if config is not None else base["config"],
    }
    for name, payload in spec.items():
        if payload is _OMIT:
            continue
        path = directory / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(dump_canonical(payload), encoding="utf-8")


def _run_binary(in_dir: Path, out_dir: Path) -> subprocess.CompletedProcess:
    out_dir.mkdir(exist_ok=True)
    return subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )


def _assert_rejected_no_output(out_dir: Path, res: subprocess.CompletedProcess):
    assert res.returncode != 0, (
        f"expected non-zero exit, got 0\nstdout={res.stdout}\nstderr={res.stderr}"
    )
    if out_dir.exists():
        extras = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
        assert extras == [], (
            f"binary wrote artifacts under argv[2]={out_dir} despite malformed input: {extras}"
        )


def test_binary_rejects_missing_all_inputs(tmp_path):
    in_dir = tmp_path / "empty_in"
    in_dir.mkdir()
    out_dir = tmp_path / "empty_out"
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("drop", ["namespaces.json", "allocations.json", "config.json"])
def test_binary_rejects_missing_each_input(tmp_path, input_data, drop):
    in_dir = tmp_path / f"drop_{drop}"
    in_dir.mkdir()
    out_dir = tmp_path / f"drop_{drop}_out"
    overrides = {
        "namespaces": _OMIT if drop == "namespaces.json" else None,
        "allocations": _OMIT if drop == "allocations.json" else None,
        "config": _OMIT if drop == "config.json" else None,
    }
    _write_inputs(in_dir, base=input_data, **overrides)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("bad_file", ["namespaces.json", "allocations.json", "config.json"])
def test_binary_rejects_invalid_json(tmp_path, input_data, bad_file):
    in_dir = tmp_path / f"bad_{bad_file}"
    in_dir.mkdir()
    out_dir = tmp_path / f"bad_{bad_file}_out"
    overrides = {
        "namespaces": "{ not json" if bad_file == "namespaces.json" else None,
        "allocations": "{ not json" if bad_file == "allocations.json" else None,
        "config": "{ not json" if bad_file == "config.json" else None,
    }
    _write_inputs(in_dir, base=input_data, **overrides)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_missing_field(tmp_path, input_data):
    bad = {"namespaces": [{"name": "x", "parent": None}]}  # missing limits
    in_dir = tmp_path / "ns_no_lim"
    in_dir.mkdir()
    out_dir = tmp_path / "ns_no_lim_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_no_root(tmp_path, input_data):
    bad = {"namespaces": [{"name": "a", "parent": "b", "limits": {"cpu": 10, "memory": 10, "storage": 10}},
                          {"name": "b", "parent": "a", "limits": {"cpu": 10, "memory": 10, "storage": 10}}]}
    in_dir = tmp_path / "no_root"
    in_dir.mkdir()
    out_dir = tmp_path / "no_root_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_two_roots(tmp_path, input_data):
    bad = {"namespaces": [
        {"name": "r1", "parent": None, "limits": {"cpu": 10, "memory": 10, "storage": 10}},
        {"name": "r2", "parent": None, "limits": {"cpu": 10, "memory": 10, "storage": 10}},
    ]}
    in_dir = tmp_path / "two_roots"
    in_dir.mkdir()
    out_dir = tmp_path / "two_roots_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_undefined_parent(tmp_path, input_data):
    bad = {"namespaces": [
        {"name": "r", "parent": None, "limits": {"cpu": 10, "memory": 10, "storage": 10}},
        {"name": "child", "parent": "ghost", "limits": {"cpu": 5, "memory": 5, "storage": 5}},
    ]}
    in_dir = tmp_path / "ghost_parent"
    in_dir.mkdir()
    out_dir = tmp_path / "ghost_parent_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_cycle(tmp_path, input_data):
    bad = {"namespaces": [
        {"name": "r", "parent": None, "limits": {"cpu": 10, "memory": 10, "storage": 10}},
        {"name": "a", "parent": "b", "limits": {"cpu": 10, "memory": 10, "storage": 10}},
        {"name": "b", "parent": "a", "limits": {"cpu": 10, "memory": 10, "storage": 10}},
    ]}
    in_dir = tmp_path / "cycle"
    in_dir.mkdir()
    out_dir = tmp_path / "cycle_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_namespace_duplicate_name(tmp_path, input_data):
    bad = {"namespaces": [
        {"name": "r", "parent": None, "limits": {"cpu": 10, "memory": 10, "storage": 10}},
        {"name": "r", "parent": None, "limits": {"cpu": 5, "memory": 5, "storage": 5}},
    ]}
    in_dir = tmp_path / "dup_name"
    in_dir.mkdir()
    out_dir = tmp_path / "dup_name_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_negative_limit(tmp_path, input_data):
    bad = {"namespaces": [
        {"name": "r", "parent": None, "limits": {"cpu": -1, "memory": 10, "storage": 10}},
    ]}
    in_dir = tmp_path / "neg_lim"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_lim_out"
    _write_inputs(in_dir, base=input_data, namespaces=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_bad_op(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "namespace": "root", "op": "burn",
                       "resources": {"cpu": 1, "memory": 1, "storage": 1}}]}
    in_dir = tmp_path / "bad_op"
    in_dir.mkdir()
    out_dir = tmp_path / "bad_op_out"
    _write_inputs(in_dir, base=input_data, allocations=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_missing_resources(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "namespace": "root", "op": "allocate"}]}
    in_dir = tmp_path / "no_res"
    in_dir.mkdir()
    out_dir = tmp_path / "no_res_out"
    _write_inputs(in_dir, base=input_data, allocations=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_event_resources_missing_cpu(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "namespace": "root", "op": "allocate",
                       "resources": {"memory": 1, "storage": 1}}]}
    in_dir = tmp_path / "no_cpu"
    in_dir.mkdir()
    out_dir = tmp_path / "no_cpu_out"
    _write_inputs(in_dir, base=input_data, allocations=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_negative_resource(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "namespace": "root", "op": "allocate",
                       "resources": {"cpu": -1, "memory": 1, "storage": 1}}]}
    in_dir = tmp_path / "neg_res"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_res_out"
    _write_inputs(in_dir, base=input_data, allocations=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_duplicate_event_id(tmp_path, input_data):
    bad = {"events": [
        {"event_id": "dup", "ts_unix_ms": 1, "namespace": "root", "op": "allocate",
         "resources": {"cpu": 1, "memory": 1, "storage": 1}},
        {"event_id": "dup", "ts_unix_ms": 2, "namespace": "root", "op": "release",
         "resources": {"cpu": 1, "memory": 1, "storage": 1}},
    ]}
    in_dir = tmp_path / "dup_event"
    in_dir.mkdir()
    out_dir = tmp_path / "dup_event_out"
    _write_inputs(in_dir, base=input_data, allocations=bad)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_missing_now(tmp_path, input_data):
    bad_config = dict(input_data["config"])
    bad_config.pop("now_unix_ms", None)
    in_dir = tmp_path / "no_now"
    in_dir.mkdir()
    out_dir = tmp_path / "no_now_out"
    _write_inputs(in_dir, base=input_data, config=bad_config)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_bad_release_action(tmp_path, input_data):
    bad_config = dict(input_data["config"])
    bad_config["release_unknown_action"] = "wat"
    in_dir = tmp_path / "bad_act"
    in_dir.mkdir()
    out_dir = tmp_path / "bad_act_out"
    _write_inputs(in_dir, base=input_data, config=bad_config)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_config_negative_now(tmp_path, input_data):
    bad_config = dict(input_data["config"])
    bad_config["now_unix_ms"] = -5
    in_dir = tmp_path / "neg_now"
    in_dir.mkdir()
    out_dir = tmp_path / "neg_now_out"
    _write_inputs(in_dir, base=input_data, config=bad_config)
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_binary_rejects_top_level_not_object(tmp_path, input_data):
    in_dir = tmp_path / "arr_top"
    in_dir.mkdir()
    out_dir = tmp_path / "arr_top_out"
    _write_inputs(in_dir, base=input_data, namespaces=[])
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("swap_to_dir", ["namespaces.json", "allocations.json", "config.json"])
def test_binary_rejects_input_path_is_directory(tmp_path, input_data, swap_to_dir):
    """Input file replaced by a (non-empty) directory: open() can never
    succeed. Distinct failure class from "missing" / "invalid JSON",
    and root-safe (no chmod tricks)."""
    in_dir = tmp_path / f"swap_{swap_to_dir}"
    in_dir.mkdir()
    out_dir = tmp_path / f"swap_{swap_to_dir}_out"
    _write_inputs(in_dir, base=input_data)
    target = in_dir / swap_to_dir
    target.unlink()
    target.mkdir()
    (target / "decoy.json").write_text("{}\n")
    res = _run_binary(in_dir, out_dir)
    _assert_rejected_no_output(out_dir, res)


def test_now_unix_ms_does_not_leak_into_outputs(binary_run_outputs):
    """`now_unix_ms` from config.json is informational and must not be
    propagated to any output document (no key named `now_unix_ms`)."""
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        assert '"now_unix_ms"' not in text, (
            f"{p} contains a now_unix_ms key but config.now_unix_ms is informational"
        )

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert k != "now_unix_ms", "unexpected now_unix_ms key in output"
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    for p, doc in binary_run_outputs.items():
        walk(doc)


def test_now_unix_ms_value_change_does_not_affect_outputs(tmp_path, input_data):
    """Bumping `now_unix_ms` while leaving everything else identical must
    yield byte-identical outputs (the field is informational only)."""
    in_a = tmp_path / "now_a"
    in_a.mkdir()
    in_b = tmp_path / "now_b"
    in_b.mkdir()
    out_a = tmp_path / "out_a"
    out_a.mkdir()
    out_b = tmp_path / "out_b"
    out_b.mkdir()
    cfg_a = dict(input_data["config"])
    cfg_b = dict(input_data["config"])
    cfg_b["now_unix_ms"] = int(cfg_a["now_unix_ms"]) + 999_999
    _write_inputs(in_a, base=input_data, config=cfg_a)
    _write_inputs(in_b, base=input_data, config=cfg_b)
    for in_dir, out_dir in [(in_a, out_a), (in_b, out_b)]:
        res = subprocess.run(
            [*_java_cmd(in_dir, out_dir)],
            capture_output=True, text=True, timeout=120,
        )
        assert res.returncode == 0, f"binary failed: {res.stderr}"
    for name in (
        "allocation_decisions.json", "namespace_usage.json",
        "rollup_tree.json", "violations.json", "summary.json",
    ):
        assert (out_a / name).read_bytes() == (out_b / name).read_bytes(), (
            f"changing config.now_unix_ms changed {name}: it must be informational only"
        )


def test_events_processed_in_input_order_not_ts_order(tmp_path, input_data):
    """Events are replayed in the order they appear in `events`,
    independent of `ts_unix_ms`. Forging a descending-ts variant of the
    main dataset must yield the same decisions/usage as the original."""
    in_dir = tmp_path / "shuf_ts_in"
    in_dir.mkdir()
    out_dir = tmp_path / "shuf_ts_out"
    out_dir.mkdir()
    events = [dict(e) for e in input_data["allocations"]["events"]]
    base_ts = 10**14
    for i, ev in enumerate(events):
        ev["ts_unix_ms"] = base_ts - i
    shuffled = {"events": events}
    _write_inputs(in_dir, base=input_data, allocations=shuffled)
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, f"binary failed: {res.stderr}"
    expected = simulate(input_data["namespaces"], shuffled, input_data["config"])
    actual = json.loads((out_dir / "allocation_decisions.json").read_text())
    assert actual == expected["allocation_decisions"], (
        "binary appears to sort events by ts_unix_ms instead of processing in input order"
    )
    canonical_events = input_data["allocations"]["events"]
    if canonical_events:
        canonical_expected = simulate(input_data["namespaces"], input_data["allocations"], input_data["config"])
        decisions_by_id_canonical = {d["event_id"]: (d["decision"], d["reason"])
                                     for d in canonical_expected["allocation_decisions"]["decisions"]}
        decisions_by_id_shuf = {d["event_id"]: (d["decision"], d["reason"])
                                for d in actual["decisions"]}
        assert decisions_by_id_canonical == decisions_by_id_shuf, (
            "decision/reason should depend only on input order, not on ts values"
        )


def test_binary_rejects_when_input_dir_does_not_exist(tmp_path):
    """`internal failure` umbrella: pointing argv[1] at a non-existent
    directory must reject and write nothing under argv[2]."""
    out_dir = tmp_path / "no_in_out"
    res = subprocess.run(
        [*_java_cmd(tmp_path / "definitely_not_there", out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    _assert_rejected_no_output(out_dir, res)


@pytest.mark.parametrize("blocker_name", [
    "allocation_decisions.json",
    "namespace_usage.json",
    "rollup_tree.json",
    "violations.json",
    "summary.json",
])
def test_binary_atomic_writes_when_target_blocked_by_directory(tmp_path, input_data, blocker_name):
    """Force a rename-time failure by pre-creating each of the five
    output filenames (one per parametrization) as a non-empty
    directory under argv[2]. The binary must exit non-zero and leave
    argv[2] with only the pre-existing blocker directory -- no
    .partial leftovers, and none of the OTHER four outputs persisted
    (atomic-write semantics)."""
    in_dir = tmp_path / f"good_in_atomic_{blocker_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"blocked_out_{blocker_name}"
    out_dir.mkdir()
    blocker = out_dir / blocker_name
    blocker.mkdir()
    (blocker / "decoy").write_text("not your file")
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with pre-existing blocker {blocker}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name], (
        f"non-atomic write (blocker={blocker_name}): argv[2] {out_dir} "
        f"contains stray artifacts {entries}"
    )
    assert blocker.is_dir()
    assert (blocker / "decoy").read_text() == "not your file"


def test_binary_atomic_writes_when_target_blocked_by_empty_directory(tmp_path, input_data):
    """Same as the parametrized blocker test above, but the blocker is
    an EMPTY directory (vs a non-empty one). POSIX rename(2) refuses
    to replace a directory target with a regular file (EISDIR), so
    the binary must reject and remove all already-committed siblings.
    Validates that the atomic-write cleanup is not predicated on the
    blocker's contents."""
    in_dir = tmp_path / "good_in_empty_blocker"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "empty_blocked_out"
    out_dir.mkdir()
    blocker_name = "rollup_tree.json"
    blocker = out_dir / blocker_name
    blocker.mkdir()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with empty-dir blocker at {blocker}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name], (
        f"non-atomic write (empty-dir blocker): argv[2] {out_dir} contains stray artifacts {entries}"
    )
    assert blocker.is_dir()


def test_binary_atomic_cleanup_propagates_to_already_committed_siblings(tmp_path, input_data):
    """Block the alphabetically LAST canonical output name with a
    non-empty directory. A naive implementation that renames each
    `.partial` immediately after writing it will have already
    committed the first four outputs by the time the fifth rename
    fails. The atomic-write contract demands that those four
    already-renamed siblings be removed before exit, leaving only the
    pre-existing blocker. This is the strongest probe of the
    cross-step cleanup discipline."""
    in_dir = tmp_path / "good_in_late"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "late_blocker_out"
    out_dir.mkdir()
    blocker_name = "violations.json"
    blocker = out_dir / blocker_name
    blocker.mkdir()
    (blocker / "decoy").write_text("keep me")
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode != 0, (
        f"binary unexpectedly succeeded with late blocker at {blocker}\n"
        f"stdout={res.stdout}\nstderr={res.stderr}"
    )
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name], (
        f"cross-step atomic cleanup failed: argv[2] {out_dir} should retain only "
        f"the blocker but contains {entries} (already-committed siblings not cleaned up)"
    )
    assert blocker.is_dir()
    assert (blocker / "decoy").read_text() == "keep me"


def test_binary_leaves_no_stray_temporary_files_on_success(tmp_path, input_data):
    """After a clean successful run, argv[2] must contain exactly the
    five canonical output files and zero staging / scratch
    artifacts (no `.partial`, `.tmp`, `.swp`, hidden, or otherwise
    unexpected entries). This is a complement to the rename-time
    atomicity test: even on the happy path the binary must clean up
    after itself."""
    in_dir = tmp_path / "good_in_clean"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "clean_out"
    out_dir.mkdir()
    res = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, f"binary failed: {res.stderr}"
    expected_names = {
        "allocation_decisions.json",
        "namespace_usage.json",
        "rollup_tree.json",
        "violations.json",
        "summary.json",
    }
    entries = {p.name for p in out_dir.iterdir()}
    assert entries == expected_names, (
        f"binary left stray files in argv[2] after a successful run: {entries - expected_names}; "
        f"missing: {expected_names - entries}"
    )
