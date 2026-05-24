"""Verifier suite for trace-span-merge-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TSM_DATA_DIR", "/app/tracespan"))
AUDIT_DIR = Path(os.environ.get("TSM_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('span_states.json', 'parent_chains.json', 'orphan_report.json', 'service_rollups.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "eaee7be8206019dc330e5af82a3d3a3560877974851c8d659576a132a9f0475f",
    "anchors/a1.txt": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "anchors/a2.txt": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "ancillary/meta.json": "cbd3b7d4384e5d82e044f4da1b7e884e65849f5a4d2cc561f9a6880f707bf380",
    "ancillary/notes.json": "2821e697e49a09b4426dadfa7546e1931baec39642c43784925f031ed414fd02",
    "grid/dims.json": "6dfc05286939c4657697ed2d6a304c679787ebb1eca82e25fa02410d88069654",
    "meta/seq.json": "c7639c2534614ae6bfef31ccefec9d67d5ae4061302f831f9c76f124a74d5b8d",
    "patches.json": "c1037da3aadd6e5583011f6174df2eb31c095247ec2393981d00421e63e5bdda",
    "policy.json": "06c7cb709a4a56ae2cc1e7129910e175c79fe9749f69678e2e7b39f627c1a832",
    "services.json": "b662423285aafb772fd91b8e4ca80c85d4384cd2a2574562371eb3ca6d575f98",
    "spans/s01.json": "8b1e667e5ad4519b836bfd22d8186b960cadeaa26febe8c4f2e5c9a5a892af63",
    "spans/s02.json": "cd4885375f21a65d86892c7e9995e3f6216c552fe2b257ade6284ef1dbf15776",
    "spans/s03.json": "7cd5cc43f21a0edac8c30b2d68b3e5881e4c3eb43ad2d707e2a40c1440a41f5a",
    "spans/s04.json": "b4f32a17741fb8533593430381a1071b60d4ef69fedfe2a721a646caa09f4848",
    "spans/s05.json": "6375f1c5b8e6d9e277a6d7953eb154a00f2143b88dac89b9e42bae6fb1b9de31",
    "spans/s06.json": "14463484e20b043642f4f6da1e31b8f4afe37125d22b7b408e06b8a12c618ca4",
    "spans/s07.json": "cb36515756464e0d6ba6ddd6cc3b7fee0403e3688b3b25d8e592383f927f535f",
    "spans/s08.json": "08f7364d8a9f43ae881fa8f6ef926d2602186cf73fea3db26c9ec43734312249",
    "spans/s09.json": "3dcc6f56d50a6d6ef0dcf7e0ca1cfc1d9444120f36527dcddf0a87aa6a621901",
    "spans/s10.json": "c7889ff906ba25031af2d7dfc95a83dfb563f21bc8442d597e22bcbcfb244ec2",
    "spans/s11.json": "a47f02febf6465f04df652a9ad554087f5b3c3de5c504c13a9d7f25d62a9049d",
    "spans/s12.json": "891d050931557e4669911450ae4c584566d62f827fdf9938dfda0a2bd4ac65e8",
    "spans/s13.json": "8ca3ca0f470a60e4c85447757f0d7587032c10012e709a60dbad19f37a14e90a",
    "spans/s14.json": "ced879e716449565d64601bb078e005165cb24ddda20fc2e563760883def2e40",
    "view.json": "84493fc743ca404a300bba07fa34fc1b9cd1f3ddd728290100834fe6c44f9b0e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "orphan_report.json": "18f7f8eef17ba237f532c68e78c5a0d50069b43cf31197baef7b1d8bf412e04b",
    "parent_chains.json": "26af29c64f58723fda31777478ee89e17cb5c348c09ce6cc5a865c84fb167f16",
    "service_rollups.json": "7aa5078e7ab3a5d0e8d2a71349454d99aee0ec3fb414441592cc7f0baff79664",
    "span_states.json": "cf66297c3b130dbba6e269174059ed85e918baf246bdf2cd88704df554565adc",
    "summary.json": "c95a7a33c48b80c2021b7db2d025a772327709ac3c9a77f4ee1716b54a5a4b8f",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "orphan_report.json": "20f42884b9204bce36f696f713324ac0382f7df1389972da903483db3ce5bd4e",
    "parent_chains.json": "29c2a8c0bb68d730401bb8237285f8a14076d38a45334706d78f460d889b3ac8",
    "service_rollups.json": "5a680356fcde965c59e6d34aa104bf4b82a6aebe1894e03d4fc22b18b3b41d28",
    "span_states.json": "fb9debe2bb39550446488b2ee7e039abe88d074800c68a49f73beda6a915c519",
    "summary.json": "5fe889721bfc67244b6ef13494338ca23e199cd910306204c4971e45659f84d3",
}

EXPECTED_FIELD_HASHES = {
    "orphan_report.orphans": "d03fc9f5e7a608e8f5e0ac8bffeea9325768b9149a49fbe8d7f82a1e6803ed57",
    "service_rollups.services": "520ea2d63e01b088fb0ca98de5f15dadaceb8048bccd490b15f67f1aa4765179",
    "span_states.spans.s03": "4701eca8eb5f7a5cd01ec3d9cc1f15c72a0670970244aa04dd61562306d264a3",
    "summary.cycle_total": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
}


def _sha256_bytes(data: bytes) -> str:
    """Return hex SHA-256 of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Minified canonical JSON for hash comparison."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load UTF-8 JSON from path."""
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

    def test_output_raw_byte_hashes(self) -> None:
        """Each audit file UTF-8 bytes must match normative layout."""
        for name, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / name).read_bytes())
            assert digest == expected, f"raw byte mismatch for {name}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{name} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match pinned canonical digests."""
        spans = {r["span_id"]: r for r in outputs["span_states.json"]["spans"]}
        assert _sha256_bytes(_canonical(spans["s03"]).encode()) == EXPECTED_FIELD_HASHES["span_states.spans.s03"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["cycle_total"]).encode()) == EXPECTED_FIELD_HASHES["summary.cycle_total"]
        assert _sha256_bytes(_canonical(outputs["orphan_report.json"]["orphans"]).encode()) == EXPECTED_FIELD_HASHES["orphan_report.orphans"]
        assert _sha256_bytes(_canonical(outputs["service_rollups.json"]["services"]).encode()) == EXPECTED_FIELD_HASHES["service_rollups.services"]



class TestSpanSemantics:
    """Semantic checks for merge statuses and latency deduction."""

    def test_s07_missing_parent_orphan(self, outputs: dict[str, object]) -> None:
        """A parent id pointing outside the span set must be classified orphan."""
        spans = {r["span_id"]: r for r in outputs["span_states.json"]["spans"]}
        assert spans["s07"]["merge_status"] == "orphan"

    def test_s08_forced_orphan(self, outputs: dict[str, object]) -> None:
        """Patches forcing orphan must override an otherwise valid parent link."""
        spans = {r["span_id"]: r for r in outputs["span_states.json"]["spans"]}
        assert spans["s08"]["merge_status"] == "orphan"

    def test_timeout_status_present(self, outputs: dict[str, object]) -> None:
        """At least one span must retain the timeout status from fixtures."""
        statuses = {r["status"] for r in outputs["span_states.json"]["spans"]}
        assert "timeout" in statuses

    def test_s02_exclusive_reduced_by_child(self, outputs: dict[str, object]) -> None:
        """Ok parents must shed child duration when deduction is enabled."""
        spans = {r["span_id"]: r for r in outputs["span_states.json"]["spans"]}
        assert spans["s02"]["exclusive_us"] < spans["s02"]["duration_us"]

    def test_cycle_pair_classified(self, outputs: dict[str, object]) -> None:
        """Mutual parent links must mark both spans as cycle members."""
        spans = {r["span_id"]: r for r in outputs["span_states.json"]["spans"]}
        assert spans["s13"]["merge_status"] == "cycle_member"
        assert spans["s14"]["merge_status"] == "cycle_member"
