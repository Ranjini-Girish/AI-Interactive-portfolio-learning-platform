#!/bin/bash
set -euo pipefail

mkdir -p /app/src /app/include /app/build /app/output

# -------------------------- include/types.hpp --------------------------
cat > /app/include/types.hpp <<'HPP'
#pragma once
#include <nlohmann/json.hpp>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <tuple>
#include <vector>

using nlohmann::json;
using nlohmann::ordered_json;

struct Process {
    long long pid;
    long long ppid;
    long long uid;
    std::string state;
    long long start_tick;
    std::optional<long long> exit_tick;
    std::optional<long long> exit_code;
    std::optional<std::string> exit_signal;
    std::string cmdline;
    // Internal: which seq turned this pid into a zombie (for W_ZOMBIE_LEAK).
    std::optional<long long> exit_seq;
};

struct Event {
    long long seq;
    long long tick;
    std::string op;
    long long pid;
    std::optional<long long> parent_pid;
    std::optional<long long> target_pid;
    std::optional<long long> exit_code;
    std::optional<std::string> signal;
    std::optional<std::string> cmdline;
};

struct Policy {
    long long init_pid;
    std::string orphan_handling;
    bool implicit_init_reap;
    std::string wait_on_living_child;
    bool track_lineage;
};

struct Diagnostic {
    std::string code;
    std::optional<long long> pid;
    std::string severity;
};

struct ReapRecord {
    long long parent_pid;
    long long pid;
    long long seq;
    long long tick;
    std::string trigger;
};

struct LineageEdge {
    long long from;
    long long to;
    std::string type;
    bool operator<(const LineageEdge& o) const {
        return std::tie(from, to, type) < std::tie(o.from, o.to, o.type);
    }
    bool operator==(const LineageEdge& o) const {
        return from == o.from && to == o.to && type == o.type;
    }
};
HPP

# -------------------------- src/main.cpp --------------------------
cat > /app/src/main.cpp <<'CPP'
#include "../include/types.hpp"

#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <vector>

namespace fs = std::filesystem;

// ---------------------------------------------------------------------------
// IO
// ---------------------------------------------------------------------------

static json read_json(const fs::path& p) {
    std::ifstream f(p);
    if (!f) throw std::runtime_error("cannot open " + p.string());
    json j;
    f >> j;
    return j;
}

static ordered_json sort_recursive(const json& j) {
    if (j.is_object()) {
        std::vector<std::string> keys;
        for (auto it = j.begin(); it != j.end(); ++it) keys.push_back(it.key());
        std::sort(keys.begin(), keys.end());
        ordered_json out = ordered_json::object();
        for (const auto& k : keys) out[k] = sort_recursive(j[k]);
        return out;
    } else if (j.is_array()) {
        ordered_json out = ordered_json::array();
        for (const auto& e : j) out.push_back(sort_recursive(e));
        return out;
    }
    return ordered_json(j);
}

static void write_canonical(const fs::path& p, const ordered_json& payload) {
    std::ostringstream oss;
    oss << payload.dump(2, ' ', /*ensure_ascii=*/true);
    std::string text = oss.str();
    text.push_back('\n');
    std::ofstream f(p, std::ios::binary);
    f.write(text.data(), static_cast<std::streamsize>(text.size()));
}

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------

static std::optional<long long> opt_ll(const json& v) {
    if (v.is_null()) return std::nullopt;
    return v.get<long long>();
}

static std::optional<std::string> opt_str(const json& v) {
    if (v.is_null()) return std::nullopt;
    return v.get<std::string>();
}

static const std::set<std::string> VALID_OPS = {
    "fork", "exit", "wait", "kill", "exec",
};
static const std::set<std::string> VALID_SIGNALS = {
    "SIGTERM", "SIGKILL", "SIGINT", "SIGCHLD",
};

static std::vector<Process> parse_processes(const json& root) {
    std::vector<Process> out;
    if (!root.is_object() || !root.contains("processes") ||
        !root["processes"].is_array()) {
        throw std::runtime_error("processes.json: missing or non-array 'processes'");
    }
    std::set<long long> seen;
    for (const auto& r : root.at("processes")) {
        if (!r.is_object()) throw std::runtime_error("processes.json: entry not object");
        Process p;
        p.pid        = r.at("pid").get<long long>();
        p.ppid       = r.at("ppid").get<long long>();
        p.uid        = r.at("uid").get<long long>();
        p.state      = r.at("state").get<std::string>();
        p.start_tick = r.at("start_tick").get<long long>();
        p.cmdline    = r.at("cmdline").get<std::string>();
        if (p.pid < 1) {
            throw std::runtime_error("processes.json: pid must be >= 1");
        }
        if (p.ppid < 0) {
            throw std::runtime_error("processes.json: ppid must be >= 0");
        }
        if (p.uid < 0) {
            throw std::runtime_error("processes.json: uid must be >= 0");
        }
        if (p.state != "RUNNING") {
            throw std::runtime_error("processes.json: initial state must be RUNNING");
        }
        if (p.start_tick < 0) {
            throw std::runtime_error("processes.json: start_tick must be >= 0");
        }
        if (!seen.insert(p.pid).second) {
            throw std::runtime_error("processes.json: duplicate pid");
        }
        out.push_back(p);
    }
    // Validate forest: every non-zero ppid must reference an initial pid.
    for (const auto& p : out) {
        if (p.ppid != 0 && !seen.count(p.ppid)) {
            throw std::runtime_error("processes.json: ppid does not reference any initial pid");
        }
    }
    return out;
}

static std::vector<Event> parse_events(const json& root) {
    std::vector<Event> out;
    if (!root.is_object() || !root.contains("events") ||
        !root["events"].is_array()) {
        throw std::runtime_error("events.json: missing or non-array 'events'");
    }
    for (const auto& e : root.at("events")) {
        if (!e.is_object()) throw std::runtime_error("events.json: entry not object");
        Event ev;
        ev.seq        = e.at("seq").get<long long>();
        ev.tick       = e.at("tick").get<long long>();
        ev.op         = e.at("op").get<std::string>();
        ev.pid        = e.at("pid").get<long long>();
        ev.parent_pid = opt_ll(e.at("parent_pid"));
        ev.target_pid = opt_ll(e.at("target_pid"));
        ev.exit_code  = opt_ll(e.at("exit_code"));
        ev.signal     = opt_str(e.at("signal"));
        ev.cmdline    = opt_str(e.at("cmdline"));
        if (!VALID_OPS.count(ev.op)) {
            throw std::runtime_error("events.json: invalid op");
        }
        if (ev.signal.has_value() && !VALID_SIGNALS.count(*ev.signal)) {
            throw std::runtime_error("events.json: invalid signal");
        }
        if (ev.seq < 0) throw std::runtime_error("events.json: seq must be >= 0");
        if (ev.tick < 0) throw std::runtime_error("events.json: tick must be >= 0");
        if (ev.pid < 1) throw std::runtime_error("events.json: pid must be >= 1");
        // Per-op required-field validation. Rejects malformed input early so
        // handle_* can dereference its required optionals safely.
        if (ev.op == "fork") {
            if (!ev.parent_pid.has_value()) {
                throw std::runtime_error("events.json: fork requires parent_pid");
            }
        } else if (ev.op == "exit") {
            if (!ev.exit_code.has_value()) {
                throw std::runtime_error("events.json: exit requires exit_code");
            }
        } else if (ev.op == "kill") {
            if (!ev.signal.has_value()) {
                throw std::runtime_error("events.json: kill requires signal");
            }
            if (!ev.target_pid.has_value()) {
                throw std::runtime_error("events.json: kill requires target_pid");
            }
        } else if (ev.op == "exec") {
            if (!ev.cmdline.has_value()) {
                throw std::runtime_error("events.json: exec requires cmdline");
            }
        }
        out.push_back(ev);
    }
    std::sort(out.begin(), out.end(),
              [](const Event& a, const Event& b) { return a.seq < b.seq; });
    for (size_t i = 0; i < out.size(); ++i) {
        if (out[i].seq != static_cast<long long>(i)) {
            throw std::runtime_error("events.json: seq must be dense 0..N-1");
        }
    }
    return out;
}

static Policy parse_policy(const json& root) {
    if (!root.is_object()) throw std::runtime_error("policy.json: not object");
    Policy p;
    p.init_pid             = root.at("init_pid").get<long long>();
    p.orphan_handling      = root.at("orphan_handling").get<std::string>();
    p.implicit_init_reap   = root.at("implicit_init_reap").get<bool>();
    p.wait_on_living_child = root.at("wait_on_living_child").get<std::string>();
    p.track_lineage        = root.at("track_lineage").get<bool>();
    if (p.init_pid < 1) throw std::runtime_error("policy.json: init_pid must be >= 1");
    static const std::set<std::string> VALID_ORPH = {"reparent_to_init", "leave_orphaned"};
    static const std::set<std::string> VALID_WAIT = {"diagnostic", "noop"};
    if (!VALID_ORPH.count(p.orphan_handling)) {
        throw std::runtime_error("policy.json: invalid orphan_handling");
    }
    if (!VALID_WAIT.count(p.wait_on_living_child)) {
        throw std::runtime_error("policy.json: invalid wait_on_living_child");
    }
    return p;
}

// ---------------------------------------------------------------------------
// Simulator
// ---------------------------------------------------------------------------

static const std::string ST_RUNNING = "RUNNING";
static const std::string ST_ZOMBIE  = "ZOMBIE";
static const std::string ST_EXITED  = "EXITED";

struct Sim {
    std::map<long long, Process> processes;          // pid -> process
    std::set<long long> seen_pids;                    // every pid ever observed
    std::map<long long, std::vector<Diagnostic>> diagnostics;
    std::vector<ReapRecord> reap_log;
    std::set<LineageEdge> lineage_edges;
    long long forks_succeeded = 0;
    long long forks_rejected = 0;
    long long killed_by_signal = 0;
    long long orphans_reparented = 0;
    long long max_concurrent_processes = 0;
    Policy policy;

    void emit(long long seq, const std::string& code,
              std::optional<long long> pid) {
        Diagnostic d;
        d.code = code;
        d.pid  = pid;
        if (code[0] == 'E') d.severity = "error";
        else if (code[0] == 'W') d.severity = "warning";
        else d.severity = "note";
        diagnostics[seq].push_back(d);
    }

    void update_max_concurrent() {
        long long count = 0;
        for (const auto& [_, p] : processes) {
            if (p.state == ST_RUNNING || p.state == ST_ZOMBIE) ++count;
        }
        if (count > max_concurrent_processes) max_concurrent_processes = count;
    }

    bool is_running(long long pid) const {
        auto it = processes.find(pid);
        return it != processes.end() && it->second.state == ST_RUNNING;
    }

    // run after a process transitions to ZOMBIE
    void run_orphan_reap_pipeline(long long just_died_pid, long long seq, long long tick) {
        // Phase 1: gather and reparent orphans (children with state RUNNING or ZOMBIE).
        std::vector<long long> children;
        for (const auto& [pid, p] : processes) {
            if (pid == just_died_pid) continue;
            if (p.ppid == just_died_pid &&
                (p.state == ST_RUNNING || p.state == ST_ZOMBIE)) {
                children.push_back(pid);
            }
        }
        std::sort(children.begin(), children.end());
        for (long long child : children) {
            emit(seq, "W_ORPHANED", child);
            orphans_reparented++;
            if (policy.orphan_handling == "reparent_to_init") {
                processes[child].ppid = policy.init_pid;
                if (policy.track_lineage) {
                    lineage_edges.insert({policy.init_pid, child, "reparent_init"});
                }
            }
        }

        // Phase 2: auto-reap reparented zombie children whose new ppid == init_pid.
        if (policy.implicit_init_reap && policy.orphan_handling == "reparent_to_init") {
            for (long long child : children) {
                auto it = processes.find(child);
                if (it == processes.end()) continue;
                if (it->second.state == ST_ZOMBIE && it->second.ppid == policy.init_pid) {
                    it->second.state = ST_EXITED;
                    ReapRecord r;
                    r.parent_pid = policy.init_pid;
                    r.pid        = child;
                    r.seq        = seq;
                    r.tick       = tick;
                    r.trigger    = "init_reap";
                    reap_log.push_back(r);
                    emit(seq, "N_AUTO_REAPED", child);
                }
            }
        }

        // Phase 3: auto-reap the just-died process itself if its ppid is init_pid.
        if (policy.implicit_init_reap) {
            auto it = processes.find(just_died_pid);
            if (it != processes.end() && it->second.state == ST_ZOMBIE &&
                it->second.ppid == policy.init_pid) {
                it->second.state = ST_EXITED;
                ReapRecord r;
                r.parent_pid = policy.init_pid;
                r.pid        = just_died_pid;
                r.seq        = seq;
                r.tick       = tick;
                r.trigger    = "init_reap";
                reap_log.push_back(r);
                emit(seq, "N_AUTO_REAPED", just_died_pid);
            }
        }
    }

    void handle_fork(const Event& ev) {
        long long parent_pid = ev.parent_pid.value_or(-1);
        long long new_pid = ev.pid;
        if (!ev.parent_pid.has_value() || !is_running(parent_pid)) {
            emit(ev.seq, "E_INVALID_PARENT", ev.parent_pid);
            forks_rejected++;
            return;
        }
        if (seen_pids.count(new_pid)) {
            emit(ev.seq, "E_PID_REUSED", new_pid);
            forks_rejected++;
            return;
        }
        Process p;
        p.pid = new_pid;
        p.ppid = parent_pid;
        p.uid = processes.at(parent_pid).uid;
        p.state = ST_RUNNING;
        p.start_tick = ev.tick;
        p.cmdline = ev.cmdline.has_value() ? *ev.cmdline
                                           : processes.at(parent_pid).cmdline;
        processes[new_pid] = p;
        seen_pids.insert(new_pid);
        forks_succeeded++;
        if (policy.track_lineage) {
            lineage_edges.insert({parent_pid, new_pid, "fork"});
        }
        update_max_concurrent();
    }

    void handle_exit(const Event& ev) {
        long long pid = ev.pid;
        auto it = processes.find(pid);
        if (it == processes.end()) {
            emit(ev.seq, "E_INVALID_TARGET", pid);
            return;
        }
        if (it->second.state != ST_RUNNING) {
            emit(ev.seq, "E_DOUBLE_EXIT", pid);
            return;
        }
        it->second.state = ST_ZOMBIE;
        it->second.exit_tick = ev.tick;
        it->second.exit_code = ev.exit_code;
        it->second.exit_signal = std::nullopt;
        it->second.exit_seq = ev.seq;
        run_orphan_reap_pipeline(pid, ev.seq, ev.tick);
        update_max_concurrent();
    }

    void handle_kill(const Event& ev) {
        long long issuer = ev.pid;
        if (!is_running(issuer)) {
            emit(ev.seq, "E_INVALID_TARGET", issuer);
            return;
        }
        if (!ev.target_pid.has_value()) {
            emit(ev.seq, "E_INVALID_TARGET", ev.target_pid);
            return;
        }
        long long target = *ev.target_pid;
        if (!is_running(target)) {
            emit(ev.seq, "E_INVALID_TARGET", target);
            return;
        }
        const std::string& sig = *ev.signal;
        if (sig == "SIGCHLD") {
            return;
        }
        // SIGTERM/SIGKILL/SIGINT
        auto& p = processes.at(target);
        p.state = ST_ZOMBIE;
        p.exit_tick = ev.tick;
        p.exit_code = std::nullopt;
        p.exit_signal = sig;
        p.exit_seq = ev.seq;
        emit(ev.seq, "W_KILLED_BY_SIGNAL", target);
        killed_by_signal++;
        run_orphan_reap_pipeline(target, ev.seq, ev.tick);
        update_max_concurrent();
    }

    void handle_wait(const Event& ev) {
        long long issuer = ev.pid;
        if (!is_running(issuer)) {
            emit(ev.seq, "E_INVALID_TARGET", issuer);
            return;
        }
        long long resolved = -1;
        if (ev.target_pid.has_value()) {
            long long target = *ev.target_pid;
            auto it = processes.find(target);
            if (it == processes.end()) {
                emit(ev.seq, "E_INVALID_TARGET", target);
                return;
            }
            if (it->second.ppid != issuer) {
                emit(ev.seq, "E_NOT_CHILD", target);
                return;
            }
            if (it->second.state == ST_RUNNING) {
                if (policy.wait_on_living_child == "diagnostic") {
                    emit(ev.seq, "E_NOT_ZOMBIE", target);
                }
                return;
            }
            if (it->second.state == ST_EXITED) {
                emit(ev.seq, "E_INVALID_TARGET", target);
                return;
            }
            resolved = target;
        } else {
            std::vector<long long> zombies;
            for (const auto& [pid, p] : processes) {
                if (p.ppid == issuer && p.state == ST_ZOMBIE) {
                    zombies.push_back(pid);
                }
            }
            if (zombies.empty()) {
                emit(ev.seq, "E_NOT_ZOMBIE", std::nullopt);
                return;
            }
            std::sort(zombies.begin(), zombies.end());
            resolved = zombies.front();
        }
        // Reap.
        processes.at(resolved).state = ST_EXITED;
        emit(ev.seq, "N_REAPED", resolved);
        ReapRecord r;
        r.parent_pid = issuer;
        r.pid = resolved;
        r.seq = ev.seq;
        r.tick = ev.tick;
        r.trigger = "wait";
        reap_log.push_back(r);
        update_max_concurrent();
    }

    void handle_exec(const Event& ev) {
        long long issuer = ev.pid;
        if (!is_running(issuer)) {
            emit(ev.seq, "E_INVALID_TARGET", issuer);
            return;
        }
        if (!ev.cmdline.has_value()) {
            // exec without cmdline is invalid input; the schema enforces a
            // string here. Defensive: skip silently.
            return;
        }
        processes.at(issuer).cmdline = *ev.cmdline;
    }

    void run(const std::vector<Process>& initial,
             const std::vector<Event>& events,
             const Policy& pol) {
        policy = pol;
        for (const auto& p : initial) {
            processes[p.pid] = p;
            seen_pids.insert(p.pid);
        }
        update_max_concurrent();
        for (const auto& ev : events) {
            if (ev.op == "fork")      handle_fork(ev);
            else if (ev.op == "exit") handle_exit(ev);
            else if (ev.op == "wait") handle_wait(ev);
            else if (ev.op == "kill") handle_kill(ev);
            else if (ev.op == "exec") handle_exec(ev);
        }
        // End-of-trace W_ZOMBIE_LEAK on every still-zombie process.
        for (const auto& [pid, p] : processes) {
            if (p.state == ST_ZOMBIE) {
                long long s = p.exit_seq.value_or(0);
                emit(s, "W_ZOMBIE_LEAK", pid);
            }
        }
    }
};

// ---------------------------------------------------------------------------
// SCC (Tarjan, iterative) over lineage graph.
// ---------------------------------------------------------------------------

static std::vector<std::vector<long long>> compute_sccs(
        const std::vector<long long>& nodes,
        const std::set<std::pair<long long, long long>>& edges) {
    std::map<long long, std::vector<long long>> out_n;
    for (long long n : nodes) out_n[n] = {};
    for (const auto& [a, b] : edges) {
        if (out_n.count(a)) out_n[a].push_back(b);
    }
    for (auto& [k, v] : out_n) std::sort(v.begin(), v.end());

    std::map<long long, long long> indices;
    std::map<long long, long long> lowlink;
    std::map<long long, bool> on_stack;
    std::vector<long long> stack;
    long long idx_counter = 0;
    std::vector<std::vector<long long>> sccs;

    auto strongconnect = [&](long long start) {
        std::vector<std::pair<long long, size_t>> call_stack;
        call_stack.push_back({start, 0});
        while (!call_stack.empty()) {
            auto& [cur, child_pos] = call_stack.back();
            if (child_pos == 0) {
                indices[cur] = idx_counter;
                lowlink[cur] = idx_counter;
                idx_counter++;
                stack.push_back(cur);
                on_stack[cur] = true;
            }
            const auto& children = out_n[cur];
            if (child_pos < children.size()) {
                long long w = children[child_pos];
                child_pos++;
                if (!indices.count(w)) {
                    call_stack.push_back({w, 0});
                } else if (on_stack[w]) {
                    lowlink[cur] = std::min(lowlink[cur], indices[w]);
                }
            } else {
                if (lowlink[cur] == indices[cur]) {
                    std::vector<long long> scc;
                    while (true) {
                        long long x = stack.back(); stack.pop_back();
                        on_stack[x] = false;
                        scc.push_back(x);
                        if (x == cur) break;
                    }
                    std::sort(scc.begin(), scc.end());
                    sccs.push_back(scc);
                }
                long long my_lowlink = lowlink[cur];
                call_stack.pop_back();
                if (!call_stack.empty()) {
                    auto& [pv, pp] = call_stack.back();
                    (void)pp;
                    lowlink[pv] = std::min(lowlink[pv], my_lowlink);
                }
            }
        }
    };
    for (long long n : nodes) {
        if (!indices.count(n)) strongconnect(n);
    }
    std::vector<std::vector<long long>> result;
    for (const auto& s : sccs) {
        if (s.size() > 1) result.push_back(s);
    }
    std::sort(result.begin(), result.end(),
              [](const std::vector<long long>& a,
                 const std::vector<long long>& b) { return a[0] < b[0]; });
    return result;
}

// ---------------------------------------------------------------------------
// Output writers
// ---------------------------------------------------------------------------

static int severity_rank(const std::string& s) {
    if (s == "error") return 0;
    if (s == "warning") return 1;
    return 2;
}

static ordered_json process_state_doc(const Sim& sim) {
    ordered_json arr = ordered_json::array();
    std::vector<long long> pids;
    for (const auto& [pid, _] : sim.processes) pids.push_back(pid);
    std::sort(pids.begin(), pids.end());
    for (long long pid : pids) {
        const Process& p = sim.processes.at(pid);
        ordered_json o;
        o["cmdline"] = p.cmdline;
        if (p.exit_code.has_value()) o["exit_code"] = *p.exit_code;
        else o["exit_code"] = nullptr;
        if (p.exit_signal.has_value()) o["exit_signal"] = *p.exit_signal;
        else o["exit_signal"] = nullptr;
        if (p.exit_tick.has_value()) o["exit_tick"] = *p.exit_tick;
        else o["exit_tick"] = nullptr;
        o["pid"] = p.pid;
        o["ppid"] = p.ppid;
        o["start_tick"] = p.start_tick;
        o["state"] = p.state;
        o["uid"] = p.uid;
        arr.push_back(o);
    }
    ordered_json doc;
    doc["processes"] = arr;
    return doc;
}

static ordered_json reap_log_doc(const Sim& sim) {
    ordered_json arr = ordered_json::array();
    for (const auto& r : sim.reap_log) {
        ordered_json o;
        o["parent_pid"] = r.parent_pid;
        o["pid"] = r.pid;
        o["seq"] = r.seq;
        o["tick"] = r.tick;
        o["trigger"] = r.trigger;
        arr.push_back(o);
    }
    ordered_json doc;
    doc["reaps"] = arr;
    return doc;
}

static ordered_json diagnostics_doc(const Sim& sim) {
    std::vector<long long> seqs;
    for (const auto& [s, _] : sim.diagnostics) seqs.push_back(s);
    std::sort(seqs.begin(), seqs.end());
    ordered_json events_arr = ordered_json::array();
    for (long long seq : seqs) {
        std::vector<Diagnostic> diags = sim.diagnostics.at(seq);
        std::sort(diags.begin(), diags.end(),
                  [](const Diagnostic& a, const Diagnostic& b) {
                      int ra = severity_rank(a.severity);
                      int rb = severity_rank(b.severity);
                      if (ra != rb) return ra < rb;
                      if (a.code != b.code) return a.code < b.code;
                      // null pid sorts before integer pid.
                      bool a_null = !a.pid.has_value();
                      bool b_null = !b.pid.has_value();
                      if (a_null != b_null) return a_null;
                      if (a_null && b_null) return false;
                      return *a.pid < *b.pid;
                  });
        ordered_json arr = ordered_json::array();
        for (const auto& d : diags) {
            ordered_json o;
            o["code"] = d.code;
            if (d.pid.has_value()) o["pid"] = *d.pid;
            else o["pid"] = nullptr;
            o["severity"] = d.severity;
            arr.push_back(o);
        }
        ordered_json e;
        e["diagnostics"] = arr;
        e["seq"] = seq;
        events_arr.push_back(e);
    }
    ordered_json doc;
    doc["events"] = events_arr;
    return doc;
}

static ordered_json lineage_graph_doc(const Sim& sim) {
    ordered_json doc;
    if (!sim.policy.track_lineage) {
        doc["cycles"] = ordered_json::array();
        doc["edges"] = ordered_json::array();
        doc["nodes"] = ordered_json::array();
        return doc;
    }
    std::set<long long> nodes_set = sim.seen_pids;
    for (const auto& e : sim.lineage_edges) {
        nodes_set.insert(e.from);
        nodes_set.insert(e.to);
    }
    std::vector<long long> nodes_sorted(nodes_set.begin(), nodes_set.end());
    std::sort(nodes_sorted.begin(), nodes_sorted.end());
    std::vector<LineageEdge> edges_sorted(sim.lineage_edges.begin(),
                                          sim.lineage_edges.end());
    std::sort(edges_sorted.begin(), edges_sorted.end());
    std::map<long long, long long> in_count, out_count;
    for (long long n : nodes_sorted) {
        in_count[n] = 0;
        out_count[n] = 0;
    }
    std::set<std::pair<long long, long long>> deduped_pair;
    for (const auto& e : edges_sorted) {
        deduped_pair.insert({e.from, e.to});
    }
    for (const auto& [a, b] : deduped_pair) {
        out_count[a]++;
        in_count[b]++;
    }
    ordered_json node_arr = ordered_json::array();
    for (long long n : nodes_sorted) {
        ordered_json o;
        o["id"] = n;
        o["in_degree"] = in_count[n];
        o["out_degree"] = out_count[n];
        node_arr.push_back(o);
    }
    ordered_json edge_arr = ordered_json::array();
    for (const auto& e : edges_sorted) {
        ordered_json o;
        o["from"] = e.from;
        o["to"] = e.to;
        o["type"] = e.type;
        edge_arr.push_back(o);
    }
    auto cycles = compute_sccs(nodes_sorted, deduped_pair);
    ordered_json cycles_arr = ordered_json::array();
    for (const auto& c : cycles) {
        ordered_json a = ordered_json::array();
        for (long long x : c) a.push_back(x);
        cycles_arr.push_back(a);
    }
    doc["cycles"] = cycles_arr;
    doc["edges"]  = edge_arr;
    doc["nodes"]  = node_arr;
    return doc;
}

static ordered_json summary_doc(const Sim& sim, long long total_events,
                                long long events_with_diagnostics) {
    long long auto_reaped = 0, explicit_reaped = 0;
    for (const auto& r : sim.reap_log) {
        if (r.trigger == "init_reap") auto_reaped++;
        else if (r.trigger == "wait") explicit_reaped++;
    }
    long long final_alive = 0;
    long long zombies = 0;
    std::set<long long> users;
    for (const auto& [_, p] : sim.processes) {
        if (p.state == "RUNNING") {
            final_alive++;
            users.insert(p.uid);
        } else if (p.state == "ZOMBIE") {
            zombies++;
        }
    }
    std::vector<long long> users_sorted(users.begin(), users.end());
    std::sort(users_sorted.begin(), users_sorted.end());
    ordered_json users_arr = ordered_json::array();
    for (long long u : users_sorted) users_arr.push_back(u);
    ordered_json s;
    s["auto_reaped"]              = auto_reaped;
    s["events_with_diagnostics"]  = events_with_diagnostics;
    s["explicit_reaped"]          = explicit_reaped;
    s["final_alive_count"]        = final_alive;
    s["forks_rejected"]           = sim.forks_rejected;
    s["forks_succeeded"]          = sim.forks_succeeded;
    s["killed_by_signal"]         = sim.killed_by_signal;
    s["max_concurrent_processes"] = sim.max_concurrent_processes;
    s["orphans_reparented"]       = sim.orphans_reparented;
    s["total_events"]             = total_events;
    s["users_at_end"]             = users_arr;
    s["zombies_at_end"]           = zombies;
    return s;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

int main(int argc, char** argv) try {
    if (argc != 3) {
        std::cerr << "usage: proctree <data_dir> <out_dir>\n";
        return 1;
    }
    fs::path data_dir = argv[1];
    fs::path out_dir = argv[2];
    if (!fs::exists(data_dir / "processes.json") ||
        !fs::exists(data_dir / "events.json") ||
        !fs::exists(data_dir / "policy.json")) {
        std::cerr << "proctree: missing required input file in " << data_dir << "\n";
        return 2;
    }
    fs::create_directories(out_dir);

    json processes_root = read_json(data_dir / "processes.json");
    json events_root    = read_json(data_dir / "events.json");
    json policy_root    = read_json(data_dir / "policy.json");
    auto initial = parse_processes(processes_root);
    auto events  = parse_events(events_root);
    auto policy  = parse_policy(policy_root);

    Sim sim;
    sim.run(initial, events, policy);

    long long events_with_diagnostics = static_cast<long long>(sim.diagnostics.size());

    write_canonical(out_dir / "process_state.json",
                    sort_recursive(process_state_doc(sim)));
    write_canonical(out_dir / "reap_log.json",
                    sort_recursive(reap_log_doc(sim)));
    write_canonical(out_dir / "process_diagnostics.json",
                    sort_recursive(diagnostics_doc(sim)));
    write_canonical(out_dir / "lineage_graph.json",
                    sort_recursive(lineage_graph_doc(sim)));
    write_canonical(out_dir / "summary.json",
                    sort_recursive(summary_doc(sim,
                        static_cast<long long>(events.size()),
                        events_with_diagnostics)));
    return 0;
} catch (const std::exception& ex) {
    std::cerr << "proctree: " << ex.what() << "\n";
    return 3;
}
CPP

# -------------------------- build --------------------------
g++ -std=c++17 -O2 -Wall -Wextra -I/usr/include \
    /app/src/main.cpp -o /app/build/proctree

# -------------------------- run --------------------------
/app/build/proctree /app/data /app/output
