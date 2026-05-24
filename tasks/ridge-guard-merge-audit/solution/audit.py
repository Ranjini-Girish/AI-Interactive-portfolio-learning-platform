from __future__ import annotations

import json
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path


def _load(p: Path) -> object:
    """Parse JSON from UTF-8 path."""
    return json.loads(p.read_text(encoding="utf-8"))


def _dump_canonical(obj: object, p: Path) -> None:
    """Write canonical JSON with trailing newline."""
    text = json.dumps(obj, ensure_ascii=True, indent=2, separators=(", ", ": "), sort_keys=True)
    p.write_text(text + "\n", encoding="utf-8")


def _micro_from_scaled(s: float) -> int:
    """Convert scaled lambda to microlambda per SPEC."""
    s_str = format(s, ".17g")
    return int((Decimal(s_str) * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))


def _micro_from_cap(cap: float) -> int:
    """Convert policy cap to integer microlambda."""
    cap_str = format(float(cap), ".17g")
    return int((Decimal(cap_str) * Decimal("1000000")).to_integral_value(rounding=ROUND_HALF_EVEN))


def main() -> int:
    """Compute ridge merge audit artifacts or exit non-zero on malformed inputs."""
    data = Path(__import__("os").environ.get("RGMA_DATA_DIR", "/app/rgma_lab"))
    out = Path(__import__("os").environ.get("RGMA_AUDIT_DIR", "/app/audit"))

    try:
        policy = _load(data / "policy.json")
        layout = _load(data / "domain_layout.json")
        pool = _load(data / "pool_state.json")
        incidents_raw = _load(data / "incident_log.json")
        window = _load(data / "anchors" / "window.json")
        meta = _load(data / "ancillary" / "meta.json")
    except (OSError, json.JSONDecodeError):
        return 1

    required_policy = (
        "alias_guard",
        "day_end",
        "day_start",
        "lambda_cap",
        "signal_cutoff",
        "tiers",
    )
    if not isinstance(policy, dict) or any(k not in policy for k in required_policy):
        return 1
    if not isinstance(layout, dict) or "hosts" not in layout:
        return 1
    if not isinstance(incidents_raw, list):
        return 1
    if not isinstance(window, dict) or "end" not in window or "start" not in window:
        return 1
    if not isinstance(meta, dict) or "alias_groups" not in meta:
        return 1
    if not isinstance(pool, dict) or not isinstance(pool.get("revision"), str):
        return 1

    tiers = policy["tiers"]
    if not isinstance(tiers, dict):
        return 1
    for tname in ("gold", "silver", "bronze"):
        if tname not in tiers or not isinstance(tiers[tname], (int, float)):
            return 1
        if not float(tiers[tname]) > 0:
            return 1

    try:
        day_start = int(policy["day_start"])
        day_end = int(policy["day_end"])
        anchor_start = int(window["start"])
        anchor_end = int(window["end"])
        alias_guard = bool(policy["alias_guard"])
        signal_cutoff = float(policy["signal_cutoff"])
        lambda_cap = float(policy["lambda_cap"])
    except (TypeError, ValueError):
        return 1

    if signal_cutoff < 0 or not lambda_cap > 0:
        return 1
    if day_end < day_start or anchor_end < anchor_start:
        return 1

    overlap_low = max(day_start, anchor_start)
    overlap_high = min(day_end, anchor_end)
    overlap_days = max(0, overlap_high - overlap_low + 1) if overlap_high >= overlap_low else 0
    k = min(overlap_days, 5)
    f_anchor = 1.0 + 0.01 * k
    anchor_factor = float(f"{f_anchor:.12f}")

    host_dir = data / "hosts"
    if not host_dir.is_dir():
        return 1

    hosts: dict[str, dict[str, object]] = {}
    for path in sorted(host_dir.glob("*.json")):
        try:
            rec = _load(path)
        except (OSError, json.JSONDecodeError):
            return 1
        if not isinstance(rec, dict):
            return 1
        hid = rec.get("host_id")
        tier = rec.get("tier")
        raw_l = rec.get("raw_lambda")
        bias = rec.get("bias_signal")
        if not isinstance(hid, str) or not hid:
            return 1
        if tier not in ("gold", "silver", "bronze"):
            return 1
        if not isinstance(raw_l, (int, float)) or not isinstance(bias, (int, float)):
            return 1
        if hid in hosts:
            return 1
        hosts[hid] = {
            "tier": tier,
            "raw_lambda": float(raw_l),
            "bias_signal": float(bias),
            "frozen": False,
        }

    expected_hosts = layout.get("hosts")
    if not isinstance(expected_hosts, list):
        return 1
    exp_ids = {str(x) for x in expected_hosts}
    if set(hosts.keys()) != exp_ids:
        return 1

    incidents: list[dict[str, object]] = []
    for inc in incidents_raw:
        if not isinstance(inc, dict):
            return 1
        if "kind" not in inc or "seq" not in inc:
            return 1
        try:
            int(inc["seq"])
        except (TypeError, ValueError):
            return 1
        kind = inc["kind"]
        if not isinstance(kind, str):
            return 1
        incidents.append(inc)

    def _inc_sort_key(inc: dict[str, object]) -> tuple[int, str, str, str]:
        hid = ""
        if isinstance(inc.get("host_id"), str):
            hid = inc["host_id"]
        canon = json.dumps(inc, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        seq = int(inc["seq"])
        kind = str(inc["kind"])
        return (seq, kind, hid, canon)

    incidents.sort(key=_inc_sort_key)

    for inc in incidents:
        kind = inc["kind"]
        hid = inc.get("host_id")
        if kind == "bump_lambda":
            if not isinstance(hid, str) or "delta" not in inc:
                return 1
            if hid not in hosts:
                continue
            if hosts[hid]["frozen"]:
                continue
            d = inc["delta"]
            if not isinstance(d, (int, float)):
                return 1
            hosts[hid]["raw_lambda"] = float(hosts[hid]["raw_lambda"]) + float(d)
        elif kind == "freeze_host":
            if not isinstance(hid, str):
                return 1
            if hid in hosts:
                hosts[hid]["frozen"] = True
        elif kind == "lift_freeze":
            if not isinstance(hid, str):
                return 1
            if hid in hosts:
                hosts[hid]["frozen"] = False
        else:
            return 1

    cap_micro = _micro_from_cap(lambda_cap)

    groups = meta["alias_groups"]
    if not isinstance(groups, list):
        return 1
    for g in groups:
        if not isinstance(g, list):
            return 1
        for x in g:
            if not isinstance(x, str):
                return 1

    entries: list[dict[str, object]] = []
    frozen_total = 0
    micros: dict[str, int | None] = {}

    for hid in sorted(hosts.keys()):
        st = hosts[hid]
        if st["frozen"]:
            frozen_total += 1
            micros[hid] = None
            entries.append(
                {
                    "bias_class": "frozen",
                    "host_id": hid,
                    "microlambda": None,
                    "tier": st["tier"],
                }
            )
            continue

        tier = str(st["tier"])
        raw_lambda = float(st["raw_lambda"])
        tier_scale = float(tiers[tier])
        s = raw_lambda * tier_scale * anchor_factor
        m = _micro_from_scaled(s)
        micros[hid] = m

        bias = float(st["bias_signal"])
        if bias > signal_cutoff:
            bclass = "high"
        elif bias < -signal_cutoff:
            bclass = "low"
        else:
            bclass = "mid"

        entries.append(
            {
                "bias_class": bclass,
                "host_id": hid,
                "microlambda": m,
                "tier": tier,
            }
        )

    merged_groups = 0
    if alias_guard:
        for group in groups:
            live = [hid for hid in group if hid in hosts and not hosts[hid]["frozen"]]
            if len(live) < 2:
                continue
            merged_groups += 1
            vals = [micros[hid] for hid in live]
            if any(v is None for v in vals):
                return 1
            mx = max(int(v) for v in vals if v is not None)
            for hid in live:
                micros[hid] = mx
        for ent in entries:
            hid = str(ent["host_id"])
            if ent["microlambda"] is None:
                continue
            ent["microlambda"] = micros[hid]

    for ent in entries:
        if ent["microlambda"] is None:
            continue
        m = int(ent["microlambda"])
        ent["microlambda"] = min(m, cap_micro)

    report = {
        "anchor_factor": anchor_factor,
        "entries": entries,
        "schema_version": 1,
    }

    summary = {
        "anchor_overlap_days": overlap_days,
        "entries_total": len(hosts),
        "frozen_total": frozen_total,
        "lambda_cap_micro": cap_micro,
        "merged_groups": merged_groups,
        "schema_version": 1,
    }

    out.mkdir(parents=True, exist_ok=True)
    _dump_canonical(report, out / "ridge_report.json")
    _dump_canonical(summary, out / "summary.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
