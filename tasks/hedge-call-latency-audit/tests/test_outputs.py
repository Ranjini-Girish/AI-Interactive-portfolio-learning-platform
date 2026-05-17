"""Behavioral tests for the hedge call latency audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HCL_DATA_DIR", "/app/hedgecalls"))
AUDIT_DIR = Path(os.environ.get("HCL_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "call_verdicts.json",
    "compromise_report.json",
    "hedge_budget.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "5090c4f9c6eda03400abcb53e37f67eebc0b78bc7a6a593e935162aa6c1d4fc8",
    "anchors/a1.txt": "335d8eb9a624dc897898bbbff64c779b738f4f21088af8c89a4e424b30773b56",
    "anchors/a2.txt": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "calls/hc-b01.json": "80cf0e006a04edb8bb120bc4abadcfd9d8ac970ed82272ac4c0f8e3349084981",
    "calls/hc-b02.json": "c591c7723cc2fbd2e08d82938974b4ab7f837ed413bf72cce135e514494012f9",
    "calls/hc-err.json": "7d0a4ba599b1fcdef6ba2cd0af2bd417c1256cb99104888ad48354a367711d4e",
    "calls/hc-g01.json": "ef13c01fe7c43bb15a635d0447371890bbc6effd5ba0b30450ed75db05269a80",
    "calls/hc-g02.json": "6eb2c795ac7e4af5127ab330ac1619997ca094342228aa24855a5cf3daefda1c",
    "calls/hc-g03.json": "db6885609255654cde7d404dd76f77074f05e8c35822f88b3243b493a7585990",
    "calls/hc-g04.json": "cdd90de5a04a922d7efbb80db6619d892b9e121c9d721c76579bfe11eb6b13dc",
    "calls/hc-g05.json": "bf3a5f1469629419c5dd4b8bfac33a36fe986fa507ca21b9b79594ffd4dc03e2",
    "calls/hc-g06.json": "6249b5f7258d742c06fa4270223ba0fe8320ae5865d89db00524125dc4ee254a",
    "calls/hc-s01.json": "219035ca575288b5bc27be73fae6b1517f0e86175f2211eb4ea3d0f7b6952192",
    "calls/hc-s02.json": "94ff520298512c24c1c5b606b83af0f6791f28eb0df3247809707b25c61b702c",
    "calls/hc-s03.json": "4b781d6bdce5933d15c48dda1b3135afcc8fc6745e1fa70ba020c7686fcd47a2",
    "calls/hc-x01.json": "674686fd7b10403971ff06f544935db9cfdc963c60f558afcf35d7ca0e8472ac",
    "calls/hc-x02.json": "3e13893a618c72d32653dd8e741e9bcf6b4d183ac32d7c3b829ef41585a12f3d",
    "incidents.json": "47a2eabf389565c3ad51981ad3d75599d144b8dff63a0aa65c7334603fc6bf71",
    "ledger/lane.json": "0aa4aeeb41f19b7af1cda74ffcb32486b9f786c31bd99e07486c2d40a16e1ffd",
    "ledger/tag.json": "a515956717967bf2ce4531f69c7c880aa4b2dc82626c02ec23d6d3e0acab174e",
    "overrides/o1_delay.json": "d4c9913ac6a8146c50503fc4417f6ca38590640956c3ffb88510f926d9ed2188",
    "overrides/o2_budget.json": "9a230df9b8bc9961212d234007e34af36c22fae5de4bfae937f2663fb520e9f1",
    "policy.json": "c3b8fd9b37daabb21d8a3651bb7f1e332a120bb8da1dceaae9bc8757f3d2e582",
    "pool_state.json": "345e36a96968b803c4f99f34768ca5c5702e2f5ce5e7cda1eaf72e23b9424b53",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "call_verdicts.json": "6012f09fdcc3ffe2379c66492ed4bdd09109f4ef9475a9ecb9b4bb5417d51701",
    "compromise_report.json": "1b1acca9f38c269f7460ff6cf59f576ce9d1977d08f91e842ea9289feb1dbad2",
    "hedge_budget.json": "dd435324fb3dc4e1e636f7df2a8d3fac13e4e2d599b97d50caa09f000b6f6a58",
    "incident_journal.json": "d517f5504cdb661aa57f249b7227349c21ef1510e8912e9fa20c8da7bb991428",
    "summary.json": "8599e46f52d71b80b6ade54e600fcacff61c74e925b1f8c09257def540b1140a",
}

EXPECTED_FIELD_HASHES = {
    "call_verdicts.calls": "c8f51d3055929a1826d8b9adbc04384a86170211aa8ed84fe5055da13be0ae43",
    "summary.verdict_counts": "f1c6c79751403f6356ee7d0886b9a80393f70870a29ec1917cb5f275bfa62492",
    "hedge_budget.tiers": "a1987a4db28daf6519e1ef3189de908f58a17dd8e7f5709229798b2445bfa296",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _int_from_any(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _reference_audit(data_dir: Path) -> dict[str, object]:
    """Independent re-derivation from SPEC.md semantics."""
    policy = _load_json(data_dir / "policy.json")
    pool = _load_json(data_dir / "pool_state.json")
    incidents = _load_json(data_dir / "incidents.json")

    bump = {t: 0 for t in ("bronze", "gold", "silver")}
    credit = {t: 0 for t in ("bronze", "gold", "silver")}
    ov_dir = data_dir / "overrides"
    if ov_dir.is_dir():
        for name in sorted(p.name for p in ov_dir.glob("*.json")):
            raw = _load_json(ov_dir / name)
            for tier, val in raw.get("delay_bump_ms", {}).items():
                bump[str(tier)] += int(val)
            for tier, val in raw.get("budget_credit", {}).items():
                credit[str(tier)] += int(val)

    disabled_roots: set[str] = set()
    disabled_calls: set[str] = set()
    accepted: list[dict[str, object]] = []
    ignored: list[dict[str, object]] = []

    supported = set(policy["supported_incident_kinds"])
    current_day = int(pool["current_day"])

    for ev in incidents.get("events", []):
        kind = str(ev.get("kind", ""))
        day = _int_from_any(ev.get("day", 0))
        eid = str(ev.get("event_id", ""))
        accepted_flag = bool(ev.get("accepted", True))
        scope = ev.get("scope") or {}
        reason = None
        if not accepted_flag:
            reason = "accepted_false"
        elif day > current_day:
            reason = "future_day"
        elif kind not in supported:
            reason = "unsupported_kind"
        if reason:
            ignored.append({"day": day, "event_id": eid, "kind": kind, "reason": reason})
            continue
        accepted.append(ev)
        if kind == "hedge_compromise":
            if "correlation_root" in scope:
                disabled_roots.add(str(scope["correlation_root"]))
            if "call_id" in scope:
                disabled_calls.add(str(scope["call_id"]))
        elif kind == "force_budget_credit":
            tier = str(scope["service_tier"])
            credit[tier] = credit.get(tier, 0) + int(scope["credit"])
        elif kind == "hedge_delay_bump":
            tier = str(scope["service_tier"])
            bump[tier] = bump.get(tier, 0) + int(scope["bump_ms"])

    anchor_dir = data_dir / "anchors"
    if anchor_dir.is_dir():
        for name in sorted(p.name for p in anchor_dir.glob("*.txt")):
            for line in (anchor_dir / name).read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "hedge_disabled":
                    disabled_calls.add(parts[0])

    calls: list[dict[str, object]] = []
    for name in sorted(p.name for p in (data_dir / "calls").glob("*.json")):
        calls.append(_load_json(data_dir / "calls" / name))
    calls.sort(key=lambda c: str(c["call_id"]))

    delay_base = policy["hedge_delay_ms_per_tier"]
    budget_base = policy["hedge_budget_per_window"]
    sla = policy["sla_max_ms_per_tier"]
    tier_used = {t: 0 for t in ("bronze", "gold", "silver")}
    tier_cap = {
        t: int(budget_base[t]) + int(credit.get(t, 0)) for t in ("bronze", "gold", "silver")
    }
    tier_delay = {
        t: int(delay_base[t]) + int(bump.get(t, 0)) for t in ("bronze", "gold", "silver")
    }

    rows: list[dict[str, object]] = []
    hedge_fired_total = 0
    verdict_counts = {
        "error": 0,
        "hedge_budget_exhausted": 0,
        "hedge_disabled": 0,
        "met_sla": 0,
        "missed_sla": 0,
    }

    for call in calls:
        cid = str(call["call_id"])
        root = str(call.get("correlation_root") or cid)
        tier = str(call["service_tier"])
        status = str(call["status"])
        primary = call.get("primary_latency_ms")
        hedge_lat = call.get("hedge_latency_ms")
        disabled = cid in disabled_calls or root in disabled_roots

        row: dict[str, object] = {
            "call_id": cid,
            "correlation_root": root,
            "effective_latency_ms": None,
            "hedge_fired": False,
            "hedge_latency_ms": hedge_lat,
            "latency_source": None,
            "primary_latency_ms": primary,
            "service_tier": tier,
            "verdict": "",
        }

        if status == "error":
            row["verdict"] = "error"
            verdict_counts["error"] += 1
            rows.append(row)
            continue

        if disabled:
            row["verdict"] = "hedge_disabled"
            if status == "success":
                row["effective_latency_ms"] = int(primary)
                row["latency_source"] = "primary"
            verdict_counts["hedge_disabled"] += 1
            rows.append(row)
            continue

        delay = tier_delay[tier]
        trigger = hedge_lat is not None and (
            (status == "success" and int(primary) > delay)
            or status == "primary_timeout"
        )

        if trigger and tier_used[tier] >= tier_cap[tier]:
            row["verdict"] = "hedge_budget_exhausted"
            if status == "success":
                row["effective_latency_ms"] = int(primary)
                row["latency_source"] = "primary"
            verdict_counts["hedge_budget_exhausted"] += 1
            rows.append(row)
            continue

        if trigger:
            row["hedge_fired"] = True
            tier_used[tier] += 1
            hedge_fired_total += 1
            h = int(hedge_lat)
            if status == "success":
                eff = min(int(primary), h)
                row["effective_latency_ms"] = eff
                row["latency_source"] = "hedge" if eff == h else "primary"
            else:
                row["effective_latency_ms"] = h
                row["latency_source"] = "hedge"
        elif status == "success":
            row["effective_latency_ms"] = int(primary)
            row["latency_source"] = "primary"

        eff = row["effective_latency_ms"]
        if eff is None:
            row["verdict"] = "missed_sla"
            verdict_counts["missed_sla"] += 1
        elif int(eff) <= int(sla[tier]):
            row["verdict"] = "met_sla"
            verdict_counts["met_sla"] += 1
        else:
            row["verdict"] = "missed_sla"
            verdict_counts["missed_sla"] += 1
        rows.append(row)

    tiers_out: dict[str, object] = {}
    for t in ("bronze", "gold", "silver"):
        tiers_out[t] = {
            "budget_cap": tier_cap[t],
            "budget_credit": credit.get(t, 0),
            "delay_bump_ms": bump.get(t, 0),
            "effective_delay_ms": tier_delay[t],
            "hedges_fired": tier_used[t],
        }

    return {
        "call_verdicts.json": {"calls": rows, "window_ms": policy["window_ms"]},
        "compromise_report.json": {
            "disabled_call_ids": sorted(disabled_calls),
            "disabled_correlation_roots": sorted(disabled_roots),
        },
        "hedge_budget.json": {"tiers": tiers_out, "window_ms": policy["window_ms"]},
        "incident_journal.json": {
            "accepted": sorted(accepted, key=lambda e: (_int_from_any(e["day"]), str(e["event_id"]))),
            "ignored": sorted(ignored, key=lambda e: (_int_from_any(e["day"]), str(e["event_id"]))),
        },
        "summary.json": {
            "calls_total": len(rows),
            "hedge_fired_total": hedge_fired_total,
            "service_tiers": ["bronze", "gold", "silver"],
            "verdict_counts": verdict_counts,
            "window_ms": policy["window_ms"],
        },
    }


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
def reference() -> dict[str, object]:
    """Recompute expected outputs from bundled inputs."""
    return _reference_audit(DATA_DIR)


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
        cv = outputs["call_verdicts.json"]
        assert isinstance(cv, dict)
        assert (
            _sha256_bytes(_canonical(cv["calls"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["call_verdicts.calls"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["verdict_counts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.verdict_counts"]
        )

        hb = outputs["hedge_budget.json"]
        assert isinstance(hb, dict)
        assert (
            _sha256_bytes(_canonical(hb["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["hedge_budget.tiers"]
        )

    def test_reference_matches_outputs(self, outputs: dict[str, object], reference: dict[str, object]) -> None:
        """Emitted artifacts must equal the independent reference re-derivation."""
        for name in OUTPUT_FILES:
            assert _canonical(outputs[name]) == _canonical(reference[name]), name


class TestCallOrdering:
    """Deterministic ordering rules on call verdict rows."""

    def test_calls_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`calls` must list rows in ascending ASCII `call_id` order."""
        rows = outputs["call_verdicts.json"]["calls"]
        assert isinstance(rows, list)
        ids = [str(r["call_id"]) for r in rows]
        assert ids == sorted(ids)


class TestVerdictSemantics:
    """Spot-check calls that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], cid: str) -> dict[str, object]:
        rows = outputs["call_verdicts.json"]["calls"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("call_id") == cid:
                return r
        raise AssertionError(f"missing call row {cid}")

    def test_hedge_wins_minimum_on_hc_g01(self, outputs: dict[str, object]) -> None:
        """`hc-g01` fires a hedge and records the faster hedge latency."""
        r = self._row(outputs, "hc-g01")
        assert r["hedge_fired"] is True
        assert r["effective_latency_ms"] == 70
        assert r["latency_source"] == "hedge"
        assert r["verdict"] == "met_sla"

    def test_primary_finishes_before_delay_on_hc_g02(self, outputs: dict[str, object]) -> None:
        """`hc-g02` is anchor-disabled and never fires a hedge despite a hedge sample."""
        r = self._row(outputs, "hc-g02")
        assert r["verdict"] == "hedge_disabled"
        assert r["hedge_fired"] is False
        assert r["effective_latency_ms"] == 40

    def test_compromise_root_disables_hc_x01(self, outputs: dict[str, object]) -> None:
        """`hc-x01` shares compromised root batch-x and is hedge_disabled."""
        r = self._row(outputs, "hc-x01")
        assert r["verdict"] == "hedge_disabled"
        assert r["hedge_fired"] is False

    def test_budget_exhausted_on_hc_g06(self, outputs: dict[str, object]) -> None:
        """`hc-g06` would hedge but gold budget is already exhausted."""
        r = self._row(outputs, "hc-g06")
        assert r["verdict"] == "hedge_budget_exhausted"
        assert r["hedge_fired"] is False
        assert r["effective_latency_ms"] == 130

    def test_error_call_on_hc_err(self, outputs: dict[str, object]) -> None:
        """`hc-err` with status error maps to verdict error."""
        r = self._row(outputs, "hc-err")
        assert r["verdict"] == "error"
        assert r["effective_latency_ms"] is None

    def test_timeout_without_hedge_path_on_hc_s03(self, outputs: dict[str, object]) -> None:
        """`hc-s03` primary_timeout without hedge_latency_ms is missed_sla."""
        r = self._row(outputs, "hc-s03")
        assert r["verdict"] == "missed_sla"
        assert r["hedge_fired"] is False
        assert r["effective_latency_ms"] is None

    def test_bronze_delay_bump_from_incident(self, outputs: dict[str, object]) -> None:
        """Bronze effective delay includes the accepted hedge_delay_bump incident."""
        tiers = outputs["hedge_budget.json"]["tiers"]
        assert isinstance(tiers, dict)
        bronze = tiers["bronze"]
        assert isinstance(bronze, dict)
        assert int(bronze["effective_delay_ms"]) == 150
        assert int(bronze["delay_bump_ms"]) == 30


class TestCompromiseReport:
    """Compromise and anchor disabled sets."""

    def test_batch_x_root_disabled(self, outputs: dict[str, object]) -> None:
        """Compromise incident disables correlation root batch-x."""
        rep = outputs["compromise_report.json"]
        assert isinstance(rep, dict)
        roots = rep["disabled_correlation_roots"]
        assert isinstance(roots, list)
        assert "batch-x" in roots

    def test_anchor_call_disabled(self, outputs: dict[str, object]) -> None:
        """Anchor line disables hc-g02 individually."""
        rep = outputs["compromise_report.json"]
        calls = rep["disabled_call_ids"]
        assert isinstance(calls, list)
        assert "hc-g02" in calls


class TestIncidentJournal:
    """Incident acceptance and rejection reasons."""

    def test_three_accepted_events(self, outputs: dict[str, object]) -> None:
        """Three incidents are accepted for the current pool day."""
        journal = outputs["incident_journal.json"]
        accepted = journal["accepted"]
        assert isinstance(accepted, list)
        assert len(accepted) == 3

    def test_ignored_reasons_cover_fixture(self, outputs: dict[str, object]) -> None:
        """Rejected incidents include accepted_false, future_day, and unsupported_kind."""
        journal = outputs["incident_journal.json"]
        ignored = journal["ignored"]
        assert isinstance(ignored, list)
        reasons = {str(row["reason"]) for row in ignored}
        assert reasons == {"accepted_false", "future_day", "unsupported_kind"}


class TestSummaryTotals:
    """Summary counters reconcile with call rows."""

    def test_hedge_fired_total(self, outputs: dict[str, object]) -> None:
        """Seven hedges fire across gold, silver, and bronze tiers."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert int(sm["hedge_fired_total"]) == 7

    def test_verdict_count_keys_sorted(self, outputs: dict[str, object]) -> None:
        """Summary verdict_counts keys are sorted lexicographically."""
        counts = outputs["summary.json"]["verdict_counts"]
        assert isinstance(counts, dict)
        assert list(counts.keys()) == sorted(counts.keys())
