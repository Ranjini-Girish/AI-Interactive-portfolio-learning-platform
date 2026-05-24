
"""Behavioral tests for lru-window-cap-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LWC_DATA_DIR", "/app/lwc_lat"))
AUDIT_DIR = Path(os.environ.get("LWC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lru_scores.json", "cache_partition.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "04d963186af3b5db94ef052cb646e76c13d9764412e0a234955e39cc6247c2dc",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "4e136a9be1fa1022eec8dfc39794898852cd86895b9a5adad345179688da8132",
    "items/item_00.json": "f31e95c289bf8d8bd5190d0f3fa3112619c1aa85288a71cea917196d4e89168f",
    "items/item_01.json": "ed18c4465d848e8b97ffbedc3028a513ef20bf4108240a10e6e199cdf1e72a5a",
    "items/item_02.json": "ce6c1239d09dd3e31607c5d80ae2c87bff82a9ed1694268cc0d95f396fb15c77",
    "items/item_03.json": "19c0f130a081c0f0993d73c4c185d8d4c1a1ddc431664194c3932dcfb50c32d3",
    "items/item_04.json": "4828c75cd8fd670c744c540aaf6d5fd6c4169c20edc53d11d2655caf556836b0",
    "items/item_05.json": "bd90c4502ffbf53f82828ce04adbc7025d8a1270ff2293ae23c69244eba51f12",
    "items/item_06.json": "cda52d525d5bd68741ecb8e16074cc5b9a047ec70b0137545fe9250ac7d9bc2a",
    "items/item_07.json": "3cb43fe08cc1d590916a424d55dfcb54c26148a359caca2842bb116a866d60fa",
    "items/item_08.json": "a75ac741e12c1a925aa5cb002a7da77a09607752129c63881dea9cc209a5b455",
    "items/item_09.json": "56ab6688fa695aa9a9be0ce9e3f6e4213c684862599029a8eb3860b6d1ed6a3c",
    "items/item_10.json": "abd03043192952bdf668a6ed7820145b73a6e19fbb824db8bbaa8e5e1a025ef5",
    "items/item_11.json": "36c7e8fbf0dfa2770c41b99cb077279da3fca43bd43765ba505db9138b5fe1a8",
    "items/item_12.json": "43edb0d8c8d84448b2163f814298c18d683f2b701a4bccf0df7a3426bbd1602c",
    "items/item_13.json": "cec0056b89c2749c521cdb0e8e1dc6de7755f37951c4bbc76757079b528fad25",
    "items/item_14.json": "3916ea6a739727bcea229babe3ec12b949b78badf001416b44ceb9e06c1beed0",
    "items/item_15.json": "d979e57487da0036df3ac502c87470e1c16f0c6f0616aa548227c025b2763675",
    "items/item_16.json": "1d74dcf35411c4243f0060bcb3364504654cb5beadd471aef58e5b88498e6168",
    "items/item_17.json": "c04edc9b95a6e731429cce420f744cc86acbac5b308953a1e614d24cc042783d",
    "policy.json": "a57e75679efe3ade679c77c2bc13a2138f42f50d57d64e0f70922803b335d39f",
    "pool_state.json": "98b34facad42f6651403f9a0d279962101775db88b22bdc5a77adb2341cb1a85"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cache_partition.json": "f4e9329dfc4ad28333c73663d87dca8da7a68caf4330e1ce0ffbf915bffea5f4",
    "lru_scores.json": "85d92f909f3881e0cd73ad8ee1110ca91c0741d202742e85e2d01302c84526e9",
    "summary.json": "d0b1d4db816bbc0d04cc7946eef35bde8fd06f683d937531318160129127f3b7"
}


EXPECTED_FIELD_HASHES = {
    "cache_partition.json.evicted": "8c2913204195a884a7f623192012e29bdff5e7b7e923b6b5a807d071cc6c910b",
    "cache_partition.json.kept": "1f12c2120b780064f9a2dd2a51fa750c9110e61cbc49018c381facaa6e2ae2c8",
    "lru_scores.json.ranked": "3b835b9cefb28cb366aa8fd756f8dadf874ae1038bd16dcd7f5b892968760a4a",
    "summary.json.capacity": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.json.current_day": "27badc983df1780b60c2b3fa9d3a19a00e46aac798451f0febdca52920faaddf",
    "summary.json.evicted_count": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.json.kept_count": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3"
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
