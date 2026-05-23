"""Behavioral tests for the openapi-drift-auditor task.

The tests verify JSON under ``/app/audit/`` against the contract delegated to
``/app/registry/SPEC.md``. Input fixtures are hash-locked; outputs are
hash-locked in canonical compact form. The task requires Go: sources under
``/app/src/`` and a compiled ``/app/bin/auditor`` that repopulates the audit
directory when re-run with fresh paths.
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

REGISTRY_DIR = Path(os.environ.get("ODA_REGISTRY_DIR", "/app/registry"))
AUDIT_DIR = Path(os.environ.get("ODA_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("ODA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("ODA_BIN_PATH", "/app/bin/auditor"))

REQUIRED_OUTPUT_FILES = [
    "change_classification.json",
    "consumer_impact.json",
    "migration_plan.json",
    "risk_assessment.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d4d1ed607fb49c95deba619cbbc9523e2d331dc690a886b37e74b8db676d62bf",
    "baselines/svc.billing.report.json": "6033cbb327bdf2a8349b3424ca0b40bd41eb3e3cd2667fa7d679731644b0f9e7",
    "baselines/svc.cycle.alpha.json": "6f867e2dfb2db5524d32eb1479b8a6ff4535b68dfaa91c057541ad59e4f990b8",
    "baselines/svc.cycle.beta.json": "4e6b0bdbe602c1675b664ff8ca487a5cd928fd2c1ae9dd9d88e5c586dcc5be58",
    "baselines/svc.gateway.json": "d22c5ba64a64abe45d24e45160826242a7bfdcb314a1949532a7e2a017daddc1",
    "baselines/svc.legacy.exporter.json": "9a89bf4e4b91561b66b6e8fb554b6ac0f464294676883356c259919f0c816fb1",
    "baselines/svc.notifications.json": "bd13ff550faef71043db293c21b31cfecd2358a163d1ff516a1a3e38c5f7044f",
    "baselines/svc.orders.json": "158b59a3df5b9e797c61c1655b59039cabe1d4c430277f7742c8203da91f9caf",
    "baselines/svc.payments.json": "79f65c012e2a31fef5991efb235e6b4b873dd88eed399e96a33accef6969cef7",
    "baselines/svc.users.profile.json": "ba0f2baf7b9fae5639085ab79add97bedc69be1c1374a65a401fab5521344d49",
    "consumers/dependencies.json": "5f726b8a26e4022f5ac5796651bbffa8ab1e4ef3d6082d3f7f77cb7199208de2",
    "incidents/incident_log.json": "aa322613732221e15deaef6b71f1421db0f83c1cbae6dea66ab3a02b39563521",
    "policy/policy.json": "61d47590afbe5a0d9a7093536b055f8577f8e919872b09d15e2576e8c23e334e",
    "pool_state.json": "d08fc110d88d5fd10ee292e6075d32f5944d4f2ea4b07fd132824a072b52304a",
    "services/svc.billing.report.json": "6033cbb327bdf2a8349b3424ca0b40bd41eb3e3cd2667fa7d679731644b0f9e7",
    "services/svc.cycle.alpha.json": "45e936337c39ca2883a1abef7a87c547338fd6cdc8373173858a7b7a2492bebb",
    "services/svc.cycle.beta.json": "4e6b0bdbe602c1675b664ff8ca487a5cd928fd2c1ae9dd9d88e5c586dcc5be58",
    "services/svc.gateway.json": "11c21dca7eb9c9a806818a46e8e30d7a0abe309d63c855c70c46a0bef49f38cb",
    "services/svc.legacy.exporter.json": "47e3eacd21685e217850e7bba9086d76b8d53c2e63b85c2a862efabc5a0226ba",
    "services/svc.notifications.json": "6b4cdb8c0ca25582098d8fe6b6fd6f774339790176edc39409eaa32487628775",
    "services/svc.orders.json": "4652e3a7d80289dbb633b47995fe5050750ddb53d644c512409b92a085ba8934",
    "services/svc.payments.json": "6adadfeb538641b96738734efc26675caad6d8defa1b8c172316751f30bea051",
    "services/svc.users.profile.json": "ec571d594f84b6e9c459d2b57525908d966ad21d545c6ffe891a3569b0ee67e9",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "change_classification.json": "3da38f9858a7811e38dab6ff613a63a57b85f306404327d8b96a7cdd27000d1a",
    "consumer_impact.json": "e07bc83b7f5cb0a19574906d75b4cb706126da132049da1f925057abc8b2e6fc",
    "migration_plan.json": "135f000f977988bc7779ad359581fbe0d8b5b537921a6f57f085f4f230822be5",
    "risk_assessment.json": "95988303e2817e528ef559c3e103fc59f728fb4cb8ace6b7434f01677e35d5da",
    "summary.json": "2a4f53f85f956e5b8b830108756de41bdb04670043576aca7b41abfc26713bb5",
}

EXPECTED_FIELD_HASHES = {
    "change_classification.services": "78784bd50c2f47e5476bd576d2b4ba007475a33247d1df423828d98855920a1d",
    "consumer_impact.consumers": "a3e13254d0f960f08fce216aad5b1b6d3be3bebd7775d841d57cb0bdbd0b4f6e",
    "migration_plan.services": "bba9d574a8c90db218061af1667f828431bb0f445afbb82d9e4cfb0ee4263eb1",
    "risk_assessment.services": "bb9ac6e2193106a856a1ccb528cdc677a10ec22280c522460b98a0bd3276c1b3",
    "summary.accepted_incident_events": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.affected_direct_count": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.affected_transitive_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.allow_action_services_count": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.block_action_services_count": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.blocked_cycle_services_count": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.breaking_count": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.breaking_forced_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.consumers_total": "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.consumers_with_no_impact": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.cyclic_consumers_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.deferred_services_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.endpoint_changes_total": "917df3320d778ddbaa5c5c7742bc4046bf803c36ed2b050f30844ed206783469",
    "summary.force_migration_required_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.force_phase_zero_count": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.ignored_incident_events": "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
    "summary.minor_count": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.non_breaking_count": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.services_total": "2e6d31a5983a91251bfae5aefa1c0a19d8ba3cf601d0e8a706b4cfa9661a6b8a",
    "summary.warn_action_services_count": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
}

CLASSIFICATION_VALUES = {"breaking", "breaking_forced", "minor", "non_breaking"}
SUMMARY_ACTION_VALUES = {"force_migrate", "migrate", "monitor", "none"}
IMPACT_TYPE_VALUES = {
    "affected_direct",
    "affected_transitive",
    "force_migration_required",
    "cyclic_field_exposure",
}
PHASE_ORIGIN_VALUES = {"blocked_cycle", "deferred_freeze", "forced_phase_zero", "topo"}
RISK_ACTION_VALUES = {"allow", "block", "warn"}
ACTION_ORIGIN_VALUES = {"forced_event", "tier_rule"}

CHANGE_KIND_VALUES = {
    "auth_mode_changed",
    "endpoint_added",
    "endpoint_removed",
    "param_added_optional",
    "param_added_required",
    "param_removed",
    "param_required_added",
    "param_type_narrowed",
    "response_field_added",
    "response_field_removed",
    "response_field_type_changed",
    "status_code_class_change",
}

SUMMARY_TOP_KEYS = {
    "accepted_incident_events",
    "affected_direct_count",
    "affected_transitive_count",
    "allow_action_services_count",
    "block_action_services_count",
    "blocked_cycle_services_count",
    "breaking_count",
    "breaking_forced_count",
    "consumers_total",
    "consumers_with_no_impact",
    "cyclic_consumers_count",
    "deferred_services_count",
    "endpoint_changes_total",
    "force_migration_required_count",
    "force_phase_zero_count",
    "ignored_incident_events",
    "minor_count",
    "non_breaking_count",
    "services_total",
    "warn_action_services_count",
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
    """Registry fixtures must remain byte-identical."""

    @pytest.mark.parametrize("rel", list(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each file under the registry tree must match its pinned SHA-256."""
        path = REGISTRY_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/registry/{rel} was modified (expected {expected}, got {actual})"
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


class TestSummaryShape:
    """``summary.json`` top-level keys are exactly the documented counter set."""

    def test_summary_top_level_keys(self, loaded_outputs):
        """Summary must expose exactly the integer counters named in SPEC."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj.keys()) == SUMMARY_TOP_KEYS
        for k, v in obj.items():
            assert isinstance(v, int) and v >= 0, f"summary.{k} must be a non-negative int"


class TestEnumCoverage:
    """Enumerated strings in outputs stay within the documented vocabularies."""

    def test_change_classification_enums(self, loaded_outputs):
        """Every endpoint row uses documented ``classification`` and ``change_kinds``."""
        for svc in loaded_outputs["change_classification.json"]["obj"]["services"]:
            for ep in svc["endpoint_changes"]:
                assert ep["classification"] in CLASSIFICATION_VALUES
                for ck in ep["change_kinds"]:
                    assert ck in CHANGE_KIND_VALUES, f"unknown change_kind {ck!r}"

    def test_consumer_impact_enums(self, loaded_outputs):
        """Consumer rows use documented ``summary_action`` and ``impact_type`` values."""
        for row in loaded_outputs["consumer_impact.json"]["obj"]["consumers"]:
            assert row["summary_action"] in SUMMARY_ACTION_VALUES
            for hit in row["impacted_endpoints"]:
                assert hit["impact_type"] in IMPACT_TYPE_VALUES

    def test_migration_plan_enums(self, loaded_outputs):
        """Migration rows only use documented ``phase_origin`` strings."""
        for row in loaded_outputs["migration_plan.json"]["obj"]["services"]:
            assert row["phase_origin"] in PHASE_ORIGIN_VALUES

    def test_risk_assessment_enums(self, loaded_outputs):
        """Risk rows use documented ``action`` and ``action_origin`` strings."""
        for row in loaded_outputs["risk_assessment.json"]["obj"]["services"]:
            assert row["action"] in RISK_ACTION_VALUES
            assert row["action_origin"] in ACTION_ORIGIN_VALUES


class TestFixtureSpotChecks:
    """Positively exercises fixture-driven branches named in SPEC."""

    def test_known_breaking_forced_endpoint(self, loaded_outputs):
        """The gold orders POST endpoint is under a forced-break event in the fixture."""
        services = loaded_outputs["change_classification.json"]["obj"]["services"]
        orders = next(s for s in services if s["service_id"] == "svc.orders")
        post = next(e for e in orders["endpoint_changes"] if e["endpoint_id"] == "POST /v1/orders")
        assert post["classification"] == "breaking_forced"
        assert post["reason"] == "forced_event"

    def test_known_cyclic_impact_present(self, loaded_outputs):
        """At least one consumer carries ``cyclic_field_exposure`` in the fixture."""
        consumers = loaded_outputs["consumer_impact.json"]["obj"]["consumers"]
        types = {h["impact_type"] for c in consumers for h in c["impacted_endpoints"]}
        assert "cyclic_field_exposure" in types

    def test_known_force_migrate_summary_action(self, loaded_outputs):
        """At least one consumer is ``force_migrate`` when forced migration hits."""
        consumers = loaded_outputs["consumer_impact.json"]["obj"]["consumers"]
        actions = {c["summary_action"] for c in consumers}
        assert "force_migrate" in actions

    def test_known_blocked_cycle_phase_origin(self, loaded_outputs):
        """At least one service is ``blocked_cycle`` in the fixture graph."""
        rows = loaded_outputs["migration_plan.json"]["obj"]["services"]
        origins = {r["phase_origin"] for r in rows}
        assert "blocked_cycle" in origins

    def test_known_deferred_freeze_phase_origin(self, loaded_outputs):
        """At least one service is ``deferred_freeze`` from the fixture incident."""
        rows = loaded_outputs["migration_plan.json"]["obj"]["services"]
        origins = {r["phase_origin"] for r in rows}
        assert "deferred_freeze" in origins


class TestImplementationLanguage:
    """Go sources and binary must reproduce ``/app/audit`` from ``/app/registry``."""

    def test_go_source_present(self):
        """``/app/src`` must contain Go files declaring ``package main``."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files under {SRC_DIR}"
        has_main = False
        for gf in go_files:
            text = gf.read_text(encoding="utf-8", errors="replace")
            if re.search(r"^\s*package\s+main\b", text, re.MULTILINE):
                has_main = True
                break
        assert has_main, f"no file under {SRC_DIR} declares package main"

    def test_binary_present(self):
        """``/app/bin/auditor`` must exist and be executable."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

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
                env["ODA_REGISTRY_DIR"] = str(REGISTRY_DIR)
                env["ODA_AUDIT_DIR"] = td
                result = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                assert result.returncode == 0, (
                    f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh = Path(td) / name
                    assert fresh.is_file(), f"binary did not write {name} into fresh ODA_AUDIT_DIR"
                    got = fresh.read_bytes()
                    assert got == saved[name], (
                        f"/app/audit/{name} was not reproduced by the binary from /app/registry"
                    )
                    obj = json.loads(got.decode("utf-8"))
                    assert _canonical_sha256(obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        finally:
            shutil.move(str(backup), str(AUDIT_DIR))
