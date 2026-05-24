"""Verifier suite for skew-bin-recalc-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SBR_DATA_DIR", "/app/sbr_lab"))
AUDIT_DIR = Path(os.environ.get("SBR_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = ["histogram.json", "summary.json"]


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5c5b7c7b9bfe88e1ba871e777c7db562e5eb6675df48d505eea1b92d18a1364d",
    "policy.json": "3393a1890dfbea8eba011ee87bf18d91f7f95fa4f36cd537bafe1a803672d672",
    "pool_state.json": "a1b98fc7c506cb1825afd3026b3a5f883b7ab0a9296a85cf3a395fef4deac302",
    "incident_log.json": "fe02f4e957155ed03947300fa0dff335eec68ebec4d81740cedc2284a0d9d276",
    "domain_layout.json": "1b1a532416f8ad5300a818209ee8bdb28f4f71cd0f842e82e1694fff826136bb",
    "anchors/east.json": "818b9eb11968d1bb3b50b186f1909a468c5f4d24d4063685ee859a57f566b9e4",
    "anchors/west.json": "853ea7c58bdb7572b6bdfef3904812f02e61176d9263928588b9d2624aa657cf",
    "ancillary/extra.json": "454f99cb3ded6631b91c98c523e6b9ab849b4490f004ac01bcb90557b3c94d32",
    "ancillary/meta.json": "9971f656b7189b031c22fcc5ce5e1bb1c1af792570acf46005d283d154219653",
    "ancillary/stub.json": "45ad609ff3677f4e926efdf23b2aa684c97acf7b14e66232fb283e78063b1045",
    "samples/sample_00.json": "16c9659f8edd6c8273c839a86313f9b32a4995a83926d30f71b7d7f88a65374d",
    "samples/sample_01.json": "7d17026f0801437dbe10fd7e5774427ed08c69b3399f578099eddeacfd5b988b",
    "samples/sample_02.json": "9e941c4ff2d8d1c3720d923188ba287bea45746b39af063047200031829e70f8",
    "samples/sample_03.json": "fea92c9dbec9dc479c2d652b2676b71a8c5c1ee7ff9de218588cc6602f80177c",
    "samples/sample_04.json": "5f64361a5e1b69041275bf1582069c6a08bde6e9a4e4301ce87dbac0e3299a0f",
    "samples/sample_05.json": "dfc7bd2c85fee242e20a4d20ac88a58ae1215d4dca9c0c45e3efada8bfa479f5",
    "samples/sample_06.json": "3bbbf71dd291e8c481e1f0c4650eba07f2a5b32e853269bbda09ea2ee713f013",
    "samples/sample_07.json": "6ee5717486b1e5224c43e3cfd1a7e0c7c8b1b9baca66d993348f4227f082e562",
    "samples/sample_08.json": "6a134040e1be42d89d9386f37281a32ccaa73a452c3e93e1fd6c10695d466c02",
    "samples/sample_09.json": "7d920c08dc97a85435eb825d39aa9727cf21f39f935b02b33cf479a1e00d3c8f",
    "samples/sample_10.json": "f66e64b6cc46574681621194893d100cd807e2badeff30005a5ec31db5818670",
    "samples/sample_11.json": "8779ecd7dbaaf57ae6b1f22e5878a0d28317507edcf5aba6a264711dc25a4ddb",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "histogram.json": "8222033506b3a73db26014781dc853d93d4235127797f24c51958133a38d4466",
    "summary.json": "33091e5e8354fecb1a428c7d6f8ff03e5b1798131c988bfa0da38e404d42bc6d",
}


EXPECTED_FIELD_HASHES = {
    "histogram.json.bins": "3bb915ebed105a31f9d01b0e3499b9cc21ff69fcd355f5cd700a040c35e9873a",
    "summary.json.as_of": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
    "summary.json.bins": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.json.samples_in": "6b51d431df5d7f141cbececcf79edf3dd861c3b4069f0b11661a3eefacbba918",
    "summary.json.samples_used": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
}


def _sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest for bytes."""
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    """Serialize using the verifier's canonical minified form."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    """Load JSON from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted audit JSON objects."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


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
