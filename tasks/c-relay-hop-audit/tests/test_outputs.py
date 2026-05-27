"""Verifier suite for the C relay hop capacity audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CRA_DATA_DIR", "/app/relayhop"))
AUDIT_DIR = Path(os.environ.get("CRA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "admissions.json",
    "denials.json",
    "carry_ledgers.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4ad0d9d8b0f4640ee7724db8fa9b1d8855a8018e105e969ec23e16d8a526dcf6",
    "anchors/a01.txt": "6d7ae7451f6d9524ddec6b118872ef2ddcb3066f18e72b2964d35bf997aa2bb9",
    "anchors/a02.txt": "98e8883d0c503325a7b4b573dbcb1fd5870008491242b63fce56ce0c2056041c",
    "anchors/a03.txt": "1c6e99533ba0ced416ca989569400fc65372aadf975aa490dd9a2b5048c632e8",
    "flows/f01.json": "cf07f2a61d722c17039a0ac7e5bb4f73e1deca115d66a8d6c5cdb411ece697c4",
    "flows/f02.json": "54362d31b2ec549402d204ba1a9443657cf200453496aca8273a9afd3e365e62",
    "flows/f03.json": "5ce3c642641cf79b1510675c092c81909a302db82f9424acd3371dcd48a74bb6",
    "flows/f04.json": "9ef1ad5380cc0532346c9cec824e5fd929263697bbfc3a8205cf5990426c79df",
    "flows/f05.json": "f600c34447f5712079ca0eb5fdeb06fe7f6dddf53e7d133c3afe9a3a43ceea58",
    "flows/f06.json": "2c426d023a5f25ff7e93da8354e40755a411eeab71edde2dff8225e516e2a55b",
    "flows/f07.json": "80d650bad611eb1bb33f26be5df984cfd651ff7c1a5fa88b1c0940987e5c55fa",
    "flows/f08.json": "3e59a010875d1cb91f29415cb22071b746b1f974a91a151433996d519c924f53",
    "flows/f09.json": "65d68d2f2d358eae791afbaace74796f129e226d5606d8e0ca39e674616f6941",
    "flows/f10.json": "27813803dd2e0032d219e4e50e940abe968c219d9c8b4f964a6defdb6671ab1d",
    "flows/f11.json": "8412dd5476d10d24400881a9c50a5aeb06253e25aec201406babb52bccb1e36e",
    "flows/f12.json": "fb96c0423faca3f474c888f221cb3eb5e67f9cc270f04012b6813ab632e071cb",
    "flows/f13.json": "f602b98b63a8df10b9d1461210de91df70731136e9ce538959751b9c226e2a71",
    "flows/f14.json": "1047c353683a47ffddaa42007e06ee1c6efc1629f2216493a6f1f803be80bf03",
    "hops/h01.json": "ee62693610184e63e327e0c1d1bf8015e59d2a93acfdbf94049111766b8c482a",
    "hops/h02.json": "30a59310b2772ffafffaaaf46292a8b10e3561187fbc1ce8bf933e693df05893",
    "hops/h03.json": "2033df539b04e2952b784c63598e4c44b89faa5af4139bc42c0a37b602d0e660",
    "hops/h04.json": "dff3445eeae2ebd9d4f3b3052c4657c30cfd3e705d4e1bdafccf0573bb13d40a",
    "incidents.json": "e09f12dd4a095194849cbaf5f644ca32cecdf2f6c219aef4e7115c5169426ec3",
    "policy.json": "3b024a5a5f5fa779beb599d5a6c1d93073c4a82d5bfaa0511e358249cd744e6f",
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


def _spec_json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


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
    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_output_on_disk_matches_spec_json_encoding(
        self, outputs: dict[str, object]
    ) -> None:
        """On-disk bytes must match SPEC canonical JSON formatting."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

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
    def test_noop_cap_add_halt_resume_all_surface(self, outputs: dict[str, object]) -> None:
        """The bundled incident stream includes noop, cap_add, halt_hop, and resume_hop kinds."""
        kinds = outputs["summary.json"]["incidents_applied"]
        assert isinstance(kinds, list)
        joined = " ".join(str(k) for k in kinds)
        assert "noop" in joined
        assert "cap_add" in joined
        assert "halt_hop" in joined
        assert "resume_hop" in joined
