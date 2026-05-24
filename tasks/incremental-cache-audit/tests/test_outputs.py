import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(os.environ.get("APP_ROOT", "/app"))
BINARY = ROOT / "build" / "incremental-cache-audit"
REPORT = ROOT / "output" / "cache_audit.json"

EXPECTED_DIRTY = {
    "api",
    "cli",
    "codegen",
    "core-model",
    "gateway",
    "legacy-adapter",
    "macro-derive",
    "parser",
    "storage",
    "telemetry",
    "util",
}


def run_analyzer(app_root: Path) -> dict:
    binary = app_root / "build" / "incremental-cache-audit"
    if not binary.exists():
        binary = BINARY
    assert binary.exists(), "expected compiled Rust binary at /app/build/incremental-cache-audit"
    env = os.environ.copy()
    env["APP_ROOT"] = str(app_root)
    result = subprocess.run(
        [str(binary)],
        cwd=str(app_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    report_path = app_root / "output" / "cache_audit.json"
    assert report_path.exists(), "analyzer did not write output/cache_audit.json"
    return json.loads(report_path.read_text())


@pytest.fixture(scope="session")
def report():
    return run_analyzer(ROOT)


def dirty_by_name(report):
    return {entry["name"]: entry for entry in report["dirty_crates"]}


def test_report_shape_and_schema(report):
    assert report["schema_version"] == 1
    assert set(report) == {
        "schema_version",
        "summary",
        "dirty_crates",
        "clean_crates",
        "build_plan",
        "findings",
        "warnings",
    }
    assert isinstance(report["dirty_crates"], list)
    assert isinstance(report["findings"], list)
    assert report["warnings"] == []


def test_summary_counts_and_test_dirty(report):
    assert report["summary"] == {
        "total_crates": 13,
        "production_dirty_count": 11,
        "clean_count": 2,
        "test_dirty_crates": ["integration-tests"],
    }


def test_dirty_and_clean_crate_sets_are_exact(report):
    assert [entry["name"] for entry in report["dirty_crates"]] == sorted(EXPECTED_DIRTY)
    assert report["clean_crates"] == ["integration-tests", "runtime"]


def test_direct_roots_and_changed_symbols(report):
    dirty = dirty_by_name(report)
    assert dirty["core-model"]["direct"] is True
    assert dirty["core-model"]["reasons"] == ["API_CHANGED"]
    assert dirty["core-model"]["changed_symbols"] == ["SchemaVersion"]

    assert dirty["macro-derive"]["direct"] is True
    assert dirty["macro-derive"]["reasons"] == ["MACRO_EXPANSION_CHANGED"]
    assert dirty["macro-derive"]["changed_symbols"] == ["derive_builder"]

    assert dirty["codegen"]["direct"] is True
    assert dirty["codegen"]["reasons"] == [
        "BUILD_DEP_IMPL_CHANGED",
        "BUILD_SCRIPT_CHANGED",
        "PROC_MACRO_DEP_CHANGED",
    ]
    assert dirty["codegen"]["changed_symbols"] == ["OUT_DIR"]

    assert dirty["util"]["direct"] is True
    assert dirty["util"]["reasons"] == ["IMPL_CHANGED"]
    assert dirty["util"]["changed_symbols"] == ["normalize_path"]

    assert dirty["telemetry"]["direct"] is True
    assert dirty["telemetry"]["reasons"] == ["IMPL_CHANGED"]
    assert dirty["telemetry"]["changed_symbols"] == ["span_export"]


def test_transitive_reasons_do_not_cross_dev_edges(report):
    dirty = dirty_by_name(report)
    assert dirty["api"]["reasons"] == ["API_DEP_CHANGED", "PROC_MACRO_DEP_CHANGED"]
    assert dirty["cli"]["reasons"] == [
        "API_DEP_CHANGED",
        "BUILD_SCRIPT_DEP_CHANGED",
        "PROC_MACRO_DEP_CHANGED",
    ]
    assert dirty["gateway"]["reasons"] == ["API_DEP_CHANGED", "PROC_MACRO_DEP_CHANGED"]
    assert dirty["parser"]["reasons"] == ["PROC_MACRO_DEP_CHANGED"]
    assert dirty["storage"]["reasons"] == ["API_DEP_CHANGED"]
    assert "integration-tests" not in dirty


def test_build_plan_batches_respect_dirty_dependencies(report):
    assert report["build_plan"]["batches"] == [
        ["macro-derive", "util"],
        ["core-model", "parser", "telemetry"],
        ["codegen", "storage"],
        ["api"],
        ["cli", "gateway", "legacy-adapter"],
    ]


def test_critical_path_uses_dirty_dependency_weights(report):
    assert report["build_plan"]["critical_path_ms"] == 1670
    assert report["build_plan"]["critical_path"] == [
        "util",
        "core-model",
        "storage",
        "api",
        "gateway",
    ]


def test_findings_cover_duplicate_macro_build_and_dev_traps(report):
    triples = {(f["crate"], f["code"], f["detail"]) for f in report["findings"]}
    assert (
        "workspace",
        "duplicate_change",
        "1 duplicate change line ignored",
    ) in triples
    assert (
        "macro-derive",
        "proc_macro_fanout",
        "macro-derive invalidates 6 downstream production crates",
    ) in triples
    assert (
        "codegen",
        "build_script_blast_radius",
        "codegen build script invalidates 1 downstream production crates",
    ) in triples
    assert (
        "telemetry",
        "private_impl_change_contained",
        "telemetry implementation change stayed out of reverse normal/dev edges",
    ) in triples
    assert (
        "integration-tests",
        "dev_dependency_not_production",
        "integration-tests depends on dirty api through a dev edge only",
    ) in triples
    assert (
        "integration-tests",
        "dev_dependency_not_production",
        "integration-tests depends on dirty cli through a dev edge only",
    ) in triples


def test_findings_are_sorted(report):
    keys = [(f["crate"], f["code"], f["detail"]) for f in report["findings"]]
    assert keys == sorted(keys)


def test_dynamic_workspace_change_prevents_hardcoded_report(tmp_path):
    app = tmp_path / "app"
    shutil.copytree(ROOT / "workspace", app / "workspace")
    (app / "output").mkdir(parents=True)
    (app / "build").mkdir()

    extra = app / "workspace" / "crates" / "bench-runner.crate"
    extra.write_text(
        "\n".join(
            [
                "name=bench-runner",
                "kind=bin",
                "build_ms=75",
                "public=crates/bench-runner/src/main.rs",
                "private=",
                "build=",
                "tests=",
                "features=bench:public",
                "unsafe=0",
                "deps=gateway:normal:public",
                "",
            ]
        )
    )
    (app / "workspace" / "changes.txt").write_text(
        "crates/runtime/src/lib.rs|api|Executor\n"
    )

    dynamic = run_analyzer(app)
    assert dynamic["summary"] == {
        "total_crates": 14,
        "production_dirty_count": 4,
        "clean_count": 10,
        "test_dirty_crates": [],
    }
    assert [entry["name"] for entry in dynamic["dirty_crates"]] == [
        "bench-runner",
        "gateway",
        "runtime",
        "telemetry",
    ]
    assert dynamic["build_plan"]["batches"] == [
        ["runtime"],
        ["telemetry"],
        ["gateway"],
        ["bench-runner"],
    ]
    assert dynamic["build_plan"]["critical_path_ms"] == 905
    assert dynamic["build_plan"]["critical_path"] == [
        "runtime",
        "telemetry",
        "gateway",
        "bench-runner",
    ]
