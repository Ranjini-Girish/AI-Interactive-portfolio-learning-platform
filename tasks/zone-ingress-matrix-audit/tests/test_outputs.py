"""Behavioral tests for the zone-ingress-matrix-audit task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/zoning/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ZIM_DATA_DIR", "/app/zoning"))
AUDIT_DIR = Path(os.environ.get("ZIM_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "incident_trace.json",
    "matrix_cells.json",
    "precedence_table.json",
    "summary.json",
    "zone_catalog.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "de039521404f9ffee99ad32a14ffa9cf6eeaf2474c6ba77b6766901e81554fbf",
    "incident_log.json": "4e9ff211eab0ad81fc364f3ca2b9122bfcb634c4b9e2791b07c015e6172ff2d7",
    "policy/implicit_matrix.json": "62ed8843dd6acb8af144b10a30d84ed1c27c832e3ac073eda049438131a80897",
    "policy/tier_weights.json": "c604159266ac08fb27d44088459666be9dbb86181e9244c389b305f4620264d8",
    "pool_state.json": "422457d45a7a3fc5c5fe7990a39faa4f6834041246b625638474a3b059fc7d1a",
    "rules/shard_broken.json": "7fc177c70d7420b22cfbfb84c7c15cde55b762f71a8587a3e353b2a0215a5a02",
    "rules/shard_core.json": "590666a82c80274c809c755f30c14a680dacb30f878edc6dfe1f22934eb856ce",
    "rules/shard_edge.json": "0904f025e449142471579a02917b895e25fe3225ec1e358631a2b49f7799aeea",
    "rules/shard_egress.json": "85615abd857b5dfb61ae5eebb1e8c8ba90c3911115da28844a471b62201b2416",
    "rules/shard_mgmt.json": "81b6eee1c29c14fbf68ddcceb5bd51fa8b3fb490ae83c92893d492af85abdbca",
    "rules/shard_staging.json": "0b4928f695b78dafb875bd3a1fee75993932c252b283dfdcb31d1f5d2d3d611c",
    "zones/z_bastion.json": "a6a5f848f0d7f264fac4525c131bb270b4885f3df96767dca17be086eae7c1fb",
    "zones/z_db.json": "e810f04f377c037e8eea5219fffb80d06f0da51a4824846f25009697d4333260",
    "zones/z_dmz.json": "1d33f4ff2eba29cb7c1459f82520067fe66d95560513898330b35308f8712920",
    "zones/z_egress.json": "a422ab34f1f17b3a2d545a9b91d72ea67d350129272935e4bd9edb2df3126f19",
    "zones/z_internal.json": "0485e526140b7eb74d216052c5316b5626be13f791e7aa16ab1a9f5104f6f46a",
    "zones/z_mgmt.json": "303e2cf8f2f3998d13af31f76e7ce49e23a6664daf9884af352e925a2d3ae456",
    "zones/z_staging.json": "fecc8971e66bc0c737ddf1941c4ed370695e2944daa8d8ef98b46eb81c45e8a8",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_trace.json": "20144a7251c7b8312c66c3e1df890bc88bf32be9390fc1eaab9bd3051ba317ee",
    "matrix_cells.json": "48fe3f734f1825a28742472c78409c6dfc1e16d782fb7842a4e4bb21000e4fbc",
    "precedence_table.json": "4cfa803f33932c4bd95bd1a7f3cdff2486fc4d66ddaef66c37fbadbf2a9c46ae",
    "summary.json": "2452cf2c39f454fd28eb6cdb499e6650803aeb0f970ebd9ac1e8a5cbd07ca9b8",
    "zone_catalog.json": "9f67fa145054a9fa5bc31fc7db539308937fd29a5b3295c353696f14e91c825a",
}

EXPECTED_FIELD_HASHES = {
    "incident_trace.events": "6cd1704ac53ba096d34431b23121c2bba2815566914b19a2e63a2e37c504b35a",
    "matrix_cells.cells": "635739b87f3dde19b44a8f9b687be352ec5ea00a374ff8fcbc608dbf414f3a2a",
    "precedence_table.rules": "cc2f021ed82c4087f6dffacf40836a76eb54635e0c5b1559822fa60f87a51c1e",
    "summary.audit_version": "6aa0b9ebb7071ed52163e02dd7334ae2bea752bb4d57cc33f7301c25c20af5e4",
    "summary.cell_count": "6169555d9248be7e184f52250129b0d66c9932af74f4ac7bc716c20013fca362",
    "summary.current_day": "084c799cd551dd1d8d5c5f9a5d593b2e931f5e36122ee5c793c1d08a19839cc0",
    "summary.ignored_incidents": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.invalid_rule_refs": "dd9901a09a12fc7640bfef033864ecf40213609ff0e31d9a1a057a257e996ed4",
    "summary.unsupported_incident_kinds": "1061edb5ec45126724d3c15589d52c3f754571e34c92bacebbc4185722484e03",
    "summary.verdict_counts": "62ca86347ec7292dbc2b9b8912cb16814631b38b0ef3a487b7039ca433565ddb",
    "summary.zone_count": "10159baf262b43a92d95db59dae1f72c645127301661e0a3ce4e38b295a97c58",
    "zone_catalog.zones": "b4e1ebc70b6f211085ae8b0859ab1a2504078259c6d60dfcc343c550b8a1a4cd",
}


def _sha256_bytes(b: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of the given bytes."""
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    """Serialize JSON for hashing: sorted keys, compact separators, UTF-8, trailing newline."""
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    """SHA-256 of the verifier's compact JSON-with-newline canonicalization of obj."""
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    """Load every required output under AUDIT_DIR into text, parsed object, and raw bytes."""
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: {AUDIT_DIR.as_posix()}/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output {AUDIT_DIR.as_posix()}/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's canonical SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: zoning/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture zoning/{rel} was modified"


class TestReportStructure:
    """The five output files must exist with the right top-level shape."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name, loaded_outputs):
        """Every required output file must be present and parseable."""
        assert name in loaded_outputs

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_canonical_hash_each_file(self, name, loaded_outputs):
        """Each output file must hash to the locked canonical baseline."""
        assert _canonical_sha256(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    def test_files_are_pretty_printed(self, loaded_outputs):
        """Every output file must use 2-space indent and end with one trailing newline."""
        for name, data in loaded_outputs.items():
            text = data["text"]
            assert text.endswith("\n"), f"{name} must end with a newline"
            assert not text.endswith("\n\n"), f"{name} must not end with multiple newlines"
            expected = json.dumps(data["obj"], indent=2, sort_keys=True, ensure_ascii=False) + "\n"
            assert text == expected, f"{name} is not canonical 2-space indented sorted JSON"

    def test_top_level_keys_exactly(self, loaded_outputs):
        """Each output file must contain exactly its documented top-level keys."""
        expected_keys = {
            "incident_trace.json": {"events"},
            "matrix_cells.json": {"cells"},
            "precedence_table.json": {"rules"},
            "summary.json": {
                "audit_version",
                "cell_count",
                "current_day",
                "ignored_incidents",
                "invalid_rule_refs",
                "unsupported_incident_kinds",
                "verdict_counts",
                "zone_count",
            },
            "zone_catalog.json": {"zones"},
        }
        for name, keys in expected_keys.items():
            assert set(loaded_outputs[name]["obj"].keys()) == keys, (
                f"{name} top-level keys must equal {sorted(keys)}"
            )


class TestFieldHashes:
    """Field-level hashes catch silent drift inside nested structures."""

    @pytest.mark.parametrize("field,expected", sorted(EXPECTED_FIELD_HASHES.items()))
    def test_field_hash(self, field, expected, loaded_outputs):
        """Each named field must match its locked canonical hash."""
        file_name, _, path = field.partition(".")
        obj = loaded_outputs[f"{file_name}.json"]["obj"]
        cur = obj
        for part in path.split("."):
            cur = cur[part]
        assert _canonical_sha256(cur) == expected, f"field {field} drifted"


class TestMatrixSemantics:
    """Spot-check compound incident and precedence behaviour."""

    def _cell(self, loaded_outputs, src: str, dst: str) -> dict:
        """Return the matrix_cells row for the ordered pair (src, dst) or raise if missing."""
        for row in loaded_outputs["matrix_cells.json"]["obj"]["cells"]:
            if row["src_zone"] == src and row["dst_zone"] == dst:
                return row
        raise AssertionError(f"missing cell {src}->{dst}")

    def test_staging_to_db_explicit_allow_after_chain(self, loaded_outputs):
        """Staging to database must end allow via injected synthetic after suspends."""
        c = self._cell(loaded_outputs, "z_staging", "z_db")
        assert c["via"] == "explicit"
        assert c["verdict"] == "allow"
        assert str(c["winning_rule_id"]).startswith("inj__")

    def test_dmz_to_db_emergency_deny(self, loaded_outputs):
        """DMZ to database must be deny once baseline dmz rule is suspended."""
        c = self._cell(loaded_outputs, "z_dmz", "z_db")
        assert c["verdict"] == "deny"
        assert c["winning_rule_id"] == "surf__e05_emergency_db"

    def test_bastion_to_db_exempt_from_surface(self, loaded_outputs):
        """Bastion must remain allow to database because emergency exempts that source."""
        c = self._cell(loaded_outputs, "z_bastion", "z_db")
        assert c["verdict"] == "allow"
        assert c["winning_rule_id"] == "r_bastion_db_allow"

    def test_mgmt_effective_tier_after_remaps(self, loaded_outputs):
        """Management zone must show internal tier after the paired remap events."""
        zones = {z["zone_id"]: z for z in loaded_outputs["zone_catalog.json"]["obj"]["zones"]}
        mg = zones["z_mgmt"]
        assert mg["declared_tier"] == "internal"
        assert mg["effective_tier"] == "internal"

    def test_staging_effective_tier_remapped_production(self, loaded_outputs):
        """Staging zone must carry production effective tier for implicit lookups."""
        zones = {z["zone_id"]: z for z in loaded_outputs["zone_catalog.json"]["obj"]["zones"]}
        st = zones["z_staging"]
        assert st["declared_tier"] == "staging"
        assert st["effective_tier"] == "production"

    def test_summary_invalid_refs_lists_unknown_dst_rule(self, loaded_outputs):
        """Invalid baseline references must surface the broken rule id."""
        refs = loaded_outputs["summary.json"]["obj"]["invalid_rule_refs"]
        assert refs == ["r_unknown_dst"]

    def test_summary_unsupported_kind_recorded(self, loaded_outputs):
        """Unsupported accepted kinds must appear in the summary list."""
        kinds = loaded_outputs["summary.json"]["obj"]["unsupported_incident_kinds"]
        assert kinds == ["deprecate_zone"]


class TestPrecedenceOrdering:
    """Precedence table must stay sorted and include synthetics."""

    def test_rules_sorted_by_id(self, loaded_outputs):
        """Rules array must be ascending by rule_id."""
        ids = [r["rule_id"] for r in loaded_outputs["precedence_table.json"]["obj"]["rules"]]
        assert ids == sorted(ids)

    def test_synthetics_present(self, loaded_outputs):
        """Injected and emergency synthetics must appear in the precedence table."""
        ids = {r["rule_id"] for r in loaded_outputs["precedence_table.json"]["obj"]["rules"]}
        assert "inj__e06_inject_staging_db" in ids
        assert "surf__e05_emergency_db" in ids
