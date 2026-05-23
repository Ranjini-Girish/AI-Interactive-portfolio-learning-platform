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
    for codes is the docs, not this test file. Lines look like:
        | E_DUPLICATE_ID | error | yes ...
    """
    text = docs_path.read_text(encoding="utf-8")
    codes: set[str] = set()
    severity: dict[str, str] = {}
    pat = re.compile(
        r"^\s*\|\s*`?(?P<code>[A-Z][A-Z0-9_]+)`?\s*\|\s*"
        r"(?P<severity>error|warning|note)\s*\|"
    )
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            codes.add(m.group("code"))
            severity[m.group("code")] = m.group("severity")
    if not codes:
        raise RuntimeError(
            f"could not parse any diagnostic codes from {docs_path}; "
            "check the docs format"
        )
    return frozenset(codes), severity


SEVERITY_RANK = {"error": 0, "warning": 1, "note": 2}

BUCKET_SIZE = {
    "keep_hourly":  3600,
    "keep_daily":   86400,
    "keep_weekly":  604800,
    "keep_monthly": 2592000,
}






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


def _emit(diags, seq, code, snapshot_id):
    diags.setdefault(seq, []).append({
        "code": code,
        "severity": DIAG_SEVERITY[code],
        "snapshot_id": snapshot_id,
    })


def _resolve_rules(policy, dataset):
    return policy.get("datasets", {}).get(dataset, policy["default_rules"])


def _rules_all_zero(rules):
    return all(int(rules.get(k, 0)) == 0 for k in
               ("keep_last_n", "keep_hourly", "keep_daily",
                "keep_weekly", "keep_monthly"))


def run_simulation(initial_snapshots, events, policy):
    state: dict[str, dict[str, Any]] = {}
    name_idx: dict[tuple[str, str], str] = {}
    for s in initial_snapshots:
        sid = s["id"]
        if sid in state:
            raise ValueError(f"duplicate id in initial snapshots: {sid}")
        key = (s["dataset"], s["name"])
        if key in name_idx:
            raise ValueError(f"duplicate (dataset,name) in initial: {key}")
        state[sid] = {
            "id": sid,
            "dataset": s["dataset"],
            "name": s["name"],
            "created_at_sec": int(s["created_at_sec"]),
            "holders": list(s.get("holders", [])),
        }
        name_idx[key] = sid

    now_sec = int(policy["now_sec"])
    held_action_default = policy["held_delete_action"]
    diags: dict[int, list[dict[str, Any]]] = {}
    prune_runs: list[dict[str, Any]] = []
    counters = {
        "snapshots_created": 0,
        "snapshots_deleted_explicitly": 0,
        "snapshots_pruned_by_retention": 0,
        "retention_runs_executed": 0,
    }

    events = sorted(events, key=lambda e: e["seq"])
    for i, ev in enumerate(events):
        if ev["seq"] != i:
            raise ValueError(
                f"events.json: seq must be dense 0..N-1; got {ev['seq']} at index {i}"
            )

    for ev in events:
        seq = ev["seq"]
        kind = ev["kind"]

        if kind == "snapshot_create":
            sid = ev["id"]
            ds  = ev["dataset"]
            nm  = ev["name"]
            if sid in state:
                _emit(diags, seq, "E_DUPLICATE_ID", sid)
                continue
            if (ds, nm) in name_idx:
                _emit(diags, seq, "E_DUPLICATE_NAME", sid)
                continue
            state[sid] = {
                "id": sid, "dataset": ds, "name": nm,
                "created_at_sec": now_sec, "holders": [],
            }
            name_idx[(ds, nm)] = sid
            counters["snapshots_created"] += 1
            continue

        if kind == "snapshot_delete":
            sid = ev["id"]
            force = bool(ev["force"])
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            snap = state[sid]
            if snap["holders"]:
                effective = "break_holds" if force else held_action_default
                if effective == "reject":
                    _emit(diags, seq, "E_HOLD_PREVENTS_DELETE", sid)
                    continue
                if effective == "skip":
                    _emit(diags, seq, "W_SKIP_HELD", sid)
                    continue
                _emit(diags, seq, "W_BREAK_HOLDS", sid)
            del name_idx[(snap["dataset"], snap["name"])]
            del state[sid]
            counters["snapshots_deleted_explicitly"] += 1
            continue

        if kind == "hold_add":
            sid = ev["id"]
            holder = ev["holder"]
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            if holder in state[sid]["holders"]:
                _emit(diags, seq, "W_HOLD_ALREADY_PRESENT", sid)
                continue
            state[sid]["holders"].append(holder)
            continue

        if kind == "hold_release":
            sid = ev["id"]
            holder = ev["holder"]
            if sid not in state:
                _emit(diags, seq, "E_SNAPSHOT_NOT_FOUND", sid)
                continue
            if holder not in state[sid]["holders"]:
                _emit(diags, seq, "W_HOLD_NOT_PRESENT", sid)
                continue
            state[sid]["holders"].remove(holder)
            continue

        if kind == "tick":
            d = int(ev["delta_sec"])
            if d < 0:
                _emit(diags, seq, "E_TICK_NEGATIVE", None)
                continue
            if d == 0:
                _emit(diags, seq, "W_TICK_ZERO", None)
                continue
            now_sec += d
            continue

        if kind == "retention_run":
            ds = ev["dataset"]
            rules = _resolve_rules(policy, ds)
            counters["retention_runs_executed"] += 1
            in_ds = sorted(
                [(sid, state[sid]) for sid in state if state[sid]["dataset"] == ds],
                key=lambda x: x[0],
            )
            if _rules_all_zero(rules):
                _emit(diags, seq, "W_NO_RULES_DEFINED", None)
            if not in_ds:
                _emit(diags, seq, "W_DATASET_EMPTY", None)
                prune_runs.append({
                    "dataset": ds, "kept": [], "pruned": [], "seq": seq,
                })
                continue
            keep_by: dict[str, set[str]] = {sid: set() for sid, _ in in_ds}

            n_last = int(rules.get("keep_last_n", 0))
            if n_last > 0:
                ranked = sorted(
                    in_ds,
                    key=lambda x: (x[1]["created_at_sec"], x[0]),
                    reverse=True,
                )
                for sid, _ in ranked[:n_last]:
                    keep_by[sid].add("keep_last_n")

            for rule in ("keep_hourly", "keep_daily", "keep_weekly", "keep_monthly"):
                n = int(rules.get(rule, 0))
                if n <= 0:
                    continue
                bsize = BUCKET_SIZE[rule]
                buckets: dict[int, list] = {}
                for sid, snap in in_ds:
                    bnum = snap["created_at_sec"] // bsize
                    buckets.setdefault(bnum, []).append((sid, snap))
                ordered_buckets = sorted(buckets.keys(), reverse=True)[:n]
                for bnum in ordered_buckets:
                    members = buckets[bnum]
                    chosen = sorted(
                        members,
                        key=lambda x: (x[1]["created_at_sec"], x[0]),
                        reverse=True,
                    )[0]
                    keep_by[chosen[0]].add(rule)

            for sid, snap in in_ds:
                if snap["holders"]:
                    keep_by[sid].add("held")

            kept_ids   = sorted([sid for sid in keep_by if keep_by[sid]])
            pruned_ids = sorted([sid for sid in keep_by if not keep_by[sid]])

            kept_entries = []
            for sid in kept_ids:
                snap = state[sid]
                kept_entries.append({
                    "id": sid,
                    "kept_by": sorted(keep_by[sid]),
                    "name": snap["name"],
                })
            kept_entries.sort(
                key=lambda e: (state[e["id"]]["created_at_sec"], e["id"]),
                reverse=True,
            )
            pruned_entries = [{"id": sid, "name": state[sid]["name"]} for sid in pruned_ids]

            prune_runs.append({
                "dataset": ds,
                "kept": kept_entries,
                "pruned": pruned_entries,
                "seq": seq,
            })
            for sid in pruned_ids:
                snap = state[sid]
                del name_idx[(snap["dataset"], snap["name"])]
                del state[sid]
                counters["snapshots_pruned_by_retention"] += 1
            continue

        raise ValueError(f"unknown event kind: {kind}")

    return _build_outputs(state, diags, prune_runs, counters, len(events))


def _build_outputs(state, diags, prune_runs, counters, total_events):
    by_ds: dict[str, list] = {}
    for sid, snap in state.items():
        by_ds.setdefault(snap["dataset"], []).append((sid, snap))
    datasets_arr = []
    for ds in sorted(by_ds):
        snaps = sorted(by_ds[ds], key=lambda x: (x[1]["created_at_sec"], x[0]))
        snap_arr = []
        for sid, snap in snaps:
            snap_arr.append({
                "created_at_sec": snap["created_at_sec"],
                "holders": sorted(snap["holders"]),
                "id": sid,
                "name": snap["name"],
            })
        datasets_arr.append({"name": ds, "snapshots": snap_arr})
    snapshot_state = {"datasets": datasets_arr}

    prune_log = {"runs": prune_runs}

    diag_events = []
    for seq in sorted(diags):
        items_sorted = sorted(diags[seq], key=lambda d: (
            SEVERITY_RANK[d["severity"]],
            d["code"],
            "" if d["snapshot_id"] is None else "1" + d["snapshot_id"],
        ))
        diag_events.append({"diagnostics": items_sorted, "seq": seq})
    diagnostics_doc = {"events": diag_events}

    summary = {
        "datasets_with_snapshots": sorted(by_ds.keys()),
        "events_with_diagnostics": len(diag_events),
        "final_snapshot_count": len(state),
        "retention_runs_executed":      counters["retention_runs_executed"],
        "snapshots_created":            counters["snapshots_created"],
        "snapshots_deleted_explicitly": counters["snapshots_deleted_explicitly"],
        "snapshots_pruned_by_retention": counters["snapshots_pruned_by_retention"],
        "total_events": total_events,
    }

    return {
        "snapshot_state":         snapshot_state,
        "prune_log":              prune_log,
        "retention_diagnostics":  diagnostics_doc,
        "summary":                summary,
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
    snaps_doc = load_json(in_dir / "snapshots.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(snaps_doc["snapshots"], events_doc["events"], policy_doc)
    write_canonical(out_dir / "snapshot_state.json", outputs["snapshot_state"])
    write_canonical(out_dir / "prune_log.json", outputs["prune_log"])
    write_canonical(out_dir / "retention_diagnostics.json", outputs["retention_diagnostics"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
