"""Behavioral tests for the rate limit merge audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("JRMA_DATA_DIR", "/app/rate_merge_lab"))
AUDIT_DIR = Path(os.environ.get("JRMA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "service_limits.json",
    "incident_journal.json",
    "host_summary.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "240f213604574f0252bc8a010efacc69db79763ffffb126da8fc7348b5c46ee9",
    "classes/legacy.json": "a6b28800527127904a416a3c4d0b6f4a662b7e98b5759b6eb00403fc003103ea",
    "classes/standard.json": "66a5def5af487b2dc90daa0a43fbbec2aba32260a24a7656cc16c1d2b459137d",
    "dropins/d1.json": "208d0d34e539c2e95eb758081bc4419becee530a0dd88267e7246a3aefcb260b",
    "dropins/d2.json": "7d273c9a71e49aa91067131f7da16dd05d863b6d465a60f6d38bd116704cf965",
    "dropins/d3.json": "3e617cdeb649780cec763aef2a746369575206182c8d401e8f00a792d9465a19",
    "dropins/d4.json": "0759ea754aaff12b5a444e7b2429075e3c127c934d1c4ff81fbf7ffb023b4416",
    "dropins/d5.json": "e8004dbe54d570ffa98d4e71a7383674b487bfe84c09d6e6111fdb4aa9fec37e",
    "hosts/h-east.json": "bb4cb3c80983ba3833d028badd21bcfec343a38303b00d29c5c4c4a91017aa73",
    "hosts/h-south.json": "7df771f73c24bfb6901e8d2b0a01120f5d402520fb4b01b55b34d29272fdadcf",
    "hosts/h-west.json": "7d733b2a2c8169c77ceb43c5677362ba33eb6e69df514ecceeb4984ad1f2e4b4",
    "incident_log.json": "27bc63ee4019d97f21990f3f3c15cdcff0aa2f40f34bd85a11af1e65d9bcf780",
    "pool_state.json": "0944500037569150b88467b5c924cb42c79b4ca85bf63c447780f4f327521fa6",
    "units/u-alpha.json": "8cfeba68715d8069ee4b6bc7fcb8d39eb28553dceca3c33a5ee533befeb87cf9",
    "units/u-beta.json": "5ce89c6ea9aa91eb5db646f343d50bf76bedafc8612db0d9763adade438c476b",
    "units/u-delta.json": "a3d404525bd1ece25a19e4cc7cfbe3bd267eb7e87d23bddf0fa87efe2dc93cb0",
    "units/u-epsilon.json": "5c97c347638358b438e6ff89b28ff06031d44c5d7ceac2292f2b89cdfde19dac",
    "units/u-gamma.json": "cbd3ed373b0c443b2f64bac527a6dd99b172c7811a5258806534dd35036dcd52",
    "units/u-iota.json": "ce9a00c682c3cdc804b8bd7364d4853a6a44e3ed90d3bd35a28cafbf6ffe0efe",
    "units/u-kappa.json": "53daed10bd920ec86243ba562879d50246d1f1a4e2e6f09678bee78673e3103a",
    "units/u-omega.json": "fc12b6c13b750767f37bea057854ee6673f3c6e5155e6335b3455a05ad031071",
    "units/u-theta.json": "af750116d0be62e45c2d9557ea859ea5e22330dec7cea20463ce760976625404",
    "units/u-zeta.json": "ae10ffab4f9f9a80560b8e95b0b2cb8350b7ced5341f03517b759de9eb90ab8d",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "host_summary.json": "b38910cb08c87c7cade3f6faddf3d26b345385f3d185ab5991be3b2c529bb6db",
    "incident_journal.json": "9fcc5c0a283d89bfea0e95ff3897b5e09502481ede40c7ea2f9fd28c1ab8b861",
    "service_limits.json": "b6d6080b561b27f3c12e5ef51b468631f085ce32c6178ef4588eda5ae9307823",
    "summary.json": "7e9d87662244ea983e7d30ebad7ce61f5fab10a5c30b944cf8a8bd665154d2cd",
}


EXPECTED_FIELD_HASHES = {
    "host_summary.hosts": "cd9de66854e293a7b047f1636f48fcbe1b83d58f2666e1751bb5abd6fba52fc6",
    "incident_journal.applied_events": (
        "5649846c3b39576c203ca9c109fca9d3f559079ca79ba7ced5212fb511433826"
    ),
    "service_limits.services": "1e76861395a81ab54bfb533b8cb0620ebca27f1ce18ba023f11b02b5ab4e0623",
    "summary.applied_incident_events": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.compromised_hosts": "6b86b273ff34fce19d6b804eff5a3f5747ada4eaa22f1d49c01e52ddb7875b4b",
    "summary.ignored_incident_events": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.legacy_units": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.max_burst_across_services": (
        "ad57366865126e55649ecb23ae1d48887544976efea46a48eb5d85a6eeb4d306"
    ),
    "summary.min_interval_across_services": (
        "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a"
    ),
    "summary.services_total": "4a44dc15364204a80fe80e9039455cc1608281820fe2b24f1e5233ade6af1dd5",
    "summary.standard_units": "7902699be42c8a8e46fbbb4501726517e86b22c56a189f7625a6da49081b2451",
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

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        sl = outputs["service_limits.json"]
        assert isinstance(sl, dict)
        assert (
            _sha256_bytes(_canonical(sl["services"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["service_limits.services"]
        )

        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )

        hs = outputs["host_summary.json"]
        assert isinstance(hs, dict)
        assert (
            _sha256_bytes(_canonical(hs["hosts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["host_summary.hosts"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incident_events",
            "compromised_hosts",
            "ignored_incident_events",
            "legacy_units",
            "max_burst_across_services",
            "min_interval_across_services",
            "services_total",
            "standard_units",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestCompromiseQuarantine:
    """Rules that tie host compromise to quarantine floors."""

    def test_h_east_services_mark_compromised_host(self, outputs: dict[str, object]) -> None:
        """Every unit on the compromised host must report compromised_host true."""
        sl = outputs["service_limits.json"]
        assert isinstance(sl, dict)
        svcs = sl["services"]
        assert isinstance(svcs, list)
        for row in svcs:
            assert isinstance(row, dict)
            if row.get("host_id") == "h-east":
                assert row.get("compromised_host") is True
                assert row.get("interval_sec") == 4
                assert row.get("burst") == 40

    def test_non_compromised_host_respects_max_burst(self, outputs: dict[str, object]) -> None:
        """South host max_burst 55 caps u-zeta and u-omega after ceiling step."""
        sl = outputs["service_limits.json"]
        assert isinstance(sl, dict)
        by_id = {r["service_id"]: r for r in sl["services"] if isinstance(r, dict)}
        assert by_id["u-zeta"]["burst"] == 55
        assert by_id["u-omega"]["burst"] == 55


class TestLegacyDropinOrder:
    """Legacy merge order differs from standard for overlapping keys."""

    def test_legacy_beta_dropins_applied_reverse_list_order(self, outputs: dict[str, object]) -> None:
        """u-beta lists drop-ins in application order d2 then d1 per SPEC for legacy."""
        sl = outputs["service_limits.json"]
        assert isinstance(sl, dict)
        by_id = {r["service_id"]: r for r in sl["services"] if isinstance(r, dict)}
        beta = by_id["u-beta"]
        assert beta["unit_class"] == "legacy"
        assert beta["dropins_applied"] == ["d2.json", "d1.json"]

    def test_standard_alpha_forward_order(self, outputs: dict[str, object]) -> None:
        """u-alpha applies drop-ins forward d1 then d2."""
        sl = outputs["service_limits.json"]
        assert isinstance(sl, dict)
        by_id = {r["service_id"]: r for r in sl["services"] if isinstance(r, dict)}
        assert by_id["u-alpha"]["dropins_applied"] == ["d1.json", "d2.json"]


class TestIncidentKindsPresent:
    """Positive coverage for each incident kind in the frozen log."""

    def test_applied_events_include_all_documented_kinds(self, outputs: dict[str, object]) -> None:
        """Applied stream must contain burst_add, interval_mult, host_compromise, burst_ceiling."""
        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        evs = ij["applied_events"]
        assert isinstance(evs, list)
        kinds = {e.get("kind") for e in evs if isinstance(e, dict)}
        assert kinds == {"burst_add", "burst_ceiling", "host_compromise", "interval_mult"}


class TestHostSummary:
    """Host rollups align with unit placement."""

    def test_h_west_lists_four_services_sorted(self, outputs: dict[str, object]) -> None:
        """h-west groups four western units in ascending service_id order."""
        hs = outputs["host_summary.json"]
        assert isinstance(hs, dict)
        west = hs["hosts"]["h-west"]
        assert isinstance(west, dict)
        assert west["service_ids"] == ["u-delta", "u-gamma", "u-kappa", "u-theta"]
