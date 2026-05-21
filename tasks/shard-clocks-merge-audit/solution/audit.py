from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> None:
    data = Path(os.environ.get("SCM_DATA_DIR", "/app/clk_lat"))
    out = Path(os.environ.get("SCM_AUDIT_DIR", "/app/audit"))
    out.mkdir(parents=True, exist_ok=True)

    policy = json.loads((data / "policy.json").read_text(encoding="utf-8"))
    pool = json.loads((data / "pool_state.json").read_text(encoding="utf-8"))
    incidents = json.loads((data / "incidents.json").read_text(encoding="utf-8"))["incidents"]

    segments = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((data / "segments").glob("*.json"))]
    segments.sort(key=lambda s: str(s["id"]))
    by_id = {str(s["id"]): s for s in segments}

    horizon = int(policy["horizon_day"])
    baseline_id = str(policy["baseline_id"])
    penalty = int(policy["penalty_ms"])
    bonus_map = {str(k): int(v) for k, v in pool["bonus_ms"].items()}

    untrusted: set[str] = set()
    frozen_flag: dict[str, bool] = {}
    for event in sorted(incidents, key=lambda e: (int(e["day"]), str(e["id"]))):
        if not event.get("accepted"):
            continue
        if int(event["day"]) > horizon:
            continue
        kind = str(event["kind"])
        target = str(event["target"])
        if kind == "falseticker":
            untrusted.add(target)
        elif kind == "hold":
            frozen_flag[target] = True
        elif kind == "lift_hold":
            frozen_flag[target] = False

    baseline_skew = int(by_id[baseline_id]["skew_ms"])

    rows: list[dict[str, object]] = []
    for seg in segments:
        sid = str(seg["id"])
        raw = int(seg["skew_ms"])
        is_frozen = bool(frozen_flag.get(sid, False))
        if is_frozen:
            bonus_skew = raw
        else:
            bonus_skew = raw + int(bonus_map.get(sid, 0))
        trusted = bool(seg.get("trusted_default", True)) and sid not in untrusted
        if trusted:
            adjusted = bonus_skew - baseline_skew
        else:
            adjusted = bonus_skew + penalty
        rows.append(
            {
                "id": sid,
                "raw_skew": raw,
                "bonus_skew": bonus_skew,
                "adjusted_skew": adjusted,
                "trusted": trusted,
                "frozen": is_frozen,
            }
        )

    summary = {
        "trusted_count": sum(1 for r in rows if r["trusted"]),
        "untrusted_count": sum(1 for r in rows if not r["trusted"]),
        "frozen_count": sum(1 for r in rows if r["frozen"]),
        "sum_adjusted": sum(int(r["adjusted_skew"]) for r in rows),
        "baseline_id_out": baseline_id,
    }

    def dump(path: Path, payload: object) -> None:
        path.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(",", ": ")) + "\n",
            encoding="utf-8",
        )

    dump(out / "segments_out.json", {"rows": rows})
    dump(out / "summary.json", summary)


if __name__ == "__main__":
    main()
