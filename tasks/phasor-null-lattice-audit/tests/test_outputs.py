"""Verifier suite for the phasor null lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("PNL_DATA_DIR", "/app/pnl_lab"))
AUDIT_DIR = Path(os.environ.get("PNL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "bin_graph.json",
    "null_manifest.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "e2ee08707dcf55173837923ef93bb65f1c6e15bda5144ffc911fed97a66275ae",
    "anchors/a.json": "184744d3329ebb67edc93c26f8c74b4639f1e9ff253378f696259aa90824bb01",
    "anchors/b.json": "15ba205a3e43b19fc6a15189a88f6cae1ca0288971c76c12030cfdd967f40a25",
    "ancillary/meta.json": "e1fb2c2832920c24ba2f6e135b4a090282a7905190df1b8ff5cb6c26c51dfa2b",
    "ancillary/notes.json": "c764c1682600fece3d514c2a26e508faed8d9b991a0f650c16ebe41b183d05dc",
    "domain_layout.json": "265b64a1dda57d424873a7cdd931a39e68f49af76673748ae8c61a8f322fc87b",
    "incident_log.json": "cf5d5cffb6bdeecddac7bc3aa6b8add92c3301eb844a350a945d5057676397de",
    "items/item_00.json": "4e4595ed6ed2c1c02beb041e79e2cc702c8c8965875084064afbe943969cfa50",
    "items/item_01.json": "7af4b7c44268c325c273b3f995a758d7f4b41eb416008f3f9c4cac67ebb8ab1b",
    "items/item_02.json": "b894f1d34e6df5ee861454fa75db7cf023b46842e756ecef33f013609fbc606f",
    "items/item_03.json": "daad382c3a6d99834e070418b65b14e15fa395ec55a733cdff6e5b9e8d891436",
    "items/item_04.json": "800443eeb176ab9c659ad393033dc00ae0ae3b2dd52718fc0d646518f0768888",
    "items/item_05.json": "2e8ea244b10671c8149c122ecc47d993777c3d63fd1a379521ea1822c0b36dde",
    "items/item_06.json": "e3e9f59ab24258b8111966466f7fc09c4ed43d52f3d0f6d66a4e3f21a85866af",
    "items/item_07.json": "9071201e9a1fd41e29ca98adbff13cf8a6652dae0e5d85fd396b51902a2a3c3e",
    "items/item_08.json": "f3f1ebbcaef0f10e13854f1313b0bb878a145eb789f173e33c4be2fd5094f96f",
    "items/item_09.json": "a4ff97d05960a8cd59e7d3a9aaaaa1b6025dc1c353d3706b26a73f004b04d3c1",
    "items/item_10.json": "cecf04a7c6e17074944f5558e2644a738cbfa2ae9844c24e972bdcdfbef544ca",
    "items/item_11.json": "80f41292e3866e964d99916ee6a2227bc6c4ed57db58382395f1b5b87825c5ca",
    "items/item_12.json": "74dabda9417b3226eb58f954693ef471f6799806ed086b28cd6f5b7033195fbb",
    "items/item_13.json": "b05f652145c1f9c905d6c9601259412394df1250392982e1a19b5831092a1cec",
    "items/item_14.json": "219fe94b4ffdc6ad8172725cbc5f15b322ee1aac0525e5b33ea61504ec679327",
    "items/item_15.json": "3315e17c8b6e254084aff46135549b391be00736a94ce2a8862511bac98f7e2c",
    "items/item_16.json": "a0416932355ee9e1b57521b880f0473056595fba3ca5358b2854aa8fee5e726f",
    "items/item_17.json": "bd03db13be9b689246f5836279f80fd44474c94ab2295f99b614535e3ec95d6b",
    "policy.json": "c319a8b71e94a5998bb6f0b680b004ec7d65503435425ab2da6bf48228a647b6",
    "pool_state.json": "8a895aae0a4225e2e450f4e8ac7406efc9ed0a77f56c740a83a1a85fcba3ab28",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "bin_graph.json": "08c103000c6cf024f45107e893f58559b912ac979ec962e2fca3ea7be33b1779",
    "null_manifest.json": "0575490550334313b221609926dfa3a1170547737ebea5f42f22734cb8f186a5",
    "summary.json": "14a8a0d64aa9b080c55fefa55d3d51beaf7dd00273cbe1090d08f92efb376902",
}


EXPECTED_FIELD_HASHES = {
    "bin_graph.edges": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
    "null_manifest.components": "116215bb20e02851731e0f31a17a1b04748f05ec5885bd6ff2b83d9ddd19915d",
    "summary.components_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
}


def _sha256_bytes(data: bytes) -> str:
    """Return lowercase hex SHA-256 for the given byte string."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize like the verifier reference: sorted keys, minified separators."""
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
def components(outputs: dict[str, object]) -> list[dict[str, object]]:
    """Return component rows from the null manifest."""
    nm = outputs["null_manifest.json"]
    assert isinstance(nm, dict)
    rows = nm["components"]
    assert isinstance(rows, list)
    out: list[dict[str, object]] = []
    for row in rows:
        assert isinstance(row, dict)
        out.append(row)
    return out


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

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        bg = outputs["bin_graph.json"]
        assert isinstance(bg, dict)
        assert (
            _sha256_bytes(_canonical(bg["edges"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["bin_graph.edges"]
        )

        nm = outputs["null_manifest.json"]
        assert isinstance(nm, dict)
        assert (
            _sha256_bytes(_canonical(nm["components"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["null_manifest.components"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["components_total"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.components_total"]
        )


class TestSummaryCrossChecks:
    """Cross-check summary counters against the manifest rows."""

    def test_summary_matches_manifest_counts(self, outputs: dict[str, object]) -> None:
        """Summary class totals must equal histogram counts from the manifest."""
        sm = outputs["summary.json"]
        nm = outputs["null_manifest.json"]
        assert isinstance(sm, dict) and isinstance(nm, dict)
        rows = nm["components"]
        assert isinstance(rows, list)
        hist: dict[str, int] = {}
        for row in rows:
            assert isinstance(row, dict)
            cls = row["class"]
            assert isinstance(cls, str)
            hist[cls] = hist.get(cls, 0) + 1
        assert sm["components_total"] == len(rows)
        assert sm["components_vacant"] == hist.get("vacant", 0)
        assert sm["deep_null_components"] == hist.get("deep_null", 0)
        assert sm["soft_null_components"] == hist.get("soft_null", 0)
        assert sm["components_energized"] == hist.get("energized", 0)


class TestBundledSemantics:
    """Spot-check behaviours that the bundled dataset is designed to exercise."""

    def test_bin_graph_empty_when_wrap_is_zero(self, outputs: dict[str, object]) -> None:
        """With wrap_delta zero, distinct bins never share edges even on the same ring."""
        sm = outputs["summary.json"]
        bg = outputs["bin_graph.json"]
        assert isinstance(sm, dict) and isinstance(bg, dict)
        assert sm["wrap_delta"] == 0
        assert bg["edges"] == []

    def test_bin_three_is_vacant_with_suppressed_item(self, components: list[dict[str, object]]) -> None:
        """Bin three only carries a suppressed item, so the component is vacant but lists it."""
        row = next(c for c in components if c["anchor_bin"] == 3)
        assert row["class"] == "vacant"
        assert row["contributors"] == []
        assert row["suppressed_ids"] == ["item_04"]

    def test_bin_five_keeps_only_non_quarantined_lineage(self, components: list[dict[str, object]]) -> None:
        """Quarantined lineage L7 drops item_06 while item_07 still contributes."""
        row = next(c for c in components if c["anchor_bin"] == 5)
        assert row["contributors"] == ["item_07"]

    def test_bin_zero_is_deep_null_with_two_contributors(self, components: list[dict[str, object]]) -> None:
        """Opposite phased bronze pair on bin zero cancels to a deep null."""
        row = next(c for c in components if c["anchor_bin"] == 0)
        assert row["class"] == "deep_null"
        assert row["contributors"] == ["item_00", "item_01"]

    def test_bin_seven_is_energized(self, components: list[dict[str, object]]) -> None:
        """The dense bin seven mix lands above the soft threshold."""
        row = next(c for c in components if c["anchor_bin"] == 7)
        assert row["class"] == "energized"
