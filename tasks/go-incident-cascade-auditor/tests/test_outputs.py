"""Behavioral tests for go-incident-cascade-auditor.

The tests validate deterministic JSON outputs at /app/report and enforce
the Go-only implementation contract by re-running the produced binary.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SIGNALS_DIR = Path(os.environ.get("GIA_SIGNALS_DIR", "/app/signals"))
REPORT_DIR = Path(os.environ.get("GIA_REPORT_DIR", "/app/report"))
SRC_DIR = Path(os.environ.get("GIA_SRC_DIR", "/app/src"))
BIN_DIR = Path(os.environ.get("GIA_BIN_DIR", "/app/bin"))
AUDITOR_BIN = BIN_DIR / "auditor"

REQUIRED_OUTPUT_FILES = [
    "anomaly_report.json",
    "blast_radius.json",
    "paging_plan.json",
    "node_health.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "ac30a87a561b3f447b1aa7bc22b11889b68601b4abd668c2672f1992194e8796",
    "incidents/incident_log.json": "49cf0f670039d9a3af2729846d7e78a925275d9d5e577ebed88dd4aac31c0336",
    "metrics/api-gateway.json": "1a7b126569f5421f92b52b1313d2cf7a253edd7b3d593bc3b0c40d7e2175a32c",
    "metrics/auth-service.json": "8698e820d2efde7516787944dd110ac07103ac247f9d5f03feede6857dcb01b2",
    "metrics/checkout-ui.json": "89025fbfd444d508b5bf1a5bb878218b4d69a6c26f08ab0faf4e3b38ba0f2f2d",
    "metrics/indexer.json": "0303eaf9ce1f968d7933c9872709476077656bef10436af7a4a10dda8e5e8495",
    "metrics/ledger-db.json": "4ec46f6b2d4d90cfa6dacca1e971822ae519c086bb8d29103d916a0f1e9fcaba",
    "metrics/payment-core.json": "85ed423fbaf4974db1557fdffaa171b58af962676545c99a949d6974426927a0",
    "metrics/reco-engine.json": "6675a80a041f9dc65566c13005cc337ccc6c7c68fd0175dbddee0c0e93c7751d",
    "metrics/search-api.json": "6d5f456d2a22040d1efc7bd443e32538e23d0d863b3e91f100bf41842f1a15ec",
    "metrics/user-db.json": "c0a8445760ccd2c828d8b71a3de2a13ba80a0368bd3764f537e99fde15e83e28",
    "oncall/rotations.json": "60bf18c7f88eeaae2cbb3363176fdb0191000b4dc758d7b45b29ce4240e5a78d",
    "policy/triage_policy.json": "25c212d9b31010a892d882b50317933ec972eaec5993305ee5a747831c8f49d9",
    "pool_state.json": "e3516d1504cb6c8ffe2de22b3df342fe62ee4e718c1a97081ace6cb0b32dd64a",
    "services/api-gateway.json": "4921be1090bc7119003dd7f913c71aaf2871b3b2235741d1886692ebac714a12",
    "services/auth-service.json": "a7b2a5b0d9b74bc77b830505aab635bd7745325dad76290043aa22a7aaccad0a",
    "services/checkout-ui.json": "18e21b81922a2a8cba30c40aefbc2767db8a809defccb7b985bacf41b3a867cd",
    "services/indexer.json": "883464038e6400795b04415f72513ecf16a3e3eab166c925896a91fdb42a0800",
    "services/ledger-db.json": "986cc6acfddaf9f1ac9867e8765a914101a53587cbae345009fe18e538b9ac3f",
    "services/payment-core.json": "106780c4c64cf94578810685c34b50def99f63cc3a5668354e4584f93192f044",
    "services/reco-engine.json": "542f3852c6f84f6c6c4a4df2c0f59521fb06f13e24c0666d643b37a6f5ac1b78",
    "services/search-api.json": "311f14f239fd0e54484f0ba238dc27e36adf730412b6e90bae9ebe3305653b00",
    "services/user-db.json": "8b09cc3804582446434ee44a3267f9f42a28440295e096e47d1213ac873b0d0c",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "anomaly_report.json": "3d531a4a69b6061d9ad718745732f2df39bf376216ef262e1ed8df9337c5ff0a",
    "blast_radius.json": "1c26c1faf7759255ebef2580f378ed0e6e4b163e8ff1ad6fe377d21c522c6fc1",
    "paging_plan.json": "8c5526a3cda4ca3c016c5d1ef041cd005eb41f65ebabf45e04741d56a4bdd023",
    "node_health.json": "08bf495aa94b677b2c2d4d9bb21bdeb29dc30e8cc903ea67b8860dbbdf5921e8",
    "summary.json": "4a80ec665d731da8898f01e6b3aa37b4f1bd0a762e87f36e06f402e40390f9c4",
}

EXPECTED_FIELD_HASHES = {
    "anomaly_report.services": "b717e0a4c07f3a333dded6d3f9982d1288e203a28c13d01160488edd89f69c5e",
    "blast_radius.roots": "db90b7f74a423b18dc95ccdc280c0804ac3fca0a0e778a5cfbd7ff0bdad68134",
    "paging_plan.pages": "1112081bb3a7f8017cd041b19c2601cb8ea395f70835a67fa7281feceb764e98",
    "node_health.nodes": "6d64d1009a8d596fb146e3b6053138b68c8e7c0e283179ef73f97c10dbe006ec",
    "summary": "4a80ec665d731da8898f01e6b3aa37b4f1bd0a762e87f36e06f402e40390f9c4",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(obj) -> str:
    payload = (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    return _sha256_bytes(payload)


@pytest.fixture(scope="module")
def loaded_outputs():
    result = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = REPORT_DIR / name
        assert p.is_file(), f"missing /app/report/{name}"
        text = p.read_text(encoding="utf-8")
        result[name] = {"text": text, "obj": json.loads(text), "bytes": text.encode("utf-8")}
    return result


class TestInputIntegrity:
    """Input fixtures must remain unchanged."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hashes_match(self, rel):
        p = SIGNALS_DIR / rel
        assert p.is_file(), f"missing input fixture: {rel}"
        assert _sha256_bytes(p.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestOutputStructure:
    """Output files must be deterministic and canonical."""

    def test_report_dir_contains_only_expected_files(self):
        actual = sorted(p.name for p in REPORT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_pretty_sorted_and_newline(self, loaded_outputs, name):
        obj = loaded_outputs[name]["obj"]
        expected = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        assert loaded_outputs[name]["bytes"] == expected

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_top_level_canonical_hash(self, loaded_outputs, name):
        assert _canonical_sha(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]


class TestSemanticBehavior:
    """Core semantic expectations from the spec."""

    def test_expected_final_severity_distribution(self, loaded_outputs):
        services = loaded_outputs["anomaly_report.json"]["obj"]["services"]
        counts = collections.Counter(s["final_severity"] for s in services)
        assert counts == {"healthy": 3, "warning": 4, "critical": 2}

    def test_propagation_reasons_present(self, loaded_outputs):
        services = {s["service_id"]: s for s in loaded_outputs["anomaly_report.json"]["obj"]["services"]}
        assert "propagated_from:auth-service" in services["api-gateway"]["reasons"]
        assert "propagated_from:auth-service" in services["checkout-ui"]["reasons"]

    def test_node_status_enums_covered(self, loaded_outputs):
        nodes = {n["node_id"]: n for n in loaded_outputs["node_health.json"]["obj"]["nodes"]}
        assert nodes["node-d"]["status"] == "quarantined"
        assert nodes["node-h"]["status"] == "quarantined_hotspot"
        assert nodes["node-b"]["status"] == "hotspot"

    def test_priority_assignment(self, loaded_outputs):
        pages = loaded_outputs["paging_plan.json"]["obj"]["pages"]
        by_service = {p["service_id"]: p["priority"] for p in pages}
        assert by_service["auth-service"] == "p1"
        assert by_service["reco-engine"] == "p1"
        assert by_service["checkout-ui"] == "p2"
        assert by_service["api-gateway"] == "p3"


class TestImplementationLanguage:
    """Implementation must provide Go source files under /app/src."""

    def test_go_source_contains_package_main(self):
        go_files = sorted(SRC_DIR.rglob("*.go"))
        assert go_files, "at least one Go source file must exist under /app/src"
        has_main = any("package main" in p.read_text(encoding="utf-8", errors="ignore") for p in go_files)
        assert has_main, "Go source under /app/src must include package main"

    def test_no_python_sources_under_src(self):
        py_files = list(SRC_DIR.rglob("*.py"))
        assert not py_files, "implementation source under /app/src must be Go-only"


class TestCompiledBinary:
    """Implementation must compile to /app/bin/auditor and execute to produce reports."""

    def test_auditor_binary_exists(self):
        """The /app/bin/auditor file must exist as a regular file with execute permission."""
        assert AUDITOR_BIN.is_file(), f"{AUDITOR_BIN} must exist as a regular file"
        assert os.access(AUDITOR_BIN, os.X_OK), f"{AUDITOR_BIN} must be executable"

    def test_auditor_binary_is_native_executable(self):
        """The binary must be a native compiled executable, not a wrapper script."""
        head = AUDITOR_BIN.read_bytes()[:4]
        assert head != b"#!/b" and head != b"#!/u" and head != b"#!/p", (
            f"{AUDITOR_BIN} must not be a script (header={head!r})"
        )
        assert head == b"\x7fELF", (
            f"{AUDITOR_BIN} must be an ELF executable produced by a Go compiler (header={head!r})"
        )

    def test_auditor_binary_built_from_go(self):
        """The binary must carry Go build metadata identifying it as a Go-compiled artifact."""
        go_bin = shutil.which("go")
        if go_bin:
            result = subprocess.run(
                [go_bin, "version", "-m", str(AUDITOR_BIN)],
                capture_output=True, text=True, timeout=30, check=False,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            assert result.returncode == 0 and "go" in first_line.lower(), (
                f"`go version -m` did not identify a Go binary "
                f"(rc={result.returncode}, first_line={first_line!r}, stderr={result.stderr[:300]!r})"
            )
        else:
            data = AUDITOR_BIN.read_bytes()
            assert b"go.buildinfo" in data or b"Go build" in data or b"runtime.go" in data, (
                f"{AUDITOR_BIN} does not contain Go build metadata"
            )

    def test_auditor_binary_executes_and_produces_reports(self, tmp_path):
        """Running /app/bin/auditor against an isolated report directory must regenerate all five canonical reports."""
        run_dir = tmp_path / "report_run"
        run_dir.mkdir()
        env = os.environ.copy()
        env["GIA_SIGNALS_DIR"] = str(SIGNALS_DIR)
        env["GIA_REPORT_DIR"] = str(run_dir)
        result = subprocess.run(
            [str(AUDITOR_BIN)],
            env=env, capture_output=True, text=True, timeout=120, check=False,
        )
        assert result.returncode == 0, (
            f"{AUDITOR_BIN} exited with rc={result.returncode}; "
            f"stdout={result.stdout[:500]!r} stderr={result.stderr[:500]!r}"
        )
        for name in REQUIRED_OUTPUT_FILES:
            p = run_dir / name
            assert p.is_file(), f"binary did not produce {name}"
            obj = json.loads(p.read_text(encoding="utf-8"))
            assert _canonical_sha(obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name], (
                f"output {name} produced by the binary does not match the canonical hash"
            )


class TestFieldHashes:
    """Field-level canonical hashes provide targeted mismatch diagnostics."""

    def test_services_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["anomaly_report.json"]["obj"]["services"])
        assert actual == EXPECTED_FIELD_HASHES["anomaly_report.services"]

    def test_roots_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["blast_radius.json"]["obj"]["roots"])
        assert actual == EXPECTED_FIELD_HASHES["blast_radius.roots"]

    def test_pages_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["paging_plan.json"]["obj"]["pages"])
        assert actual == EXPECTED_FIELD_HASHES["paging_plan.pages"]

    def test_nodes_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["node_health.json"]["obj"]["nodes"])
        assert actual == EXPECTED_FIELD_HASHES["node_health.nodes"]

    def test_summary_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["summary.json"]["obj"])
        assert actual == EXPECTED_FIELD_HASHES["summary"]
