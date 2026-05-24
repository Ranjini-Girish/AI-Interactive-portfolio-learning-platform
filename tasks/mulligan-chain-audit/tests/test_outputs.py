"""Behavioral tests for the mulligan chain audit task."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest


def data_dir() -> Path:
    """Resolve the tournament bundle root; non-empty MCA_DATA_DIR overrides the default."""
    raw = os.environ.get("MCA_DATA_DIR", "")
    return Path(raw) if raw else Path("/app/mulligan_pool")


def audit_dir() -> Path:
    """Resolve the audit output directory; non-empty MCA_AUDIT_DIR overrides the default."""
    raw = os.environ.get("MCA_AUDIT_DIR", "")
    return Path(raw) if raw else Path("/app/audit")

OUTPUT_FILES = (
    "session_verdicts.json",
    "mulligan_traces.json",
    "deck_restrictions.json",
    "incident_ledger.json",
    "summary.json",
)

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "0e25a11bc51a1f68f89e9d27de0efe3d9bd8de6ac065d0b7c7705c0258cf3361",
    "decks/d01.json": "11d7c758ea11ca19f188c97fe394c1155bc535cea3afdc64976becce135d6144",
    "decks/d02.json": "ed70a75b1f858c9d2311bc3d8ed48d00c7067a0605f3926de0dc482eda435933",
    "decks/d03.json": "054017408270f886eb95031912f6a5bd4135590a42268de00c661969ac6786d2",
    "decks/d04.json": "c3fa8bbdd82dc17c08060a270bd5ca5327c95c1bae529eeabdf2546f5dcac537",
    "decks/d05.json": "b4e98ff3c0c6ee0de2bd32f7a5be11f2a95a62b05654467114a9ce3e9137903f",
    "decks/d06.json": "d095b5da8d3aa52d9458175329b262cd1523ab781d3d748ab4c1314169fe2b2d",
    "decks/d07.json": "2c28ca92f2f6af562a6ae96984b2c9640e8808ccddc1f500393487af686216e1",
    "decks/d08.json": "8946bb8b2bf88f8b19590f2dd0a292dad1cbeefacc715cd56f25b8d85b7089ae",
    "decks/d11.json": "9a997cf4d2ffb1d27d2472b911e2fa0e84b47e6ab85d77203fa35bd9f9f5e1c5",
    "formats/fmt-modern.json": "b0f83b6a5e05dce14790bf42fee6f37e454d570584f3af7c967af7cc9b2c3bf5",
    "formats/fmt-pioneer.json": "3067263762d63b7693abb6bd3ae243202ca9d59762afe8e8630db8741aa4fc24",
    "formats/fmt-standard.json": "35a797a42d940c77d9e6247017feae8d6f36dcba7f66916e35c18e1618f3d508",
    "incidents.json": "71161b3d4dc3aeac5f3acd6e731565cf78cc4474aa6fa9c40b122cc8bf24b432",
    "meta/extra_a.json": "5443828ff3eb5ffd8270ce4c4ed918d108edce1c6687dc203c4733d3c865c9a0",
    "meta/extra_b.json": "30955ce04dbdf0c87cb325d6ab9938685c2eba4ccc67cd9daa96b9660362e9eb",
    "meta/notes.txt": "e00583631c6da9b9ba5f9a3f07533dbed81b4bc012aa721a7155b357a575d258",
    "meta/season.json": "0c4dcb4e21a468739182cdc7908dd01fa94367a28d38a1ab6603061865a78fcb",
    "meta/venue.json": "11081471d590e82056d160891f42e7a169018589298362d2b9169bb91afe2174",
    "policy.json": "80284f95864c8423bcc1542bb82bb76bf3490b1649bb2b74b7f8f9cf9e320f8c",
    "pool_state.json": "bc383d68e9727a5442852b4f4b55c1302361c4e1666ecd6ffd26fb181095b1c7",
    "sessions/s01.json": "d657fab21b6045510152b542b0e4f05ee7585db69bdf27617a668e407be3dc37",
    "sessions/s02.json": "9b173b8937e00e52117b0b2040ed5758808d79620a8d6122c0c06acbbad5a435",
    "sessions/s03.json": "b4c70f0b271a4d7a6aae5aa4534e432c2a2aced2e6cf4ee7a259c7fda5be0da5",
    "sessions/s04.json": "fafaaaee9aaa8dcc76d7806322265e91c4bc92901677fed7c1051abb2e4257eb",
    "sessions/s05.json": "dd3738f9f6cd119f85d57500fa89e4e6fd03eed07037c797caf6152c87d8cb9e",
    "sessions/s06.json": "afeb0cd289652c473a904d92f6e4242a1dee203a83013bb3ed71b9a2eb5d4c2e",
    "sessions/s07.json": "68443889661a8b8ed09928d0a23d78f61204afc6e3b420f62c809680a4361543",
    "sessions/s08.json": "653e3e50a810d1ce048022f71246e0d8e3b7c93d9673c7e7dd71dff11e264a76",
    "sessions/s09.json": "94be28aaff107c39cb3b0e675ad7baa88b194536bbd79b75deba70f7ec47448e",
    "sessions/s10.json": "624563842968c85baf6d5a663b2743daa0f983ffd3b119167a78ff0443b48ee0",
    "sessions/s11.json": "54ce9f50f34e27bdd233dc5557e681a57beaef884cdf8a194fba40b4b43af3d6",
    "sessions/s12.json": "0d44a7af798f7c23e4fd72380c5c0639014d8eafe17db3d14df9860f4ac71ee6",
}

EXPECTED_OUTPUT_FILE_SHA256 = {
    "deck_restrictions.json": "217851b21f5128cbdc833186a3607cfe6276b9a1cce61db52a9f0e21bcd1ec88",
    "incident_ledger.json": "bbcb3767ee22a6ea6c0a2435c899ae0d616de8606d0753abbc7999f9bf49702c",
    "mulligan_traces.json": "7452c94e29ef73acb9dcd94d6c581bcc374d1d67d86de18c8fc29a8f760ebc1a",
    "session_verdicts.json": "9dc3f51821395cc41a3b92d0d26e93b45021bae693a2dba0316fc8863fd69438",
    "summary.json": "bb329635d337246c1bf5e07dff5e70303fd54c12b49cd70e6fbf00b235e606b2",
}

EXPECTED_FIELD_HASHES = {
    "deck_restrictions.decks": "395170a2e4fb3efe8e9db3c98c3dbb319560a38f1499f93790ea8837adbebc7b",
    "incident_ledger.applied_events": "ccef3ba408ff3790f8bd948db42f0a9554f73c20042e42fc23e5214be85730dd",
    "mulligan_traces.traces": "256e105391f5a9d6bb81e1b9c4109b12f63d84dba76b04482dba0e44d879f99e",
    "session_verdicts.sessions": "0d47921a4578f81a7ebf8d1a5af8bc7bd626f4853541db171b30a8b280ef3ef7",
    "summary.applied_incident_events": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.chain_invalid_sessions": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.deck_restriction_hits": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.format_suspended_sessions": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.ignored_incident_events": "1121cfccd5913f0a63fec40a6ffd44ea64f9dc135c66634ba001d10bcf4302a2",
    "summary.legal_sessions": "53c234e5e8472b6ac51c1ae1cab3fe06fad053beb8ebfd8977b010655bfdd3c3",
    "summary.quarantined_sessions": "4355a46b19d348dc2f57c046f8ef63d4538ebb936000f3c9ee954a27460dd865",
    "summary.sessions_total": "a1fb50e6c86fae1679ef3351296fd6713411a08cf8dd1790a4fd05fae8688164",
}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    """Serialize like the on-disk contract: UTF-8, ASCII-only, sorted keys, two-space indent, trailing newline."""
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_hand_size(style: str, opening: int, m: int, fmt: dict[str, Any]) -> int:
    if style == "london":
        return opening
    if style == "vancouver":
        min_keep = int(fmt.get("min_keep_hand_size", 4))
        return max(min_keep, opening - m)
    if style == "partial_paris":
        return max(1, opening - 2 * m)
    return opening


def _compute_violations(deck: dict[str, Any], limits: dict[str, int]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for zone in ("maindeck", "sideboard"):
        for card in deck.get(zone, []):
            counts[card] = counts.get(card, 0) + 1
    out: list[dict[str, Any]] = []
    for card, limit in limits.items():
        found = counts.get(card, 0)
        if found > limit:
            out.append({"card": card, "found": found, "limit": limit})
    out.sort(key=lambda row: row["card"])
    return out


def _merge_restricted_counts(
    formats: dict[str, dict[str, Any]], format_ids: set[str]
) -> dict[str, int]:
    merged: dict[str, int] = {}
    for fid in format_ids:
        fmt = formats.get(fid)
        if not fmt:
            continue
        rc = fmt.get("restricted_counts") or {}
        if not isinstance(rc, dict):
            continue
        for card, lim in rc.items():
            li = int(lim)
            if card not in merged or li < merged[card]:
                merged[card] = li
    return merged


def _structural_chain_issues(chain: list[dict[str, Any]]) -> list[str]:
    flags: set[str] = set()
    keeps = 0
    for idx, step in enumerate(chain):
        if step.get("action") == "keep":
            keeps += 1
        if int(step.get("step", -1)) != idx:
            flags.add("step_index_drift")
        act = step.get("action")
        if act not in ("mulligan", "keep"):
            flags.add("invalid_action")
    if keeps > 1:
        flags.add("multiple_keep")
    return sorted(flags)


def _apply_shared_mulligan_cap(
    effective_max: int,
    pool_val: int | None,
    sessions_sorted: list[dict[str, Any]],
    cur: dict[str, Any],
    mull_by_session: dict[str, int],
) -> int:
    if pool_val is None:
        return effective_max
    cur_id = str(cur["session_id"])
    did = str(cur["deck_id"])
    prior = 0
    for s in sessions_sorted:
        if str(s["session_id"]) == cur_id:
            break
        if str(s["deck_id"]) == did:
            prior += mull_by_session[str(s["session_id"])]
    room = pool_val - prior
    if room < 0:
        room = 0
    return min(effective_max, room)


def compute_reference(base: Path) -> dict[str, Any]:
    """Re-derive all five audit artifacts from the mounted bundle."""
    policy = _load_json(base / "policy.json")
    pool = _load_json(base / "pool_state.json")
    current_day = int(pool["current_day"])
    opening = int(policy.get("opening_hand_size", 7))
    if opening < 1:
        opening = 7

    pool_shared = policy.get("shared_mulligan_pool")
    pool_shared_int: int | None
    if pool_shared is None:
        pool_shared_int = None
    else:
        pool_shared_int = int(pool_shared)

    formats: dict[str, dict[str, Any]] = {}
    for path in sorted((base / "formats").glob("*.json")):
        doc = _load_json(path)
        formats[str(doc["format_id"])] = doc

    decks: dict[str, dict[str, Any]] = {}
    for path in sorted((base / "decks").glob("*.json")):
        doc = _load_json(path)
        decks[str(doc["deck_id"])] = doc

    sessions: list[dict[str, Any]] = []
    for path in sorted((base / "sessions").glob("*.json")):
        sessions.append(_load_json(path))
    sessions_sorted = sorted(sessions, key=lambda s: str(s["session_id"]))

    incidents = _load_json(base / "incidents.json")["events"]
    kept: list[dict[str, Any]] = []
    for ev in incidents:
        if ev.get("accepted") is not True:
            continue
        day = int(ev["day"])
        if day > current_day:
            continue
        kind = ev.get("kind")
        if kind == "card_ban" and "card" not in ev:
            continue
        if kind == "deck_compromise" and "deck_id" not in ev:
            continue
        if kind == "format_suspend" and "format_id" not in ev:
            continue
        if kind not in ("card_ban", "deck_compromise", "format_suspend"):
            continue
        kept.append(ev)
    kept.sort(key=lambda ev: (int(ev["day"]), str(ev["event_id"])))
    ignored = len(incidents) - len(kept)

    banned: dict[str, int] = {}
    compromised: dict[str, int] = {}
    suspended: dict[str, int] = {}
    ledger: list[dict[str, Any]] = []
    for ev in kept:
        day = int(ev["day"])
        kind = str(ev["kind"])
        row: dict[str, Any] = {"day": day, "event_id": ev["event_id"], "kind": kind}
        if kind == "card_ban":
            banned[str(ev["card"])] = day
            row["card"] = ev["card"]
        elif kind == "deck_compromise":
            compromised[str(ev["deck_id"])] = day
            row["deck_id"] = ev["deck_id"]
        elif kind == "format_suspend":
            suspended[str(ev["format_id"])] = day
            row["format_id"] = ev["format_id"]
        ledger.append(row)

    deck_format_ids: dict[str, set[str]] = {}
    for sess in sessions:
        did = str(sess["deck_id"])
        deck_format_ids.setdefault(did, set()).add(str(sess["format_id"]))

    deck_rows: list[dict[str, Any]] = []
    deck_violations: dict[str, list[dict[str, Any]]] = {}
    for did in sorted(decks):
        limits = _merge_restricted_counts(formats, deck_format_ids.get(did, set()))
        viol = _compute_violations(decks[did], limits)
        deck_violations[did] = viol
        deck_rows.append({"deck_id": did, "violations": viol})

    mull_by_session: dict[str, int] = {}
    for sess in sessions_sorted:
        chain = sess["chain"]
        fid = str(sess["format_id"])
        fmt = formats[fid]
        has_keep = any(step.get("action") == "keep" for step in chain)
        last_keep = -1
        for idx, step in enumerate(chain):
            if step.get("action") == "keep":
                last_keep = idx
        mull_count = 0
        if has_keep:
            for step in chain[:last_keep]:
                if step.get("action") == "mulligan":
                    mull_count += 1
        else:
            mull_count = sum(1 for step in chain if step.get("action") == "mulligan")
        mull_by_session[str(sess["session_id"])] = mull_count

    verdict_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    legal_count = quarantine_count = format_suspend_count = chain_invalid_count = 0

    for sess in sessions_sorted:
        sid = str(sess["session_id"])
        did = str(sess["deck_id"])
        fid = str(sess["format_id"])
        played_day = int(sess["played_day"])
        chain = sess["chain"]
        fmt = formats[fid]
        deck = decks[did]
        viol = deck_violations[did]

        has_keep = any(step.get("action") == "keep" for step in chain)
        last_keep = -1
        for idx, step in enumerate(chain):
            if step.get("action") == "keep":
                last_keep = idx

        mull_count = mull_by_session[sid]

        steps_out: list[dict[str, Any]] = []
        size_mismatch = not has_keep
        m_prior = 0
        for step in chain:
            exp = _expected_hand_size(str(fmt["mulligan_style"]), opening, m_prior, fmt)
            hand = step.get("hand") or []
            hs = len(hand)
            ok = hs == exp
            if not ok:
                size_mismatch = True
            steps_out.append(
                {
                    "step": int(step["step"]),
                    "action": step["action"],
                    "hand_size": hs,
                    "size_ok": ok,
                }
            )
            if step.get("action") == "mulligan":
                m_prior += 1
        trace_rows.append({"session_id": sid, "steps": steps_out})

        final_hand: list[str] = []
        for step in reversed(chain):
            if step.get("action") == "keep":
                final_hand = list(step.get("hand") or [])
                break

        banned_found = sorted(
            {
                card
                for card in final_hand
                if card in banned and played_day >= banned[card]
            }
        )

        tier_cap = policy.get("max_mulligans_by_tier", {}).get(deck["tier"])
        effective_max = int(fmt["max_mulligans"])
        if tier_cap is not None and int(tier_cap) < effective_max:
            effective_max = int(tier_cap)
        effective_max = _apply_shared_mulligan_cap(
            effective_max, pool_shared_int, sessions_sorted, sess, mull_by_session
        )

        struct_reasons = _structural_chain_issues(chain)

        reasons: list[str] = []
        verdict = "legal"
        if did in compromised and played_day >= compromised[did]:
            verdict = "quarantined"
            reasons.append("deck_compromise")
        elif fid in suspended and played_day >= suspended[fid]:
            verdict = "format_suspended"
            reasons.append("format_suspend")
        elif viol:
            verdict = "deck_restriction"
            reasons.append("deck_restriction")
        elif banned_found:
            verdict = "banned_card"
            reasons.append("banned_card")
        elif struct_reasons:
            verdict = "chain_invalid"
            reasons.extend(struct_reasons)
        elif mull_count > effective_max:
            verdict = "mulligan_exceeded"
            reasons.append("mulligan_exceeded")
        elif size_mismatch:
            verdict = "hand_size_mismatch"
            reasons.append("hand_size_mismatch")

        reasons = sorted(set(reasons))
        if verdict == "legal":
            reasons = []
            legal_count += 1
        elif verdict == "quarantined":
            quarantine_count += 1
        elif verdict == "format_suspended":
            format_suspend_count += 1
        elif verdict == "chain_invalid":
            chain_invalid_count += 1

        verdict_rows.append(
            {
                "session_id": sid,
                "deck_id": did,
                "format_id": fid,
                "verdict": verdict,
                "mulligan_count": mull_count,
                "banned_cards_found": banned_found,
                "reasons": reasons,
            }
        )

    restriction_hits = sum(1 for row in deck_rows if row["violations"])

    return {
        "session_verdicts.json": {"sessions": verdict_rows},
        "mulligan_traces.json": {"traces": trace_rows},
        "deck_restrictions.json": {"decks": deck_rows},
        "incident_ledger.json": {"applied_events": ledger},
        "summary.json": {
            "applied_incident_events": len(kept),
            "chain_invalid_sessions": chain_invalid_count,
            "deck_restriction_hits": restriction_hits,
            "format_suspended_sessions": format_suspend_count,
            "ignored_incident_events": ignored,
            "legal_sessions": legal_count,
            "quarantined_sessions": quarantine_count,
            "sessions_total": len(sessions),
        },
    }


@pytest.fixture(scope="session")
def outputs() -> dict[str, Any]:
    """Load emitted audit artifacts once per session."""
    payload: dict[str, Any] = {}
    for name in OUTPUT_FILES:
        path = audit_dir() / name
        assert path.is_file(), f"missing emitted artifact: {name}"
        payload[name] = _load_json(path)
    return payload


@pytest.fixture(scope="session")
def reference() -> dict[str, Any]:
    """Independent re-derivation of the audit bundle from inputs."""
    return compute_reference(data_dir())


class TestInputIntegrity:
    """Verify the mounted workspace matches the frozen reference bytes."""

    def test_each_input_file_sha256(self) -> None:
        """Every normative input file under the data directory must match its pinned digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = data_dir() / rel
            assert path.is_file(), f"missing input fixture: {rel}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"digest mismatch for {rel}"


class TestEnvironmentRouting:
    """Verify MCA_DATA_DIR / MCA_AUDIT_DIR resolution matches the instruction contract."""

    def test_empty_mca_data_dir_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unset or empty MCA_DATA_DIR must resolve to `/app/mulligan_pool`."""
        monkeypatch.delenv("MCA_DATA_DIR", raising=False)
        monkeypatch.setenv("MCA_DATA_DIR", "")
        assert data_dir() == Path("/app/mulligan_pool")

    def test_empty_mca_audit_dir_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unset or empty MCA_AUDIT_DIR must resolve to `/app/audit`."""
        monkeypatch.delenv("MCA_AUDIT_DIR", raising=False)
        monkeypatch.setenv("MCA_AUDIT_DIR", "")
        assert audit_dir() == Path("/app/audit")

    def test_nonempty_mca_data_dir_changes_reference_bundle(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-empty MCA_DATA_DIR must make the reference pass read from that tree instead of the default."""
        src = data_dir()
        staged = tmp_path / "pool"
        shutil.copytree(src, staged)
        monkeypatch.setenv("MCA_DATA_DIR", str(staged))
        baseline = compute_reference(data_dir())
        (staged / "sessions" / "s12.json").unlink()
        updated = compute_reference(data_dir())
        assert updated != baseline

    def test_nonempty_mca_audit_dir_reads_emitted_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A non-empty MCA_AUDIT_DIR must point artifact reads at that directory."""
        default_audit = audit_dir()
        alt = tmp_path / "alt_audit"
        shutil.copytree(default_audit, alt)
        monkeypatch.setenv("MCA_AUDIT_DIR", str(alt))
        assert audit_dir().resolve() == alt.resolve()
        for name in OUTPUT_FILES:
            path = audit_dir() / name
            assert path.is_file(), f"missing copied artifact: {name}"
            _load_json(path)


class TestReportStructure:
    """Verify emitted JSON files exist and match pinned byte and field digests."""

    def test_output_file_sha256_on_disk(self) -> None:
        """Each audit file's on-disk UTF-8 bytes must match the pinned SHA-256 digest."""
        for name, expected in EXPECTED_OUTPUT_FILE_SHA256.items():
            path = audit_dir() / name
            assert path.is_file(), f"missing emitted artifact: {name}"
            digest = _sha256_bytes(path.read_bytes())
            assert digest == expected, f"output bytes mismatch for {name}"

    def test_field_hashes(self, outputs: dict[str, Any]) -> None:
        """Selected nested fields must match their pinned canonical digests."""
        for field, expected in EXPECTED_FIELD_HASHES.items():
            top, key = field.split(".", 1)
            value = outputs[f"{top}.json"][key]
            digest = _sha256_bytes(_canonical_json_bytes(value))
            assert digest == expected, f"field hash mismatch for {field}"


class TestReferenceAgreement:
    """Cross-check emitted artifacts against an independent reference pass."""

    def test_reference_matches_outputs(self, outputs: dict[str, Any], reference: dict[str, Any]) -> None:
        """Every output file must equal the independently recomputed reference."""
        for name in OUTPUT_FILES:
            assert outputs[name] == reference[name], f"reference drift in {name}"


class TestSessionOrdering:
    """Verify deterministic ordering rules on session rows."""

    def test_session_rows_sorted_by_id(self, outputs: dict[str, Any]) -> None:
        """`sessions` must list rows in ascending ASCII `session_id` order."""
        rows = outputs["session_verdicts.json"]["sessions"]
        ids = [str(row["session_id"]) for row in rows]
        assert ids == sorted(ids)


class TestVerdictSemantics:
    """Spot-check bundled rows that exercise distinct spec branches."""

    def _row(self, outputs: dict[str, Any], sid: str) -> dict[str, Any]:
        for row in outputs["session_verdicts.json"]["sessions"]:
            if row["session_id"] == sid:
                return row
        raise AssertionError(f"missing session row {sid}")

    def test_legal_london_session(self, outputs: dict[str, Any]) -> None:
        """`s01` is a clean london keep within gold tier caps."""
        row = self._row(outputs, "s01")
        assert row["verdict"] == "legal"
        assert row["mulligan_count"] == 0
        assert row["reasons"] == []

    def test_mulligan_exceeded_session(self, outputs: dict[str, Any]) -> None:
        """`s02` exceeds the silver tier mulligan cap under vancouver sizing."""
        row = self._row(outputs, "s02")
        assert row["verdict"] == "mulligan_exceeded"
        assert row["mulligan_count"] == 4
        assert row["reasons"] == ["mulligan_exceeded"]

    def test_banned_card_session(self, outputs: dict[str, Any]) -> None:
        """`s03` keeps a card banned before its played day."""
        row = self._row(outputs, "s03")
        assert row["verdict"] == "banned_card"
        assert row["banned_cards_found"] == ["Dark Ritual"]

    def test_deck_restriction_session(self, outputs: dict[str, Any]) -> None:
        """`s04` references a deck that violates merged copy caps across formats."""
        row = self._row(outputs, "s04")
        assert row["verdict"] == "deck_restriction"
        assert row["reasons"] == ["deck_restriction"]

    def test_s09_deck_restriction_same_deck_second_format(self, outputs: dict[str, Any]) -> None:
        """`s09` ties the same physical deck to a second format so merged limits stay violated."""
        row = self._row(outputs, "s09")
        assert row["verdict"] == "deck_restriction"
        assert row["reasons"] == ["deck_restriction"]

    def test_chain_invalid_multiple_keep(self, outputs: dict[str, Any]) -> None:
        """`s10` carries two keep steps, which the spec treats as a structural chain fault."""
        row = self._row(outputs, "s10")
        assert row["verdict"] == "chain_invalid"
        assert row["reasons"] == ["multiple_keep"]

    def test_shared_pool_mulligan_exceeded(self, outputs: dict[str, Any]) -> None:
        """`s11` reuses a deck after `s08` under a tight shared pool, so one mulligan exceeds the room left."""
        row = self._row(outputs, "s11")
        assert row["verdict"] == "mulligan_exceeded"
        assert row["reasons"] == ["mulligan_exceeded"]

    def test_chain_invalid_step_index(self, outputs: dict[str, Any]) -> None:
        """`s12` mis-numbers its sole step index while still sizing the hand as london."""
        row = self._row(outputs, "s12")
        assert row["verdict"] == "chain_invalid"
        assert row["reasons"] == ["step_index_drift"]

    def test_quarantined_session(self, outputs: dict[str, Any]) -> None:
        """`s05` is quarantined by a deck compromise incident."""
        row = self._row(outputs, "s05")
        assert row["verdict"] == "quarantined"
        assert row["reasons"] == ["deck_compromise"]

    def test_format_suspended_session(self, outputs: dict[str, Any]) -> None:
        """`s06` plays modern after the format suspension day."""
        row = self._row(outputs, "s06")
        assert row["verdict"] == "format_suspended"
        assert row["reasons"] == ["format_suspend"]

    def test_hand_size_mismatch_session(self, outputs: dict[str, Any]) -> None:
        """`s07` breaks partial-paris hand sizing on the second mulligan."""
        row = self._row(outputs, "s07")
        assert row["verdict"] == "hand_size_mismatch"
        assert row["reasons"] == ["hand_size_mismatch"]

    def test_legal_vancouver_session(self, outputs: dict[str, Any]) -> None:
        """`s08` is legal with two vancouver mulligans at the gold tier cap."""
        row = self._row(outputs, "s08")
        assert row["verdict"] == "legal"
        assert row["mulligan_count"] == 2


class TestMulliganTraces:
    """Verify per-step trace flags on representative chains."""

    def _trace(self, outputs: dict[str, Any], sid: str) -> dict[str, Any]:
        for row in outputs["mulligan_traces.json"]["traces"]:
            if row["session_id"] == sid:
                return row
        raise AssertionError(f"missing trace row {sid}")

    def test_partial_paris_size_failure(self, outputs: dict[str, Any]) -> None:
        """`s07` marks step 1 as failing partial-paris size validation."""
        trace = self._trace(outputs, "s07")
        step1 = trace["steps"][1]
        assert step1["size_ok"] is False
        assert step1["hand_size"] == 6


class TestDeckRestrictions:
    """Verify deck-level restriction reporting."""

    def test_d04_lightning_bolt_violation(self, outputs: dict[str, Any]) -> None:
        """`d04` exceeds the merged Lightning Bolt cap once standard and modern limits are combined."""
        decks = outputs["deck_restrictions.json"]["decks"]
        row = next(r for r in decks if r["deck_id"] == "d04")
        assert row["violations"] == [{"card": "Lightning Bolt", "found": 2, "limit": 0}]


class TestSummary:
    """Verify aggregate counters."""

    def test_summary_totals(self, outputs: dict[str, Any]) -> None:
        """Summary counters must match the bundled session verdict mix."""
        summary = outputs["summary.json"]
        assert summary["sessions_total"] == 12
        assert summary["legal_sessions"] == 2
        assert summary["quarantined_sessions"] == 1
        assert summary["format_suspended_sessions"] == 1
        assert summary["deck_restriction_hits"] == 1
        assert summary["chain_invalid_sessions"] == 2
        assert summary["applied_incident_events"] == 3
        assert summary["ignored_incident_events"] == 3
