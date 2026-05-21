#!/bin/bash
set -euo pipefail

mkdir -p "${QDQ_AUDIT_DIR:-/app/audit}"

python3 <<'PY'
from __future__ import annotations

import json
import math
import os
from pathlib import Path


def rnd6(x: float) -> float:
    """Round to 6 decimal places, ties-to-even."""
    return float(f"{x:.6f}")


def canon_dumps(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, separators=(",", ": ")) + "\n"


def load_json(p: Path) -> object:
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    data = Path(os.environ.get("QDQ_DATA_DIR", "/app/qdq_lab"))
    out = Path(os.environ.get("QDQ_AUDIT_DIR", "/app/audit"))

    policy = load_json(data / "policy.json")
    required_p = {
        "eval_day",
        "min_floor",
        "epsilon",
        "quorum_min_active",
        "tier_weights",
        "frozen_anchors",
        "pool_cap",
    }
    if not isinstance(policy, dict) or required_p != set(policy.keys()):
        raise SystemExit(1)
    eval_day = int(policy["eval_day"])
    min_floor = float(policy["min_floor"])
    eps = float(policy["epsilon"])
    qmin = int(policy["quorum_min_active"])
    tier_w = policy["tier_weights"]
    frozen = set(policy["frozen_anchors"])
    pool_cap = int(policy["pool_cap"])
    if min_floor < 0 or eps <= 0 or qmin < 1 or pool_cap < 1:
        raise SystemExit(1)
    if not isinstance(tier_w, dict) or not tier_w:
        raise SystemExit(1)

    layout = load_json(data / "domain_layout.json")
    if not isinstance(layout, dict) or set(layout.keys()) != {"quote_to_anchor"}:
        raise SystemExit(1)
    q2a = layout["quote_to_anchor"]
    if not isinstance(q2a, dict):
        raise SystemExit(1)

    incidents = load_json(data / "incident_log.json")
    if not isinstance(incidents, list):
        raise SystemExit(1)

    quotes_dir = data / "quotes"
    quote_paths = sorted(quotes_dir.glob("*.json"))
    if not quote_paths:
        raise SystemExit(1)

    quotes: list[dict] = []
    for p in quote_paths:
        q = load_json(p)
        if not isinstance(q, dict):
            raise SystemExit(1)
        need = {
            "quote_id",
            "subject_id",
            "issuer",
            "tier",
            "issued_day",
            "half_life_days",
            "raw_strength",
            "stance",
        }
        if set(q.keys()) != need:
            raise SystemExit(1)
        tid = q["tier"]
        if tid not in tier_w:
            raise SystemExit(1)
        stance = int(q["stance"])
        if stance not in (-1, 0, 1):
            raise SystemExit(1)
        if float(q["half_life_days"]) <= 0:
            raise SystemExit(1)
        quotes.append(q)

    by_subject: dict[str, list[dict]] = {}
    for q in quotes:
        sid = str(q["subject_id"])
        by_subject.setdefault(sid, []).append(q)

    quote_eval: dict[str, dict] = {}
    subjects_out: dict[str, dict] = {}

    for sid in sorted(by_subject.keys()):
        cand: list[dict] = []
        for q in by_subject[sid]:
            qid = str(q["quote_id"])
            if qid not in q2a:
                raise SystemExit(1)
            anchor = str(q2a[qid])
            D = eval_day - int(q["issued_day"])
            hl = float(q["half_life_days"])
            decayed = float(q["raw_strength"]) * math.pow(0.5, D / hl)
            eff = max(min_floor, decayed)
            adj = eff
            issuer = str(q["issuer"])
            stance = int(q["stance"])
            for inc in incidents:
                if not isinstance(inc, dict):
                    raise SystemExit(1)
                need_i = {"subject_id", "issuer", "factor", "from_day", "to_day"}
                if set(inc.keys()) != need_i:
                    raise SystemExit(1)
                if str(inc["subject_id"]) != sid or str(inc["issuer"]) != issuer:
                    continue
                fd = int(inc["from_day"])
                td = int(inc["to_day"])
                if fd <= eval_day <= td:
                    adj *= float(inc["factor"])

            eff_r = rnd6(eff)
            adj_r = rnd6(adj)
            if anchor in frozen:
                quote_eval[qid] = {
                    "adjusted": adj_r,
                    "effective": eff_r,
                    "excluded_reason": "anchor_freeze",
                }
                continue
            cand.append(
                {
                    "quote_id": qid,
                    "adjusted": adj,
                    "adjusted_r": adj_r,
                    "effective_r": eff_r,
                    "stance": stance,
                    "tier": str(q["tier"]),
                    "q": q,
                }
            )

        cand.sort(key=lambda r: (-r["adjusted"], r["quote_id"]))
        kept: list[dict] = []
        for i, row in enumerate(cand):
            qid = row["quote_id"]
            if i < pool_cap:
                quote_eval[qid] = {
                    "adjusted": row["adjusted_r"],
                    "effective": row["effective_r"],
                    "excluded_reason": "none",
                }
                kept.append(row)
            else:
                quote_eval[qid] = {
                    "adjusted": row["adjusted_r"],
                    "effective": row["effective_r"],
                    "excluded_reason": "pool_cap",
                }

        active_kept = sum(1 for r in kept if int(r["stance"]) != 0)
        wtot = 0.0
        kept_ids: list[str] = []
        for r in kept:
            kept_ids.append(r["quote_id"])
            st = int(r["stance"])
            tw = float(tier_w[r["tier"]])
            wtot += r["adjusted"] * tw * st
        kept_ids = sorted(set(kept_ids))

        if active_kept < qmin:
            verdict = "split"
        elif wtot > eps:
            verdict = "pass"
        elif wtot < -eps:
            verdict = "fail"
        else:
            verdict = "split"

        subjects_out[sid] = {
            "active_kept": active_kept,
            "kept_quote_ids": kept_ids,
            "verdict": verdict,
            "weighted_total": rnd6(wtot),
        }

    for q in quotes:
        qid = str(q["quote_id"])
        if qid not in quote_eval:
            raise SystemExit(1)

    verdict_counts = {"fail": 0, "pass": 0, "split": 0}
    wabs = 0.0
    for sid in sorted(subjects_out.keys()):
        vc = subjects_out[sid]["verdict"]
        verdict_counts[str(vc)] += 1
        wabs += abs(float(subjects_out[sid]["weighted_total"]))

    summary = {
        "subjects": len(subjects_out),
        "verdict_counts": verdict_counts,
        "weighted_sum_abs": rnd6(wabs),
    }

    out.mkdir(parents=True, exist_ok=True)
    (out / "subjects.json").write_text(canon_dumps(subjects_out), encoding="utf-8")
    (out / "quotes_eval.json").write_text(
        canon_dumps(dict(sorted(quote_eval.items()))), encoding="utf-8"
    )
    (out / "summary.json").write_text(canon_dumps(summary), encoding="utf-8")


if __name__ == "__main__":
    main()
PY
