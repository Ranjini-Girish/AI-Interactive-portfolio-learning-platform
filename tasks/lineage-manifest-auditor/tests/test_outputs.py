"""Verifier suite for lineage-manifest-auditor."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LMA_DATA_DIR", "/app/lineage_manifests"))
AUDIT_DIR = Path(os.environ.get("LMA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "manifest_graph.json",
    "integrity_report.json",
    "policy_screen.json",
    "incident_journal.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5411be4a2f4e2e557a468934577eff829fc27ebdc6a9e3c99f7addac53ed9b72",
    "ancillary/channel_tag.json": "1e642afb04cf79516458e23cb0a33e9f5ccb7bbe5096f626cddb921932377377",
    "ancillary/ci_guard.json": "2a6fc058bf1b6df7a6778e70ca6b216880f145d8db508dad63252ef98e85d145",
    "ancillary/watermark.txt": "df5ffd7e307514204919075198cdaf966178dca812fb4dd939219c11cbe86643",
    "incident_log.json": "37dfabcb02a73d259eecb708e467999da82b9099048a58acd2f8846d87fada67",
    "manifests/m01.json": "fd2dae480bcb6e528f47a0b88a2fe4e3af4c988fbc653b3044511f0437f55886",
    "manifests/m02.json": "a6cb122905438bca8737482a238727f9453ebe18adc5a18d8da5b801048fe738",
    "manifests/m03.json": "f4b30e79c8c6c64f29eac8c56237a00a1375dcc11de8c07071129fca8618e6c6",
    "manifests/m04.json": "01b42c8f7345d5ea5bda9f7cc3e8164388f21801c51a7152e3d98d54ba17db03",
    "manifests/m05.json": "4da02d244e7264f95794bc5ff79f1dfbb672b5aba413609dc3feb519a7f8ed8f",
    "manifests/m06.json": "bc236ec05ee8c3e85fa69b3fa2cb7d184c1d61eb812637f31786bb35819ed64b",
    "manifests/m07.json": "6a09fb0117c842a020ffbf9f74254d706457b3d8bc7b4fad8e2b892c8ff222dc",
    "manifests/m08.json": "031d22525858bffc667d5ef8ee0041e0579545dd6718d3de5a858eef434e26c3",
    "manifests/m09.json": "88a432a43169765e7e75a23114ee3a10d90a1e52752dd324356a0f72a30a0777",
    "manifests/m10.json": "8ff5a677cf4e61fbe58ff1bdb87935a6fc8b4793b1b3422c565aaf57c3b6e2c9",
    "manifests/m11.json": "c2218466ef11001b654f709ec878c4ce7e91ffd6520f6dff28c8f6a0f59abd43",
    "manifests/m12.json": "572c94f5cb83ff62bbc573ec46b67434f817b5bd9a47780658727be1f4b519c1",
    "manifests/m13.json": "5530a50f4c862df15e2826a1be746bbab4fd4ea7a3b63d2f983d8accf773f5c3",
    "manifests/m14.json": "c8c5c01e0b29b48a4bc389ab5bd035d7c3851d0d5630f8741a8cc8747fc1598c",
    "manifests/m15.json": "defbda153ae67cd71daebc8faff6f36d23370aab745714a6d2941a4ac827ac09",
    "policy.json": "6ae6248b4109fa8a2948c637b699c91c60bb037c4b7b6d875f6943b8e2a4ecf8",
    "pool_state.json": "dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_journal.json": "b2a8cb51b4808cd1d83269a2b6d39be8a8b84987e1f7bedcec50f422a5c9bc70",
    "integrity_report.json": "32c382a636474b5635d21a3a2476ce3fc8f9599206c7bc177bbc059e2f16867e",
    "manifest_graph.json": "29f8e45c57ccb932ae6fcd7370e03eaa7a7c253f22aeb2bdd646f81da25b993c",
    "policy_screen.json": "577067064707c2340b42aa398554855af552291b20aec356cda597e6d341dd52",
    "summary.json": "a4700d49f033fe95fc13944dd5976d10ea3d74ada9a7da01ca89e25fc27c6caf",
}


EXPECTED_FIELD_HASHES = {
    "incident_journal.applied_events": "5bec68a10b3a193f72f0807b3f0ce9ff82e0d37afd0700e5ee8afdb9c3b79f9d",
    "integrity_report.digest_invalid": "a00551c383b9de720dd94d5ce1eee38de641bb15f6f0f77907a79bad7d0790a8",
    "manifest_graph.nodes": "c9e73496500d0f7088b9acdd9293ada37b44dc850c39720db9a845f66035541c",
    "manifest_graph.scc_lists": "c60baad25069a38d5b7de1898b540e2834e9e5b3c38ad69c3cebd9a67c4e3d63",
    "policy_screen.tier_violations": "5ef38ecf4afdbc57dabdfc01015a443dc1a0f8b557eae56c780f4c2d50e5326e",
    "summary.cycles_detected": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.nodes_in_cycle": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        mg = outputs["manifest_graph.json"]
        assert isinstance(mg, dict)
        assert (
            _sha256_bytes(_canonical(mg["nodes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["manifest_graph.nodes"]
        )
        assert (
            _sha256_bytes(_canonical(mg["scc_lists"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["manifest_graph.scc_lists"]
        )

        ir = outputs["integrity_report.json"]
        assert isinstance(ir, dict)
        assert (
            _sha256_bytes(_canonical(ir["digest_invalid"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["integrity_report.digest_invalid"]
        )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        ps = outputs["policy_screen.json"]
        assert isinstance(ps, dict)
        assert (
            _sha256_bytes(_canonical(ps["tier_violations"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["policy_screen.tier_violations"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in ("cycles_detected", "nodes_in_cycle"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestSemanticCoverage:
    """Spot-check behaviours that must remain stable for the bundled dataset."""

    def test_upstream_tail_marked_in_cycle(self, outputs: dict[str, object]) -> None:
        """Manifests feeding into a two-node SCC must inherit the in-cycle flag."""
        mg = outputs["manifest_graph.json"]
        assert isinstance(mg, dict)
        by_id = {n["manifest_id"]: n for n in mg["nodes"]}
        assert by_id["m12"]["in_cycle"] is True
        assert by_id["m13"]["in_cycle"] is True

    def test_depth_cap_clamps_m07(self, outputs: dict[str, object]) -> None:
        """Bundled depth-cap incidents tighten lineage_depth while flagging overflow."""
        mg = outputs["manifest_graph.json"]
        assert isinstance(mg, dict)
        by_id = {n["manifest_id"]: n for n in mg["nodes"]}
        row = by_id["m07"]
        assert row["raw_lineage_depth"] == 4
        assert row["lineage_depth"] == 2
        assert row["depth_cap_hit"] is True

    def test_quarantine_breaks_parent_edge_for_m14(self, outputs: dict[str, object]) -> None:
        """A quarantined ancestor clears resolved_parent for downstream children."""
        mg = outputs["manifest_graph.json"]
        assert isinstance(mg, dict)
        by_id = {n["manifest_id"]: n for n in mg["nodes"]}
        assert by_id["m14"]["resolved_parent"] is None
        assert by_id["m14"]["declared_parent"] == "m03"

    def test_scc_list_excludes_upstream_tails(self, outputs: dict[str, object]) -> None:
        """SCC lists enumerate the core cycle vertices only."""
        mg = outputs["manifest_graph.json"]
        assert isinstance(mg, dict)
        assert mg["scc_lists"] == [["m10", "m11"]]
