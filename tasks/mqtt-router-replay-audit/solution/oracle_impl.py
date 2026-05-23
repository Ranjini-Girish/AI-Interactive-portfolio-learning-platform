from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
import re

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')


def _load_diag_codes_from_docs(docs_path: Path) -> tuple[frozenset[str], dict[str, str]]:
    """Parse /app/docs/diagnostics.md for the canonical list of
    diagnostic codes and their severities. The single source of truth
    for codes is the docs, not this test file. Codes live in tables
    grouped under '## Error codes', '## Warning codes', and
    '## Note codes' section headings, with each code line shaped like:
        | `E_DUPLICATE_CONNECT` | <when text> | <extra fields> |
    """
    text = docs_path.read_text(encoding="utf-8")
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
            f"could not parse any diagnostic codes from {docs_path}; "
            "check the docs format"
        )
    return frozenset(codes), severity


SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}






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


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    docs = in_dir.parent / "docs" / "diagnostics.md"
    if not docs.is_file():
        docs = Path("/app/docs/diagnostics.md")
    global DIAG_SEVERITY, VALID_DIAG_CODES
    VALID_DIAG_CODES, DIAG_SEVERITY = _load_diag_codes_from_docs(docs)
    clients_doc = load_json(in_dir / "clients.json")
    subs_doc = load_json(in_dir / "subscriptions.json")
    retained_doc = load_json(in_dir / "retained.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(clients_doc, subs_doc, retained_doc, events_doc, policy_doc)
    write_canonical(out_dir / "broker_state.json", outputs["broker_state"])
    write_canonical(out_dir / "delivery_log.json", outputs["delivery_log"])
    write_canonical(out_dir / "session_log.json", outputs["session_log"])
    write_canonical(out_dir / "diagnostics.json", outputs["diagnostics"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
