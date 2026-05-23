"""Verifier suite for tick-align-window-audit.

Pins SHA-256 digests for every fixture under `/app/taw_lab/`, checks the three
audit JSON files for canonical minified digests plus the on-disk UTF-8 layout
from the spec, and spot-checks cluster statuses against the bundled scenario.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TAW_DATA_DIR", "/app/taw_lab"))
AUDIT_DIR = Path(os.environ.get("TAW_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ("clusters.json", "pool_ledger.json", "summary.json")

BINARY_CANDIDATES = (
    Path("/app/_taw_build/taw"),
    Path("/app/bin/taw"),
    Path("/app/build/taw"),
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "dab6c7af20ee33ea72248a625670e19708d45fe854c09d6174b962b1e572e888",
    "anchors/window.json": "eeb65488eb3afbad6bcdbcb6b6697c6fc6ec23e5b7ef6ef145ab989d4e0e1f67",
    "ancillary/meta.json": "f310df5153f343f2404d321af5f08aa0437087dd043ff906e8a56c98a3ec52f2",
    "ancillary/notes.json": "1987e364f8dbe9dc59e4adbf82be2e2a1cf66ce78ab2f3da589f1b6a810e62c5",
    "ancillary/stub.json": "e12c4b281cc7b82ddd1ece15326b1ed11a6b8facbecb482a4b89d3738402e9dc",
    "domain_layout.json": "9a119ee33c7686109a2d8fd5964c36d603c0009d516d78f330ea84ba4b1253b4",
    "incident_log.json": "84d6e610bcc3820cf9459b9b1b7164468dc06586ee7d0c08c995b882ef57f1b6",
    "lanes/l01.json": "c525fc89b05b081797772c81ca9add2b5e953b990b958a44aa09b32dad33dd04",
    "lanes/l02.json": "fb848bfe38a66a5442564900baa9b92c494f88254f7f27abffe55354411e5e05",
    "lanes/l03.json": "c0d839765b3945c81b4fabc218bce920141d25434a6ce62a322eae77b91d18c8",
    "lanes/l04.json": "48e553d6ba0a633810c1ac3f06ff2a532cec308376dd28054579ecb6f304d1ca",
    "lanes/l05.json": "bea1d11a71f46b5969069d1f2509d325465cf705e84f3d0205c6623f17cb997c",
    "lanes/l06.json": "83ed2e5a0829c7b0c49edec8e1da9d203c6a09196f9a57b8888318438ae4adde",
    "lanes/l07.json": "cfc5b75a9783db4d70cfe4c778edf8b911c8c21676a2a177542131f9f4f4254d",
    "lanes/l08.json": "76669368871679d26b4ea2b2c6a1e13f61bb2f81fc6eb6de621d46cec45dfc87",
    "lanes/l09.json": "bb945e0d61e2f4e2aeaf9504b396e79ae6d63e8439b646bc3b9b5e4c096cf215",
    "lanes/l10.json": "70304ee829880839850451c9fa98b0ca6cae2a03094f2d762b8153c17421d44a",
    "lanes/l11.json": "18a0b4aa1c89d6b2a4c8b49374fd8c1cfc287eae1966a0e0f6111f1d452b22b7",
    "lanes/l12.json": "bb2e7139e4df4ca3d24c8842e0a6e523d773a80daf2663cdab75e025dd11e4fb",
    "lanes/l13.json": "ec729646a28fc98fffc85b2b86a4236779fded8a5744881d7f334420bac1b9fe",
    "lanes/l14.json": "3545abf94eb19f9d6c32e9dd7760ae1f12cec3ae00ef452688c14f18e4b515f2",
    "policy.json": "5adf9892d306c1ff95df0b9cdbe2e7f25a79736945d03cf37ceb78599ac90e19",
    "pool_state.json": "bb13868a0c02e1203652e42f693e16d9946f7f5c48cd5d3fd054e7472f9da2aa",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "clusters.json": "48a38f932ff466d60dae392dcaa4a00b690cb00cd0d44fac74cb12c841bdd30b",
    "pool_ledger.json": "6b5e66ced3b7127c90b9ada6a262c22adf18b05bebebc1b7a850dfdfe3673b3d",
    "summary.json": "4c0586710415b5604a89285e1eeb308b1b8be26c0f97349d94f9147156890319",
}


EXPECTED_OUTPUT_RAW_HASHES = {
    "clusters.json": "1faa50cc1021164c7b6cb2fcd0d269240dd1a84a5527c4edb4be5a161f838936",
    "pool_ledger.json": "ace0c4a93003c7249786afbe78c9890c579d08ca8a387be5fc925a9a389ce6a5",
    "summary.json": "dac0f86ada095797385e24164f22d9f11dcf4d235cf39dc7c8bb4f860d70f431",
}


EXPECTED_FIELD_HASHES = {
    "clusters.clusters": "7a249e0704eff7ed1d99bd56cf312ae9993971b58b5bde2fb307355498b1d95b",
    "pool_ledger.draws": "eff0f704c21f7db39c0a7e6d6d19d0ec514c9439e2f1e1eeeab7a3222817646a",
    "summary.effective_window": "55a4c9231071e24506296a86287422780299d3dd467e003d4c70d970bb6f2b14",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for a byte string."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize a JSON value with sorted keys and minimal separators."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_bytes(value: object) -> bytes:
    """Match SPEC.md on-disk UTF-8 JSON: two-space indent, ASCII, sorted keys, trailing newline."""
    text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_binary() -> Path | None:
    """Return the first existing candidate helper path, if any."""
    for candidate in BINARY_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


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

    def test_output_raw_sha256(self) -> None:
        """Each audit file's raw bytes must match the pinned on-disk digest."""
        for name, expected in EXPECTED_OUTPUT_RAW_HASHES.items():
            path = AUDIT_DIR / name
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"raw digest mismatch for {name}"

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
        clusters = outputs["clusters.json"]["clusters"]
        assert (
            _sha256_bytes(_canonical(clusters).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["clusters.clusters"]
        )
        draws = outputs["pool_ledger.json"]["draws"]
        assert (
            _sha256_bytes(_canonical(draws).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["pool_ledger.draws"]
        )
        eff = outputs["summary.json"]["effective_window"]
        assert (
            _sha256_bytes(_canonical(eff).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.effective_window"]
        )


class TestSemanticCoverage:
    """Spot-check bundled lane outcomes described in the spec."""

    def test_quarantined_singleton_lane_delta(self, outputs: dict[str, object]) -> None:
        """lane-delta must sit alone as a quarantined cluster with zero pool draw."""
        clusters = outputs["clusters.json"]["clusters"]
        row = clusters[0]
        assert row["cluster_id"] == 0
        assert row["lane_ids"] == ["lane-delta"]
        assert row["status"] == "quarantined"
        assert row["pool_draw"] == 0

    def test_aligned_pair_pool_satisfied(self, outputs: dict[str, object]) -> None:
        """lane-a and lane-b must merge and draw pool tokens when affordable."""
        clusters = outputs["clusters.json"]["clusters"]
        row = clusters[1]
        assert row["lane_ids"] == ["lane-a", "lane-b"]
        assert row["status"] == "pool_satisfied"
        assert row["pool_draw"] == 20

    def test_singleton_deferred_when_pool_short(self, outputs: dict[str, object]) -> None:
        """lane-c must remain deferred when the pool cannot fund its draw."""
        clusters = outputs["clusters.json"]["clusters"]
        row = clusters[2]
        assert row["lane_ids"] == ["lane-c"]
        assert row["status"] == "pool_deferred"
        assert row["pool_draw"] == 0

    def test_summary_token_ledger(self, outputs: dict[str, object]) -> None:
        """Summary counters must reflect one satisfied draw and one deferral."""
        summary = outputs["summary.json"]
        assert summary["opening_tokens"] == 25
        assert summary["closing_tokens"] == 5
        assert summary["pool_satisfied_clusters"] == 1
        assert summary["pool_deferred_clusters"] == 1
        assert summary["quarantined_clusters"] == 1
        assert summary["stride_sign_fold_applied"] is True
        assert summary["lane_count_in_window"] == 4
        assert summary["tiers_touched"] == ["core", "edge"]


class TestBinaryRejectsEmptyWindow:
    """Optional binary checks for invalid anchor intersections."""

    def test_binary_exits_nonzero_on_empty_window_intersection(self, tmp_path: Path) -> None:
        """When anchors and policy disagree enough to empty the intersection, exit is non-zero."""
        binary = _resolve_binary()
        if binary is None:
            pytest.skip("helper binary not present in this image layout")
        staged = tmp_path / "lab"
        out_dir = tmp_path / "out"
        staged.mkdir()
        out_dir.mkdir()
        for rel in EXPECTED_INPUT_HASHES:
            if rel == "SPEC.md":
                continue
            src = DATA_DIR / rel
            dest = staged / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        bad_anchor = {"window": {"end_day": 5, "start_day": 1}}
        (staged / "anchors" / "window.json").write_text(
            json.dumps(bad_anchor, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        proc = subprocess.run(
            [str(binary), str(staged), str(out_dir)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode != 0
        for name in OUTPUT_FILES:
            assert not (out_dir / name).is_file()
