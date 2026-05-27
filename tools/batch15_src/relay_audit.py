#!/usr/bin/env python3
"""Reference relay-hop audit (used by py-relay-hop and hash-lock generation)."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _env(key: str, default: str) -> str:
    v = os.environ.get(key, "").strip()
    return v if v else default


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, obj: object) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sorted_json_paths(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.json") if p.is_file())


def _cap_core(hop: str, base: dict[str, int], delta: dict[str, int], halted: dict[str, bool]) -> int:
    if halted.get(hop, False):
        return 0
    v = base.get(hop, 0) + delta.get(hop, 0)
    return 1 if v < 1 else v


def main() -> None:
    data = Path(_env("RELAY_DATA_DIR", "/app/relayhop"))
    audit = Path(_env("RELAY_AUDIT_DIR", "/app/audit"))
    audit.mkdir(parents=True, exist_ok=True)

    pol = _read_json(data / "policy.json")
    assert isinstance(pol, dict)
    inc_file = _read_json(data / "incidents.json")
    assert isinstance(inc_file, dict)
    carry_max = int(pol["carry_max"])
    epochs = [int(x) for x in pol["epochs"]]
    hops_order = [str(x) for x in pol["hops_order"]]

    base: dict[str, int] = {}
    for p in _sorted_json_paths(data / "hops"):
        hf = _read_json(p)
        assert isinstance(hf, dict)
        base[str(hf["hop_id"])] = int(hf["base_cap"])

    flows: list[dict[str, object]] = []
    for p in _sorted_json_paths(data / "flows"):
        ff = _read_json(p)
        assert isinstance(ff, dict)
        flows.append(
            {
                "flow_id": str(ff["flow_id"]),
                "epoch": int(ff["epoch"]),
                "hop_id": str(ff["hop_id"]),
                "bytes": int(ff["bytes"]),
            }
        )

    epoch_set = set(epochs)
    hop_set = set(hops_order)
    for f in flows:
        if f["epoch"] not in epoch_set or f["hop_id"] not in base:
            raise SystemExit(1)
    if len(hop_set) != len(hops_order) or len(hop_set) != len(base):
        raise SystemExit(1)
    for h in base:
        if h not in hop_set:
            raise SystemExit(1)

    delta = {h: 0 for h in hops_order}
    carry = {h: 0 for h in hops_order}
    halted = {h: False for h in hops_order}

    admissions: list[dict[str, object]] = []
    denials: list[dict[str, object]] = []
    ledgers: list[dict[str, object]] = []

    incidents = inc_file.get("incidents", [])
    assert isinstance(incidents, list)

    for e in epochs:
        for inc in incidents:
            assert isinstance(inc, dict)
            if int(inc["epoch"]) != e:
                continue
            kind = str(inc["kind"])
            if kind == "noop":
                continue
            h = str(inc["hop_id"])
            if kind == "cap_add":
                delta[h] = delta.get(h, 0) + int(inc["delta"])
            elif kind == "halt_hop":
                halted[h] = True
                carry[h] = 0
            elif kind == "resume_hop":
                halted[h] = False
                carry[h] = 0
            else:
                raise SystemExit(1)

        cin = {h: carry[h] for h in hops_order}
        used = {h: 0 for h in hops_order}

        epoch_flows = [f for f in flows if f["epoch"] == e]
        epoch_flows.sort(key=lambda f: (str(f["hop_id"]), str(f["flow_id"])))

        for f in epoch_flows:
            h = str(f["hop_id"])
            b = int(f["bytes"])
            avail = _cap_core(h, base, delta, halted) + cin[h] - used[h]
            if avail < 0:
                avail = 0
            if b <= avail:
                used[h] += b
                admissions.append(
                    {
                        "bytes": b,
                        "epoch": e,
                        "flow_id": str(f["flow_id"]),
                        "hop_id": h,
                    }
                )
            else:
                denials.append(
                    {
                        "available": avail,
                        "epoch": e,
                        "flow_id": str(f["flow_id"]),
                        "hop_id": h,
                        "requested": b,
                    }
                )

        for h in hops_order:
            cc = _cap_core(h, base, delta, halted)
            rem = cc + cin[h] - used[h]
            cout = min(carry_max, max(0, rem))
            if halted[h]:
                cout = 0
            ledgers.append(
                {
                    "cap_core": cc,
                    "carry_in": cin[h],
                    "carry_out": cout,
                    "epoch": e,
                    "hop_id": h,
                    "used": used[h],
                }
            )
            carry[h] = cout

    admissions.sort(key=lambda r: (int(r["epoch"]), str(r["hop_id"]), str(r["flow_id"])))
    denials.sort(key=lambda r: (int(r["epoch"]), str(r["hop_id"]), str(r["flow_id"])))
    ledgers.sort(key=lambda r: (int(r["epoch"]), str(r["hop_id"])))

    applied = [str(inc["kind"]) for inc in incidents if isinstance(inc, dict)]
    max_ep = 0
    for inc in incidents:
        if isinstance(inc, dict):
            max_ep = max(max_ep, int(inc["epoch"]))
    for row in admissions + denials:
        max_ep = max(max_ep, int(row["epoch"]))

    tot_adm = len(admissions)
    tot_adm_bytes = sum(int(r["bytes"]) for r in admissions)
    tot_den = len(denials)
    tot_den_bytes = sum(int(r["requested"]) for r in denials)

    _write_json(audit / "admissions.json", {"admissions": admissions})
    _write_json(audit / "denials.json", {"denials": denials})
    _write_json(audit / "carry_ledgers.json", {"rows": ledgers})
    _write_json(
        audit / "summary.json",
        {
            "incidents_applied": applied,
            "max_epoch": max_ep,
            "total_admissions": tot_adm,
            "total_admitted_bytes": tot_adm_bytes,
            "total_denials": tot_den,
            "total_denied_bytes": tot_den_bytes,
        },
    )


if __name__ == "__main__":
    main()
