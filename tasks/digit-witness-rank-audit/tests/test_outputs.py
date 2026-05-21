"""Verifier suite for the digit witness rank audit task."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("DWR_DATA_DIR", "/app/dwr_lab"))
AUDIT_DIR = Path(os.environ.get("DWR_AUDIT_DIR", "/app/dwr_audit"))
BINARY_PATH = Path("/app/dwr_tool/dwrank")

OUTPUT_FILES = (
    "lane_witnesses.json",
    "merged_rank.json",
    "incident_trail.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "02d0e89ab1f95f983b26e7d6a06447c093929c7434ad64e20b75f12f4dfe5992",
    "anchors/day_floor.json": "aac0951f491915f9ea1a48a0a9afe9050501b64abf0c696fc4784183b13acd0d",
    "anchors/window.json": "0e86784093ea43e6138a60691dfcaf5fa7dd40233ac3f4b2fd666e3427fc9258",
    "ancillary/extra.json": "064dc8d39ef6b60aacddbe481be86cdcb1480423c3a5b45664f13cc6b91ffd73",
    "ancillary/meta.json": "d5e8277ba91a9f693691e95d9e369e87571f7bfada99719ad27c50ecafe42503",
    "ancillary/notes.json": "a6aa5fdb199c9a85213f80418c79ff1439f72307c6b56f94a5c4a2f403c2bd73",
    "ancillary/stub.json": "ec2f80fc4b7c50c791531272a29524b9b27dd36984b5b892d7b26a07b02d821c",
    "domain_layout.json": "d7e55596ee8312994e98800bf39b5218c24b2357b5081d1b97c3b4e47ee4948d",
    "incident_log.json": "eefcabc54a6a14d52ae8de7e40b3a86007274805891dae9b0e0a462549fd8f34",
    "lanes/l01.json": "ee8ec24e91dd9fa312450d7f073b0ccc85c2886a2b5b0090df98803424eba7d0",
    "lanes/l02.json": "9aad9ba7e9b0eadf15d4c9404b00b8107fdbe97d3f5c3f5f7a1c6f13f08d0dce",
    "lanes/l03.json": "8eff0fc66316be70e59249c1e9e7a077eddd10893c4a1614570833522207789b",
    "lanes/l04.json": "fec2057fdc3828a635a181142a38bec84acd1d08a908f07a28704905e349d858",
    "lanes/l05.json": "42468653218070234ddbdd2f8f913e12c18dada9d6c5d55bb85b10467d3de0cd",
    "lanes/l06.json": "6db66ace913eba581583957d82e1fd00f1c82e66fb72d2fb4c5a625c7599d395",
    "lanes/l07.json": "8e2ff1ff3c54cdbc78e581267ee921bdce5b245e1c22e027aab31e9edc188f3b",
    "lanes/l08.json": "8449229efd65d8e7ec72594fc976cb116cdee165f35cafa5d510e2979e3328c2",
    "lanes/l09.json": "2bdea3454fd638026b1e4c59df913eed72e62f55cd52133655bf3b6080c841e8",
    "policy.json": "abd91275dc913447d7bf75c56087611c0436811abddbba4636be5bd498f126c1",
    "pool_state.json": "6b1a8b792e628f77879cab77d722804e10d1e9ea1cbcb1de39f08fe43a23b75c",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_trail.json": "3af6e66f78ecced4ffc8fa06217710e3d2ebc8a6bc29a068b0f71a829c24e1e1",
    "lane_witnesses.json": "b4137d0dd8b83aaef1c3a5c27ec5de818e0658b2a2a94e24bd9de624488775c2",
    "merged_rank.json": "e393488c621a7c97e4b6a1a0d56c14f2e784568a66821143f7f97d8bc2f1cae9",
    "summary.json": "454ffdec542b1d1b92decb8ab4a1495cfb822533b8d0c7a1e49f907482c136dd",
}


EXPECTED_FIELD_HASHES = {
    "incident_trail.applied": "c6d48f7aee71ad975081e7e1582f9d90bc54cc6378fa592d6d85527c95c979d2",
    "lane_witnesses.lanes": "24a6fafe638f90c2a626a6c6fb96cff6cb6a84245511a5eb5c7799ed92c12a4d",
    "merged_rank.witnesses": "e949be7722bacd4b3184fbd9b3da8b347f55d262f19d21921e3e5d31f470ea9d",
    "summary.radix_final": "b17ef6d19c7a5b1ee83b907c595526dcb1eb06db8227d650d5dda0a9f4ce8cd9",
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

    def test_nested_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested collections remain stable under canonical serialisation."""
        lw = outputs["lane_witnesses.json"]
        assert isinstance(lw, dict)
        lanes = _canonical(lw["lanes"])
        assert (
            _sha256_bytes(lanes.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["lane_witnesses.lanes"]
        )

        mr = outputs["merged_rank.json"]
        assert isinstance(mr, dict)
        witnesses = _canonical(mr["witnesses"])
        assert (
            _sha256_bytes(witnesses.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["merged_rank.witnesses"]
        )

        tr = outputs["incident_trail.json"]
        assert isinstance(tr, dict)
        applied = _canonical(tr["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_trail.applied"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        rf = _canonical(sm["radix_final"])
        assert (
            _sha256_bytes(rf.encode("utf-8")) == EXPECTED_FIELD_HASHES["summary.radix_final"]
        )


class TestRankingSemantics:
    """Behavioural checks aligned with the bundled scenario."""

    def test_final_radix_matches_bump(self, outputs: dict[str, object]) -> None:
        """The final working radix reflects the bundled bump sequence."""
        assert int(outputs["summary.json"]["radix_final"]) == 16

    def test_suppressed_lane_absent_from_witness_blocks(self, outputs: dict[str, object]) -> None:
        """Suppressed lanes do not appear in the per-lane witness table."""
        lanes = outputs["lane_witnesses.json"]["lanes"]
        assert isinstance(lanes, list)
        ids = {b["lane_id"] for b in lanes}
        assert "l03" not in ids

    def test_summary_counts(self, outputs: dict[str, object]) -> None:
        """Summary mirrors suppression, merged rows, and incident replay."""
        sm = outputs["summary.json"]
        tr = outputs["incident_trail.json"]
        assert sm["ignored_incidents"] == tr["ignored"]
        assert sm["applied_incidents"] == len(tr["applied"])
        assert sm["suppressed_lane_count"] == 1
        assert sm["merged_witness_count"] == 16
        assert sm["total_readings"] == 26


class TestIncidentKinds:
    """Positive coverage for bundled incident kinds."""

    def test_bump_radix_applied(self, outputs: dict[str, object]) -> None:
        """A bundled bump_radix incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "bump_radix" in kinds

    def test_suppress_lane_applied(self, outputs: dict[str, object]) -> None:
        """A bundled suppress_lane incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "suppress_lane" in kinds


class TestBinaryReplay:
    """Anti-cheat replay of the emitted Go binary when present in-container."""

    @pytest.mark.skipif(not BINARY_PATH.is_file(), reason="requires built Go binary under /app/dwr_tool")
    def test_binary_replay_matches_hashes(self, tmp_path: Path) -> None:
        """Re-running the packaged binary into a fresh directory reproduces the frozen digests."""
        out_dir = tmp_path / "replay"
        out_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["DWR_DATA_DIR"] = str(DATA_DIR)
        env["DWR_AUDIT_DIR"] = str(out_dir)
        subprocess.run([str(BINARY_PATH)], check=True, env=env)
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            payload = _load_json(out_dir / name)
            digest = _sha256_bytes(_canonical(payload).encode("utf-8"))
            assert digest == expected, f"binary drift on {name}"


class TestDataDirUntouched:
    """Ensure the verifier run did not mutate read-only inputs."""

    def test_data_dir_unchanged(self) -> None:
        """Digest map for the read-only tree remains stable after verification."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"input drift detected at {rel}"
