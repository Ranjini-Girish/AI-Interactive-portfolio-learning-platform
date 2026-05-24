"""Behavioral tests for latch-echo-bin-audit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("LEB_DATA_DIR", "/app/leb_lab"))
AUDIT_DIR = Path(os.environ.get("LEB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["latch_bins.json", "summary.json"]

_BINARY_CANDIDATES = (
    Path("/app/_leb_build/leb"),
    Path("/app/bin/leb"),
    Path("/app/leb"),
    Path("/app/build/leb"),
)


EXPECTED_INPUT_HASHES = {
    "anchors/east.json": "95a9cb71c8647837804a96549a71bcd5859d24182396cbefcdc9b2a93c97ba97",
    "anchors/west.json": "a4f6d3014b11f77ca64a1c89d914caf3335510f49fb36f6c85c6b23db62108d9",
    "ancillary/extra.json": "66e0b05e1b6ab764bae179cd10b2453c3ca980eb095f89401c38ff4f021f5dbc",
    "ancillary/meta.json": "8c183cc752b30a37abd323114a0ec6775a191c5b2d886e5aad85589a6d31ea81",
    "ancillary/notes.json": "35939c1e11de41c34c3ca02d0b877737dd0dd3fec8b669fb719b9c84de2a61cb",
    "domain_layout.json": "6c322304d0e092797682ec43070b1a8374ac38b05f01e4036a2b09dc966c7f39",
    "incident_log.json": "d91cb68778fd4deac977670dde84b594e4ffeb0332fc9d0345767aad3831df3f",
    "policy.json": "3044fbe2cc5dcd5517695c0da622d30fa1575a6c4961edf7ec4d0a7660f3f1a4",
    "pool_state.json": "9f22c46193ca7e2bec3bf0fdbe27e8f0fbd7b2a2f4e4fc6b74b151b668dc6f68",
    "samples/sample_00.json": "0ff0636c66eae057615dc4f498e13069a8917f640a2cb80b6a5b0f80997c74d8",
    "samples/sample_01.json": "09430c1192487b8479c972b7f8c6f54667b75ed86dc4cb73086aa3c14af68cc9",
    "samples/sample_02.json": "c0919ae596827bf5eb6f71df397db1dd3ae39f8d6883091205b6484e9b1844ab",
    "samples/sample_03.json": "fd118d7f13058576c550f831a2f4d3e549c0507e60aafcbf0d778828fe336af8",
    "samples/sample_04.json": "15e8a77b4da797ff86faeb053b88b526df87354a0d1fd0b9196476ab755c095e",
    "samples/sample_05.json": "87642c823a07cf8bfd175b274e470999e05dd42fa80af0a8416e9619c3b423ba",
    "samples/sample_06.json": "619b766173f05569046c9ceb3f4a105e5a59cfc3f8d13f84dda54972fd229733",
    "samples/sample_07.json": "2be02010b16071695869acb526673071f121b15c61b351542907f137af922f91",
    "samples/sample_08.json": "1d6095a4263873e77203fa9d2da6fb7a5c393651f3f09a4589016d5fb24973a4",
    "samples/sample_09.json": "dc8bef283a3cbf40f393691c82f635f11da342f07cdc04850531146689ab238f",
    "samples/sample_10.json": "f21b56ee91bfec483450f86e0ec4832cf5e44669b558f727f87db70029046ba3",
    "samples/sample_11.json": "40c1c4dde58a2c7c6c10fad9ffdbe3a9e85bae31b0dcbbcbb760579c29dd6f33",
    "SPEC.md": "66f3921e2cb07e9dbb97e0d849489d949cba10fd995c6a8ff5bf30ba311ff75c"
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "latch_bins.json": "c4319255ee081ce263cbd07f8dcb5455b6b15ae3517b41bb31411e11df864454",
    "summary.json": "5e7505d05d31de2a5f465db95ccbdb86760040fc51541df2466855397866073b"
}


EXPECTED_FIELD_HASHES = {
    "latch_bins.json.samples": "50459402a2a3627cae65b8759ac3a8310580dee866e966f3bb46d15947918e15",
    "summary.json.tail_ledger_sha": "a6a5a1e79374954569a4284a769432f35bc2674e024b094fc7c593f0339169b7",
    "summary.json.total_assignments": "9f14025af0065b30e47e23ebb3b491d39ae8ed17d33739e5ff3827ffb3634953"
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize like the reference harness."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Parse UTF-8 JSON from ``path``."""
    return json.loads(path.read_text(encoding="utf-8"))


def _json_text(obj: object) -> str:
    """Write canonical two-space JSON with one trailing newline."""
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True, separators=(",", ": ")) + "\n"


def _mod_nonneg(x: int, m: int) -> int:
    """Non-negative remainder matching the specification."""
    r = x % m
    return r + m if r < 0 else r


def _find_leb_binary() -> Path:
    """Locate the agent-built latch auditor executable."""
    for candidate in _BINARY_CANDIDATES:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    names = ", ".join(str(p) for p in _BINARY_CANDIDATES)
    raise AssertionError(f"no executable latch auditor found (checked {names})")


def _write_generated_lab(root: Path) -> None:
    """Materialize a minimal lab tree not present in the shipped bundle."""
    (root / "anchors").mkdir(parents=True)
    (root / "samples").mkdir(parents=True)
    (root / "policy.json").write_text(
        _json_text(
            {
                "bin_stride": 4,
                "blend_mod": 7,
                "echo_max": True,
                "latch_echo": True,
                "latch_mod": 2,
                "pair_span": 1,
                "skew_mix": 2,
            }
        ),
        encoding="utf-8",
    )
    (root / "pool_state.json").write_text(
        _json_text({"ledger_serial": 5, "quorum_ring": 3}),
        encoding="utf-8",
    )
    (root / "anchors/east.json").write_text(_json_text({"lane_add": 1}), encoding="utf-8")
    (root / "anchors/west.json").write_text(_json_text({"lane_add": 2}), encoding="utf-8")
    (root / "incident_log.json").write_text(
        _json_text({"masks": [{"sample_id": "alt_a", "zero_slots": [1]}]}),
        encoding="utf-8",
    )
    (root / "samples/sample_00.json").write_text(
        _json_text(
            {
                "latch": -1,
                "readings": [10, 20, 30],
                "sample_id": "alt_a",
                "trace_tag": "gen",
            }
        ),
        encoding="utf-8",
    )


def _compute_reference(data_dir: Path) -> dict[str, object]:
    """Independent re-derivation of audit outputs from SPEC.md rules."""
    policy = _load_json(data_dir / "policy.json")
    pool = _load_json(data_dir / "pool_state.json")
    east = _load_json(data_dir / "anchors/east.json")
    west = _load_json(data_dir / "anchors/west.json")
    incidents = _load_json(data_dir / "incident_log.json")
    assert isinstance(policy, dict)
    assert isinstance(pool, dict)
    assert isinstance(east, dict)
    assert isinstance(west, dict)
    assert isinstance(incidents, dict)

    w = int(policy["bin_stride"])
    blend_mod = int(policy["blend_mod"])
    pair_span = int(policy["pair_span"])
    latch_mod = int(policy["latch_mod"])
    skew_mix = int(policy["skew_mix"])
    echo_max = bool(policy["echo_max"])
    latch_echo = bool(policy["latch_echo"])
    ledger = int(pool["ledger_serial"])
    quorum = int(pool["quorum_ring"])
    e_lane = int(east["lane_add"])
    v_lane = int(west["lane_add"])

    masks: dict[str, set[int]] = {}
    for row in incidents.get("masks", []):
        if not isinstance(row, dict):
            continue
        sid = str(row["sample_id"])
        slots = row.get("zero_slots", [])
        if sid not in masks:
            masks[sid] = set()
        for z in slots:
            masks[sid].add(int(z))

    samples_out: dict[str, list[dict[str, int]]] = {}
    tail_parts: list[str] = []
    total_assignments = 0

    for sample_path in sorted(data_dir.joinpath("samples").glob("sample_*.json")):
        doc = _load_json(sample_path)
        assert isinstance(doc, dict)
        sid = str(doc["sample_id"])
        latch = int(doc["latch"])
        readings = [int(x) for x in doc["readings"]]
        n = len(readings)
        for zi in masks.get(sid, set()):
            if 0 <= zi < n:
                readings[zi] = 0

        adj = [readings[i] + _mod_nonneg(e_lane * i + v_lane, w) for i in range(n)]
        skew = _mod_nonneg(
            _mod_nonneg(ledger, blend_mod) * skew_mix + latch + _mod_nonneg(quorum, w),
            w,
        )
        hist: dict[int, int] = {}
        ssum = 0
        for k in range(1, n + 1):
            ssum += adj[k - 1]
            folded = (ssum + skew) // w // pair_span
            hist[folded] = hist.get(folded, 0) + 1
            if latch_echo and k % latch_mod == 0:
                hist[folded] = hist.get(folded, 0) + 1

        if echo_max and hist:
            b_max = max(hist)
            hist[b_max] += _mod_nonneg(e_lane + v_lane + latch, w)

        bins = sorted(b for b, cnt in hist.items() if cnt > 0)
        rows = [{"bin": b, "tally": hist[b]} for b in bins]
        samples_out[sid] = rows
        total_assignments += n
        tail_parts.append(f"{sid}:{ssum}")

    tail_parts.sort()
    tail_sha = hashlib.sha256(",".join(tail_parts).encode("utf-8")).hexdigest()
    return {
        "latch_bins.json": {"samples": samples_out},
        "summary.json": {
            "bin_stride": w,
            "blend_mod": blend_mod,
            "echo_max": echo_max,
            "latch_echo": latch_echo,
            "latch_mod": latch_mod,
            "ledger_serial": ledger,
            "pair_span": pair_span,
            "quorum_ring": quorum,
            "skew_mix": skew_mix,
            "tail_ledger_sha": tail_sha,
            "total_assignments": total_assignments,
        },
    }


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load mandated audit JSON objects."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


class TestInputIntegrity:
    """Pinned fixture bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every input file under the lab matches its digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestReportStructure:
    """Hash-locked outputs."""

    def test_output_canonical_hashes(self, outputs: dict[str, object]) -> None:
        """Each audit file matches the canonical minified digest."""
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


class TestPolicyFlags:
    """Enum coverage for policy toggles."""

    def test_echo_max_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy echo_max flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("echo_max") is True

    def test_latch_echo_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy latch_echo flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("latch_echo") is True



class TestLatchBins:
    """Semantic checks on the primary histogram artifact."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["latch_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        fixture_ids = []
        for path in sorted((DATA_DIR / "samples").glob("sample_*.json")):
            doc = _load_json(path)
            assert isinstance(doc, dict)
            fixture_ids.append(doc["sample_id"])
        for sid in fixture_ids:
            assert sid in samples, f"missing histogram for {sid}"

    def test_histogram_rows_sorted_by_bin(self, outputs: dict[str, object]) -> None:
        """Each histogram list is sorted ascending by bin."""
        main = outputs["latch_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for sid, rows in samples.items():
            assert isinstance(rows, list)
            bins = [row["bin"] for row in rows if isinstance(row, dict)]
            assert bins == sorted(bins), f"unsorted bins for {sid}"


class TestAlternateGeneratedFixture:
    """Generated lab data proves the latch pipeline beyond bundled hash locks."""

    def test_generated_lab_matches_independent_reference(self, tmp_path: Path) -> None:
        """A synthetic lab at LEB_DATA_DIR must yield outputs matching spec re-derivation."""
        lab = tmp_path / "gen_lab"
        out_dir = tmp_path / "gen_audit"
        _write_generated_lab(lab)
        out_dir.mkdir()
        expected = _compute_reference(lab)
        binary = _find_leb_binary()

        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("LEB_DATA_DIR", "LEB_AUDIT_DIR")
        }
        env["LEB_DATA_DIR"] = str(lab)
        env["LEB_AUDIT_DIR"] = str(out_dir)
        res = subprocess.run(
            [str(binary)],
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        assert res.returncode == 0, res.stderr

        for name in OUTPUT_FILES:
            path = out_dir / name
            assert path.is_file(), f"missing {name} under alternate LEB_AUDIT_DIR"
            actual = _load_json(path)
            assert _canonical(actual) == _canonical(expected[name]), f"mismatch for {name}"
