#!/usr/bin/env python3
from __future__ import annotations

from typing import Any
import json
import os
from pathlib import Path

def _load(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))

def _items(root: Path) -> list[dict[str, Any]]:
    d = root / "items"
    rows: list[dict[str, Any]] = []
    for fp in sorted(d.glob("*.json")):
        rows.append(_load(fp))
    return rows

def run_jsa(root: Path) -> dict[str, Any]:
    policy = _load(root / "policy.json")
    pool = _load(root / "pool_state.json")
    inc = _load(root / "incident_log.json")
    day = int(pool["current_day"])
    tiers = policy["tier_skew_cap"]
    grace = int(policy["expiry_grace_days"])
    skew_bump: dict[str, int] = {}
    revoked: set[str] = set()
    for ev in inc.get("events", []):
        if not ev.get("accepted", False):
            continue
        k = ev.get("kind")
        if k == "skew_bump":
            skew_bump[str(ev["scope_id"])] = int(ev.get("delta_days", 0))
        elif k == "revoke_scope":
            revoked.add(str(ev["scope_id"]))
    rows: list[dict[str, Any]] = []
    for it in _items(root):
        sid = str(it["scope_id"])
        tier = str(it["tier"])
        issued = int(it["issued_day"])
        ttl = int(it["ttl_days"])
        base_skew = int(it.get("clock_skew_days", 0))
        raw_exp = issued + ttl
        eff_skew = min(
            tiers.get(tier, 0),
            base_skew + skew_bump.get(sid, 0),
        )
        valid_through = raw_exp + eff_skew + grace
        reasons: list[str] = []
        if sid in revoked:
            reasons.append("revoked")
        if day > valid_through:
            reasons.append("expired")
        if issued > day:
            reasons.append("not_yet_valid")
        status = "invalid" if reasons else "valid"
        rows.append(
            {
                "scope_id": sid,
                "tier": tier,
                "status": status,
                "valid_through_day": valid_through,
                "effective_skew_days": eff_skew,
                "reasons": sorted(reasons),
            }
        )
    rows.sort(key=lambda r: r["scope_id"])
    valid = sum(1 for r in rows if r["status"] == "valid")
    return {
        "claim_rows.json": {"scopes": rows},
        "summary.json": {
            "current_day": day,
            "scopes_total": len(rows),
            "scopes_valid": valid,
            "scopes_invalid": len(rows) - valid,
        },
    }


def main() -> None:
    root = Path(os.environ["JSA_DATA_DIR"])
    out = Path(os.environ["JSA_AUDIT_DIR"])
    out.mkdir(parents=True, exist_ok=True)
    payloads = run_jsa(root)
    for name, payload in payloads.items():
        target = out / name
        target.write_text(
            json.dumps(payload, sort_keys=True, indent=2, separators=(", ", ": "))
            + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
