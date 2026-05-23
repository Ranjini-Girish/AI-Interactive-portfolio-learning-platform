# scaffold-status: oracle-pending
"""Behavioral tests for ket."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("KET_DATA_DIR", "/app/ket_lab"))
AUDIT_DIR = Path(os.environ.get("KET_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["trim_bins.json", "spill_events.json", "summary.json"]

EXPECTED_INPUT_HASHES = {
    "anchors/east.json": "bec736964dddab0ed5d9664b6802f04ea5ad30fecd85bbbc171f73bbeda58427",
    "anchors/west.json": "b535565aed051ecb2be962b0e574fa3809b6c8e416098c355c988959af9d4aef",
    "ancillary/extra.json": "43fd28d9184971ef33bea9d3ef844bbccafc48ebf201a3252ff8818511593600",
    "ancillary/meta.json": "10e1e9b32cc0f2aa648aea38a3b06fa22744351a14ab540af18f8589b82741d8",
    "ancillary/notes.json": "f190a28efdbf327342aaa2690db9f72c38a24bbadfc163bf042841d09be3b78d",
    "domain_layout.json": "34a83521cb57c99a0071f7ec0491f0920814692f6e7ff3ade7840232be08c149",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "ff16aa2ff86d028072910127e7d96aa156d84bc11a870c7f3245e8b9b1d504f6",
    "incident_log.json": "3b31f258c124d894546cec738c0ece083981851f4e15fd2ed778aa0f5361c9b0",
    "manifest.json": "d20250608b479c9bb5fa32f44097acac5dd914abc2a768b43fcb6619afdaee01",
    "meta/seq.json": "5f13187a33f202a8e711072610ef96aabfc4906f846beba6e67f8ce44056f56e",
    "policy.json": "12cc07de2285bd16021a12af45ce5942cd87c2a59ecc14745973244a4a880252",
    "pool_state.json": "b81d75d69a129241ea0dd52f9d1a4eef48751103605cbabb13ab33c4c479f206",
    "samples/sample_00.json": "cb2bc38a09a7c96bf66ef4797f52a82581c5f46e1af640bfb1e735125089b719",
    "samples/sample_01.json": "0c9d16bf04aee1fb102e97d8f4df69072b5e81e504d30acd1e1c74abcab0a507",
    "samples/sample_02.json": "50c86fd2b503a426d9342266f610f401e85401f57ddc229d78a1577931027db9",
    "samples/sample_03.json": "fc6739ca8e5f64ffbda3d6c98617b327ec0585c08b42f1c9a2d0605244654984",
    "samples/sample_04.json": "2f8e88ea754b0681c748688ba8df7c0d0158b44fc1f2e6eccb49c3de95b49250",
    "samples/sample_05.json": "9b501da61c330c56a591828e8e5e35ff15c9513c8a7a149c9973be79aee99e5a",
    "samples/sample_06.json": "41d902c4f64733a81b2c8324e6b922dc9198e634283264568c273ae81ee9acd5",
    "samples/sample_07.json": "f485f8bc32809237ea49b41ea29597aece45be4e77bbed5e47c1a7e502491af3",
    "samples/sample_08.json": "72d886984d43a1d7f5361dc5ba6b647c7bf4d4103f69ebcc3e608fdb57c919b7",
    "samples/sample_09.json": "a8a385a2af3b591c5286719035ffec148e24766a3d436fd441dea0d089f8c76f",
    "samples/sample_10.json": "3548d87abb6f9107f86fd16d757d347749f0273138ef1092e1c944b246e59474",
    "samples/sample_11.json": "94969edfec12577e2bfca2d927b5e598b86b13e8f7102cef0ec755460d14a8db",
    "SPEC.md": "750b80c4bab8ce75b3dcb0e61f20ce9e7669b6c2f8f7d5a83af2bc4a96d1e793",
    "spill_links.json": "67e299ade22b7da8923c9eab555a3210cbf2539819f76049b4e98982e726789c"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "trim_bins.json": "58b34306c380a54d8e778212a2b2334099e16222ba3f3cb3227d0d5863351401",
    "spill_events.json": "f3b311a6db6ae4871b68a1d90e595e390022bde17b297baf9f291136d4048a5c",
    "summary.json": "52fb339e3b9c5682e68ab9af310709ccafda6d38d2280a2e0ae21f6d9532344c"
}

EXPECTED_FIELD_HASHES = {
    "trim_bins.json.samples": "2985d1727b2fa7044c0af399685f052855d3cec790ca9cc6c7ddf749ed6d6f20",
    "summary.json.stale_sample_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.effective_fold_stride": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"
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

    def test_epoch_spill_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy epoch_spill flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("epoch_spill") is True

    def test_trim_echo_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy trim_echo flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("trim_echo") is True

    def test_link_propagate_total_matches_events(self, outputs: dict[str, object]) -> None:
        """Summary propagate total equals the number of walk events emitted."""
        summary = outputs["summary.json"]
        events_doc = outputs["spill_events.json"]
        assert isinstance(summary, dict)
        assert isinstance(events_doc, dict)
        ev = events_doc.get("events")
        assert isinstance(ev, list)
        total_key = "bind_propagate_total" if "KET" == "GTB" else "spill_propagate_total"
        assert summary.get(total_key) == len(ev)


class TestPrimaryBins:
    """Semantic checks on histogram artifacts."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["trim_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for path in sorted((DATA_DIR / "samples").glob("sample_*.json")):
            doc = _load_json(path)
            assert isinstance(doc, dict)
            assert doc["sample_id"] in samples

    def test_histogram_rows_sorted_by_bin(self, outputs: dict[str, object]) -> None:
        """Each histogram list is sorted ascending by bin."""
        main = outputs["trim_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for sid, rows in samples.items():
            assert isinstance(rows, list)
            bins = [row["bin"] for row in rows if isinstance(row, dict)]
            assert bins == sorted(bins), f"unsorted bins for {sid}"

    def test_stale_sample_total_positive(self, outputs: dict[str, object]) -> None:
        """Bundled fixtures include at least one stale sample per current_epoch rule."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("stale_sample_total", 0) >= 1

    def test_effective_fold_stride_halved_when_tags_differ(self, outputs: dict[str, object]) -> None:
        """Manifest tag mismatch halves fold stride relative to lane stride in summary."""
        summary = outputs["summary.json"]
        manifest = _load_json(DATA_DIR / "manifest.json")
        policy = _load_json(DATA_DIR / "policy.json")
        assert isinstance(summary, dict)
        assert isinstance(manifest, dict)
        assert isinstance(policy, dict)
        lane_key = "tier_stride" if "KET" == "GTB" else "epoch_stride"
        if manifest.get("cal_tag") != manifest.get("run_tag"):
            assert summary.get("effective_fold_stride") == (policy[lane_key] + 1) // 2
        else:
            assert summary.get("effective_fold_stride") == policy[lane_key]
