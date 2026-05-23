# scaffold-status: oracle-pending
"""Behavioral tests for gtb."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("GTB_DATA_DIR", "/app/gtb_lab"))
AUDIT_DIR = Path(os.environ.get("GTB_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["tier_bins.json", "bind_events.json", "summary.json"]

EXPECTED_INPUT_HASHES = {
    "anchors/north.json": "617bde82cf4814cbf4015f74c1d35cd8a3c245e4ba607645dced03803e7ea808",
    "anchors/south.json": "9dade45d819b92c0e7d8a2deb7ae8d9eed4eda57c004d9153071eefd4df19ab3",
    "ancillary/extra.json": "43fd28d9184971ef33bea9d3ef844bbccafc48ebf201a3252ff8818511593600",
    "ancillary/meta.json": "d98e97b0cee2e3db352a2220dae4a70454e47ec0ad19de42c4fc590352ada9ac",
    "ancillary/notes.json": "f190a28efdbf327342aaa2690db9f72c38a24bbadfc163bf042841d09be3b78d",
    "bind_edges.json": "67dfb1613d425c558671963e43a704a3d772ee14cc74f90e01331908cce8d229",
    "domain_layout.json": "185741b6d653474f4dce0efd7e1e00a4348f7e933a3a3df0584e30c66641448f",
    "epochs.json": "74d0df6b2da068335c9f47cea7a106bda059a331139ac65ba0f0f6873fad0aa0",
    "grid/dims.json": "59e2181df33492f98008f5cbc12af8976756ead8b59550500b5863b7b4e6346f",
    "incident_log.json": "79a521cd6cebc5ff204a071b443e39580f33b22b36f207d60562d974cae5539e",
    "manifest.json": "7eb87ab3e734b72a8e3f40cf24276e28d794cce2dc2687e76d91079cfa017b1f",
    "meta/seq.json": "5f13187a33f202a8e711072610ef96aabfc4906f846beba6e67f8ce44056f56e",
    "policy.json": "395aa0d6d6ae5d3e91641a1563326d10e267ae58a48addb3c4df15ae4e469758",
    "pool_state.json": "acd7cfe56e3ed97dcf4369538f433392ef87d3193487f455e9f42009d63d7b90",
    "samples/sample_00.json": "2f3848eec3da4e94ffd14dea154561f812060b2666d928cb9f9ad998c396842f",
    "samples/sample_01.json": "fa05669b38812deab5df0907c3b6c3a9775a62772a57c554112712d7c25fa0cf",
    "samples/sample_02.json": "d3ea23c80d4adda30dbfb86fce6797a55e37cfc6f69d6be23bf927099645afa1",
    "samples/sample_03.json": "bce51e3d84be49a8fbb5483dbea2b8671b3c8cc06ec2a2df88bcead4659828e0",
    "samples/sample_04.json": "7adf5c08562915a36fdd3eaa24c1ae6c7bb3794820eea52658d0672b344af726",
    "samples/sample_05.json": "4c6b30debaddc3df3625c5c3ed0a147a13b9930a99e01e141bd644f80940ac04",
    "samples/sample_06.json": "4f16324717e469695a339b8288f1ea372c7ec06e680201aed60949c626106385",
    "samples/sample_07.json": "da879678cf56b554fcf2ad0ccf5bb3b18b1c175c691e0dd4adc2597e48675192",
    "samples/sample_08.json": "0880ec23159e41c55a2dbb05d3294989850a991d1af644236680365f83b8536a",
    "samples/sample_09.json": "72cd35585d494b1f35303c0b31b45aae2db8c52ebaa9d488390b7c1a5f770854",
    "samples/sample_10.json": "1c6717f560d01160c12413367a63741d7609b02a1a64e1df8597ff3f93c0a8f3",
    "samples/sample_11.json": "f1203c558e27b9e44b4a804614b32b1c1ce6df4a38099060b9df640d600889e3",
    "SPEC.md": "1558768b7b2f775fe077c07ab51c94fba8aad4c3570399b18978d9c27b9d6535"
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "tier_bins.json": "9a5ad6e9d5b9a6e6a272a414dbe8310c3a6467d47aebfba9a5b61bb27d50abd7",
    "bind_events.json": "20e4af74661c5eb72d2912c91a7e88d4cea1026f63a72d3c9cf7a820993c4551",
    "summary.json": "35825d6d9290f9a9a3a53530dad439749d69f6802b9c275ac00ba6eb578cfdb6"
}

EXPECTED_FIELD_HASHES = {
    "tier_bins.json.samples": "3aaed9f3134be6b33f254ea705d843ebd826849c9fa021745d006db918f5d49d",
    "summary.json.stale_sample_total": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.json.effective_fold_stride": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce"
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

    def test_tier_spill_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy tier_spill flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("tier_spill") is True

    def test_cooldown_echo_enabled_in_summary(self, outputs: dict[str, object]) -> None:
        """Policy cooldown_echo flag is true and summary records it."""
        summary = outputs["summary.json"]
        assert isinstance(summary, dict)
        assert summary.get("cooldown_echo") is True

    def test_bind_propagate_total_matches_events(self, outputs: dict[str, object]) -> None:
        """Summary propagate total equals the number of walk events emitted."""
        summary = outputs["summary.json"]
        events_doc = outputs["bind_events.json"]
        assert isinstance(summary, dict)
        assert isinstance(events_doc, dict)
        ev = events_doc.get("events")
        assert isinstance(ev, list)
        total_key = "bind_propagate_total" if "GTB" == "GTB" else "spill_propagate_total"
        assert summary.get(total_key) == len(ev)


class TestPrimaryBins:
    """Semantic checks on histogram artifacts."""

    def test_samples_object_covers_every_fixture_id(self, outputs: dict[str, object]) -> None:
        """Every sample_*.json id appears under samples."""
        main = outputs["tier_bins.json"]
        assert isinstance(main, dict)
        samples = main.get("samples")
        assert isinstance(samples, dict)
        for path in sorted((DATA_DIR / "samples").glob("sample_*.json")):
            doc = _load_json(path)
            assert isinstance(doc, dict)
            assert doc["sample_id"] in samples

    def test_histogram_rows_sorted_by_bin(self, outputs: dict[str, object]) -> None:
        """Each histogram list is sorted ascending by bin."""
        main = outputs["tier_bins.json"]
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
        lane_key = "tier_stride" if "GTB" == "GTB" else "epoch_stride"
        if manifest.get("cal_tag") != manifest.get("run_tag"):
            assert summary.get("effective_fold_stride") == (policy[lane_key] + 1) // 2
        else:
            assert summary.get("effective_fold_stride") == policy[lane_key]
