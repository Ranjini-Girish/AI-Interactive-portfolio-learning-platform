"""Verifier suite for granite-tier-cap-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("QUOTA_DATA_DIR", "/app/quota_lab"))
AUDIT_DIR = Path(os.environ.get("QUOTA_AUDIT_DIR", "/app/audit"))
OUTPUT_FILES = ("allocations.json", "summary.json")

EXPECTED_INPUT_HASHES = {
    "aux-meta.json": "0bbe992a67bd6ec9f0e4804574c810e737cd1c067306b2ad3256cf523ccc3a68",
    "events.json": "ef61acdf2eb68e4f6a57a7551116cf48471f0978777c11c94eab9aed6f8cf16e",
    "items/item-01.json": "cd5f4a819bc32d842bdbdec5a644d86066c066d433f0bfe5bb565a4aaddf809f",
    "items/item-02.json": "523953e8c681b601a0a1371d5ed6253497bf0ee30809824399a68d348d97ed5c",
    "items/item-03.json": "52f31c84379295e0230c165803e66c4b2662203b0bbfbe502cb526be014edc7a",
    "items/item-04.json": "50a0286bc252ba98b5fec5868c47040b4040c74ab2b1ccaf3aad2fa393a14c8f",
    "items/item-05.json": "9a677ca449fbd6f4f001acbfb1cd086c930c09d5496ae353bf550d387e3fdad4",
    "items/item-06.json": "796d7af2f0a50eb0f70fec9abec398b7915eea2aa94ff0c79cb34f619d4ad49f",
    "items/item-07.json": "e3d76c87999cac625197cf5c342d1e3b9199372a0a3b7073f090320160aba4e1",
    "items/item-08.json": "c016ae3c2e77a116de133ea2a53d358e57f922002892b57d5973a7292827561f",
    "items/item-09.json": "12daa5297e90f850aa3ade2ef7e85ae78e13885ce10ba905771832acfc10fe9c",
    "items/item-10.json": "7886dea03120b6c0ef71c7029b97feccfeaeac3fceedeb6b7712fa0ad92b8305",
    "items/item-11.json": "1d6192fa6ac06f87d7251c6bc8a3bcab4f732cd1dfee4994b5332b8bd3c73724",
    "items/item-12.json": "988bd09bfda2e305a75cf2970ae6fe15851aef0424a70e7273cb91d4723280e2",
    "items/item-13.json": "491479a1cdf6e172d75dd37509d64eb232668cb98daf7947a292b0e8463499ec",
    "items/item-14.json": "bcc9429bbc4c526751f32b79b5d67e6f406c13559627a65ca34ad8c56f58bbc8",
    "items/item-15.json": "681057139e73ca8217d38784ff652bd3b7403361d7dc02374e0b30ce43b51636",
    "items/item-16.json": "fd85a7fad05afa27fe45dcc718d830a17636a4b9736a7ef3cac9ce0d1bcb08ce",
    "items/item-17.json": "83ea3ee86972af0b75f2b4ddb017a1f0ce665b2527424e4856162344cf1ffc53",
    "items/item-18.json": "4e7da35f086193263a52651b40c041ea2b99a335d38b64307d0a8cbd2fc1abc2",
    "items/item-19.json": "26c1d77a2268a220b03961aa728ac9d01bd49015f22da0b3e6ef76ab0c61ca44",
    "items/item-20.json": "1229218261487737d927161c42320d1173ad487fe4d80cb321ebed2dd5760b4f",
    "items/item-21.json": "95a48034622369b89318a286b5298f61b468087745761bfe5cc600dfaafe6ded",
    "items/item-22.json": "707ed9fc3474e214be7956f2c3968cc284096e94d00a06264df277b6ea261b03",
    "policy.json": "d676d0e9a05ff713a998461813614455ab477e1119bd27d6c0a29d6ceb7ff067",
    "SPEC.md": "dcd1cf207e802687fc6cf372f58566a75b1f5f57fad5642d0f556584d6998494"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "allocations.json": "78c201718f322e041dcda794fe03ff5a65c1c347056b5ec7851d7f036b72b436",
    "summary.json": "f146adcd2bfc4e85124e9aa5347db5b7d3507ef8857c265af12a658db4f4fbf8"
}


EXPECTED_FIELD_HASHES = {
    "allocations.items": "220b4f824f755c5e2658061f3d47274b01a831a879776d5c5df7d1ed120fa613",
    "summary.status_counts": "fb73af9589196bbf745482efb54d79b46ee36d016e7994cd2b4cbe179fe6c04b",
    "summary.tiers_touched": "f6039ec2e29afd65f235e89aea2b1155909ceda379bdbf1484eb09a705298538"
}



def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    def test_each_input_file_sha256(self) -> None:
        """Every fixture under the data directory matches its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_on_disk_matches_spec_json_encoding(
        self, outputs: dict[str, object]
    ) -> None:
        """On-disk bytes must match SPEC canonical JSON formatting."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Pinned nested field digests must match."""
        items = outputs["allocations.json"]["items"]
        assert (
            _sha256_bytes(_canonical(items).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["allocations.items"]
        )
        sc = outputs["summary.json"]["status_counts"]
        assert (
            _sha256_bytes(_canonical(sc).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.status_counts"]
        )
        tt = outputs["summary.json"]["tiers_touched"]
        assert (
            _sha256_bytes(_canonical(tt).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.tiers_touched"]
        )


class TestSemantics:
    def test_frozen_item_03(self, outputs: dict[str, object]) -> None:
        """item-03 must be frozen on the audit day with zero allocation."""
        rows = {r["item_id"]: r for r in outputs["allocations.json"]["items"]}
        row = rows["item-03"]
        assert row["status"] == "frozen"
        assert row["allocated"] == 0

    def test_shortfall_on_platinum_item_02(self, outputs: dict[str, object]) -> None:
        """item-02 demand exceeds remaining platinum cap after earlier draws."""
        rows = {r["item_id"]: r for r in outputs["allocations.json"]["items"]}
        row = rows["item-02"]
        assert row["status"] == "shortfall"
        assert row["allocated"] < row["demand"]

    def test_summary_counts(self, outputs: dict[str, object]) -> None:
        """summary.status_counts must match allocations rows."""
        items = outputs["allocations.json"]["items"]
        summary = outputs["summary.json"]
        assert summary["items_processed"] == len(items)
        frozen = sum(1 for r in items if r["status"] == "frozen")
        assert summary["frozen_items"] == frozen
        assert summary["status_counts"]["frozen"] == frozen
