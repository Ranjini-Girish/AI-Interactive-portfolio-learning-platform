"""Verifier suite for cipher-suite-lattice-audit.

These tests assert the agent's emitted JSON under ``/app/audit/`` against the
normative contract in ``/app/cipher_lattice/SPEC.md`` and the prose
``instruction.md``. Hash-locked fixtures guard the dataset while targeted
checks validate enum-like strings and ordering rules spelled out in the spec.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("CSL_DATA_DIR", "/app/cipher_lattice"))
AUDIT_DIR = Path(os.environ.get("CSL_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "downgrade_screen.json",
    "fs_tier_report.json",
    "merged_lattice.json",
    "revocation_lattice.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0b64dd1e65d18dfe41ddbb4023c08f9d8790f9d545b6e3137caa5c36cf8cd8c4",
    "anchors/profile.json": "d183cc25c6570145e65d275e4ca2d50160d1fd6f31136fa20c81b66dd34b5bad",
    "anchors/sentinel_hints.json": "6c0cb0cdd8c444a4cfe9b01ba455b4b5605eb742b2051f10c4301ca57d2faa97",
    "anchors/tier_caps.json": "79ee608377b89cf4cac55c4b22ed4ea909fd90ff14f854adc5dfb0fb5033fff0",
    "base_lattice/edges.json": "72ebad620bbb86634401e30e63d90b421d5557d00a4758ed70a1ca91e3966851",
    "base_lattice/nodes.json": "ad178f06a159d5580f3da2289238724c2b979bb185a62a01f1f0feecfcf04a18",
    "hosts/edge-ams-01.json": "ba37c4ba3082b737ecfb1b4c1b6c6204899d233aa58b46059d55dc31ad68e433",
    "hosts/edge-dub-02.json": "e767b91a2e12108a83f9344874069c5034764f458e67f5cdf86accfdada8e934",
    "hosts/edge-fra-03.json": "b529921f336c71f29c620a7ddcd83dd84ab7d957cdf2aee66c690707a1fc6a1e",
    "hosts/edge-iad-04.json": "285a4b80b5c16c3f5edcaf6b507f85723039648d35a1dc6ddfaf9621be88e2b6",
    "hosts/edge-lhr-05.json": "e434b36befc794a1a167f9786c66f026c70e06819d625bd45025a4a2bcfb9820",
    "hosts/edge-sin-06.json": "65ad53b255fe92f238ddcc64ae133d2785eccd335189080d52dddb0921eeea71",
    "hosts/edge-tlv-07.json": "c1647b65c30645496d8c7437d2047359f04087a803b55a277e1f7f6c0528d2d5",
    "hosts/edge-yyz-08.json": "fe406753d876ee8732cbbf60d2487884bee9f42cacb84922621e2e0a51552979",
    "incidents/incident_log.json": "fbb1c5728d2298d920cd3554274df7aff9b3f6e995c7aecf7ef275408710eb1d",
    "policy.json": "24ff369ddef97f0d614ccdc95d227c9a92da591e928cc7e4a1e0aa5b71589564",
    "pool_state.json": "5ecaec9a9f37282f6b1f4206c3fb493c8695717122cfd9c97f74c06487e2ed5c",
    "suites/TLS_AES_128_GCM_SHA256.json": "bd0f82eed602bf41d0b5871335fa0395dc531d8ecfeb418754a8d46b1dce7bd8",
    "suites/TLS_AES_256_GCM_SHA384.json": "595ede925370c10ec33477bc6023a22bf00fe522bb962c7c342af330d4c987c9",
    "suites/TLS_CHACHA20_POLY1305_SHA256.json": "34497f9aa32b95899bf4937c6112a8f587bf37ff6f7c21f22c9fd90c015d5858",
    "suites/TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA.json": (
        "ae00b8946218366cd6fc8716742c9b5d8b7866d2516197852d2698f2b92f7437"
    ),
    "suites/TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256.json": (
        "2394cabdcb8f89cb69c2fe882c405d9a40d4af9f9824d5cf7d1c1dc2c5b1b0e4"
    ),
    "suites/TLS_RSA_WITH_AES_128_CBC_SHA.json": "9b2fd784a25a465ed74de249f9973b1dec434ef879fcd6cfff77a860b992f909",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "downgrade_screen.json": "c8c63d4593be94c26a3849e88e69cfa43e85251cf7ab167f5c8004a7a0bb4075",
    "fs_tier_report.json": "b03b7ed5d9501a960b04dbfcf0ac31d821f5b964ea62e9219c27f1f4e1e07fad",
    "merged_lattice.json": "82f268c839987bdaa9b329be29dd3c412aa8768a1fdc726d643bd81a768a448c",
    "revocation_lattice.json": "e1d8a38b2a6ef087fd426f08cc07d21d0af5a40f610d2d6f78a619ed4f9c6510",
    "summary.json": "31d0927851e9fb4bd38216a1bae79b08f92e84f926ca02571d700e2c6b10fdbf",
}

EXPECTED_FIELD_HASHES = {
    "downgrade_screen.findings": "943bc92c2cabbb0cfb2ab2d9a0ae0a6bae412ecd46595826ad9f3a78dc948f05",
    "fs_tier_report.suites": "e9ac76b884579533c7586f0b8df3256b8d62108a72341bb4fb43ffd9e928d582",
    "merged_lattice.edges": "ac405500ff5540e7deb34e1d0db0d5c71eb506507a308767806a197515c6212e",
    "merged_lattice.meta": "7c2f52c56fc0e3ce76a7d1837622017555f69d04e8e3fe42bd9e2976136217d9",
    "merged_lattice.nodes": "a08a23df2ad43825338c61bd5844ffe318e14b76d43e8adf0d75a3722f82964a",
    "revocation_lattice.revoked_suite_ids": "fc4ae1fdbb53dd0a71b886879e1227c655dbd58b5489d20e4c4925623d02d511",
    "revocation_lattice.trace": "f6f1958501f7d4109b9ffe52887f85bd66c3584392401986627809787d7cfe7f",
    "summary.hosts": "996ed88c304c18b575600b4e6fd3645953d3947ce6ead495288038e456197550",
    "summary.downgrade_finding_count": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_sha256(obj) -> str:
    blob = (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return _sha256_bytes(blob)


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing required output file: /app/audit/{name}"
        text = path.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {exc}")
        out[name] = {"text": text, "obj": obj}
    return out


class TestInputIntegrity:
    """SHA-256 guards over the frozen cipher lattice dataset."""

    def test_each_input_fixture_matches_expected_digest(self):
        """Every normative input file must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = DATA_DIR / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            assert _sha256_bytes(path.read_bytes()) == expected, f"digest mismatch: {rel}"


class TestOutputIntegrity:
    """Canonical JSON hashes for the five audit artifacts."""

    def test_output_canonical_hashes(self, loaded_outputs):
        """Parsed outputs must match the canonical SHA-256 contract."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            assert _canonical_sha256(loaded_outputs[name]["obj"]) == expected, f"hash mismatch: {name}"

    def test_field_hashes(self, loaded_outputs):
        """Key sub-objects must match their pinned canonical digests."""
        downgrade = loaded_outputs["downgrade_screen.json"]["obj"]
        merged = loaded_outputs["merged_lattice.json"]["obj"]
        fsrep = loaded_outputs["fs_tier_report.json"]["obj"]
        rev = loaded_outputs["revocation_lattice.json"]["obj"]
        summary = loaded_outputs["summary.json"]["obj"]

        checks = {
            "downgrade_screen.findings": downgrade["findings"],
            "fs_tier_report.suites": fsrep["suites"],
            "merged_lattice.edges": merged["edges"],
            "merged_lattice.meta": merged["meta"],
            "merged_lattice.nodes": merged["nodes"],
            "revocation_lattice.revoked_suite_ids": rev["revoked_suite_ids"],
            "revocation_lattice.trace": rev["trace"],
            "summary.hosts": summary["hosts"],
            "summary.downgrade_finding_count": summary["downgrade_finding_count"],
        }
        for dotted, payload in checks.items():
            assert _canonical_sha256(payload) == EXPECTED_FIELD_HASHES[dotted], dotted


class TestDowngradeScreen:
    """Downgrade sentinel pattern coverage."""

    def test_sentinel_before_strong_fs_pattern_recorded(self, loaded_outputs):
        """The documented sentinel-before-strong-fs pattern must appear."""
        findings = loaded_outputs["downgrade_screen.json"]["obj"]["findings"]
        patterns = {row["pattern"] for row in findings}
        assert "sentinel_before_strong_fs" in patterns
        hosts = {row["host_id"] for row in findings}
        assert "edge-ams-01" in hosts
        assert "edge-sin-06" in hosts


class TestFsTierReport:
    """Forward secrecy tier co-worsening when CBC families remain revoked."""

    def test_gcm_tls13_effective_tier_worsens_when_guard_holds(self, loaded_outputs):
        """gcm_tls13 suites must reflect the co-worsen ladder while others stay put."""
        rows = {row["suite_id"]: row for row in loaded_outputs["fs_tier_report.json"]["obj"]["suites"]}
        for sid in (
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384",
            "TLS_CHACHA20_POLY1305_SHA256",
        ):
            row = rows[sid]
            assert row["base_tier"] == "T1"
            assert row["effective_tier"] == "T2"
        rsa = rows["TLS_RSA_WITH_AES_128_CBC_SHA"]
        assert rsa["base_tier"] == "T3"
        assert rsa["effective_tier"] == "T3"
        ecdhe = rows["TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"]
        assert ecdhe["base_tier"] == "T2"
        assert ecdhe["effective_tier"] == "T2"


class TestMergedLattice:
    """Lattice merge respects active suite membership and edge filtering."""

    def test_nodes_sorted_and_include_expected_ids(self, loaded_outputs):
        """Active nodes must be sorted and include the fixture union."""
        nodes = loaded_outputs["merged_lattice.json"]["obj"]["nodes"]
        ids = [row["suite_id"] for row in nodes]
        assert ids == sorted(ids)
        expected = {
            "TLS_AES_128_GCM_SHA256",
            "TLS_AES_256_GCM_SHA384",
            "TLS_CHACHA20_POLY1305_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
            "TLS_RSA_WITH_AES_128_CBC_SHA",
        }
        assert set(ids) == expected

    def test_edges_sorted_lexicographically(self, loaded_outputs):
        """Lattice edges follow weak-then-strong lexicographic ordering."""
        edges = loaded_outputs["merged_lattice.json"]["obj"]["edges"]
        keys = [(edge["weak"], edge["strong"]) for edge in edges]
        assert keys == sorted(keys)


class TestRevocationLattice:
    """Incident trace cardinality and final revocation set."""

    def test_final_revoked_set_contains_only_expected_cbc_suite(self, loaded_outputs):
        """Only the fixture CBC suite remains revoked after the ledger."""
        revoked = loaded_outputs["revocation_lattice.json"]["obj"]["revoked_suite_ids"]
        assert revoked == ["TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA"]

    def test_trace_length_matches_applied_incidents(self, loaded_outputs):
        """Every in-window incident row must produce a trace entry."""
        trace = loaded_outputs["revocation_lattice.json"]["obj"]["trace"]
        assert len(trace) == 4


class TestSummary:
    """Host cap ranks and grease counters."""

    def test_summary_counts_align_with_outputs(self, loaded_outputs):
        """Cross-check summary counters against merged and downgrade outputs."""
        summary = loaded_outputs["summary.json"]["obj"]
        merged = loaded_outputs["merged_lattice.json"]["obj"]
        downgrade = loaded_outputs["downgrade_screen.json"]["obj"]
        assert summary["active_suite_count"] == merged["meta"]["active_suite_count"]
        assert summary["edge_count"] == merged["meta"]["edge_count"]
        assert summary["downgrade_finding_count"] == len(downgrade["findings"])
        assert summary["revoked_suite_count"] == len(
            loaded_outputs["revocation_lattice.json"]["obj"]["revoked_suite_ids"]
        )

    def test_anchor_files_list_is_sorted(self, loaded_outputs):
        """Anchor file paths must be lexicographically sorted."""
        anchors = loaded_outputs["summary.json"]["obj"]["anchor_files"]
        assert anchors == sorted(anchors)
