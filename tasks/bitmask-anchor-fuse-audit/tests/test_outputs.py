# scaffold-status: oracle-pending
"""Verifier suite for bitmask-anchor-fuse-audit (compound fuse, anchors, segments, tier skew)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BAF_DATA_DIR", "/app/baf_lat"))
AUDIT_DIR = Path(os.environ.get("BAF_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["fuse_ledger.json", "incident_state.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "995e994a050c9f53dffdc03cf47768d9dda70951e624341652ec8183d9e56bd6",
    "anchors/a.json": "73841da2caf140e5914f6e743badd78fdc8e3af13e8ebc771e0b9e456f86dc9c",
    "anchors/b.json": "9835ab342bea0dacc7666670fd0e2e4651a5671c04dd7482511541524a2743d2",
    "ancillary/meta.json": "a515956717967bf2ce4531f69c7c880aa4b2dc82626c02ec23d6d3e0acab174e",
    "ancillary/notes.json": "e46048bdda148176042803a18a63011fac0ff89139c7668ccba1b1ee0e7535e5",
    "domain_layout.json": "07b344bf77f8ff2602336bfaced7e5dfb3785d13681137cbb44d86fa93107ea4",
    "incident_log.json": "dd529a141291363d0438aab5945f381865c90bd346f380797ad53efbac7d599d",
    "items/item_00.json": "00c97e2bb3d28515ec0a02a509109631929dab63b107fc80349391fb002ef27e",
    "items/item_01.json": "e15c8d8d16cb4e46cf26d5dba5d15749a104f61bcdacb623360525d4292d7fb8",
    "items/item_02.json": "de78a509f8a9695692d60ffc1bbf483445afcd0d54fc77a154062ddc3bfb3188",
    "items/item_03.json": "33125230def11fccc3d6cd0c2d45fa19f903003580e9afdbf9380c938766e45f",
    "items/item_04.json": "60c7c816f378f3c3e7bbe43b1ef5f1683ed8000f619f676b4ac6d2d203d0e826",
    "items/item_05.json": "768d98f2c7ec1ba9b00a734521088a8681aea6be1a08f6792c9e4f7df27052ee",
    "items/item_06.json": "2160cfba4cc23bd71f2190dfab607066b4259a0fa02c477f540b9406aea0b8c9",
    "items/item_07.json": "c5096897d024689a4bec5c1c33a504fc9d2dbd91626ab2cb7d5c5dede5d97eb8",
    "items/item_08.json": "4e330a9a316f8f67026ca9280fc29c18d6d5dca4fade91587d9061a7f83b0be6",
    "items/item_09.json": "1155fbc4f7ff47d3a589524f5a1a616c5f8d9246566a9d32746d27a1000cda9e",
    "items/item_10.json": "114ba7de98ef80f1c88e4a985d3e90e6ed3aa3726923c3a0dbfbb9d51b3a0edb",
    "items/item_11.json": "f4c077d53bb407932dd501f0ed07b879ae61f2a4e2fb2404c803bdafdbca5647",
    "items/item_12.json": "d6b2b773c24cb0e34e52cef53ff85d10a85dffca9e661b8a93981ed275895df2",
    "items/item_13.json": "ba8771974a53b5211fea013fa2931aed06b52ab56be16c47cddd51ae6ee93b6b",
    "items/item_14.json": "da45c164c6fd2f3d8940b28d48c1964c03d8673df421d90b54ea1756e90bb70c",
    "items/item_15.json": "fe8aec6f6c2c913ca44f42fc6d99f2ca93630942f356aeeda7992c64e6871093",
    "items/item_16.json": "0c58ca2523263fb89481e81f0647b1e27206cd84daeb10af3fa8156906cfd359",
    "items/item_17.json": "51ebd252f0fb7e48945575d53635c69a21e06f3c92ced1df3c37849e8384569e",
    "policy.json": "66473d0fd68cc2f60ad7a3a12d813b2ee2feb3518c7f247d765eb3afc5540ae6",
    "pool_state.json": "f8cd87f30ef19b1f2a157febf9d6b46aa0f3fc26b43aea70b9ec98b69668b29d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "fuse_ledger.json": "23a3e8f7f0c52b2176ae9f80142dfd6ab36288d2902e4d200a06f75b4b795df3",
    "incident_state.json": "99506de013f4eb76d624f89b6b6866bb635c1bfc85993b4644426f4badbab164",
    "summary.json": "ca895b6e9fac631df1c8103705489355e4032daa34afd10a699f454337b52473",
}


EXPECTED_FIELD_HASHES = {
    "fuse_ledger.json.entries": "18b8ca8d02141af1484d103d1be46902aa8d8303e51755a056795d5a7e61e4cf",
    "incident_state.json.anchor_lane": "031b4af5197ec30a926f48cf40e11a7dbc470048a21e4003b7a3c07c5dab1baa",
    "incident_state.json.anchor_or": "031b4af5197ec30a926f48cf40e11a7dbc470048a21e4003b7a3c07c5dab1baa",
    "incident_state.json.fuse_mask": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "incident_state.json.tier_live": "f6aa2e8630ef1189e2e59dfa6dbfa1e75a7dd0bac44f9482bed50a74e27ffaa1",
    "incident_state.json.xor_acc": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.json.anchor_lane": "031b4af5197ec30a926f48cf40e11a7dbc470048a21e4003b7a3c07c5dab1baa",
    "summary.json.anchor_or": "031b4af5197ec30a926f48cf40e11a7dbc470048a21e4003b7a3c07c5dab1baa",
    "summary.json.entries": "4ec9599fc203d176a301536c2e091a19bc852759b255bd6818810a42c5fed14a",
    "summary.json.fuse_mask": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
    "summary.json.tier_live": "f6aa2e8630ef1189e2e59dfa6dbfa1e75a7dd0bac44f9482bed50a74e27ffaa1",
    "summary.json.total_score": "5f64f9bf5a4917786dc822eb0368ef7ce3a92e6c93c3f817e09f2cabc4c9e533",
    "summary.json.xor_acc": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified JSON."""
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
        """Nested summaries remain stable."""
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


class TestSemanticInvariants:
    """Behavioural checks aligned with the published bundle."""

    def test_summary_matches_incident_state_core_fields(self, outputs: dict[str, object]) -> None:
        """Summary duplicates the five incident-derived scalars exactly."""
        summary = outputs["summary.json"]
        state = outputs["incident_state.json"]
        assert isinstance(summary, dict) and isinstance(state, dict)
        for key in ("anchor_lane", "anchor_or", "fuse_mask", "tier_live", "xor_acc"):
            assert summary[key] == state[key]

    def test_xor_accumulator_matches_fixture_incidents(self, outputs: dict[str, object]) -> None:
        """Accepted xor_acc incidents reduce to xor_acc 7 for this bundle."""
        assert outputs["summary.json"]["xor_acc"] == 7

    def test_fuse_mask_differs_from_policy_start(self, outputs: dict[str, object]) -> None:
        """Fuse twists move the active fuse away from the policy starting mask."""
        policy = _load_json(DATA_DIR / "policy.json")
        assert isinstance(policy, dict)
        assert outputs["summary.json"]["fuse_mask"] != int(policy["fuse_mask"])

    def test_tier_live_reflects_skew(self, outputs: dict[str, object]) -> None:
        """Tier skew events lift the multiplier above the policy baseline."""
        policy = _load_json(DATA_DIR / "policy.json")
        assert isinstance(policy, dict)
        assert float(outputs["summary.json"]["tier_live"]) > float(policy["tier_factor"])

    def test_ledger_rows_sorted_by_id_then_mask(self, outputs: dict[str, object]) -> None:
        """Ledger ordering follows ASCII id then effective_mask tie-break."""
        entries = outputs["fuse_ledger.json"]["entries"]
        assert isinstance(entries, list)
        keys = [(str(e["id"]), int(e["effective_mask"])) for e in entries]
        assert keys == sorted(keys)

    def test_lane_varies_with_segment_tags(self, outputs: dict[str, object]) -> None:
        """Edge-tagged rows pick a different computed lane than core-only rows."""
        entries = outputs["fuse_ledger.json"]["entries"]
        assert isinstance(entries, list)
        by_id = {str(e["id"]): e for e in entries}
        core_lane = int(by_id["n04"]["lane"])
        edge_lane = int(by_id["n00"]["lane"])
        assert core_lane != edge_lane

    def test_each_entry_exposes_intermediate_masks(self, outputs: dict[str, object]) -> None:
        """Every ledger entry carries lane and blended diagnostics required by the spec."""
        entries = outputs["fuse_ledger.json"]["entries"]
        assert isinstance(entries, list)
        for row in entries:
            assert {"blended", "effective_mask", "id", "lane", "score"} <= set(row.keys())

    def test_fixture_incident_catalog_includes_each_kind(self) -> None:
        """Bundled incidents include xor_acc, fuse_xor, tier_skew, and noop kinds for coverage."""
        log = _load_json(DATA_DIR / "incident_log.json")
        assert isinstance(log, dict)
        kinds = {str(ev.get("kind")) for ev in log.get("events", []) if isinstance(ev, dict)}
        assert {"fuse_xor", "noop", "tier_skew", "xor_acc"} <= kinds
