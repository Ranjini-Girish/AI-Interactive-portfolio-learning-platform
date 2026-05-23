"""Behavioral tests for the oauth-client-lattice-audit task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/oauthlattice/SPEC.md``. Hash-locked fixtures
are compared against the emitted JSON files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("OCL_DATA_DIR", "/app/oauthlattice"))
AUDIT_DIR = Path(os.environ.get("OCL_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "binding_access.json",
    "client_posture.json",
    "incident_trace.json",
    "redirect_eval.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d6d91051f3eb02fd6aaf4fd13619ac5c0813952a45e76a243c92eab9ceb50bcb",
    "bindings/b_01.json": "637f2bb3ddbe4294fce4f414d14db0ba488a0f9b0a2c714a39a7ff68cb16259c",
    "bindings/b_02.json": "87c814130e9219a3959f4df28e364f78e2f4fd5acd63470d2b709baed3043a2e",
    "bindings/b_03.json": "5645a6d6507d93171fd4e9141fac7da8d74d4c9af895204e301fcbcda4f3e927",
    "bindings/b_04.json": "13e9ada91828da397bfeb904cb2c5874da560d525a58e2936acf09e74593efbd",
    "bindings/b_05.json": "5b14bac6758827a0670c242d92542494d6d07731574af327134411b348e4f583",
    "bindings/b_06.json": "87cf306fdbc75f05a6f899daa6adc19ca1567f65870bc2ddf4dea67f8480be73",
    "bindings/b_07.json": "09d56f8c4862ab0d1554b2f88cdc9eb605dc3376886afae8dc4de52d40fd6d0f",
    "bindings/b_08.json": "dd989826a70f012dc213805ff1f3356fed19ed3700ad86aba90f8c7b13e4aa0b",
    "bindings/b_09.json": "61d230360df3e6e2329caa73116d7b1e23790c0257acf7a0ce4dc26ae8092ab2",
    "bindings/b_10.json": "42f76fafcf390bf849986e26a3eb327314ad5277c58a3d40ca7f7ec971fe7415",
    "bindings/b_11.json": "323c955d0d3849058cd67162e7c773f01d3e8c9262c6da1eaf19c33a1d384cd7",
    "clients/c_alpha.json": "954ca03cb4cc5ea3a75d70f81d617457a499b1a548a1e9b31a68dafb80d8a3ba",
    "clients/c_beta.json": "2f7bee9a2439f7c2766d5ed176f1cfa1afd2db73592805347e20806b623c49e7",
    "clients/c_delta.json": "fcc48ddf2b58ff2092aaa52dbee5e87553843dfb2b4c32c560a3e8d027324cec",
    "clients/c_epsilon.json": "e43529d345ffbb55e3237008954bc4d92e1412122d67ee3fff089eacb991eaa3",
    "clients/c_eta.json": "3f7de01e2f571092be2a1e4438362c642956a9005d5d1f2265a3d81c1d31606d",
    "clients/c_gamma.json": "d9d7157894f23218b5d1790bc0009fac6670b6c98d77109fdd8dc86f71fc6b38",
    "clients/c_zeta.json": "f108103954b4a98674bbc8fee20fa510e2e9e45a6d394862478b891d3951e3b8",
    "incident_log.json": "298e9d3be1e50848bb39faa102ead012856225589fbd66cf9961d2c3dcdb7d7a",
    "policy/grant_caps.json": "7e82edb0aee3bf0be4ca9e1a0235ce27c2dc2157ca564b128802b983c998852e",
    "policy/scope_implications.json": "f76b291c0632e638ce1c983a09dbe81e5e876e135947e291658e3ff7dac75d4d",
    "policy/supported_kinds.json": "84885f31746712034a729fbb64f9b6c849c9ce4abf6f56e96e1c8c921a1415e1",
    "policy/tier_rules.json": "95392e455855cd0d00878af6152e697be04cc20cce92b989907a1f5496d29153",
    "pool_state.json": "41330d3cc6339e9d82fe49519378e33f7eae7daabf5fce698687084eba50ecfe",
    "resources/r_admin.json": "0d37ee4dd914b51dd9aa4a9ba172ec0282b8b426df2663ffab961da0881993a1",
    "resources/r_api.json": "1aa98c11d43693835850a48a46bb6d8cbdac224b1fc123785a741d1ac384da70",
    "resources/r_combo.json": "55c203a80fb65283597594fbc4c992ee8f54d1a5edf6fbd9b32e4298820b82ae",
    "resources/r_device.json": "99e6a966fb1b9398b97d1c7f2b453a5c5467036b7f93bf27f0c61c00d36adf2d",
    "resources/r_reports.json": "231520e312204b9aefef063e9b3ba7d18a762c13872322a8147937bf33c4d6b0",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "binding_access.json": "e9e5a98e14e8f97466df9a0c9bff4fd1b5e6c61e288186151d9107e00e4aab6b",
    "client_posture.json": "50823e1da31d959c2a443d0ac6d9e00e2d9ea37b5b2c8570501e409d3b7d9ff7",
    "incident_trace.json": "5db0ddfdc7941766f24893847506a75b97b0ce102bcf558c85f92ebddeb0e254",
    "redirect_eval.json": "f827b959c0683b4ceadc187572a9f4ca53e901fc881901860c8eef901b932131",
    "summary.json": "2e587c49d30735316c82de3cd9d8b32a73e79327d05521824f3491d8c9687461",
}

EXPECTED_FIELD_HASHES = {
    "binding_access.bindings": "568f964f9cb04fa8c66ec6d15e84870448e59eafb9be7adc7346e66d61a1626a",
    "client_posture.clients": "bbab3972c86a420ade94ae4a258188974fff900ab145573613dd86d7ac1584d8",
    "incident_trace.events": "0437f76798a69b47305a0be1e5ed0939d20358000d910ffad916f6e858620095",
    "redirect_eval.redirects": "65d744be5002a463b5c270e068e06ba99d9c3931c324d4e09f55ba94309c6baf",
    "summary.applied_incidents": "aa67a169b0bba217aa0aa88a65346920c84c42447c36ba5f7ea65f422c1fe5d8",
    "summary.audit_version": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.binding_count": "25d4f2a86deb5e2574bb3210b67bb24fcc4afb19f93a7b65a057daa874a9d18e",
    "summary.client_count": "10159baf262b43a92d95db59dae1f72c645127301661e0a3ce4e38b295a97c58",
    "summary.current_day": "084c799cd551dd1d8d5c5f9a5d593b2e931f5e36122ee5c793c1d08a19839cc0",
    "summary.ignored_counts": "8af1207a5833f2a8aad7f97835d139aba0881172745a749abb7147d358491e36",
    "summary.illegal_grant_clients": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.localhost_redirect_matches": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.prefix_redirect_matches": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.quarantined_clients": "9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa",
    "summary.resource_allow_total": "aa67a169b0bba217aa0aa88a65346920c84c42447c36ba5f7ea65f422c1fe5d8",
    "summary.resource_deny_total": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
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
    out: dict = {}
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
        assert p.is_file(), f"missing input fixture: oauthlattice/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture oauthlattice/{rel} was modified"


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
            "binding_access.json": {"bindings"},
            "client_posture.json": {"clients"},
            "incident_trace.json": {"events"},
            "redirect_eval.json": {"redirects"},
            "summary.json": {
                "applied_incidents",
                "audit_version",
                "binding_count",
                "client_count",
                "current_day",
                "ignored_counts",
                "illegal_grant_clients",
                "localhost_redirect_matches",
                "prefix_redirect_matches",
                "quarantined_clients",
                "resource_allow_total",
                "resource_deny_total",
            },
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


class TestIncidentTraceSemantics:
    """Trace rows must reflect acceptance, support, and the current-day clock."""

    def test_future_day_event_is_ignored(self, loaded_outputs):
        """Incidents strictly after the pool clock must not count as applied."""
        evs = loaded_outputs["incident_trace.json"]["obj"]["events"]
        fut = [e for e in evs if e["event_id"] == "e10_dup_pin"]
        assert len(fut) == 1
        assert fut[0]["resolution"] == "ignored_future_day"

    def test_unsupported_kind_is_traced(self, loaded_outputs):
        """Unsupported kinds must be labeled even when marked accepted."""
        evs = loaded_outputs["incident_trace.json"]["obj"]["events"]
        row = [e for e in evs if e["event_id"] == "e03_unsupported"][0]
        assert row["resolution"] == "ignored_unsupported_kind"


class TestRedirectSemantics:
    """Redirect modes must interact with tier overrides and localhost exceptions."""

    def _verdict(self, loaded_outputs, binding_id: str) -> str:
        for row in loaded_outputs["redirect_eval.json"]["obj"]["redirects"]:
            if row["binding_id"] == binding_id:
                return str(row["verdict"])
        raise AssertionError(f"missing redirect row {binding_id}")

    def test_tier_override_tightens_redirect_for_beta(self, loaded_outputs):
        """A tier shift to strict matching must block prefix-only callbacks."""
        assert self._verdict(loaded_outputs, "b_03") == "blocked_not_listed"

    def test_localhost_public_exception_on_bronze(self, loaded_outputs):
        """Public bronze clients may satisfy localhost-style callbacks when listed hosts miss."""
        assert self._verdict(loaded_outputs, "b_05") == "allowed_localhost_public"


class TestScopeAndResourceSemantics:
    """Scope closure and revocations must line up with resource rows."""

    def _binding(self, loaded_outputs, binding_id: str) -> dict:
        for row in loaded_outputs["binding_access.json"]["obj"]["bindings"]:
            if row["binding_id"] == binding_id:
                return row
        raise AssertionError(f"missing binding {binding_id}")

    def _client(self, loaded_outputs, client_id: str) -> dict:
        for row in loaded_outputs["client_posture.json"]["obj"]["clients"]:
            if row["client_id"] == client_id:
                return row
        raise AssertionError(f"missing client {client_id}")

    def test_implication_restores_revoked_read_scope_for_beta(self, loaded_outputs):
        """Revoked base scopes can reappear when a parent scope remains and implies them."""
        row = self._client(loaded_outputs, "c_beta")
        assert "api.read" in row["effective_scopes"]
        assert "api.write" in row["effective_scopes"]

    def test_openid_revoke_blocks_device_resource(self, loaded_outputs):
        """Removing the last base copy of a scope must persist when closure cannot restore it."""
        b = self._binding(loaded_outputs, "b_11")
        assert b["resource_access"] == "deny"
        assert b["deny_reason"] == "missing_scope"


class TestIllegalGrants:
    """Grant caps must reflect the effective tier after overrides."""

    def test_beta_device_grant_illegal_under_gold_public_caps(self, loaded_outputs):
        """Gold public grant caps must reject device grants carried from silver."""
        row = next(
            r
            for r in loaded_outputs["client_posture.json"]["obj"]["clients"]
            if r["client_id"] == "c_beta"
        )
        assert "device_code" in row["illegal_grants"]
        assert row["effective_tier"] == "gold"
