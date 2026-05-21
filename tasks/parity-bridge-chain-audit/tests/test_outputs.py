
"""Behavioral tests for parity-bridge-chain-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PBC_DATA_DIR", "/app/pbc_lat"))
AUDIT_DIR = Path(os.environ.get("PBC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["bridge_parity.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "e87ca46f8b9a24f531e6566a98b683519ea03a3006cc3d4ea6593cf86275ff0b",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "10de4cb03312e4dc2cc6ebf3017d1708deb3a6aa96412b9158658c9a55585c59",
    "items/item_00.json": "05bf4032eea4d420e7badcffd9787d58bb1811f369ddd1ed86a9447a7ac80d95",
    "items/item_01.json": "987861c47bd2724447be0a61f560f71808d8fb6a920bfa88d55fb375e297ff4d",
    "items/item_02.json": "339f24e8103f94fcf9284fa900abb645f37fafed0476adf3366f3c7b0f559461",
    "items/item_03.json": "21cda71571c1fa77b914ed127e76311147025b9f5080056a80e084ddef94bdba",
    "items/item_04.json": "61f4e24ea52e418f3e8d8d5cd85f71de36e99700f3c4f1f1d14756ae9c70fafe",
    "items/item_05.json": "9d209efe037f18e43d681b7751ffe9b7e40189498043576442bfc2fc44a2ee9d",
    "items/item_06.json": "c5842131218e2e46d7fdb2bab644c6465035a7a4a3b8f92b6d52f6d305ca3501",
    "items/item_07.json": "d0fe022ec386cef2ee0927c7001bd618502d98a9114f7b2ac58b03d9356e7199",
    "items/item_08.json": "5d2ce31bd0104dea72d034e4ed097efed7985dd0c827963b20fc3c3eb7d4c8d3",
    "items/item_09.json": "e1a8d4a12ced452a3b29e8a21c67e794d918f80baf50e99b0fc5bcf048b197c8",
    "items/item_10.json": "9821e1d33fbd174d14f0f0c25ae97bff060718c4f61b75164bb0b695e9aae1aa",
    "items/item_11.json": "69e184a043fc71b298c5cba2010b7c372c0fe157347a9b8efbb440b422c0fa6c",
    "items/item_12.json": "bbf54528d10a9803819b01cdec6ecadfc85a089eb939a6c76a554ddda1a36c20",
    "items/item_13.json": "ff23d1c09ec98af11dfca1a808b6192c1066daf7622ff3b36572f47439e30406",
    "items/item_14.json": "46eb498b430d523aed55c163d5bd74d6fe98acd5ead6cfe8da6d28a9b2c11196",
    "items/item_15.json": "4dfe7e45674fdb1441fd4bed622cd33fba8f342eb68caf72271b5cde932ad009",
    "items/item_16.json": "ef587ada230dfc7bc09681a1fa632649f4df93c4078bb97aa87a59f942424315",
    "items/item_17.json": "563a7a0f0d9a68c4b86c4e3bab2df3832fafef53dd644c3f133aa178d4d447bf",
    "policy.json": "33528eb85a3ff74990b80581e92282a03fed661f2c0876e675ada94b920c1586",
    "pool_state.json": "29cc72123d74da534aaf0c657b053a3d180158ee3cdd77a4ca6891ef73a848e5"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bridge_parity.json": "4ffe2e575105fafda2a7e13c5eeb803ed1fa9fc33bf6d90fb317a923d5ca2e06",
    "summary.json": "cbb264aeb37e8c67086143240fe81c7bc44e920f14e400799b3ee259cd3366ed"
}


EXPECTED_FIELD_HASHES = {
    "bridge_parity.json.components": "ce6ff921e2fb4fdb2624ed0cd1b85c7d7e7428d88cef9507530c5b694149e873",
    "summary.json.components": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.current_day": "a88a7902cb4ef697ba0b6759c50e8c10297ff58f942243de19b984841bfe1f73",
    "summary.json.edge_count": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.xor_all_edges": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
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
