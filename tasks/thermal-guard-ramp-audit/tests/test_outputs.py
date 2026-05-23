# scaffold-status: oracle-pending
"""Behavioral tests for thermal-guard-ramp-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TGR_DATA_DIR", "/app/tgr_lat"))
AUDIT_DIR = Path(os.environ.get("TGR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["summary.json", "thermal_ledger.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "f45b968c00660ce200ce8a96b91ad0fd14166f4adcf4a1df2dce5b9203396a95",
    "anchors/a.json": "e435b2b7d8c7681105ea75b92f4283573c9b1fc7aee73d05a68d6cbef22300f7",
    "anchors/b.json": "818b9eb11968d1bb3b50b186f1909a468c5f4d24d4063685ee859a57f566b9e4",
    "ancillary/meta.json": "47855aeee741568ebb252dc1bdb459a5f32b1eabddb9cb68aeb42878e1055740",
    "ancillary/notes.json": "4a1af0e3d20fbd407b603e7f6ed98b6725d0a16c5c9cb8c8f4a15d4e4ce908c6",
    "domain_layout.json": "309a2b0702ccf3cc34828f0b3e03c3950cd3d1b2f4cbed434ef8d1b555ad0921",
    "incident_log.json": "d09a7afed7d59306ae8946837f38883e74184cd778274741f75cc15da45f0170",
    "items/item_00.json": "92a52deba1e9ed138739420a68041499c17e7e039737a713abb39d07dc4da390",
    "items/item_01.json": "c9ef0e9c967951a0927e19151238a04abda6ec3fddc074aac845ce45d39d852b",
    "items/item_02.json": "b51e9d416b298590142c1f863e8bcea1ed9269c0da8c0602691db11ea8f77c5c",
    "items/item_03.json": "aedd803f8420c33b78a7ff53bd2319caf40286e34cb5322e1802505bdadd3e67",
    "items/item_04.json": "678fc94001780704ffb51dce6ab05edf352de982feee8739dcc5395c2f1016f1",
    "items/item_05.json": "a5b61b96041bac76634f6bfbefa1c568efa87fd643937543243640dbc0a40704",
    "items/item_06.json": "e00d50434bc6a50616a6ab1e790cf1991e7d99735761e309bff5e9f4c2d3c00e",
    "items/item_07.json": "2309a53b10d309b3252944407598116761f44746af44357ca63d620a641b8617",
    "items/item_08.json": "3ed8c95e2aa9073d4f00efb837b333e4e73e974f16b52fd97a4e87dd15629f87",
    "items/item_09.json": "89237d5a619d8de6c7a674299031f88cf7000007f0ada8a605aea685d9378e36",
    "items/item_10.json": "13c398f212fd1fcdc792aa550b8e6db41209a98ccc8632cc057e1a2f3c965f50",
    "items/item_11.json": "de4589026c2b5a84d81e57ed60d9df9175d82434e919da92f083379bdfc87f56",
    "items/item_12.json": "a3d5d6b3155cc1a0f4525ab33597c39ae7b11bfa1444d9392e167b9d1ea4ebf0",
    "items/item_13.json": "9797f794b85fdb95b4253cc4466180cae01802c73cc55bc36383dcab75490650",
    "items/item_14.json": "75060690a11e5be0029a44ff2a671f0487dbac2f0f08c01364c3bbff807bb4cf",
    "items/item_15.json": "31b57d491cbc886ed9f79b598d50f17d677d65af7cd92c7e18d4410a7141b1e6",
    "items/item_16.json": "af3d5af377aa1311be58468d8c64fea383a3bcea0bdb7ac360ab2662425617b3",
    "items/item_17.json": "80b54ddb2215a9974176264e87cd7e62946dbe3c6623a263bf952c0651c53b17",
    "policy.json": "fc114fc2b39e4ee3952b4a70dab34c5717c5f5add8c5d22e085990519e99cbdd",
    "pool_state.json": "2f97ca208a1083fed51e34df0fac79b82dc8f7001bfc6d630cd1fe223ac2eec2",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "summary.json": "adecfd794306e1546836227bd2609437ec261e8a72ceaa3ca125f92393df5c0a",
    "thermal_ledger.json": "b107df777d98686cc908479c5e84097303f2e33a78781408409cdd5a26b57172",
}


EXPECTED_FIELD_HASHES = {
    "summary.json.ceiling": "b725d20650649a5221675144bab5946e013616d1ba7a25afc394f43e05e82052",
    "summary.json.day": "4fc82b26aecb47d2868c4efbe3581732a3e7cbcc6c2efb32062c08170a05eeb8",
    "summary.json.global_add": "d2cbad71ff333de67d07ec676e352ab7f38248eb69c942950157220607c55e84",
    "summary.json.guard_suppress_events": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.ramp_effective": "3135d2d71bff77be4838a7102bbac5b87af7fd0b9aef3d416f963a5afbb19061",
    "summary.json.ramp_shave_total": "4942870d7312d707982f792e63180e31f72925b998dec46f7ce23db6f16e2d3b",
    "summary.json.zone_bias_events": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.json.zones": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "thermal_ledger.json.entries": "68ee3457689e619d87ea97b4285f644fe5f7251fb72956e70195312f73e536e7",
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
