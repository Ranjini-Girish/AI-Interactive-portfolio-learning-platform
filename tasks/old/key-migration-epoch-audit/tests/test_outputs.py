"""Behavioral tests for the key migration epoch audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("KME_DATA_DIR", "/app/keymigrate"))
AUDIT_DIR = Path(os.environ.get("KME_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "compromise_report.json",
    "key_profiles.json",
    "migration_rollups.json",
    "stale_report.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5b27995af3409b941d4aaee7c28b8e37791a6ca54dfbb543332531bd0acab7d7",
    "anchors/a1.txt": "be4386c9d0e0ce24afcf59be1baf19e044b2cf29f09fd81d5598ffc64bcea211",
    "anchors/a2.txt": "9cad1caec69bda7c7a397939abdaaf3915fca7ff6b9de51577bb9141c419bbc3",
    "incidents.json": "10a174c3c5a88da418bcab0b7ca8f97a78750643c9cd3ca5c74bfc447ee2b324",
    "keys/km-01.json": "0086f7f704175328eaf4713b4621cd14266a5b559aef7e1b489dc5a017441c00",
    "keys/km-02.json": "0aa8d3459879b9413a4a1b8b8945e5cac0a1fc9db10507481f8b923e4e929a5c",
    "keys/km-03.json": "acd9872f4229d389e9c8fd90dd3c3f3e19c587fc6e88c69f4a856e6a20d33a2e",
    "keys/km-04.json": "9795303380bd84d718e9950dc362045a09bd6db6091a0d6b10c069ed69de5b43",
    "keys/km-05.json": "02ad4248227e8d8ea96df3e90e5899df356501f49c604c2d5e8340100fa846bf",
    "keys/km-06.json": "73798bb80fb1e4c0150855796fdb6495df4e3d1d9c185471cc0cde31ba1d6726",
    "keys/km-07.json": "d4a41a46294aef7fe63c481e0c199d3db66c192c23514d4b0453e04a34a6ac13",
    "keys/km-08.json": "3dc05fa49053b836d4b7372e9a16fe752409b78586a7d49f7d03de0a160729ce",
    "keys/km-09.json": "491a06dc08c4e112d76b2fbcbf1fff0bd22b9224a8d156d4e3bb96514142790c",
    "keys/km-10.json": "87c86e35da98708be57bd3d417ff36906bfcd69b4bac0f91f1bfeaeac7812230",
    "keys/km-11.json": "293ba596e1ec6b17d58eea587c71954e1f45d4c3ab14786bb1d6e22e4ea254d7",
    "keys/km-12.json": "55f8f903df741133295d00c975b45e23213e9bf493a1ef856e47eeab273f3491",
    "ledger/lane.json": "0446a959ca85fc7974839d1005e6eb45d259d828b2ae405b5568f184ca594611",
    "ledger/tag.json": "0627adb344bf51f25beb2314102d8799f7bfdfcf9cd4994f934997abb4e60c35",
    "migrations/mig-001.json": "d9be9d0f45b118b9729b195cce49d09f13d827c1bbcd80a1d9afca4b0baa5c58",
    "migrations/mig-002.json": "c644ab65853d68f70ecab86c9fa24825e1d9d141ce22e09ec170160d3ab281a1",
    "migrations/mig-003.json": "b504e579ab7a5df3b963cad61a09ba3d0cfbf250efdfbf339444bba0b7bff108",
    "migrations/mig-004.json": "83430f95ee826990d75d4cf0850ebf71fdc1d6c7be79593ffaccc3325969298b",
    "migrations/mig-005.json": "888226a51339f8838fedb21e5b9d7fafc11f1533300fed3656af4abdccd5205d",
    "migrations/mig-006.json": "72bfebe06ce5df94596c20b6f5b1cf618de9a8d0632c6e924be6ebbe5bce6c9a",
    "migrations/mig-007.json": "0b9913a2c69b4e4380ead445ebe35495e09b385dac1fee9d13a92fd5aaec2568",
    "migrations/mig-008.json": "def44fe65cbd17f35af26766748052a6d621a10a914b356bb67ee10589cee5e9",
    "migrations/mig-009.json": "6928e530623695b8a20c5ba3c83f82cc9cc20d718b4718a3cf4e7532c7dd2ca6",
    "migrations/mig-010.json": "4c00cf11aae2ee4e5290571a94c540e6e669a611c911979852a95c492cf7b764",
    "migrations/mig-011.json": "ddeb09d4851e6eb9fc8cec29b516f75329f0d74afa957905e209d6ffee9d99bc",
    "migrations/mig-012.json": "189664cef76007f040a7856725b32b6a3bdd4d9d92eb724dd11fcac18e27bcaf",
    "migrations/mig-013.json": "399780d29a762cb796f9005b90928a081dec1e0a500c8110d8c09466716848d7",
    "migrations/mig-014.json": "fba5331001d431a0d72c8f48b4f30e3feb36b7cc75dfc4ff70e24c99d6d10790",
    "nodes/nd-alpha.json": "2fb6600a0ba0c771c1c487eb965533043dca4c133b80354b98687b1ec052d590",
    "nodes/nd-bad.json": "82f1778e6b12115c12b799a3c8c566c56d1d6f6bc1ab5734bd5c91cb66677697",
    "nodes/nd-beta.json": "6de28135d03d027aa163287410e9c6c94f959080cd6092237e9aad81e6acf880",
    "nodes/nd-delta.json": "4cab4ab4d69417a9d44f8956e7fbaa0eb8d9a9240a27973115224eebbbb09b2b",
    "nodes/nd-epsilon.json": "3300a9ec9118e0431869fa704a490988f980be2f0b3d8686355eb30ce0ff409b",
    "nodes/nd-gamma.json": "961d455f9263f64987876205a7e56795e73e451acc073da658edad52f225fe54",
    "nodes/nd-noisy.json": "53b6ee17c4d8ba15f9cc3e048ae0e411b9b2974244fcf4ee36d9665decb2d332",
    "nodes/nd-stale.json": "61f99f0e0fd4535e1df321c2bc401d5c7bfedbe33c5972b7bfa0c55354698084",
    "overlays/o1.json": "ecfbc02e5e7e0f1d2e59a52068091fe5c93a6e7a3777a175d55e6d57f2e65f7c",
    "overlays/o2.json": "80087df11d4ef812d9c117b7b4b07291a0c78da8616f84659d93d923e6d9ad76",
    "policy.json": "ba7c423fa886f26fea2ebee867568e413bb021d2f82a53ae484c9004201fb46a",
    "pool_state.json": "ab753d4799deff8a51ff8b5cd7975a06ab1b322c96c9bb53843fbb5810e9255f",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "compromise_report.json": "439d424c1ab24cd4a5006c60b7356edb89a01ac994d29e1f88095b20375028a1",
    "key_profiles.json": "e4d0a9073db098405eb9fb10f15c01988c499505705cdd481de9a9755e44b3a4",
    "migration_rollups.json": "f111184bb6d013e9f6ac4f3dbe81377fae00411ae051d33195cdc57880b7ee46",
    "stale_report.json": "8cd0e53c7b3eddd5f94846e85c740d2cbc446cc7cbe3cac9fbd79056067824e7",
    "summary.json": "10c249af42753d4e407c041732e1ecd563745ae288378080e39de87cedf1b747",
}


EXPECTED_FIELD_HASHES = {
    "key_profiles.keys": "b8899be620a02d303716589526f03b9ed73b87f4ee2a66112b60d0e114ba3d32",
    "migration_rollups.buckets": "d3cbf4f4ce5b6153fa3b7de792914d75c3d3c67c8b4e4e4eb49744575594df07",
    "summary.complete_epoch_starts": "8024ffe17674cbd200405639391f3ffc579bbfc13ac8b393aec0de25ce970cb7",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
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
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        kp = outputs["key_profiles.json"]
        assert isinstance(kp, dict)
        assert (
            _sha256_bytes(_canonical(kp["keys"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["key_profiles.keys"]
        )

        mr = outputs["migration_rollups.json"]
        assert isinstance(mr, dict)
        assert (
            _sha256_bytes(_canonical(mr["buckets"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["migration_rollups.buckets"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["complete_epoch_starts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.complete_epoch_starts"]
        )


class TestKeyOrdering:
    """Deterministic ordering rules on key profile rows."""

    def test_keys_sorted_by_hash(self, outputs: dict[str, object]) -> None:
        """`keys` must list rows in ascending ASCII `key_hash` order."""
        rows = outputs["key_profiles.json"]["keys"]
        assert isinstance(rows, list)
        ids = [str(r["key_hash"]) for r in rows]
        assert ids == sorted(ids)


class TestKeySemantics:
    """Spot-check keys that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], kid: str) -> dict[str, object]:
        rows = outputs["key_profiles.json"]["keys"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("key_hash") == kid:
                return r
        raise AssertionError(f"missing key row {kid}")

    def test_transitive_chain_km01(self, outputs: dict[str, object]) -> None:
        """`km-01` chains two epoch-12 migrations and lands on nd-gamma."""
        r = self._row(outputs, "km-01")
        assert r["final_owner"] == "nd-gamma"
        assert r["migration_count"] == 2
        assert r["status"] == "ok"

    def test_anchor_hold_on_km02(self, outputs: dict[str, object]) -> None:
        """`km-02` ends on nd-beta which carries anchor hold."""
        r = self._row(outputs, "km-02")
        assert r["final_owner"] == "nd-beta"
        assert r["status"] == "hold"

    def test_compromise_quarantines_km03(self, outputs: dict[str, object]) -> None:
        """`km-03` stays on compromised nd-bad and is quarantined."""
        r = self._row(outputs, "km-03")
        assert r["status"] == "quarantined"
        assert r["initial_owner"] == "nd-bad"

    def test_weight_floor_drops_km04(self, outputs: dict[str, object]) -> None:
        """`km-04` has weight zero and is classified dropped."""
        r = self._row(outputs, "km-04")
        assert r["status"] == "dropped"

    def test_out_of_window_migration_ignored(self, outputs: dict[str, object]) -> None:
        """`km-06` ignores mig-014 at epoch 24 outside the inclusive window."""
        r = self._row(outputs, "km-06")
        assert r["final_owner"] == "nd-alpha"
        assert r["migration_count"] == 0

    def test_compromise_touch_quarantines_km09(self, outputs: dict[str, object]) -> None:
        """`km-09` migrates from nd-bad and remains quarantined."""
        r = self._row(outputs, "km-09")
        assert r["status"] == "quarantined"
        assert r["final_owner"] == "nd-alpha"


class TestMigrationRollups:
    """Epoch bucket rollups respect caps and exclusions."""

    def _bucket(self, outputs: dict[str, object], start: int) -> dict[str, object]:
        buckets = outputs["migration_rollups.json"]["buckets"]
        assert isinstance(buckets, list)
        for b in buckets:
            if isinstance(b, dict) and b.get("epoch_start") == start:
                return b
        raise AssertionError(f"missing bucket {start}")

    def test_only_complete_epoch_starts(self, outputs: dict[str, object]) -> None:
        """Rollups cover epoch buckets 10 and 17 but skip the partial tail."""
        buckets = outputs["migration_rollups.json"]["buckets"]
        assert isinstance(buckets, list)
        starts = [int(b["epoch_start"]) for b in buckets]
        assert starts == [10, 17]

    def test_bucket_cap_keeps_first_four_migrations(self, outputs: dict[str, object]) -> None:
        """Bucket 10 keeps mig-001 through mig-004 after sorting by migration_id."""
        b = self._bucket(outputs, 10)
        ids = [str(m["migration_id"]) for m in b["migrations"]]
        assert ids == ["mig-001", "mig-002", "mig-003", "mig-004"]

    def test_excluded_noisy_node_absent_from_rollups(self, outputs: dict[str, object]) -> None:
        """Migrations touching nd-noisy never appear in migration_rollups.json."""
        for b in outputs["migration_rollups.json"]["buckets"]:
            assert isinstance(b, dict)
            for row in b["migrations"]:
                assert row["from_node"] != "nd-noisy"
                assert row["to_node"] != "nd-noisy"


class TestStaleReport:
    """Stale listing omits quarantined nodes."""

    def test_stale_report_lists_nd_beta_and_nd_stale(self, outputs: dict[str, object]) -> None:
        """Nodes with stale_flag but not quarantined appear sorted by node_id."""
        rows = outputs["stale_report.json"]["nodes"]
        assert isinstance(rows, list)
        ids = [str(r["node_id"]) for r in rows]
        assert ids == ["nd-beta", "nd-stale"]


class TestCompromiseReport:
    """Compromise report enumerates compromised nodes and quarantined keys."""

    def test_compromise_nodes_and_keys(self, outputs: dict[str, object]) -> None:
        """Accepted compromise pins nd-bad and lists km-03 and km-09."""
        rep = outputs["compromise_report.json"]
        assert isinstance(rep, dict)
        assert rep["nodes"] == ["nd-bad"]
        key_ids = [str(r["key_hash"]) for r in rep["keys"]]
        assert key_ids == ["km-03", "km-09"]


class TestSummaryTotals:
    """Summary counters reconcile with profile semantics."""

    def test_summary_reconciles_counts(self, outputs: dict[str, object]) -> None:
        """Summary exposes two quarantined keys, one dropped key, and two stale nodes."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert int(sm["quarantined_total"]) == 2
        assert int(sm["dropped_total"]) == 1
        assert int(sm["stale_total"]) == 2
        assert int(sm["epoch_count"]) == 2
        assert sm["complete_epoch_starts"] == [10, 17]
