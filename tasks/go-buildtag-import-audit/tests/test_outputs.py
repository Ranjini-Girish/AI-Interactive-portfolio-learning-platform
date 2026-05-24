"""Behavioral tests for go-buildtag-import-audit.

These tests verify the five JSON files under ``/app/outcome/`` against the
contract in ``instruction.md`` and the normative rules in
``/app/buildtag/SPEC.md``. Hash-locking pins every fixture under
``/app/buildtag/`` and the canonical bytes of each output. The task requires
a Go implementation: ``TestImplementationLanguage`` rebuilds the binary
into a fresh output directory to ensure the JSON is produced by the program,
not copied from a static template.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

BUILDTAG_DIR = Path(os.environ.get("BTA_BUILDTAG_DIR", "/app/buildtag"))
OUTCOME_DIR = Path(os.environ.get("BTA_OUT_DIR", "/app/outcome"))
SRC_DIR = Path(os.environ.get("BTA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("BTA_BIN_PATH", "/app/bin/btag-audit"))

REQUIRED_OUTPUT_FILES = [
    "active_sources.json",
    "entry_closure.json",
    "package_status.json",
    "resolved_import_edges.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "97c0b7acd61895be87c0e55c304a1bd3cedecd86d0511d32089b477028985fb0",
    "context.json": "dd23745619c489e72365b0c8be04a29d10cea48285e2bd24e1508ffffe36d0e9",
    "incidents.json": "295727e4269b6cf29918eab462bd698156041f9a24b3913066b70f99bbaa4d6d",
    "packages/calpha.json": "de5ca5a6889615f97e6d9dca8ec6276e3d6e35767a003e60b7cbac46da858b04",
    "packages/cbeta.json": "bf0a48e00ece777c9208a22a732fcbf8eaca556081fa58b204fcc70dd8bd4a84",
    "packages/cgouser.json": "639bd64da98f1d315397e4c2a1691b41fc2d84a95d282ed78240b3b837948d1c",
    "packages/chain_a.json": "2ea2fec137b8837204460c3b1d00e83bd7e7dbaf44ab7d015f20ab14d6aec1ab",
    "packages/chain_b.json": "59e9bcbda261b90ccacd59dec922265c3e966040db5a6716e354a586da8e1911",
    "packages/chain_c.json": "e94edf7d5d30d2c5384ec6f7c6610f60ca5c2daf935815ece7dd26901c07d8cd",
    "packages/devnull.json": "577bbba21bedacb65c4bdcb013fac5b0dfe61ca563b46b0b418012c85fe7e115",
    "packages/entpkg.json": "f82210f640189d976781e3fa7c69aaf5e380d9fb13bccf7e61bfe4b8c670a119",
    "packages/gate.json": "d5d7a8fd21e13f1a2199363fd3abf793295f3ef088a5b4b2bf6f515f243a0243",
    "packages/ignpkg.json": "edf527b2c995e90cf097d4b903aa1cbcb1463a778b15b694d4f893844575af3c",
    "packages/indexer.json": "530dae06c8488f078b4d9f6d6cae1136c784998c9800a31e4db8ac6de6c7c918",
    "packages/lib.json": "74e0dcaf7df799bf1fc5b1623a12285c27c69e5b33076e235bfb014c0d7e3eac",
    "packages/looper.json": "5fe093be1f4afcfa7502619b3f10ab3df11b6cd40de34142e78dbb1f6fb9bb7e",
    "packages/rawbad.json": "7dbe75147319d8c6f7513246b00aa354a6a12556ed489150741369c9cdd0ff58",
    "packages/solo.json": "030e5eee52f29ae809804ba62d29fd183fcc56d83fc4d4aa01c764953d32babc",
    "packages/waived.json": "c80ce3fc9dedbf8d1d65d0f54bc6d3326d5b3a9195bfab7e3ebb3c53a130de9d",
    "policy.json": "599962d6156623e0bd6b2f8dbb1e8987e2c75948024047910b91f34ab0ece85f",
    "pool_state.json": "1cc9362e5214e6bcb24f3a45c2bb66dda9adc80c68e81110c0268c491958ac47",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "active_sources.json": "eaa1d3af2829c6fbdbad922835a62ff9b8e85b89c4b1699552a95214efc43eff",
    "entry_closure.json": "c0d109e39d284b243ffbac70c2579b9a5dfed2ad5d9af1de11da52a11936e891",
    "package_status.json": "101efd38484c4b1a6847b7a290f4fd7ffda3fa48b9824433c0b92c1a62db7981",
    "resolved_import_edges.json": "4f6306783574e71c92179be2ac0b711f062596cd1a3a42352d2add34c17e9049",
    "summary.json": "d2d247d5fc5420f87b49ae16e3f295cba936523b58a858add37e0f58c263787d",
}

EXPECTED_FIELD_HASHES = {
    "active_sources.rows": "381911ed0cf4664b8d0eb6c2a5dfe9e0a55da0839d83ea2665c25efca9e5975b",
    "resolved_import_edges.edges": "4dda7bfee1767509a176781c9e5202ac7c3bc3c5cc732354b04b8e7a9fb6b811",
    "package_status.packages": "f9732d10191e5b51cb5995d7f4a655a006390c8518952ecce6b23711f087e3c2",
    "entry_closure.entries": "012c75ebe419fc4cbba821bce1a081aeca036625f33092dd90a1cec75f20a8fc",
    "summary.active_files_total": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "summary.active_packages_total": "8527a891e224136950ff32ca212b45bc93f69fbb801c3b1ebedac52775f99e61",
    "summary.edges_resolved_total": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.entries_excluded_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.forbidden_edges_raw_total": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.forbidden_edges_waived_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.incidents_applied_total": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.packages_active_ok_total": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.packages_active_violation_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.packages_excluded_total": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.packages_import_cycle_total": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.packages_total": "b17ef6d19c7a5b1ee83b907c595526dcb1eb06db8227d650d5dda0a9f4ce8cd9",
}

PACKAGE_STATUS_VALUES = {
    "active_ok",
    "active_violation",
    "excluded",
    "import_cycle",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_field_bytes(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = OUTCOME_DIR / name
        assert p.is_file(), f"missing required output file: /app/outcome/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/outcome/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Pinned SHA-256 for every fixture under /app/buildtag/."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each input file's SHA-256 must equal the pinned hash."""
        path = BUILDTAG_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/buildtag/{rel} was modified "
            f"(sha256 expected {expected}, got {actual})"
        )


class TestOutputCanonicalHashes:
    """Full-file SHA-256 for each emitted JSON document."""

    @pytest.mark.parametrize("name", list(EXPECTED_OUTPUT_CANONICAL_HASHES.keys()))
    def test_output_file_sha256(self, loaded_outputs, name):
        """Each output file must match the pinned canonical SHA-256."""
        actual = _sha256_bytes(loaded_outputs[name]["bytes"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, (
            f"/app/outcome/{name} sha256 mismatch (expected {expected}, got {actual})"
        )


class TestFieldHashes:
    """Per-field canonical subtree hashes."""

    def test_active_sources_rows_field(self, loaded_outputs):
        """The rows array must match its pinned canonical hash."""
        rows = loaded_outputs["active_sources.json"]["obj"]["rows"]
        key = "active_sources.rows"
        actual = _sha256_bytes(_canonical_field_bytes(rows))
        assert actual == EXPECTED_FIELD_HASHES[key]

    def test_resolved_edges_field(self, loaded_outputs):
        """The edges array must match its pinned canonical hash."""
        edges = loaded_outputs["resolved_import_edges.json"]["obj"]["edges"]
        key = "resolved_import_edges.edges"
        actual = _sha256_bytes(_canonical_field_bytes(edges))
        assert actual == EXPECTED_FIELD_HASHES[key]

    def test_package_status_field(self, loaded_outputs):
        """The packages array must match its pinned canonical hash."""
        pkgs = loaded_outputs["package_status.json"]["obj"]["packages"]
        key = "package_status.packages"
        actual = _sha256_bytes(_canonical_field_bytes(pkgs))
        assert actual == EXPECTED_FIELD_HASHES[key]

    def test_entry_closure_field(self, loaded_outputs):
        """The entries array must match its pinned canonical hash."""
        entries = loaded_outputs["entry_closure.json"]["obj"]["entries"]
        key = "entry_closure.entries"
        actual = _sha256_bytes(_canonical_field_bytes(entries))
        assert actual == EXPECTED_FIELD_HASHES[key]

    @pytest.mark.parametrize(
        "field",
        [k[len("summary.") :] for k in EXPECTED_FIELD_HASHES if k.startswith("summary.")],
    )
    def test_summary_scalar_fields(self, loaded_outputs, field):
        """Each integer field in summary.json must match its pinned hash."""
        summ = loaded_outputs["summary.json"]["obj"]
        key = f"summary.{field}"
        actual = _sha256_bytes(_canonical_field_bytes(summ[field]))
        assert actual == EXPECTED_FIELD_HASHES[key], f"field {field} hash mismatch"


class TestSummaryAlgebra:
    """Cross-field consistency rules from SPEC.md."""

    def test_active_package_balance(self, loaded_outputs):
        """active_packages_total equals packages_total minus packages_excluded_total."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["active_packages_total"] == s["packages_total"] - s["packages_excluded_total"]

    def test_status_partition(self, loaded_outputs):
        """Status counters partition active packages."""
        s = loaded_outputs["summary.json"]["obj"]
        active = s["active_packages_total"]
        parts = (
            s["packages_active_ok_total"]
            + s["packages_active_violation_total"]
            + s["packages_import_cycle_total"]
        )
        assert parts == active

    def test_forbidden_waived_le_raw(self, loaded_outputs):
        """Waived forbidden edges cannot exceed raw forbidden edges."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["forbidden_edges_waived_total"] <= s["forbidden_edges_raw_total"]


class TestPackageStatuses:
    """Enum coverage for package_status.status."""

    @pytest.mark.parametrize("status", sorted(PACKAGE_STATUS_VALUES))
    def test_status_value_present_in_output(self, loaded_outputs, status):
        """Each documented status literal appears on at least one package row."""
        pkgs = loaded_outputs["package_status.json"]["obj"]["packages"]
        found = {p["status"] for p in pkgs}
        assert status in found, f"status {status!r} missing from fixture-derived output"


class TestSemanticSpotChecks:
    """Dataset-specific expectations."""

    def test_rawbad_marked_active_violation(self, loaded_outputs):
        """The rawbad package imports a non-waived forbidden path."""
        pkgs = {p["package_key"]: p["status"] for p in loaded_outputs["package_status.json"]["obj"]["packages"]}
        assert pkgs["rawbad"] == "active_violation"

    def test_waived_package_active_ok(self, loaded_outputs):
        """The waived package imports a forbidden path covered by waiver."""
        pkgs = {p["package_key"]: p["status"] for p in loaded_outputs["package_status.json"]["obj"]["packages"]}
        assert pkgs["waived"] == "active_ok"

    def test_cycle_components_marked(self, loaded_outputs):
        """Mutual-import pair and self-loop packages are import_cycle."""
        pkgs = {p["package_key"]: p["status"] for p in loaded_outputs["package_status.json"]["obj"]["packages"]}
        for k in ("calpha", "cbeta", "looper"):
            assert pkgs[k] == "import_cycle", k

    def test_unknown_entry_marked_excluded(self, loaded_outputs):
        """Nonexistent entry path yields excluded_entry true."""
        entries = loaded_outputs["entry_closure.json"]["obj"]["entries"]
        row = next(e for e in entries if e["entry_path"] == "github.com/acme/nonexistent")
        assert row["excluded_entry"] is True
        assert row["reachable_package_keys"] == []

    def test_gateway_reachability_includes_transitive(self, loaded_outputs):
        """Gateway entry reaches indexer and lib."""
        entries = loaded_outputs["entry_closure.json"]["obj"]["entries"]
        row = next(e for e in entries if e["entry_path"] == "github.com/acme/gateway")
        reach = set(row["reachable_package_keys"])
        assert row["excluded_entry"] is False
        assert {"gate", "indexer", "lib"}.issubset(reach)


class TestImplementationLanguage:
    """Go source and binary must reproduce /app/outcome/."""

    def test_go_source_present(self):
        """``/app/src/`` must contain Go sources declaring package main."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist and contain Go source"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files found under {SRC_DIR}"
        has_main = False
        for gf in go_files:
            text = gf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main = True
                break
        assert has_main, f"no Go file under {SRC_DIR} declares 'package main'"

    def test_binary_present(self):
        """``/app/bin/btag-audit`` must exist and be executable."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist (compiled auditor binary)"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_reproduces_outcome(self):
        """Fresh run of the binary against /app/buildtag/ must match on-disk outputs."""
        saved_bytes = {name: (OUTCOME_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES}
        backup = OUTCOME_DIR.parent / (OUTCOME_DIR.name + ".anti_cheat_backup")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(OUTCOME_DIR), str(backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["BTA_BUILDTAG_DIR"] = str(BUILDTAG_DIR)
                env["BTA_OUT_DIR"] = td
                result = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                assert result.returncode == 0, (
                    f"binary exit code {result.returncode}\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh_path = Path(td) / name
                    assert fresh_path.is_file(), f"binary did not write {name} to fresh output dir"
                    fresh = fresh_path.read_bytes()
                    assert fresh == saved_bytes[name], (
                        f"/app/outcome/{name} was not reproduced by {BIN_PATH} "
                        f"when /app/outcome/ was moved aside"
                    )
        finally:
            shutil.move(str(backup), str(OUTCOME_DIR))
