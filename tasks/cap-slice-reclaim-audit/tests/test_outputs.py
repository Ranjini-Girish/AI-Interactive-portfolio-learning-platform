# scaffold-status: oracle-pending
"""Verifier suite for cap-slice-reclaim-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CSR_DATA_DIR", "/app/capslice"))
AUDIT_DIR = Path(os.environ.get("CSR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ('slice_states.json', 'reclaim_plan.json', 'tier_votes.json', 'window_stats.json', 'summary.json')

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "05308fc5ead915bc480f1b1c917379352caf038659779655bc37b4d091125271",
    "anchors/a1.txt": "72e2c95bfd7d21fd2b39c4a4ded4cbd930001335dab65d2d281a7707500cfe47",
    "anchors/a2.txt": "72e2c95bfd7d21fd2b39c4a4ded4cbd930001335dab65d2d281a7707500cfe47",
    "ancillary/meta.json": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "ancillary/notes.json": "a515956717967bf2ce4531f69c7c880aa4b2dc82626c02ec23d6d3e0acab174e",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "events.json": "ab9b07586796bf885c83f0893391e3c3d9d4a0df92312192a0a947034f90013a",
    "grid/dims.json": "a868c2544d62212fe183639919ce8ca7e4956491a02bbc6b80e0a0e33bde61a8",
    "manifest.json": "7ac3e17351d43c5ca04bd9cc738dffe9298290c00c5d1a577200f76097606cdb",
    "meta/seq.json": "49095e39cd4021c534ff57d1a73f28ab8b93210997785fe8dd0cce961c09dd3a",
    "policy.json": "04a73a3157807fe611e64bde43d3a4a611d71cb4e189d85b960da0d665acb3f5",
    "slices/sl01.json": "1ea7cb4fdbafa4067884dddc189a114de2a9d9f153b65dcc58221751ea0d0138",
    "slices/sl02.json": "086741afb90295f8136cb817957ad7819799e77ffe868d236faca12ce6e88c6e",
    "slices/sl03.json": "8277bbd6380846883e34d13242fda5bab9b1767424618e296269dd7fb701e9ee",
    "slices/sl04.json": "e86e5899ba402276d0231eb37e35b45ebc9854373fcbea8d649aae7fcc74bf41",
    "slices/sl05.json": "75fbe47ec4e0bc2b28ac7e895f65654f9c7b8f0283139907b0b30a3ea79ea813",
    "slices/sl06.json": "892894ab5ea6df4b9bb337fd647c46f367bd61f140d754e96dda8e3020d13e8e",
    "slices/sl07.json": "65045119cca3d3c65e726ce1434353fc6aa941d62099df45bd6a63a54cebd8e9",
    "slices/sl08.json": "e7c07de21fe0ec6f7ec3b2dc989ce29609a5ff92d7f2351367b25752b493defa",
    "slices/sl09.json": "e5921f3e2c99544f3b93e8373c612aa7037c923229737f83093f2c6c2fcc0670",
    "slices/sl10.json": "8ddd789c5f22036a9c1decd37796528526e6a534155557fe638716f764c7a0fc",
    "slices/sl11.json": "4c12f1ea0988c0c56bb308c0880a1521878ce6c378ff3641b0883b3cfd98a2b8",
    "slices/sl12.json": "74e0497a6f63b8e40dce90fbe2690ffdbd0c4ca59ac37c3f4d62c49efa0981ab",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "reclaim_plan.json": "606733d44ce5b47a11dd5239dea8d929536c1c7dc827a62a43ff8b4c6a7cfcbf",
    "slice_states.json": "da65c52e71fe177adb08a9748ddaa5c7edba1258415842430403965b64acc54b",
    "summary.json": "5ec792a970eabe2bf8d457c086c32c0be903bfe68df029f4332dc599c9a0c94b",
    "tier_votes.json": "e086d011a67768838adbde701e65c8bb9ffb7eaed97437cc497d6e9d80a7b17b",
    "window_stats.json": "c4667e3bc648da208e307073258fb0b60dcda2fc5f8528ea144774c9195ae05e",
}

EXPECTED_OUTPUT_RAW_HASHES = {
    "reclaim_plan.json": "3d8d71f3b35739dba45c1b26a589efcbc1ccfc959c124862edc8f0ae761346da",
    "slice_states.json": "23c69c4cb6a8eca283c0b8e7f7aeb70d0e1773d40e9a38b63cf0e6f7a9260ab0",
    "summary.json": "6aed410fc0c53b7780ae5ef9bb432c4c3b2ef9536e3f62de4f563493bfb768f9",
    "tier_votes.json": "4446689375881470032b6f6b2d516454f4a26d9c1a1e5616b5cfea64a827bdd8",
    "window_stats.json": "ab650df079eb838878d681364658bea04e237e1d63cf0f17922b6ea468181ade",
}

EXPECTED_FIELD_HASHES = {
    "reclaim_plan.entries": "2a8bf4ada966c115cc9321dd3e66d83699351deb53fd6f0ad61c9613c5a952f8",
    "summary.effective_soft_cap": "f97a13577367c1d604d37c4d2b6242d7193c7ba04aa4d1a64c322b23b2f9bd2a",
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

        assert _sha256_bytes(_canonical(outputs["reclaim_plan.json"]["entries"]).encode()) == EXPECTED_FIELD_HASHES["reclaim_plan.entries"]
        assert _sha256_bytes(_canonical(outputs["summary.json"]["effective_soft_cap"]).encode()) == EXPECTED_FIELD_HASHES["summary.effective_soft_cap"]


class TestReclaimSemantics:
    """Semantic checks for halving, warmup, stale slices, and tier votes."""

    def test_effective_soft_cap_halved(self, outputs: dict[str, object]) -> None:
        """Monitor-run tag mismatch must halve the soft cap in summary."""
        assert outputs["summary.json"]["effective_soft_cap"] == 50.0

    def test_warmup_step_not_reclaimed(self, outputs: dict[str, object]) -> None:
        """Steps inside warmup must keep reclaim_factor at zero."""
        entries = outputs["reclaim_plan.json"]["entries"]
        warm = [e for e in entries if e["step"] <= 2]
        assert warm and all(e["reclaim_factor"] == 0.0 for e in warm)

    def test_stale_slice_skips_reclaim_row(self, outputs: dict[str, object]) -> None:
        """Stale slices must not appear in reclaim_plan."""
        states = {r["slice_id"]: r for r in outputs["slice_states.json"]["slices"]}
        reclaim_ids = {e["slice_id"] for e in outputs["reclaim_plan.json"]["entries"]}
        assert states["sl12"]["stale"] is True
        assert "sl12" not in reclaim_ids

    def test_low_tier_vote_rejected_on_hot_step(self, outputs: dict[str, object]) -> None:
        """A lone low tier on a contested step must fail tier acceptance."""
        votes = [v for v in outputs["tier_votes.json"]["votes"] if v["step"] == 3 and v["tier"] == "low"]
        assert votes and not any(v["accepted"] for v in votes)

