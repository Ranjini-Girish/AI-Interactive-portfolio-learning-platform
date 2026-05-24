"""Behavioral tests for the ivy build lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("IBL_DATA_DIR", "/app/ivybuild"))
AUDIT_DIR = Path(os.environ.get("IBL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "cycle_members.json",
    "linear_order.json",
    "module_catalog.json",
    "path_weights.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "10b9db3e6fe9424a29d220168dbf515e9c126c8a31656ec2805d26af86c17b4b",
    "anchors/p1.txt": "2dc43a466a3fb5896dace477dcf43876b5ff20c59d83a45c26229b743987893e",
    "anchors/p2.txt": "e131a747fbac12c08cbcc950bad932a9534e1a2950dcf9366ce36cd4657de8cf",
    "anchors/p3.txt": "93e9bcb2d9531b8be7b6ad2c1c63e9872050a265031eafaa0243e57078fdfd74",
    "anchors/p4.txt": "4acdf01a41107d956a87eae4a01da018a64c822b231318e77ca98b61c86718ba",
    "ancillary/a1.json": "01721804094869ab55ee0904c8a00ce5f6c666d1d4064b5185ea7153cdff2ee2",
    "ancillary/a2.json": "d361928e616856421a2e0ccda9b77ec5cda587515734c95b343f4a8f485e48f4",
    "ancillary/b1.json": "14a29181fe72f4608d1c1f42f1f0dbbf5793609f31de840da48e595909bd4cd4",
    "incidents.json": "82f002016f6dead0072e5ab826c641efbddd21bb85b2112624c9541f95eb667d",
    "ledger/lane.json": "59af8355547b66db58859471d35cd3e8994740af250480d60f35b652398bd02f",
    "ledger/stamp.json": "894e64274ed9e9eb6ad55a600e4d9b69105c658006f48f8a36d0e20e5caa350d",
    "ledger/tag.json": "9526d171fe0669af2c8c82f714318007637a9c42ebe2c177eeca1b639c57d06b",
    "modules/m01.json": "898cac8bce979620e8cfac3f5875bd2efe90c45c2f758853022215e09f7714b5",
    "modules/m02.json": "7129a9dc323df4a3f9f6615153bf65d04fc6ec05928bb465d416fe14b49c66e8",
    "modules/m03.json": "93987349b2b2cc30d615760384bb8e44fdc290e2052dbfdca25c94d7709413af",
    "modules/m04.json": "2e9fe4d8150a209794aaadbc0af2f2467d49fb6087db9d8f565c8e156a1bfea5",
    "modules/m05.json": "82655c8b2352eb88188c9b1bb1b8fa8595d4e1ef8e6442d8eebb9078dee5cb65",
    "modules/m06.json": "773e98ae16b3ae52d8dbca11746545f398c14fe6152dd4882c1ebb8987589920",
    "modules/m07.json": "339720d99d1c8746c23b86e8db949fd2e47b2875dbcc76a91e84f70236730c0c",
    "modules/m08.json": "2a0486c7af4d137de40518cd716bcd92db004aceb736c09e2a08bfa6f409394b",
    "modules/m09.json": "513da23cf6930db180cc78ebbbf1ce5fe9a2204b8f5fc1c059df6161cbf558c9",
    "modules/m10.json": "a3be35b2661a393b58ebfa16927e9e7bc9e90d1d05de7f17c9c0e964e9854526",
    "modules/m11.json": "13584af145dad9324219ba3e5a76f85ccaa5532eef6dbc420314b9a8b2515859",
    "modules/m12.json": "6e45f333cab35ca1d4e6607b8904a8efac108532bf3963ba1288d914ac873ab1",
    "policy.json": "28215bfb6f5c77cd942b3de441317f98a1599c4b34b802a495cd32d65fabf8ae",
    "pool_state.json": "4de86816d991850508d0a1b51491baf2a3999388a7575901a310272d01d16c37",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cycle_members.json": "9deaedb7caad43e193d031764971710e1b2c1ac157f0d4827a3f11e462ef4e8f",
    "linear_order.json": "c21e02c523a9c23024dd1c900bddb4c7fd5a2881fd40f4fdd180c7412f575971",
    "module_catalog.json": "8da2c9d672beb98ae3a143eb557398e8b0af5e5ea7b42f29bc2c36c251128dbc",
    "path_weights.json": "70b87d7dc0b5b5accfecffe8c67352bc43ee31d4ec625fb15d08f1637dfe9340",
    "summary.json": "4f66de61cf65a6498ae0cedd373acc9cc337f1be2f17cad1584fd27bd0a55c4d",
}


EXPECTED_FIELD_HASHES = {
    "module_catalog.modules": "5a41ed5c0ec37d36e5ac27255afe6225c63f4c78a64007be200daf5fc26e9ec8",
    "summary.graph_label": "857d11022796afa4998e5c7b43f4d4b912cdf929393b88a23dbb3fc4f63f37ea",
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
        mc = outputs["module_catalog.json"]
        assert isinstance(mc, dict)
        assert (
            _sha256_bytes(_canonical(mc["modules"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["module_catalog.modules"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["graph_label"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.graph_label"]
        )


class TestCycleSemantics:
    """Cycle ring is isolated to the late-module trio."""

    def test_cycle_members_ring(self, outputs: dict[str, object]) -> None:
        """Only the mutually dependent trio appears in the SCC-derived member list."""
        members = outputs["cycle_members.json"]["members"]
        assert isinstance(members, list)
        assert [str(x) for x in members] == ["m08", "m09", "m10"]

    def test_linear_order_null_when_cyclic(self, outputs: dict[str, object]) -> None:
        """A global cycle forces `linear_order` to JSON null."""
        lo = outputs["linear_order.json"]["linear_order"]
        assert lo is None

    def test_path_weights_empty_when_cyclic(self, outputs: dict[str, object]) -> None:
        """Path weights map is empty whenever the graph is not linearizable."""
        w = outputs["path_weights.json"]["weights"]
        assert isinstance(w, dict)
        assert w == {}


class TestSummary:
    """Summary mirrors module totals and policy echo."""

    def test_summary_counts(self, outputs: dict[str, object]) -> None:
        """Twelve modules are present with three cycle members and no linearization."""
        sm = outputs["summary.json"]
        assert int(sm["modules_total"]) == 12
        assert int(sm["cycle_member_count"]) == 3
        assert sm["linearizable"] is False
        assert str(sm["graph_label"]) == "ivy-lattice-preview"


class TestCatalogOrdering:
    """Catalog mirrors sorted module ids and sorted prereqs."""

    def test_modules_sorted(self, outputs: dict[str, object]) -> None:
        """Catalog rows are sorted by module id ascending."""
        rows = outputs["module_catalog.json"]["modules"]
        assert isinstance(rows, list)
        ids = [str(r["module_id"]) for r in rows]
        assert ids == sorted(ids)

    def test_prereqs_sorted_in_row(self, outputs: dict[str, object]) -> None:
        """Each catalog row keeps prereqs sorted lexicographically."""
        rows = outputs["module_catalog.json"]["modules"]
        for r in rows:
            pr = r["prereqs"]
            assert isinstance(pr, list)
            s = [str(x) for x in pr]
            assert s == sorted(s)
