"""Behavioral tests for queue-dedupe-window-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("QDW_DATA_DIR", "/app/qdw_lat"))
AUDIT_DIR = Path(os.environ.get("QDW_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["dedupe_ledger.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "49776b6d1dcd58cb1a581f75fcbb3bb6057651505c4b66c410b3530875035f2f",
    "anchors/a.json": "a1dcbb91174efe55ab5319f406c0c6b3a005b11d8b57e6c352f93ff3750937f8",
    "anchors/b.json": "8972cc4f07e3c1c39421377876505f6cd8f410517c80336365fdc2591ff22ce0",
    "ancillary/meta.json": "c7eca81c72ecd96b491203baccbc54b1128412cba5a54c0cf05e8661e7bc3fcb",
    "ancillary/notes.json": "b334c4d065e008c467a68725d489cb22c60115e055ebb125ebeab5cbd02a3b07",
    "domain_layout.json": "2fa32cbedb515023e124be07c17c90951df4c0a70fafd800e157342c6a3aeffd",
    "incident_log.json": "cd4ff60035f739c876a3589f541deabcb9057732c2b779d7a43cca5ad4479f45",
    "items/item_00.json": "9e8207c0f7f0bb411401160c45d6f6339520daa5958bfa8a0efc00899f298573",
    "items/item_01.json": "6350cd0bda2b145eaa1208631e8add5c50665c93f8ad1165c53033b8c2078845",
    "items/item_02.json": "0a5979044f8e537658172a7fd01ea3e94baa400a7f080ca9574c6d8045ab1f3f",
    "items/item_03.json": "7709e3185308e95dc2b4f95752eb62f07815bdab13b2ad413a9ed7406c2b4f8d",
    "items/item_04.json": "6338d979188b831b582f77a3ea84e9a6d5a3214a8fa9bd88035deb10ac79b56e",
    "items/item_05.json": "a27404218675153bbe3cee3ad0eeaf0f4f609386294651ca3dcac7ebcb0f7385",
    "items/item_06.json": "2e585013f041cfe3d1308c40f3217ba6f37efd4bd5e276b41778251cf5a4954d",
    "items/item_07.json": "da65e5764fd8206a9111381f4737a3ae44185b63cee05b7df0d86d73fe1fd662",
    "items/item_08.json": "fcc5115be77d0342aa78b786276a2df6111dfd7c3ff6fc70b49bc61e28a95c1d",
    "items/item_09.json": "1ade5c2844289e12080bd01037047c7e37543d0ed2928e7b4f4ce61d08a82260",
    "items/item_10.json": "89463d604fe5c91f52c6cf0e58f0925d05e3aa2a6cc665b3e4364cd0e1e4ac33",
    "items/item_11.json": "b507bbc86051ba30df1281ac27ab1363dfe1d0670e2e5217957a282335a5dde0",
    "items/item_12.json": "477158e17ed04e16f95fcd70e4f7504cc2d21a583bf64193537fdec45cd41848",
    "items/item_13.json": "90be83ff51f263d04c60600fae12e7679f2bdc12b71ba9594965fb22f778b59f",
    "items/item_14.json": "bd85fce1af243bd48452c2ac1841db8f1080c3f61f06db7345aa378cb006c840",
    "items/item_15.json": "50efb0b782ff69d778d0d808ce99341aa16d0aba521110e40af087cf27cb39ad",
    "items/item_16.json": "93ed683ab837802239649bd11be6dabd048bd91be0305c8d5eb9333975326de7",
    "items/item_17.json": "f576f3502c1078b8596c89695567c675dc1ce0fb75347f71f89c242cb22a0319",
    "policy.json": "84aa260f490ac769d4ceb73ab951f4fd4eb652f687c541e13453dabd5b3e4686",
    "pool_state.json": "65c22c740bb26021bc6f7f28d538b946a60245890e272d70e34064b32e02534d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dedupe_ledger.json": "31f2a16f74e282e4829357a4a4155a96e1093147ed19b558b78ddcd5d1547f2b",
    "summary.json": "94db032ae8b43cdb70259807757315abbdb2dca40b771c9c031baeedcab6afcb",
}


EXPECTED_FIELD_HASHES = {
    "dedupe_ledger.json.entries": "62889010a68c554e2478dd975de167739d3952b814eb00c84dc4513efdc912fe",
    "summary.json.entries": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.suppressed": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.json.total_weight": "01a6025a620037fbbf1db59ef84258dc8028e5d50a40444a1801a53bbd6b33bc",
    "summary.json.window_effective": "0de7cf39e1e6366122309794e86d197d025a81235881e67ec4f011c9db2df252",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
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
