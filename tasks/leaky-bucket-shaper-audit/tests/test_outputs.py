"""Verifier suite for Shaper (java)."""

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


def _java_class_ready() -> bool:
    """Return True when the compiled entry class exists."""
    return (BUILD_DIR / f"{JAVA_CLASS}.class").is_file()



DATA_DIR = Path("/app/data")
OUT_DIR = Path("/app/output")
JAVA_CLASS = "Shaper"
BUILD_DIR = Path("/app/build")
GSON_CP = "/opt/gson.jar"
SCHEMA_DIR = Path("/app/schemas")

BUCKETS_PATH = DATA_DIR / "buckets.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

STATE_PATH = OUT_DIR / "bucket_state.json"
ADMITS_PATH = OUT_DIR / "admits.json"
DIAG_PATH = OUT_DIR / "shaper_diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"
ALL_OUT_PATHS = (STATE_PATH, ADMITS_PATH, DIAG_PATH, SUMMARY_PATH)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    BUCKETS_PATH: "40bf4d14c828400a62031bfd4c061bb4e8a1e2ec60e002ffecc53cb9bff38464",
    EVENTS_PATH:  "f01ae43e5fd7b940b36f653dc6ff4ce660e46f71800dea2c22b8e7a754451c03",
    POLICY_PATH:  "c0189889789558f2bdb5bf7f7c8694f1d050425347c62342238184f2edb7087e",
}

SEV_RANK = {"error": 3, "warn": 2, "note": 1}


# ---------------------------------------------------------------------------
# Reference simulator
# ---------------------------------------------------------------------------


@dataclass
class RefSim:
    buckets: dict[str, dict[str, int]]
    policy: dict[str, Any]
    now_ticks: int = 0
    admits: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    dropped_bytes_total: int = 0
    overflow_drops_total: int = 0

    def _diag(self, seq, code, severity, bid="", detail=""):
        self.diagnostics.append({
            "seq": seq, "code": code, "severity": severity,
            "bucket_id": bid, "detail": detail,
        })

    def step(self, ev):
        seq = ev["seq"]
        t = ev["type"]
        if t == "submit":
            bid = ev["bucket_id"]
            sz = ev["size_bytes"]
            if bid not in self.buckets:
                self._diag(seq, "E_UNKNOWN_BUCKET", "error", bid, "")
                return
            b = self.buckets[bid]
            if b["current_bytes"] + sz <= b["capacity_bytes"]:
                b["current_bytes"] += sz
                self.admits.append({
                    "bucket_id": bid,
                    "level_after": b["current_bytes"],
                    "seq": seq,
                    "size_bytes": sz,
                })
                self._diag(seq, "N_ADMITTED", "note", bid, str(sz))
            else:
                self._diag(seq, "W_DROPPED_OVERFLOW", "warn", bid, str(sz))
                self.overflow_drops_total += 1
                if self.policy["count_dropped_bytes"]:
                    self.dropped_bytes_total += sz
            return
        if t == "tick":
            self.now_ticks += 1
            for bid in sorted(self.buckets):
                b = self.buckets[bid]
                b["current_bytes"] = max(0, b["current_bytes"] - b["leak_bytes_per_tick"])
            return
        if t == "reconfigure":
            bid = ev["bucket_id"]
            if bid not in self.buckets:
                raise ValueError(f"unknown bucket in reconfigure: {bid}")
            nc = ev["new_capacity_bytes"]
            nl = ev["new_leak_bytes_per_tick"]
            b = self.buckets[bid]
            old_cap = b["capacity_bytes"]
            old_leak = b["leak_bytes_per_tick"]
            if nc == old_cap and nl == old_leak:
                self._diag(seq, "W_RECONFIG_NOOP", "warn", bid, bid)
                return
            old_level = b["current_bytes"]
            b["capacity_bytes"] = nc
            b["leak_bytes_per_tick"] = nl
            if nc < old_level:
                b["current_bytes"] = nc
                self._diag(seq, "W_CAPACITY_REDUCED", "warn", bid,
                           f"{old_level}->{nc}")
            return
        raise ValueError(f"unknown event: {t}")

    def finalize(self, n_events: int):
        bs = sorted(
            (
                {"bucket_id": bid,
                 "capacity_bytes": b["capacity_bytes"],
                 "current_bytes": b["current_bytes"],
                 "leak_bytes_per_tick": b["leak_bytes_per_tick"]}
                for bid, b in self.buckets.items()
            ),
            key=lambda r: r["bucket_id"],
        )
        if self.policy["track_admits"]:
            ad = sorted(self.admits, key=lambda r: (r["seq"], r["bucket_id"]))
        else:
            ad = []
        diags = sorted(
            self.diagnostics,
            key=lambda d: (
                d["seq"], -SEV_RANK[d["severity"]],
                d["code"], d["bucket_id"], d["detail"],
            ),
        )
        cur_total = sum(b["current_bytes"] for b in self.buckets.values())
        max_seq = (n_events - 1 if n_events > 0 else None)
        return {
            "bucket_state": {"buckets": bs},
            "admits": {"admits": ad},
            "shaper_diagnostics": {"diagnostics": diags},
            "summary": {
                "admits_total": len(self.admits),
                "buckets_total": len(self.buckets),
                "current_bytes_total": cur_total,
                "dropped_bytes_total": self.dropped_bytes_total,
                "events_total": n_events,
                "max_seq": max_seq,
                "now_ticks_final": self.now_ticks,
                "overflow_drops_total": self.overflow_drops_total,
            },
        }


def run_simulation(buckets_in, events, policy):
    state = {}
    for b in buckets_in["buckets"]:
        state[b["bucket_id"]] = {
            "capacity_bytes": b["capacity_bytes"],
            "leak_bytes_per_tick": b["leak_bytes_per_tick"],
            "current_bytes": 0,
        }
    sim = RefSim(buckets=state, policy=dict(policy))
    for ev in events:
        sim.step(ev)
    return sim.finalize(len(events))


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
        "buckets": load_json(BUCKETS_PATH),
        "events": load_json(EVENTS_PATH)["events"],
        "policy": load_json(POLICY_PATH),
    }


@pytest.fixture(scope="module")
def expected(inputs: dict[str, Any]) -> dict[str, Any]:
    return run_simulation(inputs["buckets"], inputs["events"], inputs["policy"])


@pytest.fixture(scope="module")
def binary_run_outputs() -> dict[str, Any]:
    if not _java_class_ready():
        pytest.skip('Java entry class not built')
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"binary exit {proc.returncode}; stdout={proc.stdout!r}; stderr={proc.stderr!r}"
        )
    out: dict[str, Any] = {}
    for path, key in [
        (STATE_PATH, "bucket_state"),
        (ADMITS_PATH, "admits"),
        (DIAG_PATH, "shaper_diagnostics"),
        (SUMMARY_PATH, "summary"),
    ]:
        if not path.exists():
            raise RuntimeError(f"binary did not produce {path}")
        out[key] = load_json(path)
    return out


# ---------------------------------------------------------------------------
# Filesystem & build hygiene
# ---------------------------------------------------------------------------


def test_data_unchanged():
    """Pinned SHA-256 of every /app/data file matches the manifest baked at task-build time."""
    for path, expected_hash in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input {path} missing"
        actual = sha256_of(path)
        assert actual == expected_hash, (
            f"{path} sha256 mismatch (expected {expected_hash}, got {actual})"
        )


def test_data_dir_only_known_files():
    """/app/data contains exactly the three known input files, no extras or symlinks."""
    expected_names = {"buckets.json", "events.json", "policy.json"}
    entries = list(DATA_DIR.iterdir())
    assert {e.name for e in entries} == expected_names
    for e in entries:
        assert e.is_file() and not e.is_symlink()


def test_java_entry_class_exists():
    """Compiled Java entry class exists under /app/build after the agent build."""
    assert _java_class_ready()






def test_sources_present_and_class_newer():
    """Java sources exist under /app/src and the class mtime is no older than any build input."""
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


def test_no_stray_sources_outside_required_dirs():
    """No C/C++ sources live outside /app/src + /app/include, and src/include hold only .cpp/.hpp."""
    required_roots = (Path("/app/src"), Path("/app/include"))
    stray_outside: list[str] = []
    for s in _all_app_source_files():
        if not any(str(s).startswith(str(r) + os.sep) for r in required_roots):
            stray_outside.append(str(s))
    assert not stray_outside, f"C/C++ sources outside src/include: {stray_outside}"
    forbidden_suffixes = (".cc", ".cxx", ".c", ".h", ".hh")
    forbidden_under_required: list[str] = []
    for r in required_roots:
        if not r.exists():
            continue
        for p in r.rglob("*"):
            if p.is_file() and p.suffix in forbidden_suffixes:
                forbidden_under_required.append(str(p))
    assert not forbidden_under_required, (
        f"non-.cpp/.hpp under src/include: {forbidden_under_required}"
    )


def test_app_layout_no_unexpected_files():
    """/app contains only the allow-listed subdirectories with no stray top-level files."""
    allowed_dirs = {"build", "data", "docs", "examples",
                    "include", "output", "schemas", "src"}
    app = Path("/app")
    assert app.is_dir()
    for entry in app.iterdir():
        if entry.is_dir():
            assert entry.name in allowed_dirs, (
                f"unexpected dir at /app/{entry.name}; allowed: {sorted(allowed_dirs)}"
            )
        else:
            raise AssertionError(f"unexpected file at /app/{entry.name}")


def test_layout_dirs_have_correct_content():
    """include/ holds header files and src/ holds implementation files."""
    inc = Path("/app/include")
    src = Path("/app/src")
    assert inc.is_dir() and src.is_dir()
    headers = [p for p in inc.rglob("*")
               if p.is_file() and p.suffix in (".hpp", ".h", ".hh")]
    cpps = [p for p in src.rglob("*")
            if p.is_file() and p.suffix in (".cpp", ".cc", ".cxx")]
    assert headers and cpps


def test_sources_substantive():
    """Combined source line count clears the stub threshold (>= 200 lines)."""
    sources = _src_files()
    total_lines = sum(s.read_text(errors="ignore").count("\n") for s in sources)
    assert total_lines >= 200, f"only {total_lines} total lines; looks like a stub"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


def test_schemas_dir_present_and_parsable():
    """All seven JSON Schema files exist under /app/schemas and each parses as valid JSON."""
    expected = {
        "buckets_input.schema.json",
        "events_input.schema.json",
        "policy_input.schema.json",
        "bucket_state.schema.json",
        "admits.schema.json",
        "shaper_diagnostics.schema.json",
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
    """Each /app/data file validates against its corresponding input JSON Schema."""
    _validate(BUCKETS_PATH, SCHEMA_DIR / "buckets_input.schema.json")
    _validate(EVENTS_PATH, SCHEMA_DIR / "events_input.schema.json")
    _validate(POLICY_PATH, SCHEMA_DIR / "policy_input.schema.json")


def test_outputs_conform_to_schemas(binary_run_outputs):
    """Binary's four /app/output files each validate against their output JSON Schema."""
    _validate(STATE_PATH, SCHEMA_DIR / "bucket_state.schema.json")
    _validate(ADMITS_PATH, SCHEMA_DIR / "admits.schema.json")
    _validate(DIAG_PATH, SCHEMA_DIR / "shaper_diagnostics.schema.json")
    _validate(SUMMARY_PATH, SCHEMA_DIR / "summary.schema.json")


def test_diagnostics_codes_are_in_docs_closed_set(binary_run_outputs):
    """Every diagnostic code the binary emits appears in the closed set documented in diagnostics.md."""
    docs_path = Path("/app/docs/diagnostics.md")
    assert docs_path.exists()
    docs_text = docs_path.read_text(encoding="utf-8")
    docs_codes = set(re.findall(r"\b[EWN]_[A-Z_]+\b", docs_text))
    diag = binary_run_outputs["shaper_diagnostics"]["diagnostics"]
    produced_codes = {d["code"] for d in diag}
    leaked = produced_codes - docs_codes
    assert not leaked, f"binary emitted codes not in docs: {leaked}"


def test_outputs_have_no_extra_keys(binary_run_outputs):
    """Each output JSON has exactly the documented top-level and record-level keys, no extras."""
    bs = binary_run_outputs["bucket_state"]
    assert set(bs) == {"buckets"}
    for b in bs["buckets"]:
        assert set(b) == {"bucket_id", "capacity_bytes",
                          "current_bytes", "leak_bytes_per_tick"}, b
    ad = binary_run_outputs["admits"]
    assert set(ad) == {"admits"}
    for a in ad["admits"]:
        assert set(a) == {"bucket_id", "level_after", "seq", "size_bytes"}, a
    diag = binary_run_outputs["shaper_diagnostics"]
    assert set(diag) == {"diagnostics"}
    for d in diag["diagnostics"]:
        assert set(d) == {"bucket_id", "code", "detail", "seq", "severity"}, d
    summary = binary_run_outputs["summary"]
    assert set(summary) == {
        "admits_total", "buckets_total", "current_bytes_total",
        "dropped_bytes_total", "events_total", "max_seq",
        "now_ticks_final", "overflow_drops_total",
    }


def test_summary_counter_invariants(binary_run_outputs):
    """summary.json's bucket and current-bytes totals agree with the bucket_state.json aggregates."""
    s = binary_run_outputs["summary"]
    state = binary_run_outputs["bucket_state"]
    assert s["buckets_total"] == len(state["buckets"])
    cur_total = sum(b["current_bytes"] for b in state["buckets"])
    assert s["current_bytes_total"] == cur_total


def test_outputs_strictly_ascii_canonical(binary_run_outputs):
    """All four outputs are pure-ASCII canonical JSON (sorted keys, 2-space indent, trailing newline)."""
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
    """Binary writes only inside /app/output; immutable roots and /tmp stay untouched."""
    immutable_roots = (
        Path("/app/build"),
        Path("/app/src"),
        Path("/app/include"),
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
    foreign_before: dict[Path, set[str]] = {r: _snapshot_paths(r)
                                            for r in foreign_roots}

    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
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
            assert after_m == before_m, f"binary changed metadata of {path_str}"
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
                "/tmp/bucket_", "/tmp/_bucket", "/tmp/leaky_",
            ))
        ]
        assert not new_foreign, f"binary wrote outside /app: {new_foreign[:10]}"


def test_outputs_dir_only_known_files(binary_run_outputs):
    """/app/output contains exactly the four documented files after a run."""
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual = {p.name for p in OUT_DIR.iterdir()}
    assert actual == expected_names


def test_outputs_match_reference_byte_for_byte(binary_run_outputs, expected):
    """Each output is byte-equal to the in-process RefSim's canonical JSON."""
    for key, path in [
        ("bucket_state", STATE_PATH),
        ("admits", ADMITS_PATH),
        ("shaper_diagnostics", DIAG_PATH),
        ("summary", SUMMARY_PATH),
    ]:
        produced = path.read_text(encoding="utf-8")
        ref_text = canonical(expected[key])
        assert produced == ref_text, f"{path.name} differs from reference"


def test_idempotent_on_rerun(binary_run_outputs):
    """Re-running the binary against the same inputs produces byte-identical outputs."""
    snapshots = {p: p.read_text(encoding="utf-8") for p in ALL_OUT_PATHS}
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0
    for p, prior in snapshots.items():
        assert p.read_text(encoding="utf-8") == prior


def test_binary_rejects_wrong_arg_counts():
    """Binary exits non-zero when invoked with 0, 1, or 3 positional arguments."""
    for argv in ([], [str(DATA_DIR)], [str(DATA_DIR), str(OUT_DIR), "extra"]):
        proc = subprocess.run(
            [*_java_cmd(DATA_DIR, OUT_DIR)] + argv, capture_output=True, text=True, timeout=10,
        )
        assert proc.returncode != 0


def test_binary_honors_argv_paths():
    """Binary reads inputs from argv[1] and writes outputs to argv[2], not hardcoded paths."""
    work = Path("/tmp/leaky_argv_test")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    buckets_in = {"buckets": [
        {"bucket_id": "edge", "capacity_bytes": 1000,
         "leak_bytes_per_tick": 200},
    ]}
    events_in = {"events": [
        {"seq": 0, "type": "submit",
         "bucket_id": "edge", "size_bytes": 600},
        {"seq": 1, "type": "submit",
         "bucket_id": "edge", "size_bytes": 500},
    ]}
    policy_in = {"count_dropped_bytes": True, "track_admits": True}
    (in_dir / "buckets.json").write_text(canonical(buckets_in))
    (in_dir / "events.json").write_text(canonical(events_in))
    (in_dir / "policy.json").write_text(canonical(policy_in))
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    expected_names = {"bucket_state.json", "admits.json",
                      "shaper_diagnostics.json", "summary.json"}
    actual = {p.name for p in out_dir.iterdir()}
    assert actual == expected_names
    bs = json.loads((out_dir / "bucket_state.json").read_text())
    assert bs["buckets"][0]["current_bytes"] == 600
    summ = json.loads((out_dir / "summary.json").read_text())
    assert summ["overflow_drops_total"] == 1
    assert summ["dropped_bytes_total"] == 500
    _validate(out_dir / "bucket_state.json", SCHEMA_DIR / "bucket_state.schema.json")
    _validate(out_dir / "admits.json", SCHEMA_DIR / "admits.schema.json")
    _validate(out_dir / "shaper_diagnostics.json", SCHEMA_DIR / "shaper_diagnostics.schema.json")
    _validate(out_dir / "summary.json", SCHEMA_DIR / "summary.schema.json")


# ---------------------------------------------------------------------------
# Malformed input rejection
# ---------------------------------------------------------------------------


def _make_inputs(buckets, events, policy=None):
    work = Path("/tmp/leaky_malformed")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    if policy is None:
        policy = {"count_dropped_bytes": True, "track_admits": True}
    (in_dir / "buckets.json").write_text(canonical(buckets))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    return in_dir, out_dir


_OK_BUCKETS = {"buckets": [
    {"bucket_id": "a", "capacity_bytes": 1000, "leak_bytes_per_tick": 100},
]}
_OK_SUB = {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 100}


_MALFORMED_CASES = [
    ("bucket_invalid_id",
     {"buckets": [
         {"bucket_id": "bad id!", "capacity_bytes": 1000,
          "leak_bytes_per_tick": 100}]},
     [_OK_SUB], None),
    ("bucket_capacity_zero",
     {"buckets": [
         {"bucket_id": "a", "capacity_bytes": 0,
          "leak_bytes_per_tick": 100}]},
     [_OK_SUB], None),
    ("bucket_extra_field",
     {"buckets": [
         {"bucket_id": "a", "capacity_bytes": 1000,
          "leak_bytes_per_tick": 100, "x": 1}]},
     [_OK_SUB], None),
    ("bucket_dup_id",
     {"buckets": [
         {"bucket_id": "a", "capacity_bytes": 1000, "leak_bytes_per_tick": 100},
         {"bucket_id": "a", "capacity_bytes": 2000, "leak_bytes_per_tick": 200},
     ]}, [_OK_SUB], None),
    ("buckets_empty",
     {"buckets": []}, [], None),
    ("events_non_dense_seq",
     _OK_BUCKETS, [{"seq": 1, "type": "tick"}], None),
    ("events_unknown_type",
     _OK_BUCKETS, [{"seq": 0, "type": "foo"}], None),
    ("submit_extra_field",
     _OK_BUCKETS, [dict(_OK_SUB, x=1)], None),
    ("submit_missing_size",
     _OK_BUCKETS,
     [{"seq": 0, "type": "submit", "bucket_id": "a"}], None),
    ("submit_size_zero",
     _OK_BUCKETS,
     [{"seq": 0, "type": "submit", "bucket_id": "a",
       "size_bytes": 0}], None),
    ("submit_invalid_bucket_id",
     _OK_BUCKETS,
     [{"seq": 0, "type": "submit", "bucket_id": "bad id!",
       "size_bytes": 100}], None),
    ("tick_extra_field",
     _OK_BUCKETS, [{"seq": 0, "type": "tick", "x": 1}], None),
    ("reconfigure_extra_field",
     _OK_BUCKETS,
     [{"seq": 0, "type": "reconfigure", "bucket_id": "a",
       "new_capacity_bytes": 500, "new_leak_bytes_per_tick": 50,
       "x": 1}], None),
    ("reconfigure_unknown_bucket",
     _OK_BUCKETS,
     [{"seq": 0, "type": "reconfigure", "bucket_id": "ghost",
       "new_capacity_bytes": 500, "new_leak_bytes_per_tick": 50}], None),
    ("reconfigure_capacity_zero",
     _OK_BUCKETS,
     [{"seq": 0, "type": "reconfigure", "bucket_id": "a",
       "new_capacity_bytes": 0, "new_leak_bytes_per_tick": 50}], None),
    ("policy_missing_field",
     _OK_BUCKETS, [_OK_SUB],
     {"count_dropped_bytes": True}),
    ("policy_extra_field",
     _OK_BUCKETS, [_OK_SUB],
     {"count_dropped_bytes": True, "track_admits": True, "extra": 1}),
    ("policy_wrong_type",
     _OK_BUCKETS, [_OK_SUB],
     {"count_dropped_bytes": "yes", "track_admits": True}),
]


@pytest.mark.parametrize("name,buckets,events,policy", _MALFORMED_CASES,
                         ids=[c[0] for c in _MALFORMED_CASES])
def test_malformed_input_exits_nonzero(name, buckets, events, policy):
    """Every malformed input scenario causes the binary to exit non-zero (no silent acceptance)."""
    in_dir, out_dir = _make_inputs(buckets, events, policy)
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        f"malformed scenario {name!r} did not cause exit-non-zero; "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


# ---------------------------------------------------------------------------
# Targeted scenarios
# ---------------------------------------------------------------------------


def _run_synthetic(name, buckets, events, policy):
    work = Path(f"/tmp/leaky_synth_{name}")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    (in_dir / "buckets.json").write_text(canonical(buckets))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return {
        "bucket_state": json.loads((out_dir / "bucket_state.json").read_text()),
        "admits": json.loads((out_dir / "admits.json").read_text()),
        "shaper_diagnostics": json.loads(
            (out_dir / "shaper_diagnostics.json").read_text()),
        "summary": json.loads((out_dir / "summary.json").read_text()),
    }


_DEFAULT_POLICY = {"count_dropped_bytes": True, "track_admits": True}


def test_simple_admit_then_overflow():
    """First submit admits within capacity; the next one exceeds capacity and is dropped."""
    out = _run_synthetic(
        "simple", _OK_BUCKETS,
        [
            {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 600},
            {"seq": 1, "type": "submit", "bucket_id": "a", "size_bytes": 500},
        ],
        _DEFAULT_POLICY,
    )
    codes = [d["code"] for d in out["shaper_diagnostics"]["diagnostics"]]
    assert "N_ADMITTED" in codes
    assert "W_DROPPED_OVERFLOW" in codes
    assert out["bucket_state"]["buckets"][0]["current_bytes"] == 600
    assert out["summary"]["dropped_bytes_total"] == 500
    assert out["summary"]["overflow_drops_total"] == 1


def test_unknown_bucket_submit_emits_error_and_continues():
    """A submit to a non-existent bucket emits E_UNKNOWN_BUCKET; later events still process normally."""
    out = _run_synthetic(
        "unknown", _OK_BUCKETS,
        [
            {"seq": 0, "type": "submit", "bucket_id": "ghost",
             "size_bytes": 500},
            {"seq": 1, "type": "submit", "bucket_id": "a",
             "size_bytes": 100},
        ],
        _DEFAULT_POLICY,
    )
    codes = [d["code"] for d in out["shaper_diagnostics"]["diagnostics"]]
    assert "E_UNKNOWN_BUCKET" in codes
    assert "N_ADMITTED" in codes
    assert out["bucket_state"]["buckets"][0]["current_bytes"] == 100


def test_tick_drains_bucket():
    """Each tick drains exactly leak_bytes_per_tick from the bucket's current level."""
    buckets = {"buckets": [
        {"bucket_id": "a", "capacity_bytes": 1000, "leak_bytes_per_tick": 200},
    ]}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 800},
        {"seq": 1, "type": "tick"},
        {"seq": 2, "type": "tick"},
    ]
    out = _run_synthetic("drain", buckets, events, _DEFAULT_POLICY)
    assert out["bucket_state"]["buckets"][0]["current_bytes"] == 400
    assert out["summary"]["now_ticks_final"] == 2


def test_tick_floors_at_zero():
    """A leak rate larger than the current level floors the bucket at zero, never negative."""
    buckets = {"buckets": [
        {"bucket_id": "a", "capacity_bytes": 1000,
         "leak_bytes_per_tick": 1000},
    ]}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 100},
        {"seq": 1, "type": "tick"},
    ]
    out = _run_synthetic("floor", buckets, events, _DEFAULT_POLICY)
    assert out["bucket_state"]["buckets"][0]["current_bytes"] == 0


def test_reconfigure_noop_emits_warning():
    """A reconfigure with identical capacity and leak rate emits W_RECONFIG_NOOP."""
    events = [
        {"seq": 0, "type": "reconfigure", "bucket_id": "a",
         "new_capacity_bytes": 1000, "new_leak_bytes_per_tick": 100},
    ]
    out = _run_synthetic("noop", _OK_BUCKETS, events, _DEFAULT_POLICY)
    codes = [d["code"] for d in out["shaper_diagnostics"]["diagnostics"]]
    assert "W_RECONFIG_NOOP" in codes


def test_reconfigure_capacity_reduced_clips_level():
    """Shrinking capacity below the current level clips current_bytes and emits W_CAPACITY_REDUCED."""
    buckets = {"buckets": [
        {"bucket_id": "a", "capacity_bytes": 1000, "leak_bytes_per_tick": 0},
    ]}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 800},
        {"seq": 1, "type": "reconfigure", "bucket_id": "a",
         "new_capacity_bytes": 500, "new_leak_bytes_per_tick": 0},
    ]
    out = _run_synthetic("clip", buckets, events, _DEFAULT_POLICY)
    bs = out["bucket_state"]["buckets"][0]
    assert bs["capacity_bytes"] == 500
    assert bs["current_bytes"] == 500
    diags = out["shaper_diagnostics"]["diagnostics"]
    cap_red = [d for d in diags if d["code"] == "W_CAPACITY_REDUCED"]
    assert cap_red and cap_red[0]["detail"] == "800->500"


def test_reconfigure_grow_does_not_emit_w_capacity_reduced():
    """Growing capacity preserves the current level and never emits W_CAPACITY_REDUCED."""
    buckets = {"buckets": [
        {"bucket_id": "a", "capacity_bytes": 1000, "leak_bytes_per_tick": 0},
    ]}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 800},
        {"seq": 1, "type": "reconfigure", "bucket_id": "a",
         "new_capacity_bytes": 2000, "new_leak_bytes_per_tick": 50},
    ]
    out = _run_synthetic("grow", buckets, events, _DEFAULT_POLICY)
    codes = [d["code"] for d in out["shaper_diagnostics"]["diagnostics"]]
    assert "W_CAPACITY_REDUCED" not in codes
    bs = out["bucket_state"]["buckets"][0]
    assert bs["capacity_bytes"] == 2000
    assert bs["leak_bytes_per_tick"] == 50
    assert bs["current_bytes"] == 800


def test_track_admits_off_yields_empty_log():
    """policy.track_admits=false leaves admits.json empty but admits_total still increments."""
    pol = {"count_dropped_bytes": True, "track_admits": False}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 100},
    ]
    out = _run_synthetic("trackoff", _OK_BUCKETS, events, pol)
    assert out["admits"] == {"admits": []}
    assert out["summary"]["admits_total"] == 1


def test_count_dropped_bytes_off_keeps_total_zero():
    """policy.count_dropped_bytes=false holds dropped_bytes_total at zero even on overflow drops."""
    pol = {"count_dropped_bytes": False, "track_admits": True}
    events = [
        {"seq": 0, "type": "submit", "bucket_id": "a", "size_bytes": 1500},
    ]
    out = _run_synthetic("nocount", _OK_BUCKETS, events, pol)
    assert out["summary"]["dropped_bytes_total"] == 0
    assert out["summary"]["overflow_drops_total"] == 1


def test_empty_events_yields_null_max_seq():
    """An empty event stream yields max_seq=null with zero events_total and now_ticks_final."""
    out = _run_synthetic("empty", _OK_BUCKETS, [], _DEFAULT_POLICY)
    assert out["summary"]["max_seq"] is None
    assert out["summary"]["events_total"] == 0
    assert out["summary"]["now_ticks_final"] == 0


# ---------------------------------------------------------------------------
# Randomized property-based equivalence to RefSim
# ---------------------------------------------------------------------------


def _gen_random_inputs(rng):
    n_buckets = rng.randint(1, 4)
    bucket_ids = [f"b{i}" for i in range(n_buckets)]
    buckets = {"buckets": [
        {"bucket_id": bid,
         "capacity_bytes": rng.choice([500, 1000, 2000, 5000]),
         "leak_bytes_per_tick": rng.choice([0, 50, 100, 250, 500])}
        for bid in bucket_ids
    ]}
    n = rng.randint(20, 60)
    events = []
    seq = 0
    for _ in range(n):
        roll = rng.random()
        if roll < 0.6:
            events.append({"seq": seq, "type": "submit",
                           "bucket_id": rng.choice(bucket_ids),
                           "size_bytes": rng.choice(
                               [50, 100, 250, 500, 1000, 1500])})
        elif roll < 0.9:
            events.append({"seq": seq, "type": "tick"})
        else:
            events.append({"seq": seq, "type": "reconfigure",
                           "bucket_id": rng.choice(bucket_ids),
                           "new_capacity_bytes": rng.choice(
                               [300, 800, 1500, 3000]),
                           "new_leak_bytes_per_tick": rng.choice(
                               [0, 50, 200, 500])})
        seq += 1
    policy = {
        "count_dropped_bytes": rng.random() < 0.5,
        "track_admits": rng.random() < 0.7,
    }
    return buckets, events, policy


@pytest.mark.parametrize("trial", list(range(25)))
def test_property_random_scenarios_match_reference(trial):
    """Randomized buckets/events/policy: binary output is byte-equal to RefSim (25 trials)."""
    rng = random.Random(831_000 + trial)
    buckets_in, events, policy = _gen_random_inputs(rng)
    expected = run_simulation(buckets_in, events, policy)
    work = Path(f"/tmp/leaky_property_{trial}")
    if work.exists():
        shutil.rmtree(work)
    in_dir = work / "in"
    out_dir = work / "out"
    in_dir.mkdir(parents=True)
    out_dir.mkdir(parents=True)
    (in_dir / "buckets.json").write_text(canonical(buckets_in))
    (in_dir / "events.json").write_text(canonical({"events": events}))
    (in_dir / "policy.json").write_text(canonical(policy))
    proc = subprocess.run(
        [*_java_cmd(in_dir, out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"trial {trial} failed: {proc.stderr}"
    for key, fname in [
        ("bucket_state", "bucket_state.json"),
        ("admits", "admits.json"),
        ("shaper_diagnostics", "shaper_diagnostics.json"),
        ("summary", "summary.json"),
    ]:
        produced = (out_dir / fname).read_text(encoding="utf-8")
        ref_text = canonical(expected[key])
        assert produced == ref_text, (
            f"trial {trial}: {fname} differs\n--- produced ---\n{produced}\n"
            f"--- expected ---\n{ref_text}"
        )
