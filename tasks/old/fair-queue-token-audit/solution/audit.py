"""Fair queue token laboratory audit."""

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
    data_dir = Path(os.environ.get("FQT_DATA_DIR", "/app/fqt_lab"))
    audit_dir = Path(os.environ.get("FQT_AUDIT_DIR", "/app/audit"))
    run(data_dir, audit_dir)


def run(data_dir: Path, audit_dir: Path) -> None:
    policy = _load(data_dir / "policy.json")
    pool = _load(data_dir / "pool_state.json")
    incidents = _load(data_dir / "incident_log.json")
    window = _load(data_dir / "anchors" / "window.json")
    meta = _load(data_dir / "ancillary" / "meta.json")

    active = [str(q) for q in policy["active_queues"]]
    active_set = set(active)
    weights = {str(q): int(policy["queues"][q]["w"]) for q in policy["queues"]}
    slice_max = int(policy["slice_max"])
    max_cycles = int(policy["max_cycles"])

    jobs: list[dict[str, Any]] = []
    for i in range(18):
        jobs.append(_load(data_dir / "jobs" / f"job_{i:02d}.json"))

    working = [
        {"demand": int(j["demand"]), "id": str(j["id"]), "queue": str(j["queue"]), "stamp": int(j["stamp"])}
        for j in jobs
        if str(j["queue"]) in active_set
    ]

    events = list(incidents.get("events", []))
    applied = 0
    for ev in events:
        applied += 1
        kind = str(ev.get("kind", ""))
        if kind == "boost_weight":
            q = str(ev["queue"])
            add = int(ev["add"])
            if q in weights:
                weights[q] = max(1, weights[q] + add)
        elif kind == "freeze_queue":
            q = str(ev["queue"])
            working = [j for j in working if str(j["queue"]) != q]

    deficits = {q: 0 for q in sorted(active_set)}
    tokens = int(pool["token_budget"])
    slices: list[dict[str, Any]] = []

    for cycle in range(1, max_cycles + 1):
        for q in sorted(active_set):
            deficits[q] += weights[q]

        candidates = [
            q
            for q in active_set
            if any(int(j["demand"]) > 0 and str(j["queue"]) == q for j in working)
        ]
        if not candidates or tokens == 0:
            break

        best = max(deficits[q] for q in candidates)
        focus = [q for q in candidates if deficits[q] == best]
        q_star = min(focus)

        pool_jobs = [j for j in working if str(j["queue"]) == q_star and int(j["demand"]) > 0]
        pool_jobs.sort(key=lambda j: (int(j["stamp"]), str(j["id"])))
        job = pool_jobs[0]

        serve = min(slice_max, int(job["demand"]), tokens)
        if serve == 0:
            break

        slices.append(
            {
                "cycle": cycle,
                "job_id": str(job["id"]),
                "queue": q_star,
                "served": serve,
            }
        )
        job["demand"] = int(job["demand"]) - serve
        tokens -= serve
        deficits[q_star] -= serve

    high = window.get("high_mark", 0)
    if not isinstance(high, int):
        high = 0
    label = str(meta["label"]) if isinstance(meta.get("label"), str) else ""
    score = max(0, len(slices) - int(high))

    summary = {
        "applied_events": applied,
        "label": label,
        "score": score,
        "slices_emitted": len(slices),
        "token_remaining": tokens,
    }
    trace = {"slices": slices}
    _dump(audit_dir / "serve_trace.json", trace)
    _dump(audit_dir / "summary.json", summary)


if __name__ == "__main__":
    main()
