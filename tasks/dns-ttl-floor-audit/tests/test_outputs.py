# scaffold-status: oracle-pending
"""Verifier suite for dns-ttl-floor-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("DTF_DATA_DIR", "/app/dnsfloor"))
AUDIT_DIR = Path(os.environ.get("DTF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "cname_hops.json",
    "floor_violations.json",
    "query_outcomes.json",
    "record_states.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "941272752bd5c32250316c925e989a1e8c64e371b5becf9e76fb278b38c9e2f0",
    "anchors/a1.txt": "0081d925ae6ffbf232e997d5fabc1bfe9912e493f69296104270557a5950d63f",
    "anchors/a2.txt": "cd10fbef69a6c7045ac67498cf013dcae238377d34a02657afe06a7ba9ee5605",
    "ancillary/meta.json": "30e0a7b3cd6ee2e765bd21416062f6a91d31e083e9a02ba0c6f28d754d4a6846",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "ancillary/zones.json": "ba7987cf424f2a2f487f2de783b5302dd3e4b268c8fb15d5ef4b181fb62cc60c",
    "epochs.json": "8a9dce6a2de892a5d902064c7398c15b6132106e3632c6289cf001fc8b67a6c9",
    "grid/dims.json": "6dfc05286939c4657697ed2d6a304c679787ebb1eca82e25fa02410d88069654",
    "manifest.json": "6a65340b3072cb6441915ac27c3e9e7776c8c021f264bdca5c6a9883d880e418",
    "meta/seq.json": "113ae8c4b2d22a73be65a82c62b00f278d0ed84640ed2ff955f091c39618c579",
    "policy.json": "e18af539909bd8274117c886e752349aab19992f06447608abddf1f5386e95cd",
    "queries.json": "aacad1eaf3800e837b46ec74188e63c726e8da5c77cb80b238da789ecd17459c",
    "records/rec_a.json": "8eb1cfb53e8e57e40158381ade2d5b52f04b706d6c531d15347326caf1c851d2",
    "records/rec_b.json": "7e0b62e29a4860e20a7257a98cd3d7535c0825c9c5ce42595bb266d110b10573",
    "records/rec_c.json": "b88c7b72c62fd5ec12ee099c927d2bda0119f25148202963e6034855f4c4333e",
    "records/rec_d.json": "e0a7c6d29e4d756eb9ea8de069886be0cc8a6ec4cd831f67c1ce19fd72e49e56",
    "records/rec_e.json": "d295852f6bcd197a25acdbf8e39827598aa052f01c892e8d8a42308702923ddb",
    "records/rec_low.json": "7d525ad2e5a01ff174782914778871b0ba25bca7afe10195799ced638e9f9235",
    "records/rec_old.json": "fa697eb0489122d94d6e7ed55b744fbccc29e998f7732beb3fe8acdd1d871308",
    "records/rec_x.json": "c3d11575c8e61bac565f53b34829aa68be0e5822038c865737ee588debb07dba",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cname_hops.json": "001862776a9f0dca929f7a3dc2c029737966a75d5fdba0e3d2b3f9ef2070659e",
    "floor_violations.json": "2279e6d652835592329becec6a254fe7da586859833bde1eebdeedaa529a91e3",
    "query_outcomes.json": "65f59c0902dd90836c5df85579120e081f4d352245ff0530d69944c4083c46da",
    "record_states.json": "1cacbbe469db8d3275791ba422f0e1c186f1e6f8b9788054126750200cce5489",
    "summary.json": "67f194b589da981207c829b3b32da9b9f343f2002865b589e0911b2f4f057089",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "cname_hops.json": "a88caada5b9f74b6b0be209149f8605fae2293fdc65bbe5976ce2f6b090a8d0e",
    "floor_violations.json": "fdc04fb5b655744c675a28ea4f266883ab86cb1968233be2f20e8f3ada11aafd",
    "query_outcomes.json": "11877fe3fc139efa7ff530c28861e5589f725c1df44aa1ebf6be92cab7f51d38",
    "record_states.json": "ea48f18222537e330b8621a5f569623862340a8234375f9a8b8f564927194154",
    "summary.json": "a9e4f76d8c91ac89bb62b3e9635f93d5cbef2593e753adae166e6c862946e936",
}

EXPECTED_FIELD_HASHES = {
    "summary.effective_ttl_floor": "6af1f692e9496c6d0b668316eccb93276ae6b6774fa728aac31ff40a38318760",
    "floor_violations.floor_breach": "2279e6d652835592329becec6a254fe7da586859833bde1eebdeedaa529a91e3",
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
        assert (
            _sha256_bytes(
                _canonical(outputs["summary.json"]["effective_ttl_floor"]).encode()
            )
            == EXPECTED_FIELD_HASHES["summary.effective_ttl_floor"]
        )
        assert (
            _sha256_bytes(_canonical(outputs["floor_violations.json"]).encode())
            == EXPECTED_FIELD_HASHES["floor_violations.floor_breach"]
        )


class TestDnsFloorSemantics:
    """Semantic checks for zone spill, warmup, CNAME depth, and floor breach."""

    def test_zone_spill_raises_effective_floor(self, outputs: dict[str, object]) -> None:
        """Mismatched zone tags must raise effective_ttl_floor via spill_ratio."""
        assert outputs["summary.json"]["effective_ttl_floor"] == 240

    def test_warmup_skipped_outcome_present(self, outputs: dict[str, object]) -> None:
        """Warmup steps must record warmup_skipped without hop rows."""
        outcomes = {q["outcome"] for q in outputs["query_outcomes.json"]["queries"]}
        assert "warmup_skipped" in outcomes

    def test_floor_breach_on_low_ttl(self, outputs: dict[str, object]) -> None:
        """Raw ttl below the effective floor must be floor_breach."""
        row = next(
            q
            for q in outputs["query_outcomes.json"]["queries"]
            if q["record_id"] == "rec_low"
        )
        assert row["outcome"] == "floor_breach"

    def test_cname_depth_exceeded_outcome(self, outputs: dict[str, object]) -> None:
        """Chains longer than cname_depth_max must be cname_depth_exceeded."""
        row = next(
            q
            for q in outputs["query_outcomes.json"]["queries"]
            if q["record_id"] == "rec_c"
        )
        assert row["outcome"] == "cname_depth_exceeded"

    def test_stale_skipped_outcome(self, outputs: dict[str, object]) -> None:
        """Stale records must not produce hop rows."""
        row = next(
            q
            for q in outputs["query_outcomes.json"]["queries"]
            if q["record_id"] == "rec_old"
        )
        assert row["outcome"] == "stale_skipped"
        hop_ids = {h["record_id"] for h in outputs["cname_hops.json"]["hops"]}
        assert "rec_old" not in hop_ids

    def test_missing_record_outcome(self, outputs: dict[str, object]) -> None:
        """Unknown record ids must be missing_record."""
        row = next(
            q
            for q in outputs["query_outcomes.json"]["queries"]
            if q["record_id"] == "rec_missing"
        )
        assert row["outcome"] == "missing_record"

    def test_ok_cname_hop_min_ttl(self, outputs: dict[str, object]) -> None:
        """Successful CNAME resolution must use min hop ttl on rec_b chain."""
        hop = next(
            h for h in outputs["cname_hops.json"]["hops"] if h["record_id"] == "rec_b"
        )
        assert hop["effective_ttl"] == 250
