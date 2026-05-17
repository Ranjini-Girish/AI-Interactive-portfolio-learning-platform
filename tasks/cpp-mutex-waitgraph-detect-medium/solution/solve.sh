#!/bin/bash
set -euo pipefail

mkdir -p /app/src /app/include /app/output

cat > /app/include/types.hpp <<'HPP'
#pragma once
#include <map>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <vector>

using nlohmann::json;
using nlohmann::ordered_json;

struct MutexState {
    std::string name;
    std::optional<std::string> owner;
    std::vector<std::string> waiters;
};

struct Event {
    long long seq{0};
    long long tick{0};
    std::string op;
    std::optional<std::string> mutex;
    std::optional<std::string> task;
};

struct Policy {
    bool fifo_waiters{true};
    bool detect_cycles{false};
    bool note_on_tick{false};
};

struct Diagnostic {
    std::string code;
    std::optional<std::string> mutex;
    std::string severity;
};
HPP

cat > /app/src/main.cpp <<'CPP'
#include "types.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include <tuple>

namespace fs = std::filesystem;

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
    }
    if (j.is_array()) {
        ordered_json out = ordered_json::array();
        for (const auto& e : j) out.push_back(sort_recursive(e));
        return out;
    }
    return ordered_json(j);
}

static void write_canonical(const fs::path& p, const ordered_json& payload) {
    std::ostringstream oss;
    oss << payload.dump(2, ' ', true);
    std::string text = oss.str();
    text.push_back('\n');
    std::ofstream f(p, std::ios::binary);
    f.write(text.data(), static_cast<std::streamsize>(text.size()));
}

static std::map<std::string, std::string> load_severities() {
    return {
        {"E_UNKNOWN_MUTEX", "error"},
        {"E_BLOCKED", "error"},
        {"E_BUSY_TRY", "error"},
        {"E_IDLE", "error"},
        {"E_WRONG_OWNER", "error"},
        {"W_CYCLE", "warning"},
        {"N_TICK", "note"},
        {"N_ACQUIRE", "note"},
        {"N_WAKE", "note"},
    };
}

static int severity_rank(const std::string& s) {
    if (s == "error") return 0;
    if (s == "warning") return 1;
    return 2;
}

static bool detects_cycle(const std::map<std::string, MutexState>& mutexes,
                          const std::string& blocker, const std::string& mutex_name) {
    auto it = mutexes.find(mutex_name);
    if (it == mutexes.end() || !it->second.owner.has_value()) return false;
    const std::string& owner = *it->second.owner;
    std::map<std::string, std::set<std::string>> adj;
    for (const auto& [_, m] : mutexes) {
        if (!m.owner.has_value()) continue;
        for (const auto& w : m.waiters) adj[w].insert(*m.owner);
    }
    adj[blocker].insert(owner);
    std::vector<std::string> stack = {owner};
    std::set<std::string> visited = {owner};
    while (!stack.empty()) {
        std::string cur = stack.back();
        stack.pop_back();
        if (cur == blocker) return true;
        for (const auto& nxt : adj[cur]) {
            if (!visited.count(nxt)) {
                visited.insert(nxt);
                stack.push_back(nxt);
            }
        }
    }
    return false;
}

struct Sim {
    std::map<std::string, MutexState> mutexes;
    Policy policy;
    std::map<long long, std::vector<Diagnostic>> diagnostics;
    std::vector<json> actions;
    long long acquires_ok = 0;
    long long acquires_blocked = 0;
    long long try_rejected = 0;
    long long releases = 0;
    long long wakes = 0;
    long long cycles_detected = 0;
    long long ticks = 0;
    std::map<std::string, std::string> sev;

    explicit Sim(std::map<std::string, std::string> s) : sev(std::move(s)) {}

    void emit(long long seq, const std::string& code, std::optional<std::string> mutex) {
        Diagnostic d;
        d.code = code;
        d.mutex = mutex;
        d.severity = sev.at(code);
        diagnostics[seq].push_back(d);
    }

    std::vector<json> wait_edges() const {
        std::vector<json> edges;
        for (const auto& [mname, m] : mutexes) {
            if (!m.owner.has_value()) continue;
            for (const auto& w : m.waiters) {
                json e;
                e["mutex"] = mname;
                e["owner"] = *m.owner;
                e["waiter"] = w;
                edges.push_back(e);
            }
        }
        std::sort(edges.begin(), edges.end(), [](const json& a, const json& b) {
            if (a["waiter"].get<std::string>() != b["waiter"].get<std::string>())
                return a["waiter"].get<std::string>() < b["waiter"].get<std::string>();
            return a["mutex"].get<std::string>() < b["mutex"].get<std::string>();
        });
        return edges;
    }

    void run_acquire(const Event& ev) {
        if (!ev.mutex.has_value()) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        const std::string& name = *ev.mutex;
        if (!mutexes.count(name)) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        MutexState& m = mutexes.at(name);
        if (!m.owner.has_value()) {
            m.owner = ev.task;
            acquires_ok++;
            emit(ev.seq, "N_ACQUIRE", ev.mutex);
            json row;
            row["mutex"] = name;
            row["op"] = "acquire";
            row["seq"] = ev.seq;
            row["task"] = *ev.task;
            row["tick"] = ev.tick;
            actions.push_back(row);
        } else {
            m.waiters.push_back(*ev.task);
            acquires_blocked++;
            emit(ev.seq, "E_BLOCKED", ev.mutex);
            if (policy.detect_cycles && detects_cycle(mutexes, *ev.task, name)) {
                cycles_detected++;
                emit(ev.seq, "W_CYCLE", ev.mutex);
            }
        }
    }

    void run_try_acquire(const Event& ev) {
        if (!ev.mutex.has_value() || !ev.task.has_value()) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        const std::string& name = *ev.mutex;
        if (!mutexes.count(name)) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        MutexState& m = mutexes.at(name);
        if (!m.owner.has_value()) {
            m.owner = ev.task;
            acquires_ok++;
            emit(ev.seq, "N_ACQUIRE", ev.mutex);
            json row;
            row["mutex"] = name;
            row["op"] = "try_acquire";
            row["seq"] = ev.seq;
            row["task"] = *ev.task;
            row["tick"] = ev.tick;
            actions.push_back(row);
        } else {
            try_rejected++;
            emit(ev.seq, "E_BUSY_TRY", ev.mutex);
        }
    }

    void run_release(const Event& ev) {
        if (!ev.mutex.has_value() || !ev.task.has_value()) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        const std::string& name = *ev.mutex;
        if (!mutexes.count(name)) {
            emit(ev.seq, "E_UNKNOWN_MUTEX", ev.mutex);
            return;
        }
        MutexState& m = mutexes.at(name);
        if (!m.owner.has_value()) {
            emit(ev.seq, "E_IDLE", ev.mutex);
            return;
        }
        if (*ev.task != *m.owner) {
            emit(ev.seq, "E_WRONG_OWNER", ev.mutex);
            return;
        }
        m.owner = std::nullopt;
        releases++;
        json row;
        row["mutex"] = name;
        row["op"] = "release";
        row["seq"] = ev.seq;
        row["task"] = *ev.task;
        row["tick"] = ev.tick;
        actions.push_back(row);
        if (!m.waiters.empty()) {
            std::string next_task;
            if (policy.fifo_waiters) {
                next_task = m.waiters.front();
                m.waiters.erase(m.waiters.begin());
            } else {
                next_task = m.waiters.back();
                m.waiters.pop_back();
            }
            m.owner = next_task;
            wakes++;
            emit(ev.seq, "N_WAKE", ev.mutex);
            json wake;
            wake["mutex"] = name;
            wake["op"] = "wake";
            wake["seq"] = ev.seq;
            wake["task"] = next_task;
            wake["tick"] = ev.tick;
            actions.push_back(wake);
        }
    }
};

int main(int argc, char** argv) try {
    if (argc != 3) {
        std::cerr << "usage: mtxgraph <data_dir> <out_dir>\n";
        return 1;
    }
    fs::path data_dir = argv[1];
    fs::path out_dir = argv[2];
    for (const char* name : {"mutexes.json", "events.json", "policy.json"}) {
        if (!fs::exists(data_dir / name)) {
            std::cerr << "mtxgraph: missing " << name << "\n";
            return 2;
        }
    }
    fs::create_directories(out_dir);

    json mutexes_root = read_json(data_dir / "mutexes.json");
    json events_root = read_json(data_dir / "events.json");
    json policy_root = read_json(data_dir / "policy.json");

    Sim sim(load_severities());
    sim.policy.fifo_waiters = policy_root.at("fifo_waiters").get<bool>();
    sim.policy.detect_cycles = policy_root.at("detect_cycles").get<bool>();
    sim.policy.note_on_tick = policy_root.at("note_on_tick").get<bool>();

    for (const auto& row : mutexes_root.at("mutexes")) {
        MutexState m;
        m.name = row.at("name").get<std::string>();
        if (row.at("owner").is_null()) m.owner = std::nullopt;
        else m.owner = row.at("owner").get<std::string>();
        sim.mutexes[m.name] = m;
    }

    const auto& events = events_root.at("events");
    for (size_t i = 0; i < events.size(); ++i) {
        const auto& e = events.at(i);
        if (e.at("seq").get<long long>() != static_cast<long long>(i)) {
            throw std::runtime_error("seq not dense");
        }
        Event ev;
        ev.seq = e.at("seq").get<long long>();
        ev.tick = e.at("tick").get<long long>();
        if (ev.tick < 0) throw std::runtime_error("tick must be >= 0");
        ev.op = e.at("op").get<std::string>();
        if (!e.at("mutex").is_null()) ev.mutex = e.at("mutex").get<std::string>();
        if (!e.at("task").is_null()) ev.task = e.at("task").get<std::string>();

        if (ev.op == "tick") {
            sim.ticks++;
            if (sim.policy.note_on_tick) sim.emit(ev.seq, "N_TICK", std::nullopt);
        } else if (ev.op == "acquire") {
            if (!ev.task.has_value()) throw std::runtime_error("acquire needs task");
            sim.run_acquire(ev);
        } else if (ev.op == "try_acquire") {
            sim.run_try_acquire(ev);
        } else if (ev.op == "release") {
            sim.run_release(ev);
        } else {
            throw std::runtime_error("unknown op");
        }
    }

    ordered_json mutex_arr = ordered_json::array();
    std::vector<std::string> names;
    for (const auto& [n, _] : sim.mutexes) names.push_back(n);
    std::sort(names.begin(), names.end());
    for (const auto& n : names) {
        const MutexState& m = sim.mutexes.at(n);
        ordered_json o;
        o["name"] = m.name;
        if (m.owner.has_value()) o["owner"] = *m.owner;
        else o["owner"] = nullptr;
        mutex_arr.push_back(o);
    }
    ordered_json mutex_state;
    mutex_state["mutexes"] = mutex_arr;

    ordered_json edge_arr = ordered_json::array();
    for (const auto& e : sim.wait_edges()) edge_arr.push_back(sort_recursive(e));
    ordered_json wait_edges;
    wait_edges["edges"] = edge_arr;

    ordered_json action_arr = ordered_json::array();
    for (const auto& row : sim.actions) action_arr.push_back(sort_recursive(row));
    ordered_json action_log;
    action_log["actions"] = action_arr;

    ordered_json diag_events = ordered_json::array();
    for (const auto& [seq, diags] : sim.diagnostics) {
        std::vector<Diagnostic> sorted = diags;
        std::sort(sorted.begin(), sorted.end(),
                  [](const Diagnostic& a, const Diagnostic& b) {
                      int ra = severity_rank(a.severity);
                      int rb = severity_rank(b.severity);
                      if (ra != rb) return ra < rb;
                      if (a.code != b.code) return a.code < b.code;
                      bool a_null = !a.mutex.has_value();
                      bool b_null = !b.mutex.has_value();
                      if (a_null != b_null) return a_null;
                      if (a_null) return false;
                      return *a.mutex < *b.mutex;
                  });
        ordered_json arr = ordered_json::array();
        for (const auto& d : sorted) {
            ordered_json o;
            o["code"] = d.code;
            if (d.mutex.has_value()) o["mutex"] = *d.mutex;
            else o["mutex"] = nullptr;
            o["severity"] = d.severity;
            arr.push_back(o);
        }
        ordered_json ev;
        ev["diagnostics"] = arr;
        ev["seq"] = seq;
        diag_events.push_back(ev);
    }
    ordered_json diagnostics;
    diagnostics["events"] = diag_events;

    ordered_json summary;
    summary["acquires_blocked"] = sim.acquires_blocked;
    summary["acquires_succeeded"] = sim.acquires_ok;
    summary["cycles_detected"] = sim.cycles_detected;
    summary["releases"] = sim.releases;
    summary["ticks"] = sim.ticks;
    summary["total_events"] = static_cast<long long>(events.size());
    summary["try_acquire_rejected"] = sim.try_rejected;
    summary["wakes_from_queue"] = sim.wakes;

    write_canonical(out_dir / "mutex_state.json", sort_recursive(mutex_state));
    write_canonical(out_dir / "wait_edges.json", sort_recursive(wait_edges));
    write_canonical(out_dir / "action_log.json", sort_recursive(action_log));
    write_canonical(out_dir / "diagnostics.json", sort_recursive(diagnostics));
    write_canonical(out_dir / "summary.json", sort_recursive(summary));
    return 0;
} catch (const std::exception& ex) {
    std::cerr << "mtxgraph: " << ex.what() << "\n";
    return 3;
}
CPP

make -C /app/environment build
