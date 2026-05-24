"""Verifier suite for vfs-shadow-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("VFS_DATA_DIR", "/app/vfs_shadow"))
AUDIT_DIR = Path(os.environ.get("VFS_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "cap_violations.json",
    "freeze_state.json",
    "inode_report.json",
    "merge_graph.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "8a1ff55834d94ade265ed46b495ce9def28cec4f182fce600802ee497585e57b",
    "incidents/i01.json": "e6fbb915aa8ecce4cadc020bfab9b528b0ab4d8dedc5fcf3ff1a45d169211d14",
    "incidents/i02.json": "e7b4d79d9081b9192e74087e7d9916d438bd8c8a77d9db55654739ed3ff6cc72",
    "incidents/i03.json": "9070e9c3e166ed440cfd60806210c3ddcf32fe87d5d0544e2b501cca4fb7e5e7",
    "incidents/i04.json": "74f1efc1aebdbfa8448d60e9b210c07e58f0ef0aff703821b7dfd831e4fff9e3",
    "incidents/i05.json": "a12d9d3dafed938af51a1feb4fb5019de49491bedfe2a5276f68701ad37f8622",
    "inodes/part_a.json": "e0d9eeafb95630b2bd493c8b32281bd5043e3095956613727534b5fe0217fb3e",
    "inodes/part_b.json": "8b7c977e2f37fcce5c22b7a97769f46460278b7adc1fc607eece931e643ae364",
    "inodes/part_c.json": "c2f1d87e3fffe97446b7120d5c07e59c3859f6863b1bcf63ac68b1171060c857",
    "inodes/part_d.json": "b9bda7ebd72c96e3cab3f1f3fcf271b0da1cb743e37c9a7e2ed97d36cb04a906",
    "inodes/part_e.json": "0f59028030c71a9004e7a3ca34e3d6b4f88496037cd24145c0cf576d2edab075",
    "mounts/m01.json": "4d533028bb5be6e8cdd1bd152e7384494c6c7872383474195356d0ee2a110a1c",
    "mounts/m02.json": "e96e48d3a969a791593c96ad0d0d196bc7c43debb30baac108cd4be966a220db",
    "mounts/m03.json": "78eabb19ad241b4c56e0c711ce0d95689ec0dc516ccb06a0a816ed3b689dd18b",
    "mounts/m04.json": "19b664b34ecd6f171062a6577d2c7fdfee7cc636ed786865a55d965cc7d6971f",
    "mounts/m05.json": "2b0df9d6a68033e540e11cfab3f070d5aee920ae315c7c858d1820e81a8ec128",
    "mounts/m06.json": "adc8fdd72f9e12ec6b455a0c775d1bb91838daf7c6be8df835bd7309f43e1212",
    "mounts/m07.json": "365c8cf218e1959ebaa8f1df3545c2dbda1a9d4b1fe550fcf0d8409a9ec7eec3",
    "mounts/m08.json": "2236fd39e5b4b3a3c3b9a65edcb5799bc4e64ed2c237dbaa7984b7f1fbaf7f25",
    "mounts/m09.json": "f97f131f25cddddfdef2f3ddff690f24cb9f2617c4e14443f2c3955d62366237",
    "mounts/m10.json": "14d24cce04560c314d06f81a31eb0ad5c3efc9752693aaad40e0c3b06dab1783",
    "mounts/m11.json": "3d95e536e2510f9f6e2e7af3c93da4af8114150755353f8fffc34fb8dcf53cc4",
    "mounts/m12.json": "5d17d0de95e0204d9a8c4b38947e3b8009e1c60d824b39f7b7a48963612dd561",
    "mounts/m13.json": "4cb07f4cefe3d35b255d6cf6b1459475abf4142f079c0e33f01de5f0a1ae4686",
    "mounts/m14.json": "1d34124e2bdad6e9d0283b6bb2b1e0092bd8670914da911a6b6670bf49083235",
    "pool.json": "ca54a18984ddf4ff6454ea322d8dbae4681c9c772e7e03c03493884deb788288",
    "snapshots/s01.json": "0f376b773e09ba760795e5d1b06c0087de2e7602eab60271ece019a6d4095d6a",
    "snapshots/s02.json": "ccc4e1da9198194dc5f39a0b5d5570fe9e0adca9ac7f231d75dab0fac433378f",
    "snapshots/s03.json": "c5284f34baa7ebac6db40c2fc5c5424c6369f4d257c90266ede442666aa0f7fa",
    "snapshots/s04.json": "55037ff573486919e08d873849a7175c65f8820d3f7c3afdafb499d8a14c2f30",
    "snapshots/s05.json": "8e381db4925a53aa1fefde23a21446a4b137384340242428141131381012abec",
    "snapshots/s06.json": "963c5019bba6cef8c9a2d92ed8ff8999826642804278e7e1cfb8c175c3d08650",
    "snapshots/s07.json": "39e7839a5c2fca002a474d7dc10f2ac189166dc7b54066b25d439b0760d623c6",
    "tiers.json": "efa5514e43b91cc6d600c9f194bb4f6597df5b5eb88df2874bcb5615c6de8afc",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cap_violations.json": "39557a7843adb475e1787e2f7e7d80ec72d0e40e23e8e192590b3fb235091fed",
    "freeze_state.json": "97a69bd9598ac4586e6e19e7161d71cf161c16372efbae89db3732d07b8c149e",
    "inode_report.json": "e50f6986219a4b2cd88e357fac7a8acc776ae358ba4ad0b32a587a36a19781ac",
    "merge_graph.json": "9e3409a4aba4954c2144a1301e2b8b021d8b1a05f21143bcfeeacc34ae2b704a",
    "summary.json": "1798633f8ee18eab6efaa47b3ea48bcb9db79db4973ca0e66c1db56b103cf442",
}


EXPECTED_FIELD_HASHES = {
    "cap_violations.violations": "005eed1ef6a6582ac8e7560eeed138676fe9b2f2f99fce6cf41f8a611ede6353",
    "freeze_state.mounts": "0c86f709ed83e3c8929441dafa9e3596f55509e229531b45d189af037e34a52a",
    "inode_report.rows": "e52ebfa4f016e3268f394738babf128f459f9e6bb77e45837f188dc7f21d1d86",
    "merge_graph.nodes": "eb0f47a0eacccc639ba79933d944110c1428fb43a854e354ccd2f62f191aad1e",
    "summary.max_merged_total": "cc89202ca73256893f1aed3a1be2fa41dfc229de16250ecb79519dc150c6080a",
    "summary.pool_day_index": "b7a56873cd771f2c446d369b649430b65a756ba278ff97ec81bb6f55b2e73569",
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
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert (
            _sha256_bytes(_canonical(summary["pool_day_index"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.pool_day_index"]
        )
        assert (
            _sha256_bytes(_canonical(summary["max_merged_total"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.max_merged_total"]
        )

        merge_graph = outputs["merge_graph.json"]
        assert isinstance(merge_graph, dict)
        assert (
            _sha256_bytes(_canonical(merge_graph["nodes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["merge_graph.nodes"]
        )

        cap = outputs["cap_violations.json"]
        assert isinstance(cap, dict)
        assert (
            _sha256_bytes(_canonical(cap["violations"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["cap_violations.violations"]
        )

        inode = outputs["inode_report.json"]
        assert isinstance(inode, dict)
        assert (
            _sha256_bytes(_canonical(inode["rows"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["inode_report.rows"]
        )

        freeze = outputs["freeze_state.json"]
        assert isinstance(freeze, dict)
        assert (
            _sha256_bytes(_canonical(freeze["mounts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["freeze_state.mounts"]
        )


class TestSemanticAnchors:
    """Spot-check documented invariants that interact across phases."""

    def test_summary_counts_align_with_graph(self, outputs: dict[str, object]) -> None:
        """Summary mount and inode counts must match graph inputs."""
        summary = outputs["summary.json"]
        merge_graph = outputs["merge_graph.json"]
        inode_report = outputs["inode_report.json"]
        freeze_state = outputs["freeze_state.json"]
        assert isinstance(summary, dict)
        assert isinstance(merge_graph, dict)
        assert isinstance(inode_report, dict)
        assert isinstance(freeze_state, dict)
        nodes = merge_graph["nodes"]
        rows = inode_report["rows"]
        mounts = freeze_state["mounts"]
        assert isinstance(nodes, list)
        assert isinstance(rows, list)
        assert isinstance(mounts, list)
        assert summary["mount_count"] == len(nodes)
        assert summary["inode_row_count"] == len(rows)
        freeze_true = sum(1 for m in mounts if m["freeze_merge"])
        assert summary["freeze_merge_mount_count"] == freeze_true

    def test_pool_day_index_matches_fixture_epoch(self, outputs: dict[str, object]) -> None:
        """Pool day index must follow the anchor math on the frozen epoch."""
        pool = _load_json(DATA_DIR / "pool.json")
        assert isinstance(pool, dict)
        delta = int(pool["as_of_epoch"]) - int(pool["anchor_epoch"])
        day_len = int(pool["day_length_sec"])
        expected = 0 if delta <= 0 else delta // day_len
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert int(summary["pool_day_index"]) == expected

    def test_mount_m01_exceeds_gold_hard_cap(self, outputs: dict[str, object]) -> None:
        """The root mount must record a hard-cap breach for the gold tier."""
        cap = outputs["cap_violations.json"]
        assert isinstance(cap, dict)
        v = cap["violations"]
        assert isinstance(v, list)
        assert any(x.get("mount_id") == "m01" for x in v if isinstance(x, dict))
