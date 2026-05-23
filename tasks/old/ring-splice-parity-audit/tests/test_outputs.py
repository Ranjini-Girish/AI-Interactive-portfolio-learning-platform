"""Verifier suite for ring-splice-parity-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

RSP_DATA_DIR = Path(os.environ.get("RSP_DATA_DIR", "/app/ring_splice"))
RSP_AUDIT_DIR = Path(os.environ.get("RSP_AUDIT_DIR", "/app/audit"))

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5ce4607b60ba7dd2adc00b66727876d0b22b8d05c069761e66210035c0287ca1",
    "catalog.json": "a3618a176ba7e274df36d1567af8801494ba0610fe762cc52d962ba6a53aefd4",
    "incidents.json": "fed6469cfbf172ad1ead7707eba9305603f2495417391b1e2079ca9dd17afc8c",
    "policy.json": "4eca08f4b7a26f261554b57129dccc03a3f4682149cec1c4b0bd4f1a7d42f321",
    "snapshots/2024-03-01/alpha.json": "01cd17079f8ede841e696b9002337d3f333e0d2c844325f84e4f38d0f19c0639",
    "snapshots/2024-03-01/beta.json": "f8e6cfcbf3afbba1bbad933502a1123ba8b7a0950d0a99413beeaa4fc01bb764",
    "snapshots/2024-03-01/delta.json": "2333c8c68b4ac4a9c1a2946768ecdfae769a82472e931853b2ed7d70cc8ac298",
    "snapshots/2024-03-01/gamma.json": "d31c5703a08db6f1bef5dd43d50bb239b5a428ff6a446c2159091a5d953e3a30",
    "snapshots/2024-03-02/alpha.json": "e7b32350d0b87dc7eb234889827e8d1f2d7c132486ba9ef46f8a85e1a4dfb027",
    "snapshots/2024-03-02/beta.json": "b0331bc862ea1fa7ae279114b725a91e7054b97a451df6ba3703b8aa1d847c6e",
    "snapshots/2024-03-02/delta.json": "9bab20b3f7549b13b6f30924790cc042b60012ff08f74285e911afdd4b06cef0",
    "snapshots/2024-03-02/gamma.json": "26f9e5d1521b738c5c3a4eb0d3ed1259bc859b04adb1c5e65c034c9f5cd902a8",
    "snapshots/2024-03-03/alpha.json": "459dd93d026a6e41909f551baf36d0038e1bff330c0a39218038e606ced590b8",
    "snapshots/2024-03-03/beta.json": "d1034c0fad7e84d51c2e4d92a6953d46875fb798d9c916feefc5dfbc40860658",
    "snapshots/2024-03-03/delta.json": "aded13f65c743eca688b7a0f939392bf6d1c5333f48c8fe7cee1ff89666c1f5e",
    "snapshots/2024-03-03/gamma.json": "b4ec215744a5043dcb89128ded73fd69bc968850a7be6cf278f93547721cd97c",
    "snapshots/2024-03-04/alpha.json": "1f5da910a822703917833ec83d4498dc4049eee2394ae3cc8333acf6fa692d28",
    "snapshots/2024-03-04/beta.json": "fed043e405840f3f8bca21d0d989b9077e6120f9fba522cd983b4dc20b1e4d14",
    "snapshots/2024-03-04/delta.json": "96ad0392d169094e87b675faf7ced93dec2171ca64b3b9768511c71c8c213435",
    "snapshots/2024-03-04/gamma.json": "1e72cc289744136458503aded9ae03c2d0e83e31472c734ba8bc07159e1089a8",
    "snapshots/2024-03-05/alpha.json": "f7147ac510506501bb40fb29a1a236288aad86f315a6d701c5e0f1c677b4ab69",
    "snapshots/2024-03-05/beta.json": "57c277259320192682bd0ea66bbbcd7ad45b1af5aa0139514ce49e002c36086c",
    "snapshots/2024-03-05/delta.json": "a323a5114c79492d3d37d3fdead3ba9a7964c00817f8b1c177d4448fc574e091",
    "snapshots/2024-03-05/gamma.json": "d7bd9a5ccc958cdcb58061663878b78822fcc068cb9ef50ddd00da2582cc1cda",
}

EXPECTED_OUTPUT_FILE_SHA256 = {
    "incident_suppression.json": "3f7bf873ad5eaf47efc4c64296fe827f4c870626eac19794cfd2f67a37c26d5e",
    "overrun_ledger.json": "ea17899d37515f53ef5262d46e9c6418c362fd04bacbcd55d127ea4e1e053011",
    "splice_inventory.json": "5141b55b9f4a14734fe3a28640c65947ae337c949b2a945748d0edebb294dd07",
    "watermark_tier_matrix.json": "1f8a6a2af6fb0812c9ad603ba67aa5f1c256919ecdb5e07ebdac5a023b1b5507",
    "wrap_parity_report.json": "ae689dc2624d3963d1acb282910a4dcfd584cc16ef1a3ed98cff2d57026b4196",
}

EXPECTED_FIELD_HASHES = {
    "incident_suppression.json:severity": "90769889350b8e6c5696618b9e1f9519f34cc05574e0893a44a350dcdf158ba5",
    "incident_suppression.json:suppressed_days": "d98e35f758442cfd345fe172091165eda7f4416abf1eee9b8e4e32459885a839",
    "overrun_ledger.json:rows": "77c5602a543b00e61a4730b84c53aea1c0ac130c1a45c4d10b676c6629c603ad",
    "splice_inventory.json:entries": "57a39442f4c603236b55c973ecae1e7c6b9f751133d85737d9ac5051f7fd5f40",
    "watermark_tier_matrix.json:rows": "3b250387c9df81ccb2433ef8890fd151ca0579358a3e5a2024289ab2500f5236",
    "wrap_parity_report.json:rows": "36bad9d0db97ea3d95977ff1edda316ec1db10e32daa1a335da60a1109e5e90f",
}

OUTPUT_FILES = sorted(EXPECTED_OUTPUT_FILE_SHA256)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_field_sha(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    return _sha256_bytes(payload.encode("utf-8"))


def _load_pretty(path: Path) -> tuple[dict[str, object], bytes]:
    text = path.read_text(encoding="utf-8")
    obj = json.loads(text)
    pretty = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return obj, pretty


@pytest.fixture(scope="module")
def loaded_outputs() -> dict[str, dict[str, object]]:
    """Load each audit JSON once for the module."""
    out: dict[str, dict[str, object]] = {}
    for name in OUTPUT_FILES:
        path = RSP_AUDIT_DIR / name
        obj, pretty = _load_pretty(path)
        out[name] = {"bytes": pretty, "obj": obj, "path": path}
    return out


class TestInputIntegrity:
    """Bundled ring splice inputs must remain byte-stable."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES))
    def test_input_file_unchanged(self, rel: str) -> None:
        """Each input file must match its pinned SHA-256 digest."""
        path = RSP_DATA_DIR / rel
        assert path.is_file(), f"missing input file {path}"
        assert _sha256_file(path) == EXPECTED_INPUT_HASHES[rel]


class TestAuditLayout:
    """The audit directory must contain exactly the five documented artifacts."""

    def test_audit_dir_exists(self) -> None:
        """The audit directory must exist."""
        assert RSP_AUDIT_DIR.is_dir(), "missing /app/audit directory"

    def test_only_documented_outputs(self) -> None:
        """No extra files may appear beside the five JSON reports."""
        actual = sorted(p.name for p in RSP_AUDIT_DIR.iterdir() if p.is_file())
        assert actual == OUTPUT_FILES

    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_output_file_hash(self, name: str) -> None:
        """Each emitted JSON file must match its pinned SHA-256 digest."""
        path = RSP_AUDIT_DIR / name
        assert path.is_file(), f"missing {path}"
        assert _sha256_file(path) == EXPECTED_OUTPUT_FILE_SHA256[name]


class TestDeterministicEncoding:
    """On-disk JSON must follow the SPEC formatting contract."""

    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_pretty_sorted_ascii_json(self, name: str, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Each audit file must equal sorted two-space ASCII JSON without trailing newline."""
        bundle = loaded_outputs[name]
        assert bundle["bytes"] == bundle["path"].read_bytes()

    @pytest.mark.parametrize("name", OUTPUT_FILES)
    def test_no_trailing_newline(self, name: str, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Audit files must end on the closing delimiter without a newline."""
        bundle = loaded_outputs[name]
        assert not bundle["bytes"].endswith(b"\n")


class TestFieldHashes:
    """Pinned field digests guard nested values."""

    @pytest.mark.parametrize("key", sorted(EXPECTED_FIELD_HASHES))
    def test_field_hash(self, key: str, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Each pinned field must match its canonical digest."""
        file_name, field = key.split(":", 1)
        obj = loaded_outputs[file_name]["obj"]
        assert isinstance(obj, dict)
        assert _canonical_field_sha(obj[field]) == EXPECTED_FIELD_HASHES[key]


class TestSuppressionSemantics:
    """Incident suppression must hide suppressed days from operational reports."""

    def test_policy_floor_preserved(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """The incident bundle must echo the configured suppression floor."""
        inc = loaded_outputs["incident_suppression.json"]["obj"]
        assert isinstance(inc, dict)
        assert inc["policy_floor"] == 2

    def test_suppressed_day_listed(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """The incident bundle must record the suppressed ISO day."""
        inc = loaded_outputs["incident_suppression.json"]["obj"]
        assert isinstance(inc, dict)
        assert inc["suppressed_days"] == ["2024-03-03"]

    def test_suppressed_day_absent_from_ledgers(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Operational ledgers must omit rows for suppressed days."""
        for fname in (
            "overrun_ledger.json",
            "wrap_parity_report.json",
            "watermark_tier_matrix.json",
            "splice_inventory.json",
        ):
            obj = loaded_outputs[fname]["obj"]
            rows = obj.get("entries") or obj.get("rows") or []
            assert isinstance(rows, list)
            days = {row["day"] for row in rows if isinstance(row, dict)}
            assert "2024-03-03" not in days


class TestSpliceStatuses:
    """Splice inventory must surface each splice classification from the contract."""

    def test_span_mismatch_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """At least one splice window must be flagged span_mismatch."""
        entries = loaded_outputs["splice_inventory.json"]["obj"]["entries"]
        statuses = {row["status"] for row in entries}
        assert "span_mismatch" in statuses

    def test_tail_desync_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """At least one splice window must be flagged tail_desync."""
        entries = loaded_outputs["splice_inventory.json"]["obj"]["entries"]
        statuses = {row["status"] for row in entries}
        assert "tail_desync" in statuses

    def test_parity_drift_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """At least one splice window must be flagged parity_drift."""
        entries = loaded_outputs["splice_inventory.json"]["obj"]["entries"]
        statuses = {row["status"] for row in entries}
        assert "parity_drift" in statuses

    def test_ok_status_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """At least one splice window must remain ok after checks."""
        entries = loaded_outputs["splice_inventory.json"]["obj"]["entries"]
        statuses = {row["status"] for row in entries}
        assert "ok" in statuses


class TestOverrunLedger:
    """Overrun ledger must encode slack, nominal, and overrun bands."""

    def test_slack_status_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """A slack occupancy band must appear for the bundled workload."""
        rows = loaded_outputs["overrun_ledger.json"]["obj"]["rows"]
        statuses = {row["status"] for row in rows}
        assert "slack" in statuses

    def test_overrun_status_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """An overrun occupancy band must appear for the bundled workload."""
        rows = loaded_outputs["overrun_ledger.json"]["obj"]["rows"]
        statuses = {row["status"] for row in rows}
        assert "overrun" in statuses

    def test_negative_occupancy_overrun(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Consumer-ahead producer totals must surface as overrun, not slack."""
        rows = loaded_outputs["overrun_ledger.json"]["obj"]["rows"]
        neg = [row for row in rows if row["occupancy"] < 0]
        assert neg, "expected a negative occupancy fixture"
        assert all(row["status"] == "overrun" for row in neg)


class TestWrapParity:
    """Wrap parity rows must include match, mismatch, and anomaly paths."""

    def test_wrap_status_variants(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """The parity report must include match, mismatch, and anomaly states."""
        rows = loaded_outputs["wrap_parity_report.json"]["obj"]["rows"]
        statuses = {row["status"] for row in rows}
        assert statuses == {"anomaly", "match", "mismatch"}


class TestWatermarkTiers:
    """Tier labels must cover calm through breach for the bundled high-water marks."""

    def test_tier_labels_present(self, loaded_outputs: dict[str, dict[str, object]]) -> None:
        """Tier labels must include calm, watch, pressure, and breach."""
        rows = loaded_outputs["watermark_tier_matrix.json"]["obj"]["rows"]
        tiers = {row["tier"] for row in rows}
        assert {"breach", "calm", "pressure", "watch"}.issubset(tiers)
