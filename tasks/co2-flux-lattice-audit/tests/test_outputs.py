"""Verifier suite for the co2 flux lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CFL_DATA_DIR", "/app/flux_lat"))
AUDIT_DIR = Path(os.environ.get("CFL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("ledger.json", "summary.json")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c0a4aac59060dfb090e7b56131032433fb78b2c4bbef0ac31024d6e2b1163fc8",
    "policy.json": "e17e4433af113dcbc9005e7a8d9b63548dd769f0520e7e5281941189adb18765",
    "pool_state.json": "df886dbe9f2773bad815a2045722eea36db743e95871df820146b18d04e0a1fc",
    "incidents.json": "12d18cb0ebd48c77ab0f997b09a3cc33452a37561c179949abf6b56d16386b1d",
    "nodes/n01.json": "630c01e55266e30bce8361a71b1263e170d3d5fa363ee146d7e5561b1c26aaf8",
    "nodes/n02.json": "852384b9da3cd21a6fba899ad7d59f429ba4693551e0564532475a8635ebece2",
    "nodes/n03.json": "3cfb487c78bf80967adbaccef8e21eb80e172af1bfda17e14b8c3b1a7aedab27",
    "nodes/n04.json": "96b4f0167f7462911e6defd21eb289d7b3937719f57ccc208126f5b1d3eaaa18",
    "nodes/n05.json": "a24ba21b5f46e4ca125fd975f8d6769db254d837f7ada177e57ebc43c975012e",
    "nodes/n06.json": "e6ad2f18a239b78c1ab15d6bd146bedd51046137b286b413849301b1fc5b1612",
    "nodes/n07.json": "b3df152dde40443f688e4bdfea489820673769725827c2cfc5a85d45b1c6a62a",
    "nodes/n08.json": "b31ca77c12e70d1a2844c4741db0c5325f5fa7d469e0731aa579ae0106191daf",
    "nodes/n09.json": "92eed23bb18e72ff7f97db9b2a1099f7bc5232b96d674536febe84b2afba5943",
    "nodes/n10.json": "de370d66e5a9510587af8dbeef5e1ab43cb664075a21c5367d55361821bd3be0",
    "nodes/n11.json": "3bc82a875e9e6ac0c49a0c45647f524de706c7fef0f2b474a5f6c075fcf0aa8f",
    "nodes/n12.json": "82cff8d9dcc6615c7152fd18ce85c58c0805c1f7ac1c5799241bed1801e00887",
    "cells/c01.json": "a6721c96c3f9b17a57571e75c9de7796664ea4141e640958675fe8a3027806eb",
    "cells/c02.json": "8c7b656f0ce7713bf138c21c4364e45e4e6a9440fbe6599ffd0056c0853de7c3",
    "cells/c03.json": "789e11b630e0b9a66240a6497739495532a4d11e452a5f3e1cfd3a695d9a2119",
    "cells/c04.json": "583039d4ad469ae11eeebfc25a550c81d5ccf43e0677b94a9409277b2a83b885",
    "cells/c05.json": "b8530f65d6f64d40533158b2df47d5fe9a29f4a9d9a0c5fd7dbaffc49027b8b0",
    "cells/c06.json": "cd8974a3e328879843d68f5c2b48763ed048ec9c955b36ea256c1886bdd24d7b",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "ledger.json": "ba3e86c65f1268c3d9d729872ad890a734ae11f42d5ac9bd138d2b8ce8a4da14",
    "summary.json": "0282671529a9eaa431c3cb30d77d5d05b4496f9ce982c0789d415413432a6ce3",
}


EXPECTED_FIELD_HASHES = {
    "ledger.nodes": "48fc65bec6d0940e581a8edd967136e8610bcf7a3c86dc7939d3823e95590858",
    "summary.max_id": "dfb890a8107310f076acb7d5ee8e36b13379f76f53b1e46e26df5c0d9c302fc2",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit artefacts once per session."""
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
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            digest = _sha256_bytes(_canonical(outputs[name]).encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        ledger = outputs["ledger.json"]
        summary = outputs["summary.json"]
        assert isinstance(ledger, dict) and isinstance(summary, dict)
        assert (
            _sha256_bytes(_canonical(ledger["nodes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["ledger.nodes"]
        )
        assert (
            _sha256_bytes(_canonical(summary["max_id"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.max_id"]
        )


class TestSummarySemantics:
    """Behavioural checks aligned with the published spec."""

    def test_summary_counters_non_negative(self, outputs: dict[str, object]) -> None:
        """Summary counters must be internally consistent non-negative integers."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in ("total_nodes", "stamped", "anchored_live", "frozen_live", "sum_final_scores"):
            assert isinstance(sm[key], int)
            assert sm[key] >= 0
        assert isinstance(sm["max_id"], str)

    def test_ledger_sorted(self, outputs: dict[str, object]) -> None:
        """Ledger rows follow descending final score then ascending id."""
        ledger = outputs["ledger.json"]
        assert isinstance(ledger, dict)
        rows_obj = ledger["nodes"]
        assert isinstance(rows_obj, list)
        prev: dict[str, object] | None = None
        for row in rows_obj:
            assert isinstance(row, dict)
            if prev is None:
                prev = row
                continue
            left = (-int(prev["final_score"]), str(prev["id"]))
            right = (-int(row["final_score"]), str(row["id"]))
            assert left <= right
            prev = row

    def test_sum_final_matches_rows(self, outputs: dict[str, object]) -> None:
        """The summary sum must equal the sum of ledger finals."""
        sm = outputs["summary.json"]
        ledger = outputs["ledger.json"]
        assert isinstance(sm, dict) and isinstance(ledger, dict)
        rows = ledger["nodes"]
        assert isinstance(rows, list)
        total = sum(int(r["final_score"]) for r in rows if isinstance(r, dict))
        assert int(sm["sum_final_scores"]) == total


class TestIncidentKinds:
    """Positive coverage for each incident kind named in the spec."""

    def test_compromise_kind_fixture_present(self) -> None:
        """The frozen incidents list must include an accepted compromise row."""
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(inc, dict)
        kinds = [str(r["kind"]) for r in inc["incidents"] if isinstance(r, dict)]
        assert "compromise" in kinds

    def test_freeze_kind_fixture_present(self) -> None:
        """The frozen incidents list must include an accepted freeze row."""
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(inc, dict)
        kinds = [str(r["kind"]) for r in inc["incidents"] if isinstance(r, dict)]
        assert "freeze" in kinds

    def test_anchor_ok_kind_fixture_present(self) -> None:
        """The frozen incidents list must include an accepted anchor_ok row."""
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(inc, dict)
        kinds = [str(r["kind"]) for r in inc["incidents"] if isinstance(r, dict)]
        assert "anchor_ok" in kinds


class TestFixtureSemantics:
    """Dataset-specific assertions that should survive small fixture edits."""

    def test_frozen_node_respects_floor(self, outputs: dict[str, object]) -> None:
        """Accepted freeze rows must clamp finals to the configured floor."""
        policy = _load_json(DATA_DIR / "policy.json")
        assert isinstance(policy, dict)
        floor = int(policy["freeze_floor"])
        ledger = outputs["ledger.json"]
        assert isinstance(ledger, dict)
        rows = ledger["nodes"]
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            if row.get("frozen"):
                assert int(row["final_score"]) <= floor

    def test_compromised_nodes_zeroed(self, outputs: dict[str, object]) -> None:
        """Compromised ledger rows must carry zero raw scores."""
        ledger = outputs["ledger.json"]
        assert isinstance(ledger, dict)
        rows = ledger["nodes"]
        assert isinstance(rows, list)
        for row in rows:
            assert isinstance(row, dict)
            if row.get("compromised"):
                assert int(row["raw_score"]) == 0
