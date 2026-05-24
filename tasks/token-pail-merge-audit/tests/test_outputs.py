
"""Behavioral tests for token-pail-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TPM_DATA_DIR", "/app/tpm_lat"))
AUDIT_DIR = Path(os.environ.get("TPM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["pail_levels.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "2d71a9cef7157df46d2a96d94cb8fe5198e1c2ae06b62f1e3c7f0f6ace6ef31c",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "b23903bcf755967654c5c92027e101b00b1d881cf032ac5fa69bcf131abe4e27",
    "items/item_00.json": "a61749e5a3a8d37865d7358fc293ae62c4e1a44901ab9fe6540be725c6291b2f",
    "items/item_01.json": "921f7d8c00dcc7468e2fce39e9686d5f001b4064a465ff558b399bd53a4633ce",
    "items/item_02.json": "6219bf5bd81f7d308e577ed2c177de71cc8edcc806b7fed4fedb6c8b356b25bf",
    "items/item_03.json": "c70a07770fdd178bb734014e96386076d21592713087fee1ed3e1d29556f1fea",
    "items/item_04.json": "2b7cffe48507a11481dffe424dfbd5cd6c8e4d878e8df77d920b5f46cbd5a937",
    "items/item_05.json": "e04702f256f82989226e54ce48645b43c42ea738c6c1c16b9589ba22104f4f74",
    "items/item_06.json": "4815e245641ee1b82ee09479f5df13db5dbea54c7d396388b360c14b85dc4a5c",
    "items/item_07.json": "fee64005bd5770b0a006dd9fd0760a72404c573478a0d8f3f4dcb966f8d9eb20",
    "items/item_08.json": "c1868ae75c7754d3285dc6a89ab00f796f215d6536436a360835ab52d0ddff5c",
    "items/item_09.json": "fd90efe0a25e7c7e1f46decc67e3e2d3bdae221abf9fb17fd9fa280ed8fc6944",
    "items/item_10.json": "4714765328aa028c49de890b3452484461eac10731802bcae498993b824e4d40",
    "items/item_11.json": "e3e9ea64bb2c97c94c2839c37dc393e3bc6c0ab85b6a4ed3d64240a70954b4e9",
    "items/item_12.json": "e58b8a1f3cc2af4191690a916541d2c8710d35d7b325c256b9a6243d9b19d4c9",
    "items/item_13.json": "8580c5a90b320faf96db78a9ebc9689da51e52c8f0667aca61f3067505df35be",
    "items/item_14.json": "43eb6de6af26cb77cab3b3703e89f2fff0608afd0b667f3b8d78e494ec3693d8",
    "items/item_15.json": "537c7956fb3d3a31410116b714d2dfe94cf83988cc3ba824aca970d18128f49b",
    "items/item_16.json": "b9948483dd325858b19a60d4e38f9bb3c42edb464c18c895d2d7d7bf50e075f4",
    "items/item_17.json": "b90f9200cbcf78443422df0025d43d6378c6d0fb29d65ba3df578aa8a387cba4",
    "policy.json": "9c313ba9b44df318aa57abd16d64cd5464e84888286db6cdf567c53bb95df7df",
    "pool_state.json": "dcc69b8c2e0ecb289467ee145eeeb8a491a565789d123c134e0b0f9b29750902"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "pail_levels.json": "e37ef0f7203b0c50a6722d78f2e40cf8366ec8802d32e96a4da9ac5f9b887224",
    "summary.json": "4dd696966a4ad27647ea165b2eabde1804c1c165808be5eca080b1ca745d2897"
}


EXPECTED_FIELD_HASHES = {
    "pail_levels.json.hosts": "45cebfb9b991d9f4b5ebe9b6f8c49fe0fb9fbb8ee24baceffcf4716f995500e8",
    "summary.json.current_day": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.json.hosts": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
