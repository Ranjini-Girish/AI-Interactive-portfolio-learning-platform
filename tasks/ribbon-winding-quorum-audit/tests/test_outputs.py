"""Verifier suite for ribbon-winding-quorum-audit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RWQ_DATA_DIR", "/app/rwq_lab"))
AUDIT_DIR = Path(os.environ.get("RWQ_AUDIT_DIR", "/app/audit"))
BINARY = Path("/app/bin/rwqaudit")

OUTPUT_FILES = ("summary.json", "segment_verdicts.json")

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "2fa2a52e1e795938cf33086e42adfd8301d1b8f7c9a8001771bfec35c3eb5b2d",
    "anchors/hi.json": "be455a543442fccf4af3f719fc3f4af8a4b56fe46662512e9237d812f0f042f2",
    "anchors/lo.json": "ef7ebce024e380225734481442c7b52020f882a6258bca71bfb88deb24b96c84",
    "ancillary/meta.json": "31536bdc3e22623ebfebd88d2d5819b28d67b42e9259180c8b425297a46d930d",
    "ancillary/notes.json": "a63a38f22fb640c3ab6985d2fc18b28d55f710edabe5d06e9051e3eab1a665f4",
    "ancillary/stub.json": "a7592ac3296e3798984c6c89a0667d501838795e49c4119e4172182550eba4c2",
    "domain_layout.json": "ef03d2d9a3d71293402c301789aee0f209d9b6fad2b95ad4991d05551387ba7e",
    "incident_log.json": "461ecafd7dbd3c41511ba564caf79fedcf2dee9512dffd8a8f708bdc7c2e2591",
    "index.json": "0c6d077c40024644bfd18113c9468791cfbdba19109fce3e93b3213c1b10602b",
    "policy.json": "1f525c42f9739786c06424e9f67f5146c0431de2856856a489a4adc022dd4ccd",
    "pool_state.json": "26fc89d9a86610f74ba79422c72e4a820fd642cd6d7c210a2fad22f68293fe98",
    "segments/s00.json": "a0ee818ba87b4abd83bbde54bfb8baf8b08b7b8a9cf187b0411981e920572d0e",
    "segments/s01.json": "81f14d6ac6dc90ae455e2750acb8b611984aea45f33023f20619d3fdaf8e52d0",
    "segments/s02.json": "6c02d5692549d3b26e9fd8ebd47bd8143e50e1aeda8a26584b40ee687be4b3a6",
    "segments/s03.json": "d6d7b1274e57385ab8e90bcc7600c1930b3551f8698d76ce742489073409f5ce",
    "segments/s04.json": "594caebf0c84f89cdabdb2e78f011063ad8cbe76cb954d5e10a3971ef0872a0e",
    "segments/s05.json": "e1eb4a96cb23cf0da63389eb4565ee5fe1be5c999d1e07dbbdf2e1165552ec42",
    "segments/s06.json": "e2ba5ba4b00b43c24effd58c5b29333fddf4c186e46d17837cd2d74e16b8ced4",
    "segments/s07.json": "7f69b5ce324ff9684d203bd83d98f4d1c7d631584f803f7996cbdf90594e0f60",
    "segments/s08.json": "ef1d07742465b61f358ceca8743d6445352e70bb1f10b754494a3fc17d85564c",
    "segments/s09.json": "a33016143993f0f45ce391537f7b97885ab8877b2339b56c62da45c4828e7ddb",
    "segments/s10.json": "1b9ed7387ccba5ad7cee5ae8fe786307aa309a412fd66700ac1a9f5aefd72e61",
    "segments/s11.json": "966eb2061e066e0fdabaf2b413a3bc555e8b93f89553e455ee6632da8fe3c33e",
    "segments/s12.json": "ac4efeb1164b7bf1a12634b1929ba68f7ee477f496cae0985e1fe4d7ddff408f",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "summary.json": "e4336f4b57b5e50f8a60686aae37a452ed65005de4776a5e87ad5cd24b87ef3d",
    "segment_verdicts.json": "2164f2aaf634d766fa80691c1aec19e5cc7118c9af46dd561981a8457c0659d0",
}

EXPECTED_FIELD_HASHES = {
    "segment_verdicts.json.diagnostics": "dc1628db33e4c5c3f45bfeb99a37c177fb86055326b4bed3f2ea424b754b7961",
    "segment_verdicts.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "segment_verdicts.json.segments": "1ff8ba14b04bbfb5ed56a923df83703099c7d1cbac14eb8fbdd063dae276fad6",
    "summary.json.diagnostics_total": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.json.passed_count": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.json.quorum_starved_count": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.json.schema_version": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.segments_total": "3fdba35f04dc8c462986c992bcf875546257113072a909c162f7e470e581e278",
    "summary.json.tier_trimmed_count": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.json.winding_ok": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
    "summary.json.winding_violation_count": "5feceb66ffc86f38d952786c6d696c79c2dbc239dd4e91b46729d73a27fb57e9",
}

EXPECTED_VERDICT_BY_SEGMENT = {
    "s00": "quorum_starved",
    "s01": "quorum_starved",
    "s02": "passed",
    "s03": "passed",
    "s04": "passed",
    "s05": "passed",
    "s06": "passed",
    "s07": "passed",
    "s08": "tier_trimmed",
    "s09": "tier_trimmed",
    "s10": "tier_trimmed",
    "s11": "tier_trimmed",
    "s12": "quorum_starved",
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


@pytest.fixture(scope="session")
def segment_rows(outputs: dict[str, object]) -> list[dict[str, object]]:
    """Return the ordered segment verdict rows from the bundled audit."""
    seg = outputs["segment_verdicts.json"]
    assert isinstance(seg, dict)
    rows = seg["segments"]
    assert isinstance(rows, list)
    return [r for r in rows if isinstance(r, dict)]


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

    def test_each_output_file_has_single_trailing_newline(self) -> None:
        """On-disk outputs end with exactly one Unix newline after the JSON payload."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_bytes()
            assert raw.endswith(b"\n"), name
            assert not raw.endswith(b"\n\n"), name
            body = raw[:-1]
            assert b"\n" not in body, name

    def test_on_disk_bytes_match_canonical_minified_json(self, outputs: dict[str, object]) -> None:
        """Each audit file on disk is minified canonical JSON plus one trailing newline."""
        for name in OUTPUT_FILES:
            raw = (AUDIT_DIR / name).read_bytes()
            expected = _canonical(outputs[name]).encode("utf-8") + b"\n"
            assert raw == expected, f"on-disk presentation mismatch for {name}"
            assert b"  " not in raw, f"unexpected indentation in {name}"


class TestCompoundRules:
    """Interacting saturation, relax composition, and tier-floor trimming."""

    def test_anchor_saturation_on_double_hit_segment(self, segment_rows: list[dict[str, object]]) -> None:
        """Segments covered by both anchors use diminishing boost, not linear weight times hits."""
        by_id = {str(r["segment_id"]): r for r in segment_rows}
        assert int(by_id["s00"]["effective_witness"]) == 7

    def test_alpha_effective_quorum_uses_summed_relax(self, segment_rows: list[dict[str, object]]) -> None:
        """Alpha tiers combine overlapping incident relax values before the policy cap."""
        alpha_rows = [r for r in segment_rows if str(r["tier"]) == "alpha"]
        assert alpha_rows, "expected alpha segments in bundled dataset"
        assert all(int(r["effective_quorum"]) == 8 for r in alpha_rows)

    def test_tier_trimmed_verdict_present(self, segment_rows: list[dict[str, object]]) -> None:
        """The reference ribbon includes tier_trimmed segments after floor-aware trimming."""
        verdicts = {str(r["verdict"]) for r in segment_rows}
        assert "tier_trimmed" in verdicts


class TestVerdictCoverage:
    """Bundled verdict strings exercised by the reference dataset."""

    def test_each_segment_matches_expected_verdict(self, segment_rows: list[dict[str, object]]) -> None:
        """Every ring segment carries the verdict implied by the bundled ribbon."""
        by_id = {str(r["segment_id"]): str(r["verdict"]) for r in segment_rows}
        for sid, v in EXPECTED_VERDICT_BY_SEGMENT.items():
            assert by_id[sid] == v, f"unexpected verdict for {sid}"

    def test_summary_counts_match_rows(self, outputs: dict[str, object], segment_rows: list[dict[str, object]]) -> None:
        """Summary counters line up with the per-segment verdict table."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        verdicts = [str(r["verdict"]) for r in segment_rows]
        assert int(summary["passed_count"]) == verdicts.count("passed")
        assert int(summary["quorum_starved_count"]) == verdicts.count("quorum_starved")
        assert int(summary["tier_trimmed_count"]) == verdicts.count("tier_trimmed")
        assert int(summary["winding_violation_count"]) == verdicts.count("winding_violation")
        assert int(summary["segments_total"]) == len(segment_rows)


class TestImplementationArtifacts:
    """Go layout, binary presence, and RWQ_* directory routing."""

    def test_go_sources_under_app_src_use_package_main(self) -> None:
        """At least one Go file under /app/src declares package main."""
        src_dir = Path("/app/src")
        go_files = list(src_dir.glob("*.go"))
        assert len(go_files) >= 1, "expected at least one Go file under /app/src/"
        for gf in go_files:
            text = gf.read_text(encoding="utf-8")
            assert "package main" in text, f"{gf} must declare package main"

    def test_rwqaudit_binary_exists_and_executable(self) -> None:
        """The compiled helper must exist at /app/bin/rwqaudit and be executable."""
        assert BINARY.is_file(), "missing /app/bin/rwqaudit"
        assert os.access(BINARY, os.X_OK), "/app/bin/rwqaudit is not executable"

    def test_binary_writes_outputs_under_rwq_audit_dir(self, tmp_path: Path) -> None:
        """With RWQ_AUDIT_DIR pointing at a scratch directory, rerunning must recreate
        the same two canonical files there."""
        out_dir = tmp_path / "alt_audit"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("RWQ_AUDIT_DIR", "RWQ_DATA_DIR")}
        env["RWQ_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        for name, expected_hash in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            written = out_dir / name
            assert written.is_file(), f"missing {name} under custom RWQ_AUDIT_DIR"
            obj = _load_json(written)
            digest = _sha256_bytes(_canonical(obj).encode("utf-8"))
            assert digest == expected_hash, f"hash mismatch for {name} under RWQ_AUDIT_DIR"

    def test_binary_reads_inputs_from_rwq_data_dir(self, tmp_path: Path) -> None:
        """A full copy of the bundle at RWQ_DATA_DIR must yield byte-identical outputs."""
        lab_copy = tmp_path / "lab_mirror"
        shutil.copytree(DATA_DIR, lab_copy)
        out_dir = tmp_path / "out_mirror"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("RWQ_AUDIT_DIR", "RWQ_DATA_DIR")}
        env["RWQ_DATA_DIR"] = str(lab_copy)
        env["RWQ_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        for name, expected_hash in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            written = out_dir / name
            assert written.is_file()
            obj = _load_json(written)
            digest = _sha256_bytes(_canonical(obj).encode("utf-8"))
            assert digest == expected_hash, f"hash mismatch for {name} under RWQ_DATA_DIR copy"


class TestWindingSynthetic:
    """Synthetic ribbon where flux residues break winding closure."""

    def test_winding_break_marks_every_segment(self, tmp_path: Path) -> None:
        """When summed flux is non-zero modulo the policy modulus, every segment verdict
        must read winding_violation and diagnostics must list WINDING for each id."""
        lab = tmp_path / "wlab"
        shutil.copytree(DATA_DIR, lab)
        seg0 = lab / "segments" / "s00.json"
        data = json.loads(seg0.read_text(encoding="utf-8"))
        data["flux"] = int(data["flux"]) + 1
        seg0.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        out_dir = tmp_path / "wout"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("RWQ_AUDIT_DIR", "RWQ_DATA_DIR")}
        env["RWQ_DATA_DIR"] = str(lab)
        env["RWQ_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        summary = _load_json(out_dir / "summary.json")
        assert isinstance(summary, dict)
        assert summary["winding_ok"] is False
        seg = _load_json(out_dir / "segment_verdicts.json")
        assert isinstance(seg, dict)
        for row in seg["segments"]:
            assert isinstance(row, dict)
            assert str(row["verdict"]) == "winding_violation"
        codes = {str(d["code"]) for d in seg["diagnostics"]}
        assert codes == {"WINDING"}
        assert len(seg["diagnostics"]) == 13
        assert int(summary["winding_violation_count"]) == 13
