"""Verifier suite for ht-span-gap-audit."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pytest

DATA_DIR = Path(os.environ.get("HSG_DATA_DIR", "/app/hsg_lab"))
AUDIT_DIR = Path(os.environ.get("HSG_AUDIT_DIR", "/app/hsg_audit"))

LANE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.json$")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


EXPECTED_INPUT_HASHES = {
    "SPEC.md": "44791263a031ff3036b0df4f228f9ab4cb24a240f0c4e7d880eef3c477b2709c",
    "anchors/band.json": "9ae145f334ab23e47c96d5fb9818d3d555358104bd2465bed66f05d1509f5c85",
    "anchors/phase.json": "d14af1c45c4b47d1c597f097c0122be23d85e9c76defeda198e8ba902312c0e5",
    "ancillary/extra.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/notes.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/readme.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "ancillary/stub.json": "fe98ebff6831df72ad0cfaa257dfc2619e8224b167814d340a98fa9b9c503899",
    "incident_log.json": "7eacde0d064f2aa988b453a6dfbbd415129ffab492db8cf93a66a733ef5ffb10",
    "lanes/ch01.json": "ebd22d62bd15e17c0adf5d8daaefb4cccc68c2578aec2549ec6fab9de04d0f44",
    "lanes/ch02.json": "915dac00d3eabeed0ed159ce7a377065d759a31f487990637246ed885739e385",
    "lanes/ch03.json": "52b853ab1c55f063ba02ee06a5431c3438f12b9860cb84e4bb5a30e4b22752cb",
    "lanes/ch04.json": "bf3e5f4a5b29d1ecc701e76cf33e793b8a621462d7c12118f53f2593ef5213c6",
    "lanes/ch05.json": "0d4d063f79f64a35086c12414defc3386d6eb9860961eca66bd75710c86c4e5e",
    "lanes/ch06.json": "f9f4102bb663e1a4a106a742a2355efbd828a76ae3d4505a8b8cbe11e81ddda3",
    "lanes/ch07.json": "11452f60bd70aa908d4df29027430652b772079f65562736cce23707979948cd",
    "lanes/ch08.json": "1b5a8eb8ea1de80910d3f43cc983e651b6405df5ebb96d033a9d58db34b8f629",
    "lanes/ch09.json": "f19b3da13058e42a6fae778fa4f3688395402a322d2cefa9f865dd3e5b05d17f",
    "lanes/ch10.json": "f9d507bf308721c0ec8ddb8193d485b38b20173468835e8a712d020d678b3066",
    "lanes/ch11.json": "cd09a9e206b095c87ccc6c9832bbdd54d0026a774b296fb99dce7223b5f764ef",
    "lanes/ch12.json": "da31c5cd154459134aa3b9d07a1bcbcbdd818d91ded1e055ec90e1bae7058239",
    "policy.json": "bf7c3d7e1ac8b988956f00b146f4ddd7be94da4315a7c402d92f27e1cbe6e2f7",
    "pool_state.json": "0ee09429864f8f2edb5324fc4fc8923a728d1939e7bdfe4cc01d428ea6dd4ab3",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "report.json": "efbe24202e746cc58d73a5971907ce96cac9916fe5a6d7118710fe6b2ac1c29d",
}

EXPECTED_FIELD_HASHES = {
    "lanes": "9bf021453fccef2f9902056adc55af5aaa68ad217ca100992226ddbaf66f6683",
    "summary": "e0b31729c2ddec17c48aeb2a0966933f5812f1f508b17f7cc5b7bc0946396bd5",
}


def _int_from(v: object) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str) and v.lstrip("-").isdigit():
        return int(v)
    return None


def _sort_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        events,
        key=lambda e: (_int_from(e.get("apply_tick")) or 0, str(e.get("event_id", ""))),
    )


def _merge_intervals(raw: list[tuple[int, int]], gap: int) -> list[tuple[int, int]]:
    if not raw:
        return []
    pts = sorted(raw, key=lambda x: (x[0], x[1]))
    out = [pts[0]]
    for lo, hi in pts[1:]:
        top_lo, top_hi = out[-1]
        if lo - top_hi <= gap:
            if hi > top_hi:
                out[-1] = (top_lo, hi)
        else:
            out.append((lo, hi))
    return out


def _compute_reference() -> dict[str, object]:
    pol = _load_json(DATA_DIR / "policy.json")
    pool = _load_json(DATA_DIR / "pool_state.json")
    log = _load_json(DATA_DIR / "incident_log.json")
    assert isinstance(pol, dict) and isinstance(pool, dict) and isinstance(log, dict)
    gap = int(pol["merge_gap"])
    cur = int(pool["current_tick"])
    events = [e for e in log.get("events", []) if isinstance(e, dict)]
    sorted_ev = _sort_events(events)
    events_seen = len(sorted_ev)

    paths = sorted(p for p in DATA_DIR.joinpath("lanes").glob("*.json") if LANE_RE.match(p.name))
    loaded: list[tuple[Path, dict[str, object]]] = []
    for p in paths:
        obj = _load_json(p)
        assert isinstance(obj, dict)
        loaded.append((p, obj))

    by_lane: dict[str, list[tuple[int, int]]] = {}
    for _p, obj in loaded:
        lid = str(obj["lane_id"])
        for it in obj.get("intervals", []):
            assert isinstance(it, dict)
            lo = int(it["lo"])
            hi = int(it["hi"])
            by_lane.setdefault(lid, []).append((lo, hi))

    unknown = 0
    for ev in sorted_ev:
        at = _int_from(ev.get("apply_tick"))
        if at is None or at > cur:
            continue
        kind = str(ev.get("kind", ""))
        if kind == "noop":
            continue
        if kind == "drop_tick":
            lid = str(ev.get("lane_id", ""))
            tk = _int_from(ev.get("tick"))
            if not lid or tk is None:
                continue
            arr = by_lane.get(lid, [])
            by_lane[lid] = [seg for seg in arr if not (seg[0] <= tk < seg[1])]
            continue
        unknown += 1

    lanes: list[dict[str, object]] = []
    for _p, obj in loaded:
        lid = str(obj["lane_id"])
        merged = _merge_intervals(list(by_lane.get(lid, [])), gap)
        covered = sum(hi - lo for lo, hi in merged)
        lanes.append(
            {
                "covered_ticks": covered,
                "id": lid,
                "merged_count": len(merged),
            }
        )
    lanes = sorted(lanes, key=lambda x: str(x["id"]))
    total = sum(int(x["covered_ticks"]) for x in lanes)
    return {
        "lanes": lanes,
        "summary": {
            "covered_ticks_total": total,
            "events_seen": events_seen,
            "lanes_considered": len(lanes),
            "unknown_event_kinds": unknown,
        },
    }


class TestInputIntegrity:
    """Pinned digests for every lab input."""

    @pytest.mark.parametrize("rel", sorted(EXPECTED_INPUT_HASHES.keys()))
    def test_input_hashes(self, rel: str) -> None:
        """Each lab-relative file matches its digest."""
        path = DATA_DIR / rel
        assert path.is_file(), f"missing {rel}"
        assert _sha256_bytes(path.read_bytes()) == EXPECTED_INPUT_HASHES[rel]


class TestReportStructure:
    """Report path and semantic hashes."""

    def test_report_exists(self) -> None:
        """Single JSON output is required."""
        assert (AUDIT_DIR / "report.json").is_file()

    def test_report_semantic_hash(self) -> None:
        """Compact canonical digest matches."""
        obj = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        assert _sha256_bytes(_canonical(obj).encode("utf-8")) == EXPECTED_OUTPUT_CANONICAL_HASHES["report.json"]

    def test_field_hashes(self) -> None:
        """Section-level hashes."""
        obj = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        assert isinstance(obj, dict)
        for key, exp in EXPECTED_FIELD_HASHES.items():
            got = _sha256_bytes(_canonical(obj[key]).encode("utf-8"))
            assert got == exp


class TestReferenceAgreement:
    """Reference re-derivation."""

    def test_matches_reference(self) -> None:
        """Normalized JSON matches independent computation."""
        actual = json.loads((AUDIT_DIR / "report.json").read_text(encoding="utf-8"))
        expected = _compute_reference()
        assert _canonical(actual) == _canonical(expected)


class TestBranches:
    """Dataset-specific rules."""

    def test_drop_tick_applied(self) -> None:
        """lane-a loses the interval hit by tick four before merge."""
        ref = _compute_reference()
        lane_a = next(x for x in ref["lanes"] if x["id"] == "lane-a")
        assert int(lane_a["covered_ticks"]) == 2

    def test_unknown_kind_counted(self) -> None:
        """Honored mystery kind increments counter."""
        ref = _compute_reference()
        assert ref["summary"]["unknown_event_kinds"] == 1
