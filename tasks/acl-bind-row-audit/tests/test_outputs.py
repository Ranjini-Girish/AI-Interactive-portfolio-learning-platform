"""Verifier suite for acl-bind-row-audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("ABR_DATA_DIR", "/app/abr_lab"))
AUDIT_DIR = Path(os.environ.get("ABR_AUDIT_DIR", "/app/abr_audit"))

GRANT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.json$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "752a08364978d591d2ea75ee0d891f2650dc54753428d456f38cd1aaae11c0f3",
    "anchors/band.json": "9ae145f334ab23e47c96d5fb9818d3d555358104bd2465bed66f05d1509f5c85",
    "anchors/phase.json": "d14af1c45c4b47d1c597f097c0122be23d85e9c76defeda198e8ba902312c0e5",
    "ancillary/extra.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/notes.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/readme.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/stub.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "grants/ch01.json": "fb3352bc449650855ea394e03c1cb85cc4a1374a90ab72ede12289beb7b71569",
    "grants/ch02.json": "b8b90a930c2300462fb8a43fff3ec9c4240949db92ac88ff884917ae62c8185c",
    "grants/ch03.json": "c2bcb4ee39bbc4bccd8b65036da3527ff0621f5259d45ffdb625c2f52780530b",
    "grants/ch04.json": "67e38c3d94547ce77b80258026f884db26484a060fa34a8514630d0e3dd8af4c",
    "grants/ch05.json": "cf48f80ec5954e23f9e246620e1a5631613527f6110b5b192459a1993a5cdccc",
    "grants/ch06.json": "4e06a6537984954c3a95fca80a0d793eba72231113fe080b02a6f4c56351ed03",
    "grants/ch07.json": "4c9ee642b864fc830c6cad4b06380ee9d6918f7f54dfcf3e9ad02b8cecd9cd0b",
    "grants/ch08.json": "7cad07183fa3a7deb8e83add87f592eac73d5f6c4cce60901c0637b40431419a",
    "grants/ch09.json": "91648f3884a3d73541574ae1a55a6eaf36e1284f8d5a2f2026cbc3efc239c9e9",
    "grants/ch10.json": "cf7eb892dfa94877c442b5f1d2d3d99b7fa62872ca881487a3f6637cdb5a6695",
    "grants/ch11.json": "8cbdb24f6aab976a80452ebe60a3b754ba53876bbd5466cff73d2822c0b1a000",
    "grants/ch12.json": "5246f9f930a729d63caa18a70d587133d617265f53b94bfff54757d632ec7dfe",
    "incident_log.json": "d4292e88c246efaba1cdcd6bdae21d1ce70aabb81109c383abe7caf1288a57d2",
    "policy.json": "ca3d163bab055381827226140568f3bef7eaac187cebd76878e0b63e9e442356",
    "pool_state.json": "d6dbba0006e3e3053f6e5938378861e3947cfe6fcae6d035cea7ca5d9c3f0d80",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "report.json": "d821678b58cb975907789ffc2369f3be9f609a944934e220f8129610d3698ff7",
}

EXPECTED_FIELD_HASHES = {
    "objects": "5b580b25737eec5efb11133b76687bb09f542c4fb5aa8a485e4d6b928570dcc8",
    "summary": "e7494aa29283497d8fc3dca0ad5e3662599fb73b479173c65b036efdfe8a8aa2",
}


def _int_from(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and (v.isdigit() or (v.startswith("-") and v[1:].isdigit())):
        return int(v)
    return None


def _sort_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        events,
        key=lambda e: (_int_from(e.get("apply_step")) or 0, str(e.get("event_id", ""))),
    )


def _u32(v: int) -> int:
    return v & 0xFFFFFFFF


def _compute_reference() -> dict[str, object]:
    pool = _load_json(DATA_DIR / "pool_state.json")
    log = _load_json(DATA_DIR / "incident_log.json")
    assert isinstance(pool, dict) and isinstance(log, dict)
    cur = int(pool["current_step"])
    events = [e for e in log.get("events", []) if isinstance(e, dict)]
    sorted_ev = _sort_events(events)
    events_seen = len(sorted_ev)

    paths = sorted(p for p in DATA_DIR.joinpath("grants").glob("*.json") if GRANT_RE.match(p.name))
    rows: list[dict[str, object]] = []
    for p in paths:
        g = _load_json(p)
        assert isinstance(g, dict)
        rows.append(
            {
                "subject": str(g["subject"]),
                "object_id": str(g["object_id"]),
                "rights": _u32(int(g["rights"])),
            }
        )
    rows_loaded = len(rows)

    unknown = 0
    for ev in sorted_ev:
        st = _int_from(ev.get("apply_step"))
        if st is None or st > cur:
            continue
        kind = str(ev.get("kind", ""))
        if kind == "noop":
            continue
        if kind == "revoke_bits":
            oid = str(ev.get("object_id", ""))
            mk = _int_from(ev.get("mask"))
            if not oid or mk is None:
                continue
            mask = _u32(mk)
            inv = (~mask) & 0xFFFFFFFF
            for r in rows:
                if str(r["object_id"]) != oid:
                    continue
                r["rights"] = int(r["rights"]) & inv
            continue
        unknown += 1

    grp: dict[str, dict[str, object]] = {}
    for r in rows:
        oid = str(r["object_id"])
        if oid not in grp:
            grp[oid] = {"comb": 0, "subs": set()}
        g = grp[oid]
        assert isinstance(g["comb"], int)
        g["comb"] = int(g["comb"]) | int(r["rights"])
        assert isinstance(g["subs"], set)
        g["subs"].add(str(r["subject"]))

    objects: list[dict[str, object]] = []
    for oid in sorted(grp.keys()):
        g = grp[oid]
        subs = sorted(g["subs"])
        assert isinstance(subs, list)
        objects.append(
            {
                "combined_rights": int(g["comb"]),
                "id": oid,
                "subjects": subs,
            }
        )

    return {
        "objects": objects,
        "summary": {
            "events_seen": events_seen,
            "objects_considered": len(objects),
            "rows_loaded": rows_loaded,
            "unknown_event_kinds": unknown,
        },
    }


class TestInputIntegrity:
    """Pinned digests for lab inputs."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hashes(self, rel: str) -> None:
        """Each relative path matches its digest."""
        path = DATA_DIR / rel
        assert path.is_file(), f"missing {rel}"
        assert _sha256_bytes(path.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestReportStructure:
    """Report file checks."""

    def test_report_exists(self) -> None:
        """Single JSON output is required."""
        assert (AUDIT_DIR / "report.json").is_file()

    def test_report_semantic_hash(self) -> None:
        """Compact canonical digest matches."""
        obj = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        assert _sha256_bytes(_canonical(obj).encode("utf-8")) == EXPECTED_OUTPUT_CANONICAL_HASHES["report.json"]

    def test_field_hashes(self) -> None:
        """Section hashes."""
        obj = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        assert isinstance(obj, dict)
        for key, exp in EXPECTED_FIELD_HASHES.items():
            got = _sha256_bytes(_canonical(obj[key]).encode("utf-8"))
            assert got == exp


class TestReferenceAgreement:
    """Independent computation."""

    def test_matches_reference(self) -> None:
        """Normalized JSON matches reference."""
        actual = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        expected = _compute_reference()
        assert _canonical(actual) == _canonical(expected)


class TestBranches:
    """Dataset-specific coverage."""

    def test_revoke_on_obj_a(self) -> None:
        """Mask two clears bit one on the sole obj-a row."""
        ref = _compute_reference()
        row = next(x for x in ref["objects"] if x["id"] == "obj-a")
        assert int(row["combined_rights"]) == 5

    def test_unknown_increment(self) -> None:
        """Honored mystery kind increments counter."""
        ref = _compute_reference()
        assert ref["summary"]["unknown_event_kinds"] == 1
