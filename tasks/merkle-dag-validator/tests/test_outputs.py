"""Tests for rust-merkle-dag-validator."""
import hashlib
import json
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path("/app")
OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "validation_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


# ===============================================================================
# Section 1: Rust Binary Verification
# ===============================================================================


def test_rust_binary_exists():
    """Verify the compiled Rust binary exists."""
    binary = ROOT / "target" / "release" / "merkle-dag-validator"
    if not binary.is_file():
        binary = ROOT / "target" / "debug" / "merkle-dag-validator"
    assert binary.is_file(), (
        "Rust binary not found. The solution must be built with cargo build."
    )


def test_cargo_lock_exists():
    """Verify Rust dependencies were resolved via Cargo."""
    lock = ROOT / "Cargo.lock"
    assert lock.is_file(), (
        "Cargo.lock missing -- Rust dependencies were not installed."
    )


def test_rust_build_artifacts():
    """Verify Cargo produced build artifacts in target/."""
    target_dir = ROOT / "target"
    assert target_dir.is_dir(), (
        "target/ directory missing -- Rust code was never compiled."
    )


def test_binary_produces_report():
    """Re-run the binary and verify it regenerates the report correctly."""
    report_path = OUT_DIR / "validation_report.json"
    report_path.unlink(missing_ok=True)
    binary = ROOT / "target" / "release" / "merkle-dag-validator"
    if not binary.is_file():
        binary = ROOT / "target" / "debug" / "merkle-dag-validator"
    result = subprocess.run([str(binary)], capture_output=True, timeout=30)
    assert result.returncode == 0, f"Binary failed: {result.stderr.decode()}"
    assert report_path.is_file(), "Binary did not produce validation_report.json"


# ===============================================================================
# Section 2: Top-Level Structure
# ===============================================================================


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "validation_report.json").is_file()


def test_top_level_keys():
    """Verify the output contains all required top-level keys."""
    required = {"metadata", "nodes", "findings", "summary"}
    assert set(R.keys()) == required, f"Keys mismatch: got {sorted(R.keys())}"


def test_metadata_fields():
    """Verify metadata contains all required fields."""
    required = {"total_nodes", "total_edges", "root_count", "leaf_count", "max_depth"}
    assert set(R["metadata"].keys()) == required


def test_metadata_total_nodes():
    """Verify total node count is 20."""
    assert R["metadata"]["total_nodes"] == 20


def test_metadata_total_edges():
    """Verify total edge count matches the input (30 edges)."""
    assert R["metadata"]["total_edges"] == 30


def test_metadata_root_count():
    """Verify there are exactly 2 root nodes."""
    assert R["metadata"]["root_count"] == 2


def test_metadata_leaf_count():
    """Verify the correct number of leaf nodes."""
    leaves = [n for n in R["nodes"] if n["is_leaf"]]
    assert len(leaves) == R["metadata"]["leaf_count"]


# ===============================================================================
# Section 3: Depth Computation (catches BFS shortest-path bug)
# ===============================================================================


def test_root_depths():
    """Root nodes must have depth 0."""
    roots = [n for n in R["nodes"] if n["is_root"]]
    for root in roots:
        assert root["depth"] == 0, f"Root {root['id']} has depth {root['depth']}"


def test_n13_depth_is_3():
    """n13 depth must be 3 (longest path via n01->n03->n07->n13), not 1 (shortcut)."""
    n13 = next(n for n in R["nodes"] if n["id"] == "n13")
    assert n13["depth"] == 3, (
        f"n13 depth is {n13['depth']}; expected 3 (longest path). "
        "BFS gives 1 via the shortcut edge n01->n13."
    )


def test_n16_depth_is_3():
    """n16 depth must be 3 (longest path), not 1 (shortcut n02->n16)."""
    n16 = next(n for n in R["nodes"] if n["id"] == "n16")
    assert n16["depth"] == 3, (
        f"n16 depth is {n16['depth']}; expected 3 (longest path). "
        "BFS gives 1 via the shortcut edge n02->n16."
    )


def test_n20_depth_is_4():
    """n20 depth must be 4 (deepest node), not 2 (from BFS via shortcut to n13)."""
    n20 = next(n for n in R["nodes"] if n["id"] == "n20")
    assert n20["depth"] == 4, (
        f"n20 depth is {n20['depth']}; expected 4 (longest path n01->n03->n07->n13->n20). "
        "BFS gives 2 via shortcut."
    )


def test_max_depth_is_4():
    """The maximum depth across all nodes must be 4."""
    assert R["metadata"]["max_depth"] == 4, (
        f"max_depth is {R['metadata']['max_depth']}; expected 4"
    )


def test_intermediate_depths():
    """Nodes at layer 2 (n07-n12) must have depth 2."""
    layer2_ids = ["n07", "n08", "n09", "n10", "n11", "n12"]
    for nid in layer2_ids:
        node = next(n for n in R["nodes"] if n["id"] == nid)
        assert node["depth"] == 2, (
            f"{nid} depth is {node['depth']}; expected 2"
        )


# ===============================================================================
# Section 4: Repair Cost (catches sum-vs-max bug)
# ===============================================================================


def test_n07_repair_cost():
    """n07 repair cost: weight(5) + max(repair(n13)=11, repair(n14)=9) = 16."""
    n07 = next(n for n in R["nodes"] if n["id"] == "n07")
    assert n07["repair_cost"] == 16, (
        f"n07 repair_cost is {n07['repair_cost']}; expected 16 (parallel: 5+max(11,9)). "
        "Sum model gives 25 (5+11+9)."
    )


def test_n08_repair_cost():
    """n08 repair cost: weight(9) + max(repair(n14)=9, repair(n15)=2) = 18."""
    n08 = next(n for n in R["nodes"] if n["id"] == "n08")
    assert n08["repair_cost"] == 18, (
        f"n08 repair_cost is {n08['repair_cost']}; expected 18 (parallel: 9+max(9,2)). "
        "Sum model gives 20."
    )


def test_n01_repair_cost():
    """n01 repair cost: weight(10) + max(23, 24, 17, 11) = 34."""
    n01 = next(n for n in R["nodes"] if n["id"] == "n01")
    assert n01["repair_cost"] == 34, (
        f"n01 repair_cost is {n01['repair_cost']}; expected 34 (parallel model). "
        "Sum model gives 143."
    )


def test_n04_repair_cost():
    """n04 repair cost: weight(6) + max(repair(n08)=18, repair(n09)=6, repair(n10)=9) = 24."""
    n04 = next(n for n in R["nodes"] if n["id"] == "n04")
    assert n04["repair_cost"] == 24, (
        f"n04 repair_cost is {n04['repair_cost']}; expected 24"
    )


def test_leaf_repair_cost_equals_weight():
    """Leaf nodes have repair_cost = weight (no children to add)."""
    weights = json.loads((DATA_DIR / "weights.json").read_text())
    leaves = [n for n in R["nodes"] if n["is_leaf"]]
    for leaf in leaves:
        expected = weights[leaf["id"]]
        assert leaf["repair_cost"] == expected, (
            f"Leaf {leaf['id']} repair_cost={leaf['repair_cost']}; expected weight={expected}"
        )


# ===============================================================================
# Section 5: Validation / Findings (catches single-child skip bug)
# ===============================================================================


def test_corrupted_count_is_3():
    """Exactly 3 nodes have corrupted hashes (n08, n11, n20)."""
    assert R["summary"]["corrupted_count"] == 3, (
        f"corrupted_count is {R['summary']['corrupted_count']}; expected 3. "
        "All nodes with non-CORRECT declared_hash must be flagged."
    )


def test_n20_in_findings():
    """n20 must be in findings -- it has a corrupted hash (leaf node, no exemption)."""
    finding_ids = [f["node_id"] for f in R["findings"]]
    assert "n20" in finding_ids, (
        "n20 missing from findings. ALL nodes must be validated regardless of child count."
    )


def test_n08_in_findings():
    """n08 must be in findings -- it has a corrupted hash."""
    finding_ids = [f["node_id"] for f in R["findings"]]
    assert "n08" in finding_ids


def test_n11_in_findings():
    """n11 must be in findings -- it has a corrupted hash."""
    finding_ids = [f["node_id"] for f in R["findings"]]
    assert "n11" in finding_ids


def test_no_false_positives():
    """Only the 3 intentionally corrupted nodes should be in findings."""
    finding_ids = set(f["node_id"] for f in R["findings"])
    expected = {"n08", "n11", "n20"}
    assert finding_ids == expected, (
        f"Findings contain {finding_ids}; expected exactly {expected}"
    )


def test_all_findings_are_critical():
    """All hash_mismatch findings should have severity 'critical'."""
    for f in R["findings"]:
        assert f["severity"] == "critical", (
            f"Finding for {f['node_id']} has severity '{f['severity']}'; expected 'critical'"
        )


# ===============================================================================
# Section 6: Findings Sort Order (catches depth ASC vs DESC bug)
# ===============================================================================


def test_findings_sorted_depth_desc():
    """Findings must be sorted by depth descending (deeper nodes first)."""
    if len(R["findings"]) < 2:
        pytest.skip("Need multiple findings to test sort order")
    depths = [f["depth"] for f in R["findings"]]
    for i in range(len(depths) - 1):
        if R["findings"][i]["severity_rank"] == R["findings"][i + 1]["severity_rank"]:
            assert depths[i] >= depths[i + 1], (
                f"Findings not sorted depth DESC: {depths}. "
                f"Node {R['findings'][i]['node_id']}(depth={depths[i]}) before "
                f"{R['findings'][i+1]['node_id']}(depth={depths[i+1]})"
            )


def test_n20_is_first_finding():
    """n20 (depth 4) should appear before n08 and n11 (depth 2) in findings."""
    assert R["findings"][0]["node_id"] == "n20", (
        f"First finding is {R['findings'][0]['node_id']}; expected n20 (deepest at depth 4). "
        "Findings must be sorted by depth descending."
    )


# ===============================================================================
# Section 7: Hash Computation (catches sort-by-id vs sort-by-hash bug)
# ===============================================================================


def test_leaf_hash_computation():
    """Verify leaf node hashes are computed correctly (not affected by sort bug)."""
    hash_params = json.loads((DATA_DIR / "hash_params.json").read_text())
    salt = hash_params["salt_prefix"]
    sep = hash_params["separator"]
    leaf_marker = hash_params["leaf_marker"]

    n15 = next(n for n in R["nodes"] if n["id"] == "n15")
    hash_input = f"{salt}{sep}n15{sep}cert-validator{sep}{leaf_marker}"
    expected = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
    assert n15["computed_hash"] == expected, (
        f"n15 computed_hash wrong: got {n15['computed_hash']}, expected {expected}"
    )


def test_leaf_hash_n20():
    """Verify n20 (leaf) hash is computed correctly."""
    hash_params = json.loads((DATA_DIR / "hash_params.json").read_text())
    salt = hash_params["salt_prefix"]
    sep = hash_params["separator"]
    leaf_marker = hash_params["leaf_marker"]

    n20 = next(n for n in R["nodes"] if n["id"] == "n20")
    hash_input = f"{salt}{sep}n20{sep}nonce-gen{sep}{leaf_marker}"
    expected = hashlib.sha256(hash_input.encode()).hexdigest()[:32]
    assert n20["computed_hash"] == expected, (
        f"n20 computed_hash wrong: got {n20['computed_hash']}, expected {expected}"
    )


def test_internal_node_hash_sorted_by_hash_value():
    """Verify an internal node's hash uses children sorted by hash value, not by ID.

    Node n14 has one child (n20), so sort order doesn't matter for n14.
    Node n13 has one child (n20), so sort order doesn't matter for n13.
    Node n07 has children n13 and n14. Their hashes may sort differently than their IDs.
    We verify n07's hash is computed with children sorted by hash value.
    """
    hash_params = json.loads((DATA_DIR / "hash_params.json").read_text())
    salt = hash_params["salt_prefix"]
    sep = hash_params["separator"]
    join_str = hash_params["children_join"]
    leaf_marker = hash_params["leaf_marker"]

    # First compute n20's hash (leaf)
    n20_input = f"{salt}{sep}n20{sep}nonce-gen{sep}{leaf_marker}"
    n20_hash = hashlib.sha256(n20_input.encode()).hexdigest()[:32]

    # n13 has child n20 (single child, sorted trivially)
    n13_input = f"{salt}{sep}n13{sep}hash-engine{sep}{n20_hash}"
    n13_hash = hashlib.sha256(n13_input.encode()).hexdigest()[:32]

    # n14 has child n20 (single child, sorted trivially)
    n14_input = f"{salt}{sep}n14{sep}key-derivation{sep}{n20_hash}"
    n14_hash = hashlib.sha256(n14_input.encode()).hexdigest()[:32]

    # n07 has children n13, n14. Sort by HASH VALUE (not by ID).
    children_hashes = sorted([n13_hash, n14_hash])
    n07_input = f"{salt}{sep}n07{sep}user-store{sep}{join_str.join(children_hashes)}"
    n07_expected = hashlib.sha256(n07_input.encode()).hexdigest()[:32]

    n07 = next(n for n in R["nodes"] if n["id"] == "n07")
    assert n07["computed_hash"] == n07_expected, (
        f"n07 computed_hash wrong: got {n07['computed_hash']}, expected {n07_expected}. "
        "Children must be sorted by hash value, not by node ID."
    )


def test_n03_hash_uses_hash_sorted_children():
    """Verify n03's hash sorts children (n07, n08) by their hash values."""
    hash_params = json.loads((DATA_DIR / "hash_params.json").read_text())
    salt = hash_params["salt_prefix"]
    sep = hash_params["separator"]
    join_str = hash_params["children_join"]
    leaf_marker = hash_params["leaf_marker"]

    # Build up from leaves
    n20_input = f"{salt}{sep}n20{sep}nonce-gen{sep}{leaf_marker}"
    n20_hash = hashlib.sha256(n20_input.encode()).hexdigest()[:32]

    n15_input = f"{salt}{sep}n15{sep}cert-validator{sep}{leaf_marker}"
    n15_hash = hashlib.sha256(n15_input.encode()).hexdigest()[:32]

    n13_input = f"{salt}{sep}n13{sep}hash-engine{sep}{n20_hash}"
    n13_hash = hashlib.sha256(n13_input.encode()).hexdigest()[:32]

    n14_input = f"{salt}{sep}n14{sep}key-derivation{sep}{n20_hash}"
    n14_hash = hashlib.sha256(n14_input.encode()).hexdigest()[:32]

    # n07: children n13, n14 -- sort by hash value
    n07_children = sorted([n13_hash, n14_hash])
    n07_input = f"{salt}{sep}n07{sep}user-store{sep}{join_str.join(n07_children)}"
    n07_hash = hashlib.sha256(n07_input.encode()).hexdigest()[:32]

    # n08: children n14, n15 -- sort by hash value
    n08_children = sorted([n14_hash, n15_hash])
    n08_input = f"{salt}{sep}n08{sep}session-mgr{sep}{join_str.join(n08_children)}"
    n08_hash = hashlib.sha256(n08_input.encode()).hexdigest()[:32]

    # n03: children n07, n08 -- sort by hash value
    n03_children = sorted([n07_hash, n08_hash])
    n03_input = f"{salt}{sep}n03{sep}auth-module{sep}{join_str.join(n03_children)}"
    n03_expected = hashlib.sha256(n03_input.encode()).hexdigest()[:32]

    n03 = next(n for n in R["nodes"] if n["id"] == "n03")
    assert n03["computed_hash"] == n03_expected, (
        f"n03 computed_hash wrong: got {n03['computed_hash']}, expected {n03_expected}"
    )


# ===============================================================================
# Section 8: Summary Verification
# ===============================================================================


def test_summary_integrity_ratio():
    """All 20 nodes are reachable from roots, so integrity_ratio = 1.0."""
    assert abs(R["summary"]["integrity_ratio"] - 1.0) < FLOAT_TOL, (
        f"integrity_ratio is {R['summary']['integrity_ratio']}; expected 1.0"
    )


def test_summary_deep_node_count():
    """Nodes with depth > max_depth threshold (3): only n20 at depth 4."""
    assert R["summary"]["deep_node_count"] == 1, (
        f"deep_node_count is {R['summary']['deep_node_count']}; expected 1 (only n20 at depth 4)"
    )


def test_summary_avg_depth():
    """Average depth across all 20 nodes with correct longest-path depths."""
    # Correct depths: 0,0,1,1,1,1,2,2,2,2,2,2,3,3,3,3,3,3,3,4 = 41
    # avg = 41/20 = 2.05
    expected_avg = 41.0 / 20.0
    assert abs(R["summary"]["avg_depth"] - expected_avg) < FLOAT_TOL, (
        f"avg_depth is {R['summary']['avg_depth']}; expected {expected_avg}"
    )


def test_summary_total_repair_cost():
    """Total repair cost = sum of repair costs for corrupted nodes (n08 + n11 + n20)."""
    # n08=18, n11=10, n20=4 -> total=32
    assert R["summary"]["total_repair_cost"] == 32, (
        f"total_repair_cost is {R['summary']['total_repair_cost']}; expected 32"
    )


def test_summary_max_repair_cost():
    """Max repair cost among corrupted nodes = max(18, 10, 4) = 18."""
    assert R["summary"]["max_repair_cost"] == 18, (
        f"max_repair_cost is {R['summary']['max_repair_cost']}; expected 18"
    )


# ===============================================================================
# Section 9: Node Array Verification
# ===============================================================================


def test_nodes_sorted_by_id():
    """Node entries must be sorted by id ascending."""
    ids = [n["id"] for n in R["nodes"]]
    assert ids == sorted(ids), "Nodes not sorted by id"


def test_all_nodes_reachable():
    """All 20 nodes should be reachable from the two roots."""
    for node in R["nodes"]:
        assert node["reachable"] is True, (
            f"Node {node['id']} marked unreachable; all nodes are reachable from roots"
        )


def test_node_count_is_20():
    """There must be exactly 20 nodes in the output."""
    assert len(R["nodes"]) == 20


# ===============================================================================
# Section 10: Float Value Verification
# ===============================================================================


def test_float_value_integrity_ratio():
    """integrity_ratio must equal 1.0 (all nodes reachable)."""
    assert abs(R["summary"]["integrity_ratio"] - 1.0) < 1e-9, (
        f"integrity_ratio is {R['summary']['integrity_ratio']}; expected 1.0"
    )


def test_float_value_avg_depth():
    """avg_depth must equal 2.05 (sum of depths 41 / 20 nodes)."""
    assert abs(R["summary"]["avg_depth"] - 2.05) < 1e-9, (
        f"avg_depth is {R['summary']['avg_depth']}; expected 2.05"
    )
