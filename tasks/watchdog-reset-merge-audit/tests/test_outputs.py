
"""Behavioral tests for watchdog-reset-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WRM_DATA_DIR", "/app/wrm_lat"))
AUDIT_DIR = Path(os.environ.get("WRM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["merged_resets.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "092ec3b7abbe47906bdcb9715dfd89e6c228b9bac2f19ea2d9792beca0012eb0",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "da2d58dbead73ca96ab2f53c5cf86eef90b1261e7eb9ab77819eee9e9fce8149",
    "items/item_01.json": "20bec4b10d3d222fb475b6c1dfdc6d57c999d8f79a77c5233246edd351c8665b",
    "items/item_02.json": "824633079fa610d6ad0ecdf526c38b81773a32ef2c36fd13f6df4ba7553db220",
    "items/item_03.json": "b15d4531d4331ca32480db6ddd967175260639f4a8d46c3cc563811a1b6019f4",
    "items/item_04.json": "b4ca3dcf830d638ef8da123053707b7540b5789ef86e039e3dc49a2bb7c1efaf",
    "items/item_05.json": "3f0a7d47067e6e2925a59a8319461c933c756c4c873f80df3b92ebc116a978a9",
    "items/item_06.json": "bbf98e01015c89fcca6fbf5bb4ae90419508dd74feca55742f3f6aa61308e7cc",
    "items/item_07.json": "b966d6c5f3aba36ec762ba7eff4e2c34ffc81f9078df7553207398391080d903",
    "items/item_08.json": "54b80f4919f85cdb4524cfdbdf88872dd57e2b5c971be504f3aaf69811ea80f5",
    "items/item_09.json": "139ce043240b53a8d34fa882879085bb3c4503a9ed2b37848cddc559a9dfd9fb",
    "items/item_10.json": "b1de3461a3789f7459488f959df0bcd47176226ee6ea7f32cd3386d79bef4feb",
    "items/item_11.json": "3ec5f90994ce949c2ea2c263857f459052ffca0545de9dc4c157a766f8353528",
    "items/item_12.json": "f77e92f5a827fe81e96516fc8c1afc31d2c9e000f2d35d0f7344c8ee54a479aa",
    "items/item_13.json": "a88152506bd4096d40284e53075201d82243637edc955c3d2fb5b1706ddeeeca",
    "items/item_14.json": "24f5d33c636ad5bf2b6a14991bfdf0129c223f72cdf264703fdd072eccec0351",
    "items/item_15.json": "ccb8a52468c18c600536fc151ea7b83d188a27334d1bc5f99a3e9eb8bf96f906",
    "items/item_16.json": "d7fcde0129dd6f135be7a86689f3506a69a5b44df3456579affc576bf4c52d20",
    "items/item_17.json": "249f14e6cb1d6e15c6e38b450b6dd3616d89ded0021a1e144c2eba1ffd5b1065",
    "policy.json": "2d7d438fa03fbcfc3d3f4fde3bbd81f32a269a901d39575db16fb2572731db1c",
    "pool_state.json": "4cd5070f07bd2ed85f3e32df99317d52b05c0f41d3c2889cf45af91436449b2a"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "merged_resets.json": "37721473e0cbdda9f9a17b606e1fadb7bfa513b75ed630e7f0d8c585b1482379",
    "summary.json": "caad9f25e940d3cb1aae08648164efb3d927dc723b949770d8e336db3320c621"
}


EXPECTED_FIELD_HASHES = {
    "merged_resets.json.segments": "06535fc53b70a9a6fe2f6003d312abb0aacf7a695506bdacb43f4d28ee3cb2d3",
    "summary.json.current_day": "26d228663f13a88592a12d16cf9587caab0388b262d6d9f126ed62f9333aca94",
    "summary.json.segments": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3"
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
