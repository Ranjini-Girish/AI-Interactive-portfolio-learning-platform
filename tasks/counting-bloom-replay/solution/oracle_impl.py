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
FNV1A_A_OFFSET = 0xCBF29CE484222325

FNV1A_B_OFFSET = 0x84222325CBF29CE4

FNV1A_PRIME = 0x100000001B3

U64_MASK = (1 << 64) - 1

def _fnv1a_64(seed: int, key: str) -> int:
    h = seed
    for b in key.encode("utf-8"):
        h ^= b
        h = (h * FNV1A_PRIME) & U64_MASK
    return h


def positions(key: str, m: int, k: int) -> list[int]:
    h_a = _fnv1a_64(FNV1A_A_OFFSET, key)
    h_b = _fnv1a_64(FNV1A_B_OFFSET, key)
    return [(h_a + i * h_b) % m for i in range(k)]


def simulate(keys: list[str], events: list[dict], policy: dict) -> dict[str, Any]:
    m = policy["m"]
    k = policy["k"]
    counter_bits = policy["counter_bits"]
    saturation_action = policy["saturation_action"]
    remove_below_zero_action = policy["remove_below_zero_action"]

    counters = [0] * m
    multiset_count: dict[str, int] = {key: 0 for key in keys}

    stats = {
        "clamped_remove": 0,
        "clears": 0,
        "rejected_negative": 0,
        "rejected_saturate": 0,
        "resizes": 0,
        "successful_adds": 0,
        "successful_queries": 0,
        "successful_removes": 0,
    }

    queries: list[dict] = []
    event_log: list[dict] = []
    dumps: list[dict] = []
    fn_count = fp_count = tn_count = tp_count = 0
    queries_per_key: dict[str, int] = {}

    def saturate_max() -> int:
        return (1 << counter_bits) - 1

    def do_add(key: str) -> str:
        nonlocal counters
        positions_for_key = positions(key, m, k)
        max_v = saturate_max()
        if saturation_action == "reject":
            if any(counters[p] == max_v for p in positions_for_key):
                stats["rejected_saturate"] += 1
                return "D_REJECTED_SATURATE"
            for p in positions_for_key:
                counters[p] += 1
            multiset_count[key] = multiset_count.get(key, 0) + 1
            stats["successful_adds"] += 1
            return "D_OK_ADD"
        else:
            for p in positions_for_key:
                if counters[p] < max_v:
                    counters[p] += 1
            multiset_count[key] = multiset_count.get(key, 0) + 1
            stats["successful_adds"] += 1
            return "D_OK_ADD"

    def do_remove(key: str) -> str:
        nonlocal counters
        positions_for_key = positions(key, m, k)
        if remove_below_zero_action == "reject":
            if any(counters[p] == 0 for p in positions_for_key):
                stats["rejected_negative"] += 1
                return "D_REJECTED_NEGATIVE"
            for p in positions_for_key:
                counters[p] -= 1
            if multiset_count.get(key, 0) > 0:
                multiset_count[key] -= 1
            stats["successful_removes"] += 1
            return "D_OK_REMOVE"
        else:
            any_clamp = any(counters[p] == 0 for p in positions_for_key)
            for p in positions_for_key:
                if counters[p] > 0:
                    counters[p] -= 1
            if multiset_count.get(key, 0) > 0:
                multiset_count[key] -= 1
            if any_clamp:
                stats["clamped_remove"] += 1
                return "D_CLAMPED_REMOVE"
            stats["successful_removes"] += 1
            return "D_OK_REMOVE"

    def do_query(seq: int, key: str) -> None:
        nonlocal fn_count, fp_count, tn_count, tp_count
        positions_for_key = positions(key, m, k)
        predicted = all(counters[p] > 0 for p in positions_for_key)
        actual = multiset_count.get(key, 0) > 0
        if predicted and actual:
            outcome = "tp"
            tp_count += 1
        elif predicted and not actual:
            outcome = "fp"
            fp_count += 1
        elif not predicted and not actual:
            outcome = "tn"
            tn_count += 1
        else:
            outcome = "fn"
            fn_count += 1
        queries.append({
            "actual": actual,
            "key": key,
            "outcome": outcome,
            "predicted": predicted,
            "seq": seq,
        })
        stats["successful_queries"] += 1
        queries_per_key[key] = queries_per_key.get(key, 0) + 1

    def do_clear() -> None:
        nonlocal counters
        counters = [0] * m
        for kk in list(multiset_count.keys()):
            multiset_count[kk] = 0
        stats["clears"] += 1

    def do_resize(new_m: int, new_k: int) -> None:
        nonlocal counters, m, k
        old_multiset = dict(multiset_count)
        m = new_m
        k = new_k
        counters = [0] * m
        for kk in list(multiset_count.keys()):
            multiset_count[kk] = 0
        for key in keys:
            n = old_multiset.get(key, 0)
            for _ in range(n):
                do_add(key)
        stats["resizes"] += 1

    def do_dump_stats(seq: int) -> None:
        max_v = saturate_max()
        non_zero = sum(1 for c in counters if c > 0)
        sat = sum(1 for c in counters if c == max_v)
        total = sum(counters)
        dumps.append({
            "counter_bits": counter_bits,
            "k": k,
            "m": m,
            "non_zero_slots": non_zero,
            "saturated_slots": sat,
            "seq": seq,
            "stats": dict(stats),
            "total_count": total,
        })

    for ev in events:
        seq = ev["seq"]
        op = ev["op"]
        if op == "add":
            key = keys[ev["key_idx"]]
            code = do_add(key)
            event_log.append({"code": code, "key": key, "op": op, "seq": seq})
        elif op == "remove":
            key = keys[ev["key_idx"]]
            code = do_remove(key)
            event_log.append({"code": code, "key": key, "op": op, "seq": seq})
        elif op == "query":
            key = keys[ev["key_idx"]]
            do_query(seq, key)
            event_log.append({"code": "D_OK_QUERY", "key": key, "op": op, "seq": seq})
        elif op == "clear":
            do_clear()
            event_log.append({"code": "D_OK_CLEAR", "key": None, "op": op, "seq": seq})
        elif op == "resize":
            do_resize(ev["new_m"], ev["new_k"])
            event_log.append({"code": "D_OK_RESIZE", "key": None, "op": op, "seq": seq})
        elif op == "dump_stats":
            do_dump_stats(seq)
            event_log.append({"code": "D_OK_DUMP", "key": None, "op": op, "seq": seq})
        else:
            raise ValueError(f"unknown op: {op}")

    filter_state = {
        "counter_bits": counter_bits,
        "counters": counters,
        "k": k,
        "m": m,
        "stats": dict(stats),
    }
    query_log = {"queries": queries}
    event_log_obj = {"events": event_log}
    stats_dumps = {"dumps": dumps}

    hot_keys = sorted(
        ({"key": kk, "queries": v} for kk, v in queries_per_key.items()),
        key=lambda d: (-d["queries"], d["key"]),
    )

    summary = {
        "clamped_remove": stats["clamped_remove"],
        "clears": stats["clears"],
        "dumps_total": len(dumps),
        "events_total": len(events),
        "fn_count": fn_count,
        "fp_count": fp_count,
        "hot_keys": hot_keys,
        "queries_total": len(queries),
        "rejected_negative": stats["rejected_negative"],
        "rejected_saturate": stats["rejected_saturate"],
        "resizes": stats["resizes"],
        "successful_adds": stats["successful_adds"],
        "successful_queries": stats["successful_queries"],
        "successful_removes": stats["successful_removes"],
        "tn_count": tn_count,
        "tp_count": tp_count,
    }

    return {
        "filter_state": filter_state,
        "query_log": query_log,
        "event_log": event_log_obj,
        "stats_dumps": stats_dumps,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    keys_doc = load_json(in_dir / "keys.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    keys = keys_doc["keys"] if isinstance(keys_doc, dict) else keys_doc
    events = events_doc["events"] if isinstance(events_doc, dict) else events_doc
    outputs = simulate(keys, events, policy_doc)
    write_canonical(out_dir / "filter_state.json", outputs["filter_state"])
    write_canonical(out_dir / "query_log.json", outputs["query_log"])
    write_canonical(out_dir / "event_log.json", outputs["event_log"])
    write_canonical(out_dir / "stats_dumps.json", outputs["stats_dumps"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
