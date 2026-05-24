"""Tests for rust-feature-resolver-hard."""
import hashlib
import json
import math
import pathlib

import pytest

ROOT = pathlib.Path("/app")


OUT_DIR = pathlib.pathlib.Path('/app/output')
DATA_DIR = pathlib.pathlib.Path('/app/data')

FLOAT_TOL = 1e-4


def load_report():
    p = OUT_DIR / "build_plan.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


R = load_report()


def crate_by_name(name):
    for c in R["resolved_crates"]:
        if c["name"] == name:
            return c
    pytest.fail(f"Crate {name} not in resolved_crates")


# ── Rust binary enforcement ──────────────────────────────────────────


def test_rust_binary_exists():
    binary = ROOT / "build" / "feature-resolver"
    if not binary.is_file():
        binary = ROOT / "target" / "release" / "feature-resolver"
    assert binary.is_file(), (
        "Compiled Rust binary not found at /app/build/feature-resolver. "
        "Solution must be compiled from Rust source with cargo."
    )


def test_rust_binary_is_elf():
    binary = ROOT / "build" / "feature-resolver"
    if not binary.is_file():
        binary = ROOT / "target" / "release" / "feature-resolver"
    assert binary.is_file(), "Binary not found"
    with open(binary, "rb") as f:
        magic = f.read(4)
    assert magic == b"\x7fELF", (
        f"Binary is not an ELF executable (magic: {magic!r}). "
        "Python wrappers are not accepted."
    )


def test_cargo_build_artifacts():
    target_dir = ROOT / "target"
    assert target_dir.is_dir(), (
        "target/ directory missing — Rust code was never compiled."
    )


# ── Output structure ─────────────────────────────────────────────────


def test_output_file_exists():
    assert (OUT_DIR / "build_plan.json").is_file()


def test_top_level_keys():
    required = {
        "workspace",
        "resolved_crates",
        "dependency_graph",
        "cycles",
        "build_order",
        "build_checksum",
        "size_analysis",
        "findings",
    }
    assert set(R.keys()) == required, f"Keys mismatch: got {sorted(R.keys())}"


def test_workspace_section():
    ws = R["workspace"]
    assert ws["name"] == "acme-platform"
    assert ws["version"] == "3.1.0"
    assert ws["root_crate"] == "app-server"
    assert ws["total_crates"] == 23
    assert ws["reachable_crates"] == 22


def test_resolved_crates_count():
    assert len(R["resolved_crates"]) == 23


def test_resolved_crates_sorted():
    names = [c["name"] for c in R["resolved_crates"]]
    assert names == sorted(names), "resolved_crates not sorted by name"


# ── Feature resolution ───────────────────────────────────────────────


def test_root_features():
    c = crate_by_name("app-server")
    assert c["reachable"] is True
    assert sorted(c["resolved_features"]) == ["default"]


def test_core_lib_features():
    c = crate_by_name("core-lib")
    expected = sorted(["default", "std", "full", "serde", "async-support", "tracing"])
    assert sorted(c["resolved_features"]) == expected


def test_core_lib_optional_deps():
    c = crate_by_name("core-lib")
    assert sorted(c["activated_optional_deps"]) == ["async-rt", "serde-core"]


def test_core_lib_tracing_not_in_opt_deps():
    c = crate_by_name("core-lib")
    assert "tracing" not in c["activated_optional_deps"], (
        "Weak features must NOT appear in activated_optional_deps"
    )


def test_http_layer_features():
    c = crate_by_name("http-layer")
    expected = sorted(["default", "http1", "http2", "full", "websocket"])
    assert sorted(c["resolved_features"]) == expected


def test_http_layer_chain_http2_enables_http1():
    c = crate_by_name("http-layer")
    feats = c["resolved_features"]
    assert "http1" in feats, "full→http2→http1 chain not followed"
    assert "http2" in feats, "full→http2 chain not followed"


def test_auth_module_features():
    c = crate_by_name("auth-module")
    expected = sorted(["default", "jwt", "oauth"])
    assert sorted(c["resolved_features"]) == expected


def test_auth_module_oauth_enables_jwt():
    c = crate_by_name("auth-module")
    assert "jwt" in c["resolved_features"], (
        "oauth feature should enable jwt via feature chain"
    )


def test_db_connector_features():
    c = crate_by_name("db-connector")
    expected = sorted(["default", "postgres", "mysql"])
    assert sorted(c["resolved_features"]) == expected


def test_db_connector_optional_deps():
    c = crate_by_name("db-connector")
    assert sorted(c["activated_optional_deps"]) == ["mysql-driver", "pg-driver"]


def test_config_reader_features():
    c = crate_by_name("config-reader")
    expected = sorted(["default", "json"])
    assert sorted(c["resolved_features"]) == expected


def test_logger_features_unification():
    c = crate_by_name("logger")
    expected = sorted(["default", "colors", "structured"])
    assert sorted(c["resolved_features"]) == expected, (
        "Logger should have default+colors (from default_features=true deps) "
        "AND structured (from token-store's explicit request)"
    )


def test_utils_features_unification():
    c = crate_by_name("utils")
    feats = sorted(c["resolved_features"])
    assert "std" in feats, "std should come from default features (true wins)"
    assert "hashing" in feats, "hashing should come from token-store"
    assert "no-std" in feats, "no-std should come from crypto-utils"
    expected = sorted(["default", "std", "no-std", "hashing"])
    assert feats == expected


def test_default_features_true_wins():
    c = crate_by_name("utils")
    assert "std" in c["resolved_features"], (
        "Even though crypto-utils sets default_features=false, "
        "core-lib and config-reader set default_features=true so 'std' must be active."
    )


def test_serde_core_features():
    c = crate_by_name("serde-core")
    expected = sorted(["default", "derive", "alloc"])
    assert sorted(c["resolved_features"]) == expected, (
        "serde-core should have default+derive (from default_features=true) "
        "AND alloc (from logger's dep with features=[alloc])"
    )


def test_async_rt_features():
    c = crate_by_name("async-rt")
    expected = sorted(["default", "multi-thread"])
    assert sorted(c["resolved_features"]) == expected


def test_compression_default_only():
    c = crate_by_name("compression")
    expected = sorted(["default", "gzip"])
    assert sorted(c["resolved_features"]) == expected


def test_token_store_no_optional_activated():
    c = crate_by_name("token-store")
    assert c["activated_optional_deps"] == []


def test_orphan_unreachable():
    c = crate_by_name("orphan-crate")
    assert c["reachable"] is False
    assert c["resolved_features"] is None
    assert c["resolved_dependencies"] is None
    assert c["depth"] is None
    assert c["layer"] == "unreachable"


# ── Weak features ────────────────────────────────────────────────────


def test_weak_feature_core_lib_tracing():
    c = crate_by_name("core-lib")
    assert "tracing" in c["resolved_features"], (
        "core-lib has weak_features: tracing -> [logger/structured]. "
        "Logger has structured active, so tracing must activate."
    )


def test_weak_feature_db_connector_not_activated():
    c = crate_by_name("db-connector")
    assert "tracing" not in c.get("resolved_features", []), (
        "db-connector's weak feature tracing requires logger/structured, "
        "but db-connector doesn't depend on logger directly."
    )


def test_weak_feature_pg_driver_not_activated():
    c = crate_by_name("pg-driver")
    assert "tls-auto" not in c.get("resolved_features", []), (
        "pg-driver's weak feature tls-auto requires tls-provider/native-tls, "
        "but tls-provider does not have native-tls active."
    )


# ── Depth (longest path) ────────────────────────────────────────────


def test_root_depth():
    assert crate_by_name("app-server")["depth"] == 0


def test_depth_auth_module():
    assert crate_by_name("auth-module")["depth"] == 1


def test_depth_http_layer():
    c = crate_by_name("http-layer")
    assert c["depth"] == 3, (
        "http-layer depth should be 3: "
        "app-server(0)→auth-module(1)→oauth-client(2)→http-layer(3)"
    )


def test_depth_core_lib():
    c = crate_by_name("core-lib")
    assert c["depth"] == 4, (
        "core-lib depth should be 4 via oauth-client→http-layer→core-lib"
    )


def test_depth_serde_core():
    c = crate_by_name("serde-core")
    assert c["depth"] == 7, (
        "serde-core depth=7 via longest path through "
        "async-rt→logger→serde-core"
    )


def test_depth_logger():
    assert crate_by_name("logger")["depth"] == 6


def test_depth_utils():
    assert crate_by_name("utils")["depth"] == 5


def test_depth_hash_impl():
    assert crate_by_name("hash-impl")["depth"] == 6


def test_depth_scc_members_same():
    d_crypto = crate_by_name("crypto-utils")["depth"]
    d_tls = crate_by_name("tls-provider")["depth"]
    assert d_crypto == d_tls, "SCC members must share the same depth"
    assert d_crypto == 4


def test_depth_async_rt():
    assert crate_by_name("async-rt")["depth"] == 5


def test_depth_conn_pool():
    assert crate_by_name("conn-pool")["depth"] == 3


def test_depth_config_reader():
    assert crate_by_name("config-reader")["depth"] == 1


# ── Coupling ─────────────────────────────────────────────────────────


def test_fan_in_serde_core():
    assert crate_by_name("serde-core")["fan_in"] == 6


def test_fan_out_app_server():
    assert crate_by_name("app-server")["fan_out"] == 5


def test_fan_out_db_connector():
    assert crate_by_name("db-connector")["fan_out"] == 5


def test_fan_in_core_lib():
    assert crate_by_name("core-lib")["fan_in"] == 4


def test_fan_in_logger():
    assert crate_by_name("logger")["fan_in"] == 4


def test_fan_in_utils():
    assert crate_by_name("utils")["fan_in"] == 4


def test_instability_app_server():
    c = crate_by_name("app-server")
    assert math.isclose(c["instability"], 1.0, abs_tol=FLOAT_TOL)


def test_instability_serde_core():
    c = crate_by_name("serde-core")
    assert math.isclose(c["instability"], 0.0, abs_tol=FLOAT_TOL)


def test_instability_core_lib():
    c = crate_by_name("core-lib")
    assert math.isclose(c["instability"], 0.5, abs_tol=FLOAT_TOL)


def test_instability_orphan_null():
    c = crate_by_name("orphan-crate")
    assert c["instability"] is None


# ── Active size ──────────────────────────────────────────────────────


def test_size_core_lib():
    c = crate_by_name("core-lib")
    expected = 4500.0 * (1.0 + 0.10 + 0.20 + 0.25 + 0.05)
    assert math.isclose(c["active_size"], expected, abs_tol=FLOAT_TOL), (
        f"core-lib size should be {expected}, got {c['active_size']}. "
        "tracing weak feature adds 0.05 weight."
    )


def test_size_core_lib_now_oversized():
    c = crate_by_name("core-lib")
    assert c["active_size"] > 7000.0, (
        "core-lib active_size=7200.0 — weak feature tracing pushes it above 7000"
    )


def test_size_http_layer():
    c = crate_by_name("http-layer")
    expected = 6800.0 * (1.0 + 0.15 + 0.20 + 0.30 + 0.0)
    assert math.isclose(c["active_size"], expected, abs_tol=FLOAT_TOL)


def test_size_app_server():
    c = crate_by_name("app-server")
    assert math.isclose(c["active_size"], 8200.0, abs_tol=FLOAT_TOL), (
        "app-server has no active weighted features, size = base_size"
    )


def test_size_multiplicative_not_additive():
    c = crate_by_name("core-lib")
    correct = 4500.0 * 1.60
    assert math.isclose(c["active_size"], correct, abs_tol=FLOAT_TOL)


def test_size_orphan_uses_base():
    c = crate_by_name("orphan-crate")
    assert math.isclose(c["active_size"], 900.0, abs_tol=FLOAT_TOL)


# ── Layer classification ─────────────────────────────────────────────


def test_layer_entry():
    assert crate_by_name("app-server")["layer"] == "entry"


def test_layer_leaf_serde_core():
    assert crate_by_name("serde-core")["layer"] == "leaf"


def test_layer_leaf_hash_impl():
    assert crate_by_name("hash-impl")["layer"] == "leaf"


def test_layer_leaf_query_builder():
    assert crate_by_name("query-builder")["layer"] == "leaf"


def test_layer_internal_core_lib():
    assert crate_by_name("core-lib")["layer"] == "internal"


def test_layer_unreachable():
    assert crate_by_name("orphan-crate")["layer"] == "unreachable"


# ── Cycles ───────────────────────────────────────────────────────────


def test_cycle_detection():
    cyc = R["cycles"]
    assert cyc["is_acyclic"] is False
    assert cyc["cycle_count"] == 1


def test_cycle_members():
    members = R["cycles"]["cycles"][0]
    assert members == ["crypto-utils", "tls-provider"]


# ── Dependency graph ─────────────────────────────────────────────────


def test_total_edges():
    assert R["dependency_graph"]["total_edges"] == 40


def test_edges_sorted():
    edges = R["dependency_graph"]["edges"]
    keys = [(e["from"], e["to"]) for e in edges]
    assert keys == sorted(keys), "Edges not sorted by (from, to)"


def test_oauth_client_depends_on_http_layer():
    edges = R["dependency_graph"]["edges"]
    assert {"from": "oauth-client", "to": "http-layer"} in edges


def test_crypto_utils_depends_on_tls_provider():
    edges = R["dependency_graph"]["edges"]
    assert {"from": "crypto-utils", "to": "tls-provider"} in edges


def test_tls_provider_depends_on_crypto_utils():
    edges = R["dependency_graph"]["edges"]
    assert {"from": "tls-provider", "to": "crypto-utils"} in edges


def test_core_lib_depends_on_async_rt():
    edges = R["dependency_graph"]["edges"]
    assert {"from": "core-lib", "to": "async-rt"} in edges, (
        "core-lib's async-support feature activates optional dep async-rt"
    )


def test_logger_depends_on_serde_core():
    edges = R["dependency_graph"]["edges"]
    assert {"from": "logger", "to": "serde-core"} in edges, (
        "logger's structured feature activates optional dep serde-core"
    )


def test_no_orphan_edges():
    edges = R["dependency_graph"]["edges"]
    orphan_edges = [
        e for e in edges
        if e["from"] == "orphan-crate" or e["to"] == "orphan-crate"
    ]
    assert orphan_edges == [], "Unreachable orphan-crate should have no edges"


# ── Build order ──────────────────────────────────────────────────────


def test_build_order_length():
    assert len(R["build_order"]) == 23


def test_build_order_deps_before_dependents():
    bo = R["build_order"]
    idx = {name: i for i, name in enumerate(bo)}
    edges = R["dependency_graph"]["edges"]
    scc_members = set()
    for cyc in R["cycles"]["cycles"]:
        for m in cyc:
            scc_members.add(m)
    for e in edges:
        if e["from"] in scc_members and e["to"] in scc_members:
            continue
        dep_idx = idx.get(e["to"])
        depnt_idx = idx.get(e["from"])
        assert dep_idx is not None and depnt_idx is not None
        assert dep_idx < depnt_idx, (
            f"Dependency {e['to']} (pos {dep_idx}) must come before "
            f"dependent {e['from']} (pos {depnt_idx})"
        )


def test_build_order_scc_adjacent():
    bo = R["build_order"]
    ci = bo.index("crypto-utils")
    ti = bo.index("tls-provider")
    assert abs(ci - ti) == 1, "SCC members must be adjacent in build order"
    assert ci < ti, "SCC members in alphabetical order"


def test_build_order_priority_and_depth_tiebreaking():
    bo = R["build_order"]
    sc = bo.index("serde-core")
    hi = bo.index("hash-impl")
    assert sc < hi, (
        "serde-core (priority=1, depth=7) before hash-impl (priority=1, depth=6). "
        "Same priority → higher depth first (DESC)."
    )
    comp = bo.index("compression")
    qb = bo.index("query-builder")
    assert comp < qb, (
        "compression (priority=7) should come before query-builder (priority=8)"
    )


def test_build_order_orphan_last():
    bo = R["build_order"]
    assert bo[-1] == "orphan-crate", (
        "orphan-crate (priority=10) is unreachable and should be last"
    )


def test_build_order_root_second_to_last():
    bo = R["build_order"]
    assert bo[-2] == "app-server", (
        "app-server is the root (all deps before it), orphan-crate after"
    )


# ── Build checksum ───────────────────────────────────────────────────


def test_build_checksum_present():
    assert "build_checksum" in R
    assert isinstance(R["build_checksum"], str)
    assert len(R["build_checksum"]) == 64


def test_build_checksum_correct():
    bo = R["build_order"]
    reachable_crates = [c for c in R["resolved_crates"] if c["reachable"]]
    feature_digest = [
        [c["name"], c["resolved_features"]]
        for c in sorted(reachable_crates, key=lambda x: x["name"])
    ]
    verification = (
        json.dumps(bo, separators=(",", ":")) + "\n" +
        json.dumps(feature_digest, separators=(",", ":"))
    )
    expected = hashlib.sha256(verification.encode()).hexdigest()
    assert R["build_checksum"] == expected, (
        f"build_checksum mismatch. Expected SHA-256 of build_order + feature_digest. "
        f"Got {R['build_checksum']}, expected {expected}"
    )


def test_build_checksum_exact():
    assert R["build_checksum"] == (
        "8dc8d43d0dd57fe2376ca94a38446c4db6a20740ccca14ac102424e384b37b48"
    )


# ── Size analysis ────────────────────────────────────────────────────


def test_total_base_size():
    sa = R["size_analysis"]
    assert sa["total_base_size"] == 64900


def test_reachable_base_size():
    sa = R["size_analysis"]
    assert sa["reachable_base_size"] == 64000


def test_total_active_size():
    sa = R["size_analysis"]
    assert math.isclose(sa["total_active_size"], 80510.0, abs_tol=FLOAT_TOL)


def test_reachable_active_size():
    sa = R["size_analysis"]
    assert math.isclose(sa["reachable_active_size"], 79610.0, abs_tol=FLOAT_TOL)


# ── Findings ─────────────────────────────────────────────────────────


def test_findings_total():
    assert R["findings"]["total"] == 57


def test_findings_by_severity():
    bs = R["findings"]["by_severity"]
    assert bs["critical"] == 4
    assert bs["high"] == 13
    assert bs["medium"] == 7
    assert bs["low"] == 32
    assert bs["info"] == 1


def test_findings_sorted():
    sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}
    items = R["findings"]["items"]
    keys = [
        (-sev_rank[it["severity"]], it["type"], it["module"] or "")
        for it in items
    ]
    assert keys == sorted(keys), "Findings not sorted correctly"


def test_finding_dependency_cycle():
    items = R["findings"]["items"]
    cyc_findings = [i for i in items if i["type"] == "dependency_cycle"]
    assert len(cyc_findings) == 1
    f = cyc_findings[0]
    assert f["severity"] == "critical"
    assert f["module"] is None
    assert f["details"]["members"] == ["crypto-utils", "tls-provider"]


def test_finding_feature_conflict():
    items = R["findings"]["items"]
    conf = [i for i in items if i["type"] == "feature_conflict"]
    assert len(conf) == 2
    modules = sorted(c["module"] for c in conf)
    assert modules == ["core-lib", "utils"]


def test_finding_workspace_feature_exclusion():
    items = R["findings"]["items"]
    wfe = [i for i in items if i["type"] == "workspace_feature_exclusion"]
    assert len(wfe) == 1
    f = wfe[0]
    assert f["severity"] == "critical"
    assert f["module"] is None
    assert f["details"]["group"] == "tls_backend"
    violations = f["details"]["violations"]
    assert len(violations) == 2
    assert {"crate": "crypto-utils", "feature": "openssl"} in violations
    assert {"crate": "tls-provider", "feature": "native-tls"} in violations


def test_finding_feature_conflict_utils():
    items = R["findings"]["items"]
    conf = [i for i in items if i["type"] == "feature_conflict" and i["module"] == "utils"]
    assert len(conf) == 1
    assert sorted(conf[0]["details"]["features"]) == ["no-std", "std"]


def test_finding_feature_conflict_core_lib_weak():
    items = R["findings"]["items"]
    conf = [i for i in items if i["type"] == "feature_conflict" and i["module"] == "core-lib"]
    assert len(conf) == 1, (
        "core-lib has conflict [tracing, std]. tracing is activated via weak features "
        "(logger/structured condition met). std is from default. Both active → conflict."
    )
    assert sorted(conf[0]["details"]["features"]) == ["std", "tracing"]


def test_finding_deep_modules():
    items = R["findings"]["items"]
    deep = [i for i in items if i["type"] == "deep_module"]
    modules = sorted(i["module"] for i in deep)
    expected = [
        "async-rt", "compression", "core-lib", "crypto-utils",
        "hash-impl", "logger", "serde-core", "tls-provider", "utils", "ws-codec",
    ]
    assert modules == expected, (
        f"With max_depth=3, all crates with depth>3 are deep. Got {modules}"
    )


def test_finding_not_deep_at_threshold():
    items = R["findings"]["items"]
    deep_mods = {i["module"] for i in items if i["type"] == "deep_module"}
    assert "conn-pool" not in deep_mods, (
        "conn-pool depth=3 == max_depth=3, strictly greater required"
    )
    assert "http-layer" not in deep_mods, (
        "http-layer depth=3 == max_depth=3, strictly greater required"
    )


def test_finding_excessive_fan_out():
    items = R["findings"]["items"]
    fo = [i for i in items if i["type"] == "excessive_fan_out"]
    modules = sorted(i["module"] for i in fo)
    assert modules == ["app-server", "db-connector"]


def test_finding_not_fan_out_at_threshold():
    items = R["findings"]["items"]
    fo_mods = {i["module"] for i in items if i["type"] == "excessive_fan_out"}
    assert "core-lib" not in fo_mods, (
        "core-lib fan_out=4 == max_fan_out=4, strictly greater required"
    )


def test_finding_excessive_fan_in():
    items = R["findings"]["items"]
    fi = [i for i in items if i["type"] == "excessive_fan_in"]
    assert len(fi) == 1
    assert fi[0]["module"] == "serde-core"


def test_finding_oversized_crates():
    items = R["findings"]["items"]
    ov = [i for i in items if i["type"] == "oversized_crate"]
    modules = sorted(i["module"] for i in ov)
    assert modules == ["app-server", "auth-module", "core-lib", "http-layer"], (
        "core-lib becomes oversized due to tracing weak feature adding 0.05 weight"
    )


def test_finding_high_instability():
    items = R["findings"]["items"]
    hi = [i for i in items if i["type"] == "high_instability"]
    modules = sorted(i["module"] for i in hi)
    expected = [
        "app-server", "async-rt", "auth-module", "config-reader",
        "core-lib", "crypto-utils", "db-connector", "http-layer",
        "json-parser", "mysql-driver", "oauth-client", "pg-driver", "token-store",
    ]
    assert modules == expected


def test_finding_not_instability_at_threshold():
    items = R["findings"]["items"]
    hi_mods = {i["module"] for i in items if i["type"] == "high_instability"}
    assert "tls-provider" not in hi_mods, (
        "tls-provider instability=0.333 < threshold 0.4, not unstable"
    )


def test_finding_unreachable():
    items = R["findings"]["items"]
    ur = [i for i in items if i["type"] == "unreachable_module"]
    assert len(ur) == 1
    assert ur[0]["module"] == "orphan-crate"


# ── Compound finding: unstable_deep_module ───────────────────────────


def test_unstable_deep_module_count():
    items = R["findings"]["items"]
    udm = [i for i in items if i["type"] == "unstable_deep_module"]
    assert len(udm) == 3


def test_unstable_deep_module_members():
    items = R["findings"]["items"]
    udm = [i for i in items if i["type"] == "unstable_deep_module"]
    modules = sorted(i["module"] for i in udm)
    assert modules == ["async-rt", "core-lib", "crypto-utils"], (
        "These crates have both depth > 3 AND instability > 0.4"
    )


def test_unstable_deep_module_details():
    items = R["findings"]["items"]
    udm = [i for i in items if i["type"] == "unstable_deep_module" and i["module"] == "core-lib"]
    assert len(udm) == 1
    det = udm[0]["details"]
    assert det["depth"] == 4
    assert math.isclose(det["instability"], 0.5, abs_tol=FLOAT_TOL)
    assert det["depth_threshold"] == 3
    assert math.isclose(det["instability_threshold"], 0.4, abs_tol=FLOAT_TOL)


def test_unstable_deep_module_does_not_suppress_individuals():
    items = R["findings"]["items"]
    deep_mods = {i["module"] for i in items if i["type"] == "deep_module"}
    hi_mods = {i["module"] for i in items if i["type"] == "high_instability"}
    assert "core-lib" in deep_mods, "deep_module still emitted alongside compound"
    assert "core-lib" in hi_mods, "high_instability still emitted alongside compound"
    assert "async-rt" in deep_mods
    assert "async-rt" in hi_mods


# ── Dead feature finding ─────────────────────────────────────────────


def test_dead_feature_count():
    items = R["findings"]["items"]
    df = [i for i in items if i["type"] == "dead_feature"]
    assert len(df) == 19


def test_dead_feature_examples():
    items = R["findings"]["items"]
    df = {(i["module"], i["details"]["feature"]) for i in items if i["type"] == "dead_feature"}
    assert ("app-server", "with-metrics") in df
    assert ("compression", "brotli") in df
    assert ("compression", "zstd") in df
    assert ("token-store", "encrypted") in df
    assert ("tls-provider", "rustls") in df


def test_dead_feature_excludes_unreachable():
    items = R["findings"]["items"]
    df = [i for i in items if i["type"] == "dead_feature"]
    df_mods = {i["module"] for i in df}
    assert "orphan-crate" not in df_mods, (
        "Dead features should not be reported for unreachable crates"
    )


def test_dead_feature_severity():
    items = R["findings"]["items"]
    df = [i for i in items if i["type"] == "dead_feature"]
    for f in df:
        assert f["severity"] == "low"


# ── Exports ──────────────────────────────────────────────────────────


def test_total_exports_core_lib():
    c = crate_by_name("core-lib")
    assert c["total_exports"] == 5, (
        "core-lib: 2 base + Serialize,Deserialize(serde) + AsyncEngine(async-support) = 5"
    )


def test_total_exports_http_layer():
    c = crate_by_name("http-layer")
    assert c["total_exports"] == 5, (
        "http-layer: 3 base + Http2Connection(http2) + WsHandler(websocket) = 5"
    )


def test_total_exports_orphan():
    c = crate_by_name("orphan-crate")
    assert c["total_exports"] == 1, (
        "Unreachable crates count only unconditional exports"
    )


def test_total_exports_utils():
    c = crate_by_name("utils")
    assert c["total_exports"] == 4, (
        "utils: 2 base + compute_hash,HashAlgo(hashing active) = 4"
    )


# ── Resolved dependencies ───────────────────────────────────────────


def test_resolved_deps_core_lib():
    c = crate_by_name("core-lib")
    assert sorted(c["resolved_dependencies"]) == [
        "async-rt", "logger", "serde-core", "utils"
    ]


def test_resolved_deps_http_layer():
    c = crate_by_name("http-layer")
    assert sorted(c["resolved_dependencies"]) == [
        "compression", "core-lib", "tls-provider", "ws-codec"
    ]


def test_resolved_deps_db_connector():
    c = crate_by_name("db-connector")
    assert sorted(c["resolved_dependencies"]) == [
        "conn-pool", "core-lib", "mysql-driver", "pg-driver", "query-builder"
    ]


# ── JSON format ──────────────────────────────────────────────────────


def test_json_has_trailing_newline():
    p = OUT_DIR / "build_plan.json"
    raw = p.read_bytes()
    assert raw.endswith(b"\n"), "Output must end with a trailing newline"


def test_json_two_space_indent():
    p = OUT_DIR / "build_plan.json"
    text = p.read_text(encoding="utf-8")
    assert '\n  "' in text, "Output should use 2-space indentation"
    assert "\t" not in text, "Output should not contain tabs"


# ── Input integrity ──────────────────────────────────────────────────


def test_input_files_not_modified():
    ws = json.loads((DATA_DIR / "workspace.json").read_text())
    assert ws["root_crate"] == "app-server"
    cfg = json.loads((DATA_DIR / "config.json").read_text())
    assert cfg["thresholds"]["max_depth"] == 3


def test_all_crate_files_present():
    crate_dir = DATA_DIR / "crates"
    files = sorted(p.stem for p in crate_dir.glob("*.json"))
    assert len(files) == 23
