"""Behavioral tests for pawn-endgame-table-audit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PET_DATA_DIR = Path(os.environ.get("PET_DATA_DIR", "/app/pawn_endgame"))
PET_AUDIT_DIR = Path(os.environ.get("PET_AUDIT_DIR", "/app/audit"))
PET_SRC_DIR = Path(os.environ.get("PET_SRC_DIR", "/app/src"))
PET_BIN_DIR = Path(os.environ.get("PET_BIN_DIR", "/app/bin"))
PAWNAUDIT_BIN = PET_BIN_DIR / "pawnaudit"

REQUIRED_OUTPUT_FILES = [
    "passed_pawn_races.json",
    "opposition_grid.json",
    "tempo_loss_windows.json",
    "underpromotion_caps.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "b45cc31c0bd1b59fafdfe1f212a33580bb69a25cd40f063313d272957e214e29",
    "grid_sources/g01.json": "4d4ca6c8d404f4aa5955a64aad2b3e1c61b2c034e98f28980f10907927c79aa1",
    "grid_sources/g02.json": "7942e9806eb9573996af37f92cfb241c21213dd30ebbe5c69df207f07c985c09",
    "grid_sources/g03.json": "d76c816b3032f1c572b81618f74a30f986b850e52af66f40638b6f29102c68e7",
    "incidents/incident_log.json": "0c52f12e5095462e944159f71ae81014cd9b56532505d1c9e1ec89a61d4855c9",
    "manifest.json": "40db7811259c068f322107b313ba68fe40df5ef5cc994d6e9d9d200338361bc2",
    "policy/caps.json": "07f4a6629e81a3fbd304955c82c586f3e42449bed2a4f26ce91af2387759fa04",
    "policy/opposition_tiebreak.json": "7498ad1a1aaf588bb7b825d5d269a7d53bd664f94516c4be0a1b02e967b9166b",
    "policy/tempo_policy.json": "7dfbbc22bf2ec99df0d41ed2a0c7084981716775aea91c50b40aa8c0f7df9f05",
    "pool_state.json": "09d8a78bb8e2b1b72492590a6064f39dc040f06bd9d95132b755491921180a39",
    "positions/races/r01.json": "2ff6369c1bb49ab66a40e3326aea0ef499c6e4884ddba8315dd13441f22f75f1",
    "positions/races/r02.json": "09c72f57beae8a60fc5012ea1c925afad5dc8a7c5934bbfff880cb0ccfc74cff",
    "positions/races/r03.json": "162c5782ddb4bb73c5424b26edc4ea6fd9e0cb435217f5d78e04ad90947c89f8",
    "positions/races/r04.json": "fe53163ba8cb5d64014ab377e09d920c381a546ef65000513fc7411c07b09cd3",
    "positions/races/r05.json": "af26329a2b4ddcc00047349bfe506e5005131a1744e6a56df5867df10f1aeae7",
    "positions/races/r06.json": "5d128dacd9bb85da839d8f934cf70a78620562a09104953508917517ec650788",
    "positions/races/r07.json": "27c12584190a3a8b0d6c15f33ba3448b9614f9aa20e436c76a9a8f5c90bc1545",
    "positions/tempo/t01.json": "a9fba8b012bc8f809e55fbfbd5a211a7bb93606f0744e9b3e8e200f1a4ba0968",
    "positions/tempo/t02.json": "19f4feb202c12c36809480306974e1d216363283ba4485d595d816d39d120df5",
    "positions/tempo/t03.json": "863b1026539c70a7fb8e695a7141939b07df84e3eb0f8f41861b84b6d391cbba",
    "positions/tempo/t04.json": "352342431ffdbe37caff8422c8844b77871eaaf0bc1d1f4dfe04c27b30ae32c0",
    "positions/tempo/t05.json": "afd9e62c0ffec1fa5e6dc4493c082edd5f0c4be739cc38b815b3d1144b28f02c",
    "positions/tempo/t06.json": "1aa891d03120b9fc538111229821d0d43c9d5e7b0df3a9e09429f65089390647",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "passed_pawn_races.json": "8b790d94325d8012ab149c44e8dc8b4c966f769c4383388d5657a09ad22bbd08",
    "opposition_grid.json": "0de33859ed2937801c53549c0cd9e08fccbbeec3cc1f9627d7b3502500bc09d7",
    "tempo_loss_windows.json": "2563d2a774a9418bdc253b407cac0e6319eceef115d5b5a4727f6bd38822ed42",
    "underpromotion_caps.json": "e80a8f071795dd0878c9eb28f5d92ab58fe18343812d8ce6a01c67db57056df1",
    "summary.json": "0e9caeb63f99a18e536acd7c8cfb07f9f652fbffb0dd6dd514d8ee0fe06bb12a",
}

EXPECTED_FIELD_HASHES = {
    "opposition_grid.cells": "1d4f0b9a9229ff0ff66a1ba72d7c8c3b4c0863a0a10c00338ff7252beee80c44",
    "passed_pawn_races.races": "57758dcdddf7f1cba59d9b628dfafd6c9b61ba555a82dd553b258f6d7211669f",
    "summary": "0e9caeb63f99a18e536acd7c8cfb07f9f652fbffb0dd6dd514d8ee0fe06bb12a",
    "tempo_loss_windows.windows": "40344c134bfdb22ca5b577bb894fbd4389a47f52499f89d46207d67347590473",
    "underpromotion_caps.evaluations": "eab2736fb54bfb1a7569d373053d68ec308382431eb8f948646908b8fcfefd20",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha(obj) -> str:
    payload = (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
    return _sha256_bytes(payload)


@pytest.fixture(scope="module")
def loaded_outputs():
    result = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = PET_AUDIT_DIR / name
        assert p.is_file(), f"missing audit file {name}"
        text = p.read_text(encoding="utf-8")
        result[name] = {"text": text, "obj": json.loads(text), "bytes": text.encode("utf-8")}
    return result


class TestInputIntegrity:
    """Input fixtures must remain unchanged."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hashes_match(self, rel):
        p = PET_DATA_DIR / rel
        assert p.is_file(), f"missing input fixture: {rel}"
        assert _sha256_bytes(p.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestOutputStructure:
    """Output files must be deterministic and canonical."""

    def test_audit_dir_contains_only_expected_files(self):
        actual = sorted(p.name for p in PET_AUDIT_DIR.iterdir() if p.is_file())
        assert actual == sorted(REQUIRED_OUTPUT_FILES)

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_pretty_sorted_and_newline(self, loaded_outputs, name):
        obj = loaded_outputs[name]["obj"]
        expected = (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        assert loaded_outputs[name]["bytes"] == expected

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_top_level_canonical_hash(self, loaded_outputs, name):
        assert _canonical_sha(loaded_outputs[name]["obj"]) == EXPECTED_OUTPUT_CANONICAL_HASHES[name]


class TestSemanticBehavior:
    """Cross-checks implied by the published specification text."""

    def test_frozen_positions_suppress_race_distance(self, loaded_outputs):
        races = {r["position_id"]: r for r in loaded_outputs["passed_pawn_races.json"]["obj"]["races"]}
        assert races["race-r05"]["outcome"] == "frozen"
        assert races["race-r05"]["plies_to_decisive"] == 0

    def test_tiebreak_branch_used_for_race_r07(self, loaded_outputs):
        races = {r["position_id"]: r for r in loaded_outputs["passed_pawn_races.json"]["obj"]["races"]}
        assert races["race-r07"]["outcome"] == "black_wins"
        assert races["race-r07"]["reason_codes"] == ["opposition_tiebreak"]

    def test_tempo_window_frozen_entry(self, loaded_outputs):
        wins = {w["position_id"]: w for w in loaded_outputs["tempo_loss_windows.json"]["obj"]["windows"]}
        assert wins["tempo-t04"]["class"] == "frozen"
        assert wins["tempo-t04"]["window_index"] == -1

    def test_summary_frozen_list_sorted(self, loaded_outputs):
        ids = loaded_outputs["summary.json"]["obj"]["frozen_position_ids"]
        assert ids == ["race-r05", "tempo-t04"]

    def test_underpromotion_beyond_policy_present(self, loaded_outputs):
        ev = {e["position_id"]: e for e in loaded_outputs["underpromotion_caps.json"]["obj"]["evaluations"]}
        assert ev["race-r02"]["cap_band"] == "beyond_policy"
        assert ev["race-r03"]["cap_band"] == "beyond_policy"


class TestImplementationLanguage:
    """Implementation must provide Go source files under /app/src."""

    def test_go_source_contains_package_main(self):
        go_files = sorted(PET_SRC_DIR.rglob("*.go"))
        assert go_files, "at least one Go source file must exist under /app/src"
        has_main = any("package main" in p.read_text(encoding="utf-8", errors="ignore") for p in go_files)
        assert has_main, "Go source under /app/src must include package main"

    def test_no_python_sources_under_src(self):
        py_files = list(PET_SRC_DIR.rglob("*.py"))
        assert not py_files, "implementation source under /app/src must be Go-only"


class TestCompiledBinary:
    """Implementation must compile to /app/bin/pawnaudit and execute to produce reports."""

    def test_pawnaudit_binary_exists(self):
        assert PAWNAUDIT_BIN.is_file(), f"{PAWNAUDIT_BIN} must exist as a regular file"
        assert os.access(PAWNAUDIT_BIN, os.X_OK), f"{PAWNAUDIT_BIN} must be executable"

    def test_pawnaudit_binary_is_native_executable(self):
        head = PAWNAUDIT_BIN.read_bytes()[:4]
        assert head != b"#!/b" and head != b"#!/u" and head != b"#!/p", (
            f"{PAWNAUDIT_BIN} must not be a script (header={head!r})"
        )
        assert head == b"\x7fELF", f"{PAWNAUDIT_BIN} must be an ELF executable (header={head!r})"

    def test_pawnaudit_binary_built_from_go(self):
        go_bin = shutil.which("go")
        if go_bin:
            result = subprocess.run(
                [go_bin, "version", "-m", str(PAWNAUDIT_BIN)],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
            assert result.returncode == 0 and "go" in first_line.lower(), (
                f"`go version -m` did not identify a Go binary "
                f"(rc={result.returncode}, first_line={first_line!r}, stderr={result.stderr[:300]!r})"
            )
        else:
            data = PAWNAUDIT_BIN.read_bytes()
            assert b"go.buildinfo" in data or b"Go build" in data or b"runtime.go" in data, (
                f"{PAWNAUDIT_BIN} does not contain Go build metadata"
            )

    def test_pawnaudit_binary_regenerates_canonical_reports(self, tmp_path):
        run_dir = tmp_path / "audit_run"
        run_dir.mkdir()
        env = os.environ.copy()
        env["PET_DATA_DIR"] = str(PET_DATA_DIR)
        env["PET_AUDIT_DIR"] = str(run_dir)
        result = subprocess.run(
            [str(PAWNAUDIT_BIN)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert result.returncode == 0, (
            f"{PAWNAUDIT_BIN} exited with rc={result.returncode}; "
            f"stdout={result.stdout[:500]!r} stderr={result.stderr[:500]!r}"
        )
        for name in REQUIRED_OUTPUT_FILES:
            p = run_dir / name
            assert p.is_file(), f"binary did not produce {name}"
            obj = json.loads(p.read_text(encoding="utf-8"))
            assert _canonical_sha(obj) == EXPECTED_OUTPUT_CANONICAL_HASHES[name], (
                f"output {name} produced by the binary does not match the canonical hash"
            )


class TestFieldHashes:
    """Field-level canonical hashes provide targeted mismatch diagnostics."""

    def test_races_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["passed_pawn_races.json"]["obj"]["races"])
        assert actual == EXPECTED_FIELD_HASHES["passed_pawn_races.races"]

    def test_cells_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["opposition_grid.json"]["obj"]["cells"])
        assert actual == EXPECTED_FIELD_HASHES["opposition_grid.cells"]

    def test_windows_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["tempo_loss_windows.json"]["obj"]["windows"])
        assert actual == EXPECTED_FIELD_HASHES["tempo_loss_windows.windows"]

    def test_evaluations_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["underpromotion_caps.json"]["obj"]["evaluations"])
        assert actual == EXPECTED_FIELD_HASHES["underpromotion_caps.evaluations"]

    def test_summary_field_hash(self, loaded_outputs):
        actual = _canonical_sha(loaded_outputs["summary.json"]["obj"])
        assert actual == EXPECTED_FIELD_HASHES["summary"]
