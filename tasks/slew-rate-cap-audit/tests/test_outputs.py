"""Verifier suite for slew-rate-cap-audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("SRL_DATA_DIR", "/app/srl_lab"))
AUDIT_DIR = Path(os.environ.get("SRL_AUDIT_DIR", "/app/srl_audit"))

CH_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.json$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "af6c396354511a08f16bf3c1b33054cbe9f5187563e0e49fbabd505619e8ed18",
    "anchors/band.json": "9ae145f334ab23e47c96d5fb9818d3d555358104bd2465bed66f05d1509f5c85",
    "anchors/phase.json": "d14af1c45c4b47d1c597f097c0122be23d85e9c76defeda198e8ba902312c0e5",
    "ancillary/extra.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/notes.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/readme.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/stub.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "channels/ch01.json": "0aba02b403764f5506da20a2a848516a92e1d94224275390718f8205749ab4da",
    "channels/ch02.json": "82f958bbb1b5bfaf5d4073da218d65e37502506784c0632abf0b7ec4ac9c49ed",
    "channels/ch03.json": "7c24f5bfdb35ac86e60381c97e0e71dee2b89f56deef70fcbb0962486f2ab042",
    "channels/ch04.json": "554c7b0825495b503b0f565d6f6e5861532e4eb7bcd1cc09dff17658cb5fe54a",
    "channels/ch05.json": "b937b3d8db60f8d3f4f290c1aa7757264c8a698b695fd63da6486a958b2e33e2",
    "channels/ch06.json": "d69eedd3a7db15f63ac87c57fdbd051461016644da40188516329105903772ff",
    "channels/ch07.json": "327fce362420fb410c5d72245d85dea90eab0f944d8edb7ac6537a517e3d3dcf",
    "channels/ch08.json": "2d68c88cc8ed5d7fb71f46dda67b3b4d70feb8910e90611d77d874f45c52d40d",
    "channels/ch09.json": "3ffa6b8f7dce5cc065cc00a8fe1f61726795d4bf691345cd5c3d8ddc69a8968b",
    "channels/ch10.json": "fb825202eb4af3f40dc03a08ff6a8d8fe90e4b506889b299623c8b17315d8be8",
    "channels/ch11.json": "415a0090e813c8047e688a4ff200a93f8c23df1c1f9f105807c95c37374d58ea",
    "channels/ch12.json": "bf3c75bc8b7b8b9309c40bd62cbfc42087b607454d1efe5d1fde2ec062f8742f",
    "incident_log.json": "5e233d06edaed6ffc86a8d3891dba8628238015bb9ffa085b2b4ef279b6979ad",
    "policy.json": "c2450f9088992a20dac5599750a669238fde25260be0e917679acc10a9ab27db",
    "pool_state.json": "e1464a75e58b12f0f3f75c838c0de3eef4123aa4dc4343512c2b7de94a25e7ca",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "report.json": "75d7b6e9c72e31bd51fac5e654cae3fc4e12b5d58184ed11bd711649b9e5fdcd",
}

EXPECTED_FIELD_HASHES = {
    "channels": "2c718c7db0ba730e36b057b4113512877a18af2cb10e5416415c34df22ddb82e",
    "summary": "df7a5ee821a26d1793a28030e7573406f74c2dc4af0a59117b73bf6464a18c98",
}


def _int_from(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.isdigit():
        return int(v)
    return None


def _sort_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        events,
        key=lambda e: (_int_from(e.get("apply_t")) or 0, str(e.get("event_id", ""))),
    )


def _collapse(points: list[dict[str, object]], tie_break: str) -> list[dict[str, int]]:
    pts = sorted(
        points,
        key=lambda p: (
            int(p["t"]),
            str(p["channel_id"]),
            str(p["base"]),
        ),
    )
    if not pts:
        return []
    out = [dict(pts[0])]
    for cur in pts[1:]:
        if int(cur["t"]) == int(out[-1]["t"]):
            if tie_break == "max_v":
                if int(cur["v"]) > int(out[-1]["v"]):
                    out[-1]["v"] = int(cur["v"])
            else:
                if int(cur["v"]) < int(out[-1]["v"]):
                    out[-1]["v"] = int(cur["v"])
        else:
            out.append(dict(cur))
    return [{"t": int(p["t"]), "v": int(p["v"])} for p in out]


def _max_slew_milli(points: list[dict[str, int]], cap: int) -> tuple[int, bool]:
    if len(points) < 2:
        return 0, False
    pts = sorted(points, key=lambda p: p["t"])
    max_s = 0
    for i in range(1, len(pts)):
        dt = pts[i]["t"] - pts[i - 1]["t"]
        assert dt > 0
        slew = abs(pts[i]["v"] - pts[i - 1]["v"]) * 1000 // dt
        if slew > max_s:
            max_s = slew
    return max_s, max_s > cap


def _compute_reference() -> dict[str, object]:
    pol = _load_json(DATA_DIR / "policy.json")
    pool = _load_json(DATA_DIR / "pool_state.json")
    log = _load_json(DATA_DIR / "incident_log.json")
    assert isinstance(pol, dict) and isinstance(pool, dict) and isinstance(log, dict)
    cap = int(pol["slew_cap_milli"])
    merge_by_tag = bool(pol["merge_by_tag"])
    tie_break = str(pol["tie_break_dup_t"])
    current_t = int(pool["current_t"])
    events = log.get("events", [])
    assert isinstance(events, list)
    evs = [e for e in events if isinstance(e, dict)]

    paths = sorted(DATA_DIR.joinpath("channels").glob("*.json"))
    paths = [p for p in paths if CH_RE.match(p.name)]
    loaded: list[tuple[Path, dict[str, object]]] = []
    for p in paths:
        obj = _load_json(p)
        assert isinstance(obj, dict)
        loaded.append((p, obj))

    by_cid: dict[str, list[dict[str, object]]] = {}
    for p, obj in loaded:
        cid = str(obj["channel_id"])
        base = p.name
        lst = by_cid.setdefault(cid, [])
        for q in obj.get("points", []):
            assert isinstance(q, dict)
            lst.append(
                {
                    "t": int(q["t"]),
                    "v": int(q["v"]),
                    "channel_id": cid,
                    "base": base,
                }
            )

    events_seen = 0
    unknown_kinds = 0
    for ev in _sort_events(evs):
        events_seen += 1
        at = _int_from(ev.get("apply_t"))
        if at is None or at > current_t:
            continue
        kind = str(ev.get("kind", ""))
        if kind == "zero_window":
            cid = str(ev.get("channel_id", ""))
            st = _int_from(ev.get("start_t"))
            en = _int_from(ev.get("end_t"))
            if st is None or en is None or st > en:
                continue
            arr = by_cid.get(cid)
            if not arr:
                continue
            for row in arr:
                if st <= int(row["t"]) <= en:
                    row["v"] = 0
        elif kind == "noop":
            pass
        else:
            unknown_kinds += 1

    series: list[dict[str, object]] = []

    def merge_id(ids: list[str]) -> str:
        u = sorted(set(ids))
        return u[0] if len(u) == 1 else "+".join(u)

    if not merge_by_tag:
        for _p, obj in loaded:
            cid = str(obj["channel_id"])
            pts = [{"t": int(x["t"]), "v": int(x["v"])} for x in by_cid[cid]]
            ms, br = _max_slew_milli(pts, cap)
            series.append(
                {
                    "breach": br,
                    "id": cid,
                    "max_slew_milli": ms,
                    "points": len(pts),
                }
            )
    else:
        tag_to: dict[str, list[dict[str, object]]] = {}
        tag_ids: dict[str, list[str]] = {}
        for p, obj in loaded:
            tag = str(obj["tag"])
            cid = str(obj["channel_id"])
            tag_to.setdefault(tag, []).extend(by_cid[cid])
            tag_ids.setdefault(tag, []).append(cid)
        for tag in sorted(tag_to.keys()):
            pts_raw = tag_to[tag]
            collapsed = _collapse(pts_raw, tie_break)
            ms, br = _max_slew_milli(collapsed, cap)
            npts = len(collapsed)
            series.append(
                {
                    "breach": br,
                    "id": merge_id(tag_ids[tag]),
                    "max_slew_milli": ms,
                    "points": npts,
                }
            )

    series = sorted(series, key=lambda s: str(s["id"]))
    breach_count = sum(1 for s in series if s["breach"])
    max_overall = max((int(s["max_slew_milli"]) for s in series), default=0)
    return {
        "channels": series,
        "summary": {
            "breach_count": breach_count,
            "channels_considered": len(series),
            "events_seen": events_seen,
            "max_overall_milli": max_overall,
            "unknown_event_kinds": unknown_kinds,
        },
    }


class TestInputIntegrity:
    """SHA-256 pins on every bundled input under the lab directory."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hashes(self, rel: str) -> None:
        """Each relative path must match the pinned digest."""
        path = DATA_DIR / rel
        assert path.is_file(), f"missing {rel}"
        assert _sha256_bytes(path.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestReportStructure:
    """Output path and canonical semantic hash."""

    def test_report_exists(self) -> None:
        """The audit must emit the single report path."""
        out = AUDIT_DIR / "report.json"
        assert out.is_file()

    def test_report_semantic_hash(self) -> None:
        """Parsed JSON must normalize to the pinned compact digest."""
        raw = (AUDIT_DIR / "report.json").read_text(encoding="utf-8")
        obj = json.loads(raw)
        digest = _sha256_bytes(_canonical(obj).encode("utf-8"))
        assert digest == EXPECTED_OUTPUT_CANONICAL_HASHES["report.json"]

    def test_field_hashes(self) -> None:
        """Top-level sections hash independently."""
        obj = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        assert isinstance(obj, dict)
        for key, exp in EXPECTED_FIELD_HASHES.items():
            assert key in obj
            got = _sha256_bytes(_canonical(obj[key]).encode("utf-8"))
            assert got == exp


class TestReferenceAgreement:
    """Independent re-derivation matches emitted report."""

    def test_matches_reference(self) -> None:
        """Every field equals the reference built from the spec."""
        actual = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        expected = _compute_reference()
        assert _canonical(actual) == _canonical(expected)


class TestDatasetBranches:
    """Positive coverage for merged breach and unknown kind counters."""

    def test_unknown_event_counted(self) -> None:
        """Honored-time unknown kinds bump the counter."""
        ref = _compute_reference()
        assert ref["summary"]["unknown_event_kinds"] == 1

    def test_merge_tag_active(self) -> None:
        """Merged ids use ASCII-sorted join with plus signs."""
        ref = _compute_reference()
        ids = {str(x["id"]) for x in ref["channels"]}
        assert "alpha+beta" in ids
        assert "delta+gamma" in ids

    def test_breach_count_semantics(self) -> None:
        """Two merged series exceed the milli cap."""
        ref = _compute_reference()
        assert ref["summary"]["breach_count"] == 2
