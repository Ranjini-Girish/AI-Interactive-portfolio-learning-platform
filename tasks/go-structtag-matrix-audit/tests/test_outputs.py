"""Behavioral tests for the go-structtag-matrix-audit task."""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path

import pytest

REGISTRY_DIR = Path(os.environ.get("GTA_REGISTRY_DIR", "/app/registry"))
AUDIT_DIR = Path(os.environ.get("GTA_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("GTA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("GTA_BIN_PATH", "/app/bin/tagmatrix"))

REQUIRED_OUTPUT_FILES = [
    "incident_resolution.json",
    "json_name_collisions.json",
    "package_rollups.json",
    "summary.json",
    "tag_parse_matrix.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5f98e77b8d1f92ab64a5d9ffd294d5eb682aac47a472741b6377e575c8f78100",
    "incidents/incident_log.json": "b3cbdc6d46a72df0c7520632c7fce269898d7eb77dccc5c1be18ac82d0f86242",
    "packages/admin.token.json": "b7eae580a2177734772de2be01fc1bb20f4db830cd7ffee5cbc9058292522dfb",
    "packages/api.dto.json": "dca3f8817713c710586ff447d7dce93bd057482f283b770c764ead6399750b1c",
    "packages/billing.row.json": "afdab579e724e4551f492e2ff8940f3875f8a78f22777d6b7c9131aa02026d7f",
    "packages/cache.key.json": "cc12239d88cda055ed0c551291eb489e8b0a4f5670815ffe7c0e0c206b294110",
    "packages/chat.message.json": "6c5605f762e4ef002cb66dcbef8b9226ea306cac26e54ffaf3b02c9f03d9e8d3",
    "packages/core.ids.json": "fd674b77d796f298d540bf537ad95911d1cd036f74f8007f341c7f799059edc3",
    "packages/core.types.json": "81109c9caa03c29dbd2faf4182a95584b0b15660836b3527e287225e0c9e8055",
    "packages/embed.slot.json": "a9c14fa7ee4d545db15b3ae653bc4fa37c5966b3bc2048a8372987589c02444e",
    "packages/legacy.compat.json": "467633252104509d0550dc2471922e743c776af12a9bfe345043c88a6bc48518",
    "packages/obs.metric.json": "72c1896f2b856195ceed8d0e711b1d2bf7a941f9c136ef721aaf5b31f280a424",
    "packages/obs.trace.json": "91c670d9d5375a3effa5eb5dbafc1b57406bebed1908c3b19fac958b2ddd4dc6",
    "packages/worker.job.json": "8bee63d3607e2cfda0bcd3778af8c031ae5b17876ef6821dd1abb1e75ae37454",
    "policy/policy.json": "337b2d46bcbf084808273493c0260c7a80955cd5985aac49eec24d104b6a8236",
    "pool_state.json": "bb1dfea723885f497da3c5043231ea070e405766b63f2455924fc65a42abd94f",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_resolution.json": "b1ec12a93285814e4fe3e9c1cf531aa4a66b38bccb49691ba2ac735896fbffcd",
    "json_name_collisions.json": "09075d8268ea07d2200c9c2bbd3f26cb81644494924f8c4ac7a1d3cf8312b593",
    "package_rollups.json": "02afb33fe772f8b6107f6a500336a85c60732f88683b78af555a56be3d5c235b",
    "summary.json": "2bb3565f7dd9b1fd53bbdafd5279de282917082bdce5b6d6c82af6ee9fd46619",
    "tag_parse_matrix.json": "42797e417dbb5a57851dbf1777f67fdacbcd940f49a1bd444079d0a945aa03a4",
}

EXPECTED_FIELD_HASHES = {
    "tag_parse_matrix.entries": "b3917a79d8c141398b8082d5af586b608e21de57fcdcf926bd79ddd47f1324b5",
    "json_name_collisions.groups": "79bddad187fecb7cdad85e4772f250a804e6f2b35e6b108a125662da607ef97e",
    "package_rollups.packages": "973f796fceb85f13a68d192612931fdfd09221f05eabe34840767b419c2e08e7",
    "incident_resolution.accepted_events": "79f607e077322713df23e616ce5ff93c68f23734335b5908976b424435531c15",
    "incident_resolution.ignored_event_ids": "487d0be13dc787e09936fca1529b6c04651e3f8ef3e751db8e7812753b27f671",
    "summary.accepted_incident_events": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.blocked_packages": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.collision_groups": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.fields_missing_json_tag": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.fields_total": "238903180cc104ec2c5d8b3f20c5bc61b389ec0a967df8cc208cdc7cd454174f",
    "summary.ignored_incident_events": "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.naming_skew_fields": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.packages_total": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.parse_error_fields": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.structs_total": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.waived_naming_skew_fields": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
}

PARSE_STATUS_VALUES = {
    "invalid_empty_bson_name",
    "invalid_empty_json_name",
    "invalid_unknown_json_flag",
    "missing_json_tag",
    "ok",
}

EFFECTIVE_SEVERITY_VALUES = {"blocked", "error", "info", "ok", "warn"}

SUMMARY_TOP_KEYS = {
    "accepted_incident_events",
    "blocked_packages",
    "collision_groups",
    "fields_missing_json_tag",
    "fields_total",
    "ignored_incident_events",
    "naming_skew_fields",
    "packages_total",
    "parse_error_fields",
    "structs_total",
    "waived_naming_skew_fields",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj: object) -> str:
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
    def test_input_file_unchanged(self, rel: str) -> None:
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

    def test_audit_directory_exists(self) -> None:
        """``/app/audit`` must exist as a directory."""
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name: str) -> None:
        """Each required filename must exist under ``/app/audit/``."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self) -> None:
        """The audit directory must contain exactly the five required files."""
        actual = sorted(p.name for p in AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/audit must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name: str) -> None:
        """Each file ends with exactly one ``\\n``."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name: str) -> None:
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
    def test_object_keys_sorted_at_every_level_on_disk(self, name: str) -> None:
        """Every JSON object must emit keys in sorted order at all depths."""
        path = AUDIT_DIR / name
        ordered = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=collections.OrderedDict,
        )
        violations: list[str] = []

        def walk(node: object, path_str: str) -> None:
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
    def test_output_canonical_hash(self, loaded_outputs, name: str) -> None:
        """Compact canonical SHA-256 of each root object must match the pin."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, f"/app/audit/{name} canonical hash mismatch"


class TestFieldHashes:
    """Pinned sub-object hashes for anti-cheat."""

    @pytest.mark.parametrize("field_key", list(EXPECTED_FIELD_HASHES.keys()))
    def test_field_canonical_hash(self, loaded_outputs, field_key: str) -> None:
        """Each ``file.key`` fragment must match its pinned canonical hash."""
        stem, _, sub = field_key.partition(".")
        obj = loaded_outputs[f"{stem}.json"]["obj"]
        fragment = obj[sub]
        actual = _canonical_sha256(fragment)
        expected = EXPECTED_FIELD_HASHES[field_key]
        assert actual == expected, f"field hash mismatch for {field_key}"


class TestSummaryShape:
    """``summary.json`` exposes exactly the documented counters."""

    def test_summary_top_level_keys(self, loaded_outputs) -> None:
        """Summary must expose exactly the integer counters named in SPEC."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj.keys()) == SUMMARY_TOP_KEYS
        for k, v in obj.items():
            assert isinstance(v, int) and v >= 0, f"summary.{k} must be a non-negative int"


class TestEnumCoverage:
    """Enumerated strings stay within documented vocabularies."""

    def test_parse_status_values_present(self, loaded_outputs) -> None:
        """At least one entry exists for each documented ``parse_status`` value."""
        seen: set[str] = set()
        for row in loaded_outputs["tag_parse_matrix.json"]["obj"]["entries"]:
            seen.add(row["parse_status"])
        assert seen == PARSE_STATUS_VALUES, f"parse_status set mismatch: {seen}"

    def test_effective_severity_enumeration(self, loaded_outputs) -> None:
        """Every entry uses a documented ``effective_severity`` string."""
        for row in loaded_outputs["tag_parse_matrix.json"]["obj"]["entries"]:
            assert row["effective_severity"] in EFFECTIVE_SEVERITY_VALUES

    def test_integrity_lock_forces_blocked(self, loaded_outputs) -> None:
        """``admin.token`` fields must all be blocked under an accepted lock."""
        for row in loaded_outputs["tag_parse_matrix.json"]["obj"]["entries"]:
            if row["package_id"] == "admin.token":
                assert row["effective_severity"] == "blocked"

    def test_naming_waiver_downgrades_legacy_skew(self, loaded_outputs) -> None:
        """Skew rows under ``legacy.compat`` become info when waiver wins."""
        for row in loaded_outputs["tag_parse_matrix.json"]["obj"]["entries"]:
            if row["package_id"] == "legacy.compat" and row["naming_skew"]:
                assert row["effective_severity"] == "info"

    def test_billing_skew_stays_warn_without_waiver(self, loaded_outputs) -> None:
        """Skew on ``billing.row`` stays warn because no waiver applies there."""
        for row in loaded_outputs["tag_parse_matrix.json"]["obj"]["entries"]:
            if row["package_id"] == "billing.row" and row["naming_skew"]:
                assert row["effective_severity"] == "warn"

    def test_collision_group_lists_api_dto(self, loaded_outputs) -> None:
        """Known duplicate JSON names appear as one sorted collision group."""
        groups = loaded_outputs["json_name_collisions.json"]["obj"]["groups"]
        assert len(groups) == 1
        g0 = groups[0]
        assert g0["package_id"] == "api.dto"
        assert g0["struct_id"] == "Request"
        assert g0["json_name"] == "userId"
        assert g0["field_ids"] == ["A", "B"]

    def test_incident_accepted_and_ignored_sets(self, loaded_outputs) -> None:
        """Accepted winners and ignored ids match the fixture policy."""
        inc = loaded_outputs["incident_resolution.json"]["obj"]
        accepted_ids = {e["event_id"] for e in inc["accepted_events"]}
        assert accepted_ids == {"ev-lock-b", "ev-waiver-b"}
        assert inc["ignored_event_ids"] == [
            "ev-deny",
            "ev-future",
            "ev-lock-a",
            "ev-unsupported",
            "ev-waiver-a",
        ]


class TestGoBuildArtifact:
    """The task expects a Go main package and compiled binary path."""

    def test_src_dir_exists(self) -> None:
        """Agent workspace should keep Go sources under ``/app/src``."""
        assert SRC_DIR.is_dir(), "/app/src must exist"

    def test_binary_path_is_file(self) -> None:
        """The compiled auditor binary must exist at the pinned path."""
        assert BIN_PATH.is_file(), "/app/bin/tagmatrix must exist"
