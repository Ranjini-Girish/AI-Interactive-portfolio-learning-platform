"""Verifier suite for Replay (java)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import os
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

KEYS_PATH = DATA_DIR / "keys.json"
EVENTS_PATH = DATA_DIR / "events.json"
POLICY_PATH = DATA_DIR / "policy.json"

KEY_STATES_PATH = OUT_DIR / "key_states.json"
ENC_LOG_PATH = OUT_DIR / "encryption_log.json"
AUDIT_LOG_PATH = OUT_DIR / "audit_log.json"
DIAG_PATH = OUT_DIR / "diagnostics.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (
    KEY_STATES_PATH, ENC_LOG_PATH, AUDIT_LOG_PATH,
    DIAG_PATH, SUMMARY_PATH,
)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def is_strictly_formatted(path: Path) -> tuple[bool, str]:
    raw = path.read_bytes()
    if not raw.endswith(b"\n"):
        return False, f"{path} missing trailing newline"
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return False, f"{path} not utf-8: {exc}"
    payload = json.loads(decoded)
    canonical = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    if decoded != canonical:
        return False, f"{path} not in canonical 2-space sorted-keys form"
    return True, ""


# ---------------------------------------------------------------------------
# Reference simulator
# ---------------------------------------------------------------------------

KIND_REQUIRED_FIELDS = {
    "key_install":    ("key_id", "algorithm", "max_uses"),
    "encrypt":        ("key_id", "nonce"),
    "key_retire":     ("key_id",),
    "key_compromise": ("key_id", "reason"),
    "tick":           (),
}


def _emit(diags: list, *, seq: int, code: str, severity: str,
          severity_rank: int, key_id: str | None,
          evidence: dict) -> None:
    rec = {
        "seq": seq, "code": code, "severity": severity,
        "severity_rank": severity_rank,
        "key_id": key_id, "evidence": evidence,
    }
    diags.append(rec)


def _severity_rank(policy: dict, severity: str) -> int:
    return policy["severity_ranks"][severity]


def _push_audit(audit: list, *, seq: int, tick: int, key_id: str,
                kind: str, evidence: dict) -> None:
    audit.append({
        "seq": seq, "tick": tick, "key_id": key_id,
        "kind": kind, "evidence": evidence,
    })


def _idle_retire_sweep(now: int, seq: int, keys: dict, policy: dict,
                       diags: list, audit: list) -> None:
    threshold = policy["idle_retire_ticks"]
    for key_id in sorted(keys.keys()):
        k = keys[key_id]
        if k["state"] != "ACTIVE":
            continue
        if now - k["last_use_tick"] >= threshold:
            k["state"] = "RETIRED"
            k["retired_seq"] = seq
            evidence = {
                "last_use_tick": k["last_use_tick"],
                "now": now,
            }
            _emit(diags, seq=seq, code="N_KEY_IDLE_RETIRED",
                  severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=evidence)
            _push_audit(audit, seq=seq, tick=now, key_id=key_id,
                        kind="idle_retired", evidence=evidence)


def simulate(keys_in: dict, events_in: dict, policy: dict) -> dict[str, Any]:
    keys: dict[str, dict] = {}
    audit: list[dict] = []
    diags: list[dict] = []
    encryptions: list[dict] = []

    allowed_algorithms = set(policy["allowed_algorithms"])
    near_num, near_den = policy["near_exhaustion_ratio"]

    for k in keys_in.get("keys", []):
        key_id = k["key_id"]
        algorithm = k["algorithm"]
        max_uses = k["max_uses"]
        keys[key_id] = {
            "key_id": key_id,
            "algorithm": algorithm,
            "state": "ACTIVE",
            "max_uses": max_uses,
            "uses_count": 0,
            "installed_seq": 0,
            "retired_seq": None,
            "exhausted_seq": None,
            "compromised_seq": None,
            "last_use_tick": 0,
            "near_warned": False,
            "nonces": {},
        }
        _push_audit(audit, seq=0, tick=0, key_id=key_id, kind="installed",
                    evidence={"algorithm": algorithm, "max_uses": max_uses})

    events = sorted(events_in.get("events", []), key=lambda e: e["seq"])

    for ev in events:
        seq = ev["seq"]
        tick = ev["tick"]
        kind = ev.get("kind", "")

        _idle_retire_sweep(tick, seq, keys, policy, diags, audit)

        if kind not in KIND_REQUIRED_FIELDS:
            _emit(diags, seq=seq, code="E_INVALID_EVENT", severity="error",
                  severity_rank=_severity_rank(policy, "error"),
                  key_id=None, evidence={"reason": "unknown_kind"})
            continue
        if any(f not in ev for f in KIND_REQUIRED_FIELDS[kind]):
            _emit(diags, seq=seq, code="E_INVALID_EVENT", severity="error",
                  severity_rank=_severity_rank(policy, "error"),
                  key_id=None, evidence={"reason": "missing_field"})
            continue

        if kind == "key_install":
            key_id = ev["key_id"]
            algorithm = ev["algorithm"]
            max_uses = ev["max_uses"]
            if key_id in keys:
                _emit(diags, seq=seq, code="E_DUPLICATE_KEY",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"prior_state": keys[key_id]["state"]})
                continue
            if algorithm not in allowed_algorithms:
                _emit(diags, seq=seq, code="E_ALGORITHM_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"algorithm": algorithm})
                continue
            if not isinstance(max_uses, int) or max_uses <= 0:
                _emit(diags, seq=seq, code="E_INVALID_EVENT",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=None,
                      evidence={"reason": "non_positive_max_uses"})
                continue
            keys[key_id] = {
                "key_id": key_id,
                "algorithm": algorithm,
                "state": "ACTIVE",
                "max_uses": max_uses,
                "uses_count": 0,
                "installed_seq": seq,
                "retired_seq": None,
                "exhausted_seq": None,
                "compromised_seq": None,
                "last_use_tick": tick,
                "near_warned": False,
                "nonces": {},
            }
            _emit(diags, seq=seq, code="N_KEY_INSTALLED", severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id,
                  evidence={"algorithm": algorithm, "max_uses": max_uses})
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="installed",
                        evidence={"algorithm": algorithm,
                                  "max_uses": max_uses})

        elif kind == "encrypt":
            key_id = ev["key_id"]
            nonce = ev["nonce"]
            if key_id not in keys:
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "UNKNOWN_KEY",
                })
                _emit(diags, seq=seq, code="E_KEY_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "RETIRED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "RETIRED",
                })
                _emit(diags, seq=seq, code="E_KEY_NOT_ACTIVE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"key_state": "RETIRED"})
                continue
            if k["state"] == "EXHAUSTED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "EXHAUSTED",
                })
                _emit(diags, seq=seq, code="E_KEY_EXHAUSTED",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            if k["state"] == "COMPROMISED":
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "COMPROMISED",
                })
                _emit(diags, seq=seq, code="E_KEY_COMPROMISED",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            if nonce in k["nonces"]:
                first_seq, first_tick = k["nonces"][nonce]
                encryptions.append({
                    "seq": seq, "tick": tick, "key_id": key_id,
                    "nonce": nonce, "outcome": "rejected",
                    "reason": "NONCE_REUSE",
                })
                _emit(diags, seq=seq, code="E_NONCE_REUSE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"first_seq": first_seq,
                                "first_tick": first_tick})
                k["state"] = "COMPROMISED"
                k["compromised_seq"] = seq
                comp_ev = {"trigger": "nonce_reuse", "nonce": nonce}
                _emit(diags, seq=seq, code="N_KEY_COMPROMISED",
                      severity="notice",
                      severity_rank=_severity_rank(policy, "notice"),
                      key_id=key_id, evidence=comp_ev)
                _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                            kind="compromised", evidence=comp_ev)
                continue
            k["nonces"][nonce] = (seq, tick)
            k["uses_count"] += 1
            k["last_use_tick"] = tick
            encryptions.append({
                "seq": seq, "tick": tick, "key_id": key_id,
                "nonce": nonce, "outcome": "accepted", "reason": None,
            })
            if k["uses_count"] == k["max_uses"]:
                k["state"] = "EXHAUSTED"
                k["exhausted_seq"] = seq
                ex_ev = {"uses_count": k["uses_count"],
                         "max_uses": k["max_uses"]}
                _emit(diags, seq=seq, code="N_KEY_EXHAUSTED",
                      severity="notice",
                      severity_rank=_severity_rank(policy, "notice"),
                      key_id=key_id, evidence=ex_ev)
                _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                            kind="exhausted", evidence=ex_ev)
            elif (k["uses_count"] * near_den >= k["max_uses"] * near_num
                  and not k["near_warned"]):
                k["near_warned"] = True
                _emit(diags, seq=seq, code="W_KEY_NEAR_EXHAUSTION",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id,
                      evidence={"uses_count": k["uses_count"],
                                "max_uses": k["max_uses"]})

        elif kind == "key_retire":
            key_id = ev["key_id"]
            if key_id not in keys:
                _emit(diags, seq=seq, code="E_RETIRE_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "RETIRED":
                _emit(diags, seq=seq, code="W_RETIRE_ALREADY_RETIRED",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id, evidence={})
                continue
            if k["state"] in ("EXHAUSTED", "COMPROMISED"):
                _emit(diags, seq=seq, code="E_RETIRE_NOT_ACTIVE",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id,
                      evidence={"key_state": k["state"]})
                continue
            k["state"] = "RETIRED"
            k["retired_seq"] = seq
            ret_ev = {"trigger": "key_retire"}
            _emit(diags, seq=seq, code="N_KEY_RETIRED", severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=ret_ev)
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="retired", evidence=ret_ev)

        elif kind == "key_compromise":
            key_id = ev["key_id"]
            reason = ev["reason"]
            if key_id not in keys:
                _emit(diags, seq=seq, code="E_COMPROMISE_UNKNOWN",
                      severity="error",
                      severity_rank=_severity_rank(policy, "error"),
                      key_id=key_id, evidence={})
                continue
            k = keys[key_id]
            if k["state"] == "COMPROMISED":
                _emit(diags, seq=seq, code="W_COMPROMISE_REDUNDANT",
                      severity="warning",
                      severity_rank=_severity_rank(policy, "warning"),
                      key_id=key_id, evidence={})
                continue
            k["state"] = "COMPROMISED"
            k["compromised_seq"] = seq
            comp_ev = {"trigger": "key_compromise", "reason": reason}
            _emit(diags, seq=seq, code="N_KEY_COMPROMISED",
                  severity="notice",
                  severity_rank=_severity_rank(policy, "notice"),
                  key_id=key_id, evidence=comp_ev)
            _push_audit(audit, seq=seq, tick=tick, key_id=key_id,
                        kind="compromised", evidence=comp_ev)

        elif kind == "tick":
            pass

    return _materialize_outputs(
        keys=keys, audit=audit, encryptions=encryptions, diags=diags,
        events_total=len(events),
    )


def _materialize_outputs(*, keys: dict, audit: list, encryptions: list,
                         diags: list, events_total: int) -> dict[str, Any]:
    key_list = sorted(
        [
            {
                "algorithm": k["algorithm"],
                "compromised_seq": k["compromised_seq"],
                "exhausted_seq": k["exhausted_seq"],
                "installed_seq": k["installed_seq"],
                "key_id": k["key_id"],
                "last_use_tick": k["last_use_tick"],
                "max_uses": k["max_uses"],
                "retired_seq": k["retired_seq"],
                "state": k["state"],
                "uses_count": k["uses_count"],
            }
            for k in keys.values()
        ],
        key=lambda k: k["key_id"],
    )

    encryptions_sorted = sorted(encryptions, key=lambda e: e["seq"])
    audit_sorted = sorted(audit, key=lambda a: (a["seq"], a["key_id"]))

    def diag_sort_key(d: dict) -> tuple:
        return (
            d["severity_rank"], d["seq"], d["code"],
            d["key_id"] if d["key_id"] is not None else "",
        )

    diags_sorted = sorted(diags, key=diag_sort_key)

    sev = {"error": 0, "warning": 0, "notice": 0}
    for d in diags_sorted:
        sev[d["severity"]] += 1

    enc_accepted = sum(1 for e in encryptions_sorted if e["outcome"] == "accepted")
    enc_rejected = sum(1 for e in encryptions_sorted if e["outcome"] == "rejected")

    totals = {
        "encryptions_accepted": enc_accepted,
        "encryptions_rejected": enc_rejected,
        "encryptions_total": len(encryptions_sorted),
        "errors": sev["error"],
        "events_total": events_total,
        "keys_total": len(key_list),
        "notices": sev["notice"],
        "warnings": sev["warning"],
    }

    return {
        "key_states":     {"keys": key_list},
        "encryption_log": {"encryptions": encryptions_sorted},
        "audit_log":      {"transitions": audit_sorted},
        "diagnostics":    {"diagnostics": diags_sorted},
        "summary":        {"totals": totals},
    }


# ---------------------------------------------------------------------------
# Closed catalogues
# ---------------------------------------------------------------------------

ALLOWED_DIAGNOSTIC_CODES = frozenset({
    "E_INVALID_EVENT", "E_DUPLICATE_KEY", "E_ALGORITHM_UNKNOWN",
    "E_KEY_UNKNOWN", "E_KEY_NOT_ACTIVE", "E_KEY_EXHAUSTED",
    "E_KEY_COMPROMISED", "E_NONCE_REUSE", "E_RETIRE_UNKNOWN",
    "E_RETIRE_NOT_ACTIVE", "E_COMPROMISE_UNKNOWN",
    "W_KEY_NEAR_EXHAUSTION", "W_RETIRE_ALREADY_RETIRED",
    "W_COMPROMISE_REDUNDANT",
    "N_KEY_INSTALLED", "N_KEY_RETIRED", "N_KEY_IDLE_RETIRED",
    "N_KEY_EXHAUSTED", "N_KEY_COMPROMISED",
})

ALLOWED_KEY_STATES = frozenset({"ACTIVE", "RETIRED", "EXHAUSTED", "COMPROMISED"})
ALLOWED_EVENT_KINDS = frozenset(KIND_REQUIRED_FIELDS.keys())
ALLOWED_ENCRYPTION_REASONS = frozenset({
    None, "UNKNOWN_KEY", "RETIRED", "EXHAUSTED", "COMPROMISED", "NONCE_REUSE",
})
ALLOWED_AUDIT_KINDS = frozenset({
    "installed", "retired", "idle_retired", "exhausted", "compromised",
})

SCHEMAS_DIR = Path("/app/schemas")

OUTPUT_SCHEMA_BY_FILE = {
    "key_states.json":     "key_states.schema.json",
    "encryption_log.json": "encryption_log.schema.json",
    "audit_log.json":      "audit_log.schema.json",
    "diagnostics.json":    "diagnostics.schema.json",
    "summary.json":        "summary.schema.json",
}

_JSON_SCHEMA_TYPES = {
    "object":  dict,
    "array":   list,
    "string":  str,
    "integer": int,
    "number":  (int, float),
    "boolean": bool,
    "null":    type(None),
}


def _check_schema(data: Any, schema: dict, path: str = "$") -> list[str]:
    errors: list[str] = []
    expected_type = schema.get("type")
    if expected_type is not None:
        type_list = (
            [expected_type] if isinstance(expected_type, str)
            else list(expected_type)
        )
        py_types: list = []
        for et in type_list:
            t = _JSON_SCHEMA_TYPES.get(et)
            if t is None:
                continue
            if isinstance(t, tuple):
                py_types.extend(t)
            else:
                py_types.append(t)
        if py_types:
            ok = any(isinstance(data, t) for t in py_types)
            if "integer" in type_list and isinstance(data, bool):
                ok = False
            if not ok:
                errors.append(
                    f"{path} expected {expected_type}, got {type(data).__name__}"
                )
                return errors
    if "enum" in schema:
        if data not in schema["enum"]:
            errors.append(f"{path} value {data!r} not in enum {schema['enum']}")
    if isinstance(data, dict):
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"{path} missing required property '{req}'")
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name in data:
                errors += _check_schema(
                    data[prop_name], prop_schema, f"{path}.{prop_name}"
                )
    elif isinstance(data, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(data):
                errors += _check_schema(item, item_schema, f"{path}[{i}]")
    return errors


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def precomputed_input_hashes() -> dict[Path, str]:
    return {p: sha256_of(p) for p in (KEYS_PATH, EVENTS_PATH, POLICY_PATH)}


@pytest.fixture(scope="module")
def reference_outputs() -> dict[str, Any]:
    keys_in = load_json(KEYS_PATH)
    events_in = load_json(EVENTS_PATH)
    policy = load_json(POLICY_PATH)
    return simulate(keys_in, events_in, policy)


@pytest.fixture(scope="module")
def binary_run_outputs(reference_outputs, precomputed_input_hashes) -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not _java_class_ready():
        pytest.skip("Java entry class not built")
    proc = subprocess.run(
        [*_java_cmd(DATA_DIR, OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        pytest.fail(
            f"binary failed: rc={proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    for p in ALL_OUT_PATHS:
        if not p.exists():
            pytest.fail(f"binary did not write {p}")


# ---------------------------------------------------------------------------
# Helpers for synthetic-input scenarios
# ---------------------------------------------------------------------------


def _write_synthetic_inputs(data_dir: Path, keys: dict, events: dict,
                            policy: dict) -> None:
    (data_dir / "keys.json").write_text(json.dumps(keys), encoding="utf-8")
    (data_dir / "events.json").write_text(json.dumps(events), encoding="utf-8")
    (data_dir / "policy.json").write_text(json.dumps(policy), encoding="utf-8")


def _run_binary_synthetic(tmp_path: Path, keys: dict, events: dict,
                          policy: dict) -> tuple[dict, dict]:
    data_dir = tmp_path / "data"
    out_dir = tmp_path / "out"
    data_dir.mkdir()
    out_dir.mkdir()
    _write_synthetic_inputs(data_dir, keys, events, policy)
    proc = subprocess.run(
        [*_java_cmd(data_dir, out_dir)],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, (
        f"binary failed on synthetic input: rc={proc.returncode}\n"
        f"stderr={proc.stderr}"
    )
    actual = {
        "key_states":     load_json(out_dir / "key_states.json"),
        "encryption_log": load_json(out_dir / "encryption_log.json"),
        "audit_log":      load_json(out_dir / "audit_log.json"),
        "diagnostics":    load_json(out_dir / "diagnostics.json"),
        "summary":        load_json(out_dir / "summary.json"),
    }
    reference = simulate(keys, events, policy)
    return actual, reference


def _default_policy(*, allowed_algorithms: list[str] | None = None,
                    idle: int = 1000,
                    near_num: int = 9, near_den: int = 10) -> dict:
    return {
        "allowed_algorithms": allowed_algorithms or [
            "aes-gcm-128", "chacha20-poly1305",
        ],
        "idle_retire_ticks": idle,
        "near_exhaustion_ratio": [near_num, near_den],
        "severity_ranks": {"error": 0, "warning": 1, "notice": 2},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCliContract:
    def test_zero_args_fails(self):
        proc = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)], capture_output=True, timeout=30)
        assert proc.returncode != 0

    def test_one_arg_fails(self, tmp_path):
        proc = subprocess.run([*_java_cmd(DATA_DIR, OUT_DIR)],
                              capture_output=True, timeout=30)
        assert proc.returncode != 0

    def test_three_args_fails(self, tmp_path):
        proc = subprocess.run(
            [*_java_cmd(DATA_DIR, OUT_DIR)],
            capture_output=True, timeout=30)
        assert proc.returncode != 0

    def test_reads_from_argv_not_hardcoded(self, tmp_path, reference_outputs,
                                           binary_run_outputs):
        alt_data = tmp_path / "alt_data"
        alt_out  = tmp_path / "alt_out"
        alt_data.mkdir()
        alt_out.mkdir()
        for src in (KEYS_PATH, EVENTS_PATH, POLICY_PATH):
            shutil.copy(src, alt_data / src.name)
        proc = subprocess.run(
            [*_java_cmd(alt_data, alt_out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        actual = load_json(alt_out / "key_states.json")
        assert actual == reference_outputs["key_states"]

    def test_missing_input_file_fails(self, tmp_path, binary_run_outputs):
        only_keys = tmp_path / "only_keys"
        only_keys.mkdir()
        shutil.copy(KEYS_PATH, only_keys / "keys.json")
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(only_keys, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode != 0

    def test_malformed_json_input_fails(self, tmp_path, binary_run_outputs):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(KEYS_PATH, bad_data / "keys.json")
        shutil.copy(POLICY_PATH, bad_data / "policy.json")
        (bad_data / "events.json").write_text("{not valid json", encoding="utf-8")
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode != 0

    def test_policy_missing_required_field_fails(self, tmp_path,
                                                  binary_run_outputs):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(KEYS_PATH, bad_data / "keys.json")
        shutil.copy(EVENTS_PATH, bad_data / "events.json")
        bad_policy = load_json(POLICY_PATH)
        bad_policy.pop("idle_retire_ticks", None)
        (bad_data / "policy.json").write_text(
            json.dumps(bad_policy), encoding="utf-8"
        )
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode != 0

    def test_keys_missing_required_field_fails(self, tmp_path,
                                                binary_run_outputs):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(POLICY_PATH, bad_data / "policy.json")
        shutil.copy(EVENTS_PATH, bad_data / "events.json")
        (bad_data / "keys.json").write_text(
            json.dumps({"keys": [{"key_id": "k0", "algorithm": "aes-gcm-128"}]}),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode != 0

    def test_event_missing_top_level_field_fails(self, tmp_path,
                                                  binary_run_outputs):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(POLICY_PATH, bad_data / "policy.json")
        shutil.copy(KEYS_PATH, bad_data / "keys.json")
        (bad_data / "events.json").write_text(
            json.dumps({"events": [{"tick": 1, "kind": "tick"}]}),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode != 0

    @pytest.mark.parametrize("kind,missing_field,base_event", [
        ("key_install",    "key_id",    {"algorithm": "aes-gcm-128", "max_uses": 10}),
        ("key_install",    "algorithm", {"key_id": "k99", "max_uses": 10}),
        ("key_install",    "max_uses",  {"key_id": "k99", "algorithm": "aes-gcm-128"}),
        ("encrypt",        "key_id",    {"nonce": 1}),
        ("encrypt",        "nonce",     {"key_id": "k99"}),
        ("key_retire",     "key_id",    {}),
        ("key_compromise", "key_id",    {"reason": "side_channel"}),
        ("key_compromise", "reason",    {"key_id": "k99"}),
    ])
    def test_per_kind_missing_required_field_emits_invalid_event_and_continues(
        self, tmp_path, binary_run_outputs, kind, missing_field, base_event,
    ):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(POLICY_PATH, bad_data / "policy.json")
        (bad_data / "keys.json").write_text(
            json.dumps({"keys": []}), encoding="utf-8",
        )
        ev = {"seq": 1, "tick": 1, "kind": kind, **base_event}
        (bad_data / "events.json").write_text(
            json.dumps({"events": [ev]}), encoding="utf-8",
        )
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, (
            f"Per-kind missing fields must NOT crash; kind={kind} "
            f"missing={missing_field}; stderr={proc.stderr}"
        )
        diags = load_json(out / "diagnostics.json")["diagnostics"]
        bad = [d for d in diags
               if d["code"] == "E_INVALID_EVENT"
               and d.get("evidence", {}).get("reason") == "missing_field"]
        assert bad, (
            f"Expected E_INVALID_EVENT(missing_field) for kind={kind} "
            f"missing={missing_field}; got diagnostics={diags}"
        )

    def test_unknown_event_kind_emits_invalid_event_and_continues(
        self, tmp_path, binary_run_outputs,
    ):
        bad_data = tmp_path / "bad"
        bad_data.mkdir()
        shutil.copy(POLICY_PATH, bad_data / "policy.json")
        (bad_data / "keys.json").write_text(
            json.dumps({"keys": []}), encoding="utf-8",
        )
        (bad_data / "events.json").write_text(
            json.dumps({"events": [
                {"seq": 1, "tick": 1, "kind": "fizzbuzz"},
            ]}),
            encoding="utf-8",
        )
        out = tmp_path / "out"
        out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(bad_data, out)],
            capture_output=True, text=True, timeout=30,
        )
        assert proc.returncode == 0, proc.stderr
        diags = load_json(out / "diagnostics.json")["diagnostics"]
        bad = [d for d in diags
               if d["code"] == "E_INVALID_EVENT"
               and d.get("evidence", {}).get("reason") == "unknown_kind"]
        assert bad, f"Expected E_INVALID_EVENT(unknown_kind); got {diags}"

    def test_events_seq_is_processed_in_ascending_order(
        self, tmp_path, reference_outputs, binary_run_outputs,
    ):
        alt_data = tmp_path / "shuffled"
        alt_out  = tmp_path / "out"
        alt_data.mkdir()
        alt_out.mkdir()
        shutil.copy(KEYS_PATH, alt_data / "keys.json")
        shutil.copy(POLICY_PATH, alt_data / "policy.json")
        events = json.loads(EVENTS_PATH.read_text())
        shuffled = list(reversed(events["events"]))
        (alt_data / "events.json").write_text(
            json.dumps({"events": shuffled}), encoding="utf-8"
        )
        proc = subprocess.run(
            [*_java_cmd(alt_data, alt_out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        actual = load_json(alt_out / "diagnostics.json")
        assert actual == reference_outputs["diagnostics"]


# ---------------------------------------------------------------------------
# Targeted semantic scenarios
# ---------------------------------------------------------------------------


class TestSemanticScenarios:
    def test_nonce_reuse_marks_key_compromised(self, tmp_path,
                                                binary_run_outputs):
        keys = {"keys": [{"key_id": "ka", "algorithm": "aes-gcm-128",
                          "max_uses": 100}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "encrypt", "key_id": "ka",
             "nonce": 42},
            {"seq": 2, "tick": 2, "kind": "encrypt", "key_id": "ka",
             "nonce": 42},
            {"seq": 3, "tick": 3, "kind": "encrypt", "key_id": "ka",
             "nonce": 99},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        diag_codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_NONCE_REUSE" in diag_codes
        assert "N_KEY_COMPROMISED" in diag_codes
        ka = next(k for k in actual["key_states"]["keys"]
                  if k["key_id"] == "ka")
        assert ka["state"] == "COMPROMISED"
        third = [e for e in actual["encryption_log"]["encryptions"]
                 if e["seq"] == 3]
        assert third and third[0]["outcome"] == "rejected"
        assert third[0]["reason"] == "COMPROMISED"

    def test_max_uses_exhausts_key(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kb", "algorithm": "aes-gcm-128",
                          "max_uses": 2}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "encrypt", "key_id": "kb",
             "nonce": 1},
            {"seq": 2, "tick": 2, "kind": "encrypt", "key_id": "kb",
             "nonce": 2},
            {"seq": 3, "tick": 3, "kind": "encrypt", "key_id": "kb",
             "nonce": 3},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        kb = next(k for k in actual["key_states"]["keys"]
                  if k["key_id"] == "kb")
        assert kb["state"] == "EXHAUSTED"
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "N_KEY_EXHAUSTED" in codes
        assert "E_KEY_EXHAUSTED" in codes

    def test_near_exhaustion_warns_once(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kc", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events_list = []
        seq = 0
        for n in range(1, 10):
            seq += 1
            events_list.append(
                {"seq": seq, "tick": seq, "kind": "encrypt",
                 "key_id": "kc", "nonce": n}
            )
        events = {"events": events_list}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events,
            _default_policy(near_num=8, near_den=10),
        )
        assert actual == reference
        warns = [d for d in actual["diagnostics"]["diagnostics"]
                 if d["code"] == "W_KEY_NEAR_EXHAUSTION"]
        assert len(warns) == 1, f"Expected exactly one near-exhaustion warning; got {warns}"

    def test_duplicate_key_install_rejected(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kd", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "key_install", "key_id": "kd",
             "algorithm": "aes-gcm-128", "max_uses": 5},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_DUPLICATE_KEY" in codes

    def test_unknown_algorithm_rejected(self, tmp_path, binary_run_outputs):
        keys = {"keys": []}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "key_install", "key_id": "ke",
             "algorithm": "snake-oil-256", "max_uses": 5},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_ALGORITHM_UNKNOWN" in codes
        assert not any(k["key_id"] == "ke"
                       for k in actual["key_states"]["keys"])

    def test_idle_retire_sweep_fires(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kf", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "encrypt", "key_id": "kf",
             "nonce": 1},
            {"seq": 2, "tick": 100, "kind": "tick"},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(idle=50),
        )
        assert actual == reference
        kf = next(k for k in actual["key_states"]["keys"]
                  if k["key_id"] == "kf")
        assert kf["state"] == "RETIRED"
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "N_KEY_IDLE_RETIRED" in codes

    def test_retire_then_encrypt_rejected(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kg", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "key_retire", "key_id": "kg"},
            {"seq": 2, "tick": 2, "kind": "encrypt", "key_id": "kg",
             "nonce": 1},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_KEY_NOT_ACTIVE" in codes
        kg = next(k for k in actual["key_states"]["keys"]
                  if k["key_id"] == "kg")
        assert kg["state"] == "RETIRED"

    def test_retire_already_retired_warns(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kh", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "key_retire", "key_id": "kh"},
            {"seq": 2, "tick": 2, "kind": "key_retire", "key_id": "kh"},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "W_RETIRE_ALREADY_RETIRED" in codes

    def test_compromise_event_marks_key_and_blocks_encrypts(
        self, tmp_path, binary_run_outputs,
    ):
        keys = {"keys": [{"key_id": "ki", "algorithm": "aes-gcm-128",
                          "max_uses": 10}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "key_compromise",
             "key_id": "ki", "reason": "side_channel"},
            {"seq": 2, "tick": 2, "kind": "encrypt", "key_id": "ki",
             "nonce": 1},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_KEY_COMPROMISED" in codes
        assert "N_KEY_COMPROMISED" in codes
        ki = next(k for k in actual["key_states"]["keys"]
                  if k["key_id"] == "ki")
        assert ki["state"] == "COMPROMISED"

    def test_retire_not_active_for_exhausted(self, tmp_path, binary_run_outputs):
        keys = {"keys": [{"key_id": "kj", "algorithm": "aes-gcm-128",
                          "max_uses": 1}]}
        events = {"events": [
            {"seq": 1, "tick": 1, "kind": "encrypt", "key_id": "kj",
             "nonce": 1},
            {"seq": 2, "tick": 2, "kind": "key_retire", "key_id": "kj"},
        ]}
        actual, reference = _run_binary_synthetic(
            tmp_path, keys, events, _default_policy(),
        )
        assert actual == reference
        codes = [d["code"] for d in actual["diagnostics"]["diagnostics"]]
        assert "E_RETIRE_NOT_ACTIVE" in codes


# ---------------------------------------------------------------------------
# Schema conformance
# ---------------------------------------------------------------------------


class TestSchemaConformance:
    def test_outputs_conform_to_app_schemas(self, binary_run_outputs):
        for out_name, schema_name in OUTPUT_SCHEMA_BY_FILE.items():
            schema_path = SCHEMAS_DIR / schema_name
            assert schema_path.exists(), (
                f"missing schema {schema_path}; harness expects "
                f"{SCHEMAS_DIR} to ship the closed catalogue"
            )
            schema = load_json(schema_path)
            data = load_json(OUT_DIR / out_name)
            errors = _check_schema(data, schema)
            assert not errors, (
                f"{out_name} does not conform to {schema_name}:\n"
                + "\n".join(errors[:20])
            )

    def test_all_diagnostic_codes_are_in_closed_catalogue(
        self, binary_run_outputs,
    ):
        diags = load_json(DIAG_PATH)["diagnostics"]
        bad = [d["code"] for d in diags
               if d["code"] not in ALLOWED_DIAGNOSTIC_CODES]
        assert not bad, f"Unknown diagnostic codes: {bad}"

    def test_diagnostics_severity_and_rank_consistent(
        self, binary_run_outputs,
    ):
        policy = load_json(POLICY_PATH)
        ranks = policy["severity_ranks"]
        diags = load_json(DIAG_PATH)["diagnostics"]
        for d in diags:
            assert d["severity"] in {"error", "warning", "notice"}
            assert d["severity_rank"] == ranks[d["severity"]]

    def test_diagnostics_sorted_by_documented_key(self, binary_run_outputs):
        diags = load_json(DIAG_PATH)["diagnostics"]
        sortable = [
            (d["severity_rank"], d["seq"], d["code"],
             d["key_id"] if d["key_id"] is not None else "")
            for d in diags
        ]
        assert sortable == sorted(sortable)

    def test_key_states_use_documented_values(self, binary_run_outputs):
        keys = load_json(KEY_STATES_PATH)["keys"]
        for k in keys:
            assert k["state"] in ALLOWED_KEY_STATES
            assert k["max_uses"] > 0
            assert k["uses_count"] >= 0
            assert k["uses_count"] <= k["max_uses"]

    def test_encryption_log_uses_documented_reasons(self, binary_run_outputs):
        entries = load_json(ENC_LOG_PATH)["encryptions"]
        for e in entries:
            assert e["outcome"] in {"accepted", "rejected"}
            assert e["reason"] in ALLOWED_ENCRYPTION_REASONS, (
                f"reason {e['reason']!r} not in catalogue"
            )
            if e["outcome"] == "accepted":
                assert e["reason"] is None
            else:
                assert e["reason"] is not None

    def test_audit_log_uses_documented_kinds(self, binary_run_outputs):
        transitions = load_json(AUDIT_LOG_PATH)["transitions"]
        for t in transitions:
            assert t["kind"] in ALLOWED_AUDIT_KINDS

    def test_main_corpus_exercises_all_event_kinds(self, binary_run_outputs):
        events = load_json(EVENTS_PATH)["events"]
        seen = {ev["kind"] for ev in events if "kind" in ev}
        missing = ALLOWED_EVENT_KINDS - seen
        assert not missing, f"Main corpus missing event kinds: {missing}"

    def test_main_corpus_exercises_all_severity_tiers(self, binary_run_outputs):
        diags = load_json(DIAG_PATH)["diagnostics"]
        tiers = {d["severity"] for d in diags}
        assert tiers == {"error", "warning", "notice"}, (
            f"Main corpus missing severity tiers: {tiers}"
        )

    def test_main_corpus_exercises_all_key_states(self, binary_run_outputs):
        states = {k["state"] for k in load_json(KEY_STATES_PATH)["keys"]}
        missing = ALLOWED_KEY_STATES - states
        assert not missing, f"Main corpus missing key states: {missing}"

    def test_summary_is_consistent_with_other_outputs(self, binary_run_outputs):
        summary = load_json(SUMMARY_PATH)["totals"]
        diags = load_json(DIAG_PATH)["diagnostics"]
        encs = load_json(ENC_LOG_PATH)["encryptions"]
        keys = load_json(KEY_STATES_PATH)["keys"]
        events_in = load_json(EVENTS_PATH)["events"]

        errs = sum(1 for d in diags if d["severity"] == "error")
        warns = sum(1 for d in diags if d["severity"] == "warning")
        notices = sum(1 for d in diags if d["severity"] == "notice")
        assert summary["errors"] == errs
        assert summary["warnings"] == warns
        assert summary["notices"] == notices

        accepted = sum(1 for e in encs if e["outcome"] == "accepted")
        rejected = sum(1 for e in encs if e["outcome"] == "rejected")
        assert summary["encryptions_accepted"] == accepted
        assert summary["encryptions_rejected"] == rejected
        assert summary["encryptions_total"] == len(encs)
        assert summary["keys_total"] == len(keys)
        assert summary["events_total"] == len(events_in)

    def test_determinism_two_runs_byte_identical(self, binary_run_outputs):
        first = {p: p.read_bytes() for p in ALL_OUT_PATHS}
        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [*_java_cmd(DATA_DIR, OUT_DIR)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        second = {p: p.read_bytes() for p in ALL_OUT_PATHS}
        for p in ALL_OUT_PATHS:
            assert first[p] == second[p], (
                f"{p} differs between two consecutive runs"
            )


# ---------------------------------------------------------------------------
# Filesystem discipline
# ---------------------------------------------------------------------------


class TestStrictReplayDiscipline:
    def test_no_extra_files_written_outside_output_dir(self, tmp_path,
                                                       binary_run_outputs):
        scratch_data = tmp_path / "scratch_data"
        scratch_out  = tmp_path / "scratch_out"
        scratch_data.mkdir()
        scratch_out.mkdir()
        for src in (KEYS_PATH, EVENTS_PATH, POLICY_PATH):
            shutil.copy(src, scratch_data / src.name)
        existing_files = set(p.relative_to(tmp_path)
                             for p in tmp_path.rglob("*") if p.is_file())
        proc = subprocess.run(
            [*_java_cmd(scratch_data, scratch_out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        post_files = set(p.relative_to(tmp_path)
                         for p in tmp_path.rglob("*") if p.is_file())
        new_files = post_files - existing_files
        for p in new_files:
            assert str(p).startswith("scratch_out/"), (
                f"binary wrote outside the output directory: {p}"
            )


# ---------------------------------------------------------------------------
# Reference equality
# ---------------------------------------------------------------------------


class TestOutputsMatchReference:
    def test_key_states_match_reference(self, reference_outputs,
                                          binary_run_outputs):
        actual = load_json(KEY_STATES_PATH)
        assert actual == reference_outputs["key_states"]

    def test_encryption_log_matches_reference(self, reference_outputs,
                                              binary_run_outputs):
        actual = load_json(ENC_LOG_PATH)
        assert actual == reference_outputs["encryption_log"]

    def test_audit_log_matches_reference(self, reference_outputs,
                                          binary_run_outputs):
        actual = load_json(AUDIT_LOG_PATH)
        assert actual == reference_outputs["audit_log"]

    def test_diagnostics_match_reference(self, reference_outputs,
                                          binary_run_outputs):
        actual = load_json(DIAG_PATH)
        assert actual == reference_outputs["diagnostics"]

    def test_summary_matches_reference(self, reference_outputs,
                                        binary_run_outputs):
        actual = load_json(SUMMARY_PATH)
        assert actual == reference_outputs["summary"]


# ---------------------------------------------------------------------------
# Canonical formatting + data immutability
# ---------------------------------------------------------------------------


class TestCanonicalFormat:
    def test_all_outputs_canonical(self, binary_run_outputs):
        for p in ALL_OUT_PATHS:
            ok, why = is_strictly_formatted(p)
            assert ok, why


class TestDataUnchanged:
    def test_inputs_unchanged(self, precomputed_input_hashes,
                              binary_run_outputs):
        for p, expected_hash in precomputed_input_hashes.items():
            assert sha256_of(p) == expected_hash, (
                f"binary mutated {p} (or harness did) - data immutability "
                f"violation"
            )

    def test_data_dir_unchanged_after_run(self, tmp_path,
                                          binary_run_outputs):
        alt_data = tmp_path / "alt_data"
        alt_data.mkdir()
        for src in (KEYS_PATH, EVENTS_PATH, POLICY_PATH):
            shutil.copy(src, alt_data / src.name)
        pre_hashes = {
            p.name: sha256_of(p) for p in alt_data.iterdir() if p.is_file()
        }
        alt_out = tmp_path / "alt_out"
        alt_out.mkdir()
        proc = subprocess.run(
            [*_java_cmd(alt_data, alt_out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        post_hashes = {
            p.name: sha256_of(p) for p in alt_data.iterdir() if p.is_file()
        }
        assert pre_hashes == post_hashes, (
            "binary mutated files inside the data directory"
        )


# ---------------------------------------------------------------------------
# Build / binary provenance
# ---------------------------------------------------------------------------


class TestBinaryProvenance:
    def test_binary_built_from_authored_sources(self, binary_run_outputs):
        """Agent-authored Java sources exist under /app/src."""
        assert _src_files(), "no authored .java sources under /app/src"

    def test_binary_newer_than_sources(self, binary_run_outputs):
        """Compiled class is not older than any build input under /app."""
        assert _java_class_ready()
        binary_mtime = (BUILD_DIR / f"{JAVA_CLASS}.class").stat().st_mtime
        for f in _all_app_build_inputs():
            assert binary_mtime >= f.stat().st_mtime - 1, (
                f"class {(BUILD_DIR / f'{JAVA_CLASS}.class')} older than source {f}"
            )
