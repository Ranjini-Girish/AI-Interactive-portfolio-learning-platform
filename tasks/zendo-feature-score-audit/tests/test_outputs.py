
"""Behavioral tests for zendo-feature-score-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ZEN_DATA_DIR", "/app/zen_lat"))
AUDIT_DIR = Path(os.environ.get("ZEN_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["piece_scores.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b93c1c547f57ba54154f55f9f0e86798272f9b90ae7277d0d9c76d4c6810fd30",
    "anchors/a.json": "fe5dbcea246e15393778e452050f1682c6ef09ea907200c0a2b5a34d7db5efdc",
    "anchors/b.json": "b472e700f52ea3f43e4c8688464f7024032646332b2f7a42565b29a9aefcde1f",
    "ancillary/x.json": "b3d504b25c94af91ff5ef0ba4fd681d4ad36d645dd18d89ddcc1ebf0a7c99220",
    "incident_log.json": "0b955b12bd1397850bd799595d632ed536e02d5fedcfb61ae6e8d9559b62f738",
    "items/item_00.json": "418541410a23d320abf9f89ceed47c340346cd4e30cc1c1d6e935bd2bc415a52",
    "items/item_01.json": "2624938f4f022ae383df4aab03615957d1151d6cf7ef5e55ad2395507119fd37",
    "items/item_02.json": "869afca05dcc2242a1adfc0f7837543b030cd999d334f383c0ddeb2cb741b4a7",
    "items/item_03.json": "6475d904dd817f708d8d1e06adecc02970a224498eefb2fb0fc8d6f4b1f06022",
    "items/item_04.json": "5d03f83c1b78e338e21ee472f32d602b04a8a3e90f67ad4a08de9cf4e2b04830",
    "items/item_05.json": "18dbc6eda758058f50be57ab32ae20a61e01798f179f5120383222a2d8651dc8",
    "items/item_06.json": "03a10ffe68a678bbf3487365453a7c3c1b864c1abc994286b213aa671dad68e0",
    "items/item_07.json": "eb218bfbb1793b12645e9d312c7ce6234d9816b2dab59b5a3ca16f160746c4d1",
    "items/item_08.json": "01127360b1d75f13381b5f21dfb6eb215662536189bd406fb873d05947faed38",
    "items/item_09.json": "3f688fdee43d52055610d88ebb287c5fb84a8ca270a987b5e061ac4b1b4328d0",
    "items/item_10.json": "b36fa02fd7fdaf9a62590aba26a2220091d52be7290d453a1939babf471fe20f",
    "items/item_11.json": "4be4fe5f0e387e2c1f2212edb706b6a2deb9cc35a70554e0c0a53358b45d68cc",
    "items/item_12.json": "596dd004fe4c57d4931f1e9776d5752bfcbed512e4808ce276e716aa3188e8fa",
    "items/item_13.json": "efb5d5bb165033c4cd3017f2ee65552079d3be732d192c3ae7e753bf40e94517",
    "items/item_14.json": "990dc3135e6ecac2efe627f17e7cab964a68ee0225d768610dbda94a506fad42",
    "items/item_15.json": "00f189b55b7c202c80493b52c539b3aa1ac223f670a017be159c8961aa47838a",
    "items/item_16.json": "98173297d8410fba21540638ad5b73af1af6994c390478f2a40ae0f4e3387332",
    "items/item_17.json": "5523c94504dba89e5b202072b257b6891712279835d704f448047ceb7f0641bd",
    "policy.json": "4f1ccd85e804c60121946f172c83161e8c88af0cc66ec408b3558e024226f6e0",
    "pool_state.json": "50dfe969d3789746c192b5066a7e1f99b250c5e2c9fca82c90c9db05d28f8842"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "piece_scores.json": "4bd736047a5e43183477148c94f5c787a9c80ae70450eb5e2823aedcaf340c6b",
    "summary.json": "dc8bf66f0bb8a1b73c8110ecbab46a6797c0bab450fa95676ee3a8c627214607"
}


EXPECTED_FIELD_HASHES = {
    "piece_scores.json.pieces": "138471d56bdc15d279808e7cd2392942377378d402a58624a51cb4cc2058f308",
    "summary.json.current_day": "19581e27de7ced00ff1ce50b2047e7a567c76b1cbaebabe5ef03f7c3017bb5b7",
    "summary.json.pieces": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a"
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
