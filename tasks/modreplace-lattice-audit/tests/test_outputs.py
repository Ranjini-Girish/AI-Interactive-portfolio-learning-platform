"""Behavioral tests for the modreplace-lattice-audit task.

The tests verify JSON under ``/app/audit/`` against the contract in
``/app/modgraph/SPEC.md``. Inputs are hash-locked; outputs are hash-locked in
canonical compact form. The task requires Go sources under ``/app/src/`` and
a compiled ``/app/bin/lattice-auditor`` binary.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

MODGRAPH_DIR = Path(os.environ.get("MLA_MODGRAPH_DIR", "/app/modgraph"))
AUDIT_DIR = Path(os.environ.get("MLA_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("MLA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("MLA_BIN_PATH", "/app/bin/lattice-auditor"))

REQUIRED_OUTPUT_FILES = [
    "global_replace.json",
    "resolution.json",
    "skew_pairs.json",
    "cycle_report.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "aab0926f981cded7f84f35a0e900e65ee1ede8f7966676730968509ef7d296df",
    "modules/00-gateway.json": "894a0c1a9cbd06007ccafd3d914d907bd82032ded0693939d98114300de3759b",
    "modules/01-common.json": "538ed717154f3e65a0a10b6e4e45ac8496dd4b3e2787d2bd7e4b577f374411fc",
    "modules/02-auth.json": "cd9170246fafd99a0e99aa4ce90526768ba2c4a76672dbd4d11fec355b92b336",
    "modules/03-billing.json": "14929820823971c3d34d1a9201ad5843b7adf668f357abb0d34b692fc60041e0",
    "modules/04-cart.json": "712362a2e310496939636f1a50998315cd93590b435258f2331a1c033b17c60f",
    "modules/05-catalog.json": "5c4df7da8bcdb5525a873e3d33d077364f3f6964e8f4c9b7a42c7bc13ddce88e",
    "modules/06-checkout.json": "cea8b7fd9150a54d46d458bdb7eec5f995b7224fac5e9929ee64e682d67c67e6",
    "modules/07-inventory.json": "a5f870f0815f9fd393c70081fbfbe06f6cc66a7a13613c9542dd44b7dda96c6b",
    "modules/08-ledger.json": "ff463cb76e1874aebf0172e3c07a8ef9c0ac3802779870b5dd16821d46885735",
    "modules/09-notifications.json": "c02e74f051a12b92aafb3ff3fe5072839090f849459bf686a5dee8154e176618",
    "modules/10-orders.json": "b9be6bca929512ac60d06a5483e1522ccf567bf8e7f83204e557c120251570a8",
    "modules/11-payments.json": "6318bf27590a647e2a6703661ed2f0136665911cbd7dc9fc67e9bc4ed20cb3cb",
    "modules/12-search.json": "21834e90692d30f27b63b109e9cf45c9effc372b467716a1e07472adc84f510e",
    "modules/13-shipper.json": "b5999d2913c92eb254963224329a7853157aea5adcd6f953b3f510fd3e2c4f95",
    "modules/14-users.json": "98203d972f5f04493325a1c263bcf10e0bc87d73fa66f5d4c9dc89590d459f68",
    "modules/15-indexer.json": "be61f3efbc9661bd12a0f818dbc83f5f573e0e4a75fb5c8c68dc9c090e068d70",
    "policy/local_strip_prefixes.json": "2cd8495f8607e9bb8201a92daa8a0c6fd4c9d7dd8112f48a468dcdc7957155d8",
    "policy/strip_prefixes.json": "dda6e80f2201bf4aeb86a49855e548b3c8376c77f9d7511cf4fe19e3621cd5f9",
    "pool_state.json": "5496d16e7f2d831ec6f1fc34ab5d7ea4b7d05354e4c2c380f5aaa99ba6de45dd",
    "workspace/scan_order.json": "6ad789736d9a178fc6da96902b0d7172ecf35e627654e744ebda6f8cdd304e16",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "global_replace.json": "506d8a5a417b38db51e0c29f7cd945de25323f758d2ef9ffe56051bbfe1d986d",
    "resolution.json": "416b9edd62aa846dbccb2ae37b6305843f955e06a66621e48da6ed0d899303dc",
    "skew_pairs.json": "e81df5e87aec3b19a29bba7769a445e23fe3f70c9312c12b3ecf70df8be2d5ae",
    "cycle_report.json": "4188d67f87b4e699682c0321a1c6df3f3b973e340b9c8a85bb3c6bd09855ef01",
    "summary.json": "cbd1d47af428086d901895a4e4488981a2f9a0d2c3f72438d5d0997fabf83a51",
}

EXPECTED_FIELD_HASHES = {
    "global_replace.final": "783f15e339d070bb03f42251c576b3c90ddf8d1a716a8ccb680242bed66aa0e9",
    "resolution.by_module": "9bb1b98012a72b0fc55fdd2e6829a7864b3255bb6615e0a2caef9714583cf171",
    "skew_pairs.pairs": "969c93d6c6fe58dc21d3e5c7ae9b79d256d470252a274acd33b5254e1994a8ee",
    "cycle_report.components": "a67ebc9b6c1111bad45d08ef793aa41a77cf9716e645f3408323ad3697624b69",
    "cycle_report.has_cycle": "a17fcf0a2f50e2d495e4f90ce263410edc183add6c62699a2facbccf60410f74",
    "summary.cycle_component_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.expired_replace_drops": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.global_replace_keys": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.global_revoke_drops": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.local_strip_skipped_entries": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.module_manifests_read": "e6c21e8d260fe71882debdb339d2402a2ca7648529bc2303f48649bce0380017",
    "summary.modules_with_used_local": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.skew_distinct_require_paths": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.skew_pair_count": "e6c21e8d260fe71882debdb339d2402a2ca7648529bc2303f48649bce0380017",
    "summary.strip_excluded_entries": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.union_replace_edge_count": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.union_vertex_count": "7ee29791fc17e986b97128845622b077fb45e349fdb80523fac9dba879b4ad60",
    "summary.used_local_true_rows": "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
}

SUMMARY_TOP_KEYS = {
    "cycle_component_count",
    "expired_replace_drops",
    "global_replace_keys",
    "global_revoke_drops",
    "local_strip_skipped_entries",
    "module_manifests_read",
    "modules_with_used_local",
    "skew_distinct_require_paths",
    "skew_pair_count",
    "strip_excluded_entries",
    "union_replace_edge_count",
    "union_vertex_count",
    "used_local_true_rows",
}

RESOLVED_MARKERS = frozenset({"__cycle__", "__self_loop__"})


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    """Load all five audit JSON files once per module."""
    out: dict[str, dict] = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Modgraph fixtures must remain byte-identical."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each file under the modgraph tree must match its pinned SHA-256."""
        path = MODGRAPH_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/modgraph/{rel} was modified (expected {expected}, got {actual})"
        )


class TestOutputStructure:
    """Audit outputs exist, use canonical pretty JSON, and match pinned hashes."""

    def test_audit_directory_exists(self):
        """``/app/audit`` must exist as a directory."""
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Each required filename must exist under ``/app/audit/``."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self):
        """The audit directory must contain exactly the five required files."""
        actual = sorted(p.name for p in AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/audit must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name):
        """Each file ends with exactly one ``\\n``."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name):
        """On-disk bytes must match ``json.dumps(..., indent=2, sort_keys=True) + '\\n'``."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        assert actual_bytes == expected_bytes, (
            f"/app/audit/{name} bytes do not match canonical pretty JSON encoding"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level_on_disk(self, name):
        """Every JSON object must emit keys in sorted order at all depths."""
        path = AUDIT_DIR / name
        ordered = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=collections.OrderedDict,
        )
        violations: list[str] = []

        def walk(node, path_str: str) -> None:
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(
                        f"{path_str}: keys not sorted; got {keys}, expected {sorted(keys)}"
                    )
                for key, value in node.items():
                    walk(value, f"{path_str}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{path_str}[{index}]")

        walk(ordered, name)
        assert not violations, "key sort violations:\n  - " + "\n  - ".join(violations)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name):
        """Compact canonical SHA-256 of each root object must match the pin."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, f"/app/audit/{name} canonical hash mismatch"


class TestFieldHashes:
    """Pinned sub-object hashes for anti-cheat."""

    @pytest.mark.parametrize("field_key", list(EXPECTED_FIELD_HASHES.keys()))
    def test_field_canonical_hash(self, loaded_outputs, field_key):
        """Each ``file.key`` fragment must match its pinned canonical hash."""
        stem, _, sub = field_key.partition(".")
        obj = loaded_outputs[f"{stem}.json"]["obj"]
        fragment = obj[sub]
        actual = _canonical_sha256(fragment)
        expected = EXPECTED_FIELD_HASHES[field_key]
        assert actual == expected, f"field hash mismatch for {field_key}"


class TestEnumMarkers:
    """Resolution markers stay within the documented sentinel set."""

    def test_resolution_markers_are_known(self, loaded_outputs):
        """Any ``resolved`` value starting with ``__`` must be a known marker."""
        by_mod = loaded_outputs["resolution.json"]["obj"]["by_module"]
        for _mod, rows in by_mod.items():
            for row in rows:
                val = row["resolved"]
                if isinstance(val, str) and val.startswith("__"):
                    assert val in RESOLVED_MARKERS, f"unknown marker {val!r}"

    def test_skew_resolved_strings_are_consistent(self, loaded_outputs):
        """Skew rows only reference module ids present in ``resolution.json``."""
        mods = set(loaded_outputs["resolution.json"]["obj"]["by_module"].keys())
        for pair in loaded_outputs["skew_pairs.json"]["obj"]["pairs"]:
            assert pair["module_a"] in mods
            assert pair["module_b"] in mods


class TestFixtureSpotChecks:
    """Positively exercises fixture-driven branches named in SPEC."""

    def test_global_won_manifest_for_lib_is_indexer(self, loaded_outputs):
        """The shared ``example.com/lib`` replace is attributed to the indexer manifest."""
        fin = loaded_outputs["global_replace.json"]["obj"]["final"]["example.com/lib"]
        assert fin["won_manifest"] == "modules/15-indexer.json"

    def test_known_auth_local_overlay_on_lib(self, loaded_outputs):
        """Auth resolves ``example.com/lib`` through its local overlay."""
        rows = {r["require"]: r for r in loaded_outputs["resolution.json"]["obj"]["by_module"]["auth"]}
        row = rows["example.com/lib"]
        assert row["resolved"] == "example.com/lib-v2"
        assert row["used_local"] is True

    def test_known_cart_cycle_resolution(self, loaded_outputs):
        """Cart hits the two-node replace cycle and surfaces ``__cycle__``."""
        rows = loaded_outputs["resolution.json"]["obj"]["by_module"]["cart"]
        assert any(r["require"] == "example.com/cycle-a" and r["resolved"] == "__cycle__" for r in rows)

    def test_known_cycle_component_present(self, loaded_outputs):
        """The union replace graph exposes the expected two-node SCC."""
        comps = loaded_outputs["cycle_report.json"]["obj"]["components"]
        assert ["example.com/cycle-a", "example.com/cycle-b"] in comps

    def test_known_strip_skew_pair_present(self, loaded_outputs):
        """Billing vs inventory skew captures strip-hit divergence on legacy requires."""
        pairs = loaded_outputs["skew_pairs.json"]["obj"]["pairs"]
        hit = next(
            p
            for p in pairs
            if p["module_a"] == "billing"
            and p["module_b"] == "inventory"
            and p["require_path"] == "github.com/legacy/extra"
        )
        assert hit["resolved_a"] == "example.com/extra-new"
        assert hit["resolved_b"] == "github.com/legacy/extra"

    def test_known_billing_payments_retire_skew(self, loaded_outputs):
        """Revoked shared-map rows plus divergent locals surface skew on the same require path."""
        pairs = loaded_outputs["skew_pairs.json"]["obj"]["pairs"]
        hit = next(
            p
            for p in pairs
            if p["module_a"] == "billing"
            and p["module_b"] == "payments"
            and p["require_path"] == "example.com/retire-pkg/widget"
        )
        assert hit["resolved_a"] == "example.com/widget-billing"
        assert hit["resolved_b"] == "example.com/retire-pkg/widget"

    def test_summary_pool_pass_counters_positive(self, loaded_outputs):
        """Pool-driven revoke drops and tail local-strip suppressions must be reflected in totals."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["global_revoke_drops"] == 1
        assert s["local_strip_skipped_entries"] == 1


class TestSummaryShape:
    """``summary.json`` top-level keys are exactly the documented counter set."""

    def test_summary_top_level_keys(self, loaded_outputs):
        """Summary must expose exactly the integer counters named in SPEC."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj.keys()) == SUMMARY_TOP_KEYS
        for k, v in obj.items():
            assert isinstance(v, int) and v >= 0, f"summary.{k} must be a non-negative int"


class TestSummaryInvariants:
    """Cross-field relationships implied by SPEC definitions."""

    def test_skew_diversity_not_greater_than_pair_rows(self, loaded_outputs):
        """Distinct skewed require paths cannot exceed skew pair rows."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["skew_distinct_require_paths"] <= s["skew_pair_count"]

    def test_used_local_rows_covers_modules_flag(self, loaded_outputs):
        """Each module counted for local overlay contributes at least one row."""
        s = loaded_outputs["summary.json"]["obj"]
        assert s["used_local_true_rows"] >= s["modules_with_used_local"]

    def test_union_counts_use_deduped_edges(self, loaded_outputs):
        """Vertices and deduped edges stay within a loose complete-graph bound."""
        s = loaded_outputs["summary.json"]["obj"]
        v = s["union_vertex_count"]
        e = s["union_replace_edge_count"]
        assert v >= 0 and e >= 0
        assert e <= v * (v - 1)


class TestImplementationLanguage:
    """Go sources and binary must reproduce ``/app/audit`` from ``/app/modgraph``."""

    def test_go_source_contains_package_main(self):
        """``/app/src`` must contain at least one Go source file declaring ``package main``."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files under {SRC_DIR}"
        has_main_pkg = False
        has_main_func = False
        for src_path in go_files:
            text = src_path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main_pkg = True
            if re.search(r"^\s*func\s+main\s*\(\s*\)\s*\{", text, re.MULTILINE):
                has_main_func = True
        assert has_main_pkg, f"no file under {SRC_DIR} declares package main"
        assert has_main_func, f"no file under {SRC_DIR} declares func main()"

    def test_binary_present(self):
        """``/app/bin/lattice-auditor`` must exist and be executable."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_is_go_toolchain_build(self):
        """``/app/bin/lattice-auditor`` must carry embedded Go build info from the Go toolchain."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        go_exe = shutil.which("go")
        assert go_exe is not None, "go toolchain must be available on PATH for the verifier"
        result = subprocess.run(
            [go_exe, "version", "-m", str(BIN_PATH)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"`go version -m {BIN_PATH}` failed (rc={result.returncode}); "
            f"the artefact is not a recognisable Go binary.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        assert re.search(r"\bgo1\.\d+", first_line), (
            f"`go version -m` did not report a go1.x toolchain for {BIN_PATH}; "
            f"first line was: {first_line!r}"
        )
        assert "\tmod\t" in result.stdout or "\tpath\t" in result.stdout, (
            f"`go version -m` did not report embedded build info for {BIN_PATH}; "
            f"full output:\n{result.stdout}"
        )

    def test_binary_reproduces_audit(self):
        """Fresh run with ``/app/audit`` unavailable must recreate identical bytes."""
        saved = {name: (AUDIT_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES}
        backup = AUDIT_DIR.parent / (AUDIT_DIR.name + ".anti_cheat_backup")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(AUDIT_DIR), str(backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["MLA_MODGRAPH_DIR"] = str(MODGRAPH_DIR)
                env["MLA_AUDIT_DIR"] = td
                result = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                assert result.returncode == 0, (
                    f"binary exit code {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh_path = Path(td) / name
                    assert fresh_path.is_file(), (
                        f"binary did not write {name} to a fresh audit dir while /app/audit was moved aside"
                    )
                    fresh = fresh_path.read_bytes()
                    assert fresh == saved[name], (
                        f"/app/audit/{name} was not reproduced by a fresh binary run against /app/modgraph/"
                    )
                    fresh_obj = json.loads(fresh.decode("utf-8"))
                    assert _canonical_sha256(fresh_obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name], (
                        f"binary re-execution output for {name} disagrees with the canonical reference hash"
                    )
        finally:
            if AUDIT_DIR.exists():
                shutil.rmtree(AUDIT_DIR)
            shutil.move(str(backup), str(AUDIT_DIR))
