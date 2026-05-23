"""Verifier suite for  (typescript)."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

DATA_DIR  = Path("/app/data")
OUT_DIR   = Path("/app/output")
BUILD_DIR = Path("/app/build")
BINARY_PATH = BUILD_DIR / "mqttrtr"

CLIENTS_PATH       = DATA_DIR / "clients.json"
SUBSCRIPTIONS_PATH = DATA_DIR / "subscriptions.json"
RETAINED_PATH      = DATA_DIR / "retained.json"
EVENTS_PATH        = DATA_DIR / "events.json"
POLICY_PATH        = DATA_DIR / "policy.json"

BROKER_STATE_PATH = OUT_DIR / "broker_state.json"
DELIVERY_LOG_PATH = OUT_DIR / "delivery_log.json"
SESSION_LOG_PATH  = OUT_DIR / "session_log.json"
DIAG_PATH         = OUT_DIR / "diagnostics.json"
SUMMARY_PATH      = OUT_DIR / "summary.json"

ALL_OUT_PATHS = (BROKER_STATE_PATH, DELIVERY_LOG_PATH, SESSION_LOG_PATH,
                 DIAG_PATH, SUMMARY_PATH)

EXPECTED_INPUT_HASHES: dict[Path, str] = {
    CLIENTS_PATH:       "36d20a290fa83dd9a17dc64b90f565a94488345a11b93ead00b63da5bdf0f97e",
    SUBSCRIPTIONS_PATH: "d2ecaf28ea2d3f4efd4d9b1bfd6dd0fd1a1164d9fba05d6e871eca7dd012d4c8",
    RETAINED_PATH:      "1b69337275d7c3845a9a72799fd7190c3476399bae399e4008608b8a0da2220b",
    EVENTS_PATH:        "3dbe5f2b18d9e3da251a1db92ef0fe455fede50a649b2552faaf0fdf36f79056",
    POLICY_PATH:        "c7735ed5e009de7c1e617a176a39f5c52d9692ab3c790154ed2fef263531d9e2",
}

DOCS_DIAG_PATH = Path("/app/docs/diagnostics.md")


def _load_diag_codes_from_docs() -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of
    diagnostic codes and their severities. The single source of truth
    for codes is the docs, not this test file. Codes live in tables
    grouped under '## Error codes', '## Warning codes', and
    '## Note codes' section headings, with each code line shaped like:
        | `E_DUPLICATE_CONNECT` | <when text> | <extra fields> |
    """
    import re
    text = DOCS_DIAG_PATH.read_text(encoding="utf-8")
    codes: set[str] = set()
    severity: dict[str, str] = {}
    section_pat = re.compile(
        r"^\s*##\s+(?P<sev>Error|Warning|Note)\s+codes\b",
        re.IGNORECASE,
    )
    code_pat = re.compile(
        r"^\s*\|\s*`?(?P<code>[A-Z][A-Z0-9_]+)`?\s*\|"
    )
    cur_sev: str | None = None
    sev_map = {"error": "error", "warning": "warning", "note": "note"}
    for line in text.splitlines():
        sm = section_pat.match(line)
        if sm:
            cur_sev = sev_map[sm.group("sev").lower()]
            continue
        cm = code_pat.match(line)
        if cm and cur_sev is not None:
            code = cm.group("code")
            if code in {"CODE", "CODES"}:
                continue
            codes.add(code)
            severity[code] = cur_sev
    if not codes:
        raise RuntimeError(
            f"could not parse any diagnostic codes from {DOCS_DIAG_PATH}; "
            "check the docs format"
        )
    return frozenset(codes), severity


VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs()
SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}


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
# Reference simulator (mirrors /app/docs/) -- live verifier ground truth
# ---------------------------------------------------------------------------


def _is_valid_topic(topic: str) -> bool:
    if not topic:
        return False
    if "+" in topic or "#" in topic:
        return False
    levels = topic.split("/")
    if any(level == "" for level in levels):
        return False
    return True


def _is_valid_filter(filt: str, plus_allowed: bool, hash_allowed: bool) -> bool:
    if not filt:
        return False
    levels = filt.split("/")
    if any(level == "" for level in levels):
        return False
    for i, level in enumerate(levels):
        if "+" in level:
            if not plus_allowed:
                return False
            if level != "+":
                return False
        if "#" in level:
            if not hash_allowed:
                return False
            if level != "#":
                return False
            if i != len(levels) - 1:
                return False
    return True


def _filter_matches_topic(filt: str, topic: str) -> bool:
    f = filt.split("/")
    t = topic.split("/")
    fi = ti = 0
    while fi < len(f) and ti < len(t):
        if f[fi] == "#":
            return True
        if f[fi] == "+":
            fi += 1
            ti += 1
            continue
        if f[fi] != t[ti]:
            return False
        fi += 1
        ti += 1
    if fi < len(f) and f[fi] == "#" and fi == len(f) - 1:
        return True
    return fi == len(f) and ti == len(t)


def _add_diag(diags, seq, code, severity, **fields):
    d = {"code": code, "severity": severity}
    d.update(fields)
    diags.setdefault(seq, []).append(d)


def run_simulation(clients_doc, subs_doc, retained_doc, events_doc, policy):
    plus_allowed    = bool(policy.get("wildcard_plus_allowed", True))
    hash_allowed    = bool(policy.get("wildcard_hash_allowed", True))
    deliver_to_self = bool(policy.get("deliver_to_self", True))
    max_subs        = int(policy["max_subscriptions_per_client"])
    max_retained    = int(policy["max_retained"])
    now_sec         = int(policy["now_sec"])

    connected: dict[str, dict[str, Any]] = {}
    persistent_sessions: dict[str, dict[str, Any]] = {}

    for c in clients_doc["clients"]:
        cid = c["id"]
        is_connected  = bool(c.get("connected", True))
        is_persistent = bool(c["persistent"])
        if not is_connected and not is_persistent:
            raise ValueError(
                f"clients.json: {cid!r} disconnected & non-persistent"
            )
        if is_connected:
            if cid in connected:
                raise ValueError(f"duplicate connected client {cid!r}")
            connected[cid] = {
                "persistent": is_persistent,
                "keep_alive_sec": int(c["keep_alive_sec"]),
                "will": c.get("will"),
                "subs": {},
            }
        else:
            if cid in persistent_sessions:
                raise ValueError(f"duplicate persistent session {cid!r}")
            persistent_sessions[cid] = {"subs": {}}

    for s in subs_doc["subscriptions"]:
        cid  = s["client_id"]
        filt = s["filter"]
        q    = int(s["qos"])
        if cid in connected:
            connected[cid]["subs"][filt] = q
        elif cid in persistent_sessions:
            persistent_sessions[cid]["subs"][filt] = q
        else:
            raise ValueError(f"subscriptions.json: unknown client_id {cid!r}")

    retained: dict[str, dict[str, Any]] = {}
    for r in retained_doc["retained"]:
        retained[r["topic"]] = {
            "payload_id":      int(r["payload_id"]),
            "qos":             int(r["qos"]),
            "retained_at_sec": int(r["retained_at_sec"]),
        }

    events = sorted(events_doc["events"], key=lambda e: int(e["seq"]))
    for i, ev in enumerate(events):
        if int(ev["seq"]) != i:
            raise ValueError("events.json: seq must be dense 0..N-1")

    deliveries: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    diags: dict[int, list[dict[str, Any]]] = {}
    diag_counts: dict[str, int] = {}

    publishes_delivered = 0
    deliveries_total    = 0
    topics_published: set[str] = set()

    def _bump(code: str) -> None:
        diag_counts[code] = diag_counts.get(code, 0) + 1

    def _diag(seq, code, **fields):
        sev = DIAG_SEVERITY[code]
        _add_diag(diags, seq, code, sev, **fields)
        _bump(code)

    def _deliver_publish(seq, topic, pub_qos, payload_id, sender):
        nonlocal publishes_delivered, deliveries_total
        recipients = []
        for cid in sorted(connected):
            client = connected[cid]
            if cid == sender and not deliver_to_self:
                continue
            best = None
            for filt, sub_qos in client["subs"].items():
                if _filter_matches_topic(filt, topic):
                    q = min(pub_qos, sub_qos)
                    if best is None or q > best:
                        best = q
            if best is not None:
                recipients.append({"client_id": cid, "delivered_qos": best})
        if recipients:
            publishes_delivered += 1
            deliveries_total    += len(recipients)
        else:
            _diag(seq, "W_NO_SUBSCRIBERS", topic=topic)
        deliveries.append({
            "payload_id":  int(payload_id),
            "publish_qos": int(pub_qos),
            "recipients":  recipients,
            "seq":         int(seq),
            "topic":       topic,
        })

    def _update_retained(seq, topic, qos, payload_id):
        if payload_id == 0 and qos == 0:
            retained.pop(topic, None)
            return
        if topic not in retained and len(retained) >= max_retained:
            _diag(seq, "W_RETAINED_LIMIT", topic=topic)
            return
        retained[topic] = {
            "payload_id":      int(payload_id),
            "qos":             int(qos),
            "retained_at_sec": int(now_sec),
        }

    for ev in events:
        seq  = int(ev["seq"])
        kind = ev["kind"]

        if kind == "tick":
            now_sec += int(ev["delta_sec"])
            continue

        if kind == "connect":
            cid = ev["id"]
            clean = bool(ev["clean_start"])
            ka    = int(ev["keep_alive_sec"])
            will  = ev.get("will")
            if cid in connected:
                _diag(seq, "E_DUPLICATE_CONNECT", client_id=cid)
                continue
            if clean:
                persistent_sessions.pop(cid, None)
                connected[cid] = {
                    "persistent": False, "keep_alive_sec": ka,
                    "will": will, "subs": {},
                }
                action = "fresh"
                _diag(seq, "N_SESSION_FRESH", client_id=cid)
            else:
                if cid in persistent_sessions:
                    saved = persistent_sessions.pop(cid)
                    connected[cid] = {
                        "persistent": True, "keep_alive_sec": ka,
                        "will": will, "subs": dict(saved["subs"]),
                    }
                    action = "resumed"
                    _diag(seq, "N_SESSION_RESUMED", client_id=cid)
                else:
                    connected[cid] = {
                        "persistent": True, "keep_alive_sec": ka,
                        "will": will, "subs": {},
                    }
                    action = "fresh"
                    _diag(seq, "N_SESSION_FRESH", client_id=cid)
            sessions.append({
                "action": action, "client_id": cid,
                "kind": "connect", "seq": seq,
            })
            continue

        if kind in ("disconnect", "expire_keepalive"):
            cid = ev["id"]
            abrupt = bool(ev.get("abrupt", False)) or kind == "expire_keepalive"
            if cid not in connected:
                _diag(seq, "E_NOT_CONNECTED", client_id=cid)
                continue
            client = connected.pop(cid)
            if abrupt and client["will"] is not None:
                will = client["will"]
                if _is_valid_topic(will["topic"]):
                    _deliver_publish(seq, will["topic"], int(will["qos"]),
                                     int(will["payload_id"]), sender=cid)
                    if bool(will.get("retain", False)):
                        _update_retained(seq, will["topic"],
                                         int(will["qos"]),
                                         int(will["payload_id"]))
                    _diag(seq, "N_WILL_DELIVERED", client_id=cid)
                else:
                    _diag(seq, "E_INVALID_TOPIC", client_id=cid,
                          topic=will["topic"])
            session_kept = bool(client["persistent"])
            if session_kept:
                persistent_sessions[cid] = {"subs": dict(client["subs"])}
            sessions.append({
                "abrupt": abrupt, "client_id": cid,
                "kind": kind, "seq": seq, "session_kept": session_kept,
            })
            continue

        if kind == "subscribe":
            cid = ev["client_id"]
            filt = ev["filter"]
            q = int(ev["qos"])
            if cid not in connected:
                _diag(seq, "E_NOT_CONNECTED", client_id=cid)
                continue
            if not _is_valid_filter(filt, plus_allowed, hash_allowed):
                _diag(seq, "E_INVALID_TOPIC_FILTER",
                      client_id=cid, filter=filt)
                continue
            subs = connected[cid]["subs"]
            if filt not in subs and len(subs) >= max_subs:
                _diag(seq, "E_SUBSCRIPTION_LIMIT",
                      client_id=cid, filter=filt)
                continue
            subs[filt] = q
            for topic in sorted(retained):
                rec = retained[topic]
                if _filter_matches_topic(filt, topic):
                    delivered_qos = min(int(rec["qos"]), q)
                    deliveries.append({
                        "payload_id":  int(rec["payload_id"]),
                        "publish_qos": int(rec["qos"]),
                        "recipients":  [
                            {"client_id": cid, "delivered_qos": delivered_qos},
                        ],
                        "seq": seq, "topic": topic,
                    })
                    publishes_delivered += 1
                    deliveries_total    += 1
            continue

        if kind == "unsubscribe":
            cid = ev["client_id"]
            filt = ev["filter"]
            if cid not in connected:
                _diag(seq, "E_NOT_CONNECTED", client_id=cid)
                continue
            connected[cid]["subs"].pop(filt, None)
            continue

        if kind == "publish":
            topic = ev["topic"]
            q = int(ev["qos"])
            payload_id = int(ev["payload_id"])
            retain = bool(ev.get("retain", False))
            sender = ev.get("client_id")
            if not _is_valid_topic(topic):
                _diag(seq, "E_INVALID_TOPIC", topic=topic)
                continue
            topics_published.add(topic)
            _deliver_publish(seq, topic, q, payload_id, sender)
            if retain:
                _update_retained(seq, topic, q, payload_id)
            continue

        raise ValueError(f"unknown event kind: {kind}")

    return _build_outputs(connected, persistent_sessions, retained, now_sec,
                          deliveries, sessions, diags, diag_counts,
                          publishes_delivered, deliveries_total,
                          topics_published, len(events))


def _build_outputs(connected, persistent_sessions, retained, now_sec,
                   deliveries, sessions, diags, diag_counts,
                   publishes_delivered, deliveries_total,
                   topics_published, events_total):
    broker_state = {
        "clients": [
            {
                "id": cid,
                "keep_alive_sec": int(connected[cid]["keep_alive_sec"]),
                "persistent": bool(connected[cid]["persistent"]),
                "subscriptions": [
                    {"filter": f, "qos": int(connected[cid]["subs"][f])}
                    for f in sorted(connected[cid]["subs"])
                ],
            }
            for cid in sorted(connected)
        ],
        "now_sec": int(now_sec),
        "persistent_sessions": [
            {
                "client_id": cid,
                "subscriptions": [
                    {"filter": f, "qos": int(persistent_sessions[cid]["subs"][f])}
                    for f in sorted(persistent_sessions[cid]["subs"])
                ],
            }
            for cid in sorted(persistent_sessions)
        ],
        "retained": [
            {
                "payload_id":      int(retained[t]["payload_id"]),
                "qos":             int(retained[t]["qos"]),
                "retained_at_sec": int(retained[t]["retained_at_sec"]),
                "topic":           t,
            }
            for t in sorted(retained)
        ],
    }

    delivery_log = {
        "deliveries": [
            {
                "payload_id":  d["payload_id"],
                "publish_qos": d["publish_qos"],
                "recipients":  sorted(
                    d["recipients"], key=lambda r: r["client_id"],
                ),
                "seq":   d["seq"],
                "topic": d["topic"],
            }
            for d in sorted(deliveries, key=lambda d: (d["seq"], d["topic"]))
        ],
    }

    session_log = {"events": sessions}

    diag_events: list[dict[str, Any]] = []
    for seq in sorted(diags):
        items = sorted(diags[seq], key=lambda d: (
            SEVERITY_RANK[d["severity"]],
            d["code"],
            d.get("client_id", ""),
            d.get("topic", ""),
            d.get("filter", ""),
        ))
        diag_events.append({"diagnostics": items, "seq": seq})
    diagnostics_doc = {"events": diag_events}

    summary = {
        "active_clients":      len(connected),
        "deliveries_total":    deliveries_total,
        "diagnostics_by_code": dict(diag_counts),
        "events_total":        events_total,
        "persistent_sessions": len(persistent_sessions) +
                               sum(1 for c in connected.values() if c["persistent"]),
        "publishes_delivered": publishes_delivered,
        "retained_count":      len(retained),
        "topics_published":    sorted(topics_published),
    }

    return {
        "broker_state": broker_state,
        "delivery_log": delivery_log,
        "session_log":  session_log,
        "diagnostics":  diagnostics_doc,
        "summary":      summary,
    }


def reference_outputs() -> dict[str, Any]:
    return run_simulation(
        load_json(CLIENTS_PATH),
        load_json(SUBSCRIPTIONS_PATH),
        load_json(RETAINED_PATH),
        load_json(EVENTS_PATH),
        load_json(POLICY_PATH),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def expected_outputs() -> dict[str, Any]:
    return reference_outputs()


@pytest.fixture(scope="session")
def binary_run_outputs() -> dict[str, Any]:
    """Wipe /app/output and re-run the agent's binary with the canonical
    CLI. Tests asserting against /app/output/*.json depend on this fixture
    so the agent's binary is the only thing that produces those files."""
    assert BINARY_PATH.exists(), (
        f"binary not found at {BINARY_PATH}; agent must build TypeScript sources to "
        f"this path before tests run"
    )
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    start = time.time()
    proc = subprocess.run(
        [str(BINARY_PATH), str(DATA_DIR), str(OUT_DIR)],
        capture_output=True, text=True, timeout=120,
    )
    return {"start": start, "returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


# ---------------------------------------------------------------------------
# Tests against the pinned dataset
# ---------------------------------------------------------------------------


def test_inputs_unchanged() -> None:
    """Pinned input files must match the snapshot SHA-256 the task ships
    with. Both prevents agents rewriting inputs to ease the task AND keeps
    the live-recomputed reference deterministic."""
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input missing: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} has unexpected hash {actual}; expected {expected}"
        )


def test_binary_built_and_executable() -> None:
    """The agent must have built their TypeScript program to
    /app/build/mqttrtr and the file must be executable."""
    assert BINARY_PATH.exists(), (
        f"expected compiled binary at {BINARY_PATH}; agent must build TypeScript sources"
    )
    mode = BINARY_PATH.stat().st_mode
    assert mode & stat.S_IXUSR, f"{BINARY_PATH} is not executable"
    src_dir = Path("/app/src")
    src_files = (
        list(src_dir.rglob("*.ts"))
        + list(src_dir.rglob("*.ts"))
        + list(src_dir.rglob("*.ts"))
    )
    assert src_files, (
        "expected agent-authored TypeScript source (.ts) under /app/src; "
        f"found none (src_dir exists: {src_dir.exists()})"
    )




def test_binary_runs_on_pinned_inputs(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Smoke check that the compiled binary actually executed against the
    pinned dataset under /app/data."""
    assert binary_run_outputs["returncode"] == 0, (
        f"/app/build/mqttrtr failed to run on /app/data: "
        f"rc={binary_run_outputs['returncode']} "
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary rerun: {path}"


def test_binary_runs_cleanly_and_outputs_are_present(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The agent's binary must run with the canonical two-arg CLI on
    /app/data, exit 0, and produce all five non-empty parseable JSON
    outputs and no other files in /app/output."""
    rc = binary_run_outputs["returncode"]
    assert rc == 0, (
        f"/app/build/mqttrtr exited with rc={rc} when run with canonical "
        f"args /app/data /app/output;\nstdout={binary_run_outputs['stdout']!r}\n"
        f"stderr={binary_run_outputs['stderr']!r}"
    )
    for path in ALL_OUT_PATHS:
        assert path.exists(), f"output missing after binary run: {path}"
        assert path.stat().st_size > 0, f"output empty after binary run: {path}"
        load_json(path)
    expected_names = {p.name for p in ALL_OUT_PATHS}
    actual_files: list[Path] = []
    for entry in OUT_DIR.rglob("*"):
        if entry.is_dir():
            raise AssertionError(
                f"binary created a directory under /app/output: "
                f"{entry.relative_to(OUT_DIR)!s}; the spec says exactly five "
                "JSON output files and no other entries"
            )
        if entry.is_symlink():
            raise AssertionError(
                f"binary created a symlink under /app/output: "
                f"{entry.relative_to(OUT_DIR)!s}; only regular files allowed"
            )
        if entry.is_file():
            actual_files.append(entry)
    rels = sorted(str(p.relative_to(OUT_DIR)) for p in actual_files)
    assert rels == sorted(expected_names), (
        f"binary wrote unexpected files into /app/output: {rels}; expected "
        f"exactly {sorted(expected_names)}"
    )


def test_binary_rejects_wrong_arg_counts(tmp_path: Path) -> None:
    """The binary must enforce exactly two positional args. Calls with
    0/1/3 args must exit non-zero."""
    fake_data = tmp_path / "data"
    fake_data.mkdir()
    fake_out = tmp_path / "out"
    fake_out.mkdir()
    for n_args in (0, 1, 3):
        argv = [str(BINARY_PATH)]
        if n_args >= 1:
            argv.append(str(fake_data))
        if n_args >= 2:
            argv.append(str(fake_out))
        if n_args >= 3:
            argv.append("extra")
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        assert proc.returncode != 0, (
            f"binary should exit non-zero on {n_args} arg(s); got rc=0 "
            f"with stdout={proc.stdout!r} stderr={proc.stderr!r}"
        )


def test_outputs_strict_json_formatting(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every output is 2-space, sort-keys, ASCII-only, trailing-newline JSON."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        ok, msg = is_strictly_formatted(path)
        assert ok, msg


def _walk_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield k
            yield from _walk_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk_strings(v)


def test_outputs_are_ascii_at_every_depth(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every byte in every output JSON must be pure ASCII."""
    assert binary_run_outputs["returncode"] == 0
    for path in ALL_OUT_PATHS:
        raw = path.read_bytes()
        for i, b in enumerate(raw):
            assert b < 0x80, (
                f"{path} byte {i} = 0x{b:02x} is non-ASCII; outputs must be "
                "pure ASCII at the byte level"
            )
        doc = json.loads(raw.decode("utf-8"))
        for s in _walk_strings(doc):
            for ch in s:
                assert ord(ch) < 0x80, (
                    f"{path} contains non-ASCII string codepoint U+{ord(ch):04X} "
                    f"in {s!r}"
                )


def test_broker_state_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """broker_state.json must equal the live-computed reference exactly.

    Stresses:
      - clients sorted by id, subscriptions per client by filter
      - retained sorted by topic, persistent_sessions by client_id
      - now_sec equals starting now_sec + sum(tick.delta_sec)
      - persistent_sessions accurately reflects post-disconnect state
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(BROKER_STATE_PATH)
    assert actual == expected_outputs["broker_state"]


def test_delivery_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """delivery_log.json must equal the live-computed reference exactly.

    Stresses:
      - one delivery_log entry per publish event (including no-recipient ones)
      - retained-on-subscribe deliveries appear with correct delivered_qos
      - recipients sorted by client_id; deliveries sorted by (seq, topic)
      - delivered_qos == min(publish_qos, max matching sub_qos per recipient)
      - deliver_to_self semantics on the publishing client
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DELIVERY_LOG_PATH)
    assert actual == expected_outputs["delivery_log"]


def test_session_log_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """session_log.json must equal the live-computed reference exactly.

    Stresses:
      - exactly one entry per successful connect/disconnect/expire_keepalive
      - action='fresh'|'resumed' on connect; abrupt+session_kept on others
      - trace order preserved (no independent sort)
      - no entry for events that emitted E_NOT_CONNECTED / E_DUPLICATE_CONNECT
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SESSION_LOG_PATH)
    assert actual == expected_outputs["session_log"]


def test_diagnostics_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """diagnostics.json must equal the live-computed reference exactly.

    Stresses:
      - sparse layout: only events with diagnostics appear
      - per-event sort by (severity_rank, code, client_id, topic, filter)
      - closed code set; correct severity per code
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(DIAG_PATH)
    assert actual == expected_outputs["diagnostics"]


def test_summary_match_reference(
    binary_run_outputs: dict[str, Any],
    expected_outputs: dict[str, Any],
) -> None:
    """summary.json must equal the live-computed reference exactly.

    Stresses:
      - counters increment correctly across event kinds
      - topics_published is sorted ASCII
      - diagnostics_by_code is exactly the multiset of emitted codes
    """
    assert binary_run_outputs["returncode"] == 0
    actual = load_json(SUMMARY_PATH)
    assert actual == expected_outputs["summary"]


def test_diagnostic_codes_are_legal(
    binary_run_outputs: dict[str, Any],
) -> None:
    """Every diagnostic code is drawn from the closed set with correct
    severity, and within each event the list is sorted by
    (severity_rank, code, client_id, topic, filter)."""
    assert binary_run_outputs["returncode"] == 0
    diag = load_json(DIAG_PATH)
    seqs = [e["seq"] for e in diag["events"]]
    assert seqs == sorted(seqs), f"events not sorted by seq: {seqs}"
    for e in diag["events"]:
        prev = (-1, "", "", "", "")
        for d in e["diagnostics"]:
            assert d["code"] in VALID_DIAG_CODES, (
                f"event seq={e['seq']!r}: unknown code {d['code']!r}"
            )
            assert DIAG_SEVERITY[d["code"]] == d["severity"], (
                f"event seq={e['seq']!r}: code {d['code']!r} has wrong "
                f"severity {d['severity']!r}, expected {DIAG_SEVERITY[d['code']]!r}"
            )
            key = (
                SEVERITY_RANK[d["severity"]],
                d["code"],
                d.get("client_id", ""),
                d.get("topic", ""),
                d.get("filter", ""),
            )
            assert key >= prev, (
                f"event seq={e['seq']!r}: diagnostics not sorted by "
                f"(severity_rank, code, client_id, topic, filter); "
                f"got {key} after {prev}"
            )
            prev = key


def test_dataset_invariants_have_diversity(
    expected_outputs: dict[str, Any],
) -> None:
    """Dataset-level sanity: at least eight distinct diagnostic codes and
    at least three deliveries with at least one recipient must be exercised
    on the pinned input. A trivial trace would fail to stress the simulator.
    """
    diag_doc = expected_outputs["diagnostics"]
    seen_codes: set[str] = set()
    for e in diag_doc["events"]:
        for d in e["diagnostics"]:
            seen_codes.add(d["code"])
    assert len(seen_codes) >= 8, (
        f"dataset invariant: expected at least 8 distinct diagnostic codes "
        f"exercised; got {sorted(seen_codes)}"
    )
    delivered = [d for d in expected_outputs["delivery_log"]["deliveries"]
                 if d["recipients"]]
    assert len(delivered) >= 3, (
        "dataset invariant: expected at least three delivered publishes; "
        f"got {len(delivered)}"
    )
    assert expected_outputs["summary"]["retained_count"] >= 2, (
        "dataset invariant: expected at least two retained messages at end"
    )


# ---------------------------------------------------------------------------
# Hidden-dataset behavioural tests
# ---------------------------------------------------------------------------


def _run_binary_on(tmp_path: Path,
                   clients_doc: dict, subs_doc: dict,
                   retained_doc: dict, events_doc: dict, policy_doc: dict
                   ) -> dict[str, Any]:
    in_dir = tmp_path / "data"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / "clients.json").write_text(json.dumps(clients_doc), encoding="utf-8")
    (in_dir / "subscriptions.json").write_text(json.dumps(subs_doc), encoding="utf-8")
    (in_dir / "retained.json").write_text(json.dumps(retained_doc), encoding="utf-8")
    (in_dir / "events.json").write_text(json.dumps(events_doc), encoding="utf-8")
    (in_dir / "policy.json").write_text(json.dumps(policy_doc), encoding="utf-8")
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"binary failed on hidden dataset: rc={proc.returncode} "
        f"stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )
    docs: dict[str, Any] = {}
    for fname in ("broker_state.json", "delivery_log.json",
                  "session_log.json", "diagnostics.json", "summary.json"):
        docs[fname] = json.loads((out_dir / fname).read_text(encoding="utf-8"))
    return docs


def _ref_for(clients_doc, subs_doc, retained_doc, events_doc, policy_doc):
    return run_simulation(clients_doc, subs_doc, retained_doc,
                          events_doc, policy_doc)


def _empty_docs():
    return (
        {"clients": []},
        {"subscriptions": []},
        {"retained": []},
    )


def _base_policy(**overrides):
    p = {
        "now_sec": 0,
        "max_subscriptions_per_client": 8,
        "max_retained": 8,
        "wildcard_plus_allowed": True,
        "wildcard_hash_allowed": True,
        "deliver_to_self": True,
    }
    p.update(overrides)
    return p


def test_hidden_dataset_wildcard_plus_only_one_level(tmp_path: Path) -> None:
    """`+` matches exactly one topic level, not multiple."""
    clients = {"clients": [
        {"id": "p", "persistent": False, "keep_alive_sec": 30},
        {"id": "s", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": [
        {"client_id": "s", "filter": "a/+/c", "qos": 1},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "a/X/c", "payload_id": 1, "qos": 0, "retain": False},
        {"seq": 1, "kind": "publish", "topic": "a/X/Y/c", "payload_id": 2, "qos": 0, "retain": False},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    deliveries = actual["delivery_log.json"]["deliveries"]
    seq0 = next(d for d in deliveries if d["seq"] == 0)
    seq1 = next(d for d in deliveries if d["seq"] == 1)
    assert seq0["recipients"] == [{"client_id": "s", "delivered_qos": 0}]
    assert seq1["recipients"] == [], (
        "'a/+/c' must NOT match 'a/X/Y/c' because '+' is single-level"
    )


def test_hidden_dataset_wildcard_hash_terminal_only(tmp_path: Path) -> None:
    """`#` is only legal as the LAST level of a filter; mid-filter `#` is
    rejected with E_INVALID_TOPIC_FILTER and the subscription is unchanged."""
    clients = {"clients": [
        {"id": "s", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": []}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "subscribe", "client_id": "s",
         "filter": "a/#/b", "qos": 0},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["broker_state.json"] == expected["broker_state"]
    assert actual["diagnostics.json"]  == expected["diagnostics"]
    s = next(c for c in actual["broker_state.json"]["clients"] if c["id"] == "s")
    assert s["subscriptions"] == [], (
        "rejected subscribe must not be added to the client's subs"
    )
    diags = actual["diagnostics.json"]["events"]
    codes = [d["code"] for e in diags for d in e["diagnostics"]]
    assert codes == ["E_INVALID_TOPIC_FILTER"]


def test_hidden_dataset_qos_downgrade_min(tmp_path: Path) -> None:
    """delivered_qos = min(publish_qos, sub_qos) per recipient."""
    clients = {"clients": [
        {"id": "p",  "persistent": False, "keep_alive_sec": 30},
        {"id": "s0", "persistent": False, "keep_alive_sec": 30},
        {"id": "s1", "persistent": False, "keep_alive_sec": 30},
        {"id": "s2", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": [
        {"client_id": "s0", "filter": "t", "qos": 0},
        {"client_id": "s1", "filter": "t", "qos": 1},
        {"client_id": "s2", "filter": "t", "qos": 2},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "t", "payload_id": 1, "qos": 1, "retain": False, "client_id": "p"},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    rec = {r["client_id"]: r["delivered_qos"]
           for r in actual["delivery_log.json"]["deliveries"][0]["recipients"]}
    assert rec == {"s0": 0, "s1": 1, "s2": 1}, (
        f"min(publish_qos=1, sub_qos) downgrade wrong: {rec}"
    )


def test_hidden_dataset_recipient_max_qos_across_filters(tmp_path: Path) -> None:
    """When a single recipient matches multiple of its own filters for the
    same publish, the broker emits ONE recipient entry whose delivered_qos
    is the maximum delivered_qos across the matching filters (not one
    delivery_log entry per matching filter)."""
    clients = {"clients": [
        {"id": "s", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": [
        {"client_id": "s", "filter": "+/y", "qos": 0},
        {"client_id": "s", "filter": "x/+", "qos": 2},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "x/y", "payload_id": 1, "qos": 2, "retain": False},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    deliveries = actual["delivery_log.json"]["deliveries"]
    assert len(deliveries) == 1, (
        f"one publish should produce one delivery, not one per matching "
        f"filter; got {len(deliveries)}"
    )
    recs = deliveries[0]["recipients"]
    assert recs == [{"client_id": "s", "delivered_qos": 2}], (
        f"recipient should appear once with max delivered_qos=2; got {recs}"
    )


def test_hidden_dataset_deliver_to_self_false(tmp_path: Path) -> None:
    """When policy.deliver_to_self is false, the publishing client is
    excluded from its own publish's recipient list."""
    clients = {"clients": [
        {"id": "p", "persistent": False, "keep_alive_sec": 30},
        {"id": "q", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": [
        {"client_id": "p", "filter": "echo/#", "qos": 1},
        {"client_id": "q", "filter": "echo/#", "qos": 1},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "echo/foo", "payload_id": 1, "qos": 1, "retain": False, "client_id": "p"},
    ]}
    policy = _base_policy(deliver_to_self=False)
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    recs = [r["client_id"] for r in actual["delivery_log.json"]["deliveries"][0]["recipients"]]
    assert recs == ["q"], (
        f"deliver_to_self=false must exclude publisher; got {recs}"
    )


def test_hidden_dataset_retained_on_subscribe_delivers(tmp_path: Path) -> None:
    """A successful subscribe pushes every matching retained message to the
    new subscriber at delivered_qos = min(retained_qos, sub_qos)."""
    clients = {"clients": [
        {"id": "s", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": []}
    retained = {"retained": [
        {"topic": "r/a", "payload_id": 10, "qos": 2, "retained_at_sec": 0},
        {"topic": "r/b", "payload_id": 11, "qos": 1, "retained_at_sec": 0},
        {"topic": "x/c", "payload_id": 12, "qos": 0, "retained_at_sec": 0},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "subscribe", "client_id": "s",
         "filter": "r/+", "qos": 1},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    dels = sorted(actual["delivery_log.json"]["deliveries"], key=lambda d: d["topic"])
    assert [d["topic"] for d in dels] == ["r/a", "r/b"]
    assert dels[0]["recipients"][0]["delivered_qos"] == 1
    assert dels[1]["recipients"][0]["delivered_qos"] == 1


def test_hidden_dataset_retained_clear_via_qos_zero_payload_zero(tmp_path: Path) -> None:
    """Publishing with retain=true, qos=0, payload_id=0 clears any retained
    entry for that topic."""
    clients = {"clients": [
        {"id": "p", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": []}
    retained = {"retained": [
        {"topic": "r/keep", "payload_id": 7, "qos": 1, "retained_at_sec": 0},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "r/keep", "payload_id": 0, "qos": 0, "retain": True, "client_id": "p"},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["broker_state.json"] == expected["broker_state"]
    assert actual["broker_state.json"]["retained"] == [], (
        "retain+qos=0+payload_id=0 must clear the retained map for the topic"
    )


def test_hidden_dataset_retained_limit_warns_and_keeps(tmp_path: Path) -> None:
    """When the retained map is at policy.max_retained, a brand-new topic
    publish with retain=true emits W_RETAINED_LIMIT and is NOT stored,
    but in-place updates of an existing retained topic still succeed."""
    clients = {"clients": [
        {"id": "p", "persistent": False, "keep_alive_sec": 30},
    ]}
    subs = {"subscriptions": []}
    retained = {"retained": [
        {"topic": "r/a", "payload_id": 1, "qos": 0, "retained_at_sec": 0},
        {"topic": "r/b", "payload_id": 2, "qos": 0, "retained_at_sec": 0},
    ]}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "r/c", "payload_id": 3, "qos": 0, "retain": True, "client_id": "p"},
        {"seq": 1, "kind": "publish", "topic": "r/a", "payload_id": 99, "qos": 1, "retain": True, "client_id": "p"},
    ]}
    policy = _base_policy(max_retained=2)
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual == {
        "broker_state.json": expected["broker_state"],
        "delivery_log.json": expected["delivery_log"],
        "session_log.json":  expected["session_log"],
        "diagnostics.json":  expected["diagnostics"],
        "summary.json":      expected["summary"],
    }
    topics = sorted(r["topic"] for r in actual["broker_state.json"]["retained"])
    assert topics == ["r/a", "r/b"]
    a = next(r for r in actual["broker_state.json"]["retained"] if r["topic"] == "r/a")
    assert a["payload_id"] == 99 and a["qos"] == 1, (
        "in-place retained update must succeed even when the map is full"
    )


def test_hidden_dataset_persistent_resume_restores_subs(tmp_path: Path) -> None:
    """A clean_start=false connect on a persistent_sessions[id] entry
    restores its subscriptions and emits N_SESSION_RESUMED."""
    clients = {"clients": [
        {"id": "c", "persistent": True, "connected": False, "keep_alive_sec": 60},
    ]}
    subs = {"subscriptions": [
        {"client_id": "c", "filter": "saved/#", "qos": 2},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "connect", "id": "c",
         "clean_start": False, "keep_alive_sec": 60},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual == {
        "broker_state.json": expected["broker_state"],
        "delivery_log.json": expected["delivery_log"],
        "session_log.json":  expected["session_log"],
        "diagnostics.json":  expected["diagnostics"],
        "summary.json":      expected["summary"],
    }
    cl = next(c for c in actual["broker_state.json"]["clients"] if c["id"] == "c")
    assert cl["subscriptions"] == [{"filter": "saved/#", "qos": 2}]
    codes = [d["code"] for e in actual["diagnostics.json"]["events"]
             for d in e["diagnostics"]]
    assert codes == ["N_SESSION_RESUMED"]


def test_hidden_dataset_clean_start_drops_persistent(tmp_path: Path) -> None:
    """A clean_start=true connect on an existing persistent_sessions entry
    drops the saved subs and the new client is non-persistent."""
    clients = {"clients": [
        {"id": "c", "persistent": True, "connected": False, "keep_alive_sec": 60},
    ]}
    subs = {"subscriptions": [
        {"client_id": "c", "filter": "old/#", "qos": 2},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "connect", "id": "c",
         "clean_start": True, "keep_alive_sec": 30},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["broker_state.json"] == expected["broker_state"]
    cl = next(c for c in actual["broker_state.json"]["clients"] if c["id"] == "c")
    assert cl["persistent"] is False
    assert cl["subscriptions"] == []
    assert actual["broker_state.json"]["persistent_sessions"] == [], (
        "clean_start=true must drop any prior persistent_sessions[id]"
    )


def test_hidden_dataset_will_delivered_on_abrupt(tmp_path: Path) -> None:
    """An abrupt disconnect with a will publishes the will message and
    emits N_WILL_DELIVERED. A non-abrupt disconnect simply discards it."""
    clients = {"clients": [
        {"id": "p", "persistent": True, "keep_alive_sec": 60,
         "will": {"topic": "down/p", "payload_id": 5, "qos": 1, "retain": False}},
        {"id": "s", "persistent": False, "keep_alive_sec": 60},
    ]}
    subs = {"subscriptions": [
        {"client_id": "s", "filter": "down/+", "qos": 1},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "expire_keepalive", "id": "p"},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["delivery_log.json"] == expected["delivery_log"]
    rec = actual["delivery_log.json"]["deliveries"][0]["recipients"]
    assert rec == [{"client_id": "s", "delivered_qos": 1}]
    codes = [d["code"] for e in actual["diagnostics.json"]["events"]
             for d in e["diagnostics"]]
    assert "N_WILL_DELIVERED" in codes


def test_hidden_dataset_subscription_limit_blocks_new_keeps_existing(tmp_path: Path) -> None:
    """E_SUBSCRIPTION_LIMIT only fires when adding a brand-new filter would
    exceed the cap; a re-subscribe to an already-present filter mutates qos
    even when the cap is reached."""
    clients = {"clients": [
        {"id": "c", "persistent": False, "keep_alive_sec": 60},
    ]}
    subs = {"subscriptions": [
        {"client_id": "c", "filter": "a", "qos": 0},
        {"client_id": "c", "filter": "b", "qos": 0},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "subscribe", "client_id": "c", "filter": "c", "qos": 0},
        {"seq": 1, "kind": "subscribe", "client_id": "c", "filter": "a", "qos": 2},
    ]}
    policy = _base_policy(max_subscriptions_per_client=2)
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual["broker_state.json"] == expected["broker_state"]
    cl = next(c for c in actual["broker_state.json"]["clients"] if c["id"] == "c")
    by_filter = {sub["filter"]: sub["qos"] for sub in cl["subscriptions"]}
    assert by_filter == {"a": 2, "b": 0}, (
        "re-subscribe to existing filter must update qos even when at cap"
    )
    codes = [d["code"] for e in actual["diagnostics.json"]["events"]
             for d in e["diagnostics"]]
    assert codes == ["E_SUBSCRIPTION_LIMIT"]


def test_hidden_dataset_publish_invalid_topic_no_delivery(tmp_path: Path) -> None:
    """A publish to a topic containing a wildcard or empty levels must
    emit E_INVALID_TOPIC and produce zero delivery_log entries."""
    clients = {"clients": [
        {"id": "p", "persistent": False, "keep_alive_sec": 60},
        {"id": "s", "persistent": False, "keep_alive_sec": 60},
    ]}
    subs = {"subscriptions": [
        {"client_id": "s", "filter": "#", "qos": 0},
    ]}
    retained = {"retained": []}
    events = {"events": [
        {"seq": 0, "kind": "publish", "topic": "+/wild", "payload_id": 1, "qos": 0, "retain": False, "client_id": "p"},
        {"seq": 1, "kind": "publish", "topic": "/leading/slash", "payload_id": 2, "qos": 0, "retain": False, "client_id": "p"},
    ]}
    policy = _base_policy()
    actual   = _run_binary_on(tmp_path, clients, subs, retained, events, policy)
    expected = _ref_for(clients, subs, retained, events, policy)
    assert actual == {
        "broker_state.json": expected["broker_state"],
        "delivery_log.json": expected["delivery_log"],
        "session_log.json":  expected["session_log"],
        "diagnostics.json":  expected["diagnostics"],
        "summary.json":      expected["summary"],
    }
    assert actual["delivery_log.json"]["deliveries"] == []
    codes = sorted(d["code"] for e in actual["diagnostics.json"]["events"]
                   for d in e["diagnostics"])
    assert codes == ["E_INVALID_TOPIC", "E_INVALID_TOPIC"]


def test_hidden_dataset_determinism_two_runs_byte_identical(tmp_path: Path) -> None:
    """Two runs of the binary on the same /app/data inputs into different
    output directories must produce byte-identical files. Catches latent
    nondeterminism (hash-map iteration, address-dependent ordering, etc.)."""
    in_dir = tmp_path / "data"
    in_dir.mkdir()
    for src in (CLIENTS_PATH, SUBSCRIPTIONS_PATH, RETAINED_PATH,
                EVENTS_PATH, POLICY_PATH):
        shutil.copy2(src, in_dir / src.name)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    out_a.mkdir()
    out_b.mkdir()
    for out in (out_a, out_b):
        proc = subprocess.run(
            [str(BINARY_PATH), str(in_dir), str(out)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, (
            f"determinism run failed: rc={proc.returncode} stderr={proc.stderr!r}"
        )
    for fname in ("broker_state.json", "delivery_log.json",
                  "session_log.json", "diagnostics.json", "summary.json"):
        a = (out_a / fname).read_bytes()
        b = (out_b / fname).read_bytes()
        assert a == b, (
            f"determinism violated for {fname}: byte-by-byte differs across two runs"
        )


def _snapshot_dir_state(root: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    if not root.exists():
        return state
    for p in sorted(root.rglob("*")):
        if p.is_file():
            state[str(p.relative_to(root))] = sha256_of(p)
    return state


def test_app_data_unchanged_recursively_after_run(
    binary_run_outputs: dict[str, Any],
) -> None:
    """The instruction forbids modifying anything under /app/data/. Verify
    that after the binary runs (a) no file was added, (b) no file was
    removed, and (c) every file's sha256 is unchanged.
    """
    assert binary_run_outputs["returncode"] == 0
    after = _snapshot_dir_state(DATA_DIR)
    for path, expected in EXPECTED_INPUT_HASHES.items():
        assert path.exists(), f"input vanished after run: {path}"
        actual = sha256_of(path)
        assert actual == expected, (
            f"input file {path} was modified by the binary "
            f"(hash {actual} != pinned {expected})"
        )
    rel_inputs = {p.name for p in EXPECTED_INPUT_HASHES}
    spurious = sorted(rel_path for rel_path in after if rel_path not in rel_inputs)
    assert not spurious, (
        f"binary created unexpected files under /app/data: {spurious}; "
        "the binary must not write anything under /app/data"
    )


def test_binary_rejects_missing_input_directory(tmp_path: Path) -> None:
    """Passing a nonexistent input directory must yield non-zero exit."""
    missing_in = tmp_path / "does_not_exist"
    out_dir    = tmp_path / "out"
    out_dir.mkdir()
    proc = subprocess.run(
        [str(BINARY_PATH), str(missing_in), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        "binary should exit non-zero when the input directory does not exist; "
        f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def test_binary_rejects_missing_input_files(tmp_path: Path) -> None:
    """Empty input directory (no JSON files) must yield non-zero exit."""
    in_dir  = tmp_path / "data"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()
    proc = subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode != 0, (
        "binary should exit non-zero when input json files are missing; "
        f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
    )


def _try_run(tmp_path: Path, clients_text: str, subs_text: str,
             retained_text: str, events_text: str,
             policy_text: str) -> subprocess.CompletedProcess:
    in_dir  = tmp_path / "data"
    out_dir = tmp_path / "out"
    in_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (in_dir / "clients.json").write_text(clients_text, encoding="utf-8")
    (in_dir / "subscriptions.json").write_text(subs_text, encoding="utf-8")
    (in_dir / "retained.json").write_text(retained_text, encoding="utf-8")
    (in_dir / "events.json").write_text(events_text, encoding="utf-8")
    (in_dir / "policy.json").write_text(policy_text, encoding="utf-8")
    return subprocess.run(
        [str(BINARY_PATH), str(in_dir), str(out_dir)],
        capture_output=True, text=True, timeout=30,
    )


def test_binary_rejects_malformed_inputs(tmp_path: Path) -> None:
    """The binary must exit non-zero on a variety of malformed inputs
    rather than producing partial or junk outputs."""
    good_clients = json.dumps({"clients": [
        {"id": "c", "persistent": False, "keep_alive_sec": 30},
    ]})
    good_subs     = json.dumps({"subscriptions": []})
    good_retained = json.dumps({"retained": []})
    good_events   = json.dumps({"events": [
        {"seq": 0, "kind": "tick", "delta_sec": 1},
    ]})
    good_policy   = json.dumps({
        "now_sec": 0,
        "max_subscriptions_per_client": 4,
        "max_retained": 4,
    })
    cases: list[tuple[str, str, str, str, str, str]] = [
        ("garbage_clients_json",  "{not valid json",       good_subs,    good_retained, good_events, good_policy),
        ("garbage_subs_json",     good_clients, "{not valid json",       good_retained, good_events, good_policy),
        ("garbage_retained_json", good_clients, good_subs, "{not valid json",            good_events, good_policy),
        ("garbage_events_json",   good_clients, good_subs, good_retained, "{not valid json",          good_policy),
        ("garbage_policy_json",   good_clients, good_subs, good_retained, good_events,   "{not valid json"),
        ("missing_clients_key",   json.dumps({"not_clients_key": []}),
                                  good_subs,    good_retained, good_events, good_policy),
        ("missing_events_key",    good_clients, good_subs, good_retained,
                                  json.dumps({"evnts": []}), good_policy),
        ("client_missing_id",     json.dumps({"clients": [
            {"persistent": False, "keep_alive_sec": 30},
        ]}), good_subs, good_retained, good_events, good_policy),
        ("client_wrong_type",     json.dumps({"clients": [
            {"id": 7, "persistent": False, "keep_alive_sec": 30},
        ]}), good_subs, good_retained, good_events, good_policy),
        ("event_unknown_kind",    good_clients, good_subs, good_retained,
                                  json.dumps({"events": [
                                      {"seq": 0, "kind": "wat"},
                                  ]}), good_policy),
        ("event_seq_not_dense",   good_clients, good_subs, good_retained,
                                  json.dumps({"events": [
                                      {"seq": 1, "kind": "tick", "delta_sec": 0},
                                  ]}), good_policy),
        ("policy_missing_max_retained", good_clients, good_subs, good_retained,
                                  good_events,
                                  json.dumps({
                                      "now_sec": 0,
                                      "max_subscriptions_per_client": 4,
                                  })),
        ("subscription_unknown_client", good_clients,
                                  json.dumps({"subscriptions": [
                                      {"client_id": "ghost",
                                       "filter": "x", "qos": 0},
                                  ]}),
                                  good_retained, good_events, good_policy),
        ("disconnected_nonpersistent",  json.dumps({"clients": [
            {"id": "c", "persistent": False, "connected": False,
             "keep_alive_sec": 30},
        ]}), good_subs, good_retained, good_events, good_policy),
    ]
    failures: list[str] = []
    for label, clients, subs, retained, events, policy in cases:
        proc = _try_run(tmp_path / label, clients, subs, retained, events, policy)
        if proc.returncode == 0:
            failures.append(
                f"{label}: expected non-zero exit on malformed input; "
                f"got rc=0 stdout={proc.stdout!r} stderr={proc.stderr!r}"
            )
    assert not failures, "\n".join(failures)
