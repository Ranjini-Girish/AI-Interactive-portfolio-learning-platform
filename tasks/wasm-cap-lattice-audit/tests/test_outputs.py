"""Behavioral tests for the WASM capability lattice audit task."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("WCA_DATA_DIR", "/app/wasmcaps"))
AUDIT_DIR = Path(os.environ.get("WCA_AUDIT_DIR", "/app/audit"))

OUTPUT_FILES = (
    "module_verdicts.json",
    "import_closure.json",
    "capability_lattice.json",
    "incident_journal.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "7152bb102f3b0e972d1582594aa198265b34121337b0a448ed3aee9ee13fb156",
    "allowlists/bronze.json": "5463af9cd9a7da5773636d7d8fc684c2cb8b9c8c03ef1bc7cdbcdca16cfc3ac1",
    "allowlists/gold.json": "fa17bf6278f0239118007008bde963343f7eca2c1893145701779dd5550c61c0",
    "allowlists/silver.json": "a936690f47d75f728c99fc972e53492541c3455f540c55c45c9ed07f3357705a",
    "hosts/slot-alpha.json": "f469b2ce7914f7f9e41550368655553ce4358a6c93e5e032a87cf500b051d195",
    "hosts/slot-beta.json": "3664722ad19042d2c5a8d4da345b501d9f281a3ae51daf22d1ec50525c464417",
    "incident_log.json": "83ba0c4a84be70316e25708888289f36efdfaac4a5c3e08f68ef92a3bc964b8d",
    "ledger/note.txt": "50f536a1cd555f0fdf5371a99ead3b9babd0c422fec0ec93d8b3a24d37a1ce14",
    "ledger/tag.json": "b5535a2e68000b13f6b8f57fc2f0962da4ede952f66dc81f9a53e434a3654be1",
    "modules/mod-bronze-cache.json": "07399458347069a29c6eb4e75650a1b1b4c4b2118f47f457a63a1d3d0a053210",
    "modules/mod-bronze-lite.json": "bedc367826b2fad8b4375c2025c1b4ffffa442ae30d88550e5ab7ac328a637d8",
    "modules/mod-bronze-ok.json": "d7ccfcdcffa8cbdbb31793dca5ca53d8c5bfa786162356ec86ab16f080f9a77c",
    "modules/mod-bronze-worker.json": "1a0ef7e18f5855c8eb0c21c38b4cd7531dd3aae5ac8de256a55d6caffbf39af8",
    "modules/mod-gold-aux.json": "c629556207d0274d272e2e2f23f5d2f23b4e78b5b71b5447b5593b76c5c7717a",
    "modules/mod-gold-deny.json": "30b52d550aecad1e39013d6d55240bd1bb06288278d8241c6a02ab8309d5dfb8",
    "modules/mod-gold-hub.json": "71a4a55c303b306a23100a215a8bf579b437ae072b239ed3bf21f16d5743f374",
    "modules/mod-silver-edge.json": "bf7305074adedbdb7d57525ebe9eb10838e3dd39a368f788c20ebea31e365429",
    "modules/mod-silver-net.json": "c358e1733ae1674d62b86352ab5383980ff1af21155ee2f060e79c4cf3e0aa93",
    "modules/mod-silver-ok.json": "8eefd71f41cd6ff427c7346b4f78029154b2c6dce920773c5d35014b4e699e6c",
    "policy.json": "55b6b738d3ca935e9809ef8baa6e061ddfea6d2b393f115806a1fa9d0e8d1acf",
    "pool_state.json": "d1b77fdef15deea70474dc5f7a8c7358bd7650e6f2e9a39ab7af472df0042689",
    "reexports.json": "006f838c270c9d0890597eeb120701f81c2c2119ed8cda73f52d13b02ceae7bc",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "module_verdicts.json": "ff2768fb4c160e278ce2be127fa8e6f580cbd14b314fa3ae2e758a19468b535e",
    "import_closure.json": "eb186adaf7aa5bb341f1cfaa2dae9d4c529980810604b25f2d466d2aa68b4959",
    "capability_lattice.json": "0f94279d49e34c15473e4167aab00f6cbb9174c2acd35e903ea3a6fa2ccb57eb",
    "incident_journal.json": "31a8932cb7a493362696d805aca3b8230bd6a5f38f81ed455cc6cb8aba1ce64f",
    "summary.json": "d68296c37685226c5823297bbac97ca7bc620ebe789d46194729fba6cad9d15f",
}

EXPECTED_FIELD_HASHES = {
    "module_verdicts.modules": "0e843ae46bb865dc4dddc45051c64e7d243106f73dd22759ab7066d95e5a8e1b",
    "summary.verdict_counts": "a8caa8577445b966698be8ea919eb9cec48afc980d0fa909fb991ddb56ad8a9a",
    "capability_lattice.host_slots": "1f0dde83b0d05a592f06e56f95bc2a579c08e209447f7bdeed919591f9e1780c",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _cat(cap: str) -> str:
    return cap.split(".", 1)[0] if "." in cap else cap


def _prefix_ok(imp: str, prefixes: list[str]) -> bool:
    return any(imp.startswith(p) for p in prefixes)


def _reference_audit(data_dir: Path) -> dict[str, object]:
    """Independent re-derivation from SPEC.md semantics."""
    policy = _load_json(data_dir / "policy.json")
    pool = _load_json(data_dir / "pool_state.json")
    current_day = int(pool["current_day"])
    cap_rank: list[str] = policy["cap_rank"]
    cap_rank_idx = {c: i for i, c in enumerate(cap_rank)}
    deny_subs: list[str] = policy["import_deny_substrings"]
    supported = set(policy["supported_incident_kinds"])

    allowlists: dict[str, list[str]] = {}
    for p in sorted((data_dir / "allowlists").glob("*.json")):
        allowlists[p.stem] = _load_json(p)["prefixes"]

    modules: dict[str, dict] = {}
    for p in sorted((data_dir / "modules").glob("*.json")):
        m = _load_json(p)
        modules[str(m["module_id"])] = m

    links = _load_json(data_dir / "reexports.json")["links"]
    hosts_raw = []
    for p in sorted((data_dir / "hosts").glob("*.json")):
        hosts_raw.append(_load_json(p))
    hosts_raw.sort(key=lambda h: h["host_slot"])

    quarantined: set[str] = set()
    frozen: set[str] = set()
    revoked: set[str] = set()
    accepted: list[dict] = []
    ignored: list[dict] = []

    events = sorted(
        _load_json(data_dir / "incident_log.json")["events"],
        key=lambda e: (int(e["day"]), str(e["event_id"])),
    )

    def propagate_q() -> None:
        changed = True
        while changed:
            changed = False
            for link in links:
                if link["from"] in quarantined and link["to"] not in quarantined:
                    quarantined.add(link["to"])
                    changed = True

    for ev in events:
        kind = str(ev["kind"])
        day = int(ev["day"])
        eid = str(ev["event_id"])
        acc = bool(ev.get("accepted", True))
        scope = ev.get("scope") or {}
        reason = None
        if not acc:
            reason = "accepted_false"
        elif day > current_day:
            reason = "future_day"
        elif kind not in supported:
            reason = "unsupported_kind"
        if reason:
            ignored.append({"day": day, "event_id": eid, "kind": kind, "reason": reason})
            continue
        accepted.append(ev)
        if kind == "module_compromise":
            quarantined.add(str(scope["module_id"]))
            propagate_q()
        elif kind == "capability_revoke":
            revoked.add(str(scope["capability"]))
        elif kind == "import_freeze":
            frozen.add(str(scope["module_id"]))

    eff_maps: dict[str, set[str]] = {}
    for mid, m in modules.items():
        if mid in quarantined:
            eff_maps[mid] = set()
        else:
            eff_maps[mid] = set(m["declared_imports"])

    changed = True
    while changed:
        changed = False
        for link in links:
            fr, to = link["from"], link["to"]
            if fr in quarantined or to in quarantined:
                continue
            for imp in eff_maps[fr]:
                if not _prefix_ok(imp, link["prefix_filters"]):
                    continue
                if imp not in eff_maps[to]:
                    eff_maps[to].add(imp)
                    changed = True

    verdicts: dict[str, str] = {}
    mod_rows = []
    for mid in sorted(modules):
        m = modules[mid]
        if mid in quarantined:
            eff: list[str] = []
            verdicts[mid] = "quarantined"
        else:
            eff = sorted(eff_maps[mid])
            decl_set = set(m["declared_imports"])
            verdict = "ok"
            if mid in frozen:
                for imp in eff:
                    if imp not in decl_set:
                        verdict = "import_frozen"
                        break
            if verdict == "ok":
                for imp in eff:
                    if any(sub in imp for sub in deny_subs):
                        verdict = "import_denied"
                        break
                    if not _prefix_ok(imp, allowlists[m["tier"]]):
                        verdict = "import_denied"
                        break
            verdicts[mid] = verdict
        mod_rows.append(
            {
                "declared_imports": sorted(m["declared_imports"]),
                "effective_imports": eff,
                "module_id": mid,
                "tier": m["tier"],
                "verdict": verdicts[mid],
            }
        )

    closures = {mid: sorted(eff_maps[mid]) for mid in sorted(modules)}

    def pick_cap(caps: list[str]) -> str:
        ranked = [c for c in caps if c in cap_rank_idx]
        if ranked:
            return min(ranked, key=lambda c: (cap_rank_idx[c], c))
        return min(caps)

    host_slots: dict[str, object] = {}
    for h in hosts_raw:
        by_cat: dict[str, list[str]] = {}
        for mid in h["members"]:
            if mid in quarantined:
                continue
            for cap in modules[mid]["capabilities"]:
                if cap in revoked:
                    continue
                by_cat.setdefault(_cat(cap), []).append(cap)
        merged = [pick_cap(by_cat[c]) for c in sorted(by_cat)]
        host_slots[h["host_slot"]] = {
            "host_slot": h["host_slot"],
            "merged_capabilities": sorted(merged),
            "members": sorted(h["members"]),
        }

    verdict_counts: dict[str, int] = {}
    for v in verdicts.values():
        verdict_counts[v] = verdict_counts.get(v, 0) + 1

    return {
        "module_verdicts.json": {
            "evaluation_day": current_day,
            "modules": mod_rows,
        },
        "import_closure.json": {"closures": closures},
        "capability_lattice.json": {"host_slots": host_slots},
        "incident_journal.json": {"accepted": accepted, "ignored": ignored},
        "summary.json": {
            "evaluation_day": current_day,
            "host_slots_total": len(hosts_raw),
            "modules_total": len(modules),
            "service_tiers": ["bronze", "gold", "silver"],
            "verdict_counts": {k: verdict_counts[k] for k in sorted(verdict_counts)},
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
        mv = outputs["module_verdicts.json"]
        assert isinstance(mv, dict)
        assert (
            _sha256_bytes(_canonical(mv["modules"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["module_verdicts.modules"]
        )

        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert (
            _sha256_bytes(_canonical(sm["verdict_counts"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["summary.verdict_counts"]
        )

        lat = outputs["capability_lattice.json"]
        assert isinstance(lat, dict)
        assert (
            _sha256_bytes(_canonical(lat["host_slots"]).encode("utf-8"))
            == EXPECTED_FIELD_HASHES["capability_lattice.host_slots"]
        )

    def test_reference_matches_outputs(self, outputs: dict[str, object], reference: dict[str, object]) -> None:
        """Emitted artifacts must equal the independent reference re-derivation."""
        for name in OUTPUT_FILES:
            assert _canonical(outputs[name]) == _canonical(reference[name]), name


class TestModuleOrdering:
    """Deterministic ordering rules on module verdict rows."""

    def test_modules_sorted_by_id(self, outputs: dict[str, object]) -> None:
        """`modules` must list rows in ascending ASCII `module_id` order."""
        rows = outputs["module_verdicts.json"]["modules"]
        assert isinstance(rows, list)
        ids = [str(r["module_id"]) for r in rows]
        assert ids == sorted(ids)


class TestVerdictSemantics:
    """Spot-check modules that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, object], mid: str) -> dict[str, object]:
        rows = outputs["module_verdicts.json"]["modules"]
        assert isinstance(rows, list)
        for r in rows:
            if isinstance(r, dict) and r.get("module_id") == mid:
                return r
        raise AssertionError(f"missing module row {mid}")

    def test_quarantined_hub_propagates_to_edge(self, outputs: dict[str, object]) -> None:
        """`mod-gold-hub` compromise quarantines forward re-export chain members."""
        assert self._row(outputs, "mod-gold-hub")["verdict"] == "quarantined"
        assert self._row(outputs, "mod-silver-edge")["verdict"] == "quarantined"
        assert self._row(outputs, "mod-bronze-worker")["verdict"] == "quarantined"

    def test_import_denied_on_debug_substring(self, outputs: dict[str, object]) -> None:
        """`mod-gold-deny` carries a deny-substring import and is import_denied."""
        r = self._row(outputs, "mod-gold-deny")
        assert r["verdict"] == "import_denied"

    def test_import_denied_on_silver_net(self, outputs: dict[str, object]) -> None:
        """`mod-silver-net` declares net.connect outside the silver allowlist."""
        r = self._row(outputs, "mod-silver-net")
        assert r["verdict"] == "import_denied"

    def test_import_frozen_on_bronze_lite(self, outputs: dict[str, object]) -> None:
        """`mod-bronze-lite` inherits env.secret via re-export while frozen."""
        r = self._row(outputs, "mod-bronze-lite")
        assert r["verdict"] == "import_frozen"
        assert "env.secret" in r["effective_imports"]

    def test_ok_on_standalone_silver(self, outputs: dict[str, object]) -> None:
        """`mod-silver-ok` passes allowlist checks with only declared imports."""
        r = self._row(outputs, "mod-silver-ok")
        assert r["verdict"] == "ok"


class TestImportClosure:
    """Re-export closure shapes."""

    def test_bronze_lite_inherits_env_secret(self, outputs: dict[str, object]) -> None:
        """Closure for mod-bronze-lite includes env.secret from mod-silver-ok."""
        closures = outputs["import_closure.json"]["closures"]
        assert isinstance(closures, dict)
        lite = closures["mod-bronze-lite"]
        assert isinstance(lite, list)
        assert "env.secret" in lite


class TestCapabilityLattice:
    """Host-slot capability merge precedence."""

    def test_slot_alpha_fs_read_wins(self, outputs: dict[str, object]) -> None:
        """slot-alpha merges fs.read ahead of fs.write per cap_rank."""
        slots = outputs["capability_lattice.json"]["host_slots"]
        assert isinstance(slots, dict)
        alpha = slots["slot-alpha"]
        assert isinstance(alpha, dict)
        merged = alpha["merged_capabilities"]
        assert isinstance(merged, list)
        assert "fs.read" in merged
        assert "fs.write" not in merged

    def test_revoked_log_emit_absent(self, outputs: dict[str, object]) -> None:
        """Accepted capability_revoke removes log.emit from slot-alpha merge."""
        slots = outputs["capability_lattice.json"]["host_slots"]
        alpha = slots["slot-alpha"]
        merged = alpha["merged_capabilities"]
        assert "log.emit" not in merged


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
    """Summary counters reconcile with module rows."""

    def test_modules_total(self, outputs: dict[str, object]) -> None:
        """Ten modules are present in the bundled manifest set."""
        sm = outputs["summary.json"]
        assert isinstance(sm, dict)
        assert int(sm["modules_total"]) == 10

    def test_verdict_count_keys_sorted(self, outputs: dict[str, object]) -> None:
        """Summary verdict_counts keys are sorted lexicographically."""
        counts = outputs["summary.json"]["verdict_counts"]
        assert isinstance(counts, dict)
        assert list(counts.keys()) == sorted(counts.keys())

    def test_each_verdict_enum_represented(self, outputs: dict[str, object]) -> None:
        """Every documented module verdict enum appears at least once."""
        counts = outputs["summary.json"]["verdict_counts"]
        assert isinstance(counts, dict)
        for verdict in ("import_denied", "import_frozen", "ok", "quarantined"):
            assert int(counts[verdict]) >= 1
