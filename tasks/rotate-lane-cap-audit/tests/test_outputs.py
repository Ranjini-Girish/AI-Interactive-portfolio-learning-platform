"""Behavioral tests for rotate-lane-cap-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RLC_DATA_DIR", "/app/rlc_lab"))
AUDIT_DIR = Path(os.environ.get("RLC_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["lane_table.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4370fcac0040f21d4a0c9d3fb9617384974439adf901309af05e6191c37e8b99",
    "anchors/a.json": "7589dd6937539275e9ad99651883a8483ec22f43a9c0e384151c1cebc86b3543",
    "anchors/b.json": "2c437547ad8c4cfd92339f9182af2b7f8acd128b57f20d43765a674126643feb",
    "ancillary/w.json": "154bfec51f75e32f479372701974117abceef6006ba435597691d0b206f9112a",
    "ancillary/x.json": "e72796b9c748dd883bcacffeafc0a332ce87cc9eb53d61db68b05fc0ff0d0af6",
    "ancillary/y.json": "0d6e98eaf0a78263855c2c5e2e93e50364b524646ac0dc97f9a92d768d2570b5",
    "ancillary/z.json": "1cf8f42717456d22f2731ef7453f299557c9f51e17ec9255f5470c29836bde57",
    "incident_log.json": "b83fd1146147ba629584647da0a3680784406dc770cddbd9932b994bfc708613",
    "items/item_00.json": "582f7bb4f5e881327932115a0e11b0048a9064c9aecfe4181af9f32d18b1887a",
    "items/item_01.json": "dc75428b24a5cf776074a0fde4d64b0702a44f209dd2e6aa0c8bda0582b4466a",
    "items/item_02.json": "0029936f9ffd9a2af2e91e4151e78842adfe6eb12a74efe14158db0956595b5c",
    "items/item_03.json": "bdc9a1524e9a92a724863f217ba9a6148491f4a03a0807dfa068e63e05ea20a6",
    "items/item_04.json": "2a8a162cda1043ea2f13669128a9d1d01bcc3554fb1abb1ee25c6b15e2ccb66b",
    "items/item_05.json": "a311aefcdf8c2e084521490a5a2a2c5ede6060727ce52cb4df9b05ba0acf8253",
    "items/item_06.json": "a2289fe6c0674e311c4ff8df969e71cbc0f79b3949c189531b3244be414f7bec",
    "items/item_07.json": "c1e4a65cf9705a6fb9ad52042d7a7581158d270df929c5cbe6ac67a68671bdf9",
    "items/item_08.json": "33d2fa5ea1238b1c8f5af59005e0c9fbabfd8b13e83146403c7c32b061e797f8",
    "items/item_09.json": "0162e3a4d3bacd02ced668e880ee4bd3e975132901c0668e64a36b1a438c83ab",
    "items/item_10.json": "547289ea1fd6cb562736ac94e89d2fdc561118ef13493139546846f15358d418",
    "items/item_11.json": "a2bf28032ef42157d48064b1f05f412547d8c9ec5486e85c87e3be76a9126183",
    "policy.json": "6841fa785ac8e3558ac9c8fed5888f5151c6d459b807a0f764f50b58cbe67da4",
    "pool_state.json": "6067873f970e84439cf00da57ea367097956b51cc2cd1415718643f600e3bbd9",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "lane_table.json": "375cf7aad7e848d9d8453b59b82e291b0f11aec32f55cea6cc2cf3a36467aedd",
    "summary.json": "e843ce906d6d0e770c64d34b4b34c80b5baf39f91dedbf93a0284dfea9982f64",
}


EXPECTED_FIELD_HASHES = {
    "lane_table.json.lanes": "b31fe78d5089fbfa07d408a93ff8aeae44fcda25951e54064cfd5faae841ce91",
    "summary.json.regions": "15bdb49e8d76c7f5fe8a99dd1e0db19d39fca8af0a4a282a58504c1a09a19847",
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

    def test_regions_keys_track_active_policy_labels(self) -> None:
        """Region totals include exactly the active region labels sorted."""
        policy = _load_json(DATA_DIR / "policy.json")
        active = sorted(str(x) for x in policy["active_regions"])
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        regions = summary["regions"]
        assert isinstance(regions, dict)
        assert sorted(regions.keys()) == active

    def test_lane_rows_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """Lane table stays lexicographically ordered by identifier."""
        lt = outputs["lane_table.json"]
        assert isinstance(lt, dict)
        rows = lt["lanes"]
        assert isinstance(rows, list)
        ids = [str(row["lane_id"]) for row in rows]
        assert ids == sorted(ids)

    def test_applied_events_counts_unknown_kind(self) -> None:
        """Unknown incident kinds still advance the applied counter."""
        summary = _load_json(AUDIT_DIR / "summary.json")
        assert isinstance(summary, dict)
        assert int(summary["applied_events"]) == 4

    def test_mingled_flag_present_on_rows(self, outputs: dict[str, object]) -> None:
        """Each lane row records whether mingle logic fired."""
        lt = outputs["lane_table.json"]
        assert isinstance(lt, dict)
        for row in lt["lanes"]:
            assert isinstance(row, dict)
            assert "mingled" in row
