"""Tests for js-crdt-merge-resolver-hard."""
import json
import hashlib
import pathlib
import re

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')


def load_report():
    """Load and return the main output JSON report."""
    p = OUT_DIR / "merge_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


# ─── Structure tests ─────────────────────────────────────────────────────────


def test_output_file_exists():
    """Verify the main output file was created."""
    assert (OUT_DIR / "merge_report.json").is_file()


def test_top_level_keys():
    """Verify the output contains all required top-level keys."""
    required = {"anomalies", "convergence", "key_states", "merged_log", "metadata", "summary"}
    assert set(R.keys()) == required, f"Keys mismatch: got {sorted(R.keys())}"


def test_metadata_keys():
    """Verify metadata contains all required fields."""
    required = {"replica_ids", "total_operations", "total_replicas", "unique_keys"}
    assert set(R["metadata"].keys()) == required


def test_summary_keys():
    """Verify summary contains all required fields."""
    required = {
        "active_keys", "anomalies_by_type", "state_hash",
        "tombstoned_keys", "total_anomalies", "total_conflicts", "total_keys"
    }
    assert set(R["summary"].keys()) == required


def test_anomalies_by_type_keys():
    """Verify anomalies_by_type contains all anomaly type counts."""
    required = {"causal_violation", "clock_regression", "concurrent_write", "resurrection"}
    assert set(R["summary"]["anomalies_by_type"].keys()) == required


# ─── Metadata tests ──────────────────────────────────────────────────────────


def test_total_replicas():
    """Verify correct replica count."""
    assert R["metadata"]["total_replicas"] == 4


def test_total_operations():
    """Verify total operation count (8+8+7+6 = 29)."""
    assert R["metadata"]["total_operations"] == 29


def test_replica_ids_sorted():
    """Verify replica IDs are sorted alphabetically."""
    ids = R["metadata"]["replica_ids"]
    assert ids == sorted(ids)
    assert ids == ["alpha", "beta", "delta", "gamma"]


def test_unique_keys():
    """Verify count of unique keys across all replicas."""
    assert R["metadata"]["unique_keys"] == 11


# ─── Merged log tests ────────────────────────────────────────────────────────


def test_merged_log_length():
    """Verify merged log has all operations."""
    assert len(R["merged_log"]) == 29


def test_merged_log_sort_order():
    """Verify merged log is sorted by lamport_ts, then replica_id, then op_id."""
    log = R["merged_log"]
    for i in range(len(log) - 1):
        a, b = log[i], log[i + 1]
        key_a = (a["lamport_ts"], a["replica_id"], a["op_id"])
        key_b = (b["lamport_ts"], b["replica_id"], b["op_id"])
        assert key_a <= key_b, f"Sort violation at index {i}: {key_a} > {key_b}"


def test_merged_log_first_entries():
    """Verify first entries at lamport_ts=1."""
    ts1_ops = [op for op in R["merged_log"] if op["lamport_ts"] == 1]
    assert len(ts1_ops) == 2
    assert ts1_ops[0]["replica_id"] == "alpha"
    assert ts1_ops[1]["replica_id"] == "delta"


def test_merged_log_entry_keys():
    """Verify each merged log entry has correct keys."""
    required = {"key", "lamport_ts", "op_id", "op_type", "replica_id",
                "value", "vector_clock", "wall_clock_ms"}
    for entry in R["merged_log"]:
        assert set(entry.keys()) == required


def test_merged_log_vector_clocks_sorted():
    """Verify vector clock keys are sorted in each entry."""
    for entry in R["merged_log"]:
        vc = entry["vector_clock"]
        keys = list(vc.keys())
        assert keys == sorted(keys), (
            f"Vector clock keys unsorted in {entry['op_id']}: {keys}"
        )


# ─── Key state tests ─────────────────────────────────────────────────────────


def test_key_states_length():
    """Verify number of unique keys in key_states."""
    assert len(R["key_states"]) == 11


def test_key_states_sorted():
    """Verify key_states are sorted by key."""
    keys = [ks["key"] for ks in R["key_states"]]
    assert keys == sorted(keys)


def test_key_states_entry_keys():
    """Verify each key_state entry has correct fields."""
    required = {"conflict_count", "final_op_id", "final_value",
                "is_tombstoned", "key", "write_count"}
    for ks in R["key_states"]:
        assert set(ks.keys()) == required


def test_lww_user_1001():
    """Verify LWW for user:1001: ts=5 three-way tie, delta>beta>alpha wins."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1001")
    assert ks["final_op_id"] == "delta-006"
    assert ks["final_value"] == "Alice-D"
    assert ks["is_tombstoned"] is False
    assert ks["write_count"] == 5


def test_lww_user_1003_resurrection():
    """Verify user:1003 is resurrected (gamma-006 at ts=16 after DELETE at ts=11)."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1003")
    assert ks["final_op_id"] == "gamma-006"
    assert ks["final_value"] == "Charlie-Resurrected"
    assert ks["is_tombstoned"] is False


def test_lww_config_theme():
    """Verify config:theme resolved by LWW (gamma-005 at ts=15 wins)."""
    ks = next(k for k in R["key_states"] if k["key"] == "config:theme")
    assert ks["final_op_id"] == "gamma-005"
    assert ks["final_value"] == "auto"
    assert ks["is_tombstoned"] is False


def test_lww_config_lang_tie_breaking():
    """Verify config:lang LWW tie-breaking (ts=14 for both alpha-008 and gamma-007).

    With equal lamport_ts, higher replica_id wins: gamma > alpha.
    """
    ks = next(k for k in R["key_states"] if k["key"] == "config:lang")
    assert ks["final_op_id"] == "gamma-007"
    assert ks["final_value"] == "fr-FR"


def test_lww_counter_visits():
    """Verify counter:visits (alpha-006 at ts=10 ties with beta-006 at ts=10).

    Higher replica_id wins: beta > alpha.
    """
    ks = next(k for k in R["key_states"] if k["key"] == "counter:visits")
    assert ks["final_op_id"] == "beta-006"
    assert ks["final_value"] == "38"


def test_lww_user_1007_resurrection():
    """Verify user:1007 resurrected (delta-004 SET ts=7 > delta-003 DELETE ts=6)."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1007")
    assert ks["final_op_id"] == "delta-004"
    assert ks["final_value"] == "Grace-Reborn"
    assert ks["is_tombstoned"] is False


def test_lww_config_timeout():
    """Verify config:timeout (only one op, delta-005)."""
    ks = next(k for k in R["key_states"] if k["key"] == "config:timeout")
    assert ks["final_op_id"] == "delta-005"
    assert ks["final_value"] == "3000"
    assert ks["write_count"] == 1
    assert ks["conflict_count"] == 0


def test_user_1001_write_count():
    """user:1001 has operations from alpha(2), beta(2), delta(1) = 5 writes."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1001")
    assert ks["write_count"] == 5


def test_user_1003_write_count():
    """user:1003: beta-002, gamma-001, alpha-005, beta-005, gamma-003, gamma-006 = 6."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1003")
    assert ks["write_count"] == 6


def test_no_tombstoned_keys_in_final():
    """No key should be tombstoned in final state (all tombstones are resurrected)."""
    for ks in R["key_states"]:
        assert ks["is_tombstoned"] is False, f"Key {ks['key']} unexpectedly tombstoned"


# ─── Conflict count tests ────────────────────────────────────────────────────


def test_user_1001_conflict_count():
    """user:1001 has 4 concurrent pairs (verified via vector clock analysis)."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1001")
    assert ks["conflict_count"] == 4


def test_counter_visits_conflict_count():
    """counter:visits has 5 concurrent pairs."""
    ks = next(k for k in R["key_states"] if k["key"] == "counter:visits")
    assert ks["conflict_count"] == 5


def test_config_theme_conflict_count():
    """config:theme has 1 concurrent pair (alpha-004 vs beta-004)."""
    ks = next(k for k in R["key_states"] if k["key"] == "config:theme")
    assert ks["conflict_count"] == 1


def test_config_lang_conflict_count():
    """config:lang has 3 concurrent pairs (all three ops are mutually concurrent)."""
    ks = next(k for k in R["key_states"] if k["key"] == "config:lang")
    assert ks["conflict_count"] == 3


def test_user_1003_conflict_count():
    """user:1003 has 1 concurrent pair (beta-002 vs gamma-001)."""
    ks = next(k for k in R["key_states"] if k["key"] == "user:1003")
    assert ks["conflict_count"] == 1


# ─── Anomaly tests ───────────────────────────────────────────────────────────


def test_anomalies_is_list():
    """Verify anomalies is a list."""
    assert isinstance(R["anomalies"], list)


def test_anomaly_entry_keys():
    """Verify each anomaly has the correct fields."""
    required = {"description", "key", "op_ids", "type"}
    for anomaly in R["anomalies"]:
        assert set(anomaly.keys()) == required


def test_anomalies_sorted():
    """Verify anomalies are sorted by type, then first op_id."""
    for i in range(len(R["anomalies"]) - 1):
        a = R["anomalies"][i]
        b = R["anomalies"][i + 1]
        key_a = (a["type"], a["op_ids"][0] if a["op_ids"] else "")
        key_b = (b["type"], b["op_ids"][0] if b["op_ids"] else "")
        assert key_a <= key_b, f"Anomaly sort violation: {key_a} > {key_b}"


def test_concurrent_write_count():
    """Verify total concurrent_write anomalies = 14."""
    assert R["summary"]["anomalies_by_type"]["concurrent_write"] == 14


def test_resurrection_count():
    """Verify 3 resurrection anomalies (user:1003 x2, user:1007 x1)."""
    assert R["summary"]["anomalies_by_type"]["resurrection"] == 3


def test_clock_regression_count():
    """Verify 2 clock regression anomalies (delta and gamma)."""
    assert R["summary"]["anomalies_by_type"]["clock_regression"] == 2


def test_causal_violation_count():
    """Verify 1 causal violation: alpha-005 -> beta-005 on user:1003."""
    assert R["summary"]["anomalies_by_type"]["causal_violation"] == 1


def test_causal_violation_details():
    """Verify causal violation involves alpha-005 and beta-005 on key user:1003.

    alpha-005 (wall=8000) happens-before beta-005 (wall=7200).
    7200 < 8000 - 500 = 7500, so causal violation.
    """
    cvs = [a for a in R["anomalies"] if a["type"] == "causal_violation"]
    assert len(cvs) == 1
    assert cvs[0]["key"] == "user:1003"
    assert "alpha-005" in cvs[0]["op_ids"]
    assert "beta-005" in cvs[0]["op_ids"]


def test_resurrection_keys():
    """Verify resurrection anomalies exist for user:1003 and user:1007."""
    resurrections = [a for a in R["anomalies"] if a["type"] == "resurrection"]
    resurrection_keys = [a["key"] for a in resurrections]
    assert resurrection_keys.count("user:1003") == 2
    assert resurrection_keys.count("user:1007") == 1


def test_resurrection_user_1003_ops():
    """Verify user:1003 resurrections by beta-005 and gamma-006."""
    resurrections = [a for a in R["anomalies"]
                     if a["type"] == "resurrection" and a["key"] == "user:1003"]
    op_ids = [a["op_ids"][0] for a in resurrections]
    assert "beta-005" in op_ids
    assert "gamma-006" in op_ids


def test_resurrection_user_1007_op():
    """Verify user:1007 resurrection by delta-004."""
    resurrections = [a for a in R["anomalies"]
                     if a["type"] == "resurrection" and a["key"] == "user:1007"]
    assert len(resurrections) == 1
    assert "delta-004" in resurrections[0]["op_ids"]


def test_clock_regression_delta():
    """Verify delta clock regression (delta-005 wall=9000 -> delta-006 wall=5100)."""
    regressions = [a for a in R["anomalies"] if a["type"] == "clock_regression"]
    delta_reg = [a for a in regressions
                 if "delta-005" in a["op_ids"] and "delta-006" in a["op_ids"]]
    assert len(delta_reg) == 1


def test_clock_regression_gamma():
    """Verify gamma clock regression (gamma-006 wall=16000 -> gamma-007 wall=14800)."""
    regressions = [a for a in R["anomalies"] if a["type"] == "clock_regression"]
    gamma_reg = [a for a in regressions
                 if "gamma-006" in a["op_ids"] and "gamma-007" in a["op_ids"]]
    assert len(gamma_reg) == 1


def test_no_spurious_anomaly_types():
    """Verify no unexpected anomaly types appear."""
    valid_types = {"causal_violation", "clock_regression",
                   "concurrent_write", "resurrection"}
    for anomaly in R["anomalies"]:
        assert anomaly["type"] in valid_types


def test_total_anomaly_count():
    """Verify total anomalies = 14 + 3 + 2 + 1 = 20."""
    assert R["summary"]["total_anomalies"] == 20
    assert len(R["anomalies"]) == 20


# ─── Summary tests ───────────────────────────────────────────────────────────


def test_summary_total_keys():
    """Verify summary total keys matches key_states length."""
    assert R["summary"]["total_keys"] == len(R["key_states"])
    assert R["summary"]["total_keys"] == 11


def test_summary_active_plus_tombstoned():
    """Verify active_keys + tombstoned_keys = total_keys."""
    s = R["summary"]
    assert s["active_keys"] + s["tombstoned_keys"] == s["total_keys"]


def test_summary_active_keys():
    """All keys are active (no final tombstones)."""
    assert R["summary"]["active_keys"] == 11
    assert R["summary"]["tombstoned_keys"] == 0


def test_summary_total_anomalies():
    """Verify total_anomalies matches anomaly list length."""
    assert R["summary"]["total_anomalies"] == len(R["anomalies"])


def test_summary_total_conflicts():
    """Verify total_conflicts is sum of all key conflict_counts = 14."""
    expected = sum(ks["conflict_count"] for ks in R["key_states"])
    assert R["summary"]["total_conflicts"] == expected
    assert R["summary"]["total_conflicts"] == 14


# ─── State hash tests ────────────────────────────────────────────────────────


def test_state_hash_format():
    """Verify state_hash is a 64-char lowercase hex string."""
    h = R["summary"]["state_hash"]
    assert len(h) == 64
    assert h == h.lower()
    assert all(c in "0123456789abcdef" for c in h)


def test_state_hash_correct():
    """Verify state hash matches recomputation from key_states."""
    active = sorted(
        [ks for ks in R["key_states"] if not ks["is_tombstoned"]],
        key=lambda x: x["key"]
    )
    hash_input = ""
    for ks in active:
        hash_input += f"{ks['key']}={ks['final_value']}\n"

    expected = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()
    assert R["summary"]["state_hash"] == expected


def test_state_hash_value():
    """Verify state hash matches known-good value."""
    assert R["summary"]["state_hash"] == (
        "24c2a098bcb8444474d31d3994c1ef48a3493ce4a196071ec4ba33e4502e9b2d"
    )


# ─── JSON formatting tests ───────────────────────────────────────────────────


def test_json_two_space_indent():
    """Verify output uses 2-space indentation with sorted keys.

    Note: convergence floats use 6-decimal format (0.650000 not 0.65),
    so we verify structure matches after re-parsing (values equal).
    """
    raw = (OUT_DIR / "merge_report.json").read_text(encoding="utf-8")
    reparsed = json.loads(raw)
    canonical = json.dumps(reparsed, indent=2, sort_keys=True,
                           ensure_ascii=False) + "\n"
    # Re-parse both to verify semantic equality + sorted keys
    assert json.loads(raw) == json.loads(canonical)
    # Verify keys are sorted at top level
    assert list(reparsed.keys()) == sorted(reparsed.keys())
    # Verify indentation is 2 spaces (check non-empty non-brace lines)
    for line in raw.split("\n"):
        if line.strip() and not line.strip().startswith(("{", "}", "[", "]")):
            indent = len(line) - len(line.lstrip())
            assert indent % 2 == 0, f"Non-2-space indent: {line!r}"


def test_json_trailing_newline():
    """Verify output ends with exactly one newline."""
    raw = (OUT_DIR / "merge_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n")
    assert not raw.endswith("\n\n")


def test_json_keys_sorted_top_level():
    """Verify top-level keys are in alphabetical order."""
    raw = (OUT_DIR / "merge_report.json").read_text(encoding="utf-8")
    reparsed = json.loads(raw)
    assert list(reparsed.keys()) == sorted(reparsed.keys())


# ─── Cross-field consistency ─────────────────────────────────────────────────


def test_anomaly_op_ids_sorted():
    """Verify op_ids in each anomaly are sorted."""
    for anomaly in R["anomalies"]:
        assert anomaly["op_ids"] == sorted(anomaly["op_ids"])


def test_all_op_ids_in_merged_log():
    """Verify all op_ids referenced in anomalies exist in merged_log."""
    all_op_ids = {op["op_id"] for op in R["merged_log"]}
    for anomaly in R["anomalies"]:
        for op_id in anomaly["op_ids"]:
            assert op_id in all_op_ids, f"Unknown op_id: {op_id}"


def test_all_final_op_ids_in_merged_log():
    """Verify all final_op_ids in key_states exist in merged_log."""
    all_op_ids = {op["op_id"] for op in R["merged_log"]}
    for ks in R["key_states"]:
        assert ks["final_op_id"] in all_op_ids


def test_key_states_keys_match_merged_log():
    """Verify keys in key_states match unique keys in merged_log."""
    log_keys = sorted(set(op["key"] for op in R["merged_log"]))
    state_keys = [ks["key"] for ks in R["key_states"]]
    assert state_keys == log_keys


# ─── Convergence metrics tests ───────────────────────────────────────────────


def test_convergence_keys():
    """Verify convergence section has all required fields."""
    required = {"causality_ratio", "causal_depth", "stability_score",
                "vector_clock_magnitude"}
    assert set(R["convergence"].keys()) == required


def test_causal_depth_keys():
    """Verify causal_depth has required subfields."""
    cd = R["convergence"]["causal_depth"]
    required = {"avg_causal_depth", "max_causal_depth", "per_key"}
    assert set(cd.keys()) == required


def test_causal_depth_max():
    """Verify max causal depth = 5 (user:1003 has longest causal chain)."""
    assert R["convergence"]["causal_depth"]["max_causal_depth"] == 5


def test_causal_depth_avg():
    """Verify avg causal depth = 21/11 = 1.909091."""
    import math
    avg = R["convergence"]["causal_depth"]["avg_causal_depth"]
    assert math.isclose(avg, 21 / 11, abs_tol=1e-5)


def test_causal_depth_per_key_count():
    """Verify per_key has entries for all 11 keys."""
    assert len(R["convergence"]["causal_depth"]["per_key"]) == 11


def test_causal_depth_user_1003():
    """user:1003 has causal depth 5 (longest chain in dataset)."""
    assert R["convergence"]["causal_depth"]["per_key"]["user:1003"] == 5


def test_causal_depth_user_1001():
    """user:1001 has causal depth 3."""
    assert R["convergence"]["causal_depth"]["per_key"]["user:1001"] == 3


def test_causal_depth_user_1007():
    """user:1007 has causal depth 3 (delta-001 -> delta-003 -> delta-004)."""
    assert R["convergence"]["causal_depth"]["per_key"]["user:1007"] == 3


def test_causal_depth_config_theme():
    """config:theme has causal depth 2."""
    assert R["convergence"]["causal_depth"]["per_key"]["config:theme"] == 2


def test_causal_depth_single_op_keys():
    """Keys with single operations have causal depth 1."""
    per_key = R["convergence"]["causal_depth"]["per_key"]
    for key in ["config:timeout", "user:1002", "user:1004", "user:1005", "user:1006"]:
        assert per_key[key] == 1, f"{key} should have depth 1"


def test_stability_score():
    """Verify stability score = 8/11 (3 keys have tie-breaking)."""
    import math
    score = R["convergence"]["stability_score"]
    assert math.isclose(score, 8 / 11, abs_tol=1e-5)


def test_stability_unstable_keys():
    """user:1001, counter:visits, config:lang are unstable (tied timestamps)."""
    import math
    score = R["convergence"]["stability_score"]
    assert score < 1.0
    assert math.isclose(score, 0.727273, abs_tol=1e-4)


def test_causality_ratio():
    """Verify causality ratio = 26/40 = 0.65."""
    import math
    ratio = R["convergence"]["causality_ratio"]
    assert math.isclose(ratio, 26 / 40, abs_tol=1e-5)


def test_causality_ratio_range():
    """Causality ratio must be between 0 and 1."""
    ratio = R["convergence"]["causality_ratio"]
    assert 0 <= ratio <= 1


def test_vc_magnitude_keys():
    """Verify vector_clock_magnitude has min, max, mean."""
    vcm = R["convergence"]["vector_clock_magnitude"]
    required = {"max_magnitude", "mean_magnitude", "min_magnitude"}
    assert set(vcm.keys()) == required


def test_vc_magnitude_min():
    """Min VC magnitude = 1 (single-entry clocks like {alpha:1})."""
    assert R["convergence"]["vector_clock_magnitude"]["min_magnitude"] == 1


def test_vc_magnitude_max():
    """Max VC magnitude = 22 (gamma-005: {alpha:8, beta:8, gamma:5} or gamma-006: {alpha:8,beta:8,gamma:6})."""
    assert R["convergence"]["vector_clock_magnitude"]["max_magnitude"] == 22


def test_vc_magnitude_mean():
    """Verify mean VC magnitude = 256/29."""
    import math
    mean = R["convergence"]["vector_clock_magnitude"]["mean_magnitude"]
    assert math.isclose(mean, 256 / 29, abs_tol=1e-4)


def test_convergence_float_precision():
    """Verify float values in convergence have exactly 6 decimal places in raw JSON."""
    raw = (OUT_DIR / "merge_report.json").read_text(encoding="utf-8")
    float_fields = ["causality_ratio", "stability_score", "avg_causal_depth",
                    "mean_magnitude"]
    for field in float_fields:
        pattern = rf'"{field}":\s*(\d+\.\d+)'
        match = re.search(pattern, raw)
        assert match is not None, f"Field {field} not found in output"
        num_str = match.group(1)
        decimals = len(num_str.split(".")[1])
        assert decimals == 6, (
            f"{field}: expected 6 decimals, got {decimals} in {num_str}"
        )
