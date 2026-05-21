"""Verifier suite for quote-decay-quorum-audit (hard)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("QDQ_DATA_DIR", "/app/qdq_lab"))
AUDIT_DIR = Path(os.environ.get("QDQ_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("subjects.json", "quotes_eval.json", "summary.json")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "50c685e3cc07125a9d19e751c839bc481b7b8d7463f9f0553d9fc87f8b3f6397",
    "anchors/alpha.json": "ee06941a47a556abcf4c35045d9159be56bbdcac1b64eee12d10982f058e6ed4",
    "anchors/beta.json": "359ca330750e10972f45aa8390f7d0d4b02bd8913de6d368e502bbfce41a08d1",
    "ancillary/meta.json": "fb2a814ee566731b51429ba42dc9c794060f6d10fbbdcd466cfb54847e90878c",
    "ancillary/notes.json": "661eaa1dea7ee6f0100f3a8afdcf13bdb211fdb37c61c07aea62d80426a82bb1",
    "domain_layout.json": "a3904aaf358d5c4f9d9659111fc2e292cd2047d50705d1ac4521ffa4f24ec753",
    "incident_log.json": "b99bcffd9cdcbd278406288668816264d2d73a3613c0e17fd5abb364cb0e3d94",
    "policy.json": "fc014d83e3cb15bd744e8745115ece61f025f9fdd281b2a22f8bca4860c7ebba",
    "pool_state.json": "3ad1c246550e83301fd6cd31ec968d21b00575114ec8124d15f0ef93989d6d33",
    "quotes/q00.json": "cffe2e07f97a9d3b96e0df9c5a055dd771c5c8103aed393d2580ca668989ddb5",
    "quotes/q01.json": "f614cf5d150f95a3b66ba5a5bf9b7c15396d203a48ad4babcbd6edb20a72430d",
    "quotes/q02.json": "37745227d6805a0c8be8b109dd19a5852d5dcfa5ee78cfc6f51a7d1159a3e0f8",
    "quotes/q03.json": "76c6bccc71f9864869fb9ff12a161a0e98439d794544c6c74c5e56fe2647d596",
    "quotes/q04.json": "19d94b3edcf8b8027114e9054d36a885e68babd65ad7821242d6307cb4cec566",
    "quotes/q05.json": "85e3379cca3b498cf7149831833804b776265487e714fb169d0a405a99e49e2f",
    "quotes/q06.json": "0841f583c2bc384659367c5896163cd62b1473ea874ca84be7e6ecd682b0f89c",
    "quotes/q07.json": "92adce327f0143ee4f7ce5472f900a9ea12317f350b092adf72756ae3bff92c9",
    "quotes/q08.json": "421f1c622f5bcaace3db68fc2ea9567b769b0aae55584bcec866d06f1f80d0a0",
    "quotes/q09.json": "575fb14c452c2f8fb7698147f61071338ccd80468183cc221a8c73a3e0ea57db",
    "quotes/q10.json": "85b8952907304c3dd7eae8f925642907d4ec6a04669cabd73e9ea137667ef877",
    "quotes/q11.json": "aa2616ed4da954a0a4b4e7e5042f7eb58cdb1b8524b417ed7071db9a9254ce11",
    "quotes/q12.json": "7eb6fc11920b9285a1b61a5fe2ba57708db971b70b48607aec0a0b9de995a78a",
    "quotes/q13.json": "8fce9ecb1df4002b1f865992892857cf51307c1339a7fd0dbf892b9b9f2c2aa0",
    "quotes/q14.json": "d4a49f6df090083e4a7880549cdb6b9d656568c582831c99203f6fdf8e23d24f",
    "quotes/q15.json": "b04836502bab5bc9683abcb2a6cf0d953b9284ece4c23ee3b47cd74a31d7e142",
    "quotes/q16.json": "c279c5f112909da0bb8b144d9ec1c48d33d25f98d4a46e2018bca56677317c37",
    "quotes/q17.json": "740291967bda193cf4f800849b56f7dbba301a2699856ae828746955af03e1a6",
    "quotes/q18.json": "ec83eca9c52413a6183465db765d316b3aab2af2f7cbcb1aebb82b88b5827386",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "quotes_eval.json": "2364d1f9dd38f7ca6b7aa8ed833a71ef4ad257dbebb7c38508bec222f1e20667",
    "subjects.json": "fa87f0911419273c73add7c05875e8c7425f6215b65b55013b6732db25a7fe24",
    "summary.json": "d8f50ccdb25a94d86a645657a0b72a416e99773dbb6fbab9b3fed1fb78caf68c",
}


EXPECTED_OUTPUT_ON_DISK_SHA256 = {
    "quotes_eval.json": "32d88bff4f6af09589e1a074294e74c552788463148f37aa5fce42015aeae5ab",
    "subjects.json": "71d4bcf710a653d9385fba8365f0c1b5da26e07907d2b45b53d80e13782384fd",
    "summary.json": "1b39fc9e7f2c1edfe34cb27d2196c268cd7a0d166a85f6dc4b6739043d95897a",
}


EXPECTED_FIELD_HASHES = {
    "quotes_eval.q02": "c3ababeaa965ca722048036fc3896867b97ef4b22daf24e7a4380702fe15d00d",
    "subjects.apple": "d365363e17adfa49615ffb90df901992effb751553b2817623f7127fa0d64d5d",
    "summary.verdict_counts": "c00a994867c97c9c392c3c869a084bbaa2f69e9e1ea87d9c637ded5703a93567",
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 for raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's minified sorted-key contract."""
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
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Verify emitted JSON files exist and hash-lock to the canonical contract."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Parsed JSON must match the semantic contract via a minified sorted-key digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_on_disk_byte_hashes(self) -> None:
        """Each audit file's exact on-disk UTF-8 bytes must match the pinned layout digest."""
        for name, expected in EXPECTED_OUTPUT_ON_DISK_SHA256.items():
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            digest = _sha256_bytes(raw)
            assert digest == expected, f"on-disk byte mismatch for {name}"

    def test_output_on_disk_utf8_no_trailing_whitespace_lines(self) -> None:
        """On-disk audit JSON must be valid UTF-8 with no spaces or tabs at end of any line."""
        for name in OUTPUT_FILES:
            text = (AUDIT_DIR / name).read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(keepends=True), start=1):
                body = line.rstrip("\r\n")
                assert body == body.rstrip(" \t"), (
                    f"{name}: line {i} has trailing horizontal whitespace"
                )

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        subj = outputs["subjects.json"]
        assert isinstance(subj, dict)
        assert (
            _sha256_bytes(_canonical(subj["apple"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["subjects.apple"]
        )
        qe = outputs["quotes_eval.json"]
        assert isinstance(qe, dict)
        assert (
            _sha256_bytes(_canonical(qe["q02"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["quotes_eval.q02"]
        )
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        vc = summary["verdict_counts"]
        assert (
            _sha256_bytes(_canonical(vc).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.verdict_counts"]
        )


class TestBundleSemantics:
    """Spot-check bundled rows that exercise distinct verdict and exclusion paths."""

    def test_bundled_subject_peat_fail_verdict(self, outputs: dict[str, object]) -> None:
        """The peat subject must fail quorum when active stances remain but the weighted sum is negative."""
        row = outputs["subjects.json"]["peat"]
        assert row["verdict"] == "fail"
        assert row["active_kept"] >= 2

    def test_bundled_subject_moss_split_verdict(self, outputs: dict[str, object]) -> None:
        """The moss subject must split when not enough active stances survive the shortlist."""
        row = outputs["subjects.json"]["moss"]
        assert row["verdict"] == "split"
        assert row["active_kept"] == 0

    def test_bundled_subject_zeta_pool_cap_drops_tail(self, outputs: dict[str, object]) -> None:
        """Zeta must keep only the top pool_cap quotes so lower-ranked ids become pool_cap rows."""
        kept = outputs["subjects.json"]["zeta"]["kept_quote_ids"]
        assert "q09" in kept and "q12" in kept
        qe = outputs["quotes_eval.json"]
        assert qe["q07"]["excluded_reason"] == "pool_cap"

    def test_bundled_quote_anchor_freeze_reason(self, outputs: dict[str, object]) -> None:
        """Quote q02 sits on a frozen anchor and must record anchor_freeze without entering totals."""
        qe = outputs["quotes_eval.json"]["q02"]
        assert qe["excluded_reason"] == "anchor_freeze"

    def test_summary_counts_all_verdict_labels(self, outputs: dict[str, object]) -> None:
        """Summary verdict counters must list pass, fail, and split with the bundled tallies."""
        vc = outputs["summary.json"]["verdict_counts"]
        assert vc["pass"] == 3
        assert vc["fail"] == 1
        assert vc["split"] == 1
