
"""Behavioral tests for nim-heap-sprague-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("NHS_DATA_DIR", "/app/nhs_lat"))
AUDIT_DIR = Path(os.environ.get("NHS_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["nim_report.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "9e75c8f0ac7023fe6433ddf5a63b1851cb5e915ce9a80617c502998247ec7708",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "c9dd81c7d62163ac6ec31d54ac1a7ea708d9ab4737be0b3fe92c6bb091484b3c",
    "items/item_01.json": "9471cc8d0841e540cbf05878c94572ed3550f0f8fead44b138161403baba9fae",
    "items/item_02.json": "25bef3fe09f7c7016d9c626d457f4172460cb070fc05255dca90dd9456588fa1",
    "items/item_03.json": "6b03fe5c91b5e0e29a8ca7fd1cf306d76a724cf3a3a27c336db0aa92297c1a25",
    "items/item_04.json": "827f582595dabafcf69b32257d01b90aba1290384fb136d26116e782c13074cf",
    "items/item_05.json": "7482e02092b76fd87f1e22dee3a937ca785f029fd51f34290f54a96c9a8c3a23",
    "items/item_06.json": "59f5ae7dc7c7f809b4edc769252c9483d2d4d455d1d6539d20b85d614385fe79",
    "items/item_07.json": "f1fc02a296a1882f9f77900011ceb08bd075993c07bf6026a4c2490a0fe41f54",
    "items/item_08.json": "231caeff102cbbd6e4f02d92564e1ed5d8294c0b99a558e28aaeec56f00b4945",
    "items/item_09.json": "9471cc8d0841e540cbf05878c94572ed3550f0f8fead44b138161403baba9fae",
    "items/item_10.json": "c9dd81c7d62163ac6ec31d54ac1a7ea708d9ab4737be0b3fe92c6bb091484b3c",
    "items/item_11.json": "25bef3fe09f7c7016d9c626d457f4172460cb070fc05255dca90dd9456588fa1",
    "items/item_12.json": "59f5ae7dc7c7f809b4edc769252c9483d2d4d455d1d6539d20b85d614385fe79",
    "items/item_13.json": "6b03fe5c91b5e0e29a8ca7fd1cf306d76a724cf3a3a27c336db0aa92297c1a25",
    "items/item_14.json": "f1fc02a296a1882f9f77900011ceb08bd075993c07bf6026a4c2490a0fe41f54",
    "items/item_15.json": "827f582595dabafcf69b32257d01b90aba1290384fb136d26116e782c13074cf",
    "items/item_16.json": "7482e02092b76fd87f1e22dee3a937ca785f029fd51f34290f54a96c9a8c3a23",
    "items/item_17.json": "c9dd81c7d62163ac6ec31d54ac1a7ea708d9ab4737be0b3fe92c6bb091484b3c",
    "policy.json": "f10034aa58fd7da8264e39d972aff183a14cda3c1e257537744b48290b684008",
    "pool_state.json": "50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "nim_report.json": "823369f4825d3f50967569a1f2d6c6a793e0477b1f0170a3d85c7a07c4c0c7dc",
    "summary.json": "fbd4aad73131c843e457d50965d40f10fd2477d95ed211d6b8a60a471e2f3820"
}


EXPECTED_FIELD_HASHES = {
    "nim_report.json.heap_sizes": "fbece4ce02a93a50363221a70359338568cb3e783275fbe709fa3530450a383d",
    "nim_report.json.misere": "fcbcf165908dd18a9e49f7ff27810176db8e9f63b4352213741664245224f8aa",
    "nim_report.json.nim_sum": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "nim_report.json.verdict_next_player": "6e4722a1f3387bf8b6eb38c4081f56b9d14f5c97565a70863668503b7a5ac081",
    "summary.json.current_day": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.json.heaps_count": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


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
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the domain directory matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested summaries remain stable."""
        for field, expected in EXPECTED_FIELD_HASHES.items():
            head, sep, rest = field.partition(".json.")
            assert sep, f"bad field hash key: {field}"
            fname = head + ".json"
            key = rest.lstrip(".")
            obj = outputs[fname]
            assert isinstance(obj, dict)
            fragment = obj[key]
            digest = _sha256_bytes(_canonical(fragment).encode("utf-8"))
            assert digest == expected, f"field mismatch for {field}"
