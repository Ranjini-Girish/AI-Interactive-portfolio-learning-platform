from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field
import os
import hashlib

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def canonical(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"

def write_canonical(path: Path, obj: Any) -> None:
    path.write_text(canonical(obj), encoding='utf-8')
SCHEMA_DIR = Path("/app/schemas")

def _is_link_local(g: str) -> bool:
    p = g.split(".")
    return len(p) == 4 and p[0] == "224" and p[1] == "0" and p[2] == "0"


@dataclass
class RefSim:
    ports: dict[str, dict[str, Any]]
    policy: dict[str, Any]
    members: dict[tuple[int, str], dict[str, dict[str, Any]]] = field(default_factory=dict)
    link_state: dict[str, bool] = field(default_factory=dict)
    now: int = 0
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    forwards: list[dict[str, Any]] = field(default_factory=list)
    totals: dict[str, int] = field(default_factory=lambda: {
        "diagnostic_count": 0,
        "frames_dropped": 0,
        "frames_flooded": 0,
        "frames_forwarded": 0,
        "leave_events": 0,
        "mcast_frame_events": 0,
        "member_count": 0,
        "report_events": 0,
        "tick_events": 0,
        "total_ticks_advanced_sec": 0,
    })

    def _emit(self, seq, sev, code, name):
        self.diagnostics.append({"code": code, "name": name, "seq": seq, "severity": sev})

    def _link_up(self, p):
        return self.link_state.get(p, True)

    def _record_forward(self, ev, decision, egress, reason):
        if not self.policy.get("track_forwarding", True):
            return
        self.forwards.append({
            "decision": decision,
            "egress_ports": sorted(egress),
            "group": ev["group"],
            "ingress_port": ev["ingress_port"],
            "reason": reason,
            "seq": ev["seq"],
            "vlan": ev["vlan"],
        })

    def _bump(self, d):
        if d == "forwarded":
            self.totals["frames_forwarded"] += 1
        elif d == "flooded":
            self.totals["frames_flooded"] += 1
        else:
            self.totals["frames_dropped"] += 1

    def step(self, ev):
        seq = ev["seq"]
        op = ev["op"]
        if op in ("igmp_report", "igmp_leave"):
            port = ev["port"]
            group = ev["group"]
            vlan = ev["vlan"]
            if port not in self.ports:
                raise ValueError(f"unknown port {port}")
            p = self.ports[port]
            if p["vlan"] != vlan:
                raise ValueError("port vlan mismatch")
            if _is_link_local(group):
                raise ValueError("link-local group not allowed on report/leave")
            if op == "igmp_report":
                self.totals["report_events"] += 1
                if p["role"] == "router":
                    return
                key = (vlan, group)
                bucket = self.members.setdefault(key, {})
                if port in bucket:
                    self._emit(seq, "note", "W_REPORT_REFRESH", port)
                bucket[port] = {"last_seen_time": self.now}
            else:
                self.totals["leave_events"] += 1
                if p["role"] == "router":
                    return
                key = (vlan, group)
                bucket = self.members.get(key, {})
                if self.policy.get("fast_leave", False):
                    if port in bucket:
                        del bucket[port]
                    if key in self.members and not self.members[key]:
                        del self.members[key]
                    self._emit(seq, "note", "W_FAST_LEAVE", port)
                else:
                    if port not in bucket:
                        self._emit(seq, "warning", "E_LEAVE_UNKNOWN_GROUP", port)
                    else:
                        del bucket[port]
                        if not bucket:
                            del self.members[key]
        elif op == "mcast_frame":
            self.totals["mcast_frame_events"] += 1
            ingress = ev["ingress_port"]
            if ingress not in self.ports:
                raise ValueError(f"unknown ingress {ingress}")
            p = self.ports[ingress]
            if p["vlan"] != ev["vlan"]:
                self._emit(seq, "warning", "E_INGRESS_VLAN_MISMATCH", ingress)
                self._record_forward(ev, "dropped", [], "vlan_mismatch")
                self._bump("dropped")
                return
            if not self._link_up(ingress):
                self._emit(seq, "warning", "E_INGRESS_PORT_DOWN", ingress)
                self._record_forward(ev, "dropped", [], "ingress_port_down")
                self._bump("dropped")
                return
            vlan = ev["vlan"]
            group = ev["group"]
            if _is_link_local(group):
                eg = sorted([
                    pid for pid, pp in self.ports.items()
                    if pid != ingress and self._link_up(pid) and pp["vlan"] == vlan
                ])
                self._record_forward(ev, "flooded", eg, None)
                self._bump("flooded")
                return
            eg_set = set()
            for pid, pp in self.ports.items():
                if pid == ingress:
                    continue
                if not self._link_up(pid):
                    continue
                if pp["vlan"] != vlan:
                    continue
                if pp["role"] == "router":
                    eg_set.add(pid)
            for pid in self.members.get((vlan, group), {}).keys():
                if pid == ingress:
                    continue
                if not self._link_up(pid):
                    continue
                pp = self.ports.get(pid)
                if pp is None or pp["vlan"] != vlan:
                    continue
                eg_set.add(pid)
            eg = sorted(eg_set)
            if not eg:
                if self.policy.get("drop_unknown_groups", False):
                    self._emit(seq, "note", "W_DROPPED_NO_MEMBERS", group)
                    self._record_forward(ev, "dropped", [], "no_members")
                    self._bump("dropped")
                    return
                fb = sorted([
                    pid for pid, pp in self.ports.items()
                    if pid != ingress and self._link_up(pid) and pp["vlan"] == vlan
                ])
                self._record_forward(ev, "flooded", fb, None)
                self._bump("flooded")
                return
            decision = "forwarded" if len(eg) == 1 else "flooded"
            self._record_forward(ev, decision, eg, None)
            self._bump(decision)
        elif op == "port_link_change":
            port = ev["port"]
            if port not in self.ports:
                raise ValueError(f"unknown port {port}")
            new_state = ev["up"]
            prev = self._link_up(port)
            if prev == new_state:
                self._emit(seq, "note", "W_LINK_NOOP", port)
                self.link_state[port] = new_state
                return
            self.link_state[port] = new_state
            if not new_state:
                removed = False
                for key in list(self.members.keys()):
                    if port in self.members[key]:
                        del self.members[key][port]
                        removed = True
                        if not self.members[key]:
                            del self.members[key]
                if removed:
                    self._emit(seq, "note", "W_LINK_DOWN_PURGE", port)
        elif op == "tick":
            delta = ev["delta_sec"]
            self.totals["tick_events"] += 1
            self.totals["total_ticks_advanced_sec"] += delta
            self.now += delta
            ttl = self.policy["ttl_sec"]
            for key in list(self.members.keys()):
                bucket = self.members[key]
                aged = sorted([pid for pid, m in bucket.items()
                               if (self.now - m["last_seen_time"]) > ttl])
                for pid in aged:
                    del bucket[pid]
                    self._emit(seq, "note", "W_MEMBER_AGED", pid)
                if not bucket:
                    del self.members[key]
        else:
            raise ValueError(f"unknown op {op}")

    def finalize(self):
        sev_rank = {"error": 3, "warning": 2, "note": 1}
        diag_sorted = sorted(
            self.diagnostics,
            key=lambda d: (d["seq"], -sev_rank[d["severity"]], d["code"], d["name"]),
        )
        self.totals["diagnostic_count"] = len(diag_sorted)
        groups = []
        for (vlan, group), bucket in self.members.items():
            members = sorted(
                ({"last_seen_time": m["last_seen_time"], "port": pid}
                 for pid, m in bucket.items()),
                key=lambda m: m["port"],
            )
            groups.append({"group": group, "members": members, "vlan": vlan})
        groups.sort(key=lambda g: (g["vlan"], g["group"]))
        member_count = sum(len(g["members"]) for g in groups)
        self.totals["member_count"] = member_count
        active_groups = sorted({g["group"] for g in groups})
        return {
            "mcast_table": {"groups": groups},
            "forward_log": {
                "forwards": sorted(self.forwards, key=lambda f: f["seq"])
                if self.policy.get("track_forwarding", True) else []
            },
            "igmp_diagnostics": {"diagnostics": diag_sorted},
            "summary": {
                "active_groups": active_groups,
                "totals": dict(sorted(self.totals.items())),
            },
        }


def run_simulation(ports, events, policy):
    pmap = {p["port_id"]: p for p in ports}
    sim = RefSim(ports=pmap, policy=policy)
    for ev in events:
        sim.step(ev)
    return sim.finalize()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------








SOURCE_SUFFIXES = (".ts",)
BUILD_SCRIPT_SUFFIXES = (".mk", ".cmake", ".sh", ".bash")
BUILD_SCRIPT_NAMES = {"Makefile", "GNUmakefile", "makefile", "CMakeLists.txt", "build.ninja"}


def _src_files() -> list[Path]:
    out: list[Path] = []
    for root in (Path("/app/src"), Path("/app/src")):
        if root.exists():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix in SOURCE_SUFFIXES:
                    out.append(p)
    return out


def _all_app_source_files() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file() or p.suffix not in SOURCE_SUFFIXES:
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        out.append(p)
    return out


def _all_app_build_inputs() -> list[Path]:
    out: list[Path] = []
    skip_roots = (Path("/app/build"), Path("/app/output"))
    for p in Path("/app").rglob("*"):
        if not p.is_file():
            continue
        if any(str(p).startswith(str(r) + os.sep) for r in skip_roots):
            continue
        if p.suffix in SOURCE_SUFFIXES + BUILD_SCRIPT_SUFFIXES:
            out.append(p)
        elif p.name in BUILD_SCRIPT_NAMES:
            out.append(p)
    return out


def _snapshot_hashes(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            out[os.fspath(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _snapshot_metadata(root: Path) -> dict[str, tuple[int, int, int]]:
    out: dict[str, tuple[int, int, int]] = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            out[os.fspath(p)] = (st.st_mode, st.st_size, int(st.st_mtime))
    return out


def _snapshot_paths(root: Path) -> set[str]:
    out: set[str] = set()
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if p.is_file():
            out.add(os.fspath(p))
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: oracle <input_dir> <output_dir>", file=sys.stderr)
        return 2
    in_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    ports_doc = load_json(in_dir / "ports.json")
    events_doc = load_json(in_dir / "events.json")
    policy_doc = load_json(in_dir / "policy.json")
    outputs = run_simulation(
        ports_doc["ports"], events_doc["events"], policy_doc
    )
    write_canonical(out_dir / "mcast_table.json", outputs["mcast_table"])
    write_canonical(out_dir / "forward_log.json", outputs["forward_log"])
    write_canonical(out_dir / "igmp_diagnostics.json", outputs["igmp_diagnostics"])
    write_canonical(out_dir / "summary.json", outputs["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
