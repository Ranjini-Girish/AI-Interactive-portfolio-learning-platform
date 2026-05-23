#!/usr/bin/env bash
# Reference oracle for cpp-leaky-bucket-shaper-replay-medium.
set -euo pipefail

INCLUDE_DIR="/app/include"
SRC_DIR="/app/src"
BUILD_DIR="/app/build"
DATA_DIR="/app/data"
OUT_DIR="/app/output"
BINARY="${BUILD_DIR}/shaper"

mkdir -p "${INCLUDE_DIR}" "${SRC_DIR}" "${BUILD_DIR}" "${OUT_DIR}"

cat > "${INCLUDE_DIR}/types.hpp" <<'HPP_EOF'
#pragma once
#include <cstdint>
#include <string>
#include <vector>

namespace shaper {

using u32 = std::uint32_t;
using u64 = std::uint64_t;

struct Bucket {
    u64 capacity_bytes;
    u64 leak_bytes_per_tick;
    u64 current_bytes;
};

struct Admit {
    std::string bucket_id;
    u64 level_after;
    u64 seq;
    u64 size_bytes;
};

struct Diag {
    u64 seq;
    std::string code;
    std::string severity;
    std::string bucket_id;
    std::string detail;
};

struct Policy {
    bool count_dropped_bytes;
    bool track_admits;
};

}  // namespace shaper
HPP_EOF

cat > "${SRC_DIR}/main.cpp" <<'CPP_EOF'
#include "../include/types.hpp"

#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <map>
#include <nlohmann/json.hpp>
#include <set>
#include <sstream>
#include <string>
#include <vector>

using json = nlohmann::json;

namespace {

[[noreturn]] void die(const std::string& m) {
    std::cerr << "shaper: " << m << '\n';
    std::exit(1);
}

const std::set<std::string>& valid_event_types() {
    static const std::set<std::string> S{"submit", "tick", "reconfigure"};
    return S;
}

int sev_rank(const std::string& s) {
    if (s == "error") return 3;
    if (s == "warn") return 2;
    if (s == "note") return 1;
    return 0;
}

bool id_chars_ok(const std::string& s) {
    if (s.empty() || s.size() > 32) return false;
    for (char c : s) {
        bool ok = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                  (c >= '0' && c <= '9') || c == '.' || c == '_' || c == '-';
        if (!ok) return false;
    }
    return true;
}

void check_keys(const json& obj, const std::vector<std::string>& need, const std::string& ctx) {
    if (!obj.is_object()) die(ctx + ": not object");
    if (obj.size() != need.size()) die(ctx + ": wrong key count");
    for (const auto& k : need) if (!obj.contains(k)) die(ctx + ": missing " + k);
}

shaper::u64 require_uint(const json& v, shaper::u64 max_val, const std::string& ctx) {
    if (!v.is_number_integer()) die(ctx + ": not integer");
    long long n = v.get<long long>();
    if (n < 0) die(ctx + ": negative");
    if ((shaper::u64)n > max_val) die(ctx + ": too large");
    return (shaper::u64)n;
}

std::string require_string(const json& v, const std::string& ctx) {
    if (!v.is_string()) die(ctx + ": not string");
    return v.get<std::string>();
}

bool require_bool(const json& v, const std::string& ctx) {
    if (!v.is_boolean()) die(ctx + ": not bool");
    return v.get<bool>();
}

json load_json(const std::string& p) {
    std::ifstream f(p);
    if (!f) die("cannot open " + p);
    json j;
    try { f >> j; } catch (std::exception& e) { die(std::string("parse ") + p + ": " + e.what()); }
    return j;
}

void parse_buckets(const json& jp, std::map<std::string, shaper::Bucket>& out) {
    check_keys(jp, {"buckets"}, "buckets_root");
    if (!jp["buckets"].is_array() || jp["buckets"].empty())
        die("buckets: must be non-empty array");
    for (auto& e : jp["buckets"]) {
        check_keys(e, {"bucket_id", "capacity_bytes", "leak_bytes_per_tick"}, "bucket");
        std::string id = require_string(e["bucket_id"], "bucket_id");
        if (!id_chars_ok(id)) die("invalid bucket_id: " + id);
        shaper::u64 cap = require_uint(e["capacity_bytes"], 1000000000ull, "capacity_bytes");
        if (cap < 1) die("capacity_bytes < 1");
        shaper::u64 leak = require_uint(e["leak_bytes_per_tick"], 1000000000ull, "leak_bytes_per_tick");
        if (out.count(id)) die("duplicate bucket_id: " + id);
        out[id] = {cap, leak, 0};
    }
}

shaper::Policy parse_policy(const json& jp) {
    check_keys(jp, {"count_dropped_bytes", "track_admits"}, "policy");
    shaper::Policy p;
    p.count_dropped_bytes = require_bool(jp["count_dropped_bytes"], "count_dropped_bytes");
    p.track_admits = require_bool(jp["track_admits"], "track_admits");
    return p;
}

struct Sim {
    std::map<std::string, shaper::Bucket> buckets;
    shaper::Policy policy{};
    shaper::u64 now_ticks = 0;
    std::vector<shaper::Admit> admits;
    std::vector<shaper::Diag> diagnostics;
    shaper::u64 dropped_bytes_total = 0;
    shaper::u64 overflow_drops_total = 0;

    void emit_diag(shaper::u64 seq, const std::string& code, const std::string& severity,
                   const std::string& bid, const std::string& detail) {
        diagnostics.push_back({seq, code, severity, bid, detail});
    }

    void on_submit(shaper::u64 seq, const json& ev) {
        check_keys(ev, {"bucket_id", "seq", "size_bytes", "type"}, "submit");
        std::string bid = require_string(ev["bucket_id"], "bucket_id");
        if (!id_chars_ok(bid)) die("invalid bucket_id in submit: " + bid);
        shaper::u64 sz = require_uint(ev["size_bytes"], 1000000000ull, "size_bytes");
        if (sz < 1) die("size_bytes < 1");
        auto it = buckets.find(bid);
        if (it == buckets.end()) {
            emit_diag(seq, "E_UNKNOWN_BUCKET", "error", bid, "");
            return;
        }
        auto& b = it->second;
        if (b.current_bytes + sz <= b.capacity_bytes) {
            b.current_bytes += sz;
            admits.push_back({bid, b.current_bytes, seq, sz});
            emit_diag(seq, "N_ADMITTED", "note", bid, std::to_string(sz));
        } else {
            emit_diag(seq, "W_DROPPED_OVERFLOW", "warn", bid, std::to_string(sz));
            overflow_drops_total++;
            if (policy.count_dropped_bytes) dropped_bytes_total += sz;
        }
    }

    void on_tick(shaper::u64 /*seq*/, const json& ev) {
        check_keys(ev, {"seq", "type"}, "tick");
        now_ticks++;
        for (auto& [bid, b] : buckets) {
            (void)bid;
            if (b.current_bytes >= b.leak_bytes_per_tick)
                b.current_bytes -= b.leak_bytes_per_tick;
            else
                b.current_bytes = 0;
        }
    }

    void on_reconfigure(shaper::u64 seq, const json& ev) {
        check_keys(ev, {"bucket_id", "new_capacity_bytes", "new_leak_bytes_per_tick", "seq", "type"}, "reconfigure");
        std::string bid = require_string(ev["bucket_id"], "bucket_id");
        if (!id_chars_ok(bid)) die("invalid bucket_id in reconfigure: " + bid);
        shaper::u64 nc = require_uint(ev["new_capacity_bytes"], 1000000000ull, "new_capacity_bytes");
        if (nc < 1) die("new_capacity_bytes < 1");
        shaper::u64 nl = require_uint(ev["new_leak_bytes_per_tick"], 1000000000ull, "new_leak_bytes_per_tick");
        if (!buckets.count(bid)) die("unknown bucket in reconfigure: " + bid);
        auto& b = buckets[bid];
        shaper::u64 old_cap = b.capacity_bytes;
        shaper::u64 old_leak = b.leak_bytes_per_tick;
        if (nc == old_cap && nl == old_leak) {
            emit_diag(seq, "W_RECONFIG_NOOP", "warn", bid, bid);
            return;
        }
        shaper::u64 old_level = b.current_bytes;
        b.capacity_bytes = nc;
        b.leak_bytes_per_tick = nl;
        if (nc < old_level) {
            b.current_bytes = nc;
            emit_diag(seq, "W_CAPACITY_REDUCED", "warn", bid,
                      std::to_string(old_level) + "->" + std::to_string(nc));
        }
    }

    void step(const json& ev, shaper::u64 expected_seq) {
        if (!ev.is_object() || !ev.contains("seq") || !ev.contains("type"))
            die("event missing seq/type");
        shaper::u64 seq = require_uint(ev["seq"], 0xFFFFFFFFu, "seq");
        if (seq != expected_seq) die("non-dense seq");
        std::string t = require_string(ev["type"], "type");
        if (!valid_event_types().count(t)) die("bad type: " + t);
        if (t == "submit") on_submit(seq, ev);
        else if (t == "tick") on_tick(seq, ev);
        else on_reconfigure(seq, ev);
    }
};

std::string canonical_dump(const json& j) {
    std::string s = j.dump(2, ' ', true);
    s.push_back('\n');
    return s;
}

void write_canonical(const std::string& path, const json& j) {
    std::ofstream f(path);
    if (!f) die("cannot open output: " + path);
    f << canonical_dump(j);
    if (!f) die("write error: " + path);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: shaper <input_dir> <output_dir>\n";
        return 2;
    }
    std::string in_dir = argv[1];
    std::string out_dir = argv[2];

    json b_j = load_json(in_dir + "/buckets.json");
    json ev_j = load_json(in_dir + "/events.json");
    json pol_j = load_json(in_dir + "/policy.json");

    Sim sim;
    parse_buckets(b_j, sim.buckets);
    sim.policy = parse_policy(pol_j);

    check_keys(ev_j, {"events"}, "events_root");
    if (!ev_j["events"].is_array()) die("events: not array");
    shaper::u64 expected = 0;
    for (const auto& ev : ev_j["events"]) {
        sim.step(ev, expected);
        expected++;
    }

    json bs_out;
    {
        std::vector<std::string> ids;
        for (const auto& [k, _] : sim.buckets) ids.push_back(k);
        std::sort(ids.begin(), ids.end());
        json arr = json::array();
        for (const auto& id : ids) {
            const auto& b = sim.buckets[id];
            json row;
            row["bucket_id"] = id;
            row["capacity_bytes"] = b.capacity_bytes;
            row["current_bytes"] = b.current_bytes;
            row["leak_bytes_per_tick"] = b.leak_bytes_per_tick;
            arr.push_back(row);
        }
        bs_out["buckets"] = arr;
    }

    json ad_out;
    {
        std::vector<shaper::Admit> av = sim.policy.track_admits
            ? sim.admits : std::vector<shaper::Admit>{};
        std::sort(av.begin(), av.end(),
                  [](const shaper::Admit& a, const shaper::Admit& b) {
                      if (a.seq != b.seq) return a.seq < b.seq;
                      return a.bucket_id < b.bucket_id;
                  });
        json arr = json::array();
        for (const auto& a : av) {
            json row;
            row["bucket_id"] = a.bucket_id;
            row["level_after"] = a.level_after;
            row["seq"] = a.seq;
            row["size_bytes"] = a.size_bytes;
            arr.push_back(row);
        }
        ad_out["admits"] = arr;
    }

    json diag_out;
    {
        std::sort(sim.diagnostics.begin(), sim.diagnostics.end(),
                  [](const shaper::Diag& a, const shaper::Diag& b) {
                      if (a.seq != b.seq) return a.seq < b.seq;
                      int ra = sev_rank(a.severity), rb = sev_rank(b.severity);
                      if (ra != rb) return ra > rb;
                      if (a.code != b.code) return a.code < b.code;
                      if (a.bucket_id != b.bucket_id) return a.bucket_id < b.bucket_id;
                      return a.detail < b.detail;
                  });
        json arr = json::array();
        for (const auto& d : sim.diagnostics) {
            json row;
            row["bucket_id"] = d.bucket_id;
            row["code"] = d.code;
            row["detail"] = d.detail;
            row["seq"] = d.seq;
            row["severity"] = d.severity;
            arr.push_back(row);
        }
        diag_out["diagnostics"] = arr;
    }

    json sum_out;
    {
        shaper::u64 cur_total = 0;
        for (const auto& [_, b] : sim.buckets) cur_total += b.current_bytes;
        sum_out["admits_total"] = (shaper::u64)sim.admits.size();
        sum_out["buckets_total"] = (shaper::u64)sim.buckets.size();
        sum_out["current_bytes_total"] = cur_total;
        sum_out["dropped_bytes_total"] = sim.dropped_bytes_total;
        sum_out["events_total"] = (shaper::u64)ev_j["events"].size();
        if (ev_j["events"].empty()) sum_out["max_seq"] = nullptr;
        else sum_out["max_seq"] = expected - 1;
        sum_out["now_ticks_final"] = sim.now_ticks;
        sum_out["overflow_drops_total"] = sim.overflow_drops_total;
    }

    write_canonical(out_dir + "/bucket_state.json", bs_out);
    write_canonical(out_dir + "/admits.json", ad_out);
    write_canonical(out_dir + "/shaper_diagnostics.json", diag_out);
    write_canonical(out_dir + "/summary.json", sum_out);
    return 0;
}
CPP_EOF

g++ -std=c++17 -O2 -Wall -Wextra -I"${INCLUDE_DIR}" "${SRC_DIR}/main.cpp" -o "${BINARY}"

"${BINARY}" "${DATA_DIR}" "${OUT_DIR}"
