"""Behavioral tests for fair-queue-token-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("FQT_DATA_DIR", "/app/fqt_lab"))
AUDIT_DIR = Path(os.environ.get("FQT_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["serve_trace.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "fbe8fe335a487526fb6f791637acaef6af90f2b3e65e8e607c5736a1b2bcc36f",
    "anchors/window.json": "27a76c80180a8897e6133ffc244a7cb7d357c21f59efc63db675ca349fd21b89",
    "ancillary/meta.json": "56f7d1ac774d4ff7aa1a800456c55be8fce7ae5d44ec635cdfd118924f3f2cf2",
    "incident_log.json": "20dee15bbe8b11753eb1f7aa8dc24350ba73192abf75349664360c119bff755c",
    "jobs/job_00.json": "5e3ed81df2e090ae3ae5d5268f3cb0f1bf10cbe8cf301579f225a6152ecef576",
    "jobs/job_01.json": "b661dbb5069f9210450e9c4809e2444c45024b141708c767b638b63b3841b6ef",
    "jobs/job_02.json": "f3ef46275e4161cec9554466ade2e4da14ca97cb8d8f3240fd2ddbd41b035395",
    "jobs/job_03.json": "0aaa3a753e0176dd799cc4bc17d3eb9ac1572f27ee471927d3153176a7919759",
    "jobs/job_04.json": "737652aaef8ec1bb3c42ffb6b116de15bfc6f1de175a15c89a232baeb5bdded9",
    "jobs/job_05.json": "3025795df9d7d22b7ef9b90dfbf8deed5f80a827e130fe90b0983653b19836d4",
    "jobs/job_06.json": "b1f26e4e61c2238bdb3659d5b5d60b59dbac7e39aa9815d592ebcbca8d91ad5d",
    "jobs/job_07.json": "0aa044323baa3c4b73eb2c408a43c9971a6f3fa4ed7f667cf74332cfb58043d8",
    "jobs/job_08.json": "f2fcf21adce7b16c70e5db42715f425bfb7b7460ede603e8f5beea4603b6c6a2",
    "jobs/job_09.json": "e34a3021c03823aa9154eb16e7da4ca4790bd4690c861aa3dd67987572d8a792",
    "jobs/job_10.json": "80296cc174bf36321f432d78fe9204748662e56a5f420c2bccb23418e53f26a5",
    "jobs/job_11.json": "9688fe89df6b1fb789d855c046d73298736d3f95ae2ce9036d637a2340dd9730",
    "jobs/job_12.json": "8ce9680086566244b4a721c5b0b99f62d69592541d26b663108494d663263c2d",
    "jobs/job_13.json": "a6e483e2e6e8bb9490815d10014d1d6290290463dcfe296de99eaa2a025b7873",
    "jobs/job_14.json": "f5590c5cdb96e6ee1527fbdddb6398bf3eb0e73bcc9ece9c025103d2ad5bc6bc",
    "jobs/job_15.json": "63736ba87765a0c2e776b9a40265ff2a1b6f2c37c3211b7208a9e9dee62a1872",
    "jobs/job_16.json": "a4e2713dd18fc0c7a779abb11c66390492ff9e9ef637c8ea3f04dc4adcb4e521",
    "jobs/job_17.json": "8b6202e322f0ec9e6c130940be820e0db46f3337812912255ceaabba9b20a41d",
    "policy.json": "95466f89a03f94c69b3c35780039f2bbce813fa199b494f4f1ed8bcc234423b2",
    "pool_state.json": "e07912a8715512c8f79fc8bf1781c247839166d59543947389a13825365bac0d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "serve_trace.json": "b9253f59d127e077b8d2a1e130b8eeb2c95f582f03fccb44538c1d27d41d2679",
    "summary.json": "2485f0374926b3d6f0d956926cb294405b148bfb94703dacb7839a3b794049be",
}


EXPECTED_FIELD_HASHES = {
    "serve_trace.json.slices": "61cb8ba4de6b4a9a1d12cfbc0f50272d5788f2495c2e812bd84436cef9e54d36",
    "summary.json.applied_events": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.json.label": "ea067f93741a7112e5f28337fb60e279dcc00fec3888dfc4baddbfe3fac3da48",
    "summary.json.score": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.json.slices_emitted": "b17ef6d19c7a5b1ee83b907c595526dcb1eb06db8227d650d5dda0a9f4ce8cd9",
    "summary.json.token_remaining": "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
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


class TestServeTraceSemantics:
    """Independent checks."""

    def test_slices_reference_active_queues_only(self) -> None:
        """Every slice queue name appears in the active queue list."""
        policy = _load_json(DATA_DIR / "policy.json")
        active = {str(q) for q in policy["active_queues"]}
        trace = _load_json(AUDIT_DIR / "serve_trace.json")
        assert isinstance(trace, dict)
        slices = trace["slices"]
        assert isinstance(slices, list)
        for row in slices:
            assert isinstance(row, dict)
            assert str(row["queue"]) in active

    def test_tokens_balance(self, outputs: dict[str, object]) -> None:
        """Served tokens plus remainder matches the configured budget."""
        pool = _load_json(DATA_DIR / "pool_state.json")
        budget = int(pool["token_budget"])
        trace = outputs["serve_trace.json"]
        assert isinstance(trace, dict)
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        slices = trace["slices"]
        assert isinstance(slices, list)
        used = sum(int(row["served"]) for row in slices if isinstance(row, dict))
        assert used + int(summary["token_remaining"]) == budget
