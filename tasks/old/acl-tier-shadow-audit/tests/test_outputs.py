"""Verifier suite for acl-tier-shadow-audit."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ATSA_DATA_DIR", "/app/acl_tier"))
AUDIT_DIR = Path(os.environ.get("ATSA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "effective_access.json",
    "probe_verdicts.json",
    "summary.json",
)


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "c8ba1174b0f2d5e9bdc27949fb6c07d20331fbabeb8940e53e02cd119e239080",
    "anchors/a01.txt": "e4d4f4125875016701ebdd5f276b262d21911a75c6a4ffb4b0a5b90020c85499",
    "anchors/a02.txt": "c28ea57b59cf783feb8df7da7a61f492e45c72d99ca48f217e6916fe65408dc8",
    "anchors/a03.txt": "369e97a1dfdffdc98ba028fb40fdae6a2604abf94196d58eae4a907cab90d4c2",
    "anchors/a04.txt": "1a2e4aa4db31f9d00350f35b5a8308d1e11c93926d6fc8913e50df5915954eb6",
    "anchors/a05.txt": "8ba44ce86880a24dc1d1505a65bafeb4793f4153805afe8b724e6aeb3a1398cf",
    "anchors/a06.txt": "aa6e210304ccccabaa66f81e1565607ad0810940225834e5ccbb4e70cc8ffb93",
    "anchors/a07.txt": "0d705eebcf861ed399b8e7e9ea3dc9320af948a01cadbdbb78040c01713b72ee",
    "anchors/a08.txt": "3f976e886d9a2a2e4c5bbb74f9b6d928415f3e463543e03938d37e9e0f9bf063",
    "anchors/a09.txt": "1acb4db9ef7f86c36dce54d8f0b7d08a1cbdfdb22e00526e69d84232d445a983",
    "anchors/a10.txt": "40088efd6cb76067934331ba6cfe40f7e197957f05882b603afcaeddb4cbf1ee",
    "clients/c_br.json": "98bca1d6055c8c3ad8f2b144caeec3becbe6315ffac06292b2c462863d8208e3",
    "clients/c_go.json": "e8a9591f67b8acb1a46b6724ff30a9cc9b45f307edde7b3d42ffaba839147cdb",
    "clients/c_root.json": "aa7dda5650b7df7a0260aa10aade2dc94c40e9526f79fc4a5fe27566132938f3",
    "clients/c_sl.json": "fa1197137af5ad1315a2fa0b4cde062b2899ae4499ccb52131a3500e872d6cef",
    "clients/c_x1.json": "10761bbbae55476db5ae4dfb4cc27cc8de2ca6b79da3ff84a3a7f7f1a3e0b1d1",
    "clients/c_x2.json": "eb09dfd944b5faab08f08fe7b711b59160bafe0c38d6076309e9ed56c29eb8b6",
    "clients/c_x3.json": "460da4823b59ee2d75967f34c99321b7bd380847e61300b5ff7936848ca7900d",
    "clients/c_x4.json": "5e5be783ba863450baab5e6b8572bd3239fc26d2bc6004ed83fce5f78071aa88",
    "incident_log.json": "3860d8dc62823c67f39b9acff28cbcf160fe3393002f0ffe1682e9e2fc58e97a",
    "layers/bronze.json": "15d7a1207f670dd13c990634ae3042fb0dfd54361bcdfbac668271dfa24c0c92",
    "layers/gold.json": "56d8eea77722e2cf787e871346c72242997ee8efb9c6aeea04f8b4e23d152be1",
    "layers/silver.json": "a3e816ae088e50782d00547bd7d9871fe60f52c49582d1a3e4ed8bbbb31d6ac2",
    "policy.json": "d46bc18ee2847277e6ab84fd4e2b067bcbfb05ef007a73f040f651c33b682ba2",
    "pool_state.json": "cec950bad6f7a7af6e9ef7636bac2f695a2df99f770a755ef07492e69198db0b",
}


EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "effective_access.json": "a483be9f7094ec5e01263965c5bc7620f04a5f8d0eb03b96347281c1b595442c",
    "probe_verdicts.json": "4dc4dc69deb15fb280960ee2fde8637a22ad5b94042375c75a1ec76d9937ced4",
    "summary.json": "7e6cf0db0aa1fdcff951d4455d998b468403ed004cce4c406d628ddebac144ed",
}


EXPECTED_FIELD_HASHES = {
    "effective_access.clients": "2c429754d49ce733ddd20a2a9dcf8f88423415b6416212f8b6773067d7e3b699",
    "probe_verdicts.probes": "872ecf4971df12e3cee442e71a5665c9a25adb908b64f3d4427c39b1de39f65a",
    "summary.applied_incidents": "6baebcb30d97931fcf0cae406acf6aeb7825638706231bf603fc30f19c71f673",
    "summary.quarantined_clients": "4836576b2c6163d643bcec5b5b453d1a4ee0c2d5b55b2421be58acf12594523d",
    "summary.probes_total": "e7f6c011776e8db7cd330b54174fd76f7d0216b612387a5ffcfb81e6f0919683",
    "summary.allow_probe_count": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.deny_probe_count": "4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a",
    "summary.ignored_incidents": "d4735e3a265e16eee03f59718b9b5d03019c07d8b6c51f90da3a666eec13ab35",
    "summary.clients_total": "2c624232cdd221771294dfbb310aca000a0df6ac8b66b696d90ef06fdefb64a3",
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
        """Selected nested fields and summary scalars must match pinned canonical digests."""
        eff = outputs["effective_access.json"]
        assert isinstance(eff, dict)
        assert (
            _sha256_bytes(_canonical(eff["clients"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["effective_access.clients"]
        )

        pv = outputs["probe_verdicts.json"]
        assert isinstance(pv, dict)
        assert (
            _sha256_bytes(_canonical(pv["probes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["probe_verdicts.probes"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "applied_incidents",
            "quarantined_clients",
            "probes_total",
            "allow_probe_count",
            "deny_probe_count",
            "ignored_incidents",
            "clients_total",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestOrdering:
    """Deterministic ordering rules on list outputs."""

    def test_clients_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`clients` must list rows in ascending ASCII `client_id` order."""
        rows = outputs["effective_access.json"]["clients"]
        assert isinstance(rows, list)
        ids = [str(r["client_id"]) for r in rows]
        assert ids == sorted(ids)

    def test_client_rules_sorted(self, outputs: dict[str, object]) -> None:
        """Each client's `rules` list must sort by ascending `rule_seq` then `pattern`."""
        for block in outputs["effective_access.json"]["clients"]:
            assert isinstance(block, dict)
            if block.get("quarantined"):
                assert block["rules"] == []
                continue
            rules = block["rules"]
            assert isinstance(rules, list)
            keys = [(int(r["rule_seq"]), str(r["pattern"])) for r in rules]
            assert keys == sorted(keys)


class TestProbeSemantics:
    """Spot-check distinct probe outcomes from the bundled dataset."""

    def _probe(self, outputs: dict[str, object], idx: int) -> dict[str, object]:
        probes = outputs["probe_verdicts.json"]["probes"]
        assert isinstance(probes, list)
        row = probes[idx]
        assert isinstance(row, dict)
        return row

    def test_root_probe_matches_silver_allow(self, outputs: dict[str, object]) -> None:
        """After bronze strip removes the wide deny, the silver temperature allow wins."""
        r = self._probe(outputs, 0)
        assert r["client_id"] == "c_root"
        assert r["decision"] == "allow"
        assert r["reason"] == "matched"
        assert r["matched_pattern"] == "site/ny/+/temp"
        assert r["matched_rule_seq"] == 3

    def test_quarantined_client_probe_reason(self, outputs: dict[str, object]) -> None:
        """`c_go` sits under a quarantined anchor so probes must surface the quarantine reason."""
        r = self._probe(outputs, 1)
        assert r["client_id"] == "c_go"
        assert r["decision"] == "deny"
        assert r["reason"] == "quarantined"
        assert r["matched_pattern"] is None
        assert r["matched_rule_seq"] is None

    def test_wide_bronze_deny_beats_narrow_seed(self, outputs: dict[str, object]) -> None:
        """The broad trailing wildcard deny from bronze outranks the earlier seed allow."""
        r = self._probe(outputs, 2)
        assert r["decision"] == "deny"
        assert r["matched_pattern"] == "edge/#"
        assert r["reason"] == "matched"

    def test_unknown_client_reason(self, outputs: dict[str, object]) -> None:
        """Unknown client identifiers must emit the dedicated unknown reason."""
        r = self._probe(outputs, 3)
        assert r["client_id"] == "c_nope"
        assert r["reason"] == "unknown_client"
        assert r["decision"] == "deny"

    def test_gold_literal_allow_wins_stack(self, outputs: dict[str, object]) -> None:
        """Gold literal allow overrides broader vault patterns for the same topic."""
        r = self._probe(outputs, 4)
        assert r["client_id"] == "c_x4"
        assert r["decision"] == "allow"
        assert r["matched_pattern"] == "vault/a/read/status"
        assert r["matched_rule_seq"] == 3

    def test_default_deny_when_no_rule_matches(self, outputs: dict[str, object]) -> None:
        """Topics that match no stored pattern must fall through to default deny."""
        r = self._probe(outputs, 5)
        assert r["client_id"] == "c_x2"
        assert r["reason"] == "default_deny"
        assert r["matched_pattern"] is None


class TestSummarySemantics:
    """Counters in summary must stay internally consistent."""

    def test_summary_incident_ids(self, outputs: dict[str, object]) -> None:
        """Applied incident identifiers are the two eligible control-plane events."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["applied_incidents"] == ["e01", "e02"]

    def test_quarantine_list_matches_spec_subtree(self, outputs: dict[str, object]) -> None:
        """Quarantine from `c_br` reaches its shadow descendants only."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert sm["quarantined_clients"] == ["c_br", "c_go", "c_sl", "c_x1"]

    def test_probe_counters_sum(self, outputs: dict[str, object]) -> None:
        """Allow and deny probe counts must sum to the probe list length."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert int(sm["allow_probe_count"]) + int(sm["deny_probe_count"]) == int(
            sm["probes_total"]
        )
