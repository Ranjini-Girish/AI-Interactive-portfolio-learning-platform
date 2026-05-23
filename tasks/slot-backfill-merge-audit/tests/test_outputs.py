# scaffold-status: oracle-pending
"""Verifier suite for slot-backfill-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SBM_DATA_DIR", "/app/sbm_lab"))
AUDIT_DIR = Path(os.environ.get("SBM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["merge_report.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c07fba3c421be9716de71bbc369c0a05667cd27bff575231f2e4ca8f825062d1",
    "policy.json": "9db52a8261a8eb1aa01e023e09deaab70d698e2d25852ee51f4ef370aac508ff",
    "pool_state.json": "93904d245ce2d5de945457affeeef252f966527ed4f1d80c9fabc8ac2184b71b",
    "incident_log.json": "a59f118ff68c874553b918352cb9d640e9d0241e9b2d55771aaaf4e62ddba94a",
    "domain_layout.json": "fc4f1c7249415718237bc80eed5b98b14693715f2fa085f3363377dcb8159f6d",
    "anchors/north.json": "572171e907d183e669b82e877cc430c4f0efef6a9d66ca20c6446ab2706933ce",
    "anchors/south.json": "33b232e46c9daeb57e2293b3d054ab0e4abede15d84fad64dd583b1719e392df",
    "ancillary/note_a.json": "3a76c4272285840340d20506e8196d9074d8960511a62ce789c222b92a76c141",
    "ancillary/note_b.json": "5cad52774c122a836368c48c69d1d0abc05ef940f86c0baf0b51740824dd1e21",
    "ancillary/note_c.json": "33779e2859b5958ea0246da90cac7f881dbad5072047af10ec67f6837421fc2f",
    "items/item_00.json": "1ccb560ab0f3a31a0229fdc900fc3b98f37f98f77cf4d4cc20d0f17363bf3417",
    "items/item_01.json": "e783dfee4500de18e608a19102283bc36ac82652e7aa8eb47b2deb49f2c1c6f1",
    "items/item_02.json": "caf85f8d0d6d59d43252064bb1f9de72aee33bd4c42fc17e9a654c650dc8bda5",
    "items/item_03.json": "c4d2da1f55c7011438776ae1c72c03cdeefffceb123c6761719f2b924c862b1d",
    "items/item_04.json": "5ef7914d0b22be6f5b149a4e588c9a0a5f304632a33d413fb039d13ecebde733",
    "items/item_05.json": "ac1b1d68e01bd276251255d11d919def05d56e40b35e0706c47180702e14b6f1",
    "items/item_06.json": "77d53f126c085a5e4f4ffe6a8d99072bd064c647af5f64ff4afbc4e056e9554d",
    "items/item_07.json": "7358097b6187e36f51558f35fd98b295b89ee30a988be18e50f53ee2269cd3b2",
    "items/item_08.json": "cb619ebbae486a2172cc4e8929b654a506c9b07f94ed8664a259b755af9d0692",
    "items/item_09.json": "21e17b184c785621e698b2375e6ae9a11d5e1b174caea2e1c1a5e4f0e0b9958e",
    "items/item_10.json": "d0953824e405f3117923b19c244d792cbc00b8f6cc21b641baddb4fb5d408e99",
    "items/item_11.json": "84621b9cc974a996bb5d7f9dbb192a88623f67d760301a6874cc9b56c09990c1",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "merge_report.json": "68e1b1f37badf82ffe1d0968871d413c2fe74ac6a363789d3fc5b453d5b813d4",
    "summary.json": "d4a09d6c7c7013e45640d5cb948ff5650c8102058cd98436ce16e37cc272aed2",
}


EXPECTED_FIELD_HASHES = {
    "merge_report.json.groups": "5e4d2e0661a3cb16970d79b9e2c955ace3d7dc614bf5262693c5d7431db1c471",
    "summary.json.eligible_items": "4fc82b26aecb47d2868c4efbe3581732a3e7cbcc6c2efb32062c08170a05eeb8",
    "summary.json.groups": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.json.lanes": "b64e3448a83a5b86466465080361c1a7e1157a27ddccd4b68069cb18caffb74a",
    "summary.json.ledger_day": "811786ad1ae74adfdd20dd0372abaaebc6246e343aebd01da0bfc4c02bf0106c",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified form."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit JSON objects."""
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
