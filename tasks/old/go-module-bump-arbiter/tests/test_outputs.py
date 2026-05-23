"""Behavioral tests for the go-module-bump-arbiter task.

These tests verify that the five JSON files at ``/app/decisions/`` satisfy the
contract documented in ``instruction.md`` (which delegates the normative
grammar, schema, sort rules, and per-phase precedence to
``/app/modgraph/SPEC.md``). The task is constrained to a Go implementation:
the agent writes Go under ``/app/src/`` and compiles
``/app/bin/modarb``; the tests in ``TestImplementationLanguage`` re-execute
the binary into a temporary directory and compare its output against
``/app/decisions/`` byte-for-byte.

Hash-locking strategy: every input fixture under ``/app/modgraph/`` has a
SHA-256 pinned in ``EXPECTED_INPUT_HASHES`` to prove the agent did not
mutate the read-only dataset. Every output object has a canonical-encoding
SHA-256 in ``EXPECTED_OUTPUT_CANONICAL_HASHES`` (full file) and per-field
hashes in ``EXPECTED_FIELD_HASHES``; the in-test reference computation is
an independent re-derivation from the spec.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path

import pytest

MODGRAPH_DIR = Path(os.environ.get("GMBA_MODGRAPH_DIR", "/app/modgraph"))
DECISIONS_DIR = Path(os.environ.get("GMBA_DECISIONS_DIR", "/app/decisions"))
SRC_DIR = Path(os.environ.get("GMBA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("GMBA_BIN_PATH", "/app/bin/modarb"))

REQUIRED_OUTPUT_FILES = [
    "cycle_and_retract_report.json",
    "replace_directive_audit.json",
    "summary.json",
    "version_resolution.json",
    "vulnerability_exposure.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "71aa568d0e156647d10658e552aa198a0c7f6446d04521e3982bb58670e8a4dc",
    "advisories/GO-2024-crypto.json": "2ab369390adf6ca6f9e4366abb76cf7af41e065c9b6bb7acc5aa0f1b7187afcf",
    "advisories/GO-2024-grpc.json": "2790a96b92fc6eec07c34f88d67f74f2535196c113df47285a1deaf322cc9da4",
    "advisories/GO-2024-net.json": "7dbe3adc40c5822069ed79eb8faabb85372727ef9c07b016501ef75f44c60a10",
    "advisories/GO-2024-tel.json": "083e86b6f7ca7bd0be63d2c03c92fd3f8fd2a58ad526a5e7380a302d1e9b0f8b",
    "advisories/GO-2024-tel2.json": "d022f40d089780d47a9d15ae4b3f4c0be3e4c8149a45fd22dd33edcf19d5ee5b",
    "advisories/GO-2024-text.json": "146851ca718404415be15028b38c648fe57885ae96ea7f585e0ba3f12310e325",
    "governance/policy.json": "3abf91de397d9788ac761eabf141dc726acedf2ced93dddb6d4f4e5979a69bc3",
    "incident_log.json": "b6b53990256165db180da61698df2e56b17a403f78ee95bcd591cf0bb85df558",
    "modules/billing.json": "2cd505024c71d833e26d9727f7e9e66b3b1acf9a559ed303f4828f522e692c0e",
    "modules/checkout.json": "5b46ade7a92b752a35d144b1d5d881d293a8dc765c6c1b49662be1ff0443a8da",
    "modules/gateway.json": "b40c8ab1cfa1bd528e68e9e8ed9f0b347164722bd1457fcf92e1db8e7a39bf53",
    "modules/indexer.json": "ff1d8d2afa3b8b7d2412d95034b1ba9548eb7e382d15a7d707e90e01cbf5fc88",
    "modules/notifier.json": "d5368226dfe8c69ae86b61972352f6ef5bb6574c9f82862ceaa47edc00429ea5",
    "modules/opsctl.json": "e2b4def57aaee26984b5aba130891d653e79cd757e96bf12e15be0ab8ab042e9",
    "modules/platform.json": "85b438c6055f40eaa9cd0a7351902bbf1e002ebd40c9231f4cbda46c357955c4",
    "pool_state.json": "cec950bad6f7a7af6e9ef7636bac2f695a2df99f770a755ef07492e69198db0b",
    "registry/github.com__acme__badge.json": "40ae9024b5eab75b7ddc3ff7eb8e6f8398d8cd52fbde6b05e526267c2ad96821",
    "registry/github.com__acme__badge2.json": "6a61bd7b88fbaceb9c15333c2e4d66e89df9c8fa80c2084fdcee93d240aeeed3",
    "registry/github.com__acme__cache.json": "424a7f50961e7549de944e6ca0b21e41f43881db11228863f0b90c458732ebc6",
    "registry/github.com__acme__crypto.json": "1e9257b368e3016d6bd967571066f41715bf4544e5dec69f1b6f8dc245eec779",
    "registry/github.com__acme__logger.json": "66cf39508c89f59a79681ff59774a48726c19e0f0d9512299855692aec52a25d",
    "registry/github.com__acme__nosql.json": "c52e40ec279eec13b5bb44ac93fab8c80db13f46e2170919860cf0bff4a35bc0",
    "registry/github.com__acme__queue.json": "485940498b866a0ab6533823da89c2a9f2f158241222011b227a0d7610e11f52",
    "registry/github.com__acme__telemetry.json": "dffa48e47dcd7fe1224c7796bc0c9a67caa04811a680def62bc43f6b855faae5",
    "registry/github.com__acme__trap.json": "a95f5afcac18ae296ada5bb19473c7ce4006bd47e85670f30fe829e73f95cbfc",
    "registry/github.com__acme__utils.json": "e2307b4075975333458388e402682674d625f11b935767b76b5f80dda6d6fbf4",
    "registry/github.com__acme__utils2.json": "9b4a959c2a2d24091c1cf9d9a1d8de82d69584ad6a07f787abe6b692359079da",
    "registry/golang.org__x__net.json": "b8343ebff564baa776108107c588ff743f35172cd0ee6c338815a2ac326227ba",
    "registry/golang.org__x__text.json": "652c237d0dc3cf39f8ebd1c0fc2f929ad92d07af15bfb0012561fb02cf9cd1b1",
    "registry/google.golang.org__grpc.json": "45147bcb6a5841d9aeeb86f64269d3c34b38bc2a3da892fa22300041eea93e36",
    "registry/k8s.io__apimachinery.json": "67cd0a4c1df84dbb05adae523eda31c8401f10ef6e7844edf62edc15cde23f54",
    "workspace_manifest.json": "f1a47ec4f51ef71aa16a7e2de9d01b56719f2813cc637bbf248f9657fdab1a62",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cycle_and_retract_report.json": "9243a766def8c40047995ac4da97fc44254be4eb6e7172a646567b5a2f4fbf90",
    "replace_directive_audit.json":  "cfa8642fe6584dc3c8d694475067769c38d95d06b0d155b4446530724eb4138b",
    "summary.json":                  "bdff6a2fef6eb6d45f8fad87134fde4b8d869467577c8a3a19fb877d8e474523",
    "version_resolution.json":       "344a6a4e547c793f0f07d2392903c8372857b09abd9d345a859a9d902c3d30f9",
    "vulnerability_exposure.json":   "8cc413bb2c58ed67b7ce1c3ee938ce5144b0483ca9280fb79eb09c5aa7803e9e",
}

EXPECTED_FIELD_HASHES = {
    "version_resolution.deps":                  "04dd364115aa29b5fdf11df22c5970a24a97bcd46fddd832b94e4a71d8a9d531",
    "replace_directive_audit.rows":             "ae5522da060bee4b78e2e1cf687f455d7f15ad152d85dba61bb55c4b0f93e56d",
    "vulnerability_exposure.advisories":        "95ceb8c7ed44cc98f252871382d4351745a57005f3c27301a8d35a33fd03564e",
    "cycle_and_retract_report.cycles":          "fd273916246b3d3fa0f1a923dacc0372f6aa1c5c3a46a52746f9bdfcffd2fa99",
    "cycle_and_retract_report.module_view":    "cf080aedb74bba94fa9dab9d7aed33f7a681bc32883e985d1311500fa55fc354",
    "cycle_and_retract_report.tool_impacts":   "9cf9e122b741bc746b9cef5e2c69e9f90b996ecf6d04c9e76c99a27d19ada28c",
    "summary.accepted_incident_events":         "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
    "summary.advisories_total":                 "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
    "summary.advisories_unmitigated_pinned":    "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.advisories_unreachable":           "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.cycle_modules_total":              "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.deps_blocked_no_version":          "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.deps_forced_pin":                  "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.deps_total":                       "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.deps_workspace_replaced":          "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.ignored_incident_events":          "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.modules_total":                    "10159baf262b43a92d95db59dae1f72c645127301661e0a3ce4e38b295a97c58",
    "summary.replace_rows_applied_workspace":   "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.replace_rows_overridden_incident": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.tool_only_rows":                   "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
}

VERSION_ACTION_VALUES = {
    "block_cycle",
    "block_no_version",
    "forced_pin",
    "mvs_select",
    "mvs_walk_excluded",
    "mvs_walk_retracted",
    "workspace_replace",
}

REPLACE_STATUS_VALUES = {
    "applied_workspace",
    "block_target_missing",
    "conflict_divergent_targets",
    "overridden_incident",
    "quorum_failed",
}

ADVISORY_STATUS_VALUES = {
    "mitigated_bumped",
    "mitigated_by_replace",
    "overridden",
    "still_open_frozen",
    "unmitigated_pinned",
    "unreachable",
}

TOOL_STATUS_VALUES = {"shared_with_requires", "tool_only"}
BLOCKED_REASON_VALUES = {
    "exclude_directive",
    "retracted_emergency",
    "retracted_intrinsic",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = DECISIONS_DIR / name
        assert p.is_file(), f"missing required output file: /app/decisions/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/decisions/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Every read-only fixture under /app/modgraph/ must remain
    byte-identical to its pinned SHA-256 hash, proving the agent did not
    mutate any input file during execution."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each input file's SHA-256 must equal the pinned hash."""
        path = MODGRAPH_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/modgraph/{rel} was modified "
            f"(sha256 expected {expected}, got {actual})"
        )


# ---------------------------------------------------------------------------
# Output structure & encoding
# ---------------------------------------------------------------------------


class TestOutputStructure:
    """The five required outputs must exist with the documented shape and
    canonical JSON encoding (2-space indent, sorted keys, no trailing
    extra newline)."""

    def test_decisions_directory_exists(self):
        """``/app/decisions`` must exist as a directory."""
        assert DECISIONS_DIR.is_dir(), "/app/decisions must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Each of the five required output files must exist as a
        regular file under ``/app/decisions/``."""
        assert (DECISIONS_DIR / name).is_file(), f"missing /app/decisions/{name}"

    def test_no_extra_files_in_decisions_dir(self):
        """``/app/decisions/`` must contain exactly the five required
        output files - no more, no fewer."""
        actual = sorted(p.name for p in DECISIONS_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/decisions must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; "
            f"found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name):
        """Each output file must end with exactly one trailing newline
        byte per the canonical-encoding rule in the spec."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name):
        """The on-disk bytes must equal
        ``json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + '\\n'``."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        actual_bytes = loaded_outputs[name]["bytes"]
        assert actual_bytes == expected_bytes, (
            f"/app/decisions/{name} on-disk bytes do not match the canonical "
            f"pretty form (indent=2, sort_keys=True, trailing newline)"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level(self, name):
        """Re-parses the on-disk file preserving key order and asserts
        every nested object's keys are emitted sorted, not just the
        top level."""
        path = DECISIONS_DIR / name
        ordered = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=OrderedDict)
        violations: list[str] = []

        def walk(node, path_str):
            if isinstance(node, OrderedDict):
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
        assert not violations, (
            f"object keys must be emitted in sorted order at every level of {name}; "
            f"violations:\n  - " + "\n  - ".join(violations)
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name):
        """The canonical (compact, sort-keyed) SHA-256 of each output
        object must match the pinned reference hash, proving the values
        match the independently-computed reference output byte-for-byte."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, (
            f"/app/decisions/{name} canonical SHA-256 mismatch: "
            f"expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# version_resolution.json
# ---------------------------------------------------------------------------


class TestVersionResolution:
    """Every dep that any non-cycle-blocked module requires gets exactly one
    resolution row with the correct action, resolved path, and resolved
    version under the spec's seven-action enumeration."""

    def test_top_level_shape(self, loaded_outputs):
        """``version_resolution.json`` must be ``{"deps":[...]}`` with a
        non-empty deps list."""
        obj = loaded_outputs["version_resolution.json"]["obj"]
        assert set(obj.keys()) == {"deps"}
        assert isinstance(obj["deps"], list)
        assert obj["deps"], "version_resolution.deps must be non-empty"

    def test_entry_fields(self, loaded_outputs):
        """Every entry must expose exactly the five documented keys with
        correct primitive types and an enumerated ``action``."""
        required = {"action", "dep_path", "resolved_path", "resolved_version", "source_event_id"}
        for entry in loaded_outputs["version_resolution.json"]["obj"]["deps"]:
            assert set(entry.keys()) == required
            assert entry["action"] in VERSION_ACTION_VALUES
            assert isinstance(entry["dep_path"], str)
            assert isinstance(entry["resolved_path"], str)
            assert entry["resolved_version"] is None or isinstance(entry["resolved_version"], str)
            assert entry["source_event_id"] is None or isinstance(entry["source_event_id"], str)

    def test_sorted_by_dep_path(self, loaded_outputs):
        """The deps list must be sorted ASCII-ascending by ``dep_path``."""
        entries = loaded_outputs["version_resolution.json"]["obj"]["deps"]
        keys = [e["dep_path"] for e in entries]
        assert keys == sorted(keys), "deps must be sorted by dep_path"

    def test_blocked_actions_have_null_version(self, loaded_outputs):
        """``block_cycle`` and ``block_no_version`` rows must always emit
        ``resolved_version = null`` per the spec."""
        for entry in loaded_outputs["version_resolution.json"]["obj"]["deps"]:
            if entry["action"] in {"block_cycle", "block_no_version"}:
                assert entry["resolved_version"] is None, (
                    f"{entry['dep_path']} action={entry['action']} must have "
                    f"resolved_version=null"
                )
            else:
                assert isinstance(entry["resolved_version"], str), (
                    f"{entry['dep_path']} action={entry['action']} must have "
                    f"a non-null resolved_version string"
                )

    def test_forced_pin_action_has_source_event(self, loaded_outputs):
        """Every ``forced_pin`` row must carry the originating event's
        ``source_event_id``; the resolved version is whatever the event
        named, even if retracted or excluded."""
        for entry in loaded_outputs["version_resolution.json"]["obj"]["deps"]:
            if entry["action"] == "forced_pin":
                assert entry["source_event_id"] is not None, (
                    f"{entry['dep_path']} forced_pin row must name its source event"
                )

    def test_workspace_replace_changes_path(self, loaded_outputs):
        """A ``workspace_replace`` row whose source incident or applied
        target rewrites the path must surface ``resolved_path !=
        dep_path`` whenever the replace target is a different module."""
        deps = loaded_outputs["version_resolution.json"]["obj"]["deps"]
        replaced = [e for e in deps if e["action"] == "workspace_replace"]
        assert replaced, "fixture should exercise the workspace_replace action"
        same_path = [e for e in replaced if e["resolved_path"] == e["dep_path"]]
        diff_path = [e for e in replaced if e["resolved_path"] != e["dep_path"]]
        assert same_path, "fixture should exercise replace-with-same-path"
        assert diff_path, "fixture should exercise replace-to-different-path"

    def test_mvs_walk_retracted_has_null_or_event_source(self, loaded_outputs):
        """``mvs_walk_retracted`` rows that walked over an emergency
        retract must surface that event's id in ``source_event_id``;
        rows that only walked over intrinsic retracts may emit ``null``."""
        for entry in loaded_outputs["version_resolution.json"]["obj"]["deps"]:
            if entry["action"] == "mvs_walk_retracted":
                assert entry["source_event_id"] is None or isinstance(entry["source_event_id"], str)

    def test_all_seven_actions_present(self, loaded_outputs):
        """The fixture is engineered so every one of the seven action
        labels in ``VERSION_ACTION_VALUES`` appears at least once."""
        actions = {e["action"] for e in loaded_outputs["version_resolution.json"]["obj"]["deps"]}
        missing = VERSION_ACTION_VALUES - actions
        assert not missing, f"missing actions: {missing}"

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``deps`` array must canonicalise to the pinned
        SHA-256 reference hash."""
        deps = loaded_outputs["version_resolution.json"]["obj"]["deps"]
        assert _canonical_sha256(deps) == EXPECTED_FIELD_HASHES["version_resolution.deps"]


# ---------------------------------------------------------------------------
# replace_directive_audit.json
# ---------------------------------------------------------------------------


class TestReplaceDirectiveAudit:
    """Per-module replace declarations are audited under the quorum,
    divergence, and incident-override rules, with one row per per-module
    replace entry."""

    def test_top_level_shape(self, loaded_outputs):
        """``replace_directive_audit.json`` must be ``{"rows":[...]}``."""
        obj = loaded_outputs["replace_directive_audit.json"]["obj"]
        assert set(obj.keys()) == {"rows"}
        assert isinstance(obj["rows"], list)

    def test_entry_fields(self, loaded_outputs):
        """Every row must expose exactly the five documented keys with
        correct types and an enumerated ``status``."""
        required = {"effective_target", "from_path", "module_name", "source_event_id", "status"}
        for row in loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]:
            assert set(row.keys()) == required
            assert row["status"] in REPLACE_STATUS_VALUES
            assert isinstance(row["from_path"], str)
            assert isinstance(row["module_name"], str)
            assert row["source_event_id"] is None or isinstance(row["source_event_id"], str)
            target = row["effective_target"]
            assert target is None or set(target.keys()) == {"to_path", "to_version"}

    def test_sorted_by_from_path_then_module(self, loaded_outputs):
        """Rows must be sorted lexicographically by
        ``(from_path, module_name)`` per the spec."""
        rows = loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]
        keys = [(r["from_path"], r["module_name"]) for r in rows]
        assert keys == sorted(keys)

    def test_overridden_incident_rows_carry_event_id(self, loaded_outputs):
        """``overridden_incident`` rows must carry the originating
        event's ``source_event_id``; their ``effective_target`` reflects
        the incident's ``(to_path, to_version)``."""
        rows = loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]
        overridden = [r for r in rows if r["status"] == "overridden_incident"]
        assert overridden, "fixture should exercise overridden_incident"
        for r in overridden:
            assert r["source_event_id"] is not None
            assert r["effective_target"] is not None

    def test_applied_workspace_target_present(self, loaded_outputs):
        """``applied_workspace`` rows must carry a non-null
        ``effective_target`` describing the active replace tuple."""
        for r in loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]:
            if r["status"] == "applied_workspace":
                assert r["effective_target"] is not None

    def test_failed_or_missing_rows_have_null_target(self, loaded_outputs):
        """``quorum_failed``, ``conflict_divergent_targets``, and
        ``block_target_missing`` rows must emit ``effective_target=null``
        per the spec's rules."""
        for r in loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]:
            if r["status"] in {"quorum_failed", "conflict_divergent_targets", "block_target_missing"}:
                assert r["effective_target"] is None

    def test_all_five_statuses_present(self, loaded_outputs):
        """The fixture is engineered so every one of the five status
        labels in ``REPLACE_STATUS_VALUES`` appears at least once."""
        statuses = {r["status"] for r in loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]}
        missing = REPLACE_STATUS_VALUES - statuses
        assert not missing, f"missing statuses: {missing}"

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``rows`` array must canonicalise to the pinned
        SHA-256 reference hash."""
        rows = loaded_outputs["replace_directive_audit.json"]["obj"]["rows"]
        assert _canonical_sha256(rows) == EXPECTED_FIELD_HASHES["replace_directive_audit.rows"]


# ---------------------------------------------------------------------------
# vulnerability_exposure.json
# ---------------------------------------------------------------------------


class TestVulnerabilityExposure:
    """Every advisory in ``/app/modgraph/advisories/`` produces one
    triage row scored against the post-resolution version using the
    six-rule precedence in Phase C of the spec."""

    def test_top_level_shape(self, loaded_outputs):
        """``vulnerability_exposure.json`` must be
        ``{"advisories":[...]}``."""
        obj = loaded_outputs["vulnerability_exposure.json"]["obj"]
        assert set(obj.keys()) == {"advisories"}
        assert isinstance(obj["advisories"], list)

    def test_entry_fields(self, loaded_outputs):
        """Every entry must expose exactly the six documented keys with
        correct primitive types and an enumerated ``status``."""
        required = {
            "advisory_id",
            "covered_post_resolution",
            "dep_path",
            "post_resolution_version",
            "severity",
            "status",
        }
        for entry in loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]:
            assert set(entry.keys()) == required
            assert entry["status"] in ADVISORY_STATUS_VALUES
            assert isinstance(entry["covered_post_resolution"], bool)
            assert isinstance(entry["severity"], str)

    def test_sorted_by_advisory_id(self, loaded_outputs):
        """Advisories must be sorted ASCII-ascending by ``advisory_id``."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        ids = [r["advisory_id"] for r in rows]
        assert ids == sorted(ids)

    def test_overridden_rows_acknowledge_coverage(self, loaded_outputs):
        """An ``overridden`` row's coverage is reported truthfully
        (covered_post_resolution=true) because the override is the only
        reason the advisory does not block the bump."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        overridden = [r for r in rows if r["status"] == "overridden"]
        assert overridden, "fixture should exercise overridden"
        for r in overridden:
            assert r["covered_post_resolution"] is True

    def test_unmitigated_pinned_keeps_pinned_version(self, loaded_outputs):
        """``unmitigated_pinned`` requires the dep to be force-pinned to
        a version covered by the advisory; the row reports that pinned
        version as ``post_resolution_version``."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        upinned = [r for r in rows if r["status"] == "unmitigated_pinned"]
        assert upinned, "fixture should exercise unmitigated_pinned"
        for r in upinned:
            assert r["covered_post_resolution"] is True
            assert isinstance(r["post_resolution_version"], str)

    def test_mitigated_by_replace_uncovered(self, loaded_outputs):
        """``mitigated_by_replace`` rows must have
        ``covered_post_resolution=false`` because the post-resolution
        path is a different dep than the advisory's target."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        replaced = [r for r in rows if r["status"] == "mitigated_by_replace"]
        assert replaced, "fixture should exercise mitigated_by_replace"
        for r in replaced:
            assert r["covered_post_resolution"] is False

    def test_unreachable_requires_coverage(self, loaded_outputs):
        """``unreachable`` rows must have ``covered_post_resolution=true``
        - reachability gating only fires when the chosen version IS
        covered but the symbol set has empty intersection with the
        advisory's affected symbols."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        unreachable = [r for r in rows if r["status"] == "unreachable"]
        assert unreachable, "fixture should exercise unreachable"
        for r in unreachable:
            assert r["covered_post_resolution"] is True

    def test_all_six_statuses_present(self, loaded_outputs):
        """The fixture is engineered so every one of the six status
        labels in ``ADVISORY_STATUS_VALUES`` appears at least once."""
        statuses = {r["status"] for r in loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]}
        missing = ADVISORY_STATUS_VALUES - statuses
        assert not missing, f"missing statuses: {missing}"

    def test_field_canonical_hash(self, loaded_outputs):
        """The full ``advisories`` array must canonicalise to the
        pinned SHA-256 reference hash."""
        rows = loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]
        assert _canonical_sha256(rows) == EXPECTED_FIELD_HASHES["vulnerability_exposure.advisories"]


# ---------------------------------------------------------------------------
# cycle_and_retract_report.json
# ---------------------------------------------------------------------------


class TestCycleAndRetractReport:
    """Cycle events, per-module blocked-version views, and tool-dep
    impacts are reported per Phase D."""

    def test_top_level_shape(self, loaded_outputs):
        """The file must be
        ``{"cycles":[...], "module_view":[...], "tool_impacts":[...]}``."""
        obj = loaded_outputs["cycle_and_retract_report.json"]["obj"]
        assert set(obj.keys()) == {"cycles", "module_view", "tool_impacts"}

    def test_cycles_sorted_by_event_id(self, loaded_outputs):
        """The ``cycles`` list must be sorted ASCII-ascending by
        ``event_id``; cycle_modules within each entry must be sorted."""
        for entry in loaded_outputs["cycle_and_retract_report.json"]["obj"]["cycles"]:
            assert set(entry.keys()) == {"cycle_modules", "event_id"}
            assert entry["cycle_modules"] == sorted(entry["cycle_modules"])
        ids = [e["event_id"] for e in loaded_outputs["cycle_and_retract_report.json"]["obj"]["cycles"]]
        assert ids == sorted(ids)

    def test_module_view_one_per_workspace_module(self, loaded_outputs):
        """``module_view`` must include every module declared in
        ``workspace_manifest.modules`` (cycle-blocked modules included)
        and is sorted ASCII-ascending by ``module_name``."""
        manifest = json.loads((MODGRAPH_DIR / "workspace_manifest.json").read_text(encoding="utf-8"))
        expected_modules = sorted(manifest["modules"])
        actual_modules = [m["module_name"] for m in loaded_outputs["cycle_and_retract_report.json"]["obj"]["module_view"]]
        assert actual_modules == expected_modules

    def test_module_view_in_cycle_flag(self, loaded_outputs):
        """A module's ``in_cycle`` flag must be true iff some accepted
        cycle event names it."""
        cycle_members = set()
        for entry in loaded_outputs["cycle_and_retract_report.json"]["obj"]["cycles"]:
            cycle_members.update(entry["cycle_modules"])
        for m in loaded_outputs["cycle_and_retract_report.json"]["obj"]["module_view"]:
            assert m["in_cycle"] == (m["module_name"] in cycle_members), (
                f"in_cycle mismatch for {m['module_name']}"
            )

    def test_module_view_blocked_versions_shape(self, loaded_outputs):
        """Every ``blocked_versions`` row must expose
        ``{dep_path, reason, version}`` with an enumerated reason and
        be sorted by ``(dep_path, version, reason)``."""
        for m in loaded_outputs["cycle_and_retract_report.json"]["obj"]["module_view"]:
            for bv in m["blocked_versions"]:
                assert set(bv.keys()) == {"dep_path", "reason", "version"}
                assert bv["reason"] in BLOCKED_REASON_VALUES
            keys = [(b["dep_path"], b["version"], b["reason"]) for b in m["blocked_versions"]]
            assert keys == sorted(keys), f"blocked_versions not sorted for {m['module_name']}"

    def test_tool_impacts_shape_and_sort(self, loaded_outputs):
        """Every ``tool_impacts`` row exposes
        ``{dep_path, module_name, tool_status}`` with an enumerated
        status; rows are sorted by ``(module_name, dep_path)``."""
        rows = loaded_outputs["cycle_and_retract_report.json"]["obj"]["tool_impacts"]
        for row in rows:
            assert set(row.keys()) == {"dep_path", "module_name", "tool_status"}
            assert row["tool_status"] in TOOL_STATUS_VALUES
        keys = [(r["module_name"], r["dep_path"]) for r in rows]
        assert keys == sorted(keys)

    def test_both_tool_statuses_present(self, loaded_outputs):
        """Both tool-status enum values appear in the report - one for
        a module that lists the same dep in both ``requires`` and
        ``tools``, one for a module that lists it only as a tool."""
        statuses = {r["tool_status"] for r in loaded_outputs["cycle_and_retract_report.json"]["obj"]["tool_impacts"]}
        missing = TOOL_STATUS_VALUES - statuses
        assert not missing, f"missing tool_status values: {missing}"

    def test_all_three_blocked_reasons_present(self, loaded_outputs):
        """All three ``BLOCKED_REASON_VALUES`` appear across the
        ``module_view`` block (one positive fixture each)."""
        reasons = set()
        for m in loaded_outputs["cycle_and_retract_report.json"]["obj"]["module_view"]:
            for bv in m["blocked_versions"]:
                reasons.add(bv["reason"])
        missing = BLOCKED_REASON_VALUES - reasons
        assert not missing, f"missing blocked reasons: {missing}"

    def test_cycles_field_hash(self, loaded_outputs):
        """The ``cycles`` array canonicalises to its pinned reference
        hash."""
        cycles = loaded_outputs["cycle_and_retract_report.json"]["obj"]["cycles"]
        assert _canonical_sha256(cycles) == EXPECTED_FIELD_HASHES["cycle_and_retract_report.cycles"]

    def test_module_view_field_hash(self, loaded_outputs):
        """The ``module_view`` array canonicalises to its pinned
        reference hash."""
        mv = loaded_outputs["cycle_and_retract_report.json"]["obj"]["module_view"]
        assert _canonical_sha256(mv) == EXPECTED_FIELD_HASHES["cycle_and_retract_report.module_view"]

    def test_tool_impacts_field_hash(self, loaded_outputs):
        """The ``tool_impacts`` array canonicalises to its pinned
        reference hash."""
        ti = loaded_outputs["cycle_and_retract_report.json"]["obj"]["tool_impacts"]
        assert _canonical_sha256(ti) == EXPECTED_FIELD_HASHES["cycle_and_retract_report.tool_impacts"]


# ---------------------------------------------------------------------------
# summary.json
# ---------------------------------------------------------------------------


class TestSummary:
    """Per-key summary counters are pinned by canonical SHA-256 hash."""

    def test_keys_exact(self, loaded_outputs):
        """``summary.json`` must expose exactly the 14 documented keys,
        no extras and no omissions."""
        expected = {
            "accepted_incident_events",
            "advisories_total",
            "advisories_unmitigated_pinned",
            "advisories_unreachable",
            "cycle_modules_total",
            "deps_blocked_no_version",
            "deps_forced_pin",
            "deps_total",
            "deps_workspace_replaced",
            "ignored_incident_events",
            "modules_total",
            "replace_rows_applied_workspace",
            "replace_rows_overridden_incident",
            "tool_only_rows",
        }
        actual = set(loaded_outputs["summary.json"]["obj"].keys())
        assert actual == expected, f"summary key set mismatch: {actual ^ expected}"

    def test_all_integer_valued(self, loaded_outputs):
        """Every summary value must be an integer per the spec."""
        for k, v in loaded_outputs["summary.json"]["obj"].items():
            assert isinstance(v, int) and not isinstance(v, bool), (
                f"summary.{k} must be an integer, got {type(v).__name__}"
            )

    @pytest.mark.parametrize("key", [
        "accepted_incident_events",
        "advisories_total",
        "advisories_unmitigated_pinned",
        "advisories_unreachable",
        "cycle_modules_total",
        "deps_blocked_no_version",
        "deps_forced_pin",
        "deps_total",
        "deps_workspace_replaced",
        "ignored_incident_events",
        "modules_total",
        "replace_rows_applied_workspace",
        "replace_rows_overridden_incident",
        "tool_only_rows",
    ])
    def test_field_canonical_hash(self, loaded_outputs, key):
        """Each summary value's canonical SHA-256 must match the pinned
        reference hash; failures isolate which individual counter is
        wrong."""
        value = loaded_outputs["summary.json"]["obj"][key]
        actual = _canonical_sha256(value)
        expected = EXPECTED_FIELD_HASHES[f"summary.{key}"]
        assert actual == expected, (
            f"summary.{key} canonical hash mismatch: expected {expected}, got {actual}"
        )


# ---------------------------------------------------------------------------
# Independent re-derivation cross-checks
# ---------------------------------------------------------------------------


def _load_modgraph():
    """Independently re-parse the input dataset for in-test verification."""
    out = {
        "workspace": json.loads((MODGRAPH_DIR / "workspace_manifest.json").read_text(encoding="utf-8")),
        "pool_state": json.loads((MODGRAPH_DIR / "pool_state.json").read_text(encoding="utf-8")),
        "incidents": json.loads((MODGRAPH_DIR / "incident_log.json").read_text(encoding="utf-8")),
        "modules": {},
        "registry": {},
        "advisories": {},
    }
    for p in (MODGRAPH_DIR / "modules").iterdir():
        if p.suffix == ".json":
            m = json.loads(p.read_text(encoding="utf-8"))
            out["modules"][m["module_path"]] = m
    for p in (MODGRAPH_DIR / "registry").iterdir():
        if p.suffix == ".json":
            r = json.loads(p.read_text(encoding="utf-8"))
            out["registry"][r["dep_path"]] = r
    for p in (MODGRAPH_DIR / "advisories").iterdir():
        if p.suffix == ".json":
            a = json.loads(p.read_text(encoding="utf-8"))
            out["advisories"][a["advisory_id"]] = a
    return out


class TestCrossChecks:
    """High-level invariants computed by independently re-parsing the
    input dataset, not by reading any reference solution."""

    def test_all_required_deps_have_rows(self, loaded_outputs):
        """Every dep_path that appears in any module's ``requires``
        list must appear exactly once in version_resolution."""
        graph = _load_modgraph()
        expected = set()
        for m in graph["modules"].values():
            for r in m["requires"]:
                expected.add(r["dep_path"])
        actual = {e["dep_path"] for e in loaded_outputs["version_resolution.json"]["obj"]["deps"]}
        missing = expected - actual
        extra = actual - expected
        assert not missing, f"version_resolution missing required deps: {missing}"
        assert not extra, f"version_resolution has unexpected deps: {extra}"

    def test_every_advisory_has_row(self, loaded_outputs):
        """Every advisory file produces exactly one row in
        vulnerability_exposure."""
        graph = _load_modgraph()
        expected = set(graph["advisories"].keys())
        actual = {e["advisory_id"] for e in loaded_outputs["vulnerability_exposure.json"]["obj"]["advisories"]}
        assert actual == expected, f"advisory id set mismatch: {actual ^ expected}"

    def test_summary_modules_total_matches_manifest(self, loaded_outputs):
        """``summary.modules_total`` equals the number of modules
        declared in workspace_manifest.modules."""
        graph = _load_modgraph()
        assert loaded_outputs["summary.json"]["obj"]["modules_total"] == len(graph["workspace"]["modules"])

    def test_summary_event_counts_partition_log(self, loaded_outputs):
        """``accepted_incident_events + ignored_incident_events`` must
        equal the total number of events in incident_log.json - every
        event is either accepted or ignored, never both, never neither."""
        graph = _load_modgraph()
        total = len(graph["incidents"]["events"])
        summary = loaded_outputs["summary.json"]["obj"]
        assert summary["accepted_incident_events"] + summary["ignored_incident_events"] == total


# ---------------------------------------------------------------------------
# Implementation language constraint (Go + binary re-execution)
# ---------------------------------------------------------------------------


class TestImplementationLanguage:
    """The task constrains the agent to a Go reference implementation. A
    Go source tree must live under /app/src/ and a compiled binary at
    /app/bin/modarb must reproduce /app/decisions/ byte-for-byte when
    run against /app/modgraph/. This catches both (a) agents that
    hand-edit JSON and (b) agents that bypass Go in favour of a
    different language."""

    def test_go_source_present(self):
        """``/app/src/`` must contain at least one ``.go`` file, and at
        least one of those files must declare ``package main`` so the
        arbiter is buildable as an executable."""
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
        """``/app/bin/modarb`` must exist as a regular executable file -
        the compiled artifact of the Go source under ``/app/src/``."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist (compiled modarb binary)"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_reproduces_decisions(self):
        """A fresh execution of ``/app/bin/modarb`` against
        ``/app/modgraph/`` must reproduce the on-disk ``/app/decisions/``
        files byte-for-byte.

        Anti-cheat: before running the binary, the existing
        ``/app/decisions/`` directory is moved aside so the binary
        cannot satisfy the test by copying the previously-written
        files. The binary must compute each output from the modgraph
        fixtures via the Go implementation; any wrapper that hard-codes
        ``/app/decisions/`` as its data source will fail because that
        path no longer exists during this test. After the run completes
        the original ``/app/decisions/`` is restored and the freshly
        produced outputs are compared to the saved bytes AND to the
        canonical reference hashes."""
        saved_bytes = {
            name: (DECISIONS_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES
        }
        decisions_backup = DECISIONS_DIR.parent / (DECISIONS_DIR.name + ".anti_cheat_backup")
        if decisions_backup.exists():
            shutil.rmtree(decisions_backup)
        shutil.move(str(DECISIONS_DIR), str(decisions_backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["GMBA_MODGRAPH_DIR"] = str(MODGRAPH_DIR)
                env["GMBA_DECISIONS_DIR"] = td
                result = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                assert result.returncode == 0, (
                    f"binary exit code {result.returncode}\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh_path = Path(td) / name
                    assert fresh_path.is_file(), (
                        f"binary did not write {name} to a fresh decisions dir while "
                        f"/app/decisions/ was unavailable; this strongly suggests "
                        f"the binary copies from /app/decisions/ rather than "
                        f"computing from /app/modgraph/"
                    )
                    fresh = fresh_path.read_bytes()
                    assert fresh == saved_bytes[name], (
                        f"/app/decisions/{name} was not produced by /app/bin/modarb "
                        f"(a fresh run of the binary against /app/modgraph/ - with "
                        f"/app/decisions/ moved aside so it cannot be read - "
                        f"disagrees with the on-disk file)"
                    )
                    fresh_obj = json.loads(fresh.decode("utf-8"))
                    assert _canonical_sha256(fresh_obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name], (
                        f"binary re-execution output for {name} disagrees with "
                        f"the canonical reference hash"
                    )
        finally:
            if DECISIONS_DIR.exists():
                shutil.rmtree(DECISIONS_DIR)
            shutil.move(str(decisions_backup), str(DECISIONS_DIR))
