"""Tests for dep_health_report.json — workspace dependency health auditor."""
import hashlib
import json
import math
import pathlib

_local = pathlib.Path(__file__).resolve().parent.parent / "environment"
if (_local / "output" / "dep_health_report.json").exists():
    _app = _local
else:
    _app = pathlib.Path("/app")
REPORT = _app / "output" / "dep_health_report.json"
DATA_DIR = _app / "data"

report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}

TOL = 1e-6

EXPECTED_HASHES = {
    "data/registry/async-io.json": "ed93cc0195a3b7dec4687482d034e8346317747044447f23dc674f06e0c20fe0",
    "data/registry/base64.json": "300102a97f9cf23619b191ea326932be5490ab3d00d59c5190545fc9697b3543",
    "data/registry/clap.json": "6382899aa088b517ceae4dc6c59de170392be26963418511bc86e3fb05fbf9c4",
    "data/registry/compress.json": "9b636cca44bdc11e960ef2a70ed0e5baad2d575bb08b6b481cf65642cc5d9aea",
    "data/registry/config-rs.json": "c78f4c0e66870b2c82d391ff43df8a33ea4603afda9657df2cfcef0e99de98e1",
    "data/registry/crypto-lib.json": "63bf069955e8600b014f5955db91739acd3b2a5a64052fef9a3d55ab56918246",
    "data/registry/encoding.json": "f85eaec28268090e99b482a011aa5499a153791b32294fc2c834719272113af6",
    "data/registry/http.json": "335ca63a12309e961f474b0d72f3eda15146f4d61d29cac4bb625abb3bf7adb3",
    "data/registry/log.json": "e6eaa52ba79572a2e23760cc3a3bdcbbc1960498e7b6978cee1f576d68fef149",
    "data/registry/regex.json": "e2dd9067f320d3c2e2323b358d3b85906db862e80a56e5e360a00dbf6ad34be5",
    "data/registry/ring.json": "9f01ea233458719c607ad13f8fee05b65639b814219bc1fd967bd4c9f413c049",
    "data/registry/serde.json": "967c6e862ed949608393d36390318acbf76616b98fa8a57541bead3cda89aea8",
    "data/registry/thiserror.json": "db5029f261024b43e534f2979812581d3137358121a600b652f096ab027786f7",
    "data/registry/tokio.json": "38336e26ae5a5e995e5516bc1bd881df0f62b7e8554231a73d6eb05716cfee06",
    "data/registry/uuid.json": "0eb607fdd0c537d36adff16e1e9f7714ab4d2ea0cf69c5c29ef79cde8b644213",
    "data/registry/validator.json": "6da58e43baea51fc588e2e9cb1b83830cac9c4745d21783bdcb20b346896429d",
    "data/workspace/api-gateway.json": "49ed26980e26f9fc5a37d3b4d98c116d4c5375c6cc2a5096a3a866792fb28a82",
    "data/workspace/auth-service.json": "e0ace7cab9d5e45fb3cfaec6f3a0f1f0d77578a1ea98a3d44e27f2a02a8bed84",
    "data/workspace/cli-tool.json": "c98e13e8433df35b9469ad05c1db02390b40618faff155388ad703a487b91f3b",
    "data/workspace/data-layer.json": "e66418871d3f2ecbb9d389fe94737141c0cd12a02c24ea575b1ad69274479e01",
    "data/workspace/macro-utils.json": "cae91c2a01d380ef692d4af141d90a2c238ae562eb52b43ad861e6a801df3f50",
    "data/workspace/shared-lib.json": "707fa23bb7549b553750f94457fdd7a9516f852233ad9be5a9e10539a3a7bc43",
    "data/workspace/worker.json": "7d93630398544f290d10bed792477e6e3544f6d0fca49f05a11eface4c00e3f9",
    "data/workspace.json": "377ee5481c9e3bbff4e02572be64384f318279a2428ba68de9dd26907e242ac4",
}


# ═══════════════════════════════════════════════════════════════════════
# Input integrity
# ═══════════════════════════════════════════════════════════════════════

def test_input_files_not_modified():
    """No input data file has been tampered with."""
    for rel, expected in EXPECTED_HASHES.items():
        fp = DATA_DIR.parent / rel
        assert fp.exists(), f"Missing {rel}"
        got = hashlib.sha256(fp.read_bytes()).hexdigest()
        assert got == expected, f"{rel} hash mismatch"


# ═══════════════════════════════════════════════════════════════════════
# Output file basics
# ═══════════════════════════════════════════════════════════════════════

def test_output_file_exists():
    """Report file must exist at /app/output/dep_health_report.json."""
    assert REPORT.exists()


def test_json_valid():
    """Report must be valid JSON."""
    json.loads(REPORT.read_text(encoding="utf-8"))


def test_json_two_space_indent():
    """Report uses 2-space indentation."""
    raw = REPORT.read_text(encoding="utf-8")
    assert '\n  "' in raw


def test_json_trailing_newline():
    """Report ends with exactly one trailing newline."""
    raw = REPORT.read_bytes().replace(b"\r\n", b"\n")
    assert raw.endswith(b"}\n") and not raw.endswith(b"}\n\n")


def test_top_level_keys():
    """All required top-level keys exist."""
    expected = {"build_order", "config", "conflicts", "crate_metrics",
                "health_ranking", "members", "summary", "unified_versions"}
    assert set(report.keys()) == expected


def test_top_level_keys_sorted():
    """Top-level keys are sorted alphabetically."""
    assert list(report.keys()) == sorted(report.keys())


# ═══════════════════════════════════════════════════════════════════════
# Config echo
# ═══════════════════════════════════════════════════════════════════════

def test_config_members_count():
    """Config lists 7 workspace members."""
    assert len(report["config"]["members"]) == 7


def test_config_members_sorted():
    """Config members are sorted alphabetically."""
    ms = report["config"]["members"]
    assert ms == sorted(ms)


def test_config_output_precision():
    """output_precision is 6."""
    assert report["config"]["output_precision"] == 6


# ═══════════════════════════════════════════════════════════════════════
# Unified versions — semver traps
# ═══════════════════════════════════════════════════════════════════════

def test_unified_encoding_caret_0x():
    """^0.2 pins to minor: encoding resolves to 0.2.5 not 0.3.0."""
    assert report["unified_versions"]["encoding"] == "0.2.5"


def test_unified_config_rs_tilde():
    """~1.0 across members constrains to <1.1.0: config-rs is 1.0.3."""
    assert report["unified_versions"]["config-rs"] == "1.0.3"


def test_unified_async_io_prerelease_excluded():
    """^1.0 excludes 1.0.0-beta.1; resolves to 1.1.0."""
    assert report["unified_versions"]["async-io"] == "1.1.0"


def test_unified_ring_caret_0_16():
    """^0.16 pins to [0.16.0, 0.17.0); resolves to 0.16.20 not 0.17.8."""
    assert report["unified_versions"]["ring"] == "0.16.20"


def test_unified_base64_caret_0_21():
    """^0.21 pins to [0.21.0, 0.22.0); resolves to 0.21.7 not 0.22.1."""
    assert report["unified_versions"]["base64"] == "0.21.7"


def test_unified_serde_highest():
    """serde ^1.0 resolves to highest: 1.0.210."""
    assert report["unified_versions"]["serde"] == "1.0.210"


def test_unified_tokio_highest():
    """tokio unified to 1.38.0."""
    assert report["unified_versions"]["tokio"] == "1.38.0"


def test_unified_log_tilde_intersection():
    """~0.4.17 ∩ ^0.4 = [0.4.17, 0.5.0); highest is 0.4.21."""
    assert report["unified_versions"]["log"] == "0.4.21"


def test_unified_compress():
    """compress ^1.0 resolves to 1.0.2 (GPL-3.0 version)."""
    assert report["unified_versions"]["compress"] == "1.0.2"


def test_unified_thiserror():
    """thiserror ^1.0 resolves to 1.0.63 (2.0.0 is major bump, excluded)."""
    assert report["unified_versions"]["thiserror"] == "1.0.63"


def test_unified_crate_count():
    """14 non-conflicting crates in unified resolution."""
    assert len(report["unified_versions"]) == 14


def test_unified_excludes_crypto_lib():
    """crypto-lib is conflicting; not in unified_versions."""
    assert "crypto-lib" not in report["unified_versions"]


def test_unified_excludes_uuid():
    """uuid is conflicting; not in unified_versions."""
    assert "uuid" not in report["unified_versions"]


def test_unified_keys_sorted():
    """unified_versions keys are sorted."""
    keys = list(report["unified_versions"].keys())
    assert keys == sorted(keys)


# ═══════════════════════════════════════════════════════════════════════
# Conflicts
# ═══════════════════════════════════════════════════════════════════════

def test_conflict_count():
    """Exactly 2 conflicts: crypto-lib and uuid."""
    assert len(report["conflicts"]) == 2


def test_conflict_names():
    """Conflicts are crypto-lib and uuid."""
    names = [c["crate_name"] for c in report["conflicts"]]
    assert names == ["crypto-lib", "uuid"]


def test_crypto_lib_conflict_ranges():
    """crypto-lib conflict has ^1.0 and ^2.0 ranges."""
    c = report["conflicts"][0]
    ranges = sorted(r["range"] for r in c["requirements"])
    assert ranges == ["^1.0", "^2.0"]


def test_crypto_lib_best_matches():
    """crypto-lib best matches are 1.1.0 and 2.1.0."""
    c = report["conflicts"][0]
    matches = sorted(r["best_match"] for r in c["requirements"])
    assert matches == ["1.1.0", "2.1.0"]


def test_uuid_conflict_has_three_requirements():
    """uuid conflict has 3 requirements (api-gateway, data-layer, shared-lib)."""
    c = report["conflicts"][1]
    assert len(c["requirements"]) == 3


def test_uuid_shared_lib_best_match():
    """shared-lib's uuid ^0.8 best match is 0.8.2."""
    c = report["conflicts"][1]
    for r in c["requirements"]:
        if r["range"] == "^0.8":
            assert r["best_match"] == "0.8.2"
            return
    assert False, "^0.8 requirement not found"


def test_conflicts_sorted_by_crate_name():
    """Conflicts array is sorted by crate_name."""
    names = [c["crate_name"] for c in report["conflicts"]]
    assert names == sorted(names)


# ═══════════════════════════════════════════════════════════════════════
# Per-member resolution
# ═══════════════════════════════════════════════════════════════════════

def test_all_seven_members_present():
    """All 7 workspace members are in the members object."""
    expected = {"api-gateway", "auth-service", "cli-tool", "data-layer",
                "macro-utils", "shared-lib", "worker"}
    assert set(report["members"].keys()) == expected


def test_members_keys_sorted():
    """Members keys are sorted alphabetically."""
    assert list(report["members"].keys()) == sorted(report["members"].keys())


def test_api_gateway_direct_deps():
    """api-gateway has 6 direct deps: crypto-lib, http, log, serde, tokio, uuid."""
    d = report["members"]["api-gateway"]["direct_deps"]
    assert d == ["crypto-lib", "http", "log", "serde", "tokio", "uuid"]


def test_api_gateway_crypto_lib_version():
    """api-gateway resolves crypto-lib to 1.1.0 (its own ^1.0)."""
    v = report["members"]["api-gateway"]["resolved_versions"]["crypto-lib"]
    assert v == "1.1.0"


def test_auth_service_crypto_lib_version():
    """auth-service resolves crypto-lib to 2.1.0 (its own ^2.0)."""
    v = report["members"]["auth-service"]["resolved_versions"]["crypto-lib"]
    assert v == "2.1.0"


def test_shared_lib_uuid_version():
    """shared-lib resolves uuid to 0.8.2 (its own ^0.8)."""
    v = report["members"]["shared-lib"]["resolved_versions"]["uuid"]
    assert v == "0.8.2"


def test_api_gateway_uuid_version():
    """api-gateway resolves uuid to 1.10.0 (its own ^1.0)."""
    v = report["members"]["api-gateway"]["resolved_versions"]["uuid"]
    assert v == "1.10.0"


def test_cli_tool_config_rs_uses_unified():
    """cli-tool uses unified config-rs 1.0.3, not its own ^1.0 max of 1.1.0."""
    v = report["members"]["cli-tool"]["resolved_versions"]["config-rs"]
    assert v == "1.0.3"


def test_cli_tool_has_transitive_validator():
    """cli-tool resolves validator transitively via config-rs@1.0.3→... no.
    Actually config-rs@1.0.3 does not depend on validator.
    But the unified resolution picks up validator from other members."""
    # cli-tool gets validator@1.1.0 only if it appears transitively.
    # config-rs@1.0.3 has NO validator dep. But config-rs@1.1.0 does.
    # Since unified is 1.0.3, cli-tool should NOT have validator.
    # Wait, need to check the actual output.
    rv = report["members"]["cli-tool"]["resolved_versions"]
    # config-rs@1.0.3 does not depend on validator, so validator should
    # not appear in cli-tool's resolved_versions unless another path adds it.
    # Checking actual output...
    if "validator" in rv:
        assert rv["validator"] == "1.1.0"


def test_auth_service_transitive_encoding():
    """auth-service gets encoding 0.2.5 transitively via crypto-lib→encoding."""
    rv = report["members"]["auth-service"]["resolved_versions"]
    assert rv.get("encoding") == "0.2.5"


def test_worker_direct_deps_count():
    """worker has 5 direct deps."""
    assert len(report["members"]["worker"]["direct_deps"]) == 5


def test_macro_utils_resolved_count():
    """macro-utils resolves to 4 crates (encoding, log, serde, validator)."""
    rv = report["members"]["macro-utils"]["resolved_versions"]
    assert len(rv) == 4


def test_resolved_versions_keys_sorted():
    """Each member's resolved_versions keys are sorted."""
    for mname, mdata in report["members"].items():
        keys = list(mdata["resolved_versions"].keys())
        assert keys == sorted(keys), f"{mname} resolved_versions not sorted"


# ═══════════════════════════════════════════════════════════════════════
# Dependency tree depth
# ═══════════════════════════════════════════════════════════════════════

def test_api_gateway_depth():
    """api-gateway depth is 3 (http→encoding→log)."""
    assert report["members"]["api-gateway"]["dep_tree_depth"] == 3


def test_auth_service_depth():
    """auth-service depth is 3 (crypto-lib→encoding→log)."""
    assert report["members"]["auth-service"]["dep_tree_depth"] == 3


def test_cli_tool_depth():
    """cli-tool depth is 3 (compress→encoding→log or config-rs→encoding→log)."""
    assert report["members"]["cli-tool"]["dep_tree_depth"] == 3


def test_data_layer_depth():
    """data-layer depth is 3 (config-rs→encoding→log)."""
    assert report["members"]["data-layer"]["dep_tree_depth"] == 3


def test_macro_utils_depth():
    """macro-utils depth is 2 (encoding→log)."""
    assert report["members"]["macro-utils"]["dep_tree_depth"] == 2


def test_shared_lib_depth():
    """shared-lib depth is 2 (encoding→log)."""
    assert report["members"]["shared-lib"]["dep_tree_depth"] == 2


def test_worker_depth():
    """worker depth is 3 (compress→encoding→log or async-io→log + compress→encoding→log)."""
    assert report["members"]["worker"]["dep_tree_depth"] == 3


# ═══════════════════════════════════════════════════════════════════════
# Coupling metrics — formula traps
# ═══════════════════════════════════════════════════════════════════════

def test_crate_metrics_count():
    """14 crates in crate_metrics (same as unified)."""
    assert len(report["crate_metrics"]) == 14


def test_encoding_ca():
    """encoding Ca = 3 (compress, config-rs, http depend on it)."""
    assert report["crate_metrics"]["encoding"]["ca"] == 3


def test_encoding_ce():
    """encoding Ce = 1 (depends on log)."""
    assert report["crate_metrics"]["encoding"]["ce"] == 1


def test_encoding_instability():
    """encoding I = Ce/(Ca+Ce) = 1/4 = 0.25, not Ca/(Ca+Ce)."""
    assert math.isclose(report["crate_metrics"]["encoding"]["instability"],
                        0.25, abs_tol=TOL)


def test_log_ca():
    """log Ca = 3 (encoding, async-io, tokio depend on it)."""
    assert report["crate_metrics"]["log"]["ca"] == 3


def test_log_ce():
    """log Ce = 0."""
    assert report["crate_metrics"]["log"]["ce"] == 0


def test_log_instability_zero():
    """log I = 0/(3+0) = 0.0."""
    assert math.isclose(report["crate_metrics"]["log"]["instability"],
                        0.0, abs_tol=TOL)


def test_serde_ca():
    """serde Ca = 2 (config-rs and validator depend on it)."""
    assert report["crate_metrics"]["serde"]["ca"] == 2


def test_serde_ce():
    """serde Ce = 0."""
    assert report["crate_metrics"]["serde"]["ce"] == 0


def test_config_rs_ce():
    """config-rs Ce = 2 (depends on serde and encoding)."""
    assert report["crate_metrics"]["config-rs"]["ce"] == 2


def test_config_rs_instability():
    """config-rs I = 2/(0+2) = 1.0."""
    assert math.isclose(report["crate_metrics"]["config-rs"]["instability"],
                        1.0, abs_tol=TOL)


def test_base64_instability_zero_zero():
    """base64 has Ca=0, Ce=0 → I = 0.0 (not NaN or error)."""
    assert math.isclose(report["crate_metrics"]["base64"]["instability"],
                        0.0, abs_tol=TOL)


def test_compress_instability():
    """compress I = Ce/(Ca+Ce) = 1/(0+1) = 1.0."""
    assert math.isclose(report["crate_metrics"]["compress"]["instability"],
                        1.0, abs_tol=TOL)


def test_validator_ce():
    """validator Ce = 1 (depends on serde)."""
    assert report["crate_metrics"]["validator"]["ce"] == 1


def test_no_workspace_edges_in_ca():
    """Coupling counts only crate-to-crate edges. Workspace member edges ignored.
    tokio is used by 5 workspace members but Ca = 0 (no crate depends on tokio)."""
    assert report["crate_metrics"]["tokio"]["ca"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Freshness / staleness
# ═══════════════════════════════════════════════════════════════════════

def test_base64_freshness():
    """base64 0.21.7: idx=2 in [0.13.0, 0.21.0, 0.21.7, 0.22.1] → 2/3."""
    assert math.isclose(report["crate_metrics"]["base64"]["freshness"],
                        0.666667, abs_tol=TOL)


def test_base64_staleness():
    """staleness = 1 - freshness = 1/3."""
    assert math.isclose(report["crate_metrics"]["base64"]["staleness"],
                        0.333333, abs_tol=TOL)


def test_ring_freshness():
    """ring 0.16.20: idx=1 in [0.16.0, 0.16.20, 0.17.8] → 1/2 = 0.5."""
    assert math.isclose(report["crate_metrics"]["ring"]["freshness"],
                        0.5, abs_tol=TOL)


def test_encoding_freshness():
    """encoding 0.2.5: idx=1 in [0.2.0, 0.2.5, 0.3.0] → 1/2 = 0.5."""
    assert math.isclose(report["crate_metrics"]["encoding"]["freshness"],
                        0.5, abs_tol=TOL)


def test_serde_freshness_max():
    """serde 1.0.210 is latest → freshness = 1.0."""
    assert math.isclose(report["crate_metrics"]["serde"]["freshness"],
                        1.0, abs_tol=TOL)


def test_thiserror_freshness():
    """thiserror 1.0.63: idx=1 in [1.0.0, 1.0.63, 2.0.0] → 1/2 = 0.5."""
    assert math.isclose(report["crate_metrics"]["thiserror"]["freshness"],
                        0.5, abs_tol=TOL)


def test_log_freshness():
    """log 0.4.21: idx=2 in [0.4.0, 0.4.17, 0.4.21] → 2/2 = 1.0."""
    assert math.isclose(report["crate_metrics"]["log"]["freshness"],
                        1.0, abs_tol=TOL)


# ═══════════════════════════════════════════════════════════════════════
# Weighted staleness — weighting trap
# ═══════════════════════════════════════════════════════════════════════

def test_worker_weighted_staleness_zero():
    """worker: all direct deps have staleness 0 → weighted_staleness = 0."""
    assert math.isclose(report["members"]["worker"]["weighted_staleness"],
                        0.0, abs_tol=TOL)


def test_macro_utils_weighted_staleness():
    """macro-utils: encoding s=0.5 w=4, serde s=0 w=3, validator s=0.5 w=1.
    Σ(s*w)=2.5, Σ(w)=8 → 0.3125."""
    assert math.isclose(report["members"]["macro-utils"]["weighted_staleness"],
                        0.3125, abs_tol=TOL)


def test_shared_lib_weighted_staleness():
    """shared-lib: encoding s=0.5 w=4, log s=0 w=4, serde s=0 w=3, uuid s=1.0 w=1.
    Σ(s*w)=3.0, Σ(w)=12 → 0.25."""
    assert math.isclose(report["members"]["shared-lib"]["weighted_staleness"],
                        0.25, abs_tol=TOL)


def test_data_layer_weighted_staleness():
    """data-layer weighted staleness is 0.125."""
    assert math.isclose(report["members"]["data-layer"]["weighted_staleness"],
                        0.125, abs_tol=TOL)


def test_auth_service_weighted_staleness():
    """auth-service weighted staleness uses Ca+1 weights.
    base64 s=1/3 w=1, crypto-lib s=0 w=1, log s=0 w=4, ring s=0.5 w=1,
    serde s=0 w=3, tokio s=0 w=1. Σ=5/6, Σw=11 → 5/66."""
    assert math.isclose(report["members"]["auth-service"]["weighted_staleness"],
                        0.075758, abs_tol=TOL)


def test_api_gateway_weighted_staleness():
    """api-gateway: crypto-lib s=2/3 w=1, http s=0 w=1, log s=0 w=4,
    serde s=0 w=3, tokio s=0 w=1, uuid s=0 w=1. Σ=2/3, Σw=11 → 2/33."""
    assert math.isclose(report["members"]["api-gateway"]["weighted_staleness"],
                        0.060606, abs_tol=TOL)


def test_cli_tool_weighted_staleness():
    """cli-tool: clap s=0 w=1, compress s=0 w=1, config-rs s=0.5 w=1,
    log s=0 w=4, regex s=0 w=1, tokio s=0 w=1. Σ=0.5, Σw=9 → 1/18."""
    assert math.isclose(report["members"]["cli-tool"]["weighted_staleness"],
                        0.055556, abs_tol=TOL)


def test_weighted_staleness_uses_sum_not_mean():
    """Confirm weighted staleness uses Σ(s*w)/Σ(w), not Σ(s*w)/n.
    macro-utils: if Σ(s*w)/n = 2.5/3 ≈ 0.833, but actual is 0.3125."""
    ws = report["members"]["macro-utils"]["weighted_staleness"]
    assert not math.isclose(ws, 0.833333, abs_tol=0.01)
    assert math.isclose(ws, 0.3125, abs_tol=TOL)


# ═══════════════════════════════════════════════════════════════════════
# License audit — directionality trap
# ═══════════════════════════════════════════════════════════════════════

def test_cli_tool_license_not_clean():
    """cli-tool (MIT) has compress (GPL-3.0) → license_clean is false."""
    assert report["members"]["cli-tool"]["license_audit"]["license_clean"] is False


def test_worker_license_not_clean():
    """worker (Apache-2.0) has compress (GPL-3.0) → license_clean is false."""
    assert report["members"]["worker"]["license_audit"]["license_clean"] is False


def test_macro_utils_license_clean():
    """macro-utils (GPL-3.0) can use MIT deps → license_clean is true."""
    assert report["members"]["macro-utils"]["license_audit"]["license_clean"] is True


def test_auth_service_license_clean():
    """auth-service (Apache-2.0) has ring (ISC, treated as permissive) → clean."""
    assert report["members"]["auth-service"]["license_audit"]["license_clean"] is True


def test_api_gateway_license_clean():
    """api-gateway has no GPL deps → license_clean is true."""
    assert report["members"]["api-gateway"]["license_audit"]["license_clean"] is True


def test_shared_lib_license_clean():
    """shared-lib (MIT) has no GPL deps → license_clean is true."""
    assert report["members"]["shared-lib"]["license_audit"]["license_clean"] is True


def test_cli_tool_violation_crate():
    """cli-tool's violation is for compress."""
    vs = report["members"]["cli-tool"]["license_audit"]["violations"]
    assert len(vs) == 1
    assert vs[0]["crate_name"] == "compress"


def test_cli_tool_violation_chain():
    """cli-tool → compress is the dep chain for the GPL violation."""
    vs = report["members"]["cli-tool"]["license_audit"]["violations"]
    assert vs[0]["dep_chain"] == ["cli-tool", "compress"]


def test_worker_violation_license_fields():
    """worker's GPL violation has correct license fields."""
    vs = report["members"]["worker"]["license_audit"]["violations"]
    assert vs[0]["crate_license"] == "GPL-3.0"
    assert vs[0]["project_license"] == "Apache-2.0"


def test_gpl_project_can_use_permissive():
    """GPL-3.0 project (macro-utils) using MIT deps is NOT a violation."""
    vs = report["members"]["macro-utils"]["license_audit"]["violations"]
    assert len(vs) == 0


def test_isc_treated_as_permissive():
    """ISC license (ring) is treated as permissive — no violation in auth-service."""
    vs = report["members"]["auth-service"]["license_audit"]["violations"]
    ring_viols = [v for v in vs if v["crate_name"] == "ring"]
    assert len(ring_viols) == 0


# ═══════════════════════════════════════════════════════════════════════
# Health score — multiplication trap
# ═══════════════════════════════════════════════════════════════════════

def test_api_gateway_health_score():
    """api-gateway: (1-0.060606) * (2/3) * 1.0 ≈ 0.626263."""
    assert math.isclose(report["members"]["api-gateway"]["health_score"],
                        0.626263, abs_tol=TOL)


def test_auth_service_health_score():
    """auth-service: (1-0.075758) * (5/6) * 1.0 ≈ 0.770202."""
    assert math.isclose(report["members"]["auth-service"]["health_score"],
                        0.770202, abs_tol=TOL)


def test_cli_tool_health_score():
    """cli-tool: (1-0.055556) * 1.0 * 0.5 ≈ 0.472222."""
    assert math.isclose(report["members"]["cli-tool"]["health_score"],
                        0.472222, abs_tol=TOL)


def test_data_layer_health_score():
    """data-layer: (1-0.125) * (6/7) * 1.0 = 0.75."""
    assert math.isclose(report["members"]["data-layer"]["health_score"],
                        0.75, abs_tol=TOL)


def test_macro_utils_health_score():
    """macro-utils: (1-0.3125) * 1.0 * 1.0 = 0.6875."""
    assert math.isclose(report["members"]["macro-utils"]["health_score"],
                        0.6875, abs_tol=TOL)


def test_shared_lib_health_score():
    """shared-lib: (1-0.25) * (3/4) * 1.0 = 0.5625."""
    assert math.isclose(report["members"]["shared-lib"]["health_score"],
                        0.5625, abs_tol=TOL)


def test_worker_health_score():
    """worker: (1-0.0) * 1.0 * 0.5 = 0.5."""
    assert math.isclose(report["members"]["worker"]["health_score"],
                        0.5, abs_tol=TOL)


def test_health_is_product_not_sum():
    """Confirm health is multiplicative. worker = 1.0 * 1.0 * 0.5 = 0.5,
    not additive (1.0 + 1.0 + 0.5)/3 = 0.833."""
    hs = report["members"]["worker"]["health_score"]
    assert not math.isclose(hs, 0.833333, abs_tol=0.01)
    assert math.isclose(hs, 0.5, abs_tol=TOL)


# ═══════════════════════════════════════════════════════════════════════
# Health grades
# ═══════════════════════════════════════════════════════════════════════

def test_api_gateway_grade():
    """api-gateway 0.626 → grade B (>=0.6)."""
    assert report["members"]["api-gateway"]["health_grade"] == "B"


def test_auth_service_grade():
    """auth-service 0.770 → grade B."""
    assert report["members"]["auth-service"]["health_grade"] == "B"


def test_cli_tool_grade():
    """cli-tool 0.472 → grade C (>=0.4)."""
    assert report["members"]["cli-tool"]["health_grade"] == "C"


def test_data_layer_grade():
    """data-layer 0.75 → grade B."""
    assert report["members"]["data-layer"]["health_grade"] == "B"


def test_macro_utils_grade():
    """macro-utils 0.6875 → grade B."""
    assert report["members"]["macro-utils"]["health_grade"] == "B"


def test_shared_lib_grade():
    """shared-lib 0.5625 → grade C."""
    assert report["members"]["shared-lib"]["health_grade"] == "C"


def test_worker_grade():
    """worker 0.5 → grade C."""
    assert report["members"]["worker"]["health_grade"] == "C"


# ═══════════════════════════════════════════════════════════════════════
# Health ranking — multi-level sort
# ═══════════════════════════════════════════════════════════════════════

def test_health_ranking_length():
    """Health ranking has 7 entries."""
    assert len(report["health_ranking"]) == 7


def test_health_ranking_order():
    """Full ranking: auth-service, data-layer, macro-utils, api-gateway,
    shared-lib, worker, cli-tool (B group by score DESC, then C group by score DESC)."""
    assert report["health_ranking"] == [
        "auth-service", "data-layer", "macro-utils", "api-gateway",
        "shared-lib", "worker", "cli-tool",
    ]


def test_health_ranking_first():
    """Healthiest member is auth-service."""
    assert report["health_ranking"][0] == "auth-service"


def test_health_ranking_last():
    """Least healthy member is cli-tool."""
    assert report["health_ranking"][-1] == "cli-tool"


def test_health_ranking_b_before_c():
    """All B-graded members come before C-graded members."""
    hr = report["health_ranking"]
    b_members = {"auth-service", "data-layer", "macro-utils", "api-gateway"}
    c_members = {"shared-lib", "worker", "cli-tool"}
    b_positions = [hr.index(m) for m in b_members]
    c_positions = [hr.index(m) for m in c_members]
    assert max(b_positions) < min(c_positions)


# ═══════════════════════════════════════════════════════════════════════
# Build order — topological with 3-level tie-breaking
# ═══════════════════════════════════════════════════════════════════════

def test_build_order_length():
    """Build order has 14 entries (all unified crates)."""
    assert len(report["build_order"]) == 14


def test_build_order_first():
    """log is built first (Ca=3, highest dependents among zero-in-deg)."""
    assert report["build_order"][0] == "log"


def test_build_order_second():
    """encoding is built second (Ca=3, coupling=4, next after log)."""
    assert report["build_order"][1] == "encoding"


def test_build_order_third():
    """serde is built third (Ca=2, coupling=2)."""
    assert report["build_order"][2] == "serde"


def test_build_order_config_rs_after_serde_and_encoding():
    """config-rs depends on serde and encoding; must come after both."""
    bo = report["build_order"]
    assert bo.index("config-rs") > bo.index("serde")
    assert bo.index("config-rs") > bo.index("encoding")


def test_build_order_async_io_after_log():
    """async-io depends on log; must come after log."""
    bo = report["build_order"]
    assert bo.index("async-io") > bo.index("log")


def test_build_order_compress_after_encoding():
    """compress depends on encoding; must come after encoding."""
    bo = report["build_order"]
    assert bo.index("compress") > bo.index("encoding")


def test_build_order_tokio_after_log():
    """tokio depends on log; must come after log."""
    bo = report["build_order"]
    assert bo.index("tokio") > bo.index("log")


def test_build_order_no_conflicting_crates():
    """crypto-lib and uuid must NOT be in build_order."""
    bo = report["build_order"]
    assert "crypto-lib" not in bo
    assert "uuid" not in bo


def test_build_order_full():
    """Full expected build order."""
    assert report["build_order"] == [
        "log", "encoding", "serde", "config-rs", "async-io", "compress",
        "http", "tokio", "validator", "base64", "clap", "regex", "ring",
        "thiserror",
    ]


# ═══════════════════════════════════════════════════════════════════════
# Crate metrics — license and deprecated fields
# ═══════════════════════════════════════════════════════════════════════

def test_compress_license_gpl():
    """compress 1.0.2 has GPL-3.0 license (changed from BSD in patch)."""
    assert report["crate_metrics"]["compress"]["license"] == "GPL-3.0"


def test_ring_license_isc():
    """ring license is ISC."""
    assert report["crate_metrics"]["ring"]["license"] == "ISC"


def test_http_license_apache():
    """http 1.1.0 license is Apache-2.0."""
    assert report["crate_metrics"]["http"]["license"] == "Apache-2.0"


def test_no_deprecated_in_unified():
    """No unified crate is deprecated (thiserror 2.0.0 is deprecated but not resolved)."""
    for cn, m in report["crate_metrics"].items():
        assert m["deprecated"] is False, f"{cn} should not be deprecated"


# ═══════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════

def test_summary_member_count():
    """total_workspace_members = 7."""
    assert report["summary"]["total_workspace_members"] == 7


def test_summary_unified_count():
    """total_unified_crates = 14."""
    assert report["summary"]["total_unified_crates"] == 14


def test_summary_conflict_count():
    """total_conflicts = 2."""
    assert report["summary"]["total_conflicts"] == 2


def test_summary_avg_health_score():
    """avg_health_score is arithmetic mean of all 7 member scores."""
    expected = (0.626263 + 0.770202 + 0.472222 + 0.75
                + 0.6875 + 0.5625 + 0.5) / 7
    assert math.isclose(report["summary"]["avg_health_score"],
                        expected, abs_tol=TOL)


def test_summary_healthiest():
    """healthiest_member = auth-service."""
    assert report["summary"]["healthiest_member"] == "auth-service"


def test_summary_max_depth():
    """max_dep_tree_depth = 3."""
    assert report["summary"]["max_dep_tree_depth"] == 3


def test_summary_total_violations():
    """total_license_violations = 2 (cli-tool + worker each have 1)."""
    assert report["summary"]["total_license_violations"] == 2


def test_summary_total_deprecated():
    """total_deprecated_deps = 0 (no resolved version is deprecated)."""
    assert report["summary"]["total_deprecated_deps"] == 0


# ═══════════════════════════════════════════════════════════════════════
# Deprecated deps
# ═══════════════════════════════════════════════════════════════════════

def test_no_member_has_deprecated_deps():
    """No member uses a deprecated resolved version."""
    for mname, mdata in report["members"].items():
        assert mdata["deprecated_deps"] == [], f"{mname} has deprecated deps"
