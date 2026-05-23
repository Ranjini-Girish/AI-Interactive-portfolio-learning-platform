"""Verifier suite for the relay hop capacity audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RHC_DATA_DIR", "/app/relayhop"))
AUDIT_DIR = Path(os.environ.get("RHC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "admissions.json",
    "denials.json",
    "carry_ledgers.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "7466b6bfba6963a307dbbd265f76ccd63f926234da6cd7d867cfe5ff2a6229f3",
    "anchors/a01.txt": "a7ed408fbc0224530a795b943832e46d279d05133ed433f98c730fd913957f56",
    "anchors/a02.txt": "e48abb9e0ffc19ce80d12dbafffd377af0d5c25ca3917b5309a3a359a1a3b8db",
    "anchors/a03.txt": "9b9c687d0afeb621dcd0d0ede164b1990066f22b6f12ed142ab13757da5ff293",
    "flows/f01.json": "94fab7c2b6a6bbad51a97067bff1d06b9bbefc78113d5e3e6c798f7e2e28ae5f",
    "flows/f02.json": "11f8721cab9f4722d6574a5e470c9294f9895a15335db664e07cddf51821e4c5",
    "flows/f03.json": "9c7a5b80768011fd09285dcbf41e0b4a26c0436f3a370e9f73e65893105260ea",
    "flows/f04.json": "e90d083854dd98a5bcf64b0285344d010f629895addb9d6dee822333cfff3876",
    "flows/f05.json": "075530d7efd2a398ae8910f81f971dd65d87c9688690a0ca025ebd401ae16693",
    "flows/f06.json": "a1eba732cfe359b2a7db3c8a797343ed76116b05d61012c1741236037bb3d671",
    "flows/f07.json": "3d03588b1bff9087e23e4db4859db7664d28c7c8d7684d24cb0033982911d2bc",
    "flows/f08.json": "bb0f5053f10f0f7cbc1c5ade4e8b4c7c637da7066bf0ba65ea8ed2c01fa4d962",
    "flows/f09.json": "b3ab6e68468021c29737e17b7da0eba07cb5677f1e4efc453032a3ea3c74fe8b",
    "flows/f10.json": "96bae1980506fcb86a7eeb035c8e885ed7d87cc6e8d8915b19ddade89641ada4",
    "flows/f11.json": "fbefc9f5fcd63ad93c443efbb09ae20b0222cbb05549ba16c21f25f82e17782f",
    "flows/f12.json": "b771b0b66c4258e12ccfb4a8b5d08f601a5e13334d4674b83b51228542bf954d",
    "flows/f13.json": "01dfa9b27ae6f821898a38368a3cb54d282e8ea73e978eef4eac58d7851ef8d6",
    "flows/f14.json": "051987314050e107b942b35f630aabc41447dee17c6fb797524098a820db1352",
    "hops/h01.json": "4584eacfc93e3df531146648f0adfc884a2c306936476501a019371206da491e",
    "hops/h02.json": "b02bb8d526d3c0027a4eba81d2f1b28362e1f3ce5d12b423afeaba86b2fe0b52",
    "hops/h03.json": "db4230ed4162b161944b163a042c7f73418ae1101abedea0a585169643ab54bd",
    "hops/h04.json": "5bc901971249119e1d5b15e759a4295c8354206b0dfec2dfc74998bb20f33725",
    "incidents.json": "8e1759c300852ea2b5c8b96c22cb111dcc76ec99db12409f59347ff69c26d34f",
    "policy.json": "6506c2163797cd1d365dfde3eb4348bf68604f4a8ffcec059679de81c9458b64",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "admissions.json": "a9f652388fb646f2fbd16723553dcdd588e8cd51db4b4b879c7635bf7eac6718",
    "denials.json": "371edb867b897b47c0d61e2126e7635af34293bd55c5923c528aec1c212a3532",
    "carry_ledgers.json": "18a8555251a8d1a89536e683ad295d1b317527e4a1e319e01021532d7e6b656d",
    "summary.json": "d545884d6a7fa798bc43b97afab6d8880ef899569c8e75cdb07ec9fc0a090955",
}


EXPECTED_FIELD_HASHES = {
    "admissions.admissions": "2727944e5c84cd55cde17b570ece90b8c04454670333838edf0f5df35229ebcf",
    "summary.incidents_applied": "86c915d2345058b1f7d9dae041f020d50fbe3c5c03e8d32a35f1511a0cde7eb6",
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


@pytest.fixture(scope="session")
def policy_epochs_hops() -> tuple[list[int], list[str]]:
    """Return the policy epoch list and hop order from the frozen dataset."""
    pol = _load_json(DATA_DIR / "policy.json")
    assert isinstance(pol, dict)
    epochs = pol["epochs"]
    hops_order = pol["hops_order"]
    assert isinstance(epochs, list) and isinstance(hops_order, list)
    return [int(x) for x in epochs], [str(x) for x in hops_order]


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
        adm = outputs["admissions.json"]
        assert isinstance(adm, dict)
        assert (
            _sha256_bytes(_canonical(adm["admissions"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["admissions.admissions"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["incidents_applied"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.incidents_applied"]
        )


class TestSummarySemantics:
    """Cross-check summary counters against the emitted detail lists."""

    def test_summary_totals_match_detail(self, outputs: dict[str, object]) -> None:
        """Summary admission and denial totals must match the detail arrays."""
        sm = outputs["summary.json"]
        adm = outputs["admissions.json"]
        den = outputs["denials.json"]
        assert isinstance(sm, dict) and isinstance(adm, dict) and isinstance(den, dict)
        rows_a = adm["admissions"]
        rows_d = den["denials"]
        assert isinstance(rows_a, list) and isinstance(rows_d, list)
        assert int(sm["total_admissions"]) == len(rows_a)
        assert int(sm["total_denials"]) == len(rows_d)
        tot_bytes = sum(int(r["bytes"]) for r in rows_a)
        assert int(sm["total_admitted_bytes"]) == tot_bytes
        tot_req = sum(int(r["requested"]) for r in rows_d)
        assert int(sm["total_denied_bytes"]) == tot_req

    def test_max_epoch_matches_fixture_extents(self, outputs: dict[str, object]) -> None:
        """The summary max epoch must match the largest epoch referenced anywhere."""
        sm = outputs["summary.json"]
        adm = outputs["admissions.json"]
        den = outputs["denials.json"]
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(sm, dict) and isinstance(adm, dict) and isinstance(den, dict)
        mx = 0
        for r in adm["admissions"]:
            assert isinstance(r, dict)
            mx = max(mx, int(r["epoch"]))
        for r in den["denials"]:
            assert isinstance(r, dict)
            mx = max(mx, int(r["epoch"]))
        assert isinstance(inc, dict)
        for r in inc["incidents"]:
            assert isinstance(r, dict)
            mx = max(mx, int(r["epoch"]))
        assert int(sm["max_epoch"]) == mx

    def test_incident_kind_strings_follow_fixture_order(self, outputs: dict[str, object]) -> None:
        """Every incident kind must surface in summary order, including noop rows."""
        sm = outputs["summary.json"]
        inc = _load_json(DATA_DIR / "incidents.json")
        assert isinstance(sm, dict) and isinstance(inc, dict)
        kinds = [str(x["kind"]) for x in inc["incidents"]]
        assert sm["incidents_applied"] == kinds


class TestLedgerSemantics:
    """Spot-check ledger rows that exercise carry, bumps, and halt."""

    def test_ledger_grid_dimensions(self, outputs: dict[str, object], policy_epochs_hops) -> None:
        """The ledger must cover every epoch and hop pair exactly once."""
        epochs, hops = policy_epochs_hops
        rows = outputs["carry_ledgers.json"]["rows"]
        assert isinstance(rows, list)
        assert len(rows) == len(epochs) * len(hops)

    def test_h3_halted_epoch_has_zero_cap_and_carry(self, outputs: dict[str, object]) -> None:
        """A halted hop must show zero cap core and zero carry movement in that epoch."""
        rows = outputs["carry_ledgers.json"]["rows"]
        assert isinstance(rows, list)
        hit = [r for r in rows if int(r["epoch"]) == 1 and str(r["hop_id"]) == "h3"]
        assert len(hit) == 1
        row = hit[0]
        assert int(row["cap_core"]) == 0
        assert int(row["carry_in"]) == 0
        assert int(row["carry_out"]) == 0
        assert int(row["used"]) == 0

    def test_h2_epoch2_reflects_second_cap_add(self, outputs: dict[str, object]) -> None:
        """The second cap bump on hop two must lift the epoch-two cap core before flows."""
        rows = outputs["carry_ledgers.json"]["rows"]
        assert isinstance(rows, list)
        hit = [r for r in rows if int(r["epoch"]) == 2 and str(r["hop_id"]) == "h2"]
        assert len(hit) == 1
        assert int(hit[0]["cap_core"]) == 290


class TestAdmissionAndDenialBranches:
    """Pin representative admit and deny rows from the bundled trace."""

    def test_admissions_sorted(self, outputs: dict[str, object]) -> None:
        """Admission rows follow epoch, hop id, then flow id ascending."""
        rows = outputs["admissions.json"]["admissions"]
        assert isinstance(rows, list)
        keys = [(int(r["epoch"]), str(r["hop_id"]), str(r["flow_id"])) for r in rows]
        assert keys == sorted(keys)

    def test_denials_sorted(self, outputs: dict[str, object]) -> None:
        """Denial rows follow the same ordering rule as admissions."""
        rows = outputs["denials.json"]["denials"]
        assert isinstance(rows, list)
        keys = [(int(r["epoch"]), str(r["hop_id"]), str(r["flow_id"])) for r in rows]
        assert keys == sorted(keys)

    def test_flow_f02_denied_for_headroom(self, outputs: dict[str, object]) -> None:
        """The second hop-one flow must deny with one hundred bytes of headroom."""
        rows = outputs["denials.json"]["denials"]
        assert isinstance(rows, list)
        hit = [r for r in rows if str(r["flow_id"]) == "f02"]
        assert len(hit) == 1
        assert int(hit[0]["epoch"]) == 0
        assert int(hit[0]["requested"]) == 120
        assert int(hit[0]["available"]) == 100

    def test_flow_f07_denied_under_halt(self, outputs: dict[str, object]) -> None:
        """Hop three traffic during halt must see zero available bytes."""
        rows = outputs["denials.json"]["denials"]
        assert isinstance(rows, list)
        hit = [r for r in rows if str(r["flow_id"]) == "f07"]
        assert len(hit) == 1
        assert int(hit[0]["available"]) == 0

    def test_carry_in_feeds_second_epoch_for_h1(self, outputs: dict[str, object]) -> None:
        """Hop one must carry the capped unused budget from epoch zero into epoch one."""
        rows = outputs["carry_ledgers.json"]["rows"]
        assert isinstance(rows, list)
        e0 = [r for r in rows if int(r["epoch"]) == 0 and str(r["hop_id"]) == "h1"][0]
        e1 = [r for r in rows if int(r["epoch"]) == 1 and str(r["hop_id"]) == "h1"][0]
        assert int(e0["carry_out"]) == 60
        assert int(e1["carry_in"]) == 60


class TestIncidentKindCoverage:
    """Ensure every incident kind in the spec appears in the bundled trace."""

    def test_noop_cap_add_halt_resume_all_surface(self, outputs: dict[str, object]) -> None:
        """The bundled incident stream includes noop, cap_add, halt_hop, and resume_hop kinds."""
        kinds = outputs["summary.json"]["incidents_applied"]
        assert isinstance(kinds, list)
        joined = " ".join(str(k) for k in kinds)
        assert "noop" in joined
        assert "cap_add" in joined
        assert "halt_hop" in joined
        assert "resume_hop" in joined
