"""Verifier suite for the span-floor minimum wiring audit task."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SFM_DATA_DIR", "/app/sfm_lab"))
AUDIT_DIR = Path(os.environ.get("SFM_AUDIT_DIR", "/app/sfm_audit"))
BINARY_PATH = Path("/app/sfm_tool/sfmspan")

OUTPUT_FILES = (
    "eligible_edges.json",
    "mst_pick.json",
    "incident_trail.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d6318925f37847275852140770d42e9758267ec7af7a76c1cca595e7edffaa08",
    "anchors/day_floor.json": "aac0951f491915f9ea1a48a0a9afe9050501b64abf0c696fc4784183b13acd0d",
    "anchors/window.json": "d2f4ee65f19a34f5811e6b03be8506e7a671d5513e4c7fa156207d176caa7e7a",
    "ancillary/extra.json": "064dc8d39ef6b60aacddbe481be86cdcb1480423c3a5b45664f13cc6b91ffd73",
    "ancillary/notes.json": "a6aa5fdb199c9a85213f80418c79ff1439f72307c6b56f94a5c4a2f403c2bd73",
    "ancillary/stub.json": "ec2f80fc4b7c50c791531272a29524b9b27dd36984b5b892d7b26a07b02d821c",
    "domain_layout.json": "24a7928b8317208342273f2cabd684393a6484b214e1e28a742ff682d97cdbe2",
    "edges/e01.json": "59522c7dcf3e13b74fdb673974276d132bebf3d414bde2c0961b208116362ecb",
    "edges/e02.json": "a90843116d28e5818106f0e7010ecf92461c42158a8edad250c195930681b989",
    "edges/e03.json": "d9d300d1910b452dc0bb7b5adb7e64dbd0fcbff4d62c51e262acb349705b71db",
    "edges/e04.json": "9addb6604548a24c62846bc06257b78a0a8f335cc53ae0564b488cfe41fe089a",
    "edges/e05.json": "03033cab7cd32e5ff2f530794b7c8290985fa1173523479ee37ea18a9aaa8e59",
    "edges/e06.json": "d3b70075301af83b75dcebad21c4e9de78e985b60f7a4d307018a1f3af830b1b",
    "edges/e07.json": "d74a0d600122008d6e97d68697906b6429cfbae38e711c00e927fd70869c94c8",
    "edges/e08.json": "f23561c0778e64a9bc76f4e020914c560e9b10358403d43e0369643c35038bb1",
    "edges/e09.json": "f93687319854408fa6ebc2135c875e41ae8c0d314baf9fb2ee7650727280d471",
    "edges/e10.json": "b26101fc42737000a73409e75811948b438e26293cd4dfd087f5560d6fd2e595",
    "edges/e11.json": "18364a1dd4a9908393bdddb2b647180bcb6e4c1325df2f55d3aeec1b248204ae",
    "edges/e12.json": "e0e10c74386224ca032aacaff78be018d7ca1475a10e713819f3761989d472ce",
    "edges/e13.json": "a4776fd727dcb62f8cee2be2396724b53b0509990914d183c7b4fe30d2fefac2",
    "edges/e14.json": "a2ec5aff17d468b8b45d9a8975e7887babdbb7a44b8f2ccad28a629a0d008c25",
    "incident_log.json": "d3e65b240d6952a047ad68f8b021c4e6aea35f8feeea33fb2b6f9a42f602bb3a",
    "policy.json": "edb61519045532541a1dfef5043f188cad8c94603cc9b3ab0242dcdd530f3af0",
    "pool_state.json": "72dc34d1d40eab4aa421434c153f21eadd9053d18e097bdd9ab597b193c46c53",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "eligible_edges.json": "d0a6a1e3f0ed2fcbff4fd79bfee8965522c087a9d63764ecddaff8faf81eef98",
    "incident_trail.json": "e07ebb22fbcbf97ba92938cd8afa5a22c8cbf38588bae67c5c1085397bfc7712",
    "mst_pick.json": "1c46f5974734308efed3a0ee9cfeac9dd96e1668e7eea05ce3b37b62db0a54eb",
    "summary.json": "00b76f02409230d1639fdb92bc8b2a17fd9e0bccc818f28ed0beedb2ba4d748b",
}


EXPECTED_FIELD_HASHES = {
    "eligible_edges.edge_ids": "f80b67ebb02fcd68b81646d8975a95b7f51bd45bd8833abbb9aeeb7aa38fc512",
    "incident_trail.applied": "45f80bd3fb00adf6ad9e6d07c6c6d4f4277ffd66019321c9e3a73c5f8fde9524",
    "mst_pick.edges": "40de2f969714616e8ea0e2806488b692d1d79c737e89d6708d6508abc1ee9c8e",
    "summary.total_weight": "76a50887d8f1c2e9301755428990ad81479ee21c25b43215cf524541e0503269",
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
        ee = outputs["eligible_edges.json"]
        assert isinstance(ee, dict)
        edge_ids = _canonical(ee["edge_ids"])
        assert (
            _sha256_bytes(edge_ids.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["eligible_edges.edge_ids"]
        )

        mp = outputs["mst_pick.json"]
        assert isinstance(mp, dict)
        edges = _canonical(mp["edges"])
        assert _sha256_bytes(edges.encode("utf-8")) == EXPECTED_FIELD_HASHES["mst_pick.edges"]

        tr = outputs["incident_trail.json"]
        assert isinstance(tr, dict)
        applied = _canonical(tr["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_trail.applied"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        tw = _canonical(sm["total_weight"])
        assert (
            _sha256_bytes(tw.encode("utf-8")) == EXPECTED_FIELD_HASHES["summary.total_weight"]
        )


class TestSpanSemantics:
    """Behavioural checks aligned with the bundled scenario."""

    def test_eligible_includes_cycle_only_edge(self, outputs: dict[str, object]) -> None:
        """The eligible catalog lists the heavy bridge even when the span skips it for acyclicity."""
        ids = outputs["eligible_edges.json"]["edge_ids"]
        assert isinstance(ids, list)
        assert "e13" in ids
        picked = {e["edge_id"] for e in outputs["mst_pick.json"]["edges"]}
        assert isinstance(picked, set)
        assert "e13" not in picked

    def test_picked_weights_and_total(self, outputs: dict[str, object]) -> None:
        """Picked edges follow ascending weight with lexicographic tie breaks on identifiers."""
        edges = outputs["mst_pick.json"]["edges"]
        keys = [(int(e["w"]), str(e["edge_id"])) for e in edges]
        assert keys == sorted(keys)
        tw = int(outputs["summary.json"]["total_weight"])
        assert tw == sum(int(e["w"]) for e in edges)

    def test_summary_counts_match_trail(self, outputs: dict[str, object]) -> None:
        """Summary mirrors incident replay and component accounting."""
        sm = outputs["summary.json"]
        tr = outputs["incident_trail.json"]
        assert sm["ignored_incidents"] == tr["ignored"]
        assert sm["applied_incidents"] == len(tr["applied"])
        assert sm["component_count"] == 3
        assert sm["eligible_edge_count"] == 6
        assert sm["picked_edge_count"] == 5


class TestIncidentKinds:
    """Positive coverage for bundled incident kinds."""

    def test_raise_weight_floor_applied(self, outputs: dict[str, object]) -> None:
        """A bundled raise_weight_floor incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "raise_weight_floor" in kinds

    def test_freeze_edge_applied(self, outputs: dict[str, object]) -> None:
        """A bundled freeze_edge incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "freeze_edge" in kinds

    def test_compromise_node_applied(self, outputs: dict[str, object]) -> None:
        """A bundled compromise_node incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "compromise_node" in kinds


class TestBinaryReplay:
    """Anti-cheat replay of the emitted Go binary when present in-container."""

    @pytest.mark.skipif(not BINARY_PATH.is_file(), reason="requires built Go binary under /app/sfm_tool")
    def test_binary_replay_matches_hashes(self, tmp_path: Path) -> None:
        """Re-running the packaged binary into a fresh directory reproduces the frozen digests."""
        out_dir = tmp_path / "replay"
        out_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["SFM_DATA_DIR"] = str(DATA_DIR)
        env["SFM_AUDIT_DIR"] = str(out_dir)
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
