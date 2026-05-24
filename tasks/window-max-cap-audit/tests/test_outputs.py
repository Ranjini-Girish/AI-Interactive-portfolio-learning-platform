"""Verifier suite for the window maximum with cap audit task."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WMC_DATA_DIR", "/app/wmc_lab"))
AUDIT_DIR = Path(os.environ.get("WMC_AUDIT_DIR", "/app/wmc_audit"))
BINARY_PATH = Path("/app/wmc_tool/wmcap")

OUTPUT_FILES = (
    "dilated_series.json",
    "window_trace.json",
    "incident_trail.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "35c2619a66ae4111fe0d2a632a421650d0f2bfb56df1d1791138f780d8dc5bee",
    "anchors/day_floor.json": "aac0951f491915f9ea1a48a0a9afe9050501b64abf0c696fc4784183b13acd0d",
    "anchors/window.json": "085b83f8eef169c10690fdf28f715094b5426e43212e8d84dede7f12da306d41",
    "ancillary/extra.json": "064dc8d39ef6b60aacddbe481be86cdcb1480423c3a5b45664f13cc6b91ffd73",
    "ancillary/meta.json": "b9170c244e808c204ede712eb892821c381838812272583ab7f7aab87defec65",
    "ancillary/notes.json": "a6aa5fdb199c9a85213f80418c79ff1439f72307c6b56f94a5c4a2f403c2bd73",
    "ancillary/stub.json": "ec2f80fc4b7c50c791531272a29524b9b27dd36984b5b892d7b26a07b02d821c",
    "domain_layout.json": "17f65f2ef005ce32fb96caa57ebd6c93c18c8d03b1e1d386ed2dfb3ccb772851",
    "incident_log.json": "c6fbedcc802c6cb2bd09e5aa401cb79d2515ecebea8a831209ec32db81764c8d",
    "parts/p01.json": "b9bd97252901e7509b3ced44561bd38f90f762f5d12bac76af7c129337ad7a46",
    "parts/p02.json": "4170b07a7b11ae4413597e56fc4231726c843da2f6bca0eb24d5af530d3e9795",
    "parts/p03.json": "3e4c3f8bf0dc314ab03b621ffed3f64f9e50934c5ff38192c13b30e13fd1f78d",
    "parts/p04.json": "ae0113abf498b14f0e9a541e16a55cd351f9ec21c57cb75dd484279806cc756a",
    "parts/p05.json": "e30f42ce6128607d7ba1aa6c37fcb66b9238157bf7e60ab1b641410440458694",
    "parts/p06.json": "284e3721f825aba73d38883a0448afdfa2637e9b507cd326259254b31d3903d9",
    "parts/p07.json": "bf2686cc554a75ba6df73a9bd7c0e19f075db1c89b0cb17fa50d706ea38c6807",
    "parts/p08.json": "4ff45398bb9b2cbf297fb691322f088308377d96fa67930026f275166133d8b7",
    "parts/p09.json": "168af357fdf952a017cadc43b7cb9633f8591171f60b07f95a8e2cfbd921ba26",
    "parts/p10.json": "9b5971713ccb0864521c9719fbfcc67d0eb34a1a4a253ceeaa3e80798cb636be",
    "parts/p11.json": "12e31c06e470dda0a5d500e74e939184e516b6900f24f3d93d491bfa728d5e43",
    "parts/p12.json": "7bf304d44942e27b83bb0910bed390f212275694e2a68e191dc4e7ffb8ed6764",
    "policy.json": "b50c1f0c3341efbef78ff9774bec75e648a675327e9f18786f2d3c8ececa2d52",
    "pool_state.json": "4af11e96ce9580726d7b118da7ee8f65f3d72b23385f890db23992c64d6cb149",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dilated_series.json": "3944be1fa2c2bcdb05640b1973c94ddfa39f200a505aba9ec8cbbacac0b4301e",
    "incident_trail.json": "9f7d2f7a479cad3afb3079cf50a3fad8b6f4bf031e1ccecb06bfb2a9e2769e6c",
    "summary.json": "b297f36cb70cf774e6fe6cdbce5b7c5d2c9bf2c9209555b8106a7fcbe31a917b",
    "window_trace.json": "1ab84d19f1200f2af2298daf1ad1be49f44988867648a11602820cb174652fe3",
}


EXPECTED_FIELD_HASHES = {
    "dilated_series.values": "2e95403f60a51426e7e7691a311efb227863d5dcdd2ed48a26c481ec73801137",
    "incident_trail.applied": "2868164b6832b810c4ef7e53cf951f5eb7a62e573154474a027f216c919f2257",
    "summary.cap_final": "02d20bbd7e394ad5999a4cebabac9619732c343a4cac99470c03e23ba2bdc2bc",
    "window_trace.windows": "a87852c79bd2ca58923ce8aea2e37d3b24c6b1128c6512daf76c90886eaf6a81",
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
        ds = outputs["dilated_series.json"]
        assert isinstance(ds, dict)
        values = _canonical(ds["values"])
        assert (
            _sha256_bytes(values.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dilated_series.values"]
        )

        wt = outputs["window_trace.json"]
        assert isinstance(wt, dict)
        windows = _canonical(wt["windows"])
        assert (
            _sha256_bytes(windows.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["window_trace.windows"]
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
        cf = _canonical(sm["cap_final"])
        assert (
            _sha256_bytes(cf.encode("utf-8")) == EXPECTED_FIELD_HASHES["summary.cap_final"]
        )


class TestWindowSemantics:
    """Behavioural checks aligned with the bundled scenario."""

    def test_cap_and_length(self, outputs: dict[str, object]) -> None:
        """The final cap reflects the bump incident and geometry matches the window width."""
        sm = outputs["summary.json"]
        assert int(sm["cap_final"]) == 55
        assert int(sm["window_used"]) == 4
        assert int(sm["total_input_len"]) == 36
        assert int(sm["output_len"]) == 33

    def test_trace_matches_series(self, outputs: dict[str, object]) -> None:
        """Window trace rows align with the capped series order."""
        series = outputs["dilated_series.json"]["values"]
        wins = outputs["window_trace.json"]["windows"]
        assert isinstance(series, list) and isinstance(wins, list)
        assert len(series) == len(wins)
        for i, row in enumerate(wins):
            assert int(row["start"]) == i
            assert int(row["capped"]) == int(series[i])
            assert int(row["raw_max"]) >= int(row["capped"])

    def test_summary_matches_trail(self, outputs: dict[str, object]) -> None:
        """Summary mirrors incident replay counts."""
        sm = outputs["summary.json"]
        tr = outputs["incident_trail.json"]
        assert sm["ignored_incidents"] == tr["ignored"]
        assert sm["applied_incidents"] == len(tr["applied"])


class TestIncidentKinds:
    """Positive coverage for bundled incident kinds."""

    def test_bump_cap_applied(self, outputs: dict[str, object]) -> None:
        """A bundled bump_cap incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "bump_cap" in kinds

    def test_zero_index_applied(self, outputs: dict[str, object]) -> None:
        """A bundled zero_index incident appears in the applied trail."""
        kinds = {e["kind"] for e in outputs["incident_trail.json"]["applied"]}
        assert "zero_index" in kinds


class TestBinaryReplay:
    """Anti-cheat replay of the emitted Go binary when present in-container."""

    @pytest.mark.skipif(not BINARY_PATH.is_file(), reason="requires built Go binary under /app/wmc_tool")
    def test_binary_replay_matches_hashes(self, tmp_path: Path) -> None:
        """Re-running the packaged binary into a fresh directory reproduces the frozen digests."""
        out_dir = tmp_path / "replay"
        out_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["WMC_DATA_DIR"] = str(DATA_DIR)
        env["WMC_AUDIT_DIR"] = str(out_dir)
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
