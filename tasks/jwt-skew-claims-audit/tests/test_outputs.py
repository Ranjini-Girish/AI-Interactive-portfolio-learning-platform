
"""Behavioral tests for jwt-skew-claims-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("JSA_DATA_DIR", "/app/jsa_lat"))
AUDIT_DIR = Path(os.environ.get("JSA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["claim_rows.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "d0bca0a7c1b81a2d15898a6a6b9857e38951fb01bbe0554c98f7cddc6407523e",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "a02f8ab0035a9255855e4bd513831903a86a8ba283ff2ca365c61dc7480f9db0",
    "items/item_00.json": "b2e62baf88d356c8a7c86b03306821c6c7e9af3e400c27ebe592cc5622ac4b79",
    "items/item_01.json": "d5d15fa35e5289ac1d8d5c880938b674286046fe8152e87e9c4209ec26a19af2",
    "items/item_02.json": "68a203a1ff21f567fa8ae46eee461cb6f1e3ede51f3486441198545ae7bc38d9",
    "items/item_03.json": "4209bf7e9240b4f17784f977a9f6857912cc76407f2a175d672ddf347e83e5be",
    "items/item_04.json": "01cabca034b1c85a92513ecb987032a060d5684a60bf1c6a4aa40b7ff5bdcda2",
    "items/item_05.json": "0c840936ec2dfb5c57564785d69b39d025438fd78d133561b944d5c36b2b0d55",
    "items/item_06.json": "522f56835e64404c620651e86c9e06226a0fa86e7781f269a0b39df6dcbd7343",
    "items/item_07.json": "5dcd9f96b68de76774a5e1f028b3221be7368c2c08ed665360e3e5017d230118",
    "items/item_08.json": "fc978de111cf2ae68ef251f986d0a78094680c3507584bcce8af7573a80b66dc",
    "items/item_09.json": "b508e8011cb9eb6336d1b552662534f7024d1320c86329adc437180a72b1734b",
    "items/item_10.json": "d6d045dcfbca071c1d01a207ec1a547c2a77ef8e0226d75e391b45af505c2b2a",
    "items/item_11.json": "2576a9ce4e1cacbb5ed0085d74a30048581f46cacddafd06ac37073b64f47801",
    "items/item_12.json": "7c6ab76e9f7fce7225957959f1125fbc836796b6855598c739ec8ad29d00e6db",
    "items/item_13.json": "4de7c7be33c27a2b498418b63c3f17f715c1ece581be0ea72f5dda10b1359741",
    "items/item_14.json": "4f808ea4bf174376bed8a1145f7fd9e43cfbfd4c7afd18fc922039b9864b7727",
    "items/item_15.json": "2c930dc8de56381fb76cbc5e54ffddbbbdff6db2958ab5c92bce1b63fb9147d4",
    "items/item_16.json": "c7406e06f0d7041d7f86abb4a9b4adbacd21ebb5bebb9dc623bbbfcdf515ff1a",
    "items/item_17.json": "96f571e61223f016504583fc4e3575ff6fa54b8e6d0cffd69d16ec446fae1fc6",
    "policy.json": "f7fac5ab2b7284e287e5c54834bd55d540fc5b78b87dbb5e56903b194a6108b6",
    "pool_state.json": "378912519e942abb51b95c3ab0d195e69ba1e66abb85bd6e9093f95e93566452"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "claim_rows.json": "097e521a43d8608ed65e44e67bb638da312f1502aa34305afdf829c6004535b8",
    "summary.json": "0f5c9e49f9087d40f04198504af413c31aa259b1e6482590c67f83ea9c475f8f"
}


EXPECTED_FIELD_HASHES = {
    "claim_rows.json.scopes": "0134a7be69b7eca4e2689ba33b9287b340e0da8d30e8ff8601d7f2365804a7de",
    "summary.json.current_day": "2abaca4911e68fa9bfbf3482ee797fd5b9045b841fdff7253557c5fe15de6477",
    "summary.json.scopes_invalid": "4523540f1504cd17100c4835e85b7eefd49911580f8efff0599a8f283be6b9e3",
    "summary.json.scopes_total": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.scopes_valid": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b"
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
