# scaffold-status: oracle-pending
"""Verifier suite for dns-alias-chain-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("DAC_DATA_DIR", "/app/dnschain"))
AUDIT_DIR = Path(os.environ.get("DAC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('record_states.json', 'chain_plan.json', 'type_votes.json', 'query_stats.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "anchors/b1.txt": "456d0a1656a4c8c27c0e2600125e33445a0e026b92f539f9935e88315f1b5ef3",
    "anchors/b2.txt": "930b87bb024486caf959f75f4776e9d89e3c29b76fac9a0af7ea09b81cdbfb19",
    "ancillary/meta.json": "cc507d357dfab25da0d9610d54f2b59d09dd6eaa9ee97ab4030d3bf5f2474171",
    "ancillary/notes.json": "e0f5fcae30068156d37c73608f46020562e6e97bb4d89e3240ffd041cb2d6fcf",
    "epochs.json": "663c9b59a5d258b8738eba907edef52631a7e8ff136c4cbd8a16b1e39b53338d",
    "grid/dims.json": "473fe2a850b82d2d981070f8b927487e44c4b0e7d6fb13b96047f064273cd03f",
    "manifest.json": "f1d3fd2d1dbcbb28430a17d61ca61350463b3efdf86104415cdd9f5214ac1a54",
    "meta/seq.json": "12458d61557f106a59d1fbf80c4af4da737946699c2f2e93e3422bf0c9015919",
    "policy.json": "d5664f9aa3740d986ea4958910dfd31f5093cf73d9e6fc0e59e9cfc11935c8fe",
    "queries.json": "d3beb4365ab60839e17b762e2c304be8afc766abad71849fa14638630e3c3626",
    "records/api_example.json": "1b7e79498530c10aebe1770c57b353386cd8a77e964c02ed75c62f102a758bae",
    "records/app_example.json": "3dde7640895355c0c1bee8e65830c9daf2e576f69573c3f1810cc6618fdfdf4e",
    "records/cdn_example.json": "9ce188e298c60417a395b12265c24afb923e04452f582eccea930333c646a1ff",
    "records/deny_example.json": "ae70e3638b67af3bb9e8942ed022f237e1d2decef7996544f4362d39b96e7b57",
    "records/edge_example.json": "3cc0b99eadc19fc1ace7b6433501c0c2cdce32bd4983f16d56920aeca431cd0b",
    "records/ftp_example.json": "26e4e3fa039bf079ee71f24cbeab864cb0ec4f22a60be4fc688532a462f1bf6b",
    "records/loop_a.json": "e8e7564ef64f05c04fae27ad01cfb9ab6978797db8c9900804861503b37ed5bc",
    "records/loop_b.json": "859745b87a6fb6f9ea1ec2b04633115b4b1633a6e5159319dbef1d9ecbf60c58",
    "records/mail_example.json": "48b1a7441c0bd2fa8b536351b8d7113fddd93edd3c2bd30c3b830eac3e5629b0",
    "records/old_example.json": "132733974cc0109df6660d2120102c3b144da318061d93cd6f7ce37657ae4ac5",
    "records/svc_example.json": "dbb385782a9b0391e320859720fe666c98a90f6b7b1129f65f82ea763d0c0900",
    "records/www_example.json": "9ffc130a2a02da1b55f5dcacd1be11ede60f470cfd7cdca33fd673e7d23b57e0",
    "SPEC.md": "b98e38f63329e2b479fb40a6584938bf4570501ee5a01a45af39dd6e4a6e8d74"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "record_states.json": "ebc7ea21bb6e88ed7b8f3594c6b36256e71361a53ad067e65fdc35273b3cf21a",
    "chain_plan.json": "022e7272768b023408c9e4b03ac8c24fb796595a8c9b9d520f35e1a42417a8c5",
    "type_votes.json": "50c56012dc38bab35dba05703c91467d3f233e3a75d7238371dc2218af4cc7a9",
    "query_stats.json": "ba9633cfc54e753cdbb7914c8cd253e16af80a2918d222caba419b5d7c6d6ecf",
    "summary.json": "fc2f9a3dfa76223ea9e438e3dbdd0198d8f9bd9cdb42cf6a5d2e171961a40566"
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "record_states.json": "3b0cd702942d2abbce171315d029e9faf1c46a0003539f3453b62a897418b7a3",
    "chain_plan.json": "d8afe31f91966af3c1c2c0b4d6b237d5852faffac2e002f166d66629f0047e2c",
    "type_votes.json": "e2fef5b09e8d4a20608e0410038643cf427b4c53de8ed88f080aa32affdacfaa",
    "query_stats.json": "c39e7c66c2e8c7e2ca3b731b0dd80dc18b18dd3e3caa4428e5fd85ed13363b5e",
    "summary.json": "85d1cab050980a9b688e6c8194fcc846159e49625bc1c7991afc1ddbc70cd0ae"
}

EXPECTED_FIELD_HASHES = {
    "chain_plan.entries": "b4572d7b84a0fe17490cc58ac25ff22aa628f124227d8930516fdf6c5acfd0ef",
    "summary.effective_max_chain": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
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
    for fname in OUTPUT_FILES:
        path = AUDIT_DIR / fname
        assert path.is_file(), f"missing emitted artifact: {fname}"
        payload[fname] = _load_json(path)
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
        for fname, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            digest = _sha256_bytes((AUDIT_DIR / fname).read_bytes())
            assert digest == expected, f"raw byte mismatch for {fname}"

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for fname, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[fname])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {fname}"

    def test_output_files_single_trailing_newline(self) -> None:
        """Root JSON objects must end with exactly one line feed after the closing brace."""
        for fname in OUTPUT_FILES:
            raw = (AUDIT_DIR / fname).read_text(encoding="utf-8")
            assert raw.endswith("}\n"), f"{fname} must end with exactly one LF after root brace"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match pinned canonical digests."""
        assert _sha256_bytes(_canonical(outputs["chain_plan.json"]["entries"]).encode()) == EXPECTED_FIELD_HASHES["chain_plan.entries"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["effective_max_chain"]).encode()) == EXPECTED_FIELD_HASHES["summary.effective_max_chain"]


class TestSemantics:
    """Semantic checks for compound audit rules."""

    def test_effective_max_chain_halved(self, outputs: dict[str, object]) -> None:
        """Zone-run tag mismatch must halve max chain via integer floor division."""
        assert outputs["summary.json"]["effective_max_chain"] == 3

    def test_warmup_query_not_collapsed(self, outputs: dict[str, object]) -> None:
        """Queries inside warmup must not collapse chains."""
        entries = outputs["chain_plan.json"]["entries"]
        warm = [e for e in entries if e["step"] <= 2]
        assert warm and all(not e["collapsed"] for e in warm)

    def test_stale_record_skips_chain_row(self, outputs: dict[str, object]) -> None:
        """Stale records must not appear in chain_plan."""
        states = {r["name"]: r for r in outputs["record_states.json"]["records"]}
        chain_names = {e["name"] for e in outputs["chain_plan.json"]["entries"]}
        assert states["old.example"]["stale"] is True
        assert "old.example" not in chain_names

    def test_loop_query_not_in_chain_plan(self, outputs: dict[str, object]) -> None:
        """Looped alias walks must omit chain_plan rows."""
        stats = [s for s in outputs["query_stats.json"]["stats"] if s["name"] == "loop.a"]
        assert stats and stats[0]["looped"] is True
        chain_names = {e["name"] for e in outputs["chain_plan.json"]["entries"]}
        assert "loop.a" not in chain_names

    def test_deny_blocked_not_collapsed(self, outputs: dict[str, object]) -> None:
        """Deny records must block collapse even when aliases exist."""
        stats = [s for s in outputs["query_stats.json"]["stats"] if s["name"] == "deny.example"]
        assert stats and stats[0]["deny_blocked"] is True
