"""Behavioral tests for the tls-cert-chain-auditor task.

These tests assert the agent's outputs against the documented contract in
``instruction.md`` and ``/app/certs/SPEC.md``. Hash-locked anti-cheat
fixtures are computed independently from the input data and compared
against the agent's emitted JSON files; an agent cannot pass these tests
by writing arbitrary or hand-tweaked output.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("TLS_DATA_DIR", "/app/certs"))
AUDIT_DIR = Path(os.environ.get("TLS_AUDIT_DIR", "/app/audit"))

REQUIRED_OUTPUT_FILES = [
    "chain_audit.json",
    "expiry_report.json",
    "ocsp_summary.json",
    "ca_risk.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "SPEC.md":                                                   "892ee490c6f7c2c46abd2d838f2a3bfdc05b3651da95327c388d49fbd3167f23",
    "chain_config.json":                                         "6c9d6f9f366a880336fae5c1b10d0b3af7a13b99421666b2e933a6218992d274",
    "incident_log.json":                                         "07f1e8ed722e66b4d9f3d64b9710dec9d1ed97d6162775c3f47263ab8f15bf1f",
    "ocsp_responses.json":                                       "2f4073f4a215d630fe158fef99fdd3841c5047ba924f94a5945036ad324ca69a",
    "pool_state.json":                                           "cb7407fb08999e9118ce059c3125314591168f15c6a7422325f58d1286e40a60",
    "intermediates/int-asia-1.json":                             "81b671f6742715e7d9536b50438e6ec68bbe00c354609946aab66480a99ce2ca",
    "intermediates/int-eu-1-sub.json":                           "abc7e2af93a9cea343caec05d84013ea32b20886139d16e6523ed816f07c873c",
    "intermediates/int-eu-1.json":                               "042c35185e534e7984f21fc2985f5428c879c7af702bdd81059d843082523bdd",
    "intermediates/int-us-1.json":                               "ee50e87e58de9196e28450d193ea1855373a5efd5ad8ac199025930cd107e72f",
    "intermediates/int-us-2.json":                               "48f7a927b527f71517beca97dd7c9d74c4e5ac82638e42138a28a31198dbc8a8",
    "leafs/leaf-api-v1.json":                                    "4e1d1abe1a452aa556f93456ac9656a4e023f80deba1fdddd88c97537a983d4d",
    "leafs/leaf-cdn-v1.json":                                    "5f5755d242dda12974502e92bc8847796982491a65f4bcf9285e694be437df4c",
    "leafs/leaf-edge-v1.json":                                   "f093b3e29be68f955eb8930384e593e06099f158f5105586b03734ea1453fd24",
    "leafs/leaf-internal-v1.json":                               "b361b0486f9359b57b1d1ffe024ba9a00f3383ccaebc522470332ab014cefbf5",
    "leafs/leaf-internal-v2.json":                               "aa34d17c1e2faebb433b480caac470bf7c02a7387dba69b0e53cb0aafb6b92af",
    "leafs/leaf-legacy-v1.json":                                 "9f40c1e2e79ae79b24ebc1497d5aecfca860ee862855f6ad198e5d3cfd3b37d4",
    "leafs/leaf-ops-v1.json":                                    "81406d6f51ae21462f4b4b87f48d2353c6e8148b0d006f1e28a9ce6188404f09",
    "leafs/leaf-revoked-v1.json":                                "c4fa69aa03fa54a0c22ccb71f7c51833812c9a4f96d2d707a9603f5b1e4b6925",
    "leafs/leaf-shop-v1.json":                                   "4eeb30317e6478d88b79803c5027e505ded115f98c69792b351e09dc46eafe83",
    "leafs/leaf-staging-v1.json":                                "0699eb09f8e00236774fca0b934cc82d47f9f79a165cadf292dc98ce89805d8c",
    "leafs/leaf-staging-v2.json":                                "719dd578e4084e241ccbd86924f1d34f6018880963bb61debfbdfc11be35bf75",
    "domains/internal/internal-app.example.lan.json":            "0c292f0a4301661e4b65de66b878acade877cfca1605c1a7f982c931545bce27",
    "domains/internal/internal-tools.example.lan.json":          "4980f7e2064a23c05ae47e05322351d7dd3de401ccd573f8f5a174ac74db672a",
    "domains/production/api.example.com.json":                   "757e4fcbfbf421759e1e0d15d6657aef35771b734428ed0cde35de925b8c7bad",
    "domains/production/cdn.example.com.json":                   "7552e26369f7d80ebc5b67834fa57b6b554539525e1473634f0a7d357a916442",
    "domains/production/edge.example.com.json":                  "a1a1d6bef2e5b291e1512112a6c3bd7eec2764e35e7c5ce2b874f8337e5f19bd",
    "domains/production/legacy.example.org.json":                "d7f4b93d5b988814df3f576f3366a3d68f8bdf761a0fc7cebb1e19e7508817c6",
    "domains/production/ops.example.io.json":                    "aa994d9b3b29018b3e0b9e372700bee30ce206f87c704f62b17af6b099682ca9",
    "domains/production/revoked-svc.example.com.json":           "e2b01de6a0213395450f103473294309ec57edc7221130004e029645ddd139a6",
    "domains/production/shop.example.net.json":                  "7a32250d8c42749956a15a86fdca53171103c7be3ac7fe34d6a19ba643f14be3",
    "domains/staging/staging-app.example.com.json":              "f06f71c19f44682b9188fe0a20bf494618ebfa7650cf90150f19db0d28bfc599",
    "domains/staging/staging.example.com.json":                  "93bac54b8707b5b466401e6692505acc28f2eeac35307da4d82bbaac8a2d0b92",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "chain_audit.json":   "ea33d6d2941ec38fab528bc85058b58efa32dc75abcb47426ddf5bfffcd98483",
    "expiry_report.json": "bc7a49ae7eb5fb293fe26e47831efe5b05a4e6f681444368181a9144ef13a700",
    "ocsp_summary.json":  "bd3b7b63ef0285325234d04b5bbdc9abe63e5de8a4fad9f45ac6f6b8d42068fa",
    "ca_risk.json":       "f0cc2e55120697cce74b5dbe812dc059356a8509753ff44334b813ba73d5fbed",
    "summary.json":       "176deb35372cba315e8128f9d50e0991935aea7a4176415a97cddbd01923210b",
}

EXPECTED_FIELD_HASHES = {
    "chain_audit.domains":      "9552b2dc70f0d11d9a06ed894f6b0dd3b62eb123e46a4ae3333e68f3f28ad6c2",
    "expiry_report.buckets":    "74fe2f0cfcc317da51b1a91d2cc2ff6d87c11cc95534daac7cc36882dba1ea44",
    "ocsp_summary.details":     "3c6f84549422fd6fbb61e61219e02d2a36430a18e1442052ef09e270c9ba63ba",
    "ca_risk.intermediates":    "7d6f3e6ef92ce023d0d1b43d4a2ce2ec7a17c4a7f347c7d11883bbbe33c77bb3",
    "summary.by_verdict":       "26ba61d281a60fe608cce1882eecbf54390a62554a5ebc80d27c3b1ddc429ef7",
    "summary.by_ocsp_state":    "ea1c14496d15cd8b4566703e3724c3e40669eb4e8fb2abf823de272b0ff22669",
    "summary.compromised_cas":  "9af690fa8ca2f502f5cdbe5c20b8cd4a05b3a9947fc06a7fa6656c7e4aedd0ce",
}


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _canonical_bytes(obj) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _canonical_sha256(obj) -> str:
    return _sha256_bytes(_canonical_bytes(obj))


@pytest.fixture(scope="module")
def loaded_outputs():
    out = {}
    for name in REQUIRED_OUTPUT_FILES:
        p = AUDIT_DIR / name
        assert p.is_file(), f"missing required output file: /app/audit/{name}"
        text = p.read_text(encoding="utf-8")
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            pytest.fail(f"output /app/audit/{name} is not valid JSON: {e}")
        out[name] = {"text": text, "obj": obj, "bytes": text.encode("utf-8")}
    return out


# ---------------------------------------------------------------------------
# Input integrity
# ---------------------------------------------------------------------------


class TestInputIntegrity:
    """Inputs must remain byte-identical to the original fixtures."""

    @pytest.mark.parametrize("rel,expected", sorted(EXPECTED_INPUT_HASHES.items()))
    def test_input_unchanged(self, rel, expected):
        """Each input file's SHA-256 must match the locked baseline."""
        p = DATA_DIR / rel
        assert p.is_file(), f"input file missing: {rel}"
        actual = _sha256_bytes(p.read_bytes())
        assert actual == expected, (
            f"input file {rel} was modified (sha256 {actual} != {expected})"
        )


# ---------------------------------------------------------------------------
# Report structure & whole-output hashes
# ---------------------------------------------------------------------------


class TestReportStructure:
    """Top-level structural and canonical-hash invariants on every output."""

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_required_file_exists(self, name):
        """Each required output file must exist and be a regular file."""
        assert (AUDIT_DIR / name).is_file()

    @pytest.mark.parametrize("name", REQUIRED_OUTPUT_FILES)
    def test_output_canonical_hash(self, name, loaded_outputs):
        """Canonical SHA-256 of each output must match the locked baseline."""
        actual = _canonical_sha256(loaded_outputs[name]["obj"])
        expected = EXPECTED_OUTPUT_CANONICAL_HASHES[name]
        assert actual == expected, (
            f"{name} canonical hash mismatch: {actual} != {expected}"
        )

    def test_chain_audit_top_level(self, loaded_outputs):
        """chain_audit.json must have exactly one top-level key 'domains'."""
        assert set(loaded_outputs["chain_audit.json"]["obj"].keys()) == {"domains"}

    def test_expiry_report_top_level(self, loaded_outputs):
        """expiry_report.json must have exactly one top-level key 'buckets' with three sub-keys."""
        obj = loaded_outputs["expiry_report.json"]["obj"]
        assert set(obj.keys()) == {"buckets"}
        assert set(obj["buckets"].keys()) == {"ok", "warning", "expired"}

    def test_ocsp_summary_top_level(self, loaded_outputs):
        """ocsp_summary.json must have exactly the documented top-level keys."""
        obj = loaded_outputs["ocsp_summary.json"]["obj"]
        assert set(obj.keys()) == {"by_state", "details"}

    def test_ca_risk_top_level(self, loaded_outputs):
        """ca_risk.json must have exactly one top-level key 'intermediates'."""
        assert set(loaded_outputs["ca_risk.json"]["obj"].keys()) == {"intermediates"}

    def test_summary_top_level_keys(self, loaded_outputs):
        """summary.json must have exactly the documented top-level keys."""
        obj = loaded_outputs["summary.json"]["obj"]
        expected = {
            "current_day", "audit_version", "total_domains", "total_intermediates",
            "ignored_incident_events", "by_verdict", "by_ocsp_state", "compromised_cas",
        }
        assert set(obj.keys()) == expected


# ---------------------------------------------------------------------------
# Field-level hash gates
# ---------------------------------------------------------------------------


class TestFieldHashes:
    """Per-field canonical hashes pinpoint which output is wrong."""

    def test_chain_audit_domains_field(self, loaded_outputs):
        """chain_audit.domains must canonicalise to the locked hash."""
        v = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["chain_audit.domains"]

    def test_expiry_buckets_field(self, loaded_outputs):
        """expiry_report.buckets must canonicalise to the locked hash."""
        v = loaded_outputs["expiry_report.json"]["obj"]["buckets"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["expiry_report.buckets"]

    def test_ocsp_summary_details_field(self, loaded_outputs):
        """ocsp_summary.details must canonicalise to the locked hash."""
        v = loaded_outputs["ocsp_summary.json"]["obj"]["details"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["ocsp_summary.details"]

    def test_ca_risk_intermediates_field(self, loaded_outputs):
        """ca_risk.intermediates must canonicalise to the locked hash."""
        v = loaded_outputs["ca_risk.json"]["obj"]["intermediates"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["ca_risk.intermediates"]

    def test_summary_by_verdict_field(self, loaded_outputs):
        """summary.by_verdict must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_verdict"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_verdict"]

    def test_summary_by_ocsp_state_field(self, loaded_outputs):
        """summary.by_ocsp_state must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["by_ocsp_state"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.by_ocsp_state"]

    def test_summary_compromised_cas_field(self, loaded_outputs):
        """summary.compromised_cas must canonicalise to the locked hash."""
        v = loaded_outputs["summary.json"]["obj"]["compromised_cas"]
        assert _canonical_sha256(v) == EXPECTED_FIELD_HASHES["summary.compromised_cas"]


# ---------------------------------------------------------------------------
# Chain audit behavioural assertions
# ---------------------------------------------------------------------------


class TestChainAudit:
    """Chain-audit verdict rules covering every documented label."""

    def test_domains_sorted(self, loaded_outputs):
        """domains must be sorted by 'domain' ascending."""
        names = [d["domain"] for d in loaded_outputs["chain_audit.json"]["obj"]["domains"]]
        assert names == sorted(names)

    def test_every_domain_present(self, loaded_outputs):
        """Every declared domain must appear exactly once."""
        on_disk = []
        for tier in (DATA_DIR / "domains").iterdir():
            if not tier.is_dir():
                continue
            for fp in tier.glob("*.json"):
                on_disk.append(json.loads(fp.read_text(encoding="utf-8"))["domain"])
        out = [d["domain"] for d in loaded_outputs["chain_audit.json"]["obj"]["domains"]]
        assert sorted(out) == sorted(on_disk)

    def test_verdict_enum(self, loaded_outputs):
        """verdict must be one of the eight documented values."""
        allowed = {
            "valid", "warning", "expired", "revoked", "untrusted",
            "chain_unreachable", "compromised", "tainted",
        }
        for d in loaded_outputs["chain_audit.json"]["obj"]["domains"]:
            assert d["verdict"] in allowed

    def test_chain_starts_with_leaf(self, loaded_outputs):
        """chain[0] must equal the domain's leaf_serial."""
        leaf_by_domain = {}
        for tier in (DATA_DIR / "domains").iterdir():
            if not tier.is_dir():
                continue
            for fp in tier.glob("*.json"):
                doc = json.loads(fp.read_text(encoding="utf-8"))
                leaf_by_domain[doc["domain"]] = doc["leaf_serial"]
        for d in loaded_outputs["chain_audit.json"]["obj"]["domains"]:
            assert d["chain"][0] == leaf_by_domain[d["domain"]]

    def test_known_chain_unreachable(self, loaded_outputs):
        """A leaf with a missing intermediate yields verdict=chain_unreachable."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        edge = next(d for d in domains if d["domain"] == "edge.example.com")
        assert edge["verdict"] == "chain_unreachable"
        assert "intermediate_missing" in edge["reasons"]

    def test_known_compromised_via_key_compromise(self, loaded_outputs):
        """A leaf with an accepted key_compromise event gets verdict=compromised."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        shop = next(d for d in domains if d["domain"] == "shop.example.net")
        assert shop["verdict"] == "compromised"
        assert "key_compromise" in shop["reasons"]

    def test_known_compromised_via_ca_compromise(self, loaded_outputs):
        """A chain that visits an accepted ca_compromise serial gets verdict=compromised."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        ops = next(d for d in domains if d["domain"] == "ops.example.io")
        assert ops["verdict"] == "compromised"
        assert "ca_compromise" in ops["reasons"]

    def test_known_tainted_domain(self, loaded_outputs):
        """A chain that shares an intermediate with a compromised chain is tainted."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        st = next(d for d in domains if d["domain"] == "staging.example.com")
        assert st["verdict"] == "tainted"
        assert "ca_compromise" in st["reasons"]

    def test_known_warning_for_expiry(self, loaded_outputs):
        """A leaf within expiry_warn_days of expiration gets verdict=warning."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        cdn = next(d for d in domains if d["domain"] == "cdn.example.com")
        assert cdn["verdict"] == "warning"
        assert "expiry_warning" in cdn["reasons"]

    def test_known_revoked_domain(self, loaded_outputs):
        """A leaf with OCSP status=revoked (and no compromise) gets verdict=revoked."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        rv = next(d for d in domains if d["domain"] == "revoked-svc.example.com")
        assert rv["verdict"] == "revoked"
        assert "revoked" in rv["reasons"]

    def test_known_untrusted_via_key_size(self, loaded_outputs):
        """A leaf whose key_size is below the tier minimum gets verdict=untrusted."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        lg = next(d for d in domains if d["domain"] == "legacy.example.org")
        assert lg["verdict"] == "untrusted"
        assert "key_size_too_small" in lg["reasons"]

    def test_known_audit_review_override(self, loaded_outputs):
        """A non-compromised domain whose audit_review forces a verdict has 'audit_review_override' in reasons."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        it = next(d for d in domains if d["domain"] == "internal-tools.example.lan")
        assert it["verdict"] == "valid"
        assert "audit_review_override" in it["reasons"]

    def test_compromise_overrides_audit_review(self, loaded_outputs):
        """A compromised domain ignores audit_review even when target is 'valid'."""
        domains = loaded_outputs["chain_audit.json"]["obj"]["domains"]
        sh = next(d for d in domains if d["domain"] == "shop.example.net")
        assert sh["verdict"] == "compromised"
        assert "audit_review_override" not in sh["reasons"]

    def test_reasons_sorted(self, loaded_outputs):
        """reasons list is sorted ascending for every domain."""
        for d in loaded_outputs["chain_audit.json"]["obj"]["domains"]:
            assert d["reasons"] == sorted(d["reasons"])


# ---------------------------------------------------------------------------
# Expiry report
# ---------------------------------------------------------------------------


class TestExpiryReport:
    """Expiry buckets and per-bucket sort order."""

    def test_three_buckets_present(self, loaded_outputs):
        """buckets has exactly the three documented keys."""
        b = loaded_outputs["expiry_report.json"]["obj"]["buckets"]
        assert set(b.keys()) == {"ok", "warning", "expired"}

    def test_bucket_sort(self, loaded_outputs):
        """Each bucket is sorted by (days_to_expiry, domain) ascending."""
        for bname, blist in loaded_outputs["expiry_report.json"]["obj"]["buckets"].items():
            keys = [(e["days_to_expiry"], e["domain"]) for e in blist]
            assert keys == sorted(keys), f"bucket {bname} not sorted"

    def test_total_count_equals_domains(self, loaded_outputs):
        """The sum of all bucket sizes equals the number of domains with a known leaf."""
        total = sum(len(v) for v in loaded_outputs["expiry_report.json"]["obj"]["buckets"].values())
        leaf_serials = {p.stem for p in (DATA_DIR / "leafs").glob("*.json")}
        domains_with_leaf = 0
        for tier in (DATA_DIR / "domains").iterdir():
            if not tier.is_dir():
                continue
            for fp in tier.glob("*.json"):
                doc = json.loads(fp.read_text(encoding="utf-8"))
                if doc["leaf_serial"] in leaf_serials:
                    domains_with_leaf += 1
        assert total == domains_with_leaf


# ---------------------------------------------------------------------------
# OCSP summary
# ---------------------------------------------------------------------------


class TestOcspSummary:
    """OCSP state distribution and per-domain details."""

    def test_details_sorted(self, loaded_outputs):
        """details is sorted by 'domain' ascending."""
        names = [d["domain"] for d in loaded_outputs["ocsp_summary.json"]["obj"]["details"]]
        assert names == sorted(names)

    def test_state_enum(self, loaded_outputs):
        """ocsp_state must be one of the three documented values."""
        for d in loaded_outputs["ocsp_summary.json"]["obj"]["details"]:
            assert d["ocsp_state"] in {"valid", "revoked", "soft_fail"}

    def test_by_state_keys_complete(self, loaded_outputs):
        """by_state has all three keys."""
        assert set(loaded_outputs["ocsp_summary.json"]["obj"]["by_state"].keys()) == {
            "valid", "revoked", "soft_fail",
        }

    def test_by_state_sums_to_total_domains(self, loaded_outputs):
        """by_state values sum to the total number of domain detail entries."""
        s = loaded_outputs["ocsp_summary.json"]["obj"]
        assert sum(s["by_state"].values()) == len(s["details"])


# ---------------------------------------------------------------------------
# CA risk
# ---------------------------------------------------------------------------


class TestCaRisk:
    """CA risk per-intermediate roll-up."""

    def test_intermediates_sorted(self, loaded_outputs):
        """intermediates list is sorted by serial ascending."""
        ser = [i["serial"] for i in loaded_outputs["ca_risk.json"]["obj"]["intermediates"]]
        assert ser == sorted(ser)

    def test_intermediates_complete(self, loaded_outputs):
        """Every intermediate file appears exactly once."""
        on_disk = sorted(p.stem for p in (DATA_DIR / "intermediates").glob("*.json"))
        seen = sorted(i["serial"] for i in loaded_outputs["ca_risk.json"]["obj"]["intermediates"])
        assert seen == on_disk

    def test_compromised_flag_matches_summary(self, loaded_outputs):
        """compromised=True iff serial appears in summary.compromised_cas."""
        cas = set(loaded_outputs["summary.json"]["obj"]["compromised_cas"])
        for i in loaded_outputs["ca_risk.json"]["obj"]["intermediates"]:
            assert i["compromised"] == (i["serial"] in cas)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestSummary:
    """Summary aggregates must agree with the individual reports."""

    def test_total_domains(self, loaded_outputs):
        """total_domains equals the number of domain files on disk."""
        on_disk = sum(
            1 for tier in (DATA_DIR / "domains").iterdir() if tier.is_dir()
            for _ in tier.glob("*.json")
        )
        assert loaded_outputs["summary.json"]["obj"]["total_domains"] == on_disk

    def test_total_intermediates(self, loaded_outputs):
        """total_intermediates equals the number of files under intermediates/."""
        on_disk = sum(1 for _ in (DATA_DIR / "intermediates").glob("*.json"))
        assert loaded_outputs["summary.json"]["obj"]["total_intermediates"] == on_disk

    def test_by_verdict_keys_complete(self, loaded_outputs):
        """by_verdict has all eight documented keys."""
        d = loaded_outputs["summary.json"]["obj"]["by_verdict"]
        expected = {
            "valid", "warning", "expired", "revoked", "untrusted",
            "chain_unreachable", "compromised", "tainted",
        }
        assert set(d.keys()) == expected

    def test_by_verdict_sums_to_total_domains(self, loaded_outputs):
        """by_verdict values sum to total_domains."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_verdict"].values()) == s["total_domains"]

    def test_by_ocsp_state_sums_to_total_domains(self, loaded_outputs):
        """by_ocsp_state values sum to total_domains."""
        s = loaded_outputs["summary.json"]["obj"]
        assert sum(s["by_ocsp_state"].values()) == s["total_domains"]

    def test_compromised_cas_pass_through(self, loaded_outputs):
        """compromised_cas matches the accepted ca_compromise event serials."""
        with open(DATA_DIR / "incident_log.json", encoding="utf-8") as f:
            log = json.load(f)
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            cd = json.load(f)["current_day"]
        with open(DATA_DIR / "chain_config.json", encoding="utf-8") as f:
            roots = set(json.load(f)["trusted_roots"])
        inter_set = {p.stem for p in (DATA_DIR / "intermediates").glob("*.json")}
        accepted = sorted({
            ev["serial"] for ev in log["events"]
            if ev.get("kind") == "ca_compromise"
            and isinstance(ev.get("day"), int)
            and not isinstance(ev.get("day"), bool)
            and ev["day"] <= cd
            and (ev.get("serial") in inter_set or ev.get("serial") in roots)
        })
        assert loaded_outputs["summary.json"]["obj"]["compromised_cas"] == accepted

    def test_current_day_pass_through(self, loaded_outputs):
        """summary.current_day comes from pool_state.json."""
        with open(DATA_DIR / "pool_state.json", encoding="utf-8") as f:
            ps = json.load(f)
        assert loaded_outputs["summary.json"]["obj"]["current_day"] == ps["current_day"]
        assert loaded_outputs["summary.json"]["obj"]["audit_version"] == ps["audit_version"]
