"""Verifier suite for wagon-escort-schedule-audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WESA_DATA_DIR", "/app/escort"))
AUDIT_DIR = Path(os.environ.get("WESA_AUDIT_DIR", "/app/schedule"))
SRC_DIR = Path(os.environ.get("WESA_SRC_DIR", "/app/src"))
BIN_PATH = Path(os.environ.get("WESA_BIN_PATH", "/app/bin/escort-scheduler"))

OUTPUT_FILES = (
    "convoy_risk.json",
    "guard_assignments.json",
    "route_verdict.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "8782f699af61137c39551d02f17a8703a25d79a7cbe99b493633c1b1cc72ec33",
    "convoys/c-alpha.json": "6ef467ee85c7f19b43714b7df6b416697fb54d58b961ee995909e9806bab4428",
    "convoys/c-beta.json": "bb67a2e8b6364d7f35fcd83ffb56b68a933ed65b5296936cee528c03fb61a3b2",
    "convoys/c-delta.json": "d01488a8ed5c30bf3d7e4f658dac22d955f6b0eaf47a974f3fc2be8e5a728648",
    "convoys/c-epsilon.json": "3917e7a8c7c25c2dccef676bf6e0cba571105aefe23709484300c0ddaca76b6f",
    "convoys/c-eta.json": "86e7e8db3dc233a819a7bd38aaf598e450eb0227af22317057876dc5b71986db",
    "convoys/c-gamma.json": "25c2e74d4320a62478000c40e22fa6eef4af2793ace9fbb34bd05243593a8592",
    "convoys/c-iota.json": "fa1a554fd85f368b4fb1b050756a3b1b8ebc1042cebb323af2b2aeefbf835e86",
    "convoys/c-kappa.json": "5e5d6ac53010755cb3c269ce1493d9ebac52854601bcc38cf6a06e3c3e0a7438",
    "convoys/c-theta.json": "f6df70030fe2e54ce9fcf3284f74f7a97188b8a70606a3ec4f1c4601502a844e",
    "convoys/c-zeta.json": "ba5a85483d607c72bd8cc887543e4604ba3aee573b351fe1a25c3f39fc8d9826",
    "depots/d-east.json": "b8b19c5c850d95b26aff26a41e1959fee7f884c5c28e22efff622ea4eca0f015",
    "depots/d-north.json": "7dc8bee4b3f4fc8ffe529f257c35c8627c23b181808826df0472cef2261b4b50",
    "depots/d-south.json": "ac0148e32dd8e9c2caa64f103c348046077a636eb468e68fbb2042bd9c03f397",
    "depots/d-west.json": "f5c23204ab1339e4872c923b3ef743a7a88c772f127818e1d87dec1c1a084864",
    "guards/g01.json": "0d5378e64c2cf5e84ec88a075049bdb9ff932195247d605e6398ddd7f0bc6d1f",
    "guards/g02.json": "3290bf8e6ae99bdd0d024f6bce1a2ebb056fe5f10ed218262943098e661b5dd8",
    "guards/g03.json": "d3a4ae25339c79f3a6e2bd07ca5bc3a23a67d5c483994673d5b3cbab77de51c4",
    "guards/g04.json": "ac93c82cd7c89ab93c9b014966621e7d96a5d91d40009d7672cc8f2db1dd26cd",
    "guards/g05.json": "e122bc5f72457c375881f1789d03ae7dde1ec0780d0b9e87e060f573daf8b529",
    "guards/g06.json": "cf582692c53d9edc2214f300cb5d2549835d12743c65a752bf9f26f102b6ea22",
    "guards/g07.json": "7847110dd97315dc6213554c5f22c92e32e2bb3cbb04da009860c487bf4afb2d",
    "guards/g08.json": "d913aefef508fd82c3c2a2cc62bf7c04c23ef04f8a993272eaf57aa59246122a",
    "guards/g09.json": "d4ea2ab046dbc44ae36bc5fe561a4c30bee973c328a017fcb6e828dd9c02ad9e",
    "guards/g10.json": "1b8942fdbef8ce12344033ce78ae61adca0781b5494ceb82779901756f122dd8",
    "incident_log.json": "1b222bf5fb061c704dfeaf2b9f09961694137c2100e42bd5ba75bf68646f6f1f",
    "meta/notes.txt": "81dc542c71a60fa76929bfae4dc3c5d28b1fcfebd0a350a2c0509d29f0710d4e",
    "meta/version.json": "0d1a31d596a8b580b87082abc8d8f0c7b961f43e1c79de216012355f6d54fc5f",
    "policy.json": "929dcd60c7a6d730220bec1716de25baafff56e77ca845f86047b7d0f621deb1",
    "pool_state.json": "77068f0d531d4a4181587f1560021558ce2558b1f1df55d5f47e8462e6b7dc28",
    "routes/r-east.json": "a9c546ea5fd6c4750948140e0fcfaf2e173b14be52da55081b2ecae68fbbcac9",
    "routes/r-loop.json": "3309bb25438aae3f4077de764c3bd98f0059672ac9aed4327e2c190633431b52",
    "routes/r-mid.json": "5a7a9dbc4f18ca16a983e9580ebb026a231cd02458d064a915078502e26e558a",
    "routes/r-north.json": "4d175730af981fe23ab3b71f0f1ea6ae425616838e117c905cad1744d944190a",
    "routes/r-south.json": "4b7d6566a15a44db9ee704304f2ccde9aca55b5698fc9c758648d1805e1be777",
    "routes/r-west.json": "6f98b037c3efdb9d1613ba6c47815b558044fda6945ca58dc92bfdbb31e7cb7a",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "convoy_risk.json": "c289baaf44765d7f6e99f66f3a0b19b49e509716a7c7a511b32449b1ba5955cc",
    "guard_assignments.json": "763c28b00034daaf610e1523d67696199de1c342217cc2dea485f76a6fe8a938",
    "route_verdict.json": "8c4d5d41b2f41bc6c35502aab465eae8fbc4ea9eff09d62dbcb54c0d3713bad3",
    "incident_journal.json": "5af80fca1a9b9962d4bcda271eb5bd080256421abff4643531fbbc5757185268",
    "summary.json": "8d8666dd6aab8114c65cae9fee42162f7a49954646b511cc8ad6551e289a8a44",
}

EXPECTED_FIELD_HASHES = {
    "convoy_risk.convoys": "5864d8da431577554892ce59536799d34c96e503854707860b3e86f37622bbc9",
    "guard_assignments.convoys": "176a15a122abcc907c2db0f98c956df60e97fcc6f6f26d3af847d496e6fd8eb5",
    "incident_journal.applied_events": "2fbc22a27ac7848a51d21a1d5ab4f3600e47c6d6fe92c04d38d661fa85beef46",
    "route_verdict.routes": "39a035f46a906b3decdb4868bc06ad21c85d945fc37eeda5ac504f80e853fdee",
    "summary.blocked_routes": "4e07408562bedb8b60ce05c1decfe3ad16b72230967de01f640b7e4729b49fce",
    "summary.fully_assigned_convoys": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
    "summary.route_embargo_active": "b5bea41b6c623f7c09f1bf24dcae58ebab3c0cdd90ad966bc43a45b44867e12b",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_dir_json(data_dir: Path, sub: str) -> dict[str, object]:
    out: dict[str, object] = {}
    base = data_dir / sub
    for path in sorted(base.glob("*.json")):
        out[path.stem] = _load_json(path)
    return out


def _event_ok(ev: dict, current_day: int, supported: set[str]) -> bool:
    if ev.get("accepted") is not True:
        return False
    day = ev.get("day")
    if not isinstance(day, int) or day > current_day:
        return False
    kind = ev.get("kind")
    if not isinstance(kind, str) or kind not in supported:
        return False
    if kind == "hazard_spike":
        return isinstance(ev.get("route_id"), str) and isinstance(ev.get("delta"), int)
    if kind == "depot_closure":
        return isinstance(ev.get("depot_id"), str) and isinstance(ev.get("effective_day"), int)
    if kind == "guard_bench":
        return isinstance(ev.get("guard_id"), str)
    if kind == "route_embargo":
        rids = ev.get("route_ids")
        return isinstance(rids, list) and all(isinstance(x, str) for x in rids)
    return False


def _compute_reference(data_dir: Path) -> dict[str, object]:
    """Independent re-derivation of all schedule outputs from the normative spec."""
    ps = _load_json(data_dir / "pool_state.json")
    policy = _load_json(data_dir / "policy.json")
    il = _load_json(data_dir / "incident_log.json")
    current_day = int(ps["current_day"])
    cooldown = int(policy["guard_cooldown_days"])
    supported = set(policy["supported_incident_kinds"])

    routes = _load_dir_json(data_dir, "routes")
    depots = _load_dir_json(data_dir, "depots")
    guards = _load_dir_json(data_dir, "guards")
    convoys_raw = _load_dir_json(data_dir, "convoys")
    convoys = sorted(convoys_raw.values(), key=lambda c: c["convoy_id"])

    route_delta = {rid: 0 for rid in routes}
    depot_limit = {did: int(d["active_until"]) for did, d in depots.items()}
    benched: set[str] = set()
    spike_routes: set[str] = set()
    embargo_routes: set[str] = set()
    applied: list[dict] = []

    kept = [e for e in il["events"] if _event_ok(e, current_day, supported)]
    ignored = len(il["events"]) - len(kept)
    kept.sort(key=lambda e: (e["day"], e["event_id"]))

    for ev in kept:
        kind = ev["kind"]
        row: dict = {"day": ev["day"], "event_id": ev["event_id"], "kind": kind}
        if kind == "hazard_spike":
            route_delta[ev["route_id"]] += ev["delta"]
            spike_routes.add(ev["route_id"])
            row["delta"] = ev["delta"]
            row["route_id"] = ev["route_id"]
        elif kind == "depot_closure":
            limit = ev["effective_day"] - 1
            depot_limit[ev["depot_id"]] = min(depot_limit.get(ev["depot_id"], limit), limit)
            row["depot_id"] = ev["depot_id"]
            row["effective_day"] = ev["effective_day"]
        elif kind == "guard_bench":
            benched.add(ev["guard_id"])
            row["guard_id"] = ev["guard_id"]
        elif kind == "route_embargo":
            embargo_routes.update(ev["route_ids"])
            row["route_ids"] = sorted(ev["route_ids"])
        applied.append(row)

    risk_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}

    def classify(raw: int, tier: str) -> str:
        th = policy["risk_thresholds_by_tier"][tier]
        if raw < th["medium"]:
            return "low"
        if raw < th["high"]:
            return "medium"
        if raw < th["critical"]:
            return "high"
        return "critical"

    def covered(route_id: str, departure_day: int) -> bool:
        for did in routes[route_id]["depot_ids"]:
            if depot_limit.get(did, -1) >= departure_day:
                return True
        return False

    risk_rows = []
    covered_count = 0
    for c in convoys:
        rid = c["route_id"]
        tier = c["tier"]
        dep_day = int(c["departure_day"])
        raw = sum(
            int(seg["base_hazard"]) + route_delta.get(rid, 0)
            for seg in routes[rid]["segments"]
        )
        raw = max(0, raw - int(policy["hazard_decay_by_tier"][tier]))
        is_cov = covered(rid, dep_day)
        if is_cov:
            covered_count += 1
        reasons: list[str] = []
        if not is_cov:
            raw = (raw * int(policy["uncovered_multiplier_pct_by_tier"][tier])) // 100
            reasons.append("uncovered_route")
        if rid in spike_routes:
            reasons.append("hazard_spike_active")
        level = classify(raw, tier)
        if rid in embargo_routes:
            if risk_rank[level] < risk_rank["high"]:
                level = "high"
            reasons.append("route_embargo")
        reasons = sorted(set(reasons))
        risk_rows.append(
            {
                "convoy_id": c["convoy_id"],
                "departure_day": dep_day,
                "raw_hazard": raw,
                "risk_level": level,
                "reasons": reasons,
                "route_id": rid,
                "tier": tier,
            }
        )
    risk_rows.sort(key=lambda r: r["convoy_id"])

    eligible = sorted(
        [g for gid, g in guards.items() if gid not in benched],
        key=lambda g: (-int(g["skill"]), g["guard_id"]),
    )
    sched = sorted(convoys, key=lambda c: (int(c["departure_day"]), c["convoy_id"]))
    guard_last_day: dict[str, int] = {}
    guard_last_convoy: dict[str, str] = {}
    assign_rows = []
    fully_assigned = 0
    for c in sched:
        cid = c["convoy_id"]
        req = int(c["required_guards"])
        dep_day = int(c["departure_day"])
        if c["route_id"] in embargo_routes:
            assign_rows.append(
                {
                    "assigned_guard_ids": [],
                    "assignment_status": "blocked_escort",
                    "convoy_id": cid,
                    "required_guards": req,
                }
            )
            continue
        picked: list[str] = []
        for g in eligible:
            if len(picked) >= req:
                break
            gid = g["guard_id"]
            if gid in guard_last_day:
                d0 = guard_last_day[gid]
                if guard_last_convoy[gid] != cid and abs(dep_day - d0) <= cooldown:
                    continue
            picked.append(gid)
        picked.sort()
        if req == 0:
            status = "unassigned"
        elif len(picked) == req:
            status = "assigned"
            fully_assigned += 1
        elif len(picked) == 0:
            status = "unassigned"
        else:
            status = "partial"
        for gid in picked:
            guard_last_day[gid] = dep_day
            guard_last_convoy[gid] = cid
        assign_rows.append(
            {
                "assigned_guard_ids": picked,
                "assignment_status": status,
                "convoy_id": cid,
                "required_guards": req,
            }
        )
    assign_rows.sort(key=lambda r: r["convoy_id"])

    route_ids = sorted({c["route_id"] for c in convoys})
    verdict_rows = []
    blocked_routes = 0
    for rid in route_ids:
        risks = [
            r["risk_level"]
            for r in risk_rows
            if r["route_id"] == rid and r["departure_day"] <= current_day
        ]
        max_risk = max(risks, key=lambda x: risk_rank[x]) if risks else "low"
        if rid in embargo_routes:
            verdict = "blocked"
            reasons = ["route_embargo"]
        elif max_risk == "critical":
            verdict = "blocked"
            reasons = ["critical_risk"]
        elif max_risk == "high":
            verdict = "diverted"
            reasons = ["high_risk"]
        else:
            verdict = "cleared"
            reasons = []
        if verdict == "blocked":
            blocked_routes += 1
        verdict_rows.append({"reasons": reasons, "route_id": rid, "verdict": verdict})

    journal = sorted(applied, key=lambda e: (e["day"], e["event_id"]))
    summary = {
        "applied_incident_events": len(journal),
        "blocked_routes": blocked_routes,
        "convoys_total": len(convoys),
        "covered_convoys": covered_count,
        "embargo_routes": len(embargo_routes),
        "fully_assigned_convoys": fully_assigned,
        "ignored_incident_events": ignored,
        "route_embargo_active": len(embargo_routes) > 0,
        "uncovered_convoys": len(convoys) - covered_count,
    }
    return {
        "convoy_risk.json": {"convoys": risk_rows},
        "guard_assignments.json": {"convoys": assign_rows},
        "route_verdict.json": {"routes": verdict_rows},
        "incident_journal.json": {"applied_events": journal},
        "summary.json": summary,
    }


@pytest.fixture(scope="session")
def outputs() -> dict[str, object]:
    """Load emitted schedule artifacts once per session."""
    payload: dict[str, object] = {}
    for name in OUTPUT_FILES:
        path = AUDIT_DIR / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


@pytest.fixture(scope="session")
def reference_outputs() -> dict[str, object]:
    """Recompute expected schedule JSON from the frozen escort fixtures."""
    return _compute_reference(DATA_DIR)


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
        """Each schedule file must match the canonical minified JSON digest."""
        for name, expected in EXPECTED_OUTPUT_CANONICAL_HASHES.items():
            canon = _canonical(outputs[name])
            digest = _sha256_bytes(canon.encode("utf-8"))
            assert digest == expected, f"output mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        cr = outputs["convoy_risk.json"]
        assert isinstance(cr, dict)
        assert (
            _sha256_bytes(_canonical(cr["convoys"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["convoy_risk.convoys"]
        )
        ga = outputs["guard_assignments.json"]
        assert isinstance(ga, dict)
        assert (
            _sha256_bytes(_canonical(ga["convoys"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["guard_assignments.convoys"]
        )
        ij = outputs["incident_journal.json"]
        assert isinstance(ij, dict)
        assert (
            _sha256_bytes(_canonical(ij["applied_events"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["incident_journal.applied_events"]
        )
        rv = outputs["route_verdict.json"]
        assert isinstance(rv, dict)
        assert (
            _sha256_bytes(_canonical(rv["routes"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["route_verdict.routes"]
        )
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        for key in (
            "blocked_routes",
            "fully_assigned_convoys",
            "route_embargo_active",
        ):
            field = f"summary.{key}"
            assert (
                _sha256_bytes(_canonical(sm[key]).encode("utf-8"))
                == EXPECTED_FIELD_HASHES[field]
            )


class TestReferenceAgreement:
    """Emitted artifacts must match an independent spec re-derivation."""

    def test_convoy_risk_matches_reference(
        self, outputs: dict[str, object], reference_outputs: dict[str, object]
    ) -> None:
        """Convoy hazard rows must equal the independently recomputed schedule."""
        assert outputs["convoy_risk.json"] == reference_outputs["convoy_risk.json"]

    def test_guard_assignments_match_reference(
        self, outputs: dict[str, object], reference_outputs: dict[str, object]
    ) -> None:
        """Guard assignment rows must equal the independently recomputed schedule."""
        assert outputs["guard_assignments.json"] == reference_outputs["guard_assignments.json"]

    def test_route_verdict_matches_reference(
        self, outputs: dict[str, object], reference_outputs: dict[str, object]
    ) -> None:
        """Route verdict rows must equal the independently recomputed schedule."""
        assert outputs["route_verdict.json"] == reference_outputs["route_verdict.json"]

    def test_incident_journal_matches_reference(
        self, outputs: dict[str, object], reference_outputs: dict[str, object]
    ) -> None:
        """Applied incident journal must equal the independently recomputed schedule."""
        assert outputs["incident_journal.json"] == reference_outputs["incident_journal.json"]

    def test_summary_matches_reference(
        self, outputs: dict[str, object], reference_outputs: dict[str, object]
    ) -> None:
        """Summary counters must equal the independently recomputed schedule."""
        assert outputs["summary.json"] == reference_outputs["summary.json"]


class TestRiskLevels:
    """Exercise every documented convoy risk band in the bundled dataset."""

    def test_low_risk_convoy_present(self, outputs: dict[str, object]) -> None:
        """At least one convoy must classify as low risk."""
        levels = {r["risk_level"] for r in outputs["convoy_risk.json"]["convoys"]}
        assert "low" in levels

    def test_medium_risk_convoy_present(self, outputs: dict[str, object]) -> None:
        """At least one convoy must classify as medium risk."""
        levels = {r["risk_level"] for r in outputs["convoy_risk.json"]["convoys"]}
        assert "medium" in levels

    def test_high_risk_convoy_present(self, outputs: dict[str, object]) -> None:
        """At least one convoy must classify as high risk."""
        levels = {r["risk_level"] for r in outputs["convoy_risk.json"]["convoys"]}
        assert "high" in levels

    def test_critical_risk_convoy_present(self, outputs: dict[str, object]) -> None:
        """`c-kappa` on the loop route must reach the critical band."""
        rows = outputs["convoy_risk.json"]["convoys"]
        kappa = next(r for r in rows if r["convoy_id"] == "c-kappa")
        assert kappa["risk_level"] == "critical"


class TestAssignmentStatuses:
    """Exercise every documented guard assignment status."""

    def test_assigned_status_present(self, outputs: dict[str, object]) -> None:
        """At least one convoy must be fully assigned."""
        statuses = {r["assignment_status"] for r in outputs["guard_assignments.json"]["convoys"]}
        assert "assigned" in statuses

    def test_partial_status_present(self, outputs: dict[str, object]) -> None:
        """`c-iota` must land in the partial bucket when guard supply runs short."""
        rows = outputs["guard_assignments.json"]["convoys"]
        iota = next(r for r in rows if r["convoy_id"] == "c-iota")
        assert iota["assignment_status"] == "partial"

    def test_unassigned_status_present(self, outputs: dict[str, object]) -> None:
        """Zero-guard convoys must report unassigned."""
        rows = outputs["guard_assignments.json"]["convoys"]
        theta = next(r for r in rows if r["convoy_id"] == "c-theta")
        assert theta["assignment_status"] == "unassigned"

    def test_blocked_escort_status_present(self, outputs: dict[str, object]) -> None:
        """Embargoed routes must block escort assignment."""
        rows = outputs["guard_assignments.json"]["convoys"]
        beta = next(r for r in rows if r["convoy_id"] == "c-beta")
        assert beta["assignment_status"] == "blocked_escort"


class TestRouteVerdicts:
    """Exercise every documented route verdict value."""

    def test_cleared_verdict_present(self, outputs: dict[str, object]) -> None:
        """At least one route must clear."""
        verdicts = {r["verdict"] for r in outputs["route_verdict.json"]["routes"]}
        assert "cleared" in verdicts

    def test_diverted_verdict_present(self, outputs: dict[str, object]) -> None:
        """`r-north` must divert on high convoy risk without embargo."""
        rows = outputs["route_verdict.json"]["routes"]
        north = next(r for r in rows if r["route_id"] == "r-north")
        assert north["verdict"] == "diverted"

    def test_blocked_verdict_present(self, outputs: dict[str, object]) -> None:
        """Embargoed and critical routes must block."""
        rows = outputs["route_verdict.json"]["routes"]
        west = next(r for r in rows if r["route_id"] == "r-west")
        assert west["verdict"] == "blocked"


class TestCompoundTwists:
    """Spot-check interacting rules called out in the normative spec."""

    def test_hazard_spike_reason_on_north_convoy(self, outputs: dict[str, object]) -> None:
        """`c-alpha` must record the spike reason after the north-route delta applies."""
        rows = outputs["convoy_risk.json"]["convoys"]
        alpha = next(r for r in rows if r["convoy_id"] == "c-alpha")
        assert "hazard_spike_active" in alpha["reasons"]

    def test_depot_closure_uncovers_mid_route_convoy(self, outputs: dict[str, object]) -> None:
        """`c-eta` must be uncovered once the east depot closure bites before departure."""
        rows = outputs["convoy_risk.json"]["convoys"]
        eta = next(r for r in rows if r["convoy_id"] == "c-eta")
        assert "uncovered_route" in eta["reasons"]

    def test_guard_cooldown_shifts_delta_assignment(self, outputs: dict[str, object]) -> None:
        """Cooldown must keep high-skill guards off back-to-back convoys within the window."""
        rows = outputs["guard_assignments.json"]["convoys"]
        delta = next(r for r in rows if r["convoy_id"] == "c-delta")
        assert delta["assigned_guard_ids"] == ["g06", "g07"]

    def test_route_embargo_crosscuts_three_outputs(self, outputs: dict[str, object]) -> None:
        """Embargo on `r-west` must flip risk, assignment, and route verdict together."""
        risk = next(r for r in outputs["convoy_risk.json"]["convoys"] if r["convoy_id"] == "c-beta")
        assign = next(
            r for r in outputs["guard_assignments.json"]["convoys"] if r["convoy_id"] == "c-beta"
        )
        route = next(r for r in outputs["route_verdict.json"]["routes"] if r["route_id"] == "r-west")
        assert "route_embargo" in risk["reasons"]
        assert assign["assignment_status"] == "blocked_escort"
        assert route["verdict"] == "blocked"


class TestImplementationLanguage:
    """The task requires a Go binary that reproduces the schedule from fixtures."""

    def test_go_source_present(self) -> None:
        """`/app/src/` must contain a buildable `package main` Go tree."""
        assert SRC_DIR.is_dir(), f"{SRC_DIR} must exist and contain Go source"
        go_files = list(SRC_DIR.rglob("*.go"))
        assert go_files, f"no .go files found under {SRC_DIR}"
        has_main = any(
            re.search(r"^\s*package\s+main\b", gf.read_text(encoding="utf-8"), re.MULTILINE)
            for gf in go_files
        )
        assert has_main, f"no Go file under {SRC_DIR} declares 'package main'"

    def test_binary_present(self) -> None:
        """`/app/bin/escort-scheduler` must exist as an executable artifact."""
        assert BIN_PATH.is_file(), f"{BIN_PATH} must exist"
        assert os.access(BIN_PATH, os.X_OK), f"{BIN_PATH} must be executable"

    def test_binary_reproduces_schedule(self) -> None:
        """A fresh binary run must reproduce the on-disk schedule byte-for-byte."""
        import tempfile

        backup = None
        if AUDIT_DIR.exists():
            backup = Path(tempfile.mkdtemp())
            shutil.move(str(AUDIT_DIR), str(backup / "schedule"))
        try:
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env["WESA_DATA_DIR"] = str(DATA_DIR)
            env["WESA_AUDIT_DIR"] = str(AUDIT_DIR)
            res = subprocess.run([str(BIN_PATH)], capture_output=True, text=True, env=env, timeout=120)
            assert res.returncode == 0, res.stderr
            for name in OUTPUT_FILES:
                canon = _canonical(_load_json(AUDIT_DIR / name))
                digest = _sha256_bytes(canon.encode("utf-8"))
                assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES[name], name
        finally:
            if backup is not None:
                if AUDIT_DIR.exists():
                    shutil.rmtree(AUDIT_DIR)
                shutil.move(str(backup / "schedule"), str(AUDIT_DIR))
                shutil.rmtree(backup)
