"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
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

SPANS_PATH = DATA_DIR / "spans.json"
POLICIES_PATH = DATA_DIR / "policies.json"
CONFIG_PATH = DATA_DIR / "config.json"

DECISIONS_PATH = OUT_DIR / "sampling_decisions.json"
POLICY_STATS_PATH = OUT_DIR / "policy_stats.json"
SERVICE_STATS_PATH = OUT_DIR / "service_stats.json"
DIAGNOSTICS_PATH = OUT_DIR / "trace_diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    DECISIONS_PATH,
    POLICY_STATS_PATH,
    SERVICE_STATS_PATH,
    DIAGNOSTICS_PATH,
    SUMMARY_PATH,
)

VALID_CODES = (
    "D_CYCLE_DETECTED",
    "D_FUTURE_TIMESTAMP",
    "D_INCOMPLETE_TRACE",
    "D_MULTI_ROOT",
    "D_ORPHAN_SPAN",
)


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


def _sha256_bucket(hash_seed: str, trace_id: str) -> int:
    h = hashlib.sha256((hash_seed + ":" + trace_id).encode("utf-8")).digest()
    val = int.from_bytes(h[:8], byteorder="big", signed=False)
    return val % 1000


def _evaluate_policies(policies: list[dict], trace_spans: list[dict], trace_id: str):
    statuses_in_trace = {s["status"] for s in trace_spans}
    services_in_trace = {s["service"] for s in trace_spans}
    for p in policies:
        t = p["type"]
        if t == "status_match":
            ok_status = any(s in statuses_in_trace for s in p["statuses"])
            ok_svc = True
            if "services" in p:
                ok_svc = any(s in services_in_trace for s in p["services"])
            if ok_status and ok_svc:
                return p, p["action"]
        elif t == "latency":
            mode = p["mode"]
            thr = p["threshold_ms"]
            matched = False
            if mode == "any_span":
                matched = any(s["duration_ms"] >= thr for s in trace_spans)
            elif mode == "root_span":
                roots = [s for s in trace_spans if s["parent_span_id"] is None]
                if len(roots) == 1:
                    matched = roots[0]["duration_ms"] >= thr
                else:
                    matched = False
            elif mode == "trace_total":
                if trace_spans:
                    total = max(s["start_unix_ms"] + s["duration_ms"] for s in trace_spans) \
                          - min(s["start_unix_ms"] for s in trace_spans)
                    matched = total >= thr
            if matched:
                return p, p["action"]
        elif t == "attribute":
            key = p["key"]
            values = set(p["values"])
            if any(
                key in s["attributes"] and s["attributes"][key] in values
                for s in trace_spans
            ):
                return p, p["action"]
        elif t == "service":
            if any(s in services_in_trace for s in p["services"]):
                return p, p["action"]
        elif t == "probabilistic":
            bucket = _sha256_bucket(p["hash_seed"], trace_id)
            action = "keep" if bucket < p["sampling_rate_per_mille"] else "drop"
            return p, action
    return None, "drop"


def simulate(spans_in: dict, policies_in: dict, config: dict) -> dict[str, Any]:
    severity_ranks = config["severity_ranks"]
    now_unix_ms = config["now_unix_ms"]
    future_thresh = config["future_timestamp_threshold_ms"]

    by_trace: dict[str, list[dict]] = {}
    for sp in spans_in["spans"]:
        by_trace.setdefault(sp["trace_id"], []).append(sp)

    decisions: list[dict] = []
    diagnostics: list[dict] = []

    pol_match = {p["name"]: 0 for p in policies_in["policies"]}
    pol_keep = {p["name"]: 0 for p in policies_in["policies"]}
    pol_drop = {p["name"]: 0 for p in policies_in["policies"]}

    def add_diag(code: str, severity: str, trace_id: str, span_id, evidence: dict):
        diagnostics.append({
            "code": code,
            "evidence": evidence,
            "severity": severity,
            "severity_rank": severity_ranks[severity],
            "span_id": span_id,
            "trace_id": trace_id,
        })

    for trace_id in sorted(by_trace.keys()):
        trace_spans = sorted(by_trace[trace_id], key=lambda s: (s["start_unix_ms"], s["span_id"]))
        span_ids = {s["span_id"] for s in trace_spans}
        roots = [s for s in trace_spans if s["parent_span_id"] is None]
        parent_of: dict[str, str | None] = {s["span_id"]: s["parent_span_id"] for s in trace_spans}

        cycle_members: set[str] = set()
        for sid in span_ids:
            seen: set[str] = set()
            visited: list[str] = []
            cur = sid
            while cur is not None and cur in parent_of:
                if cur in seen:
                    idx = visited.index(cur)
                    cycle_members.update(visited[idx:])
                    break
                seen.add(cur)
                visited.append(cur)
                cur = parent_of.get(cur)
        has_cycle = bool(cycle_members)

        orphan_pairs: list[tuple[str, str]] = []
        for s in trace_spans:
            p = s["parent_span_id"]
            if p is not None and p not in span_ids:
                orphan_pairs.append((s["span_id"], p))

        has_multi_root = len(roots) >= 2
        is_incomplete = len(trace_spans) < config["min_spans_per_trace"]

        reason: str
        decision: str
        matched_policy: str | None = None

        if has_cycle:
            reason = "cycle_detected"
            decision = config["cycle_action"]
            add_diag(
                "D_CYCLE_DETECTED", "error", trace_id, None,
                {"cycle_span_ids": sorted(cycle_members)},
            )
        elif has_multi_root:
            reason = "multi_root"
            decision = config["multi_root_action"]
        elif is_incomplete:
            reason = "incomplete_trace"
            decision = config["incomplete_action"]
        elif orphan_pairs:
            reason = "orphan_span"
            decision = config["orphan_action"]
        else:
            matched, dec_action = _evaluate_policies(policies_in["policies"], trace_spans, trace_id)
            if matched is not None:
                reason = "policy_match"
                matched_policy = matched["name"]
                decision = dec_action
                pol_match[matched["name"]] += 1
                if decision == "keep":
                    pol_keep[matched["name"]] += 1
                else:
                    pol_drop[matched["name"]] += 1
            else:
                reason = "no_policy_matched"
                decision = "drop"

        if has_multi_root:
            add_diag(
                "D_MULTI_ROOT", "warn", trace_id, None,
                {"root_span_ids": sorted(r["span_id"] for r in roots)},
            )
        if is_incomplete:
            add_diag(
                "D_INCOMPLETE_TRACE", "info", trace_id, None,
                {"actual_spans": len(trace_spans), "min_required": config["min_spans_per_trace"]},
            )
        for orphan_sid, missing in orphan_pairs:
            add_diag(
                "D_ORPHAN_SPAN", "warn", trace_id, orphan_sid,
                {"missing_parent_span_id": missing},
            )

        for s in trace_spans:
            skew = s["start_unix_ms"] - now_unix_ms
            if skew > future_thresh:
                add_diag(
                    "D_FUTURE_TIMESTAMP", "warn", trace_id, s["span_id"],
                    {
                        "now_unix_ms": now_unix_ms,
                        "skew_ms": skew,
                        "start_unix_ms": s["start_unix_ms"],
                    },
                )

        decisions.append({
            "decision": decision,
            "matched_policy": matched_policy,
            "reason": reason,
            "trace_id": trace_id,
        })

    decisions.sort(key=lambda d: d["trace_id"])

    diagnostics.sort(key=lambda d: (
        d["severity_rank"],
        d["trace_id"],
        d["code"],
        (0, "") if d["span_id"] is None else (1, d["span_id"]),
    ))

    pol_stats: list[dict] = []
    for p in policies_in["policies"]:
        pol_stats.append({
            "dropped_count": pol_drop[p["name"]],
            "kept_count":    pol_keep[p["name"]],
            "matched_count": pol_match[p["name"]],
            "name":          p["name"],
            "type":          p["type"],
        })
    pol_stats.sort(key=lambda x: x["name"])

    decisions_by_trace = {d["trace_id"]: d["decision"] for d in decisions}
    trace_total_dur: dict[str, int] = {}
    for trace_id, ts in by_trace.items():
        if not ts:
            trace_total_dur[trace_id] = 0
            continue
        trace_total_dur[trace_id] = (
            max(s["start_unix_ms"] + s["duration_ms"] for s in ts)
            - min(s["start_unix_ms"] for s in ts)
        )

    services_seen: dict[str, dict] = {}
    service_traces: dict[str, set[str]] = {}
    for sp in spans_in["spans"]:
        svc = sp["service"]
        entry = services_seen.setdefault(svc, {
            "dropped_traces": 0,
            "error_spans": 0,
            "kept_traces": 0,
            "max_trace_duration_ms": 0,
            "service": svc,
            "span_count": 0,
            "timeout_spans": 0,
            "trace_count": 0,
        })
        entry["span_count"] += 1
        if sp["status"] == "error":
            entry["error_spans"] += 1
        if sp["status"] == "timeout":
            entry["timeout_spans"] += 1
        service_traces.setdefault(svc, set()).add(sp["trace_id"])

    for svc, traces in service_traces.items():
        entry = services_seen[svc]
        entry["trace_count"] = len(traces)
        kept = sum(1 for t in traces if decisions_by_trace.get(t) == "keep")
        dropped = sum(1 for t in traces if decisions_by_trace.get(t) == "drop")
        entry["kept_traces"] = kept
        entry["dropped_traces"] = dropped
        entry["max_trace_duration_ms"] = max(
            (trace_total_dur[t] for t in traces), default=0
        )

    service_stats = sorted(services_seen.values(), key=lambda x: x["service"])

    spans_total = len(spans_in["spans"])
    traces_total = len(by_trace)
    kept_traces = sum(1 for d in decisions if d["decision"] == "keep")
    traces_dropped = traces_total - kept_traces

    code_counts = {c: 0 for c in VALID_CODES}
    for d in diagnostics:
        code_counts[d["code"]] += 1

    if spans_total == 0:
        hottest = None
    else:
        best = None
        best_span = -1
        for x in service_stats:
            if x["span_count"] > best_span or (
                x["span_count"] == best_span and (best is None or x["service"] < best)
            ):
                best = x["service"]
                best_span = x["span_count"]
        hottest = best

    summary = {
        "anomaly_counts": code_counts,
        "hottest_service": hottest,
        "kept_traces": kept_traces,
        "spans_total": spans_total,
        "traces_dropped": traces_dropped,
        "traces_total": traces_total,
    }

    return {
        "sampling_decisions": {"decisions": decisions},
        "policy_stats": {"policies": pol_stats},
        "service_stats": {"services": service_stats},
        "trace_diagnostics": {"diagnostics": diagnostics},
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {
        "spans": load_json(SPANS_PATH),
        "policies": load_json(POLICIES_PATH),
        "config": load_json(CONFIG_PATH),
    }


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(input_data["spans"], input_data["policies"], input_data["config"])


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in (SPANS_PATH, POLICIES_PATH, CONFIG_PATH)}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    """Wipes /app/output and runs the agent binary fresh against /app/data,
    then loads each output document. Subsequent tests use the loaded
    documents."""
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert _java_class_ready(), f"agent binary missing at {(BUILD_DIR / f'{JAVA_CLASS}.class')}"
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True,
        text=True,
        timeout=120,
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


def test_java_entry_class_exists():
    """Compiled Java entry class exists under /app/build."""
    assert _java_class_ready()


def test_binary_runs_cleanly_and_outputs_are_fresh(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts():
    """Binary exits non-zero when argument count is not exactly two."""
    res = subprocess.run(
        ["java", "-cp", f"{BUILD_DIR}:{GSON_CP}", JAVA_CLASS, str(DATA_DIR)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode != 0
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR), "extra"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert res.returncode != 0


def test_binary_uses_argv_paths_not_hardcoded(tmp_path, input_data):
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, tmp_out)],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, f"binary failed under alt out_dir: {res.stderr}"
    for name in (
        "sampling_decisions.json", "policy_stats.json",
        "service_stats.json", "trace_diagnostics.json", "summary.json",
    ):
        assert (tmp_out / name).exists(), f"binary did not write {name} to argv[2]"


def test_binary_reads_input_from_argv1_not_hardcoded(tmp_path, input_data, expected_outputs):
    """Copy inputs to a different directory, run binary with argv[1]
    pointing at the copy, and verify outputs match the reference. A
    binary that hardcodes /app/data would still produce the right
    outputs against the visible dataset, so we ALSO mutate a single
    input field in the copy (drop one trace) and expect the outputs to
    track the mutated reference rather than the original."""
    tmp_data = tmp_path / "altdata"
    tmp_data.mkdir()
    tmp_out = tmp_path / "altout"
    tmp_out.mkdir()

    # Drop one trace from the spans copy to create a variant dataset.
    original_spans = input_data["spans"]
    trace_ids = sorted({sp["trace_id"] for sp in original_spans["spans"]})
    drop_tid = trace_ids[0]
    variant_spans = {
        "spans": [s for s in original_spans["spans"] if s["trace_id"] != drop_tid]
    }
    (tmp_data / "spans.json").write_text(
        json.dumps(variant_spans, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (tmp_data / "policies.json").write_text(
        json.dumps(input_data["policies"], indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    (tmp_data / "config.json").write_text(
        json.dumps(input_data["config"], indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )

    res = subprocess.run(
        [*_java_cmd(tmp_data, tmp_out)],
        capture_output=True, text=True, timeout=120,
    )
    assert res.returncode == 0, f"binary failed under variant data_dir: {res.stderr}"

    variant_expected = simulate(variant_spans, input_data["policies"], input_data["config"])
    for name, key in [
        ("sampling_decisions.json", "sampling_decisions"),
        ("policy_stats.json", "policy_stats"),
        ("service_stats.json", "service_stats"),
        ("trace_diagnostics.json", "trace_diagnostics"),
        ("summary.json", "summary"),
    ]:
        actual = json.loads((tmp_out / name).read_text(encoding="utf-8"))
        assert actual == variant_expected[key], (
            f"binary's {name} from argv[1]={tmp_data} did not track the variant "
            f"data -- it may be hardcoded to read /app/data"
        )
    # Sanity: the variant dataset must produce a different sampling_decisions
    # from the canonical one (so the test would actually catch a hardcoded
    # /app/data reader).
    assert variant_expected["sampling_decisions"] != expected_outputs["sampling_decisions"], (
        "variant dataset did not produce a different decision set; test is degenerate"
    )


def test_outputs_strict_json_formatting(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii_at_every_depth(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text(encoding="utf-8")
        text.encode("ascii")  # raises if any non-ascii


def test_sampling_decisions_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[DECISIONS_PATH]
    assert actual == expected_outputs["sampling_decisions"]


def test_policy_stats_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[POLICY_STATS_PATH]
    assert actual == expected_outputs["policy_stats"]


def test_service_stats_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[SERVICE_STATS_PATH]
    assert actual == expected_outputs["service_stats"]


def test_trace_diagnostics_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[DIAGNOSTICS_PATH]
    assert actual == expected_outputs["trace_diagnostics"]


def test_summary_match_reference(binary_run_outputs, expected_outputs):
    actual = binary_run_outputs[SUMMARY_PATH]
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(binary_run_outputs):
    diags = binary_run_outputs[DIAGNOSTICS_PATH]
    for d in diags["diagnostics"]:
        assert d["code"] in VALID_CODES, d
        assert d["severity"] in {"error", "warn", "info"}, d


VALID_REASONS = (
    "cycle_detected",
    "incomplete_trace",
    "multi_root",
    "no_policy_matched",
    "orphan_span",
    "policy_match",
)


def test_decision_reasons_are_in_closed_set(binary_run_outputs):
    decisions = binary_run_outputs[DECISIONS_PATH]["decisions"]
    for d in decisions:
        assert d["reason"] in VALID_REASONS, d
        assert d["decision"] in {"keep", "drop"}, d


def test_decisions_sorted_by_trace_id(binary_run_outputs):
    decisions = binary_run_outputs[DECISIONS_PATH]["decisions"]
    trace_ids = [d["trace_id"] for d in decisions]
    assert trace_ids == sorted(trace_ids)
    assert len(trace_ids) == len(set(trace_ids))


def test_policy_stats_sorted_by_name(binary_run_outputs):
    ps = binary_run_outputs[POLICY_STATS_PATH]["policies"]
    names = [p["name"] for p in ps]
    assert names == sorted(names)


def test_service_stats_sorted_by_service(binary_run_outputs):
    ss = binary_run_outputs[SERVICE_STATS_PATH]["services"]
    services = [s["service"] for s in ss]
    assert services == sorted(services)


def _diag_sort_key(d):
    return (
        d["severity_rank"],
        d["trace_id"],
        d["code"],
        (0, "") if d["span_id"] is None else (1, d["span_id"]),
    )


def test_diagnostics_sorted(binary_run_outputs, input_data):
    diags = binary_run_outputs[DIAGNOSTICS_PATH]["diagnostics"]
    ranks = input_data["config"]["severity_ranks"]
    for i in range(1, len(diags)):
        a, b = diags[i - 1], diags[i]
        assert a["severity_rank"] == ranks[a["severity"]]
        assert b["severity_rank"] == ranks[b["severity"]]
        assert _diag_sort_key(a) <= _diag_sort_key(b), (a, b)


def test_matched_policy_null_iff_non_policy_match(binary_run_outputs):
    decisions = binary_run_outputs[DECISIONS_PATH]["decisions"]
    for d in decisions:
        if d["reason"] == "policy_match":
            assert d["matched_policy"] is not None, d
        else:
            assert d["matched_policy"] is None, d


def test_summary_consistency_with_decisions(binary_run_outputs):
    decisions = binary_run_outputs[DECISIONS_PATH]["decisions"]
    summary = binary_run_outputs[SUMMARY_PATH]
    assert summary["traces_total"] == len(decisions)
    kept = sum(1 for d in decisions if d["decision"] == "keep")
    dropped = sum(1 for d in decisions if d["decision"] == "drop")
    assert summary["kept_traces"] == kept
    assert summary["traces_dropped"] == dropped


def test_policy_stats_invariant(binary_run_outputs):
    ps = binary_run_outputs[POLICY_STATS_PATH]["policies"]
    for p in ps:
        assert p["matched_count"] == p["kept_count"] + p["dropped_count"], p


def test_service_stats_invariant(binary_run_outputs):
    ss = binary_run_outputs[SERVICE_STATS_PATH]["services"]
    for s in ss:
        assert s["trace_count"] == s["kept_traces"] + s["dropped_traces"], s


def test_dataset_exercises_every_branch(expected_outputs):
    """The visible dataset must exercise every code path -- otherwise
    the task is degenerate and not solvable in the spirit of the spec."""
    summary = expected_outputs["summary"]
    decisions = expected_outputs["sampling_decisions"]["decisions"]
    reasons = {d["reason"] for d in decisions}
    assert "cycle_detected" in reasons
    assert "multi_root" in reasons
    assert "incomplete_trace" in reasons
    assert "orphan_span" in reasons
    assert "policy_match" in reasons
    assert summary["kept_traces"] > 0
    assert summary["traces_dropped"] > 0
    for code in VALID_CODES:
        assert summary["anomaly_counts"][code] > 0, code


def test_data_dir_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h, f"{p} mutated by binary run"


def test_binary_rejects_missing_input_files(tmp_path):
    bad_data = tmp_path / "nodata"
    bad_data.mkdir()
    bad_out = tmp_path / "noout"
    bad_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(bad_data, bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_malformed_json(tmp_path, input_data):
    """Pass a data dir whose config.json is not valid JSON; the binary
    must exit non-zero rather than producing outputs."""
    bad_data = tmp_path / "baddata"
    bad_data.mkdir()
    (bad_data / "spans.json").write_text(json.dumps(input_data["spans"]))
    (bad_data / "policies.json").write_text(json.dumps(input_data["policies"]))
    (bad_data / "config.json").write_text("{not valid json")
    bad_out = tmp_path / "badout"
    bad_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(bad_data, bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0


def test_binary_rejects_schema_violations(tmp_path, input_data):
    """Pass a data dir whose policies.json is JSON-parseable but missing
    a required field (the policy's `type`). The binary must exit non-zero
    because the input violates the documented schema, rather than silently
    producing partial outputs."""
    bad_data = tmp_path / "schemadata"
    bad_data.mkdir()
    bad_policies = {
        "policies": [
            {"name": "broken", "action": "keep"}  # missing required `type`
        ]
    }
    (bad_data / "spans.json").write_text(json.dumps(input_data["spans"]))
    (bad_data / "policies.json").write_text(json.dumps(bad_policies))
    (bad_data / "config.json").write_text(json.dumps(input_data["config"]))
    bad_out = tmp_path / "schemaout"
    bad_out.mkdir()
    res = subprocess.run(
        [*_java_cmd(bad_data, bad_out)],
        capture_output=True, text=True, timeout=30,
    )
    assert res.returncode != 0, (
        "binary accepted a policies.json missing the required `type` field; "
        "the malformed-input contract requires non-zero exit"
    )


def test_determinism_two_runs_byte_identical(tmp_path):
    out_a = tmp_path / "a"
    out_a.mkdir()
    out_b = tmp_path / "b"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run(
            [*_java_cmd(DATA_DIR, out)],
            capture_output=True, text=True, timeout=120,
        )
        assert res.returncode == 0
    for name in (
        "sampling_decisions.json", "policy_stats.json",
        "service_stats.json", "trace_diagnostics.json", "summary.json",
    ):
        a = (out_a / name).read_bytes()
        b = (out_b / name).read_bytes()
        assert a == b, f"{name} differs between two runs"


def test_java_sources_present_under_app_src():
    """Agent must ship Java sources under /app/src for the verifier build."""
    src_root = Path("/app/src")
    assert src_root.exists(), "/app/src missing"
    assert any(src_root.rglob("*.java")), "no .java under /app/src"
