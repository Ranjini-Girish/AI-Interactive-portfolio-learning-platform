"""Behavioral tests for the replica lag window audit task."""

from __future__ import annotations

import hashlib
import json
import os
from collections import defaultdict, deque
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("RLA_DATA_DIR", "/app/replag"))
AUDIT_DIR = Path(os.environ.get("RLA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "shard_profiles.json",
    "dependency_plan.json",
    "flush_plan.json",
    "incident_trace.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "9d6c9e3272ef5cf79ec4785b909fa6ba679f7a2d884feb6bc0b6373f5f0937d4",
    "anchors/a1.txt": "8df2c7a078641bb9e41a65daab75ae215aa1fbd7feca2958f7cb97fab59f5e1c",
    "anchors/a2.txt": "1044062d699dbe27ebdbf4404e0049605962d812b53dc6ba436acc5c17f7c8b4",
    "anchors/a3.txt": "dcac498516c0a83445e4ebe2c80209f282910fa52eee36d6813cda6918e6fb31",
    "dependencies.json": "fe82188d0e487b40de3fc1f3b0e356e50be4d0ecfaaa2d3429466f6bbeef443a",
    "incidents.json": "bf44766c1fe7d347d52f8d5f011340ea91be65f86722f1685473811708dfdd89",
    "ledger/seq.json": "b804dc15b82b8ff63caf5362e9a4b9097a1bbef9c1dfbe33f5f18a613963dfa4",
    "ledger/tag.json": "058b2c58d21f47e8a884d901b0d024f22c12b2b6c1fd6d6a0085d1e954095bc8",
    "policy.json": "a1cb4397109ce0cc3bbc4adbd1524d8c2d50b3115fe7ddec8c9ef442ec7aa3a9",
    "pool_state.json": "d53ca9ef5325da5e8c61b30aa284a8217a7c89b63d76021a321b7417f0e51094",
    "shards/sh-bronze-ok.json": "da6c2938e3b098103ee105bfa408e1a2498cbc142fbc4fdd7d9aceb5e6d84739",
    "shards/sh-bronze-outlier.json": "7d807d1354af481f91907011f31b15335d528f76463f62ba875910c85a99f719",
    "shards/sh-bronze-warn.json": "d424df2d559a1198c4811f153de30c1b063b6ad8ee024907e2d2c774a300fffd",
    "shards/sh-child.json": "d43566c96f848fe4554e8388f241e604a14934e35dd2de845bfee32ab7194e25",
    "shards/sh-cycle-a.json": "df79357859af14e62fb7a62bf060250b33f1f212a0ed42fd0a0ef67c8ab1933b",
    "shards/sh-cycle-b.json": "a06a5b91d062157191d3f41a5b8c56dc797fc77fc7dbcd086eb2f29a3eaeacf3",
    "shards/sh-embargo.json": "d2802f85f32b1a392e32b7408e14add845ed22106c6e5cfe0f6f0a268f695e4f",
    "shards/sh-frozen.json": "6bccbab588b9b464e8b6e00d5c42728370c6efbc522beef2829ab87f242b5ef2",
    "shards/sh-gold-crit.json": "c67e2bdbbdd3a1f078632526c9375ecf25be17bf95ab0fd091ed602031e40b93",
    "shards/sh-gold-ok.json": "d34d27bcb7aa27cf5caf943393b48e52075426de44d6dfb20be7e6deda7bf07a",
    "shards/sh-grace.json": "b50c90b0e67f691f33f9ff18159fa54522792991152a90f6800c5600c90df7d5",
    "shards/sh-parent.json": "7ce2037f51d5f57a217125cbff79ac7337f5341bfbafb701029b39e9745cb673",
    "shards/sh-silver-warn.json": "c3d1d16695861e4c348f9c8c1c5a1027e3420a253ba0a62902ba169af0cf6d8d",
    "shards/sh-witness.json": "a2fdbc7480f0d59233c382ea07c45202fe440df01665c6795f6af0e64a6c2e96",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "shard_profiles.json": "183d194223daa494e37f45ba4eebe22ef9b3197804986c85f8cc0b29557f1752",
    "dependency_plan.json": "86460a75f7bb47f7cc582d46ef7fc1dde7139d063e8a316e466a55564aec3828",
    "flush_plan.json": "7145a5b840db13eaecc9c2d50df90e6a5b653cfdf51798b92d808ff75a9ed1be",
    "incident_trace.json": "5fdd21e0b5c4cb213c80bfc3a8d179488648746c8a99edc687defefcf7f44f77",
    "summary.json": "835b92b4298cd937943d8b3db6ac12b2223dc968fd30eba61101a7598ce9aec6",
}

EXPECTED_FIELD_HASHES = {
    "dependency_plan.order": "8dc0ae72e8e948e1df1dd390b2b8ea524688cf6afadf32b890179dcc03a8c761",
    "shard_profiles.profiles": "f38d0f5d0f3bd1346da3410e76ef8979cd9b833ff93ef05f2122dad3e93536ed",
    "summary.tiers": "825934503e904174270b7c0a60dc12107cc774933f9763908e4439fe1a2faae5",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _spec_json_file_text(value: object) -> str:
    """Serialize exactly as SPEC.md canonical JSON (two-space indent, sorted keys, ASCII, one trailing LF)."""
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ": "),
        )
        + "\n"
    )


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _median_int(vals: list[int]) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) // 2


def _effective_lag(samples: list[dict], k: int, reject_ratio: float) -> int:
    ordered = sorted(samples, key=lambda x: (x["day"],))
    window = ordered[-k:] if len(ordered) > k else ordered
    lags = [int(s["lag_bytes"]) for s in window]
    med = _median_int(lags)
    if med == 0:
        kept = lags
    else:
        thresh = reject_ratio * med
        kept = [v for v in lags if abs(v - med) <= thresh]
    if not kept:
        return 0
    return _median_int(kept)


def _compute_reference() -> dict[str, object]:
    """Independent re-derivation from SPEC.md and bundled inputs."""
    policy = _load_json(DATA_DIR / "policy.json")
    pool = _load_json(DATA_DIR / "pool_state.json")
    deps = _load_json(DATA_DIR / "dependencies.json")
    incidents = _load_json(DATA_DIR / "incidents.json")
    current_day = int(pool["current_day"])
    k = int(policy["median_window_k"])
    reject_ratio = float(policy["median_reject_ratio"])
    grace_days = int(policy["grace_days_after_failover"])
    witness_skew = int(policy["witness_skew_bytes"])
    thresholds = policy["tier_thresholds"]

    shard_ids: list[str] = []
    shards: dict[str, dict] = {}
    for path in sorted((DATA_DIR / "shards").glob("*.json")):
        obj = _load_json(path)
        sid = str(obj["shard_id"])
        shard_ids.append(sid)
        shards[sid] = obj

    parents: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    for edge in deps.get("edges", []):
        p, c = str(edge["parent"]), str(edge["child"])
        if p in shards and c in shards:
            parents[c].append(p)
            children[p].append(c)
    for key in parents:
        parents[key] = sorted(parents[key])
    for key in children:
        children[key] = sorted(children[key])

    embargoed: set[str] = set()
    failover_day: dict[str, int] = {}
    forced: dict[str, str] = {}
    frozen: set[str] = set()
    applied: list[dict] = []

    events = sorted(
        [e for e in incidents.get("events", []) if int(e["day"]) <= current_day],
        key=lambda e: (int(e["day"]), str(e["shard_id"])),
    )
    for ev in events:
        sid = str(ev["shard_id"])
        kind = str(ev["kind"])
        day = int(ev["day"])
        if sid not in shards:
            continue
        if kind == "embargo_downstream":
            queue = deque([sid])
            seen: set[str] = set()
            while queue:
                node = queue.popleft()
                if node in seen:
                    continue
                seen.add(node)
                embargoed.add(node)
                queue.extend(children.get(node, []))
            applied.append(
                {"day": day, "effect": "embargo", "kind": kind, "shard_id": sid}
            )
        elif kind == "failover":
            failover_day[sid] = day
            applied.append(
                {"day": day, "effect": "failover", "kind": kind, "shard_id": sid}
            )
        elif kind == "force_lag_verdict":
            forced[sid] = str(ev["forced_verdict"])
            applied.append(
                {"day": day, "effect": "force", "kind": kind, "shard_id": sid}
            )
        elif kind == "freeze_shard":
            frozen.add(sid)
            applied.append(
                {"day": day, "effect": "freeze", "kind": kind, "shard_id": sid}
            )

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str) -> None:
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)
        for w in children.get(v, []):
            if w not in shards:
                continue
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])
        if lowlink[v] == indices[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.remove(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1:
                sccs.append(sorted(comp))

    for sid in sorted(shard_ids):
        if sid not in indices:
            strongconnect(sid)
    cycles_sorted = sorted(sccs, key=lambda c: c[0])
    cycle_nodes = {n for comp in sccs for n in comp}

    profiles: dict[str, dict] = {}
    for sid in shard_ids:
        sh = shards[sid]
        eff = _effective_lag(sh["samples"], k, reject_ratio)
        tier = str(sh["tier"])
        ordered = sorted(sh["samples"], key=lambda x: (x["day"],))
        latest = ordered[-1]
        wdesync = (
            int(latest["witness_lag_bytes"]) - int(latest["lag_bytes"]) > witness_skew
        )
        grace_active = False
        if sid in failover_day:
            f = failover_day[sid]
            grace_active = current_day <= f + grace_days - 1
        t = thresholds[tier]
        if eff < t["warn_lag_bytes"]:
            verdict = "lag_ok"
        elif eff < t["critical_lag_bytes"]:
            verdict = "lag_warn"
        else:
            verdict = "lag_critical"
        if grace_active and verdict in ("lag_warn", "lag_critical"):
            verdict = "lag_ok"
        if sid in forced:
            verdict = forced[sid]
        if sid in frozen:
            verdict = "frozen"
        if sid in embargoed:
            verdict = "embargoed"
        if wdesync and verdict != "frozen":
            verdict = "hold"
        profiles[sid] = {
            "effective_lag_bytes": eff,
            "embargoed": sid in embargoed,
            "final_verdict": verdict,
            "grace_active": grace_active,
            "shard_id": sid,
            "tier": tier,
            "witness_desync": wdesync,
        }

    flush_status: dict[str, str] = {}
    for sid in shard_ids:
        p = profiles[sid]
        if sid in frozen:
            flush_status[sid] = "blocked_frozen"
        elif sid in embargoed:
            flush_status[sid] = "blocked_embargo"
        elif p["witness_desync"]:
            flush_status[sid] = "blocked_witness"
        elif sid in cycle_nodes:
            flush_status[sid] = "blocked_cycle"
        elif p["final_verdict"] == "lag_ok":
            flush_status[sid] = "flush_ready"
        else:
            flush_status[sid] = "not_due"

    changed = True
    while changed:
        changed = False
        for sid in shard_ids:
            if flush_status[sid] != "flush_ready":
                continue
            for par in parents.get(sid, []):
                if profiles[par]["final_verdict"] != "lag_ok":
                    flush_status[sid] = "blocked_parent"
                    changed = True
                    break
                if flush_status[par] != "flush_ready":
                    flush_status[sid] = "blocked_parent"
                    changed = True
                    break

    def reasons_for(sid: str) -> list[str]:
        st = flush_status[sid]
        if st == "blocked_frozen":
            return ["frozen"]
        if st == "blocked_embargo":
            return ["embargo"]
        if st == "blocked_witness":
            return ["witness_desync"]
        if st == "blocked_cycle":
            return ["cycle"]
        if st == "blocked_parent":
            rs = []
            for par in parents.get(sid, []):
                if profiles[par]["final_verdict"] != "lag_ok":
                    rs.append(f"parent:{par}")
                elif flush_status[par] != "flush_ready":
                    rs.append(f"parent:{par}")
            return sorted(rs)
        if st == "not_due":
            return ["lag"]
        return []

    in_deg = {s: 0 for s in shard_ids if s not in cycle_nodes}
    for sid in in_deg:
        for par in parents.get(sid, []):
            if par in in_deg:
                in_deg[sid] += 1
    order: list[str] = []
    ready = sorted(s for s, d in in_deg.items() if d == 0)
    while ready:
        n = ready.pop(0)
        order.append(n)
        newly: list[str] = []
        for ch in children.get(n, []):
            if ch not in in_deg:
                continue
            in_deg[ch] -= 1
            if in_deg[ch] == 0:
                newly.append(ch)
        ready = sorted(ready + newly)

    tiers = {
        tier: {"lag_critical": 0, "lag_ok": 0, "lag_warn": 0}
        for tier in thresholds
    }
    hold_total = flush_ready_total = 0
    for sid in shard_ids:
        p = profiles[sid]
        if p["final_verdict"] == "hold":
            hold_total += 1
        if flush_status[sid] == "flush_ready":
            flush_ready_total += 1
        v = p["final_verdict"]
        if v in ("lag_ok", "lag_warn", "lag_critical"):
            tiers[p["tier"]][v] += 1

    profile_rows = []
    for sid in sorted(shard_ids):
        row = dict(profiles[sid])
        row["flush_status"] = flush_status[sid]
        profile_rows.append(row)

    return {
        "shard_profiles.json": {
            "current_day": current_day,
            "profiles": profile_rows,
        },
        "dependency_plan.json": {"cycles": cycles_sorted, "order": order},
        "flush_plan.json": {
            "entries": [
                {
                    "flush_status": flush_status[s],
                    "reasons": reasons_for(s),
                    "shard_id": s,
                }
                for s in sorted(shard_ids)
            ]
        },
        "incident_trace.json": {"applied": applied},
        "summary.json": {
            "current_day": current_day,
            "flush_ready_total": flush_ready_total,
            "hold_total": hold_total,
            "shards_total": len(shard_ids),
            "tiers": tiers,
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
    """Spec-derived reference payloads for cross-checks."""
    return _compute_reference()


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

    def test_output_on_disk_json_matches_spec_formatter(self, outputs: dict[str, object]) -> None:
        """On-disk bytes must be ASCII-only SPEC canonical JSON, not merely parse-equal to it."""
        for name in OUTPUT_FILES:
            raw_bytes = (AUDIT_DIR / name).read_bytes()
            text = raw_bytes.decode("ascii")
            assert text.endswith("\n") and not text.endswith("\n\n")
            assert text == _spec_json_file_text(outputs[name]), f"on-disk format mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, object]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        sp = outputs["shard_profiles.json"]
        assert isinstance(sp, dict)
        assert (
            _sha256_bytes(_canonical(sp["profiles"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["shard_profiles.profiles"]
        )
        dp = outputs["dependency_plan.json"]
        assert isinstance(dp, dict)
        assert (
            _sha256_bytes(_canonical(dp["order"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["dependency_plan.order"]
        )
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["tiers"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.tiers"]
        )

    def test_matches_independent_reference(self, outputs: dict[str, object], reference: dict[str, object]) -> None:
        """Emitted artifacts must equal an independent spec re-derivation."""
        for name in OUTPUT_FILES:
            assert outputs[name] == reference[name], f"reference mismatch for {name}"


class TestShardProfiles:
    """Semantic checks on per-shard lag profiles."""

    def test_bronze_outlier_rejection_yields_lag_ok(self, outputs: dict[str, object]) -> None:
        """Median-window outlier rejection must drop the spike on sh-bronze-outlier."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-bronze-outlier")
        assert row["effective_lag_bytes"] == 1_000_000
        assert row["final_verdict"] == "lag_ok"

    def test_grace_suppresses_critical_lag(self, outputs: dict[str, object]) -> None:
        """Failover grace on sh-grace must downgrade lag_critical to lag_ok at current_day."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-grace")
        assert row["grace_active"] is True
        assert row["final_verdict"] == "lag_ok"

    def test_witness_desync_forces_hold(self, outputs: dict[str, object]) -> None:
        """Witness skew beyond policy must set final_verdict hold on sh-witness."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-witness")
        assert row["witness_desync"] is True
        assert row["final_verdict"] == "hold"

    def test_embargo_marks_gold_ok_and_child(self, outputs: dict[str, object]) -> None:
        """Embargo downstream from sh-gold-ok must embargo that shard and sh-embargo."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        by_id = {p["shard_id"]: p for p in profiles}
        assert by_id["sh-gold-ok"]["embargoed"] is True
        assert by_id["sh-gold-ok"]["final_verdict"] == "embargoed"
        assert by_id["sh-embargo"]["embargoed"] is True
        assert by_id["sh-embargo"]["final_verdict"] == "embargoed"

    def test_bronze_warn_present_in_dataset(self, outputs: dict[str, object]) -> None:
        """sh-bronze-warn must reach lag_warn when effective lag sits between bronze thresholds."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-bronze-warn")
        assert row["final_verdict"] == "lag_warn"

    def test_gold_critical_present_in_dataset(self, outputs: dict[str, object]) -> None:
        """A shard must reach lag_critical when effective lag meets the gold critical floor."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-gold-crit")
        assert row["final_verdict"] == "lag_critical"

    def test_silver_force_critical_present(self, outputs: dict[str, object]) -> None:
        """force_lag_verdict on sh-silver-warn must set final_verdict lag_critical."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-silver-warn")
        assert row["final_verdict"] == "lag_critical"

    def test_frozen_shard_verdict(self, outputs: dict[str, object]) -> None:
        """freeze_shard on sh-frozen at day 96 must freeze the shard at current_day 97."""
        profiles = outputs["shard_profiles.json"]["profiles"]
        row = next(p for p in profiles if p["shard_id"] == "sh-frozen")
        assert row["final_verdict"] == "frozen"
        assert row["flush_status"] == "blocked_frozen"


class TestFlushPlan:
    """Flush readiness and blocking reasons."""

    def test_child_blocked_by_parent(self, outputs: dict[str, object]) -> None:
        """sh-child must be blocked_parent while sh-parent remains lag_critical."""
        entries = outputs["flush_plan.json"]["entries"]
        by_id = {e["shard_id"]: e for e in entries}
        assert by_id["sh-child"]["flush_status"] == "blocked_parent"
        assert "parent:sh-parent" in by_id["sh-child"]["reasons"]

    def test_cycle_shards_blocked(self, outputs: dict[str, object]) -> None:
        """Cycle members must use blocked_cycle with reasons exactly cycle only."""
        entries = outputs["flush_plan.json"]["entries"]
        for sid in ("sh-cycle-a", "sh-cycle-b"):
            row = next(e for e in entries if e["shard_id"] == sid)
            assert row["flush_status"] == "blocked_cycle"
            assert row["reasons"] == ["cycle"]
            assert not any(r.startswith("parent:") for r in row["reasons"])


class TestDependencyPlan:
    """Dependency graph reporting."""

    def test_cycle_pair_reported(self, outputs: dict[str, object]) -> None:
        """The sh-cycle-a and sh-cycle-b pair must appear as one directed cycle."""
        cycles = outputs["dependency_plan.json"]["cycles"]
        assert ["sh-cycle-a", "sh-cycle-b"] in cycles

    def test_order_greedy_lexicographic_topo(
        self, outputs: dict[str, object], reference: dict[str, object]
    ) -> None:
        """order must follow greedy smallest-ready shard_id topo, not batch waves."""
        assert outputs["dependency_plan.json"]["order"] == reference[
            "dependency_plan.json"
        ]["order"]


class TestIncidentTrace:
    """Incident application window."""

    def test_applied_incidents_within_current_day(self, outputs: dict[str, object]) -> None:
        """Every applied incident row must have day less than or equal to pool current_day."""
        applied = outputs["incident_trace.json"]["applied"]
        current_day = outputs["summary.json"]["current_day"]
        assert all(int(row["day"]) <= int(current_day) for row in applied)
        kinds = {(row["shard_id"], row["kind"]) for row in applied}
        assert ("sh-frozen", "freeze_shard") in kinds
        assert ("sh-silver-warn", "force_lag_verdict") in kinds


class TestSummary:
    """Rollup counters."""

    def test_summary_totals(self, outputs: dict[str, object]) -> None:
        """Summary counters must match profile and flush statuses."""
        summary = outputs["summary.json"]
        profiles = outputs["shard_profiles.json"]["profiles"]
        entries = outputs["flush_plan.json"]["entries"]
        assert summary["shards_total"] == len(profiles)
        assert summary["hold_total"] == sum(
            1 for p in profiles if p["final_verdict"] == "hold"
        )
        assert summary["flush_ready_total"] == sum(
            1 for e in entries if e["flush_status"] == "flush_ready"
        )
