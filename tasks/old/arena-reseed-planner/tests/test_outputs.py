import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


DATA_DIR = Path(os.environ.get("ARP_DATA_DIR", "/app/league"))
OUT_DIR = Path(os.environ.get("ARP_OUTPUT_DIR", "/app/plan"))
PLANNER_DIR = Path("/app/planner")

EXPECTED_FILES = [
    "match_plan.json",
    "arena_load.json",
    "bench_report.json",
    "standings_projection.json",
    "summary.json",
]

EXPECTED_INPUT_HASHES = {
    "incident_log.json": "ab23947437b3e8ee02cfb39fd0cbc80dbd6353259d94cb4afb49ee66a578e381",
    "policy.json": "647fac4f3ae8575031100519a3404adef91941d92894de31a522396abe8faed3",
    "pool_state.json": "e96125efc3aa29a146002e5e029adb8d93b197e604c4dc36ce10378d9638f6c2",
}

EXPECTED_FIELD_HASHES = {
    "arena_load": "3ed3f9b4fe9d47126de364ae5311e632df5529734a8f90fac809d00856eb28de",
    "bench_report": "811a5abe41e2d7b0c61e3970c28bc2928e2f28ff1e7adb5c9674ea213488cbb7",
    "match_plan": "a117ac58f21894b947eaed13d4eb031bf3125a2abefa70be30a9459cea746d4c",
    "standings_projection": "cf961a0f7eef0557f643e92f78829fea903671fc974415da576568c77819cd79",
    "summary": "0f872ec2b2a500f4793fe42443d0fecf434b816a65f4b9985f5cbcaba73081bf",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_hash(path: Path) -> str:
    return _sha256_text(path.read_text(encoding="utf-8"))


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _arena_score(arena, team_a, team_b):
    score = 0
    if arena["region"] == team_a["home_region"] == team_b["home_region"]:
        score += 2
    elif arena["region"] in {team_a["home_region"], team_b["home_region"]}:
        score += 1
    if arena["arena_id"] in set(team_a["preferred_arena_ids"]) | set(team_b["preferred_arena_ids"]):
        score += 1
    score += {"large": 2, "medium": 1, "small": 0}[arena["capacity_band"]]
    return score


def derive_expected_outputs():
    """Re-derive all expected reports directly from fixtures and spec rules."""
    policy = _read_json(DATA_DIR / "policy.json")
    pool_state = _read_json(DATA_DIR / "pool_state.json")
    incidents = _read_json(DATA_DIR / "incident_log.json")

    teams = sorted(
        [_read_json(p) for p in (DATA_DIR / "teams").glob("*.json")],
        key=lambda x: x["team_id"],
    )
    arenas = sorted(
        [_read_json(p) for p in (DATA_DIR / "arenas").glob("*.json")],
        key=lambda x: x["arena_id"],
    )

    current_day = pool_state["current_day"]
    active_incidents = [
        e for e in incidents if e.get("accepted") and e.get("day", 10**9) <= current_day
    ]

    suspended = set()
    locked_arenas = set()
    overrides = {}
    for event in active_incidents:
        kind = event.get("kind")
        if kind == "suspension":
            suspended.add(event["team_id"])
        elif kind == "arena_lock":
            locked_arenas.add(event["arena_id"])
        elif kind == "stamina_override":
            team_id = event["team_id"]
            prior = overrides.get(team_id)
            candidate = (event["day"], event["event_id"], event["new_stamina"])
            if prior is None or candidate[0] > prior[0] or (
                candidate[0] == prior[0] and candidate[1] < prior[1]
            ):
                overrides[team_id] = candidate

    effective_stamina = {
        t["team_id"]: overrides.get(t["team_id"], (None, None, t["stamina"]))[2] for t in teams
    }

    bench_reason = {}
    active_teams = []
    for team in teams:
        tid = team["team_id"]
        if tid in suspended:
            bench_reason[tid] = "suspended"
            continue
        if team["roster_size"] < policy["min_roster_size"]:
            bench_reason[tid] = "small_roster"
            continue
        if effective_stamina[tid] < policy["min_stamina"]:
            bench_reason[tid] = "low_stamina"
            continue
        active_teams.append(team)

    active_teams.sort(
        key=lambda t: (
            -policy["tier_priority"][t["tier"]],
            -t["seed_score"],
            t["team_id"],
        )
    )

    rivalry_pairs = {_pair_key(a, b) for a, b in policy["rivalry_pairs"]}
    arena_counts = {a["arena_id"]: 0 for a in arenas}

    projected_points = {t["team_id"]: 0 for t in teams}
    match_plan = []
    rivalry_matches = 0
    for idx in range(0, len(active_teams) - 1, 2):
        a = active_teams[idx]
        b = active_teams[idx + 1]
        rivalry = _pair_key(a["team_id"], b["team_id"]) in rivalry_pairs
        if rivalry:
            rivalry_matches += 1

        candidates = []
        for arena in arenas:
            if rivalry:
                candidates.append(arena)
            else:
                if arena["arena_id"] in locked_arenas:
                    continue
                if arena_counts[arena["arena_id"]] >= policy["max_matches_per_arena"]:
                    continue
                candidates.append(arena)

        if not candidates:
            match_plan.append(
                {
                    "arena_id": None,
                    "arena_locked_bypass": False,
                    "match_id": f"m{(idx // 2) + 1:02d}",
                    "rivalry": rivalry,
                    "status": "unassigned",
                    "team_a": a["team_id"],
                    "team_b": b["team_id"],
                }
            )
            continue

        best = min(
            candidates,
            key=lambda ar: (-_arena_score(ar, a, b), ar["arena_id"]),
        )
        arena_counts[best["arena_id"]] += 1
        bypass = rivalry and best["arena_id"] in locked_arenas
        points = policy["participation_points"] + (policy["rivalry_bonus"] if rivalry else 0)
        projected_points[a["team_id"]] += points
        projected_points[b["team_id"]] += points
        match_plan.append(
            {
                "arena_id": best["arena_id"],
                "arena_locked_bypass": bypass,
                "match_id": f"m{(idx // 2) + 1:02d}",
                "rivalry": rivalry,
                "status": "scheduled",
                "team_a": a["team_id"],
                "team_b": b["team_id"],
            }
        )

    if len(active_teams) % 2 == 1:
        bench_reason[active_teams[-1]["team_id"]] = "odd_team_out"

    for team_id in suspended:
        projected_points[team_id] += policy["suspended_penalty"]

    arena_load = [
        {
            "arena_id": a["arena_id"],
            "locked": a["arena_id"] in locked_arenas,
            "overbooked": arena_counts[a["arena_id"]] > policy["max_matches_per_arena"],
            "scheduled_count": arena_counts[a["arena_id"]],
        }
        for a in arenas
    ]
    bench_report = sorted(
        [
            {
                "effective_stamina": effective_stamina[team_id],
                "reason": reason,
                "team_id": team_id,
            }
            for team_id, reason in bench_reason.items()
        ],
        key=lambda x: x["team_id"],
    )
    benched_ids = {x["team_id"] for x in bench_report}
    standings = [
        {
            "projected_points": projected_points[t["team_id"]],
            "status": "benched" if t["team_id"] in benched_ids else "active",
            "team_id": t["team_id"],
        }
        for t in teams
    ]
    summary = {
        "active_teams": len(active_teams),
        "benched_count": len(bench_report),
        "locked_arenas": len(locked_arenas),
        "matches_scheduled": sum(1 for m in match_plan if m["status"] == "scheduled"),
        "matches_unassigned": sum(1 for m in match_plan if m["status"] == "unassigned"),
        "overbooked_arenas": sum(1 for a in arena_load if a["overbooked"]),
        "rivalry_matches": rivalry_matches,
        "suspended_count": sum(1 for b in bench_report if b["reason"] == "suspended"),
        "total_teams": len(teams),
    }
    return {
        "match_plan": match_plan,
        "arena_load": arena_load,
        "bench_report": bench_report,
        "standings_projection": standings,
        "summary": summary,
    }


class TestReportPresence:
    def test_all_report_files_exist(self):
        """Every required output report exists after planner execution."""
        for filename in EXPECTED_FILES:
            assert (OUT_DIR / filename).exists(), f"Missing output file: {filename}"


class TestInputIntegrity:
    def test_input_hashes(self):
        """Input fixtures are unchanged from the task's published baseline."""
        for filename, expected_hash in EXPECTED_INPUT_HASHES.items():
            observed = _file_hash(DATA_DIR / filename)
            assert observed == expected_hash, f"{filename} hash mismatch: {observed} != {expected_hash}"


class TestOutputSemantics:
    def test_outputs_match_spec_derivation(self):
        """Outputs match independent rule re-derivation from fixture data."""
        expected = derive_expected_outputs()
        observed = {
            "match_plan": _read_json(OUT_DIR / "match_plan.json"),
            "arena_load": _read_json(OUT_DIR / "arena_load.json"),
            "bench_report": _read_json(OUT_DIR / "bench_report.json"),
            "standings_projection": _read_json(OUT_DIR / "standings_projection.json"),
            "summary": _read_json(OUT_DIR / "summary.json"),
        }
        assert observed == expected

    def test_field_hashes(self):
        """Each output field has the expected canonical SHA-256 digest."""
        observed = {
            "match_plan": _read_json(OUT_DIR / "match_plan.json"),
            "arena_load": _read_json(OUT_DIR / "arena_load.json"),
            "bench_report": _read_json(OUT_DIR / "bench_report.json"),
            "standings_projection": _read_json(OUT_DIR / "standings_projection.json"),
            "summary": _read_json(OUT_DIR / "summary.json"),
        }
        for field, expected_hash in EXPECTED_FIELD_HASHES.items():
            actual_hash = _sha256_text(_canonical(observed[field]))
            assert actual_hash == expected_hash, (
                f"{field} hash mismatch: {actual_hash} != {expected_hash}"
            )

    def test_rivalry_lock_bypass_present(self):
        """At least one rivalry match bypasses a locked arena as required by the fixtures."""
        match_plan = _read_json(OUT_DIR / "match_plan.json")
        assert any(
            row["rivalry"] and row["arena_locked_bypass"] for row in match_plan
        ), "Expected a rivalry lock-bypass match"

    def test_bench_reasons_cover_expected_cases(self):
        """Fixture coverage includes suspended and small_roster bench reasons."""
        bench_report = _read_json(OUT_DIR / "bench_report.json")
        reasons = {row["reason"] for row in bench_report}
        assert "suspended" in reasons
        assert "small_roster" in reasons


class TestImplementationLanguage:
    def test_rust_source_exists(self):
        """Planner implementation remains in Rust source files."""
        main_rs = PLANNER_DIR / "src" / "main.rs"
        assert main_rs.exists(), "Expected /app/planner/src/main.rs to exist"
        content = main_rs.read_text(encoding="utf-8")
        assert "fn main" in content

    def test_cargo_run_reproduces_outputs(self):
        """Re-running cargo in a temp output directory reproduces report JSON exactly."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            env = os.environ.copy()
            env["ARP_DATA_DIR"] = str(DATA_DIR)
            env["ARP_OUTPUT_DIR"] = str(tmp_dir)
            subprocess.run(["cargo", "run", "--quiet"], cwd=PLANNER_DIR, check=True, env=env)
            for filename in EXPECTED_FILES:
                baseline = _read_json(OUT_DIR / filename)
                rerun = _read_json(tmp_dir / filename)
                assert rerun == baseline, f"cargo rerun mismatch for {filename}"
