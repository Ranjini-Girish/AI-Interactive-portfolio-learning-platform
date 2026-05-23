"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest



def _java_cmd(data_dir: Path, out_dir: Path) -> list[str]:
    """Build argv for the Java entry class."""
    return [
        "java",
        "-cp",
        f"{BUILD_DIR}:{GSON_CP}",
        JAVA_CLASS,
        str(data_dir),
        str(out_dir),
    ]




SOURCE_SUFFIXES = (".java",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {"Makefile", "GNUmakefile", "makefile",
                      "CMakeLists.txt", "build.ninja"}


def _src_files() -> list[Path]:
    out: list[Path] = []
    for root in (Path("/app/src"),):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                    out.append(p)
    return out


def _all_app_source_files() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES:
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        out.append(p)
    return out


def _all_app_build_inputs() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file():
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        if p.suffix in SOURCE_SUFFIXES + BUILD_SCRIPT_SUFFIXES:
            out.append(p)
        elif p.name in BUILD_SCRIPT_NAMES:
            out.append(p)
    return out

def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BUILD_DIR = Path("/app/build")
JAVA_CLASS = "Replay"
GSON_CP = "/opt/gson.jar"

EV_PATH = DATA_DIR / "events.json"
CONFIG_PATH = DATA_DIR / "config.json"

CACHE_PATH = OUT_DIR / "cache_state.json"
DEC_PATH = OUT_DIR / "decisions.json"
AUDIT_PATH = OUT_DIR / "event_audit.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
VIOL_PATH = OUT_DIR / "violations.json"

ALL_OUT_PATHS = (CACHE_PATH, DEC_PATH, AUDIT_PATH, SUMMARY_PATH, VIOL_PATH)
ALL_OUT_NAMES = tuple(p.name for p in ALL_OUT_PATHS)
ALL_INPUT_PATHS = (EV_PATH, CONFIG_PATH)

VALID_TYPES = {"access", "evict", "clear"}
VALID_OUTCOMES = {"hit_t1", "hit_t2", "ghost_hit_b1", "ghost_hit_b2",
                  "miss", "evicted", "cleared"}
VALID_REASONS = {None, "unknown_resident", "cache_empty"}
VALID_REPLACED_FROM = {None, "t1", "t2"}
VALID_DROPPED_FROM = {None, "t1", "b1", "b2"}


def sha256_of(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def dump_canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    if decoded != dump_canonical(payload):
        return False, f"{path} not canonical"
    return True, ""


# ---------------------------------------------------------------------------
# Reference simulator (mirror of /app/docs/state_machine.md).
#
# This is W-ARC, a weighted variant of canonical ARC (Megiddo-Modha 2003):
#   * Every access carries a weight in [1, 16].
#   * Each resident entry (T1, T2) carries cum_weight, summed over weights of
#     access events applied while the key is in its current tenure. A fresh
#     entry's cum_weight is set to the triggering access weight (whether the
#     entry arrived via miss insertion into T1 or via ghost-hit promotion to
#     T2). An access hit on T1 or T2 adds the access weight to the existing
#     cum_weight.
#   * Each ghost entry (B1, B2) carries entry_weight = the cum_weight of the
#     entry at the moment it was demoted.
#   * REPLACE picks the victim from the chosen side (T1 or T2) using
#     min-cum_weight first, with LRU as tiebreak (the LRU-most entry within
#     the min-weight set). The choice of side (T1 vs T2) is the canonical-
#     ARC predicate, unchanged.
#   * The miss-case "drop LRU of T1 directly" branch also uses the weighted
#     selection (min cum_weight, LRU tiebreak). The miss-case ghost drops
#     ("drop LRU of B1", "drop LRU of B2") remain plain LRU on B1/B2 because
#     the ghost lists track demotion order rather than per-entry weight.
#   * The adaptive parameter p update is unchanged: delta1 = max(|B2|/|B1|,
#     1) on B1 ghost hit; delta2 = max(|B1|/|B2|, 1) on B2 ghost hit.
# ---------------------------------------------------------------------------


class _WARC:
    def __init__(self, c: int) -> None:
        self.c = c
        # Residents: list of (key, cum_weight) tuples in MRU->LRU order.
        self.t1: list[tuple[str, int]] = []
        self.t2: list[tuple[str, int]] = []
        # Ghosts: list of (key, entry_weight) tuples in MRU->LRU order.
        self.b1: list[tuple[str, int]] = []
        self.b2: list[tuple[str, int]] = []
        self.p = 0
        self.observed: set[str] = set()
        self.weight_admitted = 0

    @staticmethod
    def _find(lst: list[tuple[str, int]], x: str) -> int:
        for i, (k, _) in enumerate(lst):
            if k == x:
                return i
        return -1

    def _in(self, lst: list[tuple[str, int]], x: str) -> bool:
        return self._find(lst, x) >= 0

    def _pop_weighted(self, lst: list[tuple[str, int]]) -> tuple[str, int]:
        # Returns (key, weight) of the entry chosen: smallest cum_weight,
        # LRU among ties (the largest index in the MRU->LRU list).
        min_w = min(w for _, w in lst)
        for i in range(len(lst) - 1, -1, -1):
            if lst[i][1] == min_w:
                return lst.pop(i)
        raise AssertionError("unreachable")

    def _replace(self, in_b2: bool) -> tuple[str | None, str | None, int | None]:
        t1n = len(self.t1)
        if t1n >= 1 and ((in_b2 and t1n == self.p) or t1n > self.p):
            key, w = self._pop_weighted(self.t1)
            self.b1.insert(0, (key, w))
            return key, "t1", w
        else:
            key, w = self._pop_weighted(self.t2)
            self.b2.insert(0, (key, w))
            return key, "t2", w

    def access(self, x: str, w: int):
        self.observed.add(x)
        self.weight_admitted += w
        rep_k = rep_f = drop_k = drop_f = None
        rep_w = drop_w = None
        cum_after = None

        i = self._find(self.t1, x)
        if i >= 0:
            outcome = "hit_t1"
            _, old = self.t1.pop(i)
            new_w = old + w
            self.t2.insert(0, (x, new_w))
            cum_after = new_w
            return (outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after)

        i = self._find(self.t2, x)
        if i >= 0:
            outcome = "hit_t2"
            _, old = self.t2.pop(i)
            new_w = old + w
            self.t2.insert(0, (x, new_w))
            cum_after = new_w
            return (outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after)

        i = self._find(self.b1, x)
        if i >= 0:
            outcome = "ghost_hit_b1"
            delta = max(len(self.b2) // len(self.b1), 1)
            self.p = min(self.p + delta, self.c)
            rep_k, rep_f, rep_w = self._replace(False)
            self.b1.pop(self._find(self.b1, x))
            self.t2.insert(0, (x, w))
            cum_after = w
            return (outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after)

        i = self._find(self.b2, x)
        if i >= 0:
            outcome = "ghost_hit_b2"
            delta = max(len(self.b1) // len(self.b2), 1)
            self.p = max(self.p - delta, 0)
            rep_k, rep_f, rep_w = self._replace(True)
            self.b2.pop(self._find(self.b2, x))
            self.t2.insert(0, (x, w))
            cum_after = w
            return (outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after)

        outcome = "miss"
        t1n = len(self.t1)
        b1n = len(self.b1)
        total = t1n + len(self.t2) + b1n + len(self.b2)
        if t1n + b1n == self.c:
            if t1n < self.c:
                k, gw = self.b1.pop()
                drop_k, drop_f, drop_w = k, "b1", gw
                rep_k, rep_f, rep_w = self._replace(False)
            else:
                k, ow = self._pop_weighted(self.t1)
                drop_k, drop_f, drop_w = k, "t1", ow
        elif t1n + b1n < self.c and total >= self.c:
            if total == 2 * self.c:
                k, gw = self.b2.pop()
                drop_k, drop_f, drop_w = k, "b2", gw
            rep_k, rep_f, rep_w = self._replace(False)
        self.t1.insert(0, (x, w))
        cum_after = w
        return (outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after)

    def evict(self, x: str) -> bool:
        i = self._find(self.t1, x)
        if i >= 0:
            self.t1.pop(i)
            return True
        i = self._find(self.t2, x)
        if i >= 0:
            self.t2.pop(i)
            return True
        return False

    def clear(self) -> bool:
        if not self.t1 and not self.t2 and not self.b1 and not self.b2:
            return False
        self.t1.clear()
        self.t2.clear()
        self.b1.clear()
        self.b2.clear()
        self.p = 0
        return True


def _resident_entries(lst: list[tuple[str, int]]) -> list[dict]:
    return [{"cum_weight": w, "key": k} for k, w in lst]


def _ghost_entries(lst: list[tuple[str, int]]) -> list[dict]:
    return [{"entry_weight": w, "key": k} for k, w in lst]


def simulate(events_doc: dict, cfg: dict) -> dict:
    arc = _WARC(int(cfg["cache_size"]))
    audit: list[dict] = []
    decisions: list[dict] = []
    counts = {k: 0 for k in [
        "total_accesses", "total_evicts", "total_clears",
        "accesses_accepted", "evicts_accepted", "evicts_rejected",
        "clears_accepted", "clears_rejected",
        "hits_t1", "hits_t2", "ghost_hits_b1", "ghost_hits_b2", "misses",
    ]}

    for ev in events_doc["events"]:
        ev_id = ev["event_id"]
        ts = int(ev["ts_unix_ms"])
        ty = ev["type"]
        p = ev["payload"]
        accepted = False
        reason = None
        decision = None

        if ty == "access":
            counts["total_accesses"] += 1
            res = arc.access(p["key"], int(p["weight"]))
            outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, cum_after = res
            accepted = True
            counts["accesses_accepted"] += 1
            counts[{
                "hit_t1": "hits_t1",
                "hit_t2": "hits_t2",
                "ghost_hit_b1": "ghost_hits_b1",
                "ghost_hit_b2": "ghost_hits_b2",
                "miss": "misses",
            }[outcome]] += 1
            decision = {
                "b1_size": len(arc.b1),
                "b2_size": len(arc.b2),
                "cum_weight_after": cum_after,
                "dropped_from": drop_f,
                "dropped_key": drop_k,
                "dropped_weight": drop_w,
                "event_id": ev_id,
                "key": p["key"],
                "outcome": outcome,
                "p_after": arc.p,
                "replaced_from": rep_f,
                "replaced_key": rep_k,
                "replaced_weight": rep_w,
                "t1_size": len(arc.t1),
                "t2_size": len(arc.t2),
                "type": "access",
            }
        elif ty == "evict":
            counts["total_evicts"] += 1
            if arc.evict(p["key"]):
                accepted = True
                counts["evicts_accepted"] += 1
                decision = {
                    "b1_size": len(arc.b1),
                    "b2_size": len(arc.b2),
                    "cum_weight_after": None,
                    "dropped_from": None,
                    "dropped_key": None,
                    "dropped_weight": None,
                    "event_id": ev_id,
                    "key": p["key"],
                    "outcome": "evicted",
                    "p_after": arc.p,
                    "replaced_from": None,
                    "replaced_key": None,
                    "replaced_weight": None,
                    "t1_size": len(arc.t1),
                    "t2_size": len(arc.t2),
                    "type": "evict",
                }
            else:
                counts["evicts_rejected"] += 1
                reason = "unknown_resident"
        else:  # clear
            counts["total_clears"] += 1
            if arc.clear():
                accepted = True
                counts["clears_accepted"] += 1
                decision = {
                    "b1_size": len(arc.b1),
                    "b2_size": len(arc.b2),
                    "cum_weight_after": None,
                    "dropped_from": None,
                    "dropped_key": None,
                    "dropped_weight": None,
                    "event_id": ev_id,
                    "key": None,
                    "outcome": "cleared",
                    "p_after": arc.p,
                    "replaced_from": None,
                    "replaced_key": None,
                    "replaced_weight": None,
                    "t1_size": len(arc.t1),
                    "t2_size": len(arc.t2),
                    "type": "clear",
                }
            else:
                counts["clears_rejected"] += 1
                reason = "cache_empty"

        audit.append({
            "accepted": accepted,
            "event_id": ev_id,
            "payload": dict(p),
            "reason_ignored": reason,
            "ts_unix_ms": ts,
            "type": ty,
        })
        if decision is not None:
            decisions.append(decision)

    audit_sorted = sorted(audit, key=lambda r: r["event_id"])
    viol_sorted = [dict(r) for r in audit_sorted if not r["accepted"]]
    summary = {
        "accesses_accepted": counts["accesses_accepted"],
        "clears_accepted": counts["clears_accepted"],
        "clears_rejected": counts["clears_rejected"],
        "evicts_accepted": counts["evicts_accepted"],
        "evicts_rejected": counts["evicts_rejected"],
        "final_b1_weight_sum": sum(w for _, w in arc.b1),
        "final_b2_weight_sum": sum(w for _, w in arc.b2),
        "final_p": arc.p,
        "final_t1_weight_sum": sum(w for _, w in arc.t1),
        "final_t2_weight_sum": sum(w for _, w in arc.t2),
        "ghost_hits_b1": counts["ghost_hits_b1"],
        "ghost_hits_b2": counts["ghost_hits_b2"],
        "hits_t1": counts["hits_t1"],
        "hits_t2": counts["hits_t2"],
        "misses": counts["misses"],
        "total_accesses": counts["total_accesses"],
        "total_clears": counts["total_clears"],
        "total_distinct_keys": len(arc.observed),
        "total_events": len(events_doc["events"]),
        "total_evicts": counts["total_evicts"],
        "total_weight_admitted": arc.weight_admitted,
    }
    return {
        "cache_state": {
            "b1": _ghost_entries(arc.b1),
            "b2": _ghost_entries(arc.b2),
            "p": arc.p,
            "t1": _resident_entries(arc.t1),
            "t2": _resident_entries(arc.t2),
        },
        "decisions": {"decisions": decisions},
        "event_audit": {"events": audit_sorted},
        "violations": {"violations": viol_sorted},
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def input_data() -> dict[str, Any]:
    return {"events": load_json(EV_PATH), "config": load_json(CONFIG_PATH)}


@pytest.fixture(scope="session")
def expected_outputs(input_data) -> dict[str, Any]:
    return simulate(input_data["events"], input_data["config"])


@pytest.fixture(scope="session")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in ALL_INPUT_PATHS}


@pytest.fixture(scope="session")
def binary_run_outputs(precomputed_input_hashes) -> dict[Path, Any]:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    assert _java_class_ready()
    assert (BUILD_DIR / f"{JAVA_CLASS}.class").stat().st_mode & True  # Java class
    res = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=180,
    )
    assert res.returncode == 0, f"rc={res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}"
    out: dict[Path, Any] = {}
    for p in ALL_OUT_PATHS:
        assert p.exists()
        out[p] = load_json(p)
    return out


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------


def test_inputs_unchanged(precomputed_input_hashes):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h



def test_java_entry_class_exists():
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()




def test_sources_present_and_class_newer():
    """Java sources under /app/src are no older than the compiled entry class."""
    required_sources = _src_files()
    assert required_sources, "no .java under /app/src"
    inputs = _all_app_build_inputs()
    class_path = BUILD_DIR / f"{JAVA_CLASS}.class"
    bin_mtime = int(class_path.stat().st_mtime)
    for s in inputs:
        src_mtime = int(s.stat().st_mtime)
        assert bin_mtime >= src_mtime, (
            f"class mtime {bin_mtime} older than build input {s} mtime {src_mtime}"
        )



def test_binary_runs_cleanly(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        assert p in binary_run_outputs


def test_binary_rejects_wrong_arg_counts(tmp_path):
    res = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    res = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)], capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    probe = tmp_path / "probe"
    probe.mkdir()
    res = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)],
                         capture_output=True, text=True, timeout=30)
    assert res.returncode != 0
    assert sorted(probe.rglob("*")) == []


def test_binary_uses_argv2_paths(tmp_path):
    tmp_out = tmp_path / "alt"
    tmp_out.mkdir()
    res = subprocess.run([*_java_cmd(DATA_DIR, tmp_out)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0
    for name in ALL_OUT_NAMES:
        p = tmp_out / name
        assert p.exists() and p.is_file() and not p.is_symlink()
    assert sorted(p.name for p in tmp_out.iterdir()) == sorted(ALL_OUT_NAMES)


def test_binary_reads_input_from_argv1(tmp_path, input_data, expected_outputs):
    in_dir = tmp_path / "alt_in"
    in_dir.mkdir()
    out_dir = tmp_path / "alt_out"
    out_dir.mkdir()
    variant = {"events": input_data["events"]["events"][:-1]}
    (in_dir / "events.json").write_text(dump_canonical(variant))
    (in_dir / "config.json").write_text(dump_canonical(input_data["config"]))
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr
    ve = simulate(variant, input_data["config"])
    name_map = {
        "cache_state.json": "cache_state",
        "decisions.json": "decisions",
        "event_audit.json": "event_audit",
        "violations.json": "violations",
        "summary.json": "summary",
    }
    for name, key in name_map.items():
        actual = json.loads((out_dir / name).read_text())
        assert actual == ve[key]
    assert ve["event_audit"] != expected_outputs["event_audit"]


def test_outputs_strict_json_formatting(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(p)
        assert ok, msg


def test_outputs_are_ascii(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        p.read_text(encoding="utf-8").encode("ascii")


def _walk_object_keys(text: str):
    obj = json.loads(text, object_pairs_hook=lambda items: items)
    out = []

    def walk(node):
        if isinstance(node, list):
            if (node and isinstance(node[0], tuple) and len(node[0]) == 2
                    and isinstance(node[0][0], str)):
                out.append([k for k, _ in node])
                for _, v in node:
                    walk(v)
            else:
                for v in node:
                    walk(v)

    walk(obj)
    return out


def test_outputs_keys_sorted(binary_run_outputs):
    for p in ALL_OUT_PATHS:
        text = p.read_text()
        for keys in _walk_object_keys(text):
            assert keys == sorted(keys)


def test_output_dir_has_exactly_five_files(binary_run_outputs):
    entries = list(OUT_DIR.iterdir())
    assert sorted(p.name for p in entries) == sorted(ALL_OUT_NAMES)
    for p in entries:
        assert p.is_file() and not p.is_symlink()


def test_cache_state_match(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[CACHE_PATH] == expected_outputs["cache_state"]


def test_decisions_match(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[DEC_PATH] == expected_outputs["decisions"]


def test_audit_match(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[AUDIT_PATH] == expected_outputs["event_audit"]


def test_violations_match(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[VIOL_PATH] == expected_outputs["violations"]


def test_summary_match(binary_run_outputs, expected_outputs):
    assert binary_run_outputs[SUMMARY_PATH] == expected_outputs["summary"]


def test_cache_state_lists_disjoint(binary_run_outputs):
    cs = binary_run_outputs[CACHE_PATH]
    seen: set[str] = set()
    for name in ("t1", "t2"):
        for entry in cs[name]:
            assert isinstance(entry, dict)
            assert set(entry.keys()) == {"cum_weight", "key"}
            k = entry["key"]
            w = entry["cum_weight"]
            assert isinstance(k, str) and k
            assert isinstance(w, int) and w >= 1
            assert k not in seen
            seen.add(k)
    for name in ("b1", "b2"):
        for entry in cs[name]:
            assert isinstance(entry, dict)
            assert set(entry.keys()) == {"entry_weight", "key"}
            k = entry["key"]
            w = entry["entry_weight"]
            assert isinstance(k, str) and k
            assert isinstance(w, int) and w >= 1
            assert k not in seen
            seen.add(k)


def test_cache_state_invariants(binary_run_outputs, input_data):
    c = input_data["config"]["cache_size"]
    cs = binary_run_outputs[CACHE_PATH]
    t1 = len(cs["t1"])
    t2 = len(cs["t2"])
    b1 = len(cs["b1"])
    b2 = len(cs["b2"])
    assert t1 + t2 <= c
    assert t1 + b1 + t2 + b2 <= 2 * c
    assert 0 <= cs["p"] <= c


def test_audit_closed_sets(binary_run_outputs):
    for r in binary_run_outputs[AUDIT_PATH]["events"]:
        assert r["type"] in VALID_TYPES
        assert r["reason_ignored"] in VALID_REASONS
        assert isinstance(r["accepted"], bool)
        if r["accepted"]:
            assert r["reason_ignored"] is None
        else:
            assert r["reason_ignored"] is not None


def test_audit_sorted(binary_run_outputs):
    ids = [r["event_id"] for r in binary_run_outputs[AUDIT_PATH]["events"]]
    assert ids == sorted(ids)


def test_violations_sorted(binary_run_outputs):
    ids = [r["event_id"] for r in binary_run_outputs[VIOL_PATH]["violations"]]
    assert ids == sorted(ids)


def test_violations_equal_audit_rejections(binary_run_outputs):
    rej = [r for r in binary_run_outputs[AUDIT_PATH]["events"] if not r["accepted"]]
    viol = binary_run_outputs[VIOL_PATH]["violations"]
    assert sorted(rej, key=lambda r: r["event_id"]) == sorted(viol, key=lambda r: r["event_id"])


def test_decisions_one_per_accepted_in_order(binary_run_outputs, input_data):
    audit = binary_run_outputs[AUDIT_PATH]["events"]
    accepted_ids = {r["event_id"] for r in audit if r["accepted"]}
    accepted_in_order = [
        ev["event_id"] for ev in input_data["events"]["events"]
        if ev["event_id"] in accepted_ids
    ]
    decision_ids = [d["event_id"] for d in binary_run_outputs[DEC_PATH]["decisions"]]
    assert decision_ids == accepted_in_order


def test_decisions_closed_sets(binary_run_outputs):
    for d in binary_run_outputs[DEC_PATH]["decisions"]:
        assert d["outcome"] in VALID_OUTCOMES
        assert d["type"] in VALID_TYPES
        assert d["replaced_from"] in VALID_REPLACED_FROM
        assert d["dropped_from"] in VALID_DROPPED_FROM


def test_decisions_replaced_dropped_paired(binary_run_outputs):
    for d in binary_run_outputs[DEC_PATH]["decisions"]:
        assert (d["replaced_key"] is None) == (d["replaced_from"] is None)
        assert (d["replaced_key"] is None) == (d["replaced_weight"] is None)
        assert (d["dropped_key"] is None) == (d["dropped_from"] is None)
        assert (d["dropped_key"] is None) == (d["dropped_weight"] is None)
        if d["replaced_weight"] is not None:
            assert isinstance(d["replaced_weight"], int) and d["replaced_weight"] >= 1
        if d["dropped_weight"] is not None:
            assert isinstance(d["dropped_weight"], int) and d["dropped_weight"] >= 1


def test_evict_clear_decisions_have_null_replaced_dropped(binary_run_outputs):
    for d in binary_run_outputs[DEC_PATH]["decisions"]:
        if d["type"] in ("evict", "clear"):
            assert d["replaced_key"] is None
            assert d["replaced_from"] is None
            assert d["replaced_weight"] is None
            assert d["dropped_key"] is None
            assert d["dropped_from"] is None
            assert d["dropped_weight"] is None
            assert d["cum_weight_after"] is None
        if d["type"] == "clear":
            assert d["key"] is None
            assert d["t1_size"] == 0
            assert d["t2_size"] == 0
            assert d["b1_size"] == 0
            assert d["b2_size"] == 0
            assert d["p_after"] == 0


def test_decisions_access_has_cum_weight_after(binary_run_outputs):
    for d in binary_run_outputs[DEC_PATH]["decisions"]:
        if d["type"] == "access":
            assert isinstance(d["cum_weight_after"], int)
            assert d["cum_weight_after"] >= 1


def test_summary_counts_consistent(binary_run_outputs):
    s = binary_run_outputs[SUMMARY_PATH]
    events = binary_run_outputs[AUDIT_PATH]["events"]
    by_type: dict[str, list[int]] = {"access": [0, 0], "evict": [0, 0], "clear": [0, 0]}
    for r in events:
        idx = 0 if r["accepted"] else 1
        by_type[r["type"]][idx] += 1
    assert s["accesses_accepted"] == by_type["access"][0]
    assert s["evicts_accepted"] == by_type["evict"][0]
    assert s["evicts_rejected"] == by_type["evict"][1]
    assert s["clears_accepted"] == by_type["clear"][0]
    assert s["clears_rejected"] == by_type["clear"][1]
    assert s["total_accesses"] == sum(by_type["access"])
    assert s["total_evicts"] == sum(by_type["evict"])
    assert s["total_clears"] == sum(by_type["clear"])
    assert s["total_events"] == len(events)
    assert s["accesses_accepted"] == (
        s["hits_t1"] + s["hits_t2"] + s["ghost_hits_b1"] + s["ghost_hits_b2"] + s["misses"]
    )
    cs = binary_run_outputs[CACHE_PATH]
    assert s["final_p"] == cs["p"]
    assert s["final_t1_weight_sum"] == sum(e["cum_weight"] for e in cs["t1"])
    assert s["final_t2_weight_sum"] == sum(e["cum_weight"] for e in cs["t2"])
    assert s["final_b1_weight_sum"] == sum(e["entry_weight"] for e in cs["b1"])
    assert s["final_b2_weight_sum"] == sum(e["entry_weight"] for e in cs["b2"])


def test_summary_total_weight_admitted_matches_input(binary_run_outputs, input_data):
    s = binary_run_outputs[SUMMARY_PATH]
    expected = sum(ev["payload"]["weight"]
                   for ev in input_data["events"]["events"]
                   if ev["type"] == "access")
    assert s["total_weight_admitted"] == expected


def test_dataset_exercises_every_outcome_and_reject(expected_outputs):
    audit = expected_outputs["event_audit"]["events"]
    seen_reasons = {r["reason_ignored"] for r in audit if not r["accepted"]}
    assert seen_reasons == {"unknown_resident", "cache_empty"}, seen_reasons
    seen_outcomes = {d["outcome"] for d in expected_outputs["decisions"]["decisions"]}
    required = {"hit_t1", "hit_t2", "ghost_hit_b1", "ghost_hit_b2",
                "miss", "evicted", "cleared"}
    missing = required - seen_outcomes
    assert not missing, f"fixture missing outcomes: {missing}"


def test_dataset_exercises_weighted_victim_corner(expected_outputs, input_data):
    """The dataset must contain at least one accepted REPLACE event where
    strict-LRU and W-ARC's min-weight + LRU-tiebreak rule choose different
    victims. Without this, the verifier cannot empirically distinguish a
    correct W-ARC implementation from a canonical-ARC implementation."""
    decisions = expected_outputs["decisions"]["decisions"]
    cfg = input_data["config"]
    # Replay a strict-LRU variant alongside the W-ARC reference and assert
    # the two diverge at some accepted-event step.
    diverged = _strict_lru_replay_diverges(input_data["events"], cfg, decisions)
    assert diverged, "dataset does not exercise the weighted-victim divergence"


def _strict_lru_replay_diverges(events_doc, cfg, ref_decisions) -> bool:
    # A strict-LRU stand-in that ignores cum_weight when picking victims.
    class _LRU(_WARC):
        def _pop_weighted(self, lst):
            return lst.pop()  # plain LRU

    arc = _LRU(int(cfg["cache_size"]))
    ref_iter = iter(ref_decisions)
    for ev in events_doc["events"]:
        ty = ev["type"]
        p = ev["payload"]
        if ty == "access":
            res = arc.access(p["key"], int(p["weight"]))
            outcome, rep_k, rep_f, rep_w, drop_k, drop_f, drop_w, _ = res
            ref = next(ref_iter)
            if (ref["replaced_key"] != rep_k
                    or ref["dropped_key"] != drop_k
                    or ref["replaced_weight"] != rep_w
                    or ref["dropped_weight"] != drop_w):
                return True
        elif ty == "evict":
            if not arc.evict(p["key"]):
                continue
            next(ref_iter)
        else:
            if not arc.clear():
                continue
            next(ref_iter)
    return False


def test_determinism_two_runs_byte_identical(tmp_path):
    out_a = tmp_path / "a"
    out_a.mkdir()
    out_b = tmp_path / "b"
    out_b.mkdir()
    for out in (out_a, out_b):
        res = subprocess.run([*_java_cmd(DATA_DIR, out)],
                             capture_output=True, text=True, timeout=180)
        assert res.returncode == 0
    for n in ALL_OUT_NAMES:
        assert (out_a / n).read_bytes() == (out_b / n).read_bytes()


def test_data_dir_unchanged_after_run(precomputed_input_hashes, binary_run_outputs):
    for p, h in precomputed_input_hashes.items():
        assert sha256_of(p) == h


def test_binary_can_be_rebuilt_from_visible_sources(tmp_path, expected_outputs):
    """Recompiling visible Java sources reproduces the reference outputs."""
    sources = _src_files()
    assert sources
    build_dir = tmp_path / "rebuilt_build"
    build_dir.mkdir()
    cmd = [
        "javac",
        "-encoding",
        "UTF-8",
        "-cp",
        GSON_CP,
        "-d",
        str(build_dir),
    ] + [str(s) for s in sources]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    assert res.returncode == 0, res.stderr
    out = tmp_path / "rout"
    out.mkdir()
    res = subprocess.run(
        ["java", "-cp", f"{build_dir}:{GSON_CP}", JAVA_CLASS, str(DATA_DIR), str(out)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert res.returncode == 0
    name_map = {
        "cache_state.json": "cache_state",
        "decisions.json": "decisions",
        "event_audit.json": "event_audit",
        "violations.json": "violations",
        "summary.json": "summary",
    }
    for name, key in name_map.items():
        actual = json.loads((out / name).read_text())
        assert actual == expected_outputs[key]


# ---------------------------------------------------------------------------
# Focused semantic tests
# ---------------------------------------------------------------------------


def _make_inputs(tmp_path: Path, label: str, cfg: dict, events: dict):
    in_dir = tmp_path / f"in_{label}"
    in_dir.mkdir()
    out_dir = tmp_path / f"out_{label}"
    out_dir.mkdir()
    (in_dir / "config.json").write_text(dump_canonical(cfg))
    (in_dir / "events.json").write_text(dump_canonical(events))
    return in_dir, out_dir


def _acc(eid: str, ts: int, key: str, w: int) -> dict:
    return {"event_id": eid, "ts_unix_ms": ts, "type": "access",
            "payload": {"key": key, "weight": w}}


def _evt(eid: str, ts: int, key: str) -> dict:
    return {"event_id": eid, "ts_unix_ms": ts, "type": "evict",
            "payload": {"key": key}}


def _clr(eid: str, ts: int) -> dict:
    return {"event_id": eid, "ts_unix_ms": ts, "type": "clear", "payload": {}}


def test_first_access_is_miss(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [_acc("a", 1, "k", 3)]}
    in_dir, out_dir = _make_inputs(tmp_path, "fm", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    assert len(decisions) == 1
    assert decisions[0]["outcome"] == "miss"
    assert decisions[0]["cum_weight_after"] == 3
    cs = load_json(out_dir / "cache_state.json")
    assert cs["t1"] == [{"cum_weight": 3, "key": "k"}]
    assert cs["t2"] == []
    assert cs["b1"] == []
    assert cs["b2"] == []
    assert cs["p"] == 0


def test_hit_t1_accumulates_weight(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [_acc("a", 1, "k", 3), _acc("b", 2, "k", 4)]}
    in_dir, out_dir = _make_inputs(tmp_path, "ht1", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    assert [d["outcome"] for d in decisions] == ["miss", "hit_t1"]
    assert decisions[1]["cum_weight_after"] == 7
    cs = load_json(out_dir / "cache_state.json")
    assert cs["t1"] == []
    assert cs["t2"] == [{"cum_weight": 7, "key": "k"}]


def test_hit_t2_accumulates_weight(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [
        _acc("a", 1, "k", 3),
        _acc("b", 2, "k", 4),
        _acc("c", 3, "k", 5),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "ht2", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    assert [d["outcome"] for d in decisions] == ["miss", "hit_t1", "hit_t2"]
    assert decisions[2]["cum_weight_after"] == 12


def test_weighted_replace_picks_min_weight_not_lru(tmp_path):
    """Construct a state where T2 holds [kc(6), kb(2), ka(20)] in MRU->LRU
    and t1n==p==0 so REPLACE demotes from T2. Strict LRU would demote ka
    (cum_weight 20); W-ARC demotes kb (cum_weight 2)."""
    cfg = {"cache_size": 3}
    events = {"events": [
        _acc("e1", 1, "ka", 10),
        _acc("e2", 2, "ka", 10),  # promote ka to T2(20)
        _acc("e3", 3, "kb", 1),
        _acc("e4", 4, "kb", 1),   # promote kb to T2(2)
        _acc("e5", 5, "kc", 3),
        _acc("e6", 6, "kc", 3),   # promote kc to T2(6); T2=[kc(6),kb(2),ka(20)], T1=[]
        _acc("e7", 7, "kd", 5),   # miss, t1n=0, t2n=3=c, REPLACE on T2
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "wm", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    last = decisions[-1]
    assert last["outcome"] == "miss"
    assert last["replaced_from"] == "t2"
    assert last["replaced_key"] == "kb"
    assert last["replaced_weight"] == 2
    cs = load_json(out_dir / "cache_state.json")
    assert {e["key"] for e in cs["t2"]} == {"kc", "ka"}
    assert {e["key"] for e in cs["b2"]} == {"kb"}
    assert cs["b2"][0]["entry_weight"] == 2


def test_weighted_drop_t1_directly_uses_min_weight(tmp_path):
    """When |T1|==c and a miss arrives with no ghosts, ARC drops T1 LRU
    directly. W-ARC drops the min-cum_weight entry from T1 instead."""
    cfg = {"cache_size": 3}
    events = {"events": [
        _acc("e1", 1, "ka", 10),
        _acc("e2", 2, "kb", 1),
        _acc("e3", 3, "kc", 10),   # T1=[kc(10),kb(1),ka(10)], total=3=c
        _acc("e4", 4, "kd", 5),    # miss, t1==c, drop T1 directly
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "wd", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    last = decisions[-1]
    assert last["outcome"] == "miss"
    assert last["dropped_from"] == "t1"
    assert last["dropped_key"] == "kb"
    assert last["dropped_weight"] == 1
    cs = load_json(out_dir / "cache_state.json")
    assert {e["key"] for e in cs["t1"]} == {"kd", "kc", "ka"}
    assert cs["b1"] == []


def test_lru_tiebreak_on_equal_weights(tmp_path):
    """When two T1 entries share the same (min) cum_weight, REPLACE picks
    the LRU-most of the tied set."""
    cfg = {"cache_size": 3}
    events = {"events": [
        _acc("e1", 1, "ka", 1),   # T1=[ka(1)]
        _acc("e2", 2, "kb", 1),   # T1=[kb(1), ka(1)]
        _acc("e3", 3, "kc", 1),   # T1=[kc(1), kb(1), ka(1)]; total=3=c
        _acc("e4", 4, "kd", 1),   # miss, drop T1 directly, all tied at 1, LRU=ka
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "tb", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    last = load_json(out_dir / "decisions.json")["decisions"][-1]
    assert last["dropped_from"] == "t1"
    assert last["dropped_key"] == "ka"


def test_ghost_hit_b1_increases_p(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [
        _acc("e1", 1, "ka", 1),
        _acc("e2", 2, "ka", 1),
        _acc("e3", 3, "kb", 1),
        _acc("e4", 4, "kc", 1),
        _acc("e5", 5, "kb", 1),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "gh1", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    assert decisions[-1]["outcome"] == "ghost_hit_b1"
    assert decisions[-1]["p_after"] >= 1


def test_evict_removes_from_t1(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [
        _acc("e1", 1, "ka", 5),
        _evt("e2", 2, "ka"),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "ev1", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    cs = load_json(out_dir / "cache_state.json")
    assert cs["t1"] == []
    assert cs["t2"] == []
    assert cs["b1"] == []
    assert cs["b2"] == []
    decisions = load_json(out_dir / "decisions.json")["decisions"]
    assert decisions[-1]["outcome"] == "evicted"
    assert decisions[-1]["cum_weight_after"] is None


def test_evict_unknown_rejected(tmp_path):
    cfg = {"cache_size": 1}
    events = {"events": [_evt("a", 1, "ghost")]}
    in_dir, out_dir = _make_inputs(tmp_path, "ung", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    audit = load_json(out_dir / "event_audit.json")["events"]
    assert audit[0]["reason_ignored"] == "unknown_resident"


def test_evict_ghost_is_unknown_resident(tmp_path):
    cfg = {"cache_size": 1}
    events = {"events": [
        _acc("e1", 1, "ka", 1),
        _acc("e2", 2, "kb", 1),
        _evt("e3", 3, "ka"),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "ung2", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    audit = load_json(out_dir / "event_audit.json")["events"]
    by_id = {r["event_id"]: r for r in audit}
    assert by_id["e3"]["reason_ignored"] == "unknown_resident"


def test_clear_empty_rejected(tmp_path):
    cfg = {"cache_size": 1}
    events = {"events": [_clr("a", 1)]}
    in_dir, out_dir = _make_inputs(tmp_path, "ce", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    audit = load_json(out_dir / "event_audit.json")["events"]
    assert audit[0]["reason_ignored"] == "cache_empty"


def test_clear_resets_state_and_p(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [
        _acc("e1", 1, "ka", 1),
        _acc("e2", 2, "kb", 1),
        _acc("e3", 3, "kc", 1),
        _acc("e4", 4, "ka", 1),
        _clr("e5", 5),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "cl", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    cs = load_json(out_dir / "cache_state.json")
    assert cs == {"b1": [], "b2": [], "p": 0, "t1": [], "t2": []}


def test_rejected_clear_does_not_modify_state(tmp_path):
    cfg = {"cache_size": 2}
    events = {"events": [
        _acc("e1", 1, "ka", 1),
        _clr("e2", 2),
        _clr("e3", 3),
    ]}
    in_dir, out_dir = _make_inputs(tmp_path, "rj", cfg, events)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode == 0
    cs = load_json(out_dir / "cache_state.json")
    assert cs["t1"] == [] and cs["t2"] == []


# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------


_OMIT = object()


def _write_inputs(d: Path, *, base, events=None, config=None):
    spec = {
        "events.json": events if events is not None else base["events"],
        "config.json": config if config is not None else base["config"],
    }
    for name, payload in spec.items():
        if payload is _OMIT:
            continue
        path = d / name
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(dump_canonical(payload), encoding="utf-8")


def _run(in_dir: Path, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    return subprocess.run([*_java_cmd(in_dir, out_dir)],
                          capture_output=True, text=True, timeout=60)


def _assert_rejected_no_output(out_dir, res):
    assert res.returncode != 0, f"expected non-zero exit\n{res.stderr}"
    if out_dir.exists():
        extras = sorted(p.relative_to(out_dir).as_posix() for p in out_dir.rglob("*"))
        assert extras == []


@pytest.mark.parametrize("rejection_cause", [
    "malformed_events_json",
    "missing_events_json",
    "duplicate_event_id",
    "bad_cache_size",
    "unknown_event_type",
    "negative_ts",
    "missing_config_json",
    "missing_weight",
    "weight_out_of_range_low",
    "weight_out_of_range_high",
    "weight_wrong_type",
])
def test_rejection_preserves_preexisting_out_dir_contents(
    tmp_path, input_data, rejection_cause,
):
    in_dir = tmp_path / f"pre_in_{rejection_cause}"
    in_dir.mkdir()
    out_dir = tmp_path / f"pre_out_{rejection_cause}"
    out_dir.mkdir()
    decoy_a = out_dir / "decoy.txt"
    decoy_a.write_text("untouched\n")
    sub = out_dir / "sub"
    sub.mkdir()
    decoy_b = sub / "deep.bin"
    decoy_b.write_bytes(b"\x00\x01\x02\x03DECOY")
    before = {p.relative_to(out_dir).as_posix(): p.read_bytes()
              for p in out_dir.rglob("*") if p.is_file()}

    if rejection_cause == "malformed_events_json":
        _write_inputs(in_dir, base=input_data, events="{ not json")
    elif rejection_cause == "missing_events_json":
        _write_inputs(in_dir, base=input_data, events=_OMIT)
    elif rejection_cause == "duplicate_event_id":
        _write_inputs(in_dir, base=input_data, events={"events": [
            _acc("dup", 1, "a", 1), _acc("dup", 2, "b", 1),
        ]})
    elif rejection_cause == "bad_cache_size":
        cfg = dict(input_data["config"])
        cfg["cache_size"] = 0
        _write_inputs(in_dir, base=input_data, config=cfg)
    elif rejection_cause == "unknown_event_type":
        _write_inputs(in_dir, base=input_data, events={"events": [
            {"event_id": "e1", "ts_unix_ms": 1, "type": "boom",
             "payload": {}},
        ]})
    elif rejection_cause == "negative_ts":
        _write_inputs(in_dir, base=input_data, events={"events": [_clr("e1", -1)]})
    elif rejection_cause == "missing_config_json":
        _write_inputs(in_dir, base=input_data, config=_OMIT)
    elif rejection_cause == "missing_weight":
        _write_inputs(in_dir, base=input_data, events={"events": [
            {"event_id": "e1", "ts_unix_ms": 1, "type": "access",
             "payload": {"key": "k"}},
        ]})
    elif rejection_cause == "weight_out_of_range_low":
        _write_inputs(in_dir, base=input_data, events={"events": [_acc("e1", 1, "k", 0)]})
    elif rejection_cause == "weight_out_of_range_high":
        _write_inputs(in_dir, base=input_data, events={"events": [_acc("e1", 1, "k", 17)]})
    elif rejection_cause == "weight_wrong_type":
        _write_inputs(in_dir, base=input_data, events={"events": [
            {"event_id": "e1", "ts_unix_ms": 1, "type": "access",
             "payload": {"key": "k", "weight": "5"}},
        ]})
    else:
        raise AssertionError(f"unexpected cause {rejection_cause}")

    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0, f"expected non-zero exit for {rejection_cause}"
    after = {p.relative_to(out_dir).as_posix(): p.read_bytes()
             for p in out_dir.rglob("*") if p.is_file()}
    assert before == after, (
        f"out_dir was modified on rejection ({rejection_cause})\n"
        f"before={sorted(before)}\nafter={sorted(after)}"
    )
    new_entries = {p.relative_to(out_dir).as_posix()
                   for p in out_dir.rglob("*")} - {
        p.relative_to(out_dir).as_posix() for p in (decoy_a, sub, decoy_b)
    }
    assert new_entries == set(), f"new entries introduced: {new_entries}"


def test_rejects_missing_inputs(tmp_path):
    in_dir = tmp_path / "e"
    in_dir.mkdir()
    out_dir = tmp_path / "eo"
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("drop", ["events.json", "config.json"])
def test_rejects_missing_each(tmp_path, input_data, drop):
    in_dir = tmp_path / f"d_{drop}"
    in_dir.mkdir()
    out_dir = tmp_path / f"d_{drop}_o"
    overrides = {"events": _OMIT if drop == "events.json" else None,
                 "config": _OMIT if drop == "config.json" else None}
    _write_inputs(in_dir, base=input_data, **overrides)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("bad", ["events.json", "config.json"])
def test_rejects_bad_json(tmp_path, input_data, bad):
    in_dir = tmp_path / f"b_{bad}"
    in_dir.mkdir()
    out_dir = tmp_path / f"b_{bad}_o"
    _write_inputs(in_dir, base=input_data,
                  events="{ not json" if bad == "events.json" else None,
                  config="{ not json" if bad == "config.json" else None)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_unknown_event_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "boom", "payload": {}}]}
    in_dir = tmp_path / "bt"
    in_dir.mkdir()
    out_dir = tmp_path / "bt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_event_record_extra_key(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": "k", "weight": 1}, "extra": 1}]}
    in_dir = tmp_path / "rx"
    in_dir.mkdir()
    out_dir = tmp_path / "rx_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_access_payload_extra(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": "k", "weight": 1, "bonus": 1}}]}
    in_dir = tmp_path / "iex"
    in_dir.mkdir()
    out_dir = tmp_path / "iex_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_evict_payload_extra(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "evict",
                       "payload": {"key": "k", "extra": 1}}]}
    in_dir = tmp_path / "evx"
    in_dir.mkdir()
    out_dir = tmp_path / "evx_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_evict_payload_with_weight(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "evict",
                       "payload": {"key": "k", "weight": 1}}]}
    in_dir = tmp_path / "evw"
    in_dir.mkdir()
    out_dir = tmp_path / "evw_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_clear_payload_with_keys(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "clear",
                       "payload": {"key": "should_not_be_here"}}]}
    in_dir = tmp_path / "cpx"
    in_dir.mkdir()
    out_dir = tmp_path / "cpx_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_empty_key(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": "", "weight": 1}}]}
    in_dir = tmp_path / "ek"
    in_dir.mkdir()
    out_dir = tmp_path / "ek_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_duplicate_event_id(tmp_path, input_data):
    bad = {"events": [_acc("dup", 1, "a", 1), _acc("dup", 2, "b", 1)]}
    in_dir = tmp_path / "de"
    in_dir.mkdir()
    out_dir = tmp_path / "de_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_negative_ts(tmp_path, input_data):
    bad = {"events": [_clr("e1", -1)]}
    in_dir = tmp_path / "nt"
    in_dir.mkdir()
    out_dir = tmp_path / "nt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_config_extra_key(tmp_path, input_data):
    cfg = dict(input_data["config"])
    cfg["bonus"] = "x"
    in_dir = tmp_path / "cex"
    in_dir.mkdir()
    out_dir = tmp_path / "cex_o"
    _write_inputs(in_dir, base=input_data, config=cfg)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("val", [0, -1, 257, 10000])
def test_rejects_config_bad_cache_size(tmp_path, input_data, val):
    cfg = dict(input_data["config"])
    cfg["cache_size"] = val
    in_dir = tmp_path / f"cm_{val}"
    in_dir.mkdir()
    out_dir = tmp_path / f"cm_{val}_o"
    _write_inputs(in_dir, base=input_data, config=cfg)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("val", [0, -1, 17, 1000])
def test_rejects_weight_out_of_range(tmp_path, input_data, val):
    bad = {"events": [_acc("e1", 1, "k", val)]}
    in_dir = tmp_path / f"wm_{val}"
    in_dir.mkdir()
    out_dir = tmp_path / f"wm_{val}_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("swap", ["events.json", "config.json"])
def test_rejects_input_is_directory(tmp_path, input_data, swap):
    in_dir = tmp_path / f"sd_{swap}"
    in_dir.mkdir()
    out_dir = tmp_path / f"sd_{swap}_o"
    _write_inputs(in_dir, base=input_data)
    (in_dir / swap).unlink()
    (in_dir / swap).mkdir()
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_when_input_dir_missing(tmp_path):
    out_dir = tmp_path / "out"
    res = subprocess.run([*_java_cmd(tmp_path / "absent", out_dir)],
                         capture_output=True, text=True, timeout=60)
    _assert_rejected_no_output(out_dir, res)


def test_rejects_when_output_dir_missing(tmp_path, input_data):
    in_dir = tmp_path / "g"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    missing = tmp_path / "absent_out"
    res = subprocess.run([*_java_cmd(in_dir, missing)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert not missing.exists() or list(missing.iterdir()) == []


def test_rejects_when_output_dir_is_symlink_to_dir(tmp_path, input_data):
    in_dir = tmp_path / "g_sym"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    real_out = tmp_path / "real_out"
    real_out.mkdir()
    link = tmp_path / "out_link"
    link.symlink_to(real_out)
    assert link.is_symlink()
    res = subprocess.run([*_java_cmd(in_dir, link)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert link.is_symlink()
    assert sorted(real_out.rglob("*")) == []


def test_rejects_when_input_dir_is_symlink_to_dir(tmp_path, input_data):
    real_in = tmp_path / "real_in"
    real_in.mkdir()
    _write_inputs(real_in, base=input_data)
    link_in = tmp_path / "in_link"
    link_in.symlink_to(real_in)
    out_dir = tmp_path / "ol"
    out_dir.mkdir()
    res = subprocess.run([*_java_cmd(link_in, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert sorted(p.name for p in out_dir.iterdir()) == []


def test_rejects_when_output_dir_is_file(tmp_path, input_data):
    in_dir = tmp_path / "g"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    f_out = tmp_path / "isfile"
    f_out.write_text("hi\n")
    orig = f_out.read_bytes()
    res = subprocess.run([*_java_cmd(in_dir, f_out)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert f_out.is_file()
    assert f_out.read_bytes() == orig


@pytest.mark.parametrize("blocker_name", list(ALL_OUT_NAMES))
def test_atomic_blocker_directory(tmp_path, input_data, blocker_name):
    in_dir = tmp_path / f"in_{blocker_name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"blk_{blocker_name}"
    out_dir.mkdir()
    blk = out_dir / blocker_name
    blk.mkdir()
    (blk / "decoy").write_text("keep")
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [blocker_name]
    assert blk.is_dir()
    assert (blk / "decoy").read_text() == "keep"


@pytest.mark.parametrize("name", list(ALL_OUT_NAMES))
def test_atomic_rejects_preexisting_file(tmp_path, input_data, name):
    in_dir = tmp_path / f"ip_{name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"p_{name}"
    out_dir.mkdir()
    s = out_dir / name
    s.write_text("sentinel\n")
    orig = s.read_bytes()
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert sorted(p.name for p in out_dir.iterdir()) == [name]
    assert s.read_bytes() == orig


@pytest.mark.parametrize("name", list(ALL_OUT_NAMES))
def test_atomic_rejects_preexisting_partial(tmp_path, input_data, name):
    in_dir = tmp_path / f"ipp_{name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"pp_{name}"
    out_dir.mkdir()
    pn = name + ".partial"
    stale = out_dir / pn
    stale.write_text("stale\n")
    orig = stale.read_bytes()
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert sorted(p.name for p in out_dir.iterdir()) == [pn]
    assert stale.read_bytes() == orig


@pytest.mark.parametrize("name", list(ALL_OUT_NAMES))
def test_atomic_rejects_preexisting_symlink(tmp_path, input_data, name):
    in_dir = tmp_path / f"il_{name}"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / f"l_{name}"
    out_dir.mkdir()
    s = out_dir / name
    target = tmp_path / f"abs_{name}"
    s.symlink_to(target)
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=60)
    assert res.returncode != 0
    assert sorted(p.name for p in out_dir.iterdir()) == [name]
    assert s.is_symlink()


def test_no_stray_temporaries_on_success(tmp_path, input_data):
    in_dir = tmp_path / "ic"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "oc"
    out_dir.mkdir()
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    entries = {p.name for p in out_dir.iterdir()}
    assert entries == set(ALL_OUT_NAMES)


def test_rename_order_alphabetical_by_ctime(tmp_path, input_data):
    """rename(2) is performed in alphabetical filename order; the resulting
    ctimes (ns granularity) of the five final outputs must be monotonically
    non-decreasing in that order."""
    in_dir = tmp_path / "in_ro"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "out_ro"
    out_dir.mkdir()
    res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    ordered = sorted(ALL_OUT_NAMES)
    times = [(out_dir / n).stat().st_ctime_ns for n in ordered]
    for prev, nxt in zip(times, times[1:]):
        assert prev <= nxt, (
            f"ctimes are not non-decreasing in alphabetical order: "
            f"{list(zip(ordered, times))}"
        )


def test_rejects_io_failure_unwritable_out_dir(tmp_path, input_data):
    """IO failure path: when <out_dir> is not writable, the binary must exit
    non-zero and leave the directory empty (no .partial residue)."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses unix permissions")
    in_dir = tmp_path / "in_io"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "out_io"
    out_dir.mkdir()
    out_dir.chmod(0o500)
    try:
        res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode != 0
    finally:
        out_dir.chmod(0o700)
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [], (
        f"out_dir must remain empty on IO failure, found: {entries}"
    )


def test_rejects_when_output_dir_is_fifo(tmp_path, input_data):
    """A FIFO at <out_dir> is not a real directory; the binary must exit
    non-zero and leave the FIFO untouched."""
    in_dir = tmp_path / "in_fifo"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    fifo = tmp_path / "out_fifo"
    os.mkfifo(str(fifo))
    try:
        res = subprocess.run([*_java_cmd(in_dir, fifo)],
                             capture_output=True, text=True, timeout=10)
        assert res.returncode != 0
        assert stat.S_ISFIFO(fifo.lstat().st_mode)
    finally:
        if fifo.exists():
            fifo.unlink()


def test_rejects_when_input_dir_is_fifo(tmp_path, input_data):
    """A FIFO at <in_dir> is not a real directory; the binary must exit
    non-zero and leave <out_dir> empty."""
    fifo = tmp_path / "in_fifo"
    os.mkfifo(str(fifo))
    out_dir = tmp_path / "out_ff"
    out_dir.mkdir()
    try:
        res = subprocess.run([*_java_cmd(fifo, out_dir)],
                             capture_output=True, text=True, timeout=10)
        assert res.returncode != 0
        assert sorted(p.name for p in out_dir.iterdir()) == []
    finally:
        if fifo.exists():
            fifo.unlink()


def test_rejects_io_failure_unreadable_in_dir(tmp_path, input_data):
    """IO failure: when <in_dir> denies read (chmod 0o100), reads of
    events.json/config.json fail and the binary must exit non-zero with no
    outputs written."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses unix permissions")
    in_dir = tmp_path / "in_ur"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    in_dir.chmod(0o100)
    out_dir = tmp_path / "out_ur"
    out_dir.mkdir()
    try:
        res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode != 0
    finally:
        in_dir.chmod(0o700)
    entries = sorted(p.name for p in out_dir.iterdir())
    assert entries == [], (
        f"out_dir must remain empty on IO failure, found: {entries}"
    )


def test_rejects_io_failure_unreadable_events_file(tmp_path, input_data):
    """IO failure: when events.json itself is unreadable, the binary must
    exit non-zero with no outputs written and the input untouched."""
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("root bypasses unix permissions")
    in_dir = tmp_path / "in_uef"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    ev = in_dir / "events.json"
    orig = ev.read_bytes()
    ev.chmod(0o000)
    out_dir = tmp_path / "out_uef"
    out_dir.mkdir()
    try:
        res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                             capture_output=True, text=True, timeout=60)
        assert res.returncode != 0
    finally:
        ev.chmod(0o600)
    assert ev.read_bytes() == orig
    assert sorted(p.name for p in out_dir.iterdir()) == []


# -----------------------------------------------------------------------------
# Direct .partial usage verification via Linux inotify (ctypes-based, no
# external dependency). The binary's spec requires writing via "<name>.partial"
# staging followed by rename(2). inotify gives us a direct record of CREATE
# (.partial appears) and MOVED_TO (rename target appears) events.
# -----------------------------------------------------------------------------

import ctypes  # noqa: E402
import ctypes.util  # noqa: E402
import select  # noqa: E402
import struct  # noqa: E402
import threading  # noqa: E402

_IN_CREATE = 0x00000100
_IN_MOVED_TO = 0x00000080


def _inotify_available() -> bool:
    libc = ctypes.util.find_library("c")
    if not libc:
        return False
    try:
        lib = ctypes.CDLL(libc, use_errno=True)
        return hasattr(lib, "inotify_init1") and hasattr(lib, "inotify_add_watch")
    except OSError:
        return False


def _watch_dir_events(out_dir: Path, stop_evt: threading.Event,
                      sink: list[tuple[int, str]]):
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    fd = libc.inotify_init1(0o4000)  # IN_NONBLOCK
    if fd < 0:
        return
    wd = libc.inotify_add_watch(fd, str(out_dir).encode("utf-8"),
                                _IN_CREATE | _IN_MOVED_TO)
    if wd < 0:
        os.close(fd)
        return
    try:
        while not stop_evt.is_set():
            r, _, _ = select.select([fd], [], [], 0.05)
            if not r:
                continue
            buf = os.read(fd, 65536)
            i = 0
            while i + 16 <= len(buf):
                _, mask, _, nlen = struct.unpack_from("iIII", buf, i)
                i += 16
                name = buf[i:i + nlen].rstrip(b"\x00").decode("utf-8", "replace")
                i += nlen
                if name:
                    sink.append((mask, name))
    finally:
        os.close(fd)


def test_binary_uses_partial_then_rename(tmp_path, input_data):
    """Directly verify the .partial-then-rename contract: while the binary
    runs, every final output must be preceded by a same-named `.partial`
    creation (CREATE) and reach its final name via inotify MOVED_TO
    (rename(2)). This proves the staging mechanism, not just side effects."""
    if not _inotify_available():
        pytest.skip("inotify (libc) not available on this platform")
    in_dir = tmp_path / "in_part"
    in_dir.mkdir()
    _write_inputs(in_dir, base=input_data)
    out_dir = tmp_path / "out_part"
    out_dir.mkdir()
    sink: list[tuple[int, str]] = []
    stop = threading.Event()
    t = threading.Thread(
        target=_watch_dir_events, args=(out_dir, stop, sink), daemon=True
    )
    t.start()
    try:
        res = subprocess.run([*_java_cmd(in_dir, out_dir)],
                             capture_output=True, text=True, timeout=120)
        assert res.returncode == 0, res.stderr
        # Give the watcher a moment to flush remaining queued events.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        stop.set()
        t.join(timeout=2.0)
    creates = [n for mask, n in sink if mask & _IN_CREATE]
    moved_to = [n for mask, n in sink if mask & _IN_MOVED_TO]
    for name in ALL_OUT_NAMES:
        assert (name + ".partial") in creates, (
            f"expected .partial create for {name}, saw creates={creates}"
        )
        assert name in moved_to, (
            f"expected rename(2) target {name}, saw moved_to={moved_to}"
        )


# -----------------------------------------------------------------------------
# Authoritative JSON-Schema validation (instruction declares /app/schemas/ as
# the authoritative source). Every produced output must validate against the
# corresponding schema shipped in the container; if a schema file is missing
# from the image (different evaluation environment) we skip cleanly rather
# than mis-fail.
# -----------------------------------------------------------------------------

SCHEMAS_DIR = Path("/app/schemas")

_SCHEMA_MAP = {
    "cache_state.json": "cache_state.schema.json",
    "decisions.json": "decisions.schema.json",
    "event_audit.json": "event_audit.schema.json",
    "summary.json": "summary.schema.json",
    "violations.json": "violations.schema.json",
}


def _require_jsonschema():
    """jsonschema is a hard test dependency installed by test.sh."""
    import jsonschema  # noqa: F401
    return jsonschema


@pytest.mark.parametrize("output_name,schema_name", list(_SCHEMA_MAP.items()))
def test_output_validates_against_schema(
    binary_run_outputs, output_name, schema_name,
):
    """Each emitted output MUST validate against the authoritative JSON Schema
    published in /app/schemas/. This is a hard requirement: the schema files
    are shipped in the container by the Dockerfile, so absence is a failure."""
    jsonschema = _require_jsonschema()
    schema_path = SCHEMAS_DIR / schema_name
    assert schema_path.is_file(), (
        f"authoritative schema missing from image: {schema_path}"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    data = binary_run_outputs[OUT_DIR / output_name]
    jsonschema.validate(instance=data, schema=schema)


def _load_input_schema(name: str):
    p = SCHEMAS_DIR / name
    assert p.is_file(), f"authoritative schema missing from image: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def test_bundled_inputs_validate_against_input_schemas(input_data):
    """The bundled events.json/config.json must satisfy the authoritative
    /app/schemas/{events,config}.schema.json. This anchors the rest of the
    rejection tests against the same authoritative schema set."""
    jsonschema = _require_jsonschema()
    events_schema = _load_input_schema("events.schema.json")
    config_schema = _load_input_schema("config.schema.json")
    jsonschema.validate(instance=input_data["events"], schema=events_schema)
    jsonschema.validate(instance=input_data["config"], schema=config_schema)


# Pairs of (input description, malformed events.json body). Each must be
# rejected by both /app/schemas/events.schema.json AND the binary, ensuring
# the binary enforces the same authoritative input schema, not a looser one.
_INPUT_SCHEMA_REJECT_CASES = [
    ("event_id_missing",
     {"events": [{"ts_unix_ms": 1, "type": "access",
                  "payload": {"key": "k", "weight": 1}}]}),
    ("ts_missing",
     {"events": [{"event_id": "e", "type": "access",
                  "payload": {"key": "k", "weight": 1}}]}),
    ("type_missing",
     {"events": [{"event_id": "e", "ts_unix_ms": 1,
                  "payload": {"key": "k", "weight": 1}}]}),
    ("payload_missing",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "clear"}]}),
    ("event_id_wrong_type",
     {"events": [{"event_id": 1, "ts_unix_ms": 1, "type": "access",
                  "payload": {"key": "k", "weight": 1}}]}),
    ("ts_wrong_type",
     {"events": [{"event_id": "e", "ts_unix_ms": "1", "type": "access",
                  "payload": {"key": "k", "weight": 1}}]}),
    ("weight_zero",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "access",
                  "payload": {"key": "k", "weight": 0}}]}),
    ("weight_seventeen",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "access",
                  "payload": {"key": "k", "weight": 17}}]}),
    ("weight_float",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "access",
                  "payload": {"key": "k", "weight": 1.5}}]}),
    ("type_unknown",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "noop",
                  "payload": {}}]}),
    ("event_extra_top_key",
     {"events": [], "extra": 1}),
    ("event_payload_wrong_type",
     {"events": [{"event_id": "e", "ts_unix_ms": 1, "type": "access",
                  "payload": "nope"}]}),
]


@pytest.mark.parametrize("name,bad", _INPUT_SCHEMA_REJECT_CASES,
                         ids=[c[0] for c in _INPUT_SCHEMA_REJECT_CASES])
def test_inputs_violating_schema_are_rejected(
    tmp_path, input_data, name, bad,
):
    """For each malformed events.json: it must fail jsonschema validation AND
    the binary must exit non-zero with no outputs. This binds binary
    behaviour to /app/schemas/events.schema.json across many violation kinds.
    """
    jsonschema = _require_jsonschema()
    events_schema = _load_input_schema("events.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=bad, schema=events_schema)
    in_dir = tmp_path / f"ivs_{name}"
    in_dir.mkdir()
    out_dir = tmp_path / f"ivs_{name}_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


_CONFIG_SCHEMA_REJECT_CASES = [
    ("missing", {}),
    ("wrong_type", {"cache_size": "8"}),
    ("zero", {"cache_size": 0}),
    ("negative", {"cache_size": -3}),
    ("over_max", {"cache_size": 257}),
    ("extra_key", {"cache_size": 8, "bonus": 1}),
    ("float", {"cache_size": 1.5}),
]


@pytest.mark.parametrize("name,cfg", _CONFIG_SCHEMA_REJECT_CASES,
                         ids=[c[0] for c in _CONFIG_SCHEMA_REJECT_CASES])
def test_config_violating_schema_is_rejected(
    tmp_path, input_data, name, cfg,
):
    jsonschema = _require_jsonschema()
    config_schema = _load_input_schema("config.schema.json")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=cfg, schema=config_schema)
    in_dir = tmp_path / f"cvs_{name}"
    in_dir.mkdir()
    out_dir = tmp_path / f"cvs_{name}_o"
    _write_inputs(in_dir, base=input_data, config=cfg)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


# -----------------------------------------------------------------------------
# Extra schema-violation rejection coverage (every required key, payload type,
# and primitive type must be enforced by the binary, not just a subset).
# -----------------------------------------------------------------------------

@pytest.mark.parametrize("drop_key", [
    "event_id", "ts_unix_ms", "type", "payload",
])
def test_rejects_event_record_missing_required_key(
    tmp_path, input_data, drop_key,
):
    rec = {"event_id": "e1", "ts_unix_ms": 1, "type": "access",
           "payload": {"key": "k", "weight": 1}}
    rec.pop(drop_key)
    bad = {"events": [rec]}
    in_dir = tmp_path / f"mrk_{drop_key}"
    in_dir.mkdir()
    out_dir = tmp_path / f"mrk_{drop_key}_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


@pytest.mark.parametrize("drop_key", ["key", "weight"])
def test_rejects_access_payload_missing_required_key(
    tmp_path, input_data, drop_key,
):
    payload = {"key": "k", "weight": 1}
    payload.pop(drop_key)
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": payload}]}
    in_dir = tmp_path / f"apm_{drop_key}"
    in_dir.mkdir()
    out_dir = tmp_path / f"apm_{drop_key}_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_evict_payload_missing_key(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "evict",
                       "payload": {}}]}
    in_dir = tmp_path / "evmk"
    in_dir.mkdir()
    out_dir = tmp_path / "evmk_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_event_id_wrong_type(tmp_path, input_data):
    bad = {"events": [{"event_id": 1, "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": "k", "weight": 1}}]}
    in_dir = tmp_path / "etwt"
    in_dir.mkdir()
    out_dir = tmp_path / "etwt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_ts_unix_ms_wrong_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": "1", "type": "access",
                       "payload": {"key": "k", "weight": 1}}]}
    in_dir = tmp_path / "tswt"
    in_dir.mkdir()
    out_dir = tmp_path / "tswt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_weight_wrong_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": "k", "weight": 1.5}}]}
    in_dir = tmp_path / "wwt"
    in_dir.mkdir()
    out_dir = tmp_path / "wwt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_key_wrong_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": {"key": 7, "weight": 1}}]}
    in_dir = tmp_path / "kwt"
    in_dir.mkdir()
    out_dir = tmp_path / "kwt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_payload_wrong_type(tmp_path, input_data):
    bad = {"events": [{"event_id": "e1", "ts_unix_ms": 1, "type": "access",
                       "payload": "not_an_object"}]}
    in_dir = tmp_path / "pwt"
    in_dir.mkdir()
    out_dir = tmp_path / "pwt_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_config_missing_cache_size(tmp_path, input_data):
    in_dir = tmp_path / "cms"
    in_dir.mkdir()
    out_dir = tmp_path / "cms_o"
    _write_inputs(in_dir, base=input_data, config={})
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_config_cache_size_wrong_type(tmp_path, input_data):
    in_dir = tmp_path / "ccwt"
    in_dir.mkdir()
    out_dir = tmp_path / "ccwt_o"
    _write_inputs(in_dir, base=input_data, config={"cache_size": "8"})
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_events_top_level_extra_key(tmp_path, input_data):
    bad = {"events": input_data["events"]["events"], "extra": 1}
    in_dir = tmp_path / "tlx"
    in_dir.mkdir()
    out_dir = tmp_path / "tlx_o"
    _write_inputs(in_dir, base=input_data, events=bad)
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))


def test_rejects_events_top_level_missing_events_key(tmp_path, input_data):
    in_dir = tmp_path / "tlm"
    in_dir.mkdir()
    out_dir = tmp_path / "tlm_o"
    _write_inputs(in_dir, base=input_data, events={})
    _assert_rejected_no_output(out_dir, _run(in_dir, out_dir))
