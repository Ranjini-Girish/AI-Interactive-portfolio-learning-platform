"""Journal extent merge laboratory audit."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, sort_keys=True, indent=2, separators=(", ", ": ")) + "\n"
    path.write_text(txt, encoding="utf-8")


def main() -> None:
    data_dir = Path(os.environ.get("JEM_DATA_DIR", "/app/jem_lab"))
    audit_dir = Path(os.environ.get("JEM_AUDIT_DIR", "/app/audit"))
    run(data_dir, audit_dir)


def run(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    guard_path = data_dir / "anchors" / "guard.json"
    guard = _load(guard_path) if guard_path.is_file() else {}
    notes_path = data_dir / "ancillary" / "notes.json"
    notes = _load(notes_path) if notes_path.is_file() else {}

    active = sorted({str(v) for v in policy["active_volumes"]})
    active_set = set(active)
    vol_cfg = {str(k): v for k, v in policy["volumes"].items()}

    extents: list[dict[str, Any]] = []
    for i in range(18):
        extents.append(_load(data_dir / "extents" / f"ext_{i:02d}.json"))

    cur_ext = [e for e in extents if str(e["vol"]) in active_set]

    events = list(incidents.get("events", []))
    applied = 0
    for ev in events:
        applied += 1
        kind = str(ev.get("kind", ""))
        if kind == "delete_extent":
            eid = str(ev["id"])
            cur_ext = [e for e in cur_ext if str(e["id"]) != eid]
        elif kind == "shrink_end":
            eid = str(ev["id"])
            new_end = int(ev["new_end"])
            nxt: list[dict[str, Any]] = []
            for e in cur_ext:
                if str(e["id"]) != eid:
                    nxt.append(e)
                    continue
                e2 = dict(e)
                e2["end"] = new_end
                if new_end <= int(e2["start"]):
                    continue
                nxt.append(e2)
            cur_ext = nxt

    by_vol: dict[str, list[dict[str, Any]]] = {v: [] for v in active}
    for e in cur_ext:
        by_vol[str(e["vol"])].append(e)

    watch = [str(x) for x in guard.get("watch", [])]
    watch_set = set(watch)

    merged_by_vol: dict[str, list[dict[str, Any]]] = {}
    merged_total = 0
    watch_hits = 0

    for vol in active:
        gap = int(vol_cfg[vol]["gap_merge_max"])
        ceiling = int(vol_cfg[vol]["byte_ceiling"])
        rows = sorted(by_vol[vol], key=lambda r: (int(r["start"]), str(r["id"])))
        out_rows: list[dict[str, Any]] = []
        if not rows:
            merged_by_vol[vol] = out_rows
            continue

        cur = {
            "bytes": int(rows[0]["bytes"]),
            "end": int(rows[0]["end"]),
            "id": str(rows[0]["id"]),
            "start": int(rows[0]["start"]),
        }
        absorbed = {str(rows[0]["id"])}

        def flush() -> None:
            nonlocal merged_total, watch_hits
            capped = cur["bytes"] > ceiling
            b = min(int(cur["bytes"]), ceiling) if capped else int(cur["bytes"])
            out_rows.append(
                {
                    "bytes": b,
                    "capped": bool(capped),
                    "end": int(cur["end"]),
                    "id": str(cur["id"]),
                    "start": int(cur["start"]),
                }
            )
            merged_total += 1
            if str(cur["id"]) in watch_set or bool(absorbed & watch_set):
                watch_hits += 1

        for nxt in rows[1:]:
            if int(nxt["start"]) - int(cur["end"]) <= gap:
                cur["end"] = max(int(cur["end"]), int(nxt["end"]))
                cur["bytes"] += int(nxt["bytes"])
                nid = str(nxt["id"])
                if nid < cur["id"]:
                    cur["id"] = nid
                absorbed.add(nid)
            else:
                flush()
                cur = {
                    "bytes": int(nxt["bytes"]),
                    "end": int(nxt["end"]),
                    "id": str(nxt["id"]),
                    "start": int(nxt["start"]),
                }
                absorbed = {str(nxt["id"])}
        flush()
        merged_by_vol[vol] = out_rows

    tag = str(notes["tag"]) if isinstance(notes.get("tag"), str) else ""
    summary = {
        "applied_events": applied,
        "journal_seq": int(pool["journal_seq"]),
        "merged_extent_count": merged_total,
        "tag": tag,
        "watch_hits": watch_hits,
    }
    merged = {"volumes": {k: merged_by_vol[k] for k in sorted(merged_by_vol.keys())}}
    _dump(audit_dir / "merged_extents.json", merged)
    _dump(audit_dir / "summary.json", summary)


if __name__ == "__main__":
    main()
