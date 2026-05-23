#!/bin/bash
set -euo pipefail

export SBW_DATA_DIR="${SBW_DATA_DIR:-/app/sloburn}"
export SBW_AUDIT_DIR="${SBW_AUDIT_DIR:-/app/audit}"
mkdir -p "${SBW_AUDIT_DIR}"

python3 <<'PYEOF'
import json
import os
from pathlib import Path


def pretty(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )


def blacked(host_id: str, slot: int, windows: list[dict]) -> bool:
    for w in windows:
        hid = w["host_id"]
        if hid not in (host_id, "*"):
            continue
        if w["start_slot"] <= slot <= w["end_slot"]:
            return True
    return False


def solve(root: Path) -> dict[str, object]:
    policy = json.loads((root / "policy.json").read_text(encoding="utf-8"))
    view = json.loads((root / "view.json").read_text(encoding="utf-8"))
    incidents = json.loads((root / "incidents.json").read_text(encoding="utf-8"))
    blackout = json.loads((root / "blackout.json").read_text(encoding="utf-8"))

    w = int(policy["window_slots"])
    warmup = int(policy["warmup_slots"])
    if view["ops_tag"] != policy["fleet_tag"]:
        warmup += 1
    burn_num = int(policy["burn_num"])
    burn_den = int(policy["burn_den"])
    critical = set(policy["critical_hosts"])
    active_tag = incidents["active_freeze_tag"]
    windows = blackout["windows"]

    host_rows: list[dict] = []
    burn_rows: list[dict] = []
    blackout_zeroed = 0
    fleet_num = 0
    fleet_den = 0
    counts = {"active": 0, "breach": 0, "frozen": 0}

    for path in sorted((root / "hosts").glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        hid = doc["host_id"]
        freeze_tag = doc["freeze_tag"]
        samples = [s for s in doc["samples"] if int(s["slot"]) >= warmup]
        samples.sort(key=lambda s: int(s["slot"]))
        window = samples[-w:] if samples else []
        num = 0
        den = 0
        last_slot = -1
        for s in window:
            slot = int(s["slot"])
            ok = int(s["ok"])
            err = int(s["err"])
            eff_err = 0 if blacked(hid, slot, windows) else err
            if eff_err == 0 and err > 0:
                blackout_zeroed += 1
            num += eff_err
            den += ok + eff_err
            last_slot = slot
        burn_ppm = (1_000_000 * num // den) if den > 0 else 0
        breach = den > 0 and num * burn_den >= burn_num * den
        if hid in critical and breach:
            status = "breach"
        elif freeze_tag != active_tag:
            status = "frozen"
        elif breach:
            status = "breach"
        else:
            status = "active"
        host_rows.append(
            {
                "burn_ppm": burn_ppm,
                "den": den,
                "host_id": hid,
                "last_slot": last_slot,
                "num": num,
                "status": status,
            }
        )
        burn_rows.append(
            {
                "burn_ppm": burn_ppm,
                "den": den,
                "host_id": hid,
                "num": num,
                "sample_count": len(window),
            }
        )
        counts[status] += 1
        if status in ("active", "breach"):
            fleet_num += num
            fleet_den += den

    host_rows.sort(key=lambda r: r["host_id"])
    burn_rows.sort(key=lambda r: r["host_id"])
    fleet_ppm = (1_000_000 * fleet_num // fleet_den) if fleet_den > 0 else 0
    summary = {
        "active_total": counts["active"],
        "blackout_zeroed_errors": blackout_zeroed,
        "breach_total": counts["breach"],
        "effective_warmup": warmup,
        "fleet_burn_ppm": fleet_ppm,
        "fleet_den": fleet_den,
        "fleet_num": fleet_num,
        "frozen_total": counts["frozen"],
        "host_total": len(host_rows),
    }
    return {
        "host_states.json": {"effective_warmup": warmup, "hosts": host_rows},
        "window_burns.json": {"burn_windows": burn_rows},
        "fleet_summary.json": summary,
    }


data = Path(os.environ.get("SBW_DATA_DIR", "/app/sloburn"))
audit = Path(os.environ.get("SBW_AUDIT_DIR", "/app/audit"))
for name, obj in solve(data).items():
    pretty(audit / name, obj)
PYEOF
