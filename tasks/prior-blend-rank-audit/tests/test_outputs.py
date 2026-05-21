"""Verifier suite for prior-blend-rank-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PBR_DATA_DIR", "/app/pbr_lab"))
AUDIT_DIR = Path(os.environ.get("PBR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["allocation_table.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b9abc2322703ffae376e1ff6a3de6a1c7de1c0d7d942a0f40f74202afd485269",
    "anchors/a.json": "0383d9bf110c9b26caa23c35fd21c4b7888fb6509597df9bb5ee53721299981a",
    "anchors/b.json": "9b2102b4ea84029b53efc229a4a9f665a2ea7c904329519f55075b60fa964cf8",
    "ancillary/meta.json": "b28f75b375d6d5d4f2039600192047987a86738a6fff51e30a58c09a0e53ca87",
    "ancillary/notes.json": "a4ea682ce18e914bb133574a90258ae27155e7074826fd2f6a8e911579b56bcf",
    "ancillary/stub.json": "2f99984fb8e096b8cad288a9dfe59d59d2db3470ba6645cb93bc0b0773788059",
    "domain_layout.json": "b1a2335a1bd758b226541e37f36029df0e0fe8fdf34cb72d5dfb63595f456452",
    "incident_log.json": "3e073554e03d003499cc9f1c4db17158e18a10a21c1999b3fb808cc9545d9a89",
    "items/item_00.json": "96f25cffe13657141743c8f7ceb0608cf891c9f7414460082a25fce037cbc5da",
    "items/item_01.json": "cc582b3530fce7472c89c6938e9c938b1083174713dc93c629a1980ab27af778",
    "items/item_02.json": "5dd8762d3c7c8fa299996dbbc610deb66751ad3a079947a820b514122c634b8f",
    "items/item_03.json": "3da03397a0d3d6f68a81d0c385716645b115f2620f53c08f667c84ba0dc8c4c9",
    "items/item_04.json": "104e3bb1eaac6c1b33e5bc8151f45c9ddf965fd9d89e4ed76a9070415a32bebc",
    "items/item_05.json": "0bb626864f1c7080899e5c4e2352123eb646b22055e135eb5c9e83534887c9a9",
    "items/item_06.json": "93c5259f450a9e0dc343464ae4a6a9bd7948c30366e1780dc03ff8ff08f8ea8d",
    "items/item_07.json": "74a3df004bfa99cfec9f1a031e9b46f70d1fe897c3555119a01dc1fc556f07fc",
    "items/item_08.json": "28c41d5d84db1a00d35a204623dbfc0ce524d0f5245170bfb0c57f47b5da9f0e",
    "items/item_09.json": "9ca494440b3d04756370dfd9c61bf04ca2dd69b71bb7cd316586f8e1f4aea7e6",
    "lanes/l01.json": "a1c954ca853f920fc8863e0663f1ce4ff39cfdf69fa8089e8b2fc92e2c3bef59",
    "lanes/l02.json": "56c324aa3e297b77964277f96137406f1d088e4107e265bac18729e2d11ec743",
    "lanes/l03.json": "fcdb4d3fd960453317f79f58c9daca3601d4ff60ad0821d3b7d1db4a0a2e42d4",
    "lanes/l04.json": "7ede5d77ac37a049d7692faad36ec5069313e73a924333c517dc8b47c9001952",
    "lanes/l05.json": "52748e32bdd0bd117c0932b4ee52f31792f1b32b4af45c3d7dce8628145ab6b4",
    "lanes/l06.json": "adaea7ecc48429ae7f7bc3f3d987a12fe8d7c17c27e10fc00d1b4d71206bf2ac",
    "lanes/l07.json": "51d826a67315d79f9b2d4ee10a98321c437823334f206875d79b2047bf2131c4",
    "lanes/l08.json": "b77cc872bd4fc41314a401a086c039afc1a9e21afeb4e029466ea96b5e41184e",
    "policy.json": "7ca1a6aaaa3156f608560985512bfab0de41d5d0352d07f87f38361f5f13846d",
    "pool_state.json": "4520c2f8537b041c238249223daf9d3e5f9a0323f5974110a76eddd8fe65958c",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "allocation_table.json": "69eb16ef6b82e5f73c9c890a17ed28b5e422a6e435c66280e6aec1f3191be349",
    "summary.json": "1a0be0f0bd46a9f84452f27dffd0c44733049bc115f0f8a39be2a6ab7c017fc4",
}


EXPECTED_FIELD_HASHES = {
    "allocation_table.json.allocations": "188c57384ca2e9b5e58bf425c1baaac4e4da26fc3dc7f5b7c8e082b958004cf4",
    "summary.json.regions": "e95c99b0cf37d0dc8e8216369a290f402e83d342b55a9621bba7dad3d1c16c86",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 digest for a byte string."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize JSON in the verifier's canonical minified form."""
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
        """Nested collections remain stable under canonical serialisation."""
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


class TestSummarySemantics:
    """Behavioural checks aligned with the bundled scenario."""

    def test_applied_events_counts_full_log(self) -> None:
        """Every incident row is counted, including unknown kinds."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["applied_events"]) == 4

    def test_holdout_breach_keeps_only_west_regions(self) -> None:
        """Quarantine removes the configured region while west rows remain."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        regions = summary["regions"]
        assert isinstance(regions, dict)
        assert list(regions.keys()) == ["west"]
        assert int(regions["west"]) == 47

    def test_survivor_count_matches_bundle(self) -> None:
        """Five west items survive after the drop and quarantine."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["survivors"]) == 5

    def test_allocations_sorted_by_item_id(self, outputs: dict[str, object]) -> None:
        """Allocation rows stay lexicographically ordered by identifier."""
        table = outputs["allocation_table.json"]
        assert isinstance(table, dict)
        rows = table["allocations"]
        assert isinstance(rows, list)
        ids = [str(row["item_id"]) for row in rows]
        assert ids == sorted(ids)

    def test_budget_splits_completely(self, outputs: dict[str, object]) -> None:
        """All budget units are assigned when survivors exist."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        table = outputs["allocation_table.json"]
        assert isinstance(summary, dict)
        assert isinstance(table, dict)
        rows = table["allocations"]
        assert isinstance(rows, list)
        total_alloc = sum(int(row["allocated"]) for row in rows)
        assert total_alloc == int(summary["regions"]["west"])
        assert int(summary["unallocated"]) == 0

    def test_lane_nudge_reflected_in_witness_used(self, outputs: dict[str, object]) -> None:
        """Lane witness nudges clamp under witness_cap before allocation."""
        table = outputs["allocation_table.json"]
        assert isinstance(table, dict)
        by_id = {str(row["item_id"]): row for row in table["allocations"]}
        row = by_id["item_03"]
        assert int(row["witness_used"]) == 130


class TestPoolFlags:
    """Pool flag wiring visible in the fixture."""

    def test_bundled_pool_flags_match_scenario(self) -> None:
        """Bundled pool flags enable quarantine while leaving compromise off."""
        pool = _load_json(DATA_DIR / "pool_state.json")
        assert isinstance(pool, dict)
        flags = pool["flags"]
        assert isinstance(flags, dict)
        assert flags["holdout_breach"] is True
        assert flags["experiment_compromised"] is False
