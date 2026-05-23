"""Verifier suite for go-stream-quorum-audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

DATA_DIR = Path("/app/stream")
REPORT_PATH = Path("/app/audit/report.json")

EXPECTED_INPUT_HASHES = {
    "manifest.json": "2f14972891c0edca268005d0687ad8e83026375b11c515c09407892c28b9ccf3",
    "policy.json": "b2c3692734447a089888979174f922c93f56731593a38e47d45a5239d5cbf7fa",
    "quorum.json": "4665ee231a6e5e38f53d35cae7cdefed53137013b7798e12ef806112c78faf9e",
    "slices/s01.json": "8fb7daf2075f09210ccf2de44ccbbf6d2edcb02f10a9854eed01d086faa1e8b4",
    "slices/s02.json": "5951bafdc23d5906ffd27e5c1f1ed1326651dfd8f9a2af32e4f714dd250a16a8",
    "slices/s03.json": "f54c4adffe169659f3fd964ac944ee60078fdc876102b9e9ef54ebe39309f389",
    "slices/s04.json": "ce6465d1c95b275ecc3999d4e1137c60b66b7c545b1a979f8a7b8db76d3de3c3",
    "slices/s05.json": "36643ece66dc3b2701d38c662778325bd223902d2a7639fd6cab32e958dd5af6",
    "slices/s06.json": "03bace81cada44417f00af8ebd6a2684bc6009e7a701e16ed4f92b8193b9c76f",
    "slices/s07.json": "7a0617be31f1f109ed904d0792e7e1d0e87a401c9eb7ca9582c6ff03bd6eba7d",
    "slices/s08.json": "3139c057fa5c10d48d76c5564d9f34f8b1dae6a86e9a8f8e8a26dd327b572295",
    "slices/s09.json": "400671b4e9cec0da88750bf0c549ac28ba6a9b09f961e665091f9c1598d8d44a",
    "slices/s10.json": "9711512574e6df63dd915e2d0343439b1b0c11b988efe9d7a6e152da95120edb",
    "slices/s11.json": "a1d82a9bbb6653b6bdb85a31b47db04639c7c5b443451120232a9fa12257c365",
    "slices/s12.json": "ecf42098a8ae67b0f6e1186c71a7a678df7eff80761c9d623a9da3e4c75b0b43",
    "slices/s13.json": "b81877802d3854082d9b547d1fe060950e66a16fb8d9654063b3c9c075eea9e2",
    "slices/s14.json": "b92e922c3fcbe28a3cd72ed27557dcddc348995bc45ca425e035c4e89e8a53f2",
    "slices/s15.json": "c4497fd1095f5f4e57cde6d6de5c48b9a34a3ac176941d467f65f82a579e1140",
    "slices/s16.json": "30ed5717db1f6b2b9899ba3edb93b8fd62d68b1c6f99c335209b4ed3cf2a021a",
    "slices/s17.json": "7845918259fba219d1369228b556427e800ad448908e82922f5660612c7461aa",
    "slices/s18.json": "f288c961fe241b21e3ac2c401e1fb0dd84e65c786ff0f0f5a839259e8a301405",
    "slices/s19.json": "92af577c9c98c13e3e0592c27c51ab6dd80229bbce1d0c856a8ec86098feea1a",
    "slices/s20.json": "a5338d955b09046ec0b16f3a9625b7955c763aae07dc722e474e6078745f932f",
}

EXPECTED_REPORT_HASH = "a5497e5c9ae120d03f10af8d0a2f1473d9d72afe6009a7c2af253e4feb0bec71"
EXPECTED_FIELD_HASHES = {
    "ballots": "57286ace2673873626af99260b2b2ae3c00230898e2ecd676d5e3eb0e7294ecd",
    "decisions": "50dd215c3f64e1fcb3c2d1c3c1ed79736cb2841362547117cc2e9cbbaba5cf83",
    "stale": "e58e3dce342df64ced9a2478ece97e99c8ebb4359b833d37e01db668054d81f4",
    "summary": "26caebf9a4830abac69630731722eb1fa6e62ce2cd9806258334b5a53071e077",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha(obj: object) -> str:
    return _sha256_bytes(
        (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf-8"
        )
    )


@pytest.fixture(scope="module")
def loaded_report() -> dict[str, object]:
    """Load the emitted quorum report once for the module."""
    text = REPORT_PATH.read_text(encoding="utf-8")
    return {"bytes": text.encode("utf-8"), "obj": json.loads(text), "text": text}


class TestInputIntegrity:
    """Bundled stream inputs must remain byte-stable."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES))
    def test_input_file_unchanged(self, rel: str) -> None:
        """Each input file must match its pinned SHA-256 digest."""
        path = DATA_DIR / rel
        assert path.is_file(), f"missing input file {path}"
        assert _sha256_file(path) == EXPECTED_INPUT_HASHES[rel]


class TestReportStructure:
    """The report must exist and use the documented deterministic formatting."""

    def test_report_exists(self) -> None:
        """The program must emit the quorum report at the documented path."""
        assert REPORT_PATH.is_file(), "missing /app/audit/report.json"

    def test_no_extra_audit_files(self) -> None:
        """The audit directory must contain only the documented report file."""
        actual = sorted(path.name for path in REPORT_PATH.parent.iterdir() if path.is_file())
        assert actual == ["report.json"]

    def test_top_level_keys(self, loaded_report: dict[str, object]) -> None:
        """The report must expose exactly the four required top-level keys."""
        obj = loaded_report["obj"]
        assert isinstance(obj, dict)
        assert list(obj.keys()) == ["ballots", "decisions", "stale", "summary"]

    def test_pretty_sorted_ascii_json(self, loaded_report: dict[str, object]) -> None:
        """The on-disk JSON must equal sorted, 2-space-indented ASCII output."""
        expected = json.dumps(
            loaded_report["obj"], indent=2, sort_keys=True, ensure_ascii=True
        ).encode("utf-8")
        assert loaded_report["bytes"] == expected

    def test_no_trailing_newline(self, loaded_report: dict[str, object]) -> None:
        """The file must end at the final closing brace."""
        assert not loaded_report["bytes"].endswith(b"\n")

    def test_report_hash(self, loaded_report: dict[str, object]) -> None:
        """The full report value must match the pinned canonical hash."""
        assert _canonical_sha(loaded_report["obj"]) == EXPECTED_REPORT_HASH


class TestFieldHashes:
    """Each top-level report field must match its pinned canonical value."""

    @pytest.mark.parametrize("field", ["ballots", "decisions", "stale", "summary"])
    def test_field_hash(self, loaded_report: dict[str, object], field: str) -> None:
        """Every top-level field must match its canonical hash."""
        assert _canonical_sha(loaded_report["obj"][field]) == EXPECTED_FIELD_HASHES[field]


class TestSemantics:
    """Spot-check summary counters and representative quorum paths."""

    def test_summary_counters(self, loaded_report: dict[str, object]) -> None:
        """The summary counters must match the expected derived values."""
        summary = loaded_report["obj"]["summary"]
        assert summary["rows_seen"] == 50
        assert summary["rows_dropped_watermark"] == 2
        assert summary["rows_deduped"] == 3
        assert summary["groups_total"] == 21
        assert summary["groups_quorum"] == 11
        assert summary["stale_logged"] == 13

    def test_prepare_and_commit_phases_present(self, loaded_report: dict[str, object]) -> None:
        """The bundled workload must exercise both prepare and commit phase groups."""
        phases = {phase[0] for ballot in loaded_report["obj"]["ballots"] for phase in ballot["phases"]}
        assert phases == {"commit", "prepare"}

    def test_open_status_present_in_ballots(self, loaded_report: dict[str, object]) -> None:
        """At least one phase group must remain open when counted weight is below threshold."""
        statuses = {phase[1] for ballot in loaded_report["obj"]["ballots"] for phase in ballot["phases"]}
        assert "open" in statuses

    def test_quorum_status_present_in_ballots(self, loaded_report: dict[str, object]) -> None:
        """At least one phase group must reach quorum when counted weight meets threshold."""
        statuses = {phase[1] for ballot in loaded_report["obj"]["ballots"] for phase in ballot["phases"]}
        assert "quorum" in statuses

    def test_decisions_count_matches_summary(self, loaded_report: dict[str, object]) -> None:
        """Every quorum group must appear in decisions and only quorum groups may appear."""
        summary = loaded_report["obj"]["summary"]
        decisions = loaded_report["obj"]["decisions"]
        assert len(decisions) == summary["groups_quorum"]
        quorum_keys = {
            (ballot["stream"], ballot["epoch"], phase[0])
            for ballot in loaded_report["obj"]["ballots"]
            for phase in ballot["phases"]
            if phase[1] == "quorum"
        }
        decision_keys = {(row["stream"], row["epoch"], row["phase"]) for row in decisions}
        assert decision_keys == quorum_keys

    def test_prepare_quorum_alpha(self, loaded_report: dict[str, object]) -> None:
        """Alpha epoch 1 prepare must reach quorum after dedupe and watermark drops."""
        ballots = loaded_report["obj"]["ballots"]
        alpha = next(b for b in ballots if b["stream"] == "alpha" and b["epoch"] == 1)
        prepare = next(p for p in alpha["phases"] if p[0] == "prepare")
        assert prepare[1] == "quorum"
        assert prepare[2] == 3

    def test_commit_escrow_gamma_open(self, loaded_report: dict[str, object]) -> None:
        """Gamma commit without prepare quorum must stay open when only escrow votes count."""
        ballots = loaded_report["obj"]["ballots"]
        gamma = next(b for b in ballots if b["stream"] == "gamma" and b["epoch"] == 1)
        commit = next(p for p in gamma["phases"] if p[0] == "commit")
        assert commit[1] == "open"
        assert commit[2] == 6

    def test_stale_late_tick_code(self, loaded_report: dict[str, object]) -> None:
        """Stale entries on open groups must use the LATE_TICK code."""
        stale = loaded_report["obj"]["stale"]
        assert any(row["code"] == "LATE_TICK" for row in stale)

    def test_theta_manifest_order_dedupe(self, loaded_report: dict[str, object]) -> None:
        """Theta prepare must keep the later-slice row when duplicate ticks tie."""
        ballots = loaded_report["obj"]["ballots"]
        theta = next(b for b in ballots if b["stream"] == "theta" and b["epoch"] == 1)
        prepare = next(p for p in theta["phases"] if p[0] == "prepare")
        assert prepare[2] == 3

    def test_delta_prepare_quorum_after_late_watermark_gate(self, loaded_report: dict[str, object]) -> None:
        """Delta prepare reaches quorum because late rows kept past the watermark gate still count once tick >= policy.watermark."""
        ballots = loaded_report["obj"]["ballots"]
        delta = next(b for b in ballots if b["stream"] == "delta" and b["epoch"] == 1)
        prepare = next(p for p in delta["phases"] if p[0] == "prepare")
        assert prepare[1] == "quorum"
        assert prepare[2] == 3

    def test_lambda_epoch2_commit_blocked_by_chain(self, loaded_report: dict[str, object]) -> None:
        """Lambda epoch 2 commit stays open because epoch 1 never became prepare-quorate."""
        ballots = loaded_report["obj"]["ballots"]
        lam = next(b for b in ballots if b["stream"] == "lambda" and b["epoch"] == 2)
        prepare = next(p for p in lam["phases"] if p[0] == "prepare")
        assert prepare[1] == "quorum"
        commit = next(p for p in lam["phases"] if p[0] == "commit")
        assert commit[1] == "open"

    def test_gamma_commit_escrow_exempt_from_stale(self, loaded_report: dict[str, object]) -> None:
        """Open gamma commit skips stale logging for escrow voters when prepare never quorates."""
        stale = loaded_report["obj"]["stale"]
        gamma_stale = [r for r in stale if r["stream"] == "gamma" and r["phase"] == "commit"]
        voters = {r["voter"] for r in gamma_stale}
        assert "c1" not in voters
        assert {"c2", "c3"}.issubset(voters)
