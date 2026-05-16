"""Behavioral tests for the attest-bundle-lattice task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/attest/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ABL_DATA_DIR", "/app/attest"))
AUDIT_DIR = Path(os.environ.get("ABL_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "artifact_catalog.json",
    "delegation_audit.json",
    "incident_trace.json",
    "signature_outcomes.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "cb74fd653858da4a10375c59e6838d60959cc87142e00fd2f07c1fe72713658c",
    "artifacts/art_admin.json": "40f7c75b5cf08093a0c3af440f46578435b85a4f4f950e004f9a61f209418e9b",
    "artifacts/art_batch.json": "c29155257d653d49eee3cb80a0d0a249c5bc1973147467b46f898b5ac267a5a1",
    "artifacts/art_cache.json": "6b3385d3e368c557de07b026f5a8910037586f2c20584a2f4cde161819b70224",
    "artifacts/art_depth.json": "1e7d02b5c876d90c665fa7564d8301b98f196dc74b69fc88e28d4e78a9925a2b",
    "artifacts/art_frontend.json": "fc094a5049e515d183140d9b8e0100ab965c7a8ad61b8440d96e46a282ff383f",
    "artifacts/art_gateway.json": "60c06fffebbb64e19372aef33121a8918c37adfc59df73e2a562e040d489f3ef",
    "artifacts/art_legacy.json": "af580b734ef351b6678e47343b398f7b8b853c2facdbe48b8e8da517c55d038c",
    "artifacts/art_proxy.json": "679aebeb34a36f2b355fd218a08c97d2b1fd1a5443e3d0389ad4ff709e9ad711",
    "artifacts/art_router.json": "124e265d9d873f44e1e79fd8db740159f68820fde08d238d58ddfbf436ff2b22",
    "artifacts/art_sidecar.json": "952e17bad1cc149905b0918ad313ff48f91b4258ca594dc07b594ff67c47c6af",
    "artifacts/art_sink.json": "f70a70449966b602e3209d510c4c420be909c43c565cc27dbecc40626eca06ce",
    "artifacts/art_twin.json": "787387c165fe17b897251987ffb49d4c20c841feec0ef5d762479f5b66f3701c",
    "artifacts/art_worker.json": "c144b6f5e033c6f5476848ca3d752921af50715c4f5eb4e5de34dc4b714f755f",
    "incident_log.json": "11b54c8e77df6f85fcf717ecd929b172e65953e6b6435dbe23fbc50026721ebf",
    "policy/emit_labels.json": "640f43a8feca047985c1eaef0965c95694707220586eaab022d4441327c97b43",
    "policy/identity_rules.json": "1a57a889d2059097bb3af12563c1738bf16c320dfe26c868e016e0b4c9c1d6a4",
    "policy/predicate_gates.json": "56651328e00a2f03b6052e33f195a632a074f0722547d5f9ba1169df1d1f6e3e",
    "policy/revision_stamp.json": "565ca0e8634b48c7940c4adfa9a69f9689df15de68be1a99fe3f3ed25318ac93",
    "policy/trust_graph.json": "0ef148c07e542f764575c4d707429d805446fc7d92ad26486ae68b480d4e7e20",
    "pool_state.json": "d68ad1e85b14639e77d54a12506933682fb1807a8a1a3ce0150562117b4dd08a",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "artifact_catalog.json": "cd61a8eac5c66624a5246c4b0a8f16268bc00ba574603e811e41515fe2f5f2c7",
    "delegation_audit.json": "00f3b7d075e9de45fd748aadbc530902776817da329a2e7b78a2dc89a69908b9",
    "incident_trace.json": "33b42dabbaf2c0003c8946fa1e33393fd6fb795acb6dceee446c09c9ceab6334",
    "signature_outcomes.json": "342f117821eee84bc38d4507b7864e62ec7dfcc29cc1777dce330cf2cd29ba35",
    "summary.json": "6e62267fa15e7ab12529612d7b2cd5e4c88c848103163caf62df5f9fda1ff6d7",
}

EXPECTED_FIELD_HASHES = {
    "artifact_catalog.json.artifacts": "977af755c3c4a00fd0b9ecc577b3dd3122a670b1be2582ae15d49cf8227ca16d",
    "delegation_audit.json.keys": "31dd8be6278f5ac3160420e802c377085ad54151a37f327d50a500ff622d5256",
    "incident_trace.json.events": "8460fad545d3e212aff72d1a5019c4969d66075f95cd535d2c55d95f916434df",
    "signature_outcomes.json.signatures": "844318130e251dd22e0655600128034017306a76ee98f1fea864ea3ddd2cb3f7",
    "summary.json.artifact_count": "1a252402972f6057fa53cc172b52b9ffca698e18311facd0f3b06ecaaef79e17",
    "summary.json.audit_version": "0a087e5793e16e6837bd276ff0980c476348e1300420d289e667f5da1bbeffd1",
    "summary.json.current_day": "238903180cc104ec2c5d8b3f20c5bc61b389ec0a967df8cc208cdc7cd454174f",
    "summary.json.ignored_incidents": "7de1555df0c2700329e815b93b32c571c3ea54dc967b89e81ab73b9972b72d1d",
    "summary.json.quarantined_artifacts": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.json.signature_rows": "e6c21e8d260fe71882debdb339d2402a2ca7648529bc2303f48649bce0380017",
    "summary.json.unsupported_incident_kinds": "2420aaa4f7491453736bed33a9d83001e44d3fc7daf0cdba70d088037ae7e535",
    "summary.json.verdict_counts": "1130bb8bf34e631ee955b974eab32d85293e0f2392b265befa28ead3fff5229f",
}


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
        assert p.is_file(), f"missing input fixture: attest/{rel}"
        if p.suffix == ".json":
            obj = json.loads(p.read_text(encoding="utf-8"))
            actual = _canonical_sha256(obj)
        else:
            actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, f"input fixture attest/{rel} was modified"


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
            "artifact_catalog.json": {"artifacts"},
            "delegation_audit.json": {"keys"},
            "incident_trace.json": {"events"},
            "signature_outcomes.json": {"signatures"},
            "summary.json": {
                "artifact_count",
                "audit_version",
                "current_day",
                "ignored_incidents",
                "quarantined_artifacts",
                "signature_rows",
                "unsupported_incident_kinds",
                "verdict_counts",
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
        marker = ".json."
        assert marker in field, f"bad field key: {field}"
        head, tail = field.split(marker, 1)
        file_name = f"{head}.json"
        obj = loaded_outputs[file_name]["obj"]
        cur = obj
        for part in tail.split("."):
            cur = cur[part]
        assert _canonical_sha256(cur) == expected, f"field {field} drifted"


class TestCatalogSemantics:
    """Spot-check compound delegation, quarantine, and ranking behaviour."""

    def _row(self, loaded_outputs, aid: str) -> dict:
        for r in loaded_outputs["artifact_catalog.json"]["obj"]["artifacts"]:
            if r["artifact_id"] == aid:
                return r
        raise AssertionError(f"missing artifact {aid}")

    def _sig(self, loaded_outputs, aid: str, sid: str) -> dict:
        for r in loaded_outputs["signature_outcomes.json"]["obj"]["signatures"]:
            if r["artifact_id"] == aid and r["signature_id"] == sid:
                return r
        raise AssertionError(f"missing signature {aid}/{sid}")

    def test_twin_prefers_lower_policy_rank(self, loaded_outputs):
        """When two signatures verify, the winner uses the smallest policy_rank."""
        row = self._row(loaded_outputs, "art_twin")
        assert row["final_verdict"] == "verified_ok"
        assert row["winning_signature_id"] == "sig_twin_low"

    def test_admin_keeps_verified_despite_banned_sibling(self, loaded_outputs):
        """A banned sibling signature must not remove a separate verified path."""
        row = self._row(loaded_outputs, "art_admin")
        assert row["final_verdict"] == "verified_ok"
        assert row["winning_signature_id"] == "sig_admin_main"
        assert self._sig(loaded_outputs, "art_admin", "sig_admin_extra")["outcome"] == "ban_hit"

    def test_proxy_quarantine_short_circuits_signatures(self, loaded_outputs):
        """Quarantined artifacts must classify every signature as quarantine_artifact."""
        row = self._row(loaded_outputs, "art_proxy")
        assert row["quarantined"] is True
        assert row["final_verdict"] == "quarantine_artifact"
        for sid in ("sig_proxy_a", "sig_proxy_b"):
            assert self._sig(loaded_outputs, "art_proxy", sid)["outcome"] == "quarantine_artifact"

    def test_worker_revoked_via_parent_chain(self, loaded_outputs):
        """A revoked ancestor on the delegation chain must surface as revoked_key."""
        row = self._row(loaded_outputs, "art_worker")
        assert row["final_verdict"] == "revoked_key"

    def test_batch_identity_blocked(self, loaded_outputs):
        """Production identity rules must reject unknown allowlisted emails."""
        row = self._row(loaded_outputs, "art_batch")
        assert row["final_verdict"] == "identity_blocked"

    def test_sink_final_ban_hit(self, loaded_outputs):
        """Ban patterns must be able to drive the artifact-level final verdict."""
        row = self._row(loaded_outputs, "art_sink")
        assert row["final_verdict"] == "ban_hit"

    def test_depth_key_reports_depth_exceeded(self, loaded_outputs):
        """Delegation depth caps must surface on the catalog for the deep-chain key."""
        row = self._row(loaded_outputs, "art_depth")
        assert row["final_verdict"] == "depth_exceeded"

    def test_legacy_reports_delegation_cycle(self, loaded_outputs):
        """Cyclic delegation graphs must surface as delegation_cycle."""
        row = self._row(loaded_outputs, "art_legacy")
        assert row["final_verdict"] == "delegation_cycle"

    def test_summary_lists_unsupported_kind(self, loaded_outputs):
        """Unsupported incident kinds must be collected when accepted and in-window."""
        kinds = loaded_outputs["summary.json"]["obj"]["unsupported_incident_kinds"]
        assert kinds == ["freeze_predicate"]


class TestDelegationAudit:
    """Delegation audit rows must expose anchors and the deep-chain failure."""

    def test_root_is_anchor_with_zero_edges(self, loaded_outputs):
        """Anchor keys must report anchor_ok with zero chain edges."""
        rows = {r["key_id"]: r for r in loaded_outputs["delegation_audit.json"]["obj"]["keys"]}
        root = rows["k_root"]
        assert root["delegation_status"] == "anchor_ok"
        assert root["chain_edges"] == 0
        assert root["effective_parent_key_id"] is None

    def test_d1_reports_depth_exceeded(self, loaded_outputs):
        """The long-chain key must report depth_exceeded in the delegation audit."""
        rows = {r["key_id"]: r for r in loaded_outputs["delegation_audit.json"]["obj"]["keys"]}
        d1 = rows["k_d1"]
        assert d1["delegation_status"] == "depth_exceeded"


class TestIncidentTrace:
    """Incident trace must preserve ordering and eligibility labelling."""

    def test_trace_preserves_original_order(self, loaded_outputs):
        """Events must stay in the same order as the incident log."""
        log = json.loads((DATA_DIR / "incident_log.json").read_text(encoding="utf-8"))["incidents"]
        events = loaded_outputs["incident_trace.json"]["obj"]["events"]
        assert [e["event_id"] for e in events] == [str(i.get("event_id", "")) for i in log]

    def test_unsupported_incident_marked(self, loaded_outputs):
        """Unsupported kinds must be flagged while remaining in original order."""
        ev = next(
            e
            for e in loaded_outputs["incident_trace.json"]["obj"]["events"]
            if e["event_id"] == "e_unknown_kind"
        )
        assert ev["ignored_reason"] == "unsupported_kind"
        assert ev["applied"] is False
