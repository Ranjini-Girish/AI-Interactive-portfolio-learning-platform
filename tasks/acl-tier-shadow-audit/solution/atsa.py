"""Reference audit generator for acl-tier-shadow-audit (packaged with solve script)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(os.environ.get("ATSA_DATA_DIR", "/app/acl_tier"))
OUT = Path(os.environ.get("ATSA_AUDIT_DIR", "/app/audit"))


def _matches(pat: str, topic: str) -> bool:
    ps = pat.split("/")
    ts = topic.split("/")

    def rec(i: int, j: int) -> bool:
        if i == len(ps):
            return j == len(ts)
        if ps[i] == "#":
            return i == len(ps) - 1
        if j >= len(ts):
            return False
        if ps[i] == "+":
            return rec(i + 1, j + 1)
        if ps[i] != ts[j]:
            return False
        return rec(i + 1, j + 1)

    return rec(0, 0)


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _canon_write(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, sort_keys=True, indent=2, separators=(",", ": "))
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    policy = _load(DATA / "policy.json")
    pool = _load(DATA / "pool_state.json")
    log = _load(DATA / "incident_log.json")
    cascade = [str(x) for x in policy["cascade_tiers"]]
    current_day = int(pool["current_day"])
    client_dir = DATA / "clients"
    client_ids = sorted(p.stem for p in client_dir.glob("*.json"))
    clients = {cid: _load(client_dir / f"{cid}.json") for cid in client_ids}
    parent: dict[str, str | None] = {
        cid: clients[cid].get("shadow_parent") for cid in client_ids
    }
    for cid, p in list(parent.items()):
        if p is not None and p not in clients:
            raise ValueError(f"unknown parent for {cid}: {p}")

    children: dict[str, list[str]] = {cid: [] for cid in client_ids}
    for cid in client_ids:
        p = parent[cid]
        if p is not None:
            children[p].append(cid)
    for k in children:
        children[k].sort()

    def subtree(root_id: str) -> set[str]:
        acc = {root_id}
        stack = [root_id]
        while stack:
            u = stack.pop()
            for v in children.get(u, []):
                if v not in acc:
                    acc.add(v)
                    stack.append(v)
        return acc

    def owned_for(client_id: str) -> list[dict[str, object]]:
        c = clients[client_id]
        seq = 0
        owned_list: list[dict[str, object]] = []

        def push(
            pattern: str,
            action: str,
            tier_origin: str | None,
            introducer: str,
        ) -> None:
            nonlocal seq
            owned_list[:] = [r for r in owned_list if str(r["pattern"]) != pattern]
            seq += 1
            owned_list.append(
                {
                    "pattern": pattern,
                    "action": action,
                    "rule_seq": seq,
                    "tier_origin": tier_origin,
                    "introducer": introducer,
                }
            )

        for r in c.get("seed_rules", []):
            push(str(r["pattern"]), str(r["action"]), None, client_id)
        for tier in cascade:
            layer = _load(DATA / "layers" / f"{tier}.json")
            if str(layer["tier"]) != tier:
                raise ValueError(f"tier mismatch in layer file {tier}")
            for add in layer["additions"]:
                if str(add["client_id"]) != client_id:
                    continue
                push(
                    str(add["pattern"]),
                    str(add["action"]),
                    tier,
                    str(add["client_id"]),
                )
        return owned_list

    def chain(client_id: str) -> list[str]:
        out: list[str] = []
        cur: str | None = client_id
        while cur is not None:
            out.append(cur)
            cur = parent[cur]
        out.reverse()
        return out

    def shadow_merge(client_id: str) -> list[dict[str, object]]:
        seq_counter = 0
        merged: dict[str, dict[str, object]] = {}

        def upsert_from_owned(owned_rules: list[dict[str, object]]) -> None:
            nonlocal seq_counter
            for r in owned_rules:
                seq_counter += 1
                merged[str(r["pattern"])] = {
                    "pattern": str(r["pattern"]),
                    "action": str(r["action"]),
                    "rule_seq": seq_counter,
                    "tier_origin": r["tier_origin"],
                    "introducer": str(r["introducer"]),
                }

        for node in chain(client_id):
            upsert_from_owned(owned_for(node))
        rules = sorted(
            merged.values(),
            key=lambda x: (int(x["rule_seq"]), str(x["pattern"])),
        )
        return rules

    supported = {"tier_strip", "quarantine_subtree"}
    events = log["events"]

    def is_eligible(ev: dict[str, object]) -> bool:
        if not bool(ev.get("accepted")):
            return False
        if int(ev["day"]) > current_day:
            return False
        return str(ev.get("kind")) in supported

    ignored_incidents = sum(1 for e in events if not is_eligible(e))

    eligible_events = [e for e in events if is_eligible(e)]
    eligible_events.sort(key=lambda e: (int(e["day"]), str(e["event_id"])))

    quarantined: set[str] = set()
    effective: dict[str, list[dict[str, object]]] = {
        cid: shadow_merge(cid) for cid in client_ids
    }
    applied_incidents: list[str] = []

    for ev in eligible_events:
        kind = str(ev["kind"])
        if kind == "tier_strip":
            applied_incidents.append(str(ev["event_id"]))
            tier = str(ev["tier"])
            intro = str(ev["strip_introducer"])
            for cid in client_ids:
                if cid in quarantined:
                    continue
                effective[cid] = [
                    r
                    for r in effective[cid]
                    if not (
                        r.get("tier_origin") == tier and str(r.get("introducer")) == intro
                    )
                ]
        elif kind == "quarantine_subtree":
            applied_incidents.append(str(ev["event_id"]))
            quarantined |= subtree(str(ev["target_client"]))
            for q in sorted(quarantined):
                effective[q] = []

    applied_incidents.sort()

    def probe_one(
        client_id: str, topic: str
    ) -> dict[str, object]:
        if client_id not in clients:
            return {
                "client_id": client_id,
                "topic": topic,
                "decision": "deny",
                "reason": "unknown_client",
                "matched_pattern": None,
                "matched_rule_seq": None,
            }
        if client_id in quarantined:
            return {
                "client_id": client_id,
                "topic": topic,
                "decision": "deny",
                "reason": "quarantined",
                "matched_pattern": None,
                "matched_rule_seq": None,
            }
        rules = effective[client_id]
        best: dict[str, object] | None = None
        for r in sorted(rules, key=lambda x: -int(x["rule_seq"])):
            if _matches(str(r["pattern"]), topic):
                best = r
                break
        if best is None:
            return {
                "client_id": client_id,
                "topic": topic,
                "decision": "deny",
                "reason": "default_deny",
                "matched_pattern": None,
                "matched_rule_seq": None,
            }
        return {
            "client_id": client_id,
            "topic": topic,
            "decision": str(best["action"]),
            "reason": "matched",
            "matched_pattern": str(best["pattern"]),
            "matched_rule_seq": int(best["rule_seq"]),
        }

    probes_in = policy["probes"]
    probe_rows = [probe_one(str(p["client_id"]), str(p["topic"])) for p in probes_in]
    allow_probe_count = sum(1 for p in probe_rows if p["decision"] == "allow")
    deny_probe_count = sum(1 for p in probe_rows if p["decision"] == "deny")

    eff_clients = []
    for cid in sorted(client_ids):
        eff_clients.append(
            {
                "client_id": cid,
                "quarantined": cid in quarantined,
                "rules": ([] if cid in quarantined else effective[cid]),
            }
        )

    summary = {
        "allow_probe_count": allow_probe_count,
        "applied_incidents": applied_incidents,
        "clients_total": len(client_ids),
        "deny_probe_count": deny_probe_count,
        "ignored_incidents": ignored_incidents,
        "probes_total": len(probe_rows),
        "quarantined_clients": sorted(quarantined),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    _canon_write(OUT / "effective_access.json", {"clients": eff_clients})
    _canon_write(OUT / "probe_verdicts.json", {"probes": probe_rows})
    _canon_write(OUT / "summary.json", summary)


if __name__ == "__main__":
    main()
