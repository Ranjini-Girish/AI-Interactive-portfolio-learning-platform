"""Verifier suite for gossip-presence-replay (hard, Rust implementation)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

LAB_ROOT = Path(os.environ.get("GSP_LAB_ROOT", "/app/gossip_lab"))
OUT_DIR = Path(os.environ.get("GSP_OUT_DIR", "/app/output"))
REPORT = OUT_DIR / "gossip_report.json"

EXPECTED_INPUT_HASHES = {
    "SPEC.md": "a9bad8d632cb2094cde6b98b01e75c2d8a7b662008cd9dad620b68f8cc1b6c10",
    "corpus/void.txt": "b1b7a8fa6945fd110863261fcf3c6320b22c018b37667f356133d137d2e7a683",
    "inbox/events.log": "a3fa0d5f75d26ddf8b74cafbe74ffb1cc4fe8625ce20004b3f6bbd2480126e05",
    "inbox/events_overflow.log": "c35ad4daf270b2ade0d024a7a9ea8f2ad0dce8a49137c63bc5f6e43e17aecb05",
    "retainers/ret-01.txt": "3b30e39004e7c28b9526e8f5f04ee549718eb86aeba2f25c8f96a11ac6d71218",
    "retainers/ret-02.txt": "089b5ec1f80e499a079a0013da2a583acf8153834add6b04423c903b35d88631",
    "retainers/ret-03.txt": "2ec060c1edb176fed9fb05182c06a781715449612af8d89a1bcda6d1d8c71d9b",
    "retainers/ret-04.txt": "c09566d923dbbd339da19812af7d0349fd8ba375c821c6261e953f43f87fd4a2",
    "retainers/ret-05.txt": "7171ed8002d7a95f23028c33d5c91de0891f4d126f09e438e0576f062c40f5ba",
    "retainers/ret-06.txt": "51b6351a15eb58ab9662cd1154f99fa85e52351778f48457877bc521b6cc7185",
    "retainers/ret-07.txt": "35465f9402cca5935f61552c145642b08419f5afff095aa7d83756d22327b62d",
    "retainers/ret-08.txt": "d5efb14ae03f544d0f02953d758cedfdb4faaaab172739a8130f62b495bb35a4",
    "retainers/ret-09.txt": "46a3360ec4b5d9ad383bf87b89ae61f9d9983f66ee3b370e20098b3c53b4b158",
    "retainers/ret-10.txt": "bf79ecbacc83a21e3afa3b00da1d7404b9b970caac0d3351002a96a886758c41",
    "retainers/ret-11.txt": "ef592566d169f0f8b8a0c5424e7da22e35399e1ff5a3222eeab7474c56b66045",
    "retainers/ret-12.txt": "0ab11a9a4e89e8ba2e2d9873902cdf58f9f594eb16c953d947889bc14adcd8b9",
    "retainers/ret-13.txt": "3828ec7303eae139ff8f0c460842bc22df67a3b2de83dbb9eaf59a78543ae006",
    "retainers/ret-14.txt": "023090a29cd13d741d12f417517b16fdbedd070aad9ae0599f6e7ed369e706f6",
    "retainers/ret-15.txt": "9d9f37318088d8b009186691f8b62725ec6218f2d1a73f7c0b69f939d2ccb001",
    "retainers/ret-16.txt": "5e2d9316101f36fdbf77c7d558dbb3a7fb9ad8d205dcf7b7dc4b73983e35e1af",
    "retainers/ret-17.txt": "277b817a96ebb46aca4783849f0be88fb4aa28177b3749cb21b7c8246713132b",
    "retainers/ret-18.txt": "f2f2054229b3251c3f0b03cdd213944ae566a97fec32ad19380b5c6b02cd8b25",
}

EXPECTED_OUTPUT_CANONICAL_HASHES = {
    "gossip_report.json": "59afecb43f066decd734c252d71ce4e80efa364dfc5db0b120d70256b809785f",
}

EXPECTED_FIELD_HASHES = {
    "canonical_replay": "22822fdf45d7051f788d0b9b2e635170b39b228e35592144ba237a4194f9db3a",
    "edge_totals": "e6a8d416d92d79c3f1cd596874bbcd0ec74ba34be26b0044e012138bf34d9020",
    "nodes": "1596a77a3a3271d5ba30e878c0be8040332b77b911405cc4442fb9a79aca2137",
    "per_update": "95881fffd7f4b1118fd63513523dd1c47933c81ed849c9414aa1c4dae156e4a1",
    "round_snapshots": "930b65a429df7c2e6cb706a34e9fdcf1128d9d58417b0436152a9ba402f24b13",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canon_disk(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _field_canon(obj: Any) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    ).encode("utf-8")


def _field_sha(obj: Any) -> str:
    return hashlib.sha256(_field_canon(obj)).hexdigest()


def _parse_lines(text: str) -> list[tuple[int, str, str, str, str]]:
    out: list[tuple[int, str, str, str, str]] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.match(r"^(\d+)\s+(\S+)\s+(\S+)\s+(push|pull)\s+(\S+)\s*$", line)
        if not m:
            raise ValueError(f"bad line: {raw!r}")
        out.append(
            (
                int(m.group(1)),
                m.group(2),
                m.group(3),
                m.group(4),
                m.group(5),
            )
        )
    return out


def _all_digits(s: str) -> bool:
    return len(s) > 0 and all(c.isdigit() for c in s)


def reference_report(lab: Path) -> dict[str, Any]:
    """Re-derive the gossip report from SPEC.md rules (independent of any bundled tool)."""
    main_txt = (lab / "inbox" / "events.log").read_text(encoding="utf-8")
    over_txt = (lab / "inbox" / "events_overflow.log").read_text(encoding="utf-8")
    events = _parse_lines(main_txt) + _parse_lines(over_txt)

    nodes: set[str] = set()
    marks: set[tuple[str, str]] = set()
    first_round: dict[str, int] = {}
    last_round: dict[str, int] = {}
    edge_counts: dict[str, int] = {}
    last_line_idx_for_update: dict[str, int] = {}
    canon_lines: list[str] = []

    for idx, (r, a, b, verb, uid) in enumerate(events):
        canon_lines.append(f"{r} {a} {b} {verb} {uid}")
        nodes.add(a)
        nodes.add(b)
        marks.add((a, uid))
        marks.add((b, uid))
        if uid not in first_round:
            first_round[uid] = r
        last_round[uid] = r
        ek = f"{a}>{b}"
        edge_counts[ek] = edge_counts.get(ek, 0) + 1
        last_line_idx_for_update[uid] = idx

    node_list = sorted(nodes)
    uids = sorted(set(first_round), key=lambda u: (0, int(u)) if _all_digits(u) else (1, u))

    max_round = max((r for r, *_ in events), default=0)

    pull_last_hits = 0
    for uid in uids:
        li = last_line_idx_for_update[uid]
        if events[li][3] == "pull":
            pull_last_hits += 1

    round_snapshots: dict[str, dict[str, list[str]]] = {}
    for k in range(1, max_round + 1):
        snap: dict[str, list[str]] = {}
        for n in node_list:
            have: list[str] = []
            for u in uids:
                if first_round[u] <= k and (n, u) in marks:
                    have.append(u)
            snap[n] = have
        round_snapshots[str(k)] = snap

    per_update: dict[str, dict[str, int]] = {}
    for u in uids:
        fr = first_round[u]
        lr = last_round[u]
        per_update[u] = {
            "first_round": fr,
            "last_round": lr,
            "propagation_delay": lr - fr + 1,
        }

    edge_totals = dict(sorted(edge_counts.items()))

    return {
        "canonical_replay": canon_lines,
        "edge_totals": edge_totals,
        "max_round": max_round,
        "nodes": node_list,
        "per_update": per_update,
        "pull_last_hits": pull_last_hits,
        "round_snapshots": round_snapshots,
    }


class TestInputIntegrity:
    """Ensure bundled lab files are unchanged."""

    def test_all_input_digests(self) -> None:
        """Every corpus file under the lab root must match the frozen digest."""
        for rel, expected in EXPECTED_INPUT_HASHES.items():
            path = LAB_ROOT / rel
            assert path.is_file(), f"missing {rel}"
            assert _sha256_file(path) == expected, f"digest mismatch {rel}"


class TestReportArtifact:
    """Check the emitted gossip_report.json."""

    def test_report_exists(self) -> None:
        """The auditor must emit gossip_report.json under the output directory."""
        assert REPORT.is_file(), "gossip_report.json missing"

    def test_output_canonical_hash(self) -> None:
        """Byte-stable JSON layout matches the frozen digest."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        got = hashlib.sha256(_canon_disk(raw).encode("utf-8")).hexdigest()
        assert got == EXPECTED_OUTPUT_CANONICAL_HASHES["gossip_report.json"]

    def test_field_hashes(self) -> None:
        """Major nested sections match independent field digests."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        for field, exp in EXPECTED_FIELD_HASHES.items():
            assert _field_sha(raw[field]) == exp, field

    def test_top_level_keys_only(self) -> None:
        """No extra top-level keys beyond the seven contract fields."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        assert set(raw.keys()) == {
            "canonical_replay",
            "edge_totals",
            "max_round",
            "nodes",
            "per_update",
            "pull_last_hits",
            "round_snapshots",
        }

    def test_scalar_metrics(self) -> None:
        """Bundled overflow tail shifts update 2 while preserving pull-tail score."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        assert raw["max_round"] == 5
        assert raw["pull_last_hits"] == 5
        assert raw["per_update"]["2"]["last_round"] == 5
        assert raw["per_update"]["2"]["propagation_delay"] == 4

    def test_reference_matches_disk(self) -> None:
        """Disk report matches an independent re-derivation from the inbox logs."""
        ref = reference_report(LAB_ROOT)
        disk = json.loads(REPORT.read_text(encoding="utf-8"))
        assert ref == disk


class TestSemanticCoverage:
    """Spot-check behaviours documented in SPEC.md."""

    def test_round_one_presence_snapshot(self) -> None:
        """Round one witness rows match the presence ledger for the first round."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        r1 = raw["round_snapshots"]["1"]
        assert r1["A"] == ["1"]
        assert r1["B"] == ["1"]
        assert r1["C"] == ["1"]
        assert r1["D"] == []
        assert r1["F"] == []

    def test_edge_histogram_includes_overflow_edge(self) -> None:
        """Overflow append introduces the F>B directed edge once."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        assert raw["edge_totals"]["F>B"] == 1

    def test_canonical_replay_line_count(self) -> None:
        """Merged stream length is main plus overflow record lines."""
        raw = json.loads(REPORT.read_text(encoding="utf-8"))
        assert len(raw["canonical_replay"]) == 11
