"""Tests for rust-semver-resolver."""
import json
import pathlib

ROOT = pathlib.Path("/app")

OUT_DIR = pathlib.pathlib.Path('/app/output')


def load_report():
    """Load the resolution report JSON."""
    p = OUT_DIR / "resolution_report.json"
    assert p.is_file(), f"Missing output file: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


# ── Output existence and structure ──────────────────────────────────────


def test_output_file_exists():
    """Verify the resolution report file was created."""
    assert (OUT_DIR / "resolution_report.json").is_file()


def test_top_level_keys():
    """Verify the report contains exactly the four required top-level keys."""
    data = load_report()
    assert set(data.keys()) == {"conflicts", "metadata", "resolutions", "statistics"}


def test_top_level_keys_sorted():
    """Verify top-level keys appear in alphabetical order."""
    raw = (OUT_DIR / "resolution_report.json").read_text(encoding="utf-8")
    data = json.loads(raw)
    assert list(data.keys()) == sorted(data.keys())


def test_json_two_space_indent():
    """Verify the output uses 2-space indentation."""
    raw = (OUT_DIR / "resolution_report.json").read_text(encoding="utf-8")
    for line in raw.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent > 0:
            assert indent % 2 == 0, f"Odd indent of {indent} on: {line!r}"


def test_json_trailing_newline():
    """Verify the output file ends with exactly one trailing newline."""
    raw = (OUT_DIR / "resolution_report.json").read_text(encoding="utf-8")
    assert raw.endswith("\n") and not raw.endswith("\n\n")


# ── Metadata ────────────────────────────────────────────────────────────


def test_metadata_project_count():
    """Verify the project count equals the number of manifest files."""
    data = load_report()
    assert data["metadata"]["project_count"] == 7


def test_metadata_registry_package_count():
    """Verify the registry package count matches the input data."""
    data = load_report()
    assert data["metadata"]["registry_package_count"] == 20


def test_metadata_registry_version_count():
    """Verify the total version count across all registry packages."""
    data = load_report()
    assert data["metadata"]["registry_version_count"] == 64


# ── Resolutions: webapp ─────────────────────────────────────────────────


def test_webapp_tokio():
    """Verify webapp resolves tokio ^1.0 to 1.38.0."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["tokio"] == "1.38.0"


def test_webapp_serde():
    """Verify webapp resolves serde ^1.0.100 to 1.0.210."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["serde"] == "1.0.210"


def test_webapp_http():
    """Verify webapp resolves http ^1.0 to 1.1.0."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["http"] == "1.1.0"


def test_webapp_log():
    """Verify webapp resolves log ~0.4.17 to 0.4.21."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["log"] == "0.4.21"


def test_webapp_uuid():
    """Verify webapp resolves uuid ^1.0 to 1.10.0."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["uuid"] == "1.10.0"


def test_webapp_clap():
    """Verify webapp resolves clap ^4.0 to 4.5.16."""
    data = load_report()
    assert data["resolutions"]["webapp"]["resolved"]["clap"] == "4.5.16"


def test_webapp_no_unresolved():
    """Verify webapp has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["webapp"]["unresolved"] == []


# ── Resolutions: auth-service (0.x caret traps) ────────────────────────


def test_auth_ring_resolved():
    """Verify auth-service resolves ring ^0.16 to 0.16.20, not 0.17.x.

    ^0.16 means >=0.16.0, <0.17.0 (minor is breaking for 0.x).
    """
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["ring"] == "0.16.20"


def test_auth_base64_resolved():
    """Verify auth-service resolves base64 ^0.21 to 0.21.7, not 0.22.x.

    ^0.21 means >=0.21.0, <0.22.0 (minor is breaking for 0.x).
    """
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["base64"] == "0.21.7"


def test_auth_sha2_resolved():
    """Verify auth-service resolves sha2 ^0.10 to 0.10.8."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["sha2"] == "0.10.8"


def test_auth_hmac_resolved():
    """Verify auth-service resolves hmac ^0.12 to 0.12.1."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["hmac"] == "0.12.1"


def test_auth_tokio_resolved():
    """Verify auth-service resolves tokio ^1.28 to 1.38.0."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["tokio"] == "1.38.0"


def test_auth_serde_resolved():
    """Verify auth-service resolves serde ^1.0 to 1.0.210."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["serde"] == "1.0.210"


def test_auth_log_resolved():
    """Verify auth-service resolves log ^0.4 to 0.4.21."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["resolved"]["log"] == "0.4.21"


def test_auth_no_unresolved():
    """Verify auth-service has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["auth-service"]["unresolved"] == []


# ── Resolutions: api-client (tilde trap + 0.x caret) ───────────────────


def test_api_client_http():
    """Verify api-client resolves http ^0.2 to 0.2.12."""
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["http"] == "0.2.12"


def test_api_client_bytes():
    """Verify api-client resolves bytes ~0.5.6 to 0.5.6.

    ~0.5.6 means >=0.5.6, <0.6.0. Only 0.5.6 is in range.
    """
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["bytes"] == "0.5.6"


def test_api_client_tokio():
    """Verify api-client resolves tokio ^0.2 to 0.2.25."""
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["tokio"] == "0.2.25"


def test_api_client_serde():
    """Verify api-client resolves serde ~1.0.197 to 1.0.210.

    ~1.0.197 means >=1.0.197, <1.1.0.
    """
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["serde"] == "1.0.210"


def test_api_client_url():
    """Verify api-client resolves url ^2.0 to 2.5.2."""
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["url"] == "2.5.2"


def test_api_client_log():
    """Verify api-client resolves log ^0.4 to 0.4.21."""
    data = load_report()
    assert data["resolutions"]["api-client"]["resolved"]["log"] == "0.4.21"


def test_api_client_no_unresolved():
    """Verify api-client has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["api-client"]["unresolved"] == []


# ── Resolutions: macro-utils ────────────────────────────────────────────


def test_macro_utils_syn():
    """Verify macro-utils resolves syn ^2.0 to 2.0.72."""
    data = load_report()
    assert data["resolutions"]["macro-utils"]["resolved"]["syn"] == "2.0.72"


def test_macro_utils_quote():
    """Verify macro-utils resolves quote ^1.0 to 1.0.37."""
    data = load_report()
    assert data["resolutions"]["macro-utils"]["resolved"]["quote"] == "1.0.37"


def test_macro_utils_proc_macro2():
    """Verify macro-utils resolves proc-macro2 ^1.0 to 1.0.86."""
    data = load_report()
    assert data["resolutions"]["macro-utils"]["resolved"]["proc-macro2"] == "1.0.86"


def test_macro_utils_no_unresolved():
    """Verify macro-utils has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["macro-utils"]["unresolved"] == []


# ── Resolutions: cli-tool ───────────────────────────────────────────────


def test_cli_tool_clap():
    """Verify cli-tool resolves clap ^3.0 to 3.2.25."""
    data = load_report()
    assert data["resolutions"]["cli-tool"]["resolved"]["clap"] == "3.2.25"


def test_cli_tool_anyhow():
    """Verify cli-tool resolves anyhow ^1.0 to 1.0.86."""
    data = load_report()
    assert data["resolutions"]["cli-tool"]["resolved"]["anyhow"] == "1.0.86"


def test_cli_tool_regex():
    """Verify cli-tool resolves regex ^1.5 to 1.10.6."""
    data = load_report()
    assert data["resolutions"]["cli-tool"]["resolved"]["regex"] == "1.10.6"


def test_cli_tool_tokio():
    """Verify cli-tool resolves tokio ^1.0 to 1.38.0."""
    data = load_report()
    assert data["resolutions"]["cli-tool"]["resolved"]["tokio"] == "1.38.0"


def test_cli_tool_no_unresolved():
    """Verify cli-tool has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["cli-tool"]["unresolved"] == []


# ── Resolutions: data-layer (pre-release trap) ─────────────────────────


def test_data_layer_thiserror():
    """Verify data-layer resolves thiserror ^2.0.0-rc.1 to 2.0.0.

    The stable 2.0.0 has higher precedence than 2.0.0-rc.1 and is within
    the range [2.0.0-rc.1, 3.0.0).
    """
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["thiserror"] == "2.0.0"


def test_data_layer_serde():
    """Verify data-layer resolves serde ~1.0.100 to 1.0.210.

    ~1.0.100 means >=1.0.100, <1.1.0.
    """
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["serde"] == "1.0.210"


def test_data_layer_chrono():
    """Verify data-layer resolves chrono ^0.4 to 0.4.38."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["chrono"] == "0.4.38"


def test_data_layer_futures():
    """Verify data-layer resolves futures ^0.3 to 0.3.30."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["futures"] == "0.3.30"


def test_data_layer_uuid():
    """Verify data-layer resolves uuid ^1.0 to 1.10.0."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["uuid"] == "1.10.0"


def test_data_layer_tokio():
    """Verify data-layer resolves tokio ^1.28 to 1.38.0."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["tokio"] == "1.38.0"


def test_data_layer_log():
    """Verify data-layer resolves log ~0.4.17 to 0.4.21."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["resolved"]["log"] == "0.4.21"


def test_data_layer_no_unresolved():
    """Verify data-layer has no unresolved dependencies."""
    data = load_report()
    assert data["resolutions"]["data-layer"]["unresolved"] == []


# ── Resolutions: legacy-bridge (unresolved trap) ───────────────────────


def test_legacy_bridge_ring_unresolved():
    """Verify legacy-bridge cannot resolve ring ^0.15.

    ^0.15 means >=0.15.0, <0.16.0 — no registry version matches.
    """
    data = load_report()
    assert "ring" in data["resolutions"]["legacy-bridge"]["unresolved"]


def test_legacy_bridge_log():
    """Verify legacy-bridge resolves log ^0.3 to 0.3.9.

    ^0.3 means >=0.3.0, <0.4.0 for a 0.x package.
    """
    data = load_report()
    assert data["resolutions"]["legacy-bridge"]["resolved"]["log"] == "0.3.9"


def test_legacy_bridge_uuid():
    """Verify legacy-bridge resolves uuid ^0.8 to 0.8.2.

    ^0.8 means >=0.8.0, <0.9.0.
    """
    data = load_report()
    assert data["resolutions"]["legacy-bridge"]["resolved"]["uuid"] == "0.8.2"


def test_legacy_bridge_tokio():
    """Verify legacy-bridge resolves tokio ^0.2 to 0.2.25."""
    data = load_report()
    assert data["resolutions"]["legacy-bridge"]["resolved"]["tokio"] == "0.2.25"


def test_legacy_bridge_serde():
    """Verify legacy-bridge resolves serde ^1.0 to 1.0.210."""
    data = load_report()
    assert data["resolutions"]["legacy-bridge"]["resolved"]["serde"] == "1.0.210"


def test_legacy_bridge_resolved_count():
    """Verify legacy-bridge has exactly 4 resolved dependencies."""
    data = load_report()
    assert len(data["resolutions"]["legacy-bridge"]["resolved"]) == 4


def test_legacy_bridge_unresolved_count():
    """Verify legacy-bridge has exactly 1 unresolved dependency."""
    data = load_report()
    assert len(data["resolutions"]["legacy-bridge"]["unresolved"]) == 1


# ── Conflicts ───────────────────────────────────────────────────────────


def test_conflict_count():
    """Verify there are exactly 5 cross-project conflicts."""
    data = load_report()
    assert len(data["conflicts"]) == 5


def test_conflicts_sorted_by_package():
    """Verify conflicts are sorted by package name."""
    data = load_report()
    names = [c["package"] for c in data["conflicts"]]
    assert names == sorted(names)


def test_clap_conflict_exists():
    """Verify clap has a conflict between webapp (^4.0) and cli-tool (^3.0)."""
    data = load_report()
    clap_conflicts = [c for c in data["conflicts"] if c["package"] == "clap"]
    assert len(clap_conflicts) == 1
    projects = clap_conflicts[0]["projects"]
    assert "webapp" in projects
    assert "cli-tool" in projects
    assert projects["webapp"]["resolved"] == "4.5.16"
    assert projects["cli-tool"]["resolved"] == "3.2.25"


def test_http_conflict_exists():
    """Verify http has a conflict between webapp (^1.0) and api-client (^0.2)."""
    data = load_report()
    http_conflicts = [c for c in data["conflicts"] if c["package"] == "http"]
    assert len(http_conflicts) == 1
    projects = http_conflicts[0]["projects"]
    assert projects["webapp"]["resolved"] == "1.1.0"
    assert projects["api-client"]["resolved"] == "0.2.12"


def test_log_conflict_exists():
    """Verify log has a conflict — legacy-bridge (^0.3) vs the 0.4.x group.

    ^0.3 yields [0.3.0, 0.4.0) while ^0.4/~0.4 yield [0.4.x, 0.5.0).
    """
    data = load_report()
    log_conflicts = [c for c in data["conflicts"] if c["package"] == "log"]
    assert len(log_conflicts) == 1
    projects = log_conflicts[0]["projects"]
    assert projects["legacy-bridge"]["resolved"] == "0.3.9"
    assert projects["webapp"]["resolved"] == "0.4.21"


def test_tokio_conflict_exists():
    """Verify tokio has a conflict between 0.2.x and 1.x groups."""
    data = load_report()
    tokio_conflicts = [c for c in data["conflicts"] if c["package"] == "tokio"]
    assert len(tokio_conflicts) == 1
    projects = tokio_conflicts[0]["projects"]
    assert projects["api-client"]["resolved"] == "0.2.25"
    assert projects["webapp"]["resolved"] == "1.38.0"


def test_uuid_conflict_exists():
    """Verify uuid has a conflict — legacy-bridge (0.8.x) vs webapp/data-layer (1.x)."""
    data = load_report()
    uuid_conflicts = [c for c in data["conflicts"] if c["package"] == "uuid"]
    assert len(uuid_conflicts) == 1
    projects = uuid_conflicts[0]["projects"]
    assert projects["legacy-bridge"]["resolved"] == "0.8.2"
    assert projects["webapp"]["resolved"] == "1.10.0"


def test_ring_not_in_conflicts():
    """Verify ring is NOT a conflict since legacy-bridge cannot resolve it."""
    data = load_report()
    ring_conflicts = [c for c in data["conflicts"] if c["package"] == "ring"]
    assert len(ring_conflicts) == 0


def test_serde_not_in_conflicts():
    """Verify serde is NOT a conflict — all constraints have a common version."""
    data = load_report()
    serde_conflicts = [c for c in data["conflicts"] if c["package"] == "serde"]
    assert len(serde_conflicts) == 0


# ── Statistics ──────────────────────────────────────────────────────────


def test_statistics_conflict_count():
    """Verify statistics.conflict_count equals 5."""
    data = load_report()
    assert data["statistics"]["conflict_count"] == 5


def test_statistics_most_depended_package():
    """Verify most_depended_package is 'log' (alphabetically first among ties at 6)."""
    data = load_report()
    assert data["statistics"]["most_depended_package"] == "log"


def test_statistics_most_depended_count():
    """Verify most_depended_count is 6."""
    data = load_report()
    assert data["statistics"]["most_depended_count"] == 6


def test_statistics_projects_fully_resolved():
    """Verify 6 projects are fully resolved."""
    data = load_report()
    assert data["statistics"]["projects_fully_resolved"] == 6


def test_statistics_projects_with_unresolved():
    """Verify 1 project has unresolved dependencies."""
    data = load_report()
    assert data["statistics"]["projects_with_unresolved"] == 1


def test_statistics_total_unique_dependencies():
    """Verify there are 20 unique dependency packages across all projects."""
    data = load_report()
    assert data["statistics"]["total_unique_dependencies"] == 20


# ── Resolution key sorting ──────────────────────────────────────────────


def test_resolutions_sorted_by_project():
    """Verify resolutions are sorted by project name."""
    data = load_report()
    project_names = list(data["resolutions"].keys())
    assert project_names == sorted(project_names)


def test_resolved_deps_sorted():
    """Verify each project's resolved dependencies are sorted by name."""
    data = load_report()
    for proj_name, resolution in data["resolutions"].items():
        dep_names = list(resolution["resolved"].keys())
        assert dep_names == sorted(dep_names), f"{proj_name} deps unsorted"


def test_conflict_projects_sorted():
    """Verify project names within each conflict entry are sorted."""
    data = load_report()
    for conflict in data["conflicts"]:
        proj_names = list(conflict["projects"].keys())
        assert proj_names == sorted(proj_names), (
            f"Unsorted projects in {conflict['package']} conflict"
        )


# ── Cross-validation ────────────────────────────────────────────────────


def test_all_seven_projects_present():
    """Verify all 7 projects appear in resolutions."""
    data = load_report()
    expected = {
        "api-client", "auth-service", "cli-tool", "data-layer",
        "legacy-bridge", "macro-utils", "webapp",
    }
    assert set(data["resolutions"].keys()) == expected


def test_resolution_has_resolved_and_unresolved():
    """Verify every resolution entry has both resolved and unresolved keys."""
    data = load_report()
    for proj_name, entry in data["resolutions"].items():
        assert "resolved" in entry, f"{proj_name} missing 'resolved'"
        assert "unresolved" in entry, f"{proj_name} missing 'unresolved'"


def test_conflict_entry_structure():
    """Verify every conflict entry has package and projects keys."""
    data = load_report()
    for conflict in data["conflicts"]:
        assert "package" in conflict
        assert "projects" in conflict
        for proj_name, info in conflict["projects"].items():
            assert "constraint" in info
            assert "resolved" in info


def test_log_conflict_includes_all_users():
    """Verify the log conflict includes all 6 projects that depend on log."""
    data = load_report()
    log_conflicts = [c for c in data["conflicts"] if c["package"] == "log"]
    assert len(log_conflicts) == 1
    projects = log_conflicts[0]["projects"]
    expected = {
        "api-client", "auth-service", "cli-tool",
        "data-layer", "legacy-bridge", "webapp",
    }
    assert set(projects.keys()) == expected


def test_tokio_conflict_includes_all_users():
    """Verify the tokio conflict includes all 6 projects that depend on tokio."""
    data = load_report()
    tokio_conflicts = [c for c in data["conflicts"] if c["package"] == "tokio"]
    projects = tokio_conflicts[0]["projects"]
    expected = {
        "api-client", "auth-service", "cli-tool",
        "data-layer", "legacy-bridge", "webapp",
    }
    assert set(projects.keys()) == expected
