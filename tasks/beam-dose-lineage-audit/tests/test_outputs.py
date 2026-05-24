"""Behavioural tests for beam-dose-lineage-audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("BDL_DATA_DIR", "/app/beamline"))
AUDIT_DIR = Path(os.environ.get("BDL_AUDIT_DIR", "/app/audit"))
SRC_DIR = Path(os.environ.get("BDL_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("BDL_BIN_PATH", "/app/bin/bdlaudit"))

REQUIRED_OUTPUT_FILES = [
    "dose_assessment.json",
    "lineage_impact.json",
    "window_utilization.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "4cb10b08686b6502f873582c06825b19c64f1aac46004135a9fca2d490f2ceca",
    "incidents/events.json": "631bd97115e500561dc592254255964ce83f40c9152868a77a97ea36b4dda7d5",
    "policy/tier_rules.json": "f825e30e8dbdc67654af5c04bab8704477f365fa32558901c3f8ec538dfd5a7b",
    "pool_state.json": "591a7de45f8748b1c87602d5af6100a889101527c81888258c521c404a54e338",
    "profiles/p-high.json": "4291c8c1e76c31a215d1819f4c5c11ac6b24d95aeeb77848da293e0f0ff4820b",
    "profiles/p-low.json": "7c566c1a56f0e51ea39b955ca0429a66ef7765962c00af6de7130f6f090545c7",
    "profiles/p-micro.json": "fbda8a7ccdd828f93ab97864fd661cf95bf703ab0054f00bfacbec7909f29452",
    "runs/r01.json": "1e0af3a4197aa629dd5a3eef0d77a9d82fcbdd46bf4aed183a032f8a254ef909",
    "runs/r02.json": "32c3cf9388101374b6975498998630d25adaa798d68ce002a335af85c8b54160",
    "runs/r03.json": "4691d871a090335db270553236fdcfb7281394202b7652e65530f0f6c5828ed6",
    "runs/r04.json": "89741b1ab0d2a2e732ea9655ad4371b980691f702002689bf2f0ff706c9785cd",
    "runs/r05.json": "0c9bce4755a63e1a50de0aedcb312c9f388a2ad5186787fe8360af2dc745f85b",
    "runs/r06.json": "499a0fe340939f4898eb1994eeabb2652b2efeb00a129debe33c9f9f922b3d74",
    "runs/r07.json": "2362c5b06cdef8ddfb05b4716e1bbfc6bb1d7fb1b2d657c3be70365974adec53",
    "runs/r08.json": "ce0ba8da4b18176e984a214104b44326d58330464a063694c82468f703c93216",
    "runs/r09.json": "d1e76ead011b9f7e716d422d64c72e69e5ef55c337f8b37d1209ac2f409ea37a",
    "runs/r10.json": "8052b7bf4ed30cf190837220ad8f9291edf4eaaf590a53d99f01519a660ad0d3",
    "runs/r11.json": "f5e121dc3fb33c084ea0dfafe726f82b95006324847744ebc9018714b09a494f",
    "runs/r12.json": "4b4c54c1566c7854e82499aeb49db82eb8f18cbecbaf50c7992bdd7c507ec8b0",
    "specimens/s-alpha.json": "79bab4ddf0e3671dc004d96ae06575724b65a9f95e56b527264827aac9280bfd",
    "specimens/s-beta.json": "94afb05a611c8aa7995b25e1229bf4eaf3042f6334be17c3361e0850028711c3",
    "specimens/s-delta.json": "e7f872f7b35fb5dc3460ace28182269def2ffe3622a36cac0103ac2244a0773c",
    "specimens/s-epsilon.json": "0064579701648d5cfbbf74b54d40b1dc2adc4aed9f21d2848b6afef984a008d5",
    "specimens/s-eta.json": "39f3c4ac0c75dabfee100530cefb6a0281178e8e0ee3eebfbffd9160b00a4a10",
    "specimens/s-gamma.json": "778c3f7cdd0ecd6dfd61d4351d987a28c3bafdf5eacc87c1af6786b2a4b96c87",
    "specimens/s-iota.json": "2dc75ea98c43835d18ee170df32d75dfab96bcce4b18f5f30bdfa208a9849bc7",
    "specimens/s-kappa.json": "0d9040bbc0d472ef716b0430654333daf40e455747adfc82e1d547d4d83740a5",
    "specimens/s-lambda.json": "4eaccd11dfdbcb7694b3d086756920ae493ef9c45110ce6b65f629fc8da754d4",
    "specimens/s-mu.json": "19fcbea6abcb61e37e2e1d8704d87503c0b1e3892ccd13d32875754594582782",
    "specimens/s-theta.json": "386473435a1eea0b020ec927f282c3f1f84d185240711c7c858fd821c54ee4b9",
    "specimens/s-zeta.json": "40e83bf1b72da20e7546ab9dabd9e6fd80323f28079dacee48f111267d85c95f",
    "windows/w-alpha.json": "d6a7306fa0da33018be175d482976e95a62dd7d6a28f9d823f10932b18377439",
    "windows/w-beta.json": "04eb4789249ce8f2b4d2f3ffe4a6d7cfcbc2f55b7eb4bfec9471197cd518817c",
    "windows/w-gamma.json": "b84487ab0f4d5521ac96d944c83f895a967aa1aee39ba4722356cdbd17bded74",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "dose_assessment.json": "021bc25061c11d5a3020d7fa1e62c61863ec5bf423b2a363427e30638a1fd88b",
    "lineage_impact.json": "dc866523cd2f782e215a0ca2aaba140a36e929d976f75d6ea455729862c3dc98",
    "summary.json": "d194dd14502e049bcca973435a4be7af043b6c20fc479e8c4e32d286fb2f13b6",
    "window_utilization.json": "ce4549f5fc4501222a7bcda4da39fcdf7078a1e16354f773bac6431a3dd17b03",
}

EXPECTED_FIELD_HASHES = {
    "dose_assessment.runs": "fe10a50d77e12ce46a5d95e05692d6b7ed225154823e199da665ddebb6f8ddba",
    "lineage_impact.specimens": "dbf6bb31723f2f2f9eff8fef547da9f8d87b12b2b87687d10cf118419463f927",
    "summary.as_of_minute": "862db587c4257f71293cf07cafc521961712c088a52981f3d81be056eaabc95e",
    "summary.frozen_windows": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.ignored_incident_events": "f0b5c2c2211c8d67ed15e75e656c7862d086e9245420892a7de62cd9ec582a06",
    "summary.lineage_status_counts": "3550e3ad6b8b63ddeb3f235e9131eacf985d8c5690a6da3f63af921837b1e434",
    "summary.run_count": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.specimen_count": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
    "summary.status_counts": "9cd7c9819efb0d68c70666e609eedf389a72621611071a39f5e7619172abe17d",
    "window_utilization.windows": "c76a264e1ab27b4f8b72cfccd512db8bf99c1a938898a2eed6f47b9a17786244",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj: object) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    """Load emitted audit files once for the module."""
    out: dict[str, dict] = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {exc}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


class TestInputIntegrity:
    """Beamline fixtures must remain byte-identical."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES))
    def test_input_file_unchanged(self, rel):
        """Every file under the dataset tree must match its pinned SHA-256."""
        path = DATA_DIR / rel
        assert path.is_file(), f"required input file missing: {path}"
        assert _sha256_bytes(path.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestOutputStructure:
    """Audit outputs exist with canonical pretty JSON."""

    def test_audit_directory_exists(self):
        """The audit directory must exist."""
        assert AUDIT_DIR.is_dir(), "/app/audit must exist as a directory"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_file_exists(self, name):
        """Every required output file must be present."""
        assert (AUDIT_DIR / name).is_file(), f"missing /app/audit/{name}"

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_pretty_json_has_one_trailing_newline(self, loaded_outputs, name):
        """Each file must be two-space pretty JSON with one final newline."""
        obj = loaded_outputs[name]["obj"]
        expected = json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        assert loaded_outputs[name]["text"] == expected

    @pytest.mark.parametrize("name", sorted(EXPECTED_OUTPUT_CANONICAL_HASHES))
    def test_canonical_output_hash(self, loaded_outputs, name):
        """Each full output object must match the pinned canonical hash."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        assert actual == EXPECTED_OUTPUT_CANONICAL_HASHES[name]

    @pytest.mark.parametrize("field", sorted(EXPECTED_FIELD_HASHES))
    def test_field_hash(self, loaded_outputs, field):
        """Important top-level fields must match their pinned canonical hash."""
        file_stem, key = field.split(".", 1)
        obj = loaded_outputs[f"{file_stem}.json"]["obj"]
        assert key in obj
        assert _canonical_sha256(obj[key]) == EXPECTED_FIELD_HASHES[field]


class TestDoseAssessment:
    """Per-run status and dose rules must follow the contract."""

    def test_all_status_enum_values_are_exercised(self, loaded_outputs):
        """The fixture covers every documented run status except missing shots."""
        rows = loaded_outputs["dose_assessment.json"]["obj"]["runs"]
        statuses = {row["status"] for row in rows}
        assert {
            "bad_quality",
            "cyclic_lineage",
            "lineage_contaminated",
            "no_window",
            "ok",
            "over_dose",
            "specimen_hold",
            "window_frozen",
        }.issubset(statuses)

    def test_median_rejects_dark_and_non_positive_pulses(self, loaded_outputs):
        """Run r01 drops the zero pulse, applies dark-current rejection, and uses K recent."""
        rows = {row["run_id"]: row for row in loaded_outputs["dose_assessment.json"]["obj"]["runs"]}
        assert rows["r01"]["median_adjusted_pulse"] == 110
        assert rows["r01"]["effective_dose_mgy"] == 16

    def test_dose_override_still_allows_over_dose(self, loaded_outputs):
        """Run r08 uses the accepted override and remains over the primary dose cap."""
        rows = {row["run_id"]: row for row in loaded_outputs["dose_assessment.json"]["obj"]["runs"]}
        assert rows["r08"]["effective_dose_mgy"] == 130
        assert rows["r08"]["status"] == "over_dose"
        assert "dose_override:r08" in rows["r08"]["reasons"]

    def test_precedence_blocks_quality_and_window_checks_after_lineage(self, loaded_outputs):
        """Lineage contamination outranks later quality and dose checks."""
        rows = {row["run_id"]: row for row in loaded_outputs["dose_assessment.json"]["obj"]["runs"]}
        assert rows["r03"]["status"] == "lineage_contaminated"
        assert rows["r12"]["status"] == "lineage_contaminated"
        assert rows["r12"]["window_id"] == "w-gamma"


class TestLineageImpact:
    """Specimen ancestry, contamination propagation, and cycles are audited."""

    def test_direct_and_inherited_contamination_depths(self, loaded_outputs):
        """Contamination from s-beta reaches descendants with minimum depths."""
        rows = {
            row["specimen_id"]: row
            for row in loaded_outputs["lineage_impact.json"]["obj"]["specimens"]
        }
        assert rows["s-beta"]["lineage_status"] == "direct_contam"
        assert rows["s-beta"]["contam_depth"] == 0
        assert rows["s-gamma"]["contam_depth"] == 1
        assert rows["s-delta"]["contam_depth"] == 2

    def test_cycles_outrank_other_lineage_states(self, loaded_outputs):
        """The zeta/eta parent loop must be reported as cyclic."""
        rows = {
            row["specimen_id"]: row
            for row in loaded_outputs["lineage_impact.json"]["obj"]["specimens"]
        }
        assert rows["s-zeta"]["lineage_status"] == "cyclic"
        assert rows["s-eta"]["lineage_status"] == "cyclic"


class TestWindowUtilization:
    """Window assignment and capacity accounting must match the contract."""

    def test_frozen_window_charges_zero(self, loaded_outputs):
        """Frozen windows still list assigned runs but charge no capacity."""
        rows = {
            row["window_id"]: row
            for row in loaded_outputs["window_utilization.json"]["obj"]["windows"]
        }
        assert rows["w-beta"]["assigned_runs"] == ["r05"]
        assert rows["w-beta"]["charged_weight"] == 0
        assert rows["w-beta"]["status"] == "frozen"

    def test_over_capacity_counts_chargeable_non_ok_runs(self, loaded_outputs):
        """Bad-quality and over-dose rows consume capacity on w-gamma."""
        rows = {
            row["window_id"]: row
            for row in loaded_outputs["window_utilization.json"]["obj"]["windows"]
        }
        assert rows["w-gamma"]["charged_weight"] == 6
        assert rows["w-gamma"]["status"] == "over_capacity"


class TestSummary:
    """Aggregate counts must agree with detailed outputs."""

    def test_status_counts_match_rows(self, loaded_outputs):
        """Summary status counts must be derived from dose rows."""
        rows = loaded_outputs["dose_assessment.json"]["obj"]["runs"]
        expected: dict[str, int] = {}
        for row in rows:
            expected[row["status"]] = expected.get(row["status"], 0) + 1
        assert loaded_outputs["summary.json"]["obj"]["status_counts"] == expected

    def test_lineage_counts_match_rows(self, loaded_outputs):
        """Summary lineage counts must be derived from specimen rows."""
        rows = loaded_outputs["lineage_impact.json"]["obj"]["specimens"]
        expected: dict[str, int] = {}
        for row in rows:
            expected[row["lineage_status"]] = expected.get(row["lineage_status"], 0) + 1
        assert loaded_outputs["summary.json"]["obj"]["lineage_status_counts"] == expected


class TestImplementationLanguage:
    """The audit must be implemented as a Go program that can regenerate outputs."""

    def test_go_source_present(self):
        """The source tree must include a Go file declaring package main."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist and contain Go source"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files found under {SRC_DIR}"
        assert any(
            re.search(r"^\s*package\s+main\b", p.read_text(encoding="utf-8"), re.MULTILINE)
            for p in go_files
        )

    def test_binary_present(self):
        """The compiled executable must be present."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_reproduces_outputs(self):
        """A fresh execution of the binary must reproduce the audit files."""
        saved = {name: (AUDIT_DIR / name).read_bytes() for name in REQUIRED_OUTPUT_FILES}
        backup = AUDIT_DIR.parent / (AUDIT_DIR.name + ".backup_for_replay")
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(AUDIT_DIR), str(backup))
        try:
            with tempfile.TemporaryDirectory() as td:
                env = os.environ.copy()
                env["BDL_DATA_DIR"] = str(DATA_DIR)
                env["BDL_AUDIT_DIR"] = td
                result = subprocess.run(
                    [str(BIN_PATH)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                assert result.returncode == 0, (
                    f"binary exit code {result.returncode}\n"
                    f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
                )
                for name in REQUIRED_OUTPUT_FILES:
                    fresh = (Path(td) / name).read_bytes()
                    assert fresh == saved[name], f"fresh binary output differs for {name}"
                    assert (
                        _canonical_sha256(json.loads(fresh.decode("utf-8")))
                        == EXPECTED_OUTPUT_CANONICAL_HASHES[name]
                    )
        finally:
            if AUDIT_DIR.exists():
                shutil.rmtree(AUDIT_DIR)
            shutil.move(str(backup), str(AUDIT_DIR))
