"""Verifier suite for the series-parallel capacitor network audit task."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SPN_DATA_DIR", "/app/spn_lab"))
AUDIT_DIR = Path(os.environ.get("SPN_AUDIT_DIR", "/app/spn_audit"))
BINARY = Path("/app/spn_tool/spnaudit")

OUTPUT_FILES = (
    "rack_equivalents.json",
    "incident_applied.json",
    "cap_working.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0138717044ed4d4d4d0c108c0204809b04e00cf9b2ed7ee517d7ee2aee97d111",
    "anchors/site.json": "d46046d24f943e48826e78c42f71d2fb1b6954bc1c91411fdfc502a4162af093",
    "ancillary/meta.json": "39bc435005ebaa2bc4fb8608049234cb70a53e2d0fc7594744906ebeb293ea92",
    "caps/k01.json": "ec5295fdaf7630731211a719b7d7f9bc83d06737d85cf02b8cf6533a31a050cd",
    "caps/k02.json": "eea108dd92022c5510faffa109d56920f0bbf91081efb3a9d5ff2cb169323ed1",
    "caps/k03.json": "77c4d712bddda2ed1afb03c6ae0a13a0baa82e82ce574e9de0d7ad5d582f5def",
    "caps/k04.json": "025cbeab181e8861f52444eb6b13ee37a83fea815e15a510e137c909172857ea",
    "caps/k05.json": "2ca977e29e29d4db03c504ac6fbdcce2daf98f547aa1ce373dc38f16c8c183c4",
    "caps/k06.json": "e508554f27d4a8a47914586b1d2384826221d5d19cfd09e8404e4334e20d7685",
    "caps/k07.json": "8b65f1195d3bb70ff28ff93d1b9798e410ba5ef4de8223b2848903a0a225b0c2",
    "caps/k08.json": "f0d805512135e23a136fcb1bfb74f5a9fdd3ab899e0f078ac78ffbf9101ff905",
    "caps/k09.json": "95037e67842b68440ebfec842b53d2574d15ef09bfc2587fe4967bb61efacf6f",
    "caps/k10.json": "0d3907ee526d3accca7b401f13403c3948929bd4099d9ec532f5b99573906d04",
    "caps/k11.json": "617a5449de80fd12d90464a54a7ce631ba2f31c7cdfd57137c89b6ea6c84b9d7",
    "caps/k12.json": "becdd472612b9083765dc6b240726d8627df49533c341d5de52af1042dccec34",
    "caps/k13.json": "dbe201e9df2573eca165cf04367b0a3e2cca451226b3fdd7554f58d95fb81f69",
    "caps/k14.json": "1a180fff94677e146bd4f3964acd948b679ef488edd152641b67e06beede60d5",
    "incident_log.json": "c7ce56f882627b81aaf631876518e445925dcefd47c6c819f6b4afb61f31040b",
    "policy.json": "14cc7471b4943d7dd4317fb6eac51c265630460dc0507c49d44e0af33958d60f",
    "pool_state.json": "c43aca50bbb7b6a7c040450d7e0d4908b6698daf9330fb19369afd250ea86b56",
    "racks/a01.json": "7a7a10b62c691d73a31e388bf63b93e57e98c3443875e301b948a092305fc537",
    "racks/a02.json": "fb1f3061d3d4f973688c73519f3eaa60d5d290cee5b4edec73191ef11fa4da19",
    "racks/a03.json": "87427343e9bbd529b42dd3c96a5ffc7f3b4bab1b5f80d51557ba4f1198287fab",
    "racks/a04.json": "5bfa6a909f85e29f68ae0da618f346b77c9c02c41ff44fc286d61ec3c5f7da01",
    "racks/a05.json": "439beefad29996eefa38e8d307fd288bb3c895c5a2906480f148d4bfe605c26f",
    "racks/a06.json": "a4acdd5f4c643f268a74e3be657a0857e4857818460fc67808377dd00a6db818",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "cap_working.json": "2ddb5767bd68b36ecf4b48aa57ab58d230d2c5b1b0ff3b126b31a2749ca1b9fb",
    "incident_applied.json": "64baa91c04f00a2f36088a4f6b1f46f913ba9213b10740fee05a1ffb416875d1",
    "rack_equivalents.json": "5233ff4cd46f0c53340e67e1dfabe3e07c602cd6048daddc2bd37058d7f574d8",
    "summary.json": "2280818dc36a732c27971126b431c44035ccde9b7aed8d4cf855229bf7234584",
}


EXPECTED_FIELD_HASHES = {
    "incident_applied.applied": "4853fa5ad4540973d8921908674cf7e0ec0fd6084055f82cb5e2f1209ff8bcf3",
    "rack_equivalents.racks": "c69edcfd96a4cbefacff5e8db0474e2296608a03215c124558c0e829468b06d2",
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

    def test_nested_field_hashes(self, outputs: dict[str, object]) -> None:
        """Nested collections remain stable under canonical serialisation."""
        re = outputs["rack_equivalents.json"]
        assert isinstance(re, dict)
        racks = _canonical(re["racks"])
        assert (
            _sha256_bytes(racks.encode("utf-8")) == EXPECTED_FIELD_HASHES["rack_equivalents.racks"]
        )
        ia = outputs["incident_applied.json"]
        assert isinstance(ia, dict)
        applied = _canonical(ia["applied"])
        assert (
            _sha256_bytes(applied.encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_applied.applied"]
        )


class TestRackStates:
    """Semantic checks on rack disposition strings."""

    def test_quarantine_rack_emits_host_compromised(self, outputs: dict[str, object]) -> None:
        """The compromised-host rack must quarantine with null headroom and null ESR."""
        racks = outputs["rack_equivalents.json"]["racks"]
        hit = next(r for r in racks if r["rack_id"] == "a03")
        assert hit["state"] == "quarantine"
        assert hit["reasons"] == ["host_compromised"]
        assert hit["headroom_uj"] is None
        assert hit["equiv_esr_mohm"] is None

    def test_ok_rack_has_empty_reasons(self, outputs: dict[str, object]) -> None:
        """The clean beta rack with no incidents must report ok with an empty reasons list."""
        racks = outputs["rack_equivalents.json"]["racks"]
        hit = next(r for r in racks if r["rack_id"] == "a06")
        assert hit["state"] == "ok"
        assert hit["reasons"] == []

    def test_negative_headroom_rack(self, outputs: dict[str, object]) -> None:
        """The high-energy rack must degrade solely on negative headroom."""
        racks = outputs["rack_equivalents.json"]["racks"]
        hit = next(r for r in racks if r["rack_id"] == "a04")
        assert hit["state"] == "degraded"
        assert hit["reasons"] == ["negative_headroom"]

    def test_frozen_rack_still_flags_incident_touch(self, outputs: dict[str, object]) -> None:
        """Frozen evaluation ignores scaling for equivalence but still records incident touch."""
        racks = outputs["rack_equivalents.json"]["racks"]
        hit = next(r for r in racks if r["rack_id"] == "a02")
        assert hit["state"] == "degraded"
        assert "incident_touch" in hit["reasons"]
        assert "esr_offset" not in hit["reasons"]


class TestSummaryRollups:
    """Cross-check summary counters against per-rack rows."""

    def test_summary_state_counts_match_rows(self, outputs: dict[str, object]) -> None:
        """Summary.state histogram must equal rack disposition counts."""
        racks = outputs["rack_equivalents.json"]["racks"]
        sm = outputs["summary.json"]
        c = Counter(str(r["state"]) for r in racks)
        assert sm["states"]["ok"] == c["ok"]
        assert sm["states"]["degraded"] == c["degraded"]
        assert sm["states"]["quarantine"] == c["quarantine"]

    def test_applied_incident_count(self, outputs: dict[str, object]) -> None:
        """Four accepted windowed events apply on the bundled current_day."""
        applied = outputs["incident_applied.json"]["applied"]
        assert len(applied) == 4


@pytest.mark.skipif(
    not BINARY.is_file(),
    reason="spnaudit binary not present (outside bench image or before build)",
)
class TestImplementationArtifacts:
    """Binary presence and deterministic re-execution."""

    def test_go_sources_under_spn_tool_use_package_main(self) -> None:
        """At least one Go file under /app/spn_tool declares package main."""
        src_dir = Path("/app/spn_tool")
        go_files = list(src_dir.glob("*.go"))
        assert len(go_files) >= 1, "expected at least one .go file under /app/spn_tool/"
        for gf in go_files:
            text = gf.read_text(encoding="utf-8")
            assert "package main" in text, f"{gf} must declare package main"

    def test_spnaudit_binary_exists_and_executable(self) -> None:
        """The compiled auditor must exist at /app/spn_tool/spnaudit and be executable."""
        assert BINARY.is_file(), "missing /app/spn_tool/spnaudit"
        assert os.access(BINARY, os.X_OK), "/app/spn_tool/spnaudit is not executable"

    def test_binary_writes_outputs_under_custom_audit_dir(self, tmp_path: Path) -> None:
        """Rerunning with a fresh SPN_AUDIT_DIR must recreate the same four canonical files."""
        out_dir = tmp_path / "alt_audit"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("SPN_AUDIT_DIR", "SPN_DATA_DIR")}
        env["SPN_AUDIT_DIR"] = str(out_dir)
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
            assert written.is_file(), f"missing {name} under custom SPN_AUDIT_DIR"
            obj = _load_json(written)
            digest = _sha256_bytes(_canonical(obj).encode("utf-8"))
            assert digest == expected_hash, f"hash mismatch for {name} under SPN_AUDIT_DIR"

    def test_binary_reads_inputs_from_spn_data_dir_copy(self, tmp_path: Path) -> None:
        """A full copy of the lab bundle must yield byte-identical canonical outputs."""
        lab_copy = tmp_path / "lab_mirror"
        shutil.copytree(DATA_DIR, lab_copy)
        out_dir = tmp_path / "out_mirror"
        out_dir.mkdir()
        env = {k: v for k, v in os.environ.items() if k not in ("SPN_AUDIT_DIR", "SPN_DATA_DIR")}
        env["SPN_DATA_DIR"] = str(lab_copy)
        env["SPN_AUDIT_DIR"] = str(out_dir)
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
            assert digest == expected_hash, f"hash mismatch for {name} under SPN_DATA_DIR copy"
