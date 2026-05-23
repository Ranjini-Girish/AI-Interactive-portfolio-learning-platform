"""Behavioural tests for cryostat-lattice-audit.

The verifier checks four canonical JSON artifacts under ``/app/audit/``
against pinned digests for the read-only cryostat fixture tree.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CLR_DATA_DIR", "/app/cryostat"))
AUDIT_DIR = Path(os.environ.get("CLR_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "sensor_verdicts.json",
    "thermal_relaxed.json",
    "incident_touch.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "860df3eed194f471babe0b3321f66fddb47e7e988232fcedee9fd85d74f35c8c",
    "arrays/manifest.json": "18514067a7be2113596844373c650944ce48bb5b10b6c3a6aad54fc22217712a",
    "calibration/linear.json": "bb005a00d5fd7620341e917e3d81d02bc96aca91d603b5fbb63624991bb00d76",
    "incidents/incident_log.json": "45afb168e918751b9844d76b5fa9d6805666de0faec18f4059f01b15a43f7fd1",
    "pool_state.json": "8892b8cab0a55f1780041b68a80a2238a6fe537ec7f2c6136b917c8a5d603fa7",
    "readings/readings.json": "983775b1ccd1f1bc07372b31601d5242f325f462912136afb9fcd2ca943c5c36",
    "rigs/east.json": "2296dcafb617d44969a9b4262dd2c03841d72a6ff086f57dc2556394ee5dec7b",
    "rigs/north.json": "7df1e5fd68420a14f857bc1ecb2054bbb57c2f8238de5dd00b5179782f0035b7",
    "rigs/south.json": "db9d79916db7f00e79773378a06fb117f26c0e6457475092a551ce63401f39af",
    "sensors/s01.json": "440f668588d990f59daaae739e213b50ec6603f1d136807aabe00244b39bb515",
    "sensors/s02.json": "75f598edf6faac8e71070d7e100e340b4a58b63ea7d1a237b34e9e5d33316cdd",
    "sensors/s03.json": "fb6574855341c52f22b771543353efa723880fa93a72c2def18ebd1112f94352",
    "sensors/s04.json": "b1fc64602bbc1a6961946d1bbc0204bc7abba5abac72587056f05b242a57ffaa",
    "sensors/s05.json": "4fe864df861ddd149feefdc65e4d6c7f39cf99a041657a562d5e56e580964475",
    "sensors/s06.json": "427a13566a97aa13b73e139bb4d2478ecf1a0ede6a7deb49ac6250061f842d69",
    "sensors/s07.json": "b433bdc7b8ba720a8238cafcfd72ceb24b066efe0e8dde146a0a9538ca82a2ae",
    "sensors/s08.json": "a13b8b3f6943fab3372040618648bd25e0fb8e5ba6a1b2d07965222d21971a2f",
    "sensors/s09.json": "9bd61b90da18f2b7e7f3c5a752287e2fc8e2e8b590ebc44a0cda39972b7f2c2e",
    "sensors/s10.json": "6df0338fcc1ef30141883dfebe9e5e2c7aa41b16e12272de15fe2c79d6131a53",
    "sensors/s11.json": "e40d31d6a51cc9881598becb6a6cb556c9e9aeb04b437a6e028d103bb5d59c79",
    "sensors/s12.json": "607454ef3d344375da528dff1b87b020cc5fa0c08bf34f566b043b7994a1925f",
    "thermal/edges.json": "34231c4cdc7486f45a0c1ba04cda65ce2aea192d945afb1caa3c93afdf2faa34",
    "zones/alpha.json": "0ad9e5f4e1b914fdadac26adfc7ba7e30850e2233182bfc4008dd4ca9b32a053",
    "zones/beta.json": "f10ad83a7eda60a8db4499aa693955718c0ad0eb4a42da6b511e0ef5de4834a3",
    "zones/gamma.json": "40c5bb43442b95059741e6ce4a70f5e7db37743e54603317100120a89404ca8e",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "incident_touch.json": "ff0140a15eab6182ccfdcb39a0307cdbbd5ed623a9721bd1da5a09cb422378c2",
    "sensor_verdicts.json": "31f6d62ecba01e31e96395f171cf06a74988244d91ae4910161cc1cf6d8360ae",
    "summary.json": "12295183f294a21d8ef07f3173ca645edc75e69162d7be6204659b0b94340ac5",
    "thermal_relaxed.json": "c83742372d06eaa3cb889a4ac3442b63be0a2ec4aa5533f84b89181413bae1f9",
}

EXPECTED_FIELD_HASHES = {
    "incident_touch.touches": "f9a03c71d417dec1eb2b0259f14876f0885571982ce8f35177a919182c8fb9f5",
    "sensor_verdicts.verdicts": "8d05f948294efde8fc4bfb280961a93f557d4df23dd01e1125c630733010acb9",
    "summary.as_of_day": "95cf32708a31caa478a0e9141103ac567d85e5186e697e7e0c81f75589999e31",
    "summary.edge_count": "06e9d52c1720fca412803e3b07c4b228ff113e303f4c7ab94665319d832bbfb7",
    "summary.reading_rows": "19b8d5c59e421f037fe563007c7254eb8d98bc221b278c3db3e5fdbbfd52e273",
    "summary.relax_rounds": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.sensor_count": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.verdict_counts": "88197cff2bcec57db1149ea5c9aabb1a67856967a57728bf82f517bf74aa3e4a",
    "thermal_relaxed.temps": "b5d8671d1e4950140c8f477884a4d253eb84555342659fd5c997ee76ec91652d",
}

SUMMARY_TOP_KEYS = {
    "as_of_day",
    "edge_count",
    "reading_rows",
    "relax_rounds",
    "sensor_count",
    "verdict_counts",
}

VERDICT_ENUM = {
    "lattice_faulted",
    "missing_read",
    "ok",
    "out_of_range",
    "precommission",
    "stale_calibration",
    "strap_quenched",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj: object) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    """Load audit JSON once."""
    out: dict[str, dict] = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Cryostat fixtures must remain byte-identical."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_file_unchanged(self, rel):
        """Each file under the cryostat tree must match its pinned SHA-256."""
        path = DATA_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        actual = _sha256_bytes(path.read_bytes())
        expected = EXPECTED_INPUT_HASHES[rel]
        assert actual == expected, (
            f"input file /app/cryostat/{rel} was modified (expected {expected}, got {actual})"
        )


class TestOutputStructure:
    """Audit outputs exist with canonical pretty JSON."""

    def test_audit_directory_exists(self):
        """``/app/audit`` must exist as a directory."""
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Each required filename must exist under ``/app/audit/``."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    def test_no_extra_files_in_audit_dir(self):
        """The audit directory must contain exactly the four required files."""
        actual = sorted(p.name for p in AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES), (
            f"/app/audit must contain exactly {sorted(REQUIRED_OUTPUT_FILES)}; found {actual}"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_ends_with_single_newline(self, loaded_outputs, name):
        """Each file ends with exactly one ``\\n``."""
        b = loaded_outputs[name]["bytes"]
        assert b.endswith(b"\n"), f"{name} must end with a trailing newline"
        assert not b.endswith(b"\n\n"), f"{name} must end with exactly one trailing newline"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_matches_canonical_pretty_form(self, loaded_outputs, name):
        """On-disk bytes must match ``json.dumps(..., indent=2, sort_keys=True) + '\\n'``."""
        obj = loaded_outputs[name]["obj"]
        expected_bytes = (
            json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        ).encode("utf-8")
        assert loaded_outputs[name]["bytes"] == expected_bytes, (
            f"/app/audit/{name} bytes do not match canonical pretty JSON encoding"
        )

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_object_keys_sorted_at_every_level_on_disk(self, name):
        """Every JSON object must emit keys in sorted order at all depths."""
        path = AUDIT_DIR / name
        ordered = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=collections.OrderedDict,
        )
        violations: list[str] = []

        def walk(node: object, path_str: str) -> None:
            if isinstance(node, collections.OrderedDict):
                keys = list(node.keys())
                if keys != sorted(keys):
                    violations.append(
                        f"{path_str}: keys not sorted; got {keys}, expected {sorted(keys)}"
                    )
                for key, value in node.items():
                    walk(value, f"{path_str}.{key}")
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, f"{path_str}[{index}]")

        walk(ordered, name)
        assert not violations, "key sort violations:\n  - " + "\n  - ".join(violations)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, loaded_outputs, name):
        """Compact canonical SHA-256 of each root object must match the pin."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, f"/app/audit/{name} canonical hash mismatch"


class TestFieldHashes:
    """Pinned sub-object hashes."""

    @pytest.mark.parametrize("field_key", sorted(EXPECTED_FIELD_HASHES.keys()))
    def test_field_canonical_hash(self, loaded_outputs, field_key):
        """Each ``file.key`` fragment must match its pinned canonical hash."""
        stem, _, sub = field_key.partition(".")
        obj = loaded_outputs[f"{stem}.json"]["obj"]
        fragment = obj
        for part in sub.split("."):
            fragment = fragment[part]  # type: ignore[index]
        actual = _canonical_sha256(fragment)
        expected = EXPECTED_FIELD_HASHES[field_key]
        assert actual == expected, f"field hash mismatch for {field_key}"


class TestSummaryShape:
    """Summary counters match the documented top-level key set."""

    def test_summary_top_level_keys(self, loaded_outputs):
        """Summary exposes exactly the counters named in SPEC."""
        obj = loaded_outputs["summary.json"]["obj"]
        assert set(obj.keys()) == SUMMARY_TOP_KEYS
        assert obj["relax_rounds"] == 3
        for k, v in obj["verdict_counts"].items():
            assert k in VERDICT_ENUM, f"unknown verdict key {k!r}"
            assert isinstance(v, int) and v > 0


class TestVerdictCoverage:
    """Each documented verdict string appears on at least one sensor row."""

    def test_ok_fixture_sensor(self, loaded_outputs):
        """Sensor ``s01`` is in-range after relaxation in the fixture."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s01"]["verdict"] == "ok"
        assert "rig_warm:north:20" in rows["s01"]["reasons"]
        assert "calib_drift" in rows["s01"]["reasons"]

    def test_out_of_range_after_relaxation(self, loaded_outputs):
        """Sensor ``s02`` is pushed past its high tolerance by relaxation in round 2."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s02"]["verdict"] == "out_of_range"
        assert "rig_warm:north:20" in rows["s02"]["reasons"]

    def test_overlay_reason_on_sensor_s03(self, loaded_outputs):
        """Overlay applies to ``s03`` and must appear among sorted reasons."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert "overlay" in rows["s03"]["reasons"]
        assert rows["s03"]["verdict"] == "ok"

    def test_stale_calibration_no_drift(self, loaded_outputs):
        """Sensor ``s04`` has a calibration horizon ahead of its reading day."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s04"]["verdict"] == "stale_calibration"
        assert "calib_drift" not in rows["s04"]["reasons"]

    def test_missing_read_fixture_sensor(self, loaded_outputs):
        """Sensor ``s05`` has no in-window reading and no chosen ADC."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s05"]["verdict"] == "missing_read"
        assert rows["s05"]["relaxed_millic"] is None
        assert rows["s05"]["reading_day"] is None

    def test_strap_quench_fixture_sensor(self, loaded_outputs):
        """Sensor ``s06`` carries the strap-quench incident verdict."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s06"]["verdict"] == "strap_quenched"
        assert any(x.startswith("strap_quench:") for x in rows["s06"]["reasons"])

    def test_lattice_fault_fixture_sensors(self, loaded_outputs):
        """Sensors ``s07`` and ``s08`` share the lattice fault component."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s07"]["verdict"] == "lattice_faulted"
        assert rows["s08"]["verdict"] == "lattice_faulted"

    def test_precommission_fixture_sensor(self, loaded_outputs):
        """Sensor ``s09`` has historical readings only before its commission day."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s09"]["verdict"] == "precommission"
        assert rows["s09"]["reading_day"] is None


class TestAggregationSemantics:
    """Median-of-K aggregation, rejection, and reading_day semantics."""

    def test_s08_rejected_first_reading_shifts_reading_day(self, loaded_outputs):
        """Sensor ``s08`` has its day-50 row rejected (adc <= 0); kept reading_day = 49."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s08"]["reading_day"] == 49

    def test_relaxed_temps_match_pin(self, loaded_outputs):
        """Sensors with chosen readings expose a pinned relaxed integer map."""
        temps = loaded_outputs["thermal_relaxed.json"]["obj"]["temps"]
        assert set(temps.keys()) == {
            "s01", "s02", "s03", "s04", "s06", "s07", "s08", "s10", "s11", "s12",
        }
        for v in temps.values():
            assert isinstance(v, int)


class TestEdgeFreezing:
    """Verdict-aware edge freezing must use end-of-previous-round band status."""

    def test_s11_kept_in_band_despite_cold_neighbour(self, loaded_outputs):
        """Sensor ``s11`` stays inside its band because cold neighbour ``s10`` freezes after round 1."""
        rows = {r["sensor_id"]: r for r in loaded_outputs["sensor_verdicts.json"]["obj"]["verdicts"]}
        assert rows["s11"]["verdict"] == "ok"
        assert rows["s10"]["verdict"] == "out_of_range"


class TestSummaryInvariants:
    """Cross-field checks implied by SPEC."""

    def test_verdict_counts_sum_to_sensor_count(self, loaded_outputs):
        """Per-verdict totals must sum to the number of sensor registry files."""
        s = loaded_outputs["summary.json"]["obj"]
        total = sum(s["verdict_counts"].values())
        assert total == s["sensor_count"]

