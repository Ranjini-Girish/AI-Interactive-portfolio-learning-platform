#!/bin/bash
set -euo pipefail

mkdir -p "${TLS_AUDIT_DIR:-/app/audit}"

python3 - <<'PYEOF'
import json
import os
from pathlib import Path

DATA = Path(os.environ.get("TLS_DATA_DIR", "/app/certs"))
OUT = Path(os.environ.get("TLS_AUDIT_DIR", "/app/audit"))

ALLOWED_INCIDENT_KINDS = {"key_compromise", "ca_compromise", "audit_review"}
ALLOWED_TARGET_VERDICTS = {"valid", "untrusted"}


def write_json(path, obj):
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
        f.write("\n")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    pool = load_json(DATA / "pool_state.json")
    current_day = pool["current_day"]
    audit_version = pool["audit_version"]

    cfg = load_json(DATA / "chain_config.json")
    trusted_roots = set(cfg["trusted_roots"])

    leafs = {}
    for fp in sorted((DATA / "leafs").glob("*.json")):
        leafs[fp.stem] = load_json(fp)

    intermediates = {}
    for fp in sorted((DATA / "intermediates").glob("*.json")):
        intermediates[fp.stem] = load_json(fp)

    domains = []
    for tier_dir in sorted((DATA / "domains").iterdir()):
        if not tier_dir.is_dir():
            continue
        for fp in sorted(tier_dir.glob("*.json")):
            domains.append(load_json(fp))
    domains.sort(key=lambda d: d["domain"])

    ocsp_doc = load_json(DATA / "ocsp_responses.json")
    ocsp_by_serial = {}
    for r in ocsp_doc.get("responses", []):
        sid = r["serial"]
        cur = ocsp_by_serial.get(sid)
        if cur is None or r["produced_day"] > cur["produced_day"]:
            ocsp_by_serial[sid] = r

    log = load_json(DATA / "incident_log.json")
    accepted_events = []
    ignored = 0
    domain_set = {d["domain"] for d in domains}
    leaf_serials = set(leafs.keys())
    inter_serials = set(intermediates.keys())

    for ev in log.get("events", []):
        kind = ev.get("kind")
        day = ev.get("day")
        if kind not in ALLOWED_INCIDENT_KINDS:
            ignored += 1
            continue
        if not isinstance(day, int) or isinstance(day, bool):
            ignored += 1
            continue
        if day > current_day:
            ignored += 1
            continue
        if kind == "key_compromise":
            if ev.get("serial") not in leaf_serials:
                ignored += 1
                continue
        elif kind == "ca_compromise":
            s = ev.get("serial")
            if s not in inter_serials and s not in trusted_roots:
                ignored += 1
                continue
        elif kind == "audit_review":
            if ev.get("domain") not in domain_set:
                ignored += 1
                continue
            if ev.get("target_verdict") not in ALLOWED_TARGET_VERDICTS:
                ignored += 1
                continue
        accepted_events.append(ev)

    key_compromised_leafs = {ev["serial"] for ev in accepted_events if ev["kind"] == "key_compromise"}
    ca_compromised = {ev["serial"] for ev in accepted_events if ev["kind"] == "ca_compromise"}

    audit_overrides = {}
    for idx, ev in enumerate(accepted_events):
        if ev["kind"] == "audit_review":
            d = ev["domain"]
            cur = audit_overrides.get(d)
            if cur is None or ev["day"] > cur[1]["day"] or (ev["day"] == cur[1]["day"] and idx > cur[0]):
                audit_overrides[d] = (idx, ev)

    def walk_chain(leaf_serial):
        if leaf_serial not in leafs:
            return [leaf_serial], "leaf_missing"
        chain = [leaf_serial]
        current = leafs[leaf_serial]
        max_depth = cfg["max_chain_depth"]
        seen = {leaf_serial}
        while True:
            issuer = current["issuer_serial"]
            if issuer in seen:
                chain.append(issuer)
                return chain, "cycle_detected"
            seen.add(issuer)
            if issuer in trusted_roots:
                chain.append(issuer)
                if len(chain) > max_depth:
                    return chain, "chain_too_long"
                return chain, None
            if issuer not in intermediates:
                chain.append(issuer)
                return chain, "intermediate_missing"
            chain.append(issuer)
            if len(chain) > max_depth:
                return chain, "chain_too_long"
            current = intermediates[issuer]

    def san_match(leaf, expected_list, policy):
        leaf_san = leaf.get("san", [])
        cn = leaf.get("subject_cn", "")
        if policy == "exact":
            for e in expected_list:
                if e not in leaf_san:
                    return False
            return True
        if policy == "wildcard_ok":
            for e in expected_list:
                if e in leaf_san:
                    continue
                matched = False
                for s in leaf_san:
                    if s.startswith("*."):
                        rest = s[2:]
                        parts = e.split(".", 1)
                        if len(parts) == 2 and parts[1] == rest:
                            matched = True
                            break
                if not matched:
                    return False
            return True
        if policy == "cn_only":
            for e in expected_list:
                if e != cn:
                    return False
            return True
        return False

    domain_chain = {}
    domain_walk_failure = {}
    for d in domains:
        chain, fail = walk_chain(d["leaf_serial"])
        domain_chain[d["domain"]] = chain
        domain_walk_failure[d["domain"]] = fail

    domain_visits_compromised_ca = {}
    for d in domains:
        chain = domain_chain[d["domain"]]
        domain_visits_compromised_ca[d["domain"]] = any(s in ca_compromised for s in chain)

    domain_intermediate_set = {}
    for d in domains:
        chain = domain_chain[d["domain"]]
        if len(chain) >= 2:
            ints_only = [s for s in chain[1:-1] if s in intermediates]
            if domain_walk_failure[d["domain"]] is None and len(chain) >= 2:
                if chain[-1] in trusted_roots:
                    pass
            domain_intermediate_set[d["domain"]] = set(ints_only)
        else:
            domain_intermediate_set[d["domain"]] = set()

    compromised_intermediates_in_chains = set()
    for dom, visits in domain_visits_compromised_ca.items():
        if visits:
            chain = domain_chain[dom]
            for s in chain:
                if s in intermediates:
                    compromised_intermediates_in_chains.add(s)

    domain_records = []
    for d in domains:
        dom = d["domain"]
        tier = d["tier"]
        leaf_serial = d["leaf_serial"]
        chain = domain_chain[dom]
        fail = domain_walk_failure[dom]

        leaf = leafs.get(leaf_serial)
        reasons = set()

        if fail is not None:
            reasons.add(fail)

        if leaf is not None:
            if current_day > leaf["not_after_day"]:
                reasons.add("expired")
            if current_day < leaf["not_before_day"]:
                reasons.add("not_yet_valid")
            days_to_expiry = leaf["not_after_day"] - current_day
            if 0 <= days_to_expiry <= cfg["expiry_warn_days"]:
                reasons.add("expiry_warning")

        if leaf is not None:
            if leaf["key_size"] < cfg["key_size_min_per_tier"][tier]:
                reasons.add("key_size_too_small")

        if leaf is not None:
            policy = cfg["san_policy_per_tier"][tier]
            if not san_match(leaf, d["expected_san"], policy):
                reasons.add("san_mismatch")

        ocsp_state = "soft_fail"
        if leaf_serial in ocsp_by_serial:
            r = ocsp_by_serial[leaf_serial]
            stale = (current_day - r["produced_day"]) > cfg["ocsp_stale_days"]
            if r["status"] == "revoked":
                ocsp_state = "revoked"
            elif r["status"] == "good" and not stale:
                ocsp_state = "valid"
            else:
                ocsp_state = "soft_fail"
        if ocsp_state == "revoked":
            reasons.add("revoked")
        elif ocsp_state == "soft_fail":
            reasons.add("ocsp_soft_fail")

        if fail is not None:
            verdict = "chain_unreachable"
        elif "expired" in reasons or "not_yet_valid" in reasons:
            verdict = "expired"
        elif ocsp_state == "revoked":
            verdict = "revoked"
        elif "key_size_too_small" in reasons or "san_mismatch" in reasons:
            verdict = "untrusted"
        elif "expiry_warning" in reasons or ocsp_state == "soft_fail":
            verdict = "warning"
        else:
            verdict = "valid"

        if leaf_serial in key_compromised_leafs:
            verdict = "compromised"
            reasons.add("key_compromise")
        elif domain_visits_compromised_ca[dom]:
            verdict = "compromised"
            reasons.add("ca_compromise")
        else:
            shared = domain_intermediate_set[dom] & compromised_intermediates_in_chains
            if shared:
                verdict = "tainted"
                reasons.add("ca_compromise")

        if verdict not in ("compromised",) and dom in audit_overrides:
            target = audit_overrides[dom][1]["target_verdict"]
            verdict = target
            reasons.add("audit_review_override")

        domain_records.append({
            "domain": dom,
            "tier": tier,
            "verdict": verdict,
            "chain": chain,
            "reasons": sorted(reasons) if (verdict != "valid" or "audit_review_override" in reasons) else [],
        })

    domain_records.sort(key=lambda x: x["domain"])
    write_json(OUT / "chain_audit.json", {"domains": domain_records})

    buckets = {"ok": [], "warning": [], "expired": []}
    for d in domains:
        leaf = leafs.get(d["leaf_serial"])
        if leaf is None:
            continue
        days = leaf["not_after_day"] - current_day
        is_expired = current_day > leaf["not_after_day"] or current_day < leaf["not_before_day"]
        if is_expired:
            bucket = "expired"
        elif 0 <= days <= cfg["expiry_warn_days"]:
            bucket = "warning"
        else:
            bucket = "ok"
        buckets[bucket].append({"domain": d["domain"], "days_to_expiry": days})
    for k in buckets:
        buckets[k].sort(key=lambda x: (x["days_to_expiry"], x["domain"]))
    write_json(OUT / "expiry_report.json", {"buckets": buckets})

    ocsp_details = []
    by_state = {"valid": 0, "revoked": 0, "soft_fail": 0}
    for d in domains:
        ls = d["leaf_serial"]
        r = ocsp_by_serial.get(ls)
        if r is None:
            state = "soft_fail"
        else:
            stale = (current_day - r["produced_day"]) > cfg["ocsp_stale_days"]
            if r["status"] == "revoked":
                state = "revoked"
            elif r["status"] == "good" and not stale:
                state = "valid"
            else:
                state = "soft_fail"
        ocsp_details.append({"domain": d["domain"], "leaf_serial": ls, "ocsp_state": state})
        by_state[state] += 1
    ocsp_details.sort(key=lambda x: x["domain"])
    write_json(OUT / "ocsp_summary.json", {"by_state": by_state, "details": ocsp_details})

    inter_records = []
    for serial in sorted(intermediates.keys()):
        anchor = None
        cur = serial
        seen = {serial}
        max_d = cfg["max_chain_depth"]
        depth = 1
        while True:
            issuer = intermediates[cur]["issuer_serial"]
            if issuer in trusted_roots:
                anchor = issuer
                break
            if issuer in seen or issuer not in intermediates:
                break
            seen.add(issuer)
            cur = issuer
            depth += 1
            if depth > max_d:
                break

        domains_signed = sum(1 for d in domains if serial in domain_chain[d["domain"]])
        tainted = sorted(rec["domain"] for rec in domain_records
                         if rec["verdict"] == "tainted" and serial in domain_intermediate_set[rec["domain"]])
        inter_records.append({
            "serial": serial,
            "trusted_root_anchor": anchor,
            "compromised": serial in ca_compromised,
            "domains_signed": domains_signed,
            "tainted_domains": tainted,
        })
    write_json(OUT / "ca_risk.json", {"intermediates": inter_records})

    by_verdict = {"valid": 0, "warning": 0, "expired": 0, "revoked": 0,
                  "untrusted": 0, "chain_unreachable": 0, "compromised": 0, "tainted": 0}
    for rec in domain_records:
        by_verdict[rec["verdict"]] = by_verdict.get(rec["verdict"], 0) + 1

    summary = {
        "current_day": current_day,
        "audit_version": audit_version,
        "total_domains": len(domains),
        "total_intermediates": len(intermediates),
        "ignored_incident_events": ignored,
        "by_verdict": by_verdict,
        "by_ocsp_state": by_state,
        "compromised_cas": sorted(ca_compromised),
    }
    write_json(OUT / "summary.json", summary)


if __name__ == "__main__":
    main()
PYEOF
