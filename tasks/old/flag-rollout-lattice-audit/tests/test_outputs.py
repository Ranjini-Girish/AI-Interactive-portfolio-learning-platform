"""Verifier suite for flag-rollout-lattice-audit."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


DATA_DIR = Path(os.environ.get("FRLA_FLAGS_DIR", "/app/flags"))
AUDIT_DIR = Path(os.environ.get("FRLA_AUDIT_DIR", "/app/audit"))
APP_DIR = Path(os.environ.get("FRLA_APP_DIR", "/app"))

EXPECTED_INPUT_TREE_HASH = "92b1668f83961c298cfb5bd0b87dac72f3ae0aa2a906661607c5f0764c773ac1"
EXPECTED_FIELD_HASHES = {
    "dependency_waves": "5fa22dbd80ddb2185e90cb33d838f467a64528ee9a3470ae2c057dbb7385e5f3",
    "exposure_budget": "6c6e2a79f466e4e08c25b99ab22b22e670e5e7a4236b0a6b1d0edc7b5ac343d4",
    "incident_journal": "8d76102d4aa8d267f4b7e38457052e402f2b282d7c863d4a07e0aceef18979f7",
    "rollout_matrix": "ef86e50ab8eb96ec4887bcae097969c9b3f3a00beaadcf831a1f5f9110fca820",
    "summary": "a7aab3c16498a74f766558b93698a56307095c5a1ff3dfa05ec2e6f06bc44a1e"
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def input_tree_hash():
    h = hashlib.sha256()
    for path in sorted(DATA_DIR.rglob("*")):
        if path.is_file():
            h.update(path.relative_to(DATA_DIR).as_posix().encode())
            h.update(b"\0")
            h.update(path.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def descendants(segments, start):
    out = []
    stack = [start]
    while stack:
        cur = stack.pop()
        out.append(cur)
        children = sorted(sid for sid, row in segments.items() if row["parent_id"] == cur)
        stack.extend(reversed(children))
    return out


def ancestors(segments, start):
    out = []
    cur = start
    while cur is not None:
        out.append(cur)
        cur = segments[cur]["parent_id"]
    return out


def reference_outputs():
    policy = load_json(DATA_DIR / "policy.json")
    pool = load_json(DATA_DIR / "pool_state.json")
    dependencies = load_json(DATA_DIR / "dependencies.json")
    segments = {
        row["segment_id"]: row
        for row in (load_json(p) for p in sorted((DATA_DIR / "segments").glob("*.json")))
    }
    flags = {
        row["flag_id"]: row
        for row in (load_json(p) for p in sorted((DATA_DIR / "flags").glob("*.json")))
    }
    incidents = load_json(DATA_DIR / "incidents" / "incident_log.json")["events"]
    exposures = []
    for path in sorted((DATA_DIR / "exposures").glob("*.json")):
        exposures.extend(load_json(path)["records"])

    current_day = pool["current_day"]
    accepted = []
    ignored = []
    for row in sorted(incidents, key=lambda r: (r["day"], r["event_id"])):
        reason = None
        if not row.get("valid", False):
            reason = "invalid"
        elif row["day"] > current_day:
            reason = "future_day"
        elif row["kind"] not in policy["supported_incidents"]:
            reason = "unsupported_kind"
        if reason:
            ignored.append({"event_id": row["event_id"], "kind": row["kind"], "reason": reason})
        else:
            accepted.append(row)

    budget_delta = {fid: 0 for fid in flags}
    killed = set()
    forced_active = set()
    locks = {}
    compromised = set()
    waivers = set()
    applied = []
    for row in accepted:
        applied.append({k: row[k] for k in sorted(row) if k != "valid"})
        if row["kind"] == "budget_grant":
            budget_delta[row["flag_id"]] += row["delta_pct"]
        elif row["kind"] == "kill_switch":
            killed.add(row["flag_id"])
        elif row["kind"] == "force_state" and row["state"] == "active":
            forced_active.add(row["flag_id"])
        elif row["kind"] == "segment_lock":
            until = row["day"] + row["duration_days"] - 1
            lock_until = until + policy["tiers"]["gold"]["lock_grace_days"]
            for segment_id in descendants(segments, row["segment_id"]):
                locks[segment_id] = max(locks.get(segment_id, -1), lock_until)
        elif row["kind"] == "segment_compromise":
            compromised.update(descendants(segments, row["segment_id"]))
        elif row["kind"] == "dependency_waiver":
            until = row["day"] + row["duration_days"] - 1
            if until >= current_day:
                waivers.add((row["flag_id"], row["depends_on"]))

    active_edges = [
        (edge["flag_id"], edge["depends_on"])
        for edge in dependencies["edges"]
        if (edge["flag_id"], edge["depends_on"]) not in waivers
    ]
    by_flag = {
        fid: sorted(dep for flag_id, dep in active_edges if flag_id == fid)
        for fid in flags
    }
    visiting = set()
    memo = {}
    cycle_nodes = set()

    def wave(flag_id):
        if flag_id in memo:
            return memo[flag_id]
        if flag_id in visiting:
            cycle_nodes.update(visiting)
            return None
        visiting.add(flag_id)
        values = []
        for dep in by_flag[flag_id]:
            val = wave(dep)
            if val is None:
                cycle_nodes.add(flag_id)
            else:
                values.append(val)
        visiting.remove(flag_id)
        memo[flag_id] = None if flag_id in cycle_nodes else (max(values) + 1 if values else 0)
        return memo[flag_id]

    for flag_id in sorted(flags):
        wave(flag_id)

    rollouts = []
    allowed_by_flag = {fid: 0 for fid in flags}
    for flag_id in sorted(flags):
        flag = flags[flag_id]
        for segment_id in sorted(segments):
            candidates = []
            for index, override in enumerate(flag["overrides"]):
                if override["segment_id"] in ancestors(segments, segment_id):
                    candidates.append((override["priority"], index, override))
            pct = flag["default_pct"]
            source = "default"
            if candidates:
                _, _, winner = sorted(candidates, key=lambda x: (-x[0], x[1], x[2]["segment_id"]))[0]
                pct = winner["pct"]
                source = winner["segment_id"]
            reasons = []
            state = "active"
            if flag_id in cycle_nodes or any(dep in killed for dep in by_flag[flag_id]):
                state = "blocked_dependency"
                pct = 0
                reasons.append("dependency_block")
            if locks.get(segment_id, -1) >= current_day:
                if state == "active":
                    state = "locked"
                pct = 0
                reasons.append("segment_lock")
            cap = policy["tiers"][flag["tier"]]["max_pct"]
            if pct > cap:
                pct = cap
                reasons.append("tier_cap")
            if flag_id in forced_active and state in {"blocked_dependency", "locked"}:
                state = "active"
                reasons.append("force_state_active")
            if flag_id in killed:
                state = "killed"
                pct = 0
                reasons.append("kill_switch")
            if segment_id in compromised:
                state = "quarantined"
                pct = 0
                reasons.append("segment_compromise")
            allowed_by_flag[flag_id] += (segments[segment_id]["size"] * pct) // 100
            rollouts.append({
                "flag_id": flag_id,
                "segment_id": segment_id,
                "effective_pct": pct,
                "state": state,
                "source_segment": source,
                "reasons": sorted(set(reasons)),
            })

    observed = {fid: 0 for fid in flags}
    for row in exposures:
        observed[row["flag_id"]] += row["users"]
    total_population = sum(row["size"] for row in segments.values())
    budget_rows = []
    for flag_id in sorted(flags):
        flag = flags[flag_id]
        budget_pct = policy["tiers"][flag["tier"]]["default_budget_pct"] + budget_delta[flag_id]
        allowed_users = min((total_population * budget_pct) // 100, allowed_by_flag[flag_id])
        status = "within_budget"
        if flag_id in killed:
            status = "killed"
        elif any(row["flag_id"] == flag_id and row["segment_id"] in compromised for row in exposures):
            status = "quarantine_exposure"
        elif observed[flag_id] > allowed_users:
            status = "over_budget"
        budget_rows.append({
            "flag_id": flag_id,
            "observed_users": observed[flag_id],
            "allowed_users": allowed_users,
            "budget_pct": budget_pct,
            "budget_delta_pct": budget_delta[flag_id],
            "status": status,
        })

    wave_rows = []
    for flag_id in sorted(flags):
        if flag_id in cycle_nodes:
            wave_rows.append({
                "flag_id": flag_id,
                "wave": None,
                "dependency_status": "cycle_blocked",
                "blocked_by": sorted(by_flag[flag_id]),
            })
        else:
            killed_deps = sorted(dep for dep in by_flag[flag_id] if dep in killed)
            if killed_deps:
                wave_rows.append({
                    "flag_id": flag_id,
                    "wave": None,
                    "dependency_status": "upstream_killed",
                    "blocked_by": killed_deps,
                })
            else:
                wave_rows.append({
                    "flag_id": flag_id,
                    "wave": memo[flag_id],
                    "dependency_status": "ready",
                    "blocked_by": [],
                })

    return {
        "rollout_matrix": {"rollouts": rollouts},
        "exposure_budget": {"flags": budget_rows},
        "dependency_waves": {"flags": wave_rows},
        "incident_journal": {"applied": applied, "ignored": ignored},
        "summary": {
            "flags_total": len(flags),
            "segments_total": len(segments),
            "applied_incidents": len(applied),
            "ignored_incidents": len(ignored),
            "killed_flags": len(killed),
            "cycle_blocked_flags": len(cycle_nodes),
            "quarantined_segments": len(compromised),
            "over_budget_flags": sum(1 for row in budget_rows if row["status"] == "over_budget"),
            "quarantine_exposure_flags": sum(1 for row in budget_rows if row["status"] == "quarantine_exposure"),
        },
    }


class TestReportStructure:
    def test_required_files_and_top_level_keys(self):
        """Each required report exists and exposes the documented top-level object."""
        expected_keys = {
            "rollout_matrix.json": ["rollouts"],
            "exposure_budget.json": ["flags"],
            "dependency_waves.json": ["flags"],
            "incident_journal.json": ["applied", "ignored"],
            "summary.json": [
                "applied_incidents",
                "cycle_blocked_flags",
                "flags_total",
                "ignored_incidents",
                "killed_flags",
                "over_budget_flags",
                "quarantine_exposure_flags",
                "quarantined_segments",
                "segments_total",
            ],
        }
        for name, keys in expected_keys.items():
            payload = load_json(AUDIT_DIR / name)
            assert sorted(payload) == keys

    def test_reports_use_canonical_json(self):
        """Output JSON is UTF-8, sorted by keys, indented by two spaces, and newline terminated."""
        for name in [f"{stem}.json" for stem in ['rollout_matrix', 'exposure_budget', 'dependency_waves', 'incident_journal', 'summary']]:
            path = AUDIT_DIR / name
            raw = path.read_text(encoding="utf-8")
            assert raw.endswith("\n")
            assert raw == json.dumps(json.loads(raw), indent=2, sort_keys=True) + "\n"


class TestInputIntegrity:
    def test_input_tree_hash_matches_fixture(self):
        """The bundled input files must not be edited while producing the audit."""
        assert input_tree_hash() == EXPECTED_INPUT_TREE_HASH


class TestRolloutMatrix:
    def test_rollout_matrix_matches_reference(self):
        """Per-flag and per-segment rollout states follow the precedence lattice."""
        assert load_json(AUDIT_DIR / "rollout_matrix.json") == reference_outputs()["rollout_matrix"]

    def test_segment_compromise_has_highest_precedence(self):
        """Rows in compromised segment subtrees are quarantined even when another rule applies."""
        rows = load_json(AUDIT_DIR / "rollout_matrix.json")["rollouts"]
        compromised = [row for row in rows if row["segment_id"] == "beta-ring"]
        assert compromised
        assert all(row["state"] == "quarantined" for row in compromised)
        assert all("segment_compromise" in row["reasons"] for row in compromised)

    def test_locked_segment_descendants_are_frozen(self):
        """Segment locks apply to the named segment and descendants through the grace period."""
        rows = load_json(AUDIT_DIR / "rollout_matrix.json")["rollouts"]
        locked = [row for row in rows if row["segment_id"] == "enterprise-eu" and row["state"] == "locked"]
        assert locked
        assert all(row["effective_pct"] == 0 for row in locked)


class TestExposureBudget:
    def test_exposure_budget_matches_reference(self):
        """Budget rows combine tier defaults, grants, observed exposure, and quarantine exposure."""
        assert load_json(AUDIT_DIR / "exposure_budget.json") == reference_outputs()["exposure_budget"]

    def test_budget_grants_change_budget_percent(self):
        """Accepted budget grants are reflected in the budget percentage and delta fields."""
        rows = {row["flag_id"]: row for row in load_json(AUDIT_DIR / "exposure_budget.json")["flags"]}
        assert rows["checkout-v3"]["budget_delta_pct"] == 10
        assert rows["mobile-paywall"]["budget_delta_pct"] == 15


class TestDependencyWaves:
    def test_dependency_waves_match_reference(self):
        """Dependency waves account for waivers, killed upstreams, and cycles."""
        assert load_json(AUDIT_DIR / "dependency_waves.json") == reference_outputs()["dependency_waves"]

    def test_cycle_and_waiver_are_both_represented(self):
        """The fixture covers both a cycle block and a waived dependency edge."""
        rows = {row["flag_id"]: row for row in load_json(AUDIT_DIR / "dependency_waves.json")["flags"]}
        assert rows["ops-console"]["dependency_status"] == "cycle_blocked"
        assert rows["mobile-paywall"]["dependency_status"] == "ready"


class TestIncidentJournal:
    def test_incident_journal_matches_reference(self):
        """Applied and ignored incident rows are classified in stable chronological order."""
        assert load_json(AUDIT_DIR / "incident_journal.json") == reference_outputs()["incident_journal"]

    def test_ignored_reasons_cover_all_rejection_modes(self):
        """The fixture includes invalid, future-day, and unsupported-kind incident rows."""
        reasons = {
            row["reason"]
            for row in load_json(AUDIT_DIR / "incident_journal.json")["ignored"]
        }
        assert reasons == {"future_day", "invalid", "unsupported_kind"}


class TestSummaryAndHashes:
    def test_summary_matches_reference(self):
        """Summary counters are recomputed from the same interpreted state as the reports."""
        assert load_json(AUDIT_DIR / "summary.json") == reference_outputs()["summary"]

    def test_reference_field_hashes_are_stable(self):
        """Reference fields are hash-locked to catch accidental verifier drift."""
        expected = reference_outputs()
        for key, digest in EXPECTED_FIELD_HASHES.items():
            assert canonical_hash(expected[key]) == digest


class TestTypeScriptImplementation:
    def test_typescript_source_and_runner_regenerate_outputs(self):
        """The TypeScript project under /app can regenerate the same audit in a fresh directory."""
        project = APP_DIR / "rollout"
        main = project / "src" / "main.ts"
        assert main.exists()
        assert "typescript" in load_json(project / "package.json")["devDependencies"]
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            copied = tmp_path / "flags"
            shutil.copytree(DATA_DIR, copied)
            fresh_out = tmp_path / "audit"
            npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
            subprocess.run(
                [npm, "run", "audit", "--", "--input", str(copied), "--output", str(fresh_out)],
                cwd=project,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for name in [f"{stem}.json" for stem in ['rollout_matrix', 'exposure_budget', 'dependency_waves', 'incident_journal', 'summary']]:
                assert (fresh_out / name).read_text(encoding="utf-8") == (AUDIT_DIR / name).read_text(encoding="utf-8")
