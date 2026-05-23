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
    path.write_text(canonical(obj), encoding="utf-8")



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

def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    events_doc = load_json(in_dir / "events.json")
    cfg = load_json(in_dir / "config.json")
    outputs = simulate(events_doc, cfg)
    write_canonical(out_dir / "cache_state.json", outputs["cache_state"])
    write_canonical(out_dir / "decisions.json", outputs["decisions"])
    write_canonical(out_dir / "event_audit.json", outputs["event_audit"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    write_canonical(out_dir / "violations.json", outputs["violations"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
