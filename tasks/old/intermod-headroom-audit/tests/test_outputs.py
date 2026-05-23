"""Verifier suite for intermod-headroom-audit."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

APP_ROOT = Path("/app")
SOURCE_SUFFIXES = frozenset(
    {".c", ".cc", ".cpp", ".go", ".java", ".js", ".py", ".rs", ".sh", ".ts"}
)
_HELPER_SKIP_PARTS = frozenset({"imhr_lab", "audit", "imha-src", "bin"})

DATA_DIR = Path(os.environ.get("IMHA_DATA_DIR", "/app/imhr_lab"))
AUDIT_DIR = Path(os.environ.get("IMHA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("registry.json", "intermod_hits.json", "summary.json")

BINARY_PATH = Path("/app/bin/imha")


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "40a975c4374de52f241b8585791208b686e2f7cb593611c1b6bf7555d6e1b725",
    "anchors/window.json": "3f8b0758e35663f1b584658eb9ce32698bbe0d10f8febb23b910cf66c877e5a9",
    "ancillary/thresholds.json": "97f4841992ea0d4a819c5f83a64ef76607b721183efab16c418d35d3c05a86d6",
    "incident_log.json": "a5fe9650bb1574de5917957868c3adc3b7cd62f36bd049609b351f9a80850b24",
    "policy.json": "5101340248cf317b65e9c6127104759fe40a43177a2c8c654ae769b5f3478db4",
    "pool_state.json": "40ca75a8c4d2e06282b35e7db5812311d64b7d3af72799b0c1f370c346ed7b19",
    "sites/s01.json": "869fecf665f001371f1688d088474f854420c7cc05f14af5e7349687b7d340b7",
    "sites/s02.json": "46f7369f2a90f479ef0b4e87028e257b7bf41ff3d8b5b0cedfd2a30f775c2f90",
    "sites/s03.json": "57197e4d08b752f585aad65c2164c13535de1064e80a2e7e919a31c8cda7a18d",
    "sites/s04.json": "fce5dfdc08ff00694f1b1825a54e4ff33e93211db0b7e163eeb6ed630d0ff4f4",
    "sites/s05.json": "20d91ec575643c1b81b6a7907fee16002e2fe408b29936127ad1664831b73967",
    "sites/s06.json": "70dcd895222e6391f96dea0d97d5af335c2f62da9df7fec6fb50b9c064565499",
    "sites/s07.json": "2f8b7918d7d84f6c0c60ab9687d4840e7218584416e8689efd9924b20eeb2779",
    "sites/s08.json": "ee84ab9084577ae680bb7eb9e990883785b3f4f46b23e5a1733d732eded3f8f4",
    "sites/s09.json": "79b65e8e79e2828ffdda0a11a93dcfcd0262368d2b4b9688cdd4c51aac591283",
    "sites/s10.json": "a3c1717bb62f155178f24dc7b96def897818d1d58afb788b761db75b6bf39312",
    "sites/s11.json": "bcceebce5f688515b9c6c4557a3135aeabf594a184c416fc893863ed34b8ce0a",
    "sites/s12.json": "e05db78cf7b41f25a2aa228660c0548e780ff4f18ccac0e11db317f608d67bb8",
    "sites/s13.json": "a485f51632a2c7c4b1fed3931ff9505197af7ae5b6ee8093dc1a6f66daf66913",
    "sites/s14.json": "a891292e8dfa5f1b36531ba57ee78dd9ff5416fade555f13148af6d459f8c54c",
    "sites/s15.json": "ba8a34632f1a5aead6d6d796d33c7839ca62af059504e88633a0fc01649f22bf",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "intermod_hits.json": "156300a528191f64c158dfb4e6498e2423e33a2164e939823b719cbdbfe750b7",
    "registry.json": "9df48f86b0451a364b39b0848b18c69b6def9a56dd8939d6e189b25b3aba19dd",
    "summary.json": "48e598a85bca253a9958f7d89f734b69b00182f47a3a2668f0c1728080539eee",
}


EXPECTED_FIELD_HASHES = {
    "intermod_hits.hits": "1c04ff330dcac1b71cdc97c02bd68aa9a5d74a054b501e6791a13d093cc7fe70",
    "registry.admission_order": "94684e3d6bcf2c2c5920c2b4b5f308aad8152c9aad9c836e2724bb63a62c3c1a",
    "registry.registry": "5e32fa36b51c1a9f55e94241cd4631f48a84cfd24ce86ca392be333b80281af8",
    "registry.tiers_used": "ef46b0fa9e3818cfee2d9c8590ba398f5d0b127dc1d682a8196d6874e1fae41b",
    "summary.adjusted_sites": "d74cf0cc3cd0f5e91a44e9b6ef887aa0b5fe18055916767562977724d38f1357",
    "summary.bands": "483c392c2d1b5b7230c2ce9f8552e57ab7732a570c575d8883d1b5ac08cec592",
    "summary.frozen_skipped_sites": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    """SPEC.md canonical JSON: UTF-8, two-space indent, ASCII, sorted keys, trailing newline."""
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _compiled_helpers_under_app() -> list[Path]:
    """ELF executables under /app/ outside the read-only data and audit trees."""
    helpers: list[Path] = []
    for path in APP_ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(APP_ROOT).parts
        if any(part in _HELPER_SKIP_PARTS for part in rel_parts):
            continue
        try:
            if path.read_bytes()[:4] != b"\x7fELF":
                continue
        except OSError:
            continue
        if os.access(path, os.X_OK):
            helpers.append(path)
    return helpers


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

    def test_output_on_disk_matches_spec_json_encoding(
        self, outputs: dict[str, object]
    ) -> None:
        """Each audit file's bytes must match SPEC.md canonical JSON formatting."""
        for name in OUTPUT_FILES:
            path = AUDIT_DIR / name
            raw = path.read_bytes()
            expected = _spec_json_bytes(outputs[name])
            assert raw == expected, f"encoding mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        reg = outputs["registry.json"]
        assert (
            _sha256_bytes(_canonical(reg["admission_order"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["registry.admission_order"]
        )
        assert (
            _sha256_bytes(_canonical(reg["registry"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["registry.registry"]
        )
        assert (
            _sha256_bytes(_canonical(reg["tiers_used"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["registry.tiers_used"]
        )
        hits = outputs["intermod_hits.json"]["hits"]
        assert (
            _sha256_bytes(_canonical(hits).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["intermod_hits.hits"]
        )
        summary = outputs["summary.json"]
        for key in ("adjusted_sites", "bands", "frozen_skipped_sites"):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(summary[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestRegistrySemantics:
    """Behavioural checks grounded in the bundled dataset."""

    def test_compromised_site_emits_no_registry_rows(self, outputs: dict[str, object]) -> None:
        """Accepted compromise must remove the affected site from the merged registry."""
        rows = outputs["registry.json"]["registry"]
        sites = {str(r["site_id"]) for r in rows}
        assert "site-comp-01" not in sites

    def test_silver_tier_hits_emit_cap(self, outputs: dict[str, object]) -> None:
        """Silver tier admissions must stop at the configured cap."""
        assert outputs["registry.json"]["tiers_used"]["silver"] == 7
        rows = outputs["registry.json"]["registry"]
        assert sum(1 for r in rows if r["tier"] == "silver") == 7

    def test_bronze_edge_intermod_lists_expected_hit(self, outputs: dict[str, object]) -> None:
        """First L-band intermod record must tie the two stacked bronze emitters together."""
        hits = outputs["intermod_hits.json"]["hits"]
        first = hits[0]
        assert first["band_tag"] == "L"
        assert first["site_low"] == "site-bronze-edge"
        assert first["site_high"] == "site-bronze-near"
        assert first["hit_mhz"]

    def test_summary_registry_counts_agree(self, outputs: dict[str, object]) -> None:
        """Summary carrier and hit totals must mirror the structured outputs."""
        summary = outputs["summary.json"]
        reg = outputs["registry.json"]["registry"]
        hits = outputs["intermod_hits.json"]["hits"]
        assert summary["registry_carriers"] == len(reg)
        assert summary["hits"] == len(hits)
        assert summary["sweep_rounds"] >= 1


class TestHelperSources:
    """Optional compiled helpers must ship sources alongside them under /app/."""

    def test_compiled_helpers_have_source_files_alongside(self) -> None:
        """Every ELF helper under /app must have a source file in the same directory."""
        for binary in _compiled_helpers_under_app():
            parent = binary.parent
            sources = [
                entry
                for entry in parent.iterdir()
                if entry.is_file() and entry.suffix in SOURCE_SUFFIXES
            ]
            assert sources, (
                f"compiled helper {binary} requires a source file alongside it in {parent}"
            )


class TestGoDelivery:
    """Go sources and release binary paths from the task prompt must exist on disk."""

    def test_go_sources_exist_under_imha_src(self) -> None:
        """At least one Go source file must live under /app/imha-src/ as required by the prompt."""
        src_dir = Path("/app/imha-src")
        assert src_dir.is_dir(), "expected /app/imha-src directory"
        go_files = list(src_dir.rglob("*.go"))
        assert len(go_files) >= 1, "expected at least one .go file under /app/imha-src"


class TestBinaryMalformedInput:
    """Malformed fixture runs must fail closed with no named audit artifacts."""

    def test_malformed_policy_json_exits_without_audit_files(self, tmp_path: Path) -> None:
        """Invalid policy.json must yield a non-zero exit and none of the three JSON outputs."""
        assert BINARY_PATH.is_file(), "release binary must exist at /app/bin/imha"
        staged = tmp_path / "imhr_lab"
        shutil.copytree(DATA_DIR, staged)
        (staged / "policy.json").write_text("{invalid", encoding="utf-8")
        out_dir = tmp_path / "audit"
        out_dir.mkdir()
        env = os.environ.copy()
        env["IMHA_DATA_DIR"] = str(staged)
        env["IMHA_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY_PATH)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode != 0, res.stderr
        for name in OUTPUT_FILES:
            assert not (out_dir / name).is_file(), f"unexpected output file on error: {name}"


class TestBinaryRerun:
    """End-to-end rerun against a copied dataset must reproduce the same digests."""

    def test_release_binary_replay_matches_hashes(self, tmp_path: Path) -> None:
        """Re-running the packaged Go binary on a fresh copy of the fixtures stays stable."""
        assert BINARY_PATH.is_file(), "release binary must exist at /app/bin/imha"
        staged = tmp_path / "imhr_lab"
        shutil.copytree(DATA_DIR, staged)
        out_dir = tmp_path / "audit"
        out_dir.mkdir()
        env = os.environ.copy()
        env["IMHA_DATA_DIR"] = str(staged)
        env["IMHA_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(BINARY_PATH)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            obj = _load_json(out_dir / name)
            digest = _sha256_bytes(_canonical(obj).encode("utf-8"))
            assert digest == expected, f"replay mismatch for {name}"
