from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')
VALID_DECISIONS = {
    "accept", "accept_passive",
    "replay_logged", "replay_dropped",
    "too_old_logged", "too_old_dropped",
    "unknown_drop",
}

REPLAY_LOG_DECISIONS = {
    "replay_logged", "replay_dropped",
    "too_old_logged", "too_old_dropped",
    "unknown_drop",
}

def _encode_bitmap(bitmap_int: int, window_size: int) -> str:
    nbytes = (window_size + 7) // 8
    out = []
    for i in range(nbytes):
        b = (bitmap_int >> (8 * i)) & 0xFF
        out.append(f"{b:02x}")
    return "".join(out)


def _shift_bitmap(bitmap_int: int, shift: int, window_size: int) -> int:
    new = (bitmap_int << shift) | 1
    return new & ((1 << window_size) - 1)


def run_simulation(initial_sas, events, policy):
    sas: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    counters: dict[str, dict[str, int]] = {}
    decisions: list[dict[str, Any]] = []

    def init_counters(sa_id: str):
        if sa_id not in counters:
            counters[sa_id] = {
                "accepted": 0, "recv_total": 0,
                "replays": 0, "too_old": 0, "rekeys": 0,
            }

    for s in initial_sas:
        sa_id = s["id"]
        sas[sa_id] = {"id": sa_id, "top": s["top"],
                      "window_size": s["window_size"],
                      "owner": s["owner"], "bitmap": 0}
        seen_ids.add(sa_id)
        init_counters(sa_id)

    add_sa_failures = 0
    rekey_failures = 0
    rekey_successes = 0
    drop_unknown_sa = 0
    passive_created_count = 0
    replays_total = 0
    too_old_total = 0

    allowed_windows = list(policy["window_sizes_allowed"])
    allowed_set = set(allowed_windows)

    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "add_sa":
            sa_id = ev["sa_id"]
            top = ev["top"]
            window_size = ev["window_size"]
            owner = ev["owner"]
            if sa_id in seen_ids:
                add_sa_failures += 1
                continue
            if window_size not in allowed_set:
                add_sa_failures += 1
                continue
            if top < 0:
                add_sa_failures += 1
                continue
            sas[sa_id] = {"id": sa_id, "top": top, "window_size": window_size,
                          "owner": owner, "bitmap": 0}
            seen_ids.add(sa_id)
            init_counters(sa_id)
            continue
        if op == "delete_sa":
            sa_id = ev["sa_id"]
            if sa_id not in sas:
                continue
            del sas[sa_id]
            continue
        if op == "rekey":
            sa_id = ev["sa_id"]
            window_size = ev["window_size"]
            if sa_id not in sas:
                rekey_failures += 1
                continue
            if window_size not in allowed_set:
                rekey_failures += 1
                continue
            sa = sas[sa_id]
            sa["top"] = 0
            sa["bitmap"] = 0
            sa["window_size"] = window_size
            counters[sa_id]["rekeys"] += 1
            rekey_successes += 1
            continue
        if op == "recv":
            sa_id = ev["sa_id"]
            esp_seq = ev["esp_seq"]
            passive_created = False
            if sa_id not in sas:
                if policy["on_unknown_sa"] == "drop":
                    drop_unknown_sa += 1
                    decisions.append({
                        "decision": "unknown_drop",
                        "diagnostic": "E_UNKNOWN_SA",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                    continue
                w0 = allowed_windows[0]
                sas[sa_id] = {"id": sa_id, "top": 0, "window_size": w0,
                              "owner": "passive", "bitmap": 0}
                seen_ids.add(sa_id)
                init_counters(sa_id)
                passive_created = True
                passive_created_count += 1
            sa = sas[sa_id]
            top = sa["top"]
            ws = sa["window_size"]
            bitmap = sa["bitmap"]
            counters[sa_id]["recv_total"] += 1
            if esp_seq > top:
                shift = esp_seq - top
                sa["bitmap"] = _shift_bitmap(bitmap, shift, ws)
                sa["top"] = esp_seq
                counters[sa_id]["accepted"] += 1
                if passive_created:
                    decisions.append({
                        "decision": "accept_passive",
                        "diagnostic": "N_PASSIVE_CREATED",
                        "esp_seq": esp_seq,
                        "passive_created": True,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    decisions.append({
                        "decision": "accept",
                        "diagnostic": None,
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            if esp_seq == top:
                replays_total += 1
                counters[sa_id]["replays"] += 1
                if policy["on_replay"] == "drop":
                    decisions.append({
                        "decision": "replay_dropped",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "replay_logged",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            offset = top - esp_seq
            if offset >= ws:
                too_old_total += 1
                counters[sa_id]["too_old"] += 1
                if policy["on_too_old"] == "drop":
                    decisions.append({
                        "decision": "too_old_dropped",
                        "diagnostic": "W_TOO_OLD",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "too_old_logged",
                        "diagnostic": "W_TOO_OLD",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            bit = (bitmap >> offset) & 1
            if bit == 1:
                replays_total += 1
                counters[sa_id]["replays"] += 1
                if policy["on_replay"] == "drop":
                    decisions.append({
                        "decision": "replay_dropped",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                else:
                    counters[sa_id]["accepted"] += 1
                    decisions.append({
                        "decision": "replay_logged",
                        "diagnostic": "W_REPLAY",
                        "esp_seq": esp_seq,
                        "passive_created": False,
                        "sa_id": sa_id,
                        "seq": seq,
                    })
                continue
            sa["bitmap"] = bitmap | (1 << offset)
            counters[sa_id]["accepted"] += 1
            decisions.append({
                "decision": "accept",
                "diagnostic": None,
                "esp_seq": esp_seq,
                "passive_created": False,
                "sa_id": sa_id,
                "seq": seq,
            })

    sa_state_arr = []
    for sa_id in sorted(sas):
        sa = sas[sa_id]
        c = counters[sa_id]
        sa_state_arr.append({
            "accepted":    c["accepted"],
            "bitmap":      _encode_bitmap(sa["bitmap"], sa["window_size"]),
            "id":          sa_id,
            "owner":       sa["owner"],
            "recv_total":  c["recv_total"],
            "rekeys":      c["rekeys"],
            "replays":     c["replays"],
            "too_old":     c["too_old"],
            "top":         sa["top"],
            "window_size": sa["window_size"],
        })

    accepted_total = sum(c["accepted"] for c in counters.values())

    hot = []
    for sa_id in sorted(counters):
        c = counters[sa_id]
        s = c["replays"] + c["too_old"]
        if s > 0 and s >= policy["min_hot_threshold"]:
            hot.append({"id": sa_id, "replays": c["replays"],
                        "too_old": c["too_old"]})
    hot.sort(key=lambda h: (-(h["replays"] + h["too_old"]), h["id"]))

    summary = {
        "accepted_total":        accepted_total,
        "active_sa_count":       len(sas),
        "add_sa_failures":       add_sa_failures,
        "drop_unknown_sa":       drop_unknown_sa,
        "hot_sas":               hot,
        "passive_created_count": passive_created_count,
        "policy_on_replay":      policy["on_replay"],
        "policy_on_too_old":     policy["on_too_old"],
        "policy_on_unknown_sa":  policy["on_unknown_sa"],
        "rekey_failures":        rekey_failures,
        "rekey_successes":       rekey_successes,
        "replays_total":         replays_total,
        "too_old_total":         too_old_total,
        "total_events":          len(events),
    }

    replay_log = []
    for d in decisions:
        if d["decision"] in REPLAY_LOG_DECISIONS:
            replay_log.append({
                "decision":   d["decision"],
                "diagnostic": d["diagnostic"],
                "esp_seq":    d["esp_seq"],
                "sa_id":      d["sa_id"],
                "seq":        d["seq"],
            })

    return {
        "sa_state":         {"sas": sa_state_arr},
        "packet_decisions": {"decisions": decisions},
        "replay_log":       {"entries": replay_log},
        "summary":          summary,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    sas_doc = load_json(in_dir / "sas.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(sas_doc["sas"], events_doc["events"], policy_doc)
    write_canonical(out_dir / "sa_state.json", outputs["sa_state"])
    write_canonical(out_dir / "packet_decisions.json", outputs["packet_decisions"])
    write_canonical(out_dir / "replay_log.json", outputs["replay_log"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
