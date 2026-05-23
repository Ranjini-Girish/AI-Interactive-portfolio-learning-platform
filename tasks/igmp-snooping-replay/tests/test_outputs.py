"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import pytest


DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
BINARY_PATH = Path("/app/build/igmpsnoop")
SCHEMA_DIR = Path("/app/schemas")

PORTS_PATH = DATA_DIR / "ports.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

MCAST_TABLE_PATH = OUT_DIR / "mcast_table.json"
FORWARD_LOG_PATH = OUT_DIR / "forward_log.json"
DIAG_PATH = OUT_DIR / "igmp_diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
ALL_OUT_PATHS = (MCAST_TABLE_PATH, FORWARD_LOG_PATH, DIAG_PATH, SUMMARY_PATH)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    PORTS_PATH:   "fd4bfcae78cb35b8d1de739e2c2ca93ce4a5b3c75b5ca675a80b3ea932b6e4ba",
    EVENTS_PATH:  "5d6aef82f775ac58d2cbce8ca2390585a6593ac477d9425692027029b67102e6",
    POLICY_PATH:  "8a41b878d50e567768c80d4f0fa3d86d0aef0cd5de66f90e2e25e5f53f5e8ffd",
}


# ---------------------------------------------------------------------------
# Reference simulator (RefSim)
# ---------------------------------------------------------------------------


def _is_link_local(g: str) -> bool:
    p = g.split(".")
    return len(p) == 4 and p[0] == "224" and p[1] == "0" and p[2] == "0"


@dataclass
class RefSim:
    ports: dict[str, dict[str, Any]]
    policy: dict[str, Any]
    members: dict[tuple[int, str], dict[str, dict[str, Any]]] = field(default_factory=dict)
    link_state: dict[str, bool] = field(default_factory=dict)
    now: int = 0
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    forwards: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=lambda: {
        "diagnostic_count": 0,
        "frames_dropped": 0,
        "frames_flooded": 0,
        "frames_forwarded": 0,
        "leave_events": 0,
        "mcast_frame_events": 0,
        "member_count": 0,
        "report_events": 0,
        "tick_events": 0,
        "total_ticks_advanced_sec": 0,
    })

    def _emit(self, seq, sev, code, name):
        self.diagnostics.append({"code": code, "name": name, "seq": seq, "severity": sev})

    def _link_up(self, p):
        return self.link_state.get(p, True)

    def _record_forward(self, ev, decision, egress, reason):
        if not self.policy.get("track_forwarding", True):
            return
        self.forwards.append({
            "decision": decision,
            "egress_ports": sorted(egress),
            "group": ev["group"],
            "ingress_port": ev["ingress_port"],
            "reason": reason,
            "seq": ev["seq"],
            "vlan": ev["vlan"],
        })

    def _bump(self, d):
        if d == "forwarded":
            self.totals["frames_forwarded"] += 1
        elif d == "flooded":
            self.totals["frames_flooded"] += 1
        else:
            self.totals["frames_dropped"] += 1

    def step(self, ev):
        seq = ev["seq"]
        op = ev["op"]
        if op in ("igmp_report", "igmp_leave"):
            port = ev["port"]
            group = ev["group"]
            vlan = ev["vlan"]
            if port not in self.ports:
                raise ValueError(f"unknown port {port}")
            p = self.ports[port]
            if p["vlan"] != vlan:
                raise ValueError("port vlan mismatch")
            if _is_link_local(group):
                raise ValueError("link-local group not allowed on report/leave")
            if op == "igmp_report":
                self.totals["report_events"] += 1
                if p["role"] == "router":
                    return
                key = (vlan, group)
                bucket = self.members.setdefault(key, {})
                if port in bucket:
                    self._emit(seq, "note", "W_REPORT_REFRESH", port)
                bucket[port] = {"last_seen_time": self.now}
            else:
                self.totals["leave_events"] += 1
                if p["role"] == "router":
                    return
                key = (vlan, group)
                bucket = self.members.get(key, {})
                if self.policy.get("fast_leave", False):
                    if port in bucket:
                        del bucket[port]
                    if key in self.members and not self.members[key]:
                        del self.members[key]
                    self._emit(seq, "note", "W_FAST_LEAVE", port)
                else:
                    if port not in bucket:
                        self._emit(seq, "warning", "E_LEAVE_UNKNOWN_GROUP", port)
                    else:
                        del bucket[port]
                        if not bucket:
                            del self.members[key]
        elif op == "mcast_frame":
            self.totals["mcast_frame_events"] += 1
            ingress = ev["ingress_port"]
            if ingress not in self.ports:
                raise ValueError(f"unknown ingress {ingress}")
            p = self.ports[ingress]
            if p["vlan"] != ev["vlan"]:
                self._emit(seq, "warning", "E_INGRESS_VLAN_MISMATCH", ingress)
                self._record_forward(ev, "dropped", [], "vlan_mismatch")
                self._bump("dropped")
                return
            if not self._link_up(ingress):
                self._emit(seq, "warning", "E_INGRESS_PORT_DOWN", ingress)
                self._record_forward(ev, "dropped", [], "ingress_port_down")
                self._bump("dropped")
                return
            vlan = ev["vlan"]
            group = ev["group"]
            if _is_link_local(group):
                eg = sorted([
                    pid for pid, pp in self.ports.items()
                    if pid != ingress and self._link_up(pid) and pp["vlan"] == vlan
                ])
                self._record_forward(ev, "flooded", eg, None)
                self._bump("flooded")
                return
            eg_set = set()
            for pid, pp in self.ports.items():
                if pid == ingress:
                    continue
                if not self._link_up(pid):
                    continue
                if pp["vlan"] != vlan:
                    continue
                if pp["role"] == "router":
                    eg_set.add(pid)
            for pid in self.members.get((vlan, group), {}).keys():
                if pid == ingress:
                    continue
                if not self._link_up(pid):
                    continue
                pp = self.ports.get(pid)
                if pp is None or pp["vlan"] != vlan:
                    continue
                eg_set.add(pid)
            eg = sorted(eg_set)
            if not eg:
                if self.policy.get("drop_unknown_groups", False):
                    self._emit(seq, "note", "W_DROPPED_NO_MEMBERS", group)
                    self._record_forward(ev, "dropped", [], "no_members")
                    self._bump("dropped")
                    return
                fb = sorted([
                    pid for pid, pp in self.ports.items()
                    if pid != ingress and self._link_up(pid) and pp["vlan"] == vlan
                ])
                self._record_forward(ev, "flooded", fb, None)
                self._bump("flooded")
                return
            decision = "forwarded" if len(eg) == 1 else "flooded"
            self._record_forward(ev, decision, eg, None)
            self._bump(decision)
        elif op == "port_link_change":
            port = ev["port"]
            if port not in self.ports:
                raise ValueError(f"unknown port {port}")
            new_state = ev["up"]
            prev = self._link_up(port)
            if prev == new_state:
                self._emit(seq, "note", "W_LINK_NOOP", port)
                self.link_state[port] = new_state
                return
            self.link_state[port] = new_state
            if not new_state:
                removed = False
                for key in list(self.members.keys()):
                    if port in self.members[key]:
                        del self.members[key][port]
                        removed = True
                        if not self.members[key]:
                            del self.members[key]
                if removed:
                    self._emit(seq, "note", "W_LINK_DOWN_PURGE", port)
        elif op == "tick":
            delta = ev["delta_sec"]
            self.totals["tick_events"] += 1
            self.totals["total_ticks_advanced_sec"] += delta
            self.now += delta
            ttl = self.policy["ttl_sec"]
            for key in list(self.members.keys()):
                bucket = self.members[key]
                aged = sorted([pid for pid, m in bucket.items()
                               if (self.now - m["last_seen_time"]) > ttl])
                for pid in aged:
                    del bucket[pid]
                    self._emit(seq, "note", "W_MEMBER_AGED", pid)
                if not bucket:
                    del self.members[key]
        else:
            raise ValueError(f"unknown op {op}")

    def finalize(self):
        sev_rank = {"error": 3, "warning": 2, "note": 1}
        diag_sorted = sorted(
            self.diagnostics,
            key=lambda d: (d["seq"], -sev_rank[d["severity"]], d["code"], d["name"]),
        )
        self.totals["diagnostic_count"] = len(diag_sorted)
        groups = []
        for (vlan, group), bucket in self.members.items():
            members = sorted(
                ({"last_seen_time": m["last_seen_time"], "port": pid}
                 for pid, m in bucket.items()),
                key=lambda m: m["port"],
            )
            groups.append({"group": group, "members": members, "vlan": vlan})
        groups.sort(key=lambda g: (g["vlan"], g["group"]))
        member_count = sum(len(g["members"]) for g in groups)
        self.totals["member_count"] = member_count
        active_groups = sorted({g["group"] for g in groups})
        return {
            "mcast_table": {"groups": groups},
            "forward_log": {
                "forwards": sorted(self.forwards, key=lambda f: f["seq"])
                if self.policy.get("track_forwarding", True) else []
            },
            "igmp_diagnostics": {"diagnostics": diag_sorted},
            "summary": {
                "active_groups": active_groups,
                "totals": dict(sorted(self.totals.items())),
            },
        }


def run_simulation(ports, events, policy):
    pmap = {p["port_id"]: p for p in ports}
    sim = RefSim(ports=pmap, policy=policy)
    for ev in events:
        sim.step(ev)
    return sim.finalize()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"


SOURCE_SUFFIXES = (".ts",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {"Makefile", "GNUmakefile", "makefile", "CMakeLists.txt", "build.ninja"}


def _src_files() -> list[Path]:
    out: list[Path] = []
    for root in (Path("/app/src"), Path("/app/src")):
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


def _snapshot_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            out[os.fspath(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _snapshot_metadata(root: Path) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            out[os.fspath(p)] = (st.st_mode, st.st_size, int(st.st_mtime))
    return out


def _snapshot_paths(root: Path) -> set[str]:
    out: set[str] = set()
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            out.add(os.fspath(p))
    return out


@pytest.fixture(scope="module")
def inputs() -> dict[str, Any]:
    return {
        "ports": load_json(PORTS_PATH)["ports"],
        "events": load_json(EVENTS_PATH)["events"],
        "policy": load_json(POLICY_PATH),
    }


@pytest.fixture(scope="module")
def expected(inputs: dict[str, Any]) -> dict[str, Any]:
    return run_simulation(inputs["ports"], inputs["events"], inputs["policy"])


@pytest.fixture(scope="module")
def binary_run_outputs() -> dict[str, Any]:
    if not BINARY_PATH.exists():
        pytest.skip(f"binary {BINARY_PATH} not built; agent did not produce one")
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"binary exit {proc.returncode}; stdout={proc.stdout!r}; stderr={proc.stderr!r}"
        )
    out: dict[str, Any] = {}
    for path, key in [
        (MCAST_TABLE_PATH, "mcast_table"),
        (FORWARD_LOG_PATH, "forward_log"),
        (DIAG_PATH, "igmp_diagnostics"),
        (SUMMARY_PATH, "summary"),
    ]:
        if not path.exists():
            raise RuntimeError(f"binary did not produce {path}")
        out[key] = load_json(path)
    return out


def test_data_unchanged():
    """Anti-cheat: each /app/data/*.json file's sha256 still matches the
    pre-pinned hash, so the agent cannot tamper with the inputs to make
    the live reference and the binary agree on a doctored trace."""
    for path, expected_hash in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input {path} missing"
        actual = sha256_of(path)
        assert actual == expected_hash, (
            f"{path} sha256 mismatch (expected {expected_hash}, got {actual}); "
            "did you modify /app/data/?"
        )


def test_data_dir_only_known_files():
    """/app/data/ contains exactly the three named JSON inputs (no
    extras, no symlinks) -- the agent must not stash scratch data
    under /app/data/."""
    expected_names = {"ports.json", "events.json", "policy.json"}
    entries = list(DATA_DIR.iterdir())
    assert {e.name for e in entries} == expected_names
    for e in entries:
        assert e.is_file() and not e.is_symlink()


def test_binary_exists():
    """The agent shipped a file at /app/build/igmpsnoop and it is
    marked executable -- otherwise the verifier cannot invoke it."""
    assert BINARY_PATH.exists()
    assert BINARY_PATH.stat().st_mode & 0o111








def test_app_layout_no_unexpected_files():
    """/app's top level contains only the documented directories
    (build, data, docs, examples, include, output, schemas, src) and
    no stray files. Blocks agents that drop helper scripts or temp
    artefacts at /app's root."""
    allowed_dirs = {"build", "data", "docs", "examples", "include", "output", "schemas", "src"}
    app = Path("/app")
    assert app.is_dir()
    for entry in app.iterdir():
        if entry.is_dir():
            assert entry.name in allowed_dirs, (
                f"unexpected dir at /app/{entry.name}; allowed: {sorted(allowed_dirs)}"
            )
        else:
            raise AssertionError(f"unexpected file at /app/{entry.name}")






def test_schemas_dir_present_and_parsable():
    """/app/schemas/ ships all seven required schemas (three input,
    four output) and every one parses as valid JSON. Guards the
    schema-validation contract used by the next two tests."""
    expected = {
        "ports_input.schema.json",
        "events_input.schema.json",
        "policy_input.schema.json",
        "mcast_table.schema.json",
        "forward_log.schema.json",
        "igmp_diagnostics.schema.json",
        "summary.schema.json",
    }
    assert SCHEMA_DIR.is_dir()
    have = {p.name for p in SCHEMA_DIR.iterdir() if p.is_file()}
    assert expected.issubset(have), f"missing schemas: {expected - have}"
    for name in expected:
        with (SCHEMA_DIR / name).open() as f:
            json.load(f)


def _validate(json_path: Path, schema_path: Path) -> None:
    schema = json.loads(schema_path.read_text())
    instance = json.loads(json_path.read_text())
    jsonschema.validate(instance=instance, schema=schema)


def test_inputs_conform_to_schemas():
    """The bundled /app/data/{ports,events,policy}.json each validate
    against their JSON Schema. A failure here means the shipped trace
    itself is malformed, which would be a task-author bug."""
    _validate(PORTS_PATH, SCHEMA_DIR / "ports_input.schema.json")
    _validate(EVENTS_PATH, SCHEMA_DIR / "events_input.schema.json")
    _validate(POLICY_PATH, SCHEMA_DIR / "policy_input.schema.json")


def test_outputs_conform_to_schemas(binary_run_outputs):
    """Each of the four output files (mcast_table, forward_log,
    igmp_diagnostics, summary) validates against its JSON Schema.
    Cheaper structural gate before the byte-for-byte reference check."""
    _validate(MCAST_TABLE_PATH, SCHEMA_DIR / "mcast_table.schema.json")
    _validate(FORWARD_LOG_PATH, SCHEMA_DIR / "forward_log.schema.json")
    _validate(DIAG_PATH, SCHEMA_DIR / "igmp_diagnostics.schema.json")
    _validate(SUMMARY_PATH, SCHEMA_DIR / "summary.schema.json")


def test_diagnostics_codes_are_in_docs_closed_set(binary_run_outputs):
    """Every diagnostic code in the binary's igmp_diagnostics.json is
    one of the codes documented in /app/docs/diagnostics.md. Catches
    agents that invent their own codes outside the closed catalogue."""
    docs_path = Path("/app/docs/diagnostics.md")
    assert docs_path.exists()
    docs_text = docs_path.read_text(encoding="utf-8")
    docs_codes = set(re.findall(r"\b[EWN]_[A-Z_]+\b", docs_text))
    diag = binary_run_outputs["igmp_diagnostics"]["diagnostics"]
    produced_codes = {d["code"] for d in diag}
    leaked = produced_codes - docs_codes
    assert not leaked, (
        f"binary emitted codes not in docs: {leaked}"
    )


def test_outputs_have_no_extra_keys(binary_run_outputs):
    """Each output object has exactly the documented key set at every
    depth -- mcast_table, forward_log, igmp_diagnostics, summary, and
    summary.totals. Catches agents that pad outputs with diagnostic
    fields not in the spec."""
    mt = binary_run_outputs["mcast_table"]
    assert set(mt) == {"groups"}
    for g in mt["groups"]:
        assert set(g) == {"group", "members", "vlan"}, g
        for m in g["members"]:
            assert set(m) == {"last_seen_time", "port"}, m
    fl = binary_run_outputs["forward_log"]
    assert set(fl) == {"forwards"}
    for f in fl["forwards"]:
        assert set(f) == {"decision", "egress_ports", "group", "ingress_port",
                          "reason", "seq", "vlan"}, f
    diag = binary_run_outputs["igmp_diagnostics"]
    assert set(diag) == {"diagnostics"}
    for d in diag["diagnostics"]:
        assert set(d) == {"code", "name", "seq", "severity"}, d
    summary = binary_run_outputs["summary"]
    assert set(summary) == {"active_groups", "totals"}
    assert set(summary["totals"]) == {
        "diagnostic_count", "frames_dropped", "frames_flooded", "frames_forwarded",
        "leave_events", "mcast_frame_events", "member_count", "report_events",
        "tick_events", "total_ticks_advanced_sec",
    }


def test_summary_counter_invariants(binary_run_outputs):
    """summary.totals is internally consistent with the other outputs:
    frames_dropped + frames_flooded + frames_forwarded equals
    mcast_frame_events, member_count equals the sum of members across
    mcast_table.groups, and diagnostic_count equals the length of
    igmp_diagnostics.diagnostics."""
    t = binary_run_outputs["summary"]["totals"]
    assert t["frames_dropped"] + t["frames_flooded"] + t["frames_forwarded"] == t["mcast_frame_events"]
    member_count = sum(len(g["members"]) for g in binary_run_outputs["mcast_table"]["groups"])
    assert t["member_count"] == member_count
    assert t["diagnostic_count"] == len(binary_run_outputs["igmp_diagnostics"]["diagnostics"])


def test_outputs_strictly_ascii_canonical(binary_run_outputs):
    """Each output file is canonical JSON: pure ASCII (no CRLF, no
    tabs, no high bytes), and byte-identical to
    json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + '\\n'.
    Byte-level check, not just structural-equivalence."""
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        assert b"\r\n" not in raw
        assert b"\t" not in raw
        try:
            raw.decode("ascii")
        except UnicodeDecodeError as e:
            raise AssertionError(f"{path.name} not pure ASCII: {e}")
        obj = json.loads(raw)
        assert path.read_text(encoding="utf-8") == canonical(obj), (
            f"{path.name} not in canonical form"
        )


def test_app_filesystem_no_unrelated_writes(binary_run_outputs):
    """During a fresh binary run, content+metadata under /app/build,
    /app/src, /app/include, /app/data, /app/docs, /app/schemas,
    /app/examples stay byte-identical, no new files appear outside
    /app/output, and /tmp + /var/tmp pick up no agent scratch files.
    Blocks scratch-cache and side-channel cheats."""
    immutable_roots = (
        Path("/app/build"),
        Path("/app/src"),
        Path("/app/src"),
        Path("/app/data"),
        Path("/app/docs"),
        Path("/app/schemas"),
        Path("/app/examples"),
    )
    before_hashes: dict[str, str] = {}
    before_meta: dict[str, tuple[int, int, int]] = {}
    for root in immutable_roots + (Path("/app/output"),):
        before_hashes.update(_snapshot_hashes(root))
        before_meta.update(_snapshot_metadata(root))
    foreign_roots = (Path("/tmp"), Path("/var/tmp"))
    foreign_before: dict[Path, set[str]] = {r: _snapshot_paths(r) for r in foreign_roots}

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"binary failed: {proc.stderr}"

    after_hashes: dict[str, str] = {}
    after_meta: dict[str, tuple[int, int, int]] = {}
    for root in immutable_roots + (Path("/app/output"),):
        after_hashes.update(_snapshot_hashes(root))
        after_meta.update(_snapshot_metadata(root))
    for path_str, before in before_hashes.items():
        if any(path_str.startswith(os.fspath(r) + os.sep) for r in immutable_roots):
            after = after_hashes.get(path_str)
            assert after is not None, f"binary deleted {path_str}"
            assert after == before, f"binary modified {path_str}"
    for path_str, before_m in before_meta.items():
        if any(path_str.startswith(os.fspath(r) + os.sep) for r in immutable_roots):
            after_m = after_meta.get(path_str)
            assert after_m is not None
            assert after_m == before_m, (
                f"binary changed metadata of {path_str}"
            )
    new_paths = set(after_hashes) - set(before_hashes)
    output_root_str = os.fspath(OUT_DIR) + os.sep
    for p in new_paths:
        assert p.startswith(output_root_str), f"unexpected new file {p}"
    for r in foreign_roots:
        if not r.exists():
            continue
        new_foreign = sorted(_snapshot_paths(r) - foreign_before[r])
        new_foreign = [
            p for p in new_foreign
            if not p.startswith((
                "/tmp/.", "/var/tmp/.", "/tmp/uv-", "/tmp/tmp", "/tmp/pytest-",
                "/tmp/igmp_", "/tmp/_igmp",
            ))
        ]
        assert not new_foreign, f"binary wrote outside /app: {new_foreign[:10]}"


def test_outputs_dir_only_known_files(binary_run_outputs):
    """/app/output/ contains exactly the four named JSON outputs
    (mcast_table, forward_log, igmp_diagnostics, summary) -- no temp
    files, no logs, no extras."""
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual = {p.name for p in OUT_DIR.iterdir()}
    assert actual == expected_names


def test_outputs_match_reference_byte_for_byte(binary_run_outputs, expected):
    """Each of the four binary-produced outputs is byte-identical to
    the live RefSim reference run on the same /app/data inputs. The
    primary correctness gate -- if this passes, the agent's snooping
    state machine matches the spec down to canonical formatting."""
    for key, path in [
        ("mcast_table", MCAST_TABLE_PATH),
        ("forward_log", FORWARD_LOG_PATH),
        ("igmp_diagnostics", DIAG_PATH),
        ("summary", SUMMARY_PATH),
    ]:
        produced = path.read_text(encoding="utf-8")
        ref_text = canonical(expected[key])
        assert produced == ref_text, f"{path.name} differs from reference"


def test_idempotent_on_rerun(binary_run_outputs):
    """Running the binary a second time on the same inputs produces
    the same four output files byte-for-byte. Rules out non-determinism
    leaking from unordered_map iteration order or unsorted set traversal."""
    snapshots = {p: p.read_text(encoding="utf-8") for p in ALL_OUT_PATHS}
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    for p, prior in snapshots.items():
        assert p.read_text(encoding="utf-8") == prior


def test_binary_rejects_wrong_arg_counts():
    """The CLI contract is exactly two positional args. Zero, one, or
    three-or-more arguments must result in a non-zero exit, regardless
    of whether the supplied paths happen to exist."""
    for argv in ([], [str(DATA_DIR)], [str(DATA_DIR), str(OUT_DIR), "extra"]):
        proc = subprocess.run(
            [str(BINARY_PATH)] + argv, capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode != 0


def test_binary_honors_argv_paths(tmp_path):
    """Running the binary with a custom input dir + custom output dir
    under /tmp proves the binary reads from argv[1] and writes to
    argv[2], not to a hardcoded /app/data + /app/output pair. The
    custom output dir then gets schema-validated for all four files."""
    work = Path("/tmp/igmp_argv_test")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    ports_in = {"ports": [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "host", "vlan": 10},
        {"port_id": "Eth3", "role": "router", "vlan": 10},
    ]}
    events_in = {"events": [
        {"seq": 0, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "mcast_frame", "ingress_port": "Eth3",
         "group": "239.1.1.1", "vlan": 10, "len": 256},
    ]}
    policy_in = {"drop_unknown_groups": False, "fast_leave": False,
                 "track_forwarding": True, "ttl_sec": 300}
    (in_dir / "ports.json").write_text(canonical(ports_in))
    (in_dir / "events.json").write_text(canonical(events_in))
    (in_dir / "policy.json").write_text(canonical(policy_in))
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    expected_names = {"mcast_table.json", "forward_log.json",
                      "igmp_diagnostics.json", "summary.json"}
    actual = {p.name for p in out_dir.iterdir()}
    assert actual == expected_names
    mt = json.loads((out_dir / "mcast_table.json").read_text())
    assert mt["groups"] and mt["groups"][0]["group"] == "239.1.1.1"
    fl = json.loads((out_dir / "forward_log.json").read_text())
    assert fl["forwards"] and fl["forwards"][0]["decision"] == "forwarded"
    _validate(out_dir / "mcast_table.json", SCHEMA_DIR / "mcast_table.schema.json")
    _validate(out_dir / "forward_log.json", SCHEMA_DIR / "forward_log.schema.json")
    _validate(out_dir / "igmp_diagnostics.json", SCHEMA_DIR / "igmp_diagnostics.schema.json")
    _validate(out_dir / "summary.json", SCHEMA_DIR / "summary.schema.json")


# ---------------------------------------------------------------------------
# Malformed input rejection
# ---------------------------------------------------------------------------


def _make_inputs(ports, events, policy=None):
    work = Path("/tmp/igmp_malformed")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    if policy is None:
        policy = {"drop_unknown_groups": False, "fast_leave": False,
                  "track_forwarding": True, "ttl_sec": 300}
    (in_dir / "ports.json").write_text(canonical({"ports": ports}))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    return in_dir, out_dir


_OK_PORT = {"port_id": "Eth1", "role": "host", "vlan": 10}
_OK_PORT_R = {"port_id": "Eth2", "role": "router", "vlan": 10}
_OK_REPORT = {"seq": 0, "op": "igmp_report", "port": "Eth1",
              "group": "239.1.1.1", "vlan": 10}
_OK_FRAME = {"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
             "group": "239.1.1.1", "vlan": 10, "len": 256}


_MALFORMED_CASES = [
    ("ports_dup_port_id",
     [_OK_PORT, dict(_OK_PORT)], [_OK_REPORT], None),
    ("ports_unknown_role",
     [{"port_id": "Eth1", "role": "transit", "vlan": 10}], [_OK_REPORT], None),
    ("ports_vlan_zero",
     [dict(_OK_PORT, vlan=0)], [_OK_REPORT], None),
    ("ports_vlan_too_high",
     [dict(_OK_PORT, vlan=4095)], [_OK_REPORT], None),
    ("events_non_dense_seq",
     [_OK_PORT, _OK_PORT_R], [{"seq": 1, "op": "tick", "delta_sec": 1}], None),
    ("events_bad_op",
     [_OK_PORT, _OK_PORT_R], [{"seq": 0, "op": "foo"}], None),
    ("events_extra_field",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_REPORT, extra="x")], None),
    ("report_missing_field",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "igmp_report", "port": "Eth1", "vlan": 10}], None),
    ("report_link_local_group",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_REPORT, group="224.0.0.1")], None),
    ("report_non_multicast_group",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_REPORT, group="10.0.0.1")], None),
    ("report_unknown_port",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_REPORT, port="EthX")], None),
    ("report_vlan_mismatch",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_REPORT, vlan=20)], None),
    ("leave_extra_field",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "igmp_leave", "port": "Eth1",
       "group": "239.1.1.1", "vlan": 10, "extra": True}], None),
    ("leave_link_local",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "igmp_leave", "port": "Eth1",
       "group": "224.0.0.5", "vlan": 10}], None),
    ("frame_unknown_ingress",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_FRAME, ingress_port="EthX")], None),
    ("frame_len_too_small",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_FRAME, len=10)], None),
    ("frame_non_multicast_group",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_FRAME, group="10.0.0.1")], None),
    ("frame_extra_field",
     [_OK_PORT, _OK_PORT_R], [dict(_OK_FRAME, extra="x")], None),
    ("port_link_change_missing_up",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "port_link_change", "port": "Eth1"}], None),
    ("port_link_change_unknown_port",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "port_link_change", "port": "EthX", "up": False}], None),
    ("tick_extra_field",
     [_OK_PORT, _OK_PORT_R],
     [{"seq": 0, "op": "tick", "delta_sec": 1, "port": "Eth1"}], None),
    ("tick_missing_delta",
     [_OK_PORT, _OK_PORT_R], [{"seq": 0, "op": "tick"}], None),
    ("policy_missing_ttl",
     [_OK_PORT, _OK_PORT_R], [_OK_REPORT],
     {"drop_unknown_groups": False, "fast_leave": False, "track_forwarding": True}),
    ("policy_extra_field",
     [_OK_PORT, _OK_PORT_R], [_OK_REPORT],
     {"drop_unknown_groups": False, "fast_leave": False,
      "track_forwarding": True, "ttl_sec": 300, "extra": True}),
    ("policy_string_ttl",
     [_OK_PORT, _OK_PORT_R], [_OK_REPORT],
     {"drop_unknown_groups": False, "fast_leave": False,
      "track_forwarding": True, "ttl_sec": "300"}),
    ("policy_string_track",
     [_OK_PORT, _OK_PORT_R], [_OK_REPORT],
     {"drop_unknown_groups": False, "fast_leave": False,
      "track_forwarding": "yes", "ttl_sec": 300}),
]


@pytest.mark.parametrize("name,ports,events,policy", _MALFORMED_CASES,
                         ids=[c[0] for c in _MALFORMED_CASES])
def test_malformed_input_exits_nonzero(name, ports, events, policy):
    """Parametrized over the malformed-input matrix (duplicate port_id,
    out-of-range vlan, non-dense seq, unknown op, extra fields,
    link-local on report/leave, missing required fields, etc.) -- the
    binary must exit non-zero rather than producing partial outputs."""
    in_dir, out_dir = _make_inputs(ports, events, policy)
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        f"malformed scenario {name!r} did not cause exit-non-zero; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Targeted scenarios
# ---------------------------------------------------------------------------


def _run_synthetic(name, ports, events, policy):
    work = Path(f"/tmp/igmp_synth_{name}")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    (in_dir / "ports.json").write_text(canonical({"ports": ports}))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return {
        "mcast_table": json.loads((out_dir / "mcast_table.json").read_text()),
        "forward_log": json.loads((out_dir / "forward_log.json").read_text()),
        "igmp_diagnostics": json.loads((out_dir / "igmp_diagnostics.json").read_text()),
        "summary": json.loads((out_dir / "summary.json").read_text()),
    }


def test_router_port_floods_unconditionally():
    """A multicast frame for an unknown group, with one router-role
    port on the ingress VLAN, must be forwarded onto that router port
    even though no host has joined the group. Encodes the
    'router-ports are always egress' rule from forwarding.md."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "host", "vlan": 10},
        {"port_id": "Eth3", "role": "router", "vlan": 10},
    ]
    events = [
        {"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
         "group": "239.5.5.5", "vlan": 10, "len": 64},
    ]
    policy = {"drop_unknown_groups": True, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("router_floods", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "forwarded"
    assert fwd["egress_ports"] == ["Eth3"]


def test_link_local_always_flooded():
    """A frame whose group falls inside 224.0.0.0/24 (link-local
    multicast) is flooded on every other live port on the ingress VLAN,
    regardless of snooped membership and regardless of
    drop_unknown_groups. Verifies the link-local carve-out."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "host", "vlan": 10},
        {"port_id": "Eth3", "role": "host", "vlan": 20},
    ]
    events = [{"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
               "group": "224.0.0.1", "vlan": 10, "len": 64}]
    policy = {"drop_unknown_groups": True, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("link_local", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "flooded"
    assert fwd["egress_ports"] == ["Eth2"]


def test_no_members_drop_under_policy():
    """With drop_unknown_groups=true and no router and no host members,
    an unknown-group frame is dropped with reason='no_members' and a
    W_DROPPED_NO_MEMBERS diagnostic is emitted."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "host", "vlan": 10},
    ]
    events = [{"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
               "group": "239.5.5.5", "vlan": 10, "len": 64}]
    policy = {"drop_unknown_groups": True, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("no_members_drop", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "dropped"
    assert fwd["reason"] == "no_members"
    assert any(d["code"] == "W_DROPPED_NO_MEMBERS" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_no_members_fallback_floods():
    """Same no-members scenario as above but with
    drop_unknown_groups=false: the frame is flooded on every other
    live port on the ingress VLAN and no W_DROPPED_NO_MEMBERS
    diagnostic is emitted. Sibling-case to test_no_members_drop_under_policy."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "host", "vlan": 10},
    ]
    events = [{"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
               "group": "239.5.5.5", "vlan": 10, "len": 64}]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("no_members_flood", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "flooded"
    assert fwd["egress_ports"] == ["Eth2"]
    assert all(d["code"] != "W_DROPPED_NO_MEMBERS" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_member_aged_after_ttl():
    """A snooped membership is removed once the elapsed time since its
    last refresh exceeds ttl_sec, and a W_MEMBER_AGED diagnostic is
    emitted at the tick that caused the expiry."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "router", "vlan": 10},
    ]
    events = [
        {"seq": 0, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "tick", "delta_sec": 301},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("aging", ports, events, policy)
    assert out["mcast_table"]["groups"] == []
    assert any(d["code"] == "W_MEMBER_AGED" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_link_down_purges():
    """A port_link_change to up=false on a port that carries snooped
    members purges every membership entry for that port and emits a
    W_LINK_DOWN_PURGE diagnostic. Empty buckets disappear from
    mcast_table afterwards."""
    ports = [
        {"port_id": "Eth1", "role": "host", "vlan": 10},
        {"port_id": "Eth2", "role": "router", "vlan": 10},
    ]
    events = [
        {"seq": 0, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "port_link_change", "port": "Eth1", "up": False},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("purge", ports, events, policy)
    assert out["mcast_table"]["groups"] == []
    assert any(d["code"] == "W_LINK_DOWN_PURGE" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_link_noop_emitted():
    """A port_link_change that doesn't change a port's up/down state
    (here: port already up, new state up=true) emits a W_LINK_NOOP
    diagnostic without affecting memberships."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [{"seq": 0, "op": "port_link_change", "port": "Eth1", "up": True}]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("noop", ports, events, policy)
    assert any(d["code"] == "W_LINK_NOOP" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_report_refresh_emitted():
    """A second igmp_report from a port that already has an active
    membership entry for the (vlan, group) bumps last_seen_time and
    emits W_REPORT_REFRESH rather than treating the second report as
    a brand-new join."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [
        {"seq": 0, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("refresh", ports, events, policy)
    assert any(d["code"] == "W_REPORT_REFRESH" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_fast_leave_emitted():
    """With fast_leave=true, an igmp_leave from a host that holds
    the only membership entry tears down the entry immediately and
    emits W_FAST_LEAVE; the snooping table becomes empty."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [
        {"seq": 0, "op": "igmp_report", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "igmp_leave", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": True,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("fast_leave", ports, events, policy)
    assert any(d["code"] == "W_FAST_LEAVE" for d in
               out["igmp_diagnostics"]["diagnostics"])
    assert out["mcast_table"]["groups"] == []


def test_leave_unknown_emitted():
    """An igmp_leave for a (vlan, group) that the port never joined
    emits E_LEAVE_UNKNOWN_GROUP without modifying the snooping table
    (since fast_leave is off)."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [
        {"seq": 0, "op": "igmp_leave", "port": "Eth1",
         "group": "239.1.1.1", "vlan": 10},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("leave_unknown", ports, events, policy)
    assert any(d["code"] == "E_LEAVE_UNKNOWN_GROUP" for d in
               out["igmp_diagnostics"]["diagnostics"])


def test_router_port_silent_on_report_leave():
    """igmp_report / igmp_leave events arriving on a router-role port
    are silently ignored: no snooping entry, no diagnostic, no
    error. Membership state stays empty."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [
        {"seq": 0, "op": "igmp_report", "port": "Eth2",
         "group": "239.1.1.1", "vlan": 10},
        {"seq": 1, "op": "igmp_leave", "port": "Eth2",
         "group": "239.1.1.1", "vlan": 10},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("router_silent", ports, events, policy)
    assert out["mcast_table"]["groups"] == []
    assert out["igmp_diagnostics"]["diagnostics"] == []


def test_track_forwarding_off_yields_empty_log():
    """With track_forwarding=false, forward_log.json must be exactly
    {"forwards": []} even when mcast_frame events occur; the
    summary.totals.mcast_frame_events counter still increments."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [{"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
               "group": "239.1.1.1", "vlan": 10, "len": 64}]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": False, "ttl_sec": 300}
    out = _run_synthetic("track_off", ports, events, policy)
    assert out["forward_log"] == {"forwards": []}
    assert out["summary"]["totals"]["mcast_frame_events"] == 1


def test_ingress_vlan_mismatch_drops():
    """A mcast_frame whose vlan does not match the ingress port's
    configured vlan is dropped with reason='vlan_mismatch' and
    E_INGRESS_VLAN_MISMATCH is emitted."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [{"seq": 0, "op": "mcast_frame", "ingress_port": "Eth1",
               "group": "239.1.1.1", "vlan": 20, "len": 64}]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("ingress_vlan", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "dropped"
    assert fwd["reason"] == "vlan_mismatch"


def test_ingress_down_drops():
    """A mcast_frame arriving on a port whose link is currently down
    is dropped with reason='ingress_port_down' and E_INGRESS_PORT_DOWN
    is emitted."""
    ports = [_OK_PORT, _OK_PORT_R]
    events = [
        {"seq": 0, "op": "port_link_change", "port": "Eth1", "up": False},
        {"seq": 1, "op": "mcast_frame", "ingress_port": "Eth1",
         "group": "239.1.1.1", "vlan": 10, "len": 64},
    ]
    policy = {"drop_unknown_groups": False, "fast_leave": False,
              "track_forwarding": True, "ttl_sec": 300}
    out = _run_synthetic("ingress_down", ports, events, policy)
    fwd = out["forward_log"]["forwards"][0]
    assert fwd["decision"] == "dropped"
    assert fwd["reason"] == "ingress_port_down"
    assert any(d["code"] == "E_INGRESS_PORT_DOWN" for d in
               out["igmp_diagnostics"]["diagnostics"])


# ---------------------------------------------------------------------------
# Randomized property-based equivalence to RefSim
# ---------------------------------------------------------------------------


def _gen_random_inputs(rng):
    n_ports = rng.randint(4, 7)
    ports: list[dict[str, Any]] = []
    for i in range(1, n_ports + 1):
        role = "router" if rng.random() < 0.2 else "host"
        ports.append({"port_id": f"Eth{i}", "role": role,
                      "vlan": rng.choice([10, 20, 30])})
    port_ids = sorted([p["port_id"] for p in ports])
    host_ports_by_vlan = {}
    for p in ports:
        if p["role"] == "host":
            host_ports_by_vlan.setdefault(p["vlan"], []).append(p["port_id"])
    for v in host_ports_by_vlan:
        host_ports_by_vlan[v].sort()
    if not host_ports_by_vlan:
        host_ports_by_vlan = {10: [port_ids[0]]}
    groups = sorted({f"239.{rng.randint(1, 5)}.{rng.randint(1, 5)}.{rng.randint(1, 254)}"
                     for _ in range(5)})
    events: list[dict[str, Any]] = []
    seq = 0
    for _ in range(rng.randint(20, 40)):
        kind = rng.random()
        vlan = rng.choice(sorted(host_ports_by_vlan.keys()))
        if kind < 0.4:
            port = rng.choice(host_ports_by_vlan[vlan])
            events.append({"seq": seq, "op": "igmp_report", "port": port,
                           "group": rng.choice(groups), "vlan": vlan})
        elif kind < 0.55:
            port = rng.choice(host_ports_by_vlan[vlan])
            events.append({"seq": seq, "op": "igmp_leave", "port": port,
                           "group": rng.choice(groups), "vlan": vlan})
        elif kind < 0.85:
            ingress = rng.choice(port_ids)
            ip = next(pp for pp in ports if pp["port_id"] == ingress)
            events.append({"seq": seq, "op": "mcast_frame",
                           "ingress_port": ingress,
                           "group": rng.choice(groups + ["224.0.0.1", "224.0.0.5"]),
                           "vlan": ip["vlan"],
                           "len": rng.choice([64, 128, 256, 512])})
        elif kind < 0.95:
            events.append({"seq": seq, "op": "tick",
                           "delta_sec": rng.choice([1, 5, 50, 200, 400])})
        else:
            events.append({"seq": seq, "op": "port_link_change",
                           "port": rng.choice(port_ids),
                           "up": rng.choice([True, False])})
        seq += 1
    policy = {
        "drop_unknown_groups": rng.random() < 0.5,
        "fast_leave": rng.random() < 0.4,
        "track_forwarding": rng.random() < 0.7,
        "ttl_sec": rng.choice([100, 300, 600]),
    }
    return ports, events, policy


@pytest.mark.parametrize("trial", list(range(25)))
def test_property_random_scenarios_match_reference(trial):
    """Property-based: 25 seeded-random traces (mixing reports, leaves,
    multicast frames, ticks, and link changes across 4-7 ports and
    three VLANs, with randomly toggled policy flags) are run through
    both the agent's binary and RefSim, and every output must match
    byte-for-byte. Catches edge-case bugs not exercised by the
    bundled trace."""
    rng = random.Random(91111 + trial)
    ports, events, policy = _gen_random_inputs(rng)
    expected = run_simulation(ports, events, policy)
    work = Path(f"/tmp/igmp_property_{trial}")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    (in_dir / "ports.json").write_text(canonical({"ports": ports}))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"trial {trial} failed: {proc.stderr}"
    for key, fname in [
        ("mcast_table", "mcast_table.json"),
        ("forward_log", "forward_log.json"),
        ("igmp_diagnostics", "igmp_diagnostics.json"),
        ("summary", "summary.json"),
    ]:
        produced = (out_dir / fname).read_text(encoding="utf-8")
        ref_text = canonical(expected[key])
        assert produced == ref_text, f"trial {trial}: {fname} differs"
