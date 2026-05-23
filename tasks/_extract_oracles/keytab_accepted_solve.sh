#!/bin/bash
set -euo pipefail

mkdir -p /app/audit

cat << 'CPPEOF' > /tmp/oracle.cpp
#include <nlohmann/json.hpp>
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace fs = std::filesystem;
using json = nlohmann::json;

// ---------- SHA-256 (self-contained) ----------
struct Sha256 {
    uint32_t s[8];
    uint64_t bits = 0;
    uint8_t buf[64];
    size_t buf_len = 0;
    Sha256() { reset(); }
    void reset() {
        s[0]=0x6a09e667; s[1]=0xbb67ae85; s[2]=0x3c6ef372; s[3]=0xa54ff53a;
        s[4]=0x510e527f; s[5]=0x9b05688c; s[6]=0x1f83d9ab; s[7]=0x5be0cd19;
        bits = 0; buf_len = 0;
    }
    static uint32_t rr(uint32_t x, int n) { return (x>>n)|(x<<(32-n)); }
    void process(const uint8_t* p) {
        static const uint32_t K[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for (int i=0;i<16;i++) w[i] = (uint32_t(p[i*4])<<24)|(uint32_t(p[i*4+1])<<16)|(uint32_t(p[i*4+2])<<8)|uint32_t(p[i*4+3]);
        for (int i=16;i<64;i++) {
            uint32_t s0 = rr(w[i-15],7)^rr(w[i-15],18)^(w[i-15]>>3);
            uint32_t s1 = rr(w[i-2],17)^rr(w[i-2],19)^(w[i-2]>>10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        uint32_t a=s[0],b=s[1],c=s[2],d=s[3],e=s[4],f=s[5],g=s[6],h=s[7];
        for (int i=0;i<64;i++) {
            uint32_t S1 = rr(e,6)^rr(e,11)^rr(e,25);
            uint32_t ch = (e & f) ^ ((~e) & g);
            uint32_t t1 = h + S1 + ch + K[i] + w[i];
            uint32_t S0 = rr(a,2)^rr(a,13)^rr(a,22);
            uint32_t mj = (a & b) ^ (a & c) ^ (b & c);
            uint32_t t2 = S0 + mj;
            h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        s[0]+=a; s[1]+=b; s[2]+=c; s[3]+=d; s[4]+=e; s[5]+=f; s[6]+=g; s[7]+=h;
    }
    void update(const uint8_t* data, size_t len) {
        bits += uint64_t(len) * 8;
        while (len > 0) {
            size_t take = std::min(len, size_t(64) - buf_len);
            std::memcpy(buf + buf_len, data, take);
            buf_len += take; data += take; len -= take;
            if (buf_len == 64) { process(buf); buf_len = 0; }
        }
    }
    std::string hex() {
        uint8_t pad[64] = {0x80};
        size_t pad_len = (buf_len < 56) ? (56 - buf_len) : (120 - buf_len);
        uint8_t lenbe[8];
        for (int i=0;i<8;i++) lenbe[7-i] = uint8_t(bits >> (i*8));
        update(pad, pad_len);
        update(lenbe, 8);
        std::ostringstream o;
        for (int i=0;i<8;i++) o << std::hex << std::setw(8) << std::setfill('0') << s[i];
        return o.str();
    }
};

static std::string sha256_hex(const std::string& bytes) {
    Sha256 h;
    h.update(reinterpret_cast<const uint8_t*>(bytes.data()), bytes.size());
    return h.hex();
}

// ---------- Types ----------
struct Principal {
    std::string name;
    std::string tier;
    bool exempt = false;
    std::optional<int> override_rotation_days;
};

struct KeytabEvent {
    std::string event_id;
    std::string kind; // add | revoke | retire
    std::string principal;
    int kvno = 0;
    int day = 0;
    int hour = 0;
    std::string enctype;
    std::string reason;
};

struct TgsRequest {
    std::string request_id;
    std::string principal;
    int kvno = 0;
    int day = 0;
    int hour = 0;
};

struct KvnoRecord {
    int kvno = 0;
    int added_day = 0;
    int added_hour = 0;
    std::string enctype;
    std::optional<int> revoked_day;
    std::optional<int> revoked_hour;
    std::optional<std::string> revoke_reason;
    std::optional<int> retired_day;
    std::optional<int> retired_hour;
    std::string final_state = "active";
};

struct PolicyVersion {
    std::string version;
    int effective_day = 0;
    std::set<std::string> allowed;
    std::set<std::string> forbidden;
};

struct Anomaly {
    std::string kind;
    std::string severity;
    std::string principal;
    std::optional<int> kvno;
    int day = 0;
    int hour = 0;
};

// ---------- IO ----------
static json read_json(const fs::path& p) {
    std::ifstream f(p);
    if (!f) throw std::runtime_error("cannot open " + p.string());
    json j; f >> j; return j;
}

static std::vector<json> read_jsonl(const fs::path& p) {
    std::vector<json> out;
    std::ifstream f(p);
    if (!f) throw std::runtime_error("cannot open " + p.string());
    std::string line;
    while (std::getline(f, line)) {
        if (line.empty()) continue;
        out.push_back(json::parse(line));
    }
    return out;
}

static void write_json_atomic(const fs::path& p, const json& j) {
    std::string s = j.dump(2);
    std::ofstream f(p, std::ios::binary);
    f << s << "\n";
}

static int severity_rank(const std::string& s) {
    if (s == "critical") return 0;
    if (s == "high")     return 1;
    if (s == "medium")   return 2;
    if (s == "low")      return 3;
    return 4;
}

static std::string anomaly_id(const Anomaly& a) {
    json j;
    j["day"] = a.day;
    j["hour"] = a.hour;
    j["kind"] = a.kind;
    if (a.kvno) j["kvno"] = *a.kvno; else j["kvno"] = nullptr;
    j["principal"] = a.principal;
    return sha256_hex(j.dump());
}

static std::string anomaly_details(const Anomaly& a) {
    if (!a.kvno) return a.kind + " on " + a.principal;
    return a.kind + " on " + a.principal + " kvno=" + std::to_string(*a.kvno);
}

int main() {
    const fs::path DATA = "/app/data";
    const fs::path OUT  = "/app/audit";

    // ---- Inputs ----
    json pool = read_json(DATA / "pool_state.json");
    int current_day = pool["current_day"].get<int>();
    int current_hour = pool["current_hour"].get<int>();

    json rotpol = read_json(DATA / "policies" / "rotation_policy.json");
    int cross_fade_hours = rotpol["cross_fade_hours"].get<int>();
    std::map<std::string,int> tier_windows;
    for (auto& [k,v] : rotpol["tier_windows"].items()) tier_windows[k] = v.get<int>();

    json encpol = read_json(DATA / "policies" / "enctype_policy.json");
    std::vector<PolicyVersion> policies;
    for (auto& v : encpol["versions"]) {
        PolicyVersion pv;
        pv.version = v["version"].get<std::string>();
        pv.effective_day = v["effective_day"].get<int>();
        for (auto& e : v["allowed_enctypes"]) pv.allowed.insert(e.get<std::string>());
        for (auto& e : v["forbidden_enctypes"]) pv.forbidden.insert(e.get<std::string>());
        policies.push_back(pv);
    }
    std::sort(policies.begin(), policies.end(),
        [](const PolicyVersion& a, const PolicyVersion& b){ return a.effective_day < b.effective_day; });

    auto policy_at = [&](int d) -> const PolicyVersion* {
        const PolicyVersion* best = nullptr;
        for (const auto& pv : policies) {
            if (pv.effective_day <= d) {
                if (!best || pv.effective_day > best->effective_day) best = &pv;
            }
        }
        return best;
    };
    auto enctype_allowed_at = [&](const std::string& enc, int d) -> bool {
        const PolicyVersion* pv = policy_at(d);
        if (!pv) return true;
        if (pv->forbidden.count(enc)) return false;
        return pv->allowed.count(enc) > 0;
    };

    std::map<std::string, Principal> principals;
    for (const auto& entry : fs::directory_iterator(DATA / "principals")) {
        if (!entry.is_regular_file()) continue;
        json j = read_json(entry.path());
        Principal p;
        p.name = j["principal"].get<std::string>();
        p.tier = j["tier"].get<std::string>();
        p.exempt = j["exempt"].get<bool>();
        if (j.contains("override_rotation_days") && !j["override_rotation_days"].is_null())
            p.override_rotation_days = j["override_rotation_days"].get<int>();
        principals[p.name] = p;
    }

    std::vector<KeytabEvent> all_keytab;
    int total_keytab_events = 0;
    int invalid_keytab_events = 0;
    {
        std::vector<json> raw;
        for (const auto& entry : fs::directory_iterator(DATA / "events")) {
            if (!entry.is_regular_file()) continue;
            std::string name = entry.path().filename().string();
            if (name.rfind("keytab_chunk_", 0) != 0) continue;
            auto v = read_jsonl(entry.path());
            for (auto& j : v) raw.push_back(j);
        }
        total_keytab_events = static_cast<int>(raw.size());
        std::set<std::string> seen_ids;
        std::set<std::string> kvalid{"add","revoke","retire"};
        std::set<std::string> rvalid{"compromise","expired","policy_violation","administrative"};
        for (auto& j : raw) {
            try {
                std::string eid = j.at("event_id").get<std::string>();
                std::string kind = j.at("kind").get<std::string>();
                std::string princ = j.at("principal").get<std::string>();
                int kvno = j.at("kvno").get<int>();
                int day = j.at("day").get<int>();
                int hour = j.at("hour").get<int>();
                if (eid.empty()) throw std::runtime_error("");
                if (seen_ids.count(eid)) throw std::runtime_error("");
                if (!kvalid.count(kind)) throw std::runtime_error("");
                if (!principals.count(princ)) throw std::runtime_error("");
                if (kvno < 1 || kvno > 99999) throw std::runtime_error("");
                if (day < 0) throw std::runtime_error("");
                if (hour < 0 || hour > 23) throw std::runtime_error("");
                if (day > current_day || (day == current_day && hour > current_hour)) throw std::runtime_error("");
                KeytabEvent e;
                e.event_id = eid; e.kind = kind; e.principal = princ;
                e.kvno = kvno; e.day = day; e.hour = hour;
                if (kind == "add") {
                    e.enctype = j.at("enctype").get<std::string>();
                    if (e.enctype.empty()) throw std::runtime_error("");
                } else if (kind == "revoke") {
                    e.reason = j.at("reason").get<std::string>();
                    if (!rvalid.count(e.reason)) throw std::runtime_error("");
                }
                seen_ids.insert(eid);
                all_keytab.push_back(e);
            } catch (...) {
                invalid_keytab_events++;
            }
        }
    }

    std::vector<TgsRequest> all_tgs;
    int total_tgs_requests = 0;
    int invalid_tgs_requests = 0;
    {
        std::vector<json> raw;
        for (const auto& entry : fs::directory_iterator(DATA / "events")) {
            if (!entry.is_regular_file()) continue;
            std::string name = entry.path().filename().string();
            if (name.rfind("tgs_chunk_", 0) != 0) continue;
            auto v = read_jsonl(entry.path());
            for (auto& j : v) raw.push_back(j);
        }
        total_tgs_requests = static_cast<int>(raw.size());
        std::set<std::string> seen_ids;
        for (auto& j : raw) {
            try {
                std::string rid = j.at("request_id").get<std::string>();
                std::string princ = j.at("principal").get<std::string>();
                int kvno = j.at("kvno").get<int>();
                int day = j.at("day").get<int>();
                int hour = j.at("hour").get<int>();
                if (rid.empty()) throw std::runtime_error("");
                if (seen_ids.count(rid)) throw std::runtime_error("");
                if (!principals.count(princ)) throw std::runtime_error("");
                if (kvno < 1 || kvno > 99999) throw std::runtime_error("");
                if (day < 0) throw std::runtime_error("");
                if (hour < 0 || hour > 23) throw std::runtime_error("");
                if (day > current_day || (day == current_day && hour > current_hour)) throw std::runtime_error("");
                TgsRequest r;
                r.request_id = rid; r.principal = princ;
                r.kvno = kvno; r.day = day; r.hour = hour;
                seen_ids.insert(rid);
                all_tgs.push_back(r);
            } catch (...) {
                invalid_tgs_requests++;
            }
        }
    }

    auto et_cmp = [](const KeytabEvent& a, const KeytabEvent& b){
        return std::tie(a.day, a.hour, a.event_id) < std::tie(b.day, b.hour, b.event_id);
    };
    std::sort(all_keytab.begin(), all_keytab.end(), et_cmp);

    auto tr_cmp = [](const TgsRequest& a, const TgsRequest& b){
        return std::tie(a.day, a.hour, a.request_id) < std::tie(b.day, b.hour, b.request_id);
    };
    std::sort(all_tgs.begin(), all_tgs.end(), tr_cmp);

    std::set<std::string> valid_principal_names;
    std::set<std::string> invalid_principal_names;
    for (const auto& [n, p] : principals) {
        if (!tier_windows.count(p.tier)) invalid_principal_names.insert(n);
        else valid_principal_names.insert(n);
    }

    std::map<std::string, std::map<int, KvnoRecord>> state;
    std::map<std::string, std::vector<const KeytabEvent*>> per_principal_adds;
    std::vector<Anomaly> anomalies;

    auto record = [&](const std::string& kind, const std::string& severity,
                      const std::string& principal, std::optional<int> kvno,
                      int day, int hour) {
        Anomaly a; a.kind = kind; a.severity = severity;
        a.principal = principal; a.kvno = kvno; a.day = day; a.hour = hour;
        anomalies.push_back(a);
    };

    for (const auto& e : all_keytab) {
        if (!valid_principal_names.count(e.principal)) continue;
        auto& st = state[e.principal];
        if (e.kind == "add") {
            bool exists = st.count(e.kvno) > 0;
            bool not_strict_max = false;
            if (!exists && !st.empty()) {
                int mx = st.rbegin()->first;
                if (e.kvno <= mx) not_strict_max = true;
            }
            if (exists || not_strict_max) {
                record("kvno_non_monotonic", "high", e.principal, e.kvno, e.day, e.hour);
                continue;
            }
            KvnoRecord r;
            r.kvno = e.kvno; r.added_day = e.day; r.added_hour = e.hour;
            r.enctype = e.enctype; r.final_state = "active";
            st[e.kvno] = r;
            per_principal_adds[e.principal].push_back(&e);
        } else if (e.kind == "revoke") {
            auto it = st.find(e.kvno);
            if (it == st.end()) {
                record("revoke_unknown_kvno", "medium", e.principal, e.kvno, e.day, e.hour);
                continue;
            }
            if (it->second.final_state != "active") {
                record("revoke_already_terminal", "low", e.principal, e.kvno, e.day, e.hour);
                continue;
            }
            it->second.revoked_day = e.day;
            it->second.revoked_hour = e.hour;
            it->second.revoke_reason = e.reason;
            it->second.final_state = "revoked";
        } else if (e.kind == "retire") {
            auto it = st.find(e.kvno);
            if (it == st.end()) {
                record("retire_unknown_kvno", "medium", e.principal, e.kvno, e.day, e.hour);
                continue;
            }
            if (it->second.final_state != "active") {
                record("retire_already_terminal", "low", e.principal, e.kvno, e.day, e.hour);
                continue;
            }
            it->second.retired_day = e.day;
            it->second.retired_hour = e.hour;
            it->second.final_state = "retired";
        }
    }

    std::set<std::string> compromised;
    for (const auto& [n, st] : state) {
        for (const auto& [k, r] : st) {
            if (r.final_state == "revoked" && r.revoke_reason.value_or("") == "compromise") {
                compromised.insert(n);
                break;
            }
        }
    }

    auto active_at = [&](const std::string& princ, int d, int h) -> std::vector<int> {
        std::vector<int> act;
        auto it = state.find(princ);
        if (it == state.end()) return act;
        for (const auto& [k, r] : it->second) {
            bool added_ok = std::tie(r.added_day, r.added_hour) <= std::tie(d, h);
            if (!added_ok) continue;
            if (r.revoked_day) {
                if (std::tie(*r.revoked_day, *r.revoked_hour) <= std::tie(d, h)) continue;
            }
            if (r.retired_day) {
                if (std::tie(*r.retired_day, *r.retired_hour) <= std::tie(d, h)) continue;
            }
            act.push_back(k);
        }
        std::sort(act.begin(), act.end());
        return act;
    };

    auto in_cross_fade_at = [&](const std::string& princ, int kv, int d, int h) -> bool {
        auto it = state.find(princ);
        if (it == state.end()) return false;
        auto act = active_at(princ, d, h);
        if (act.empty()) return false;
        int cur = act.back();
        if (kv == cur) return false;
        const auto& cr = it->second.at(cur);
        long long t_h = static_cast<long long>(d) * 24 + h;
        long long add_h = static_cast<long long>(cr.added_day) * 24 + cr.added_hour;
        return t_h < add_h + cross_fade_hours;
    };

    json ticket_validity;
    ticket_validity["requests"] = json::array();
    std::map<std::string, int> verdict_counts;
    for (const std::string& v : {"valid","valid_cross_fade","invalid_kvno_unknown","invalid_kvno_revoked","invalid_kvno_retired","downgrade_attempt","weak_enctype"})
        verdict_counts[v] = 0;

    for (const auto& r : all_tgs) {
        if (!valid_principal_names.count(r.principal)) continue;
        std::string verdict;
        std::optional<std::string> anomaly_kind;
        std::string anomaly_sev;
        auto sit = state.find(r.principal);
        const KvnoRecord* rec = nullptr;
        if (sit != state.end()) {
            auto kit = sit->second.find(r.kvno);
            if (kit != sit->second.end()) rec = &kit->second;
        }
        bool unknown = (!rec) ||
            (std::tie(rec->added_day, rec->added_hour) > std::tie(r.day, r.hour));
        if (unknown) {
            verdict = "invalid_kvno_unknown";
            anomaly_kind = "ticket_unknown_kvno"; anomaly_sev = "high";
        } else if (rec->revoked_day &&
                   std::tie(*rec->revoked_day, *rec->revoked_hour) <= std::tie(r.day, r.hour)) {
            verdict = "invalid_kvno_revoked";
            anomaly_kind = "ticket_against_revoked"; anomaly_sev = "critical";
        } else if (rec->retired_day &&
                   std::tie(*rec->retired_day, *rec->retired_hour) <= std::tie(r.day, r.hour)) {
            verdict = "invalid_kvno_retired";
            anomaly_kind = "ticket_against_retired"; anomaly_sev = "medium";
        } else if (!enctype_allowed_at(rec->enctype, r.day)) {
            verdict = "weak_enctype";
            anomaly_kind = "weak_enctype_in_use"; anomaly_sev = "high";
        } else {
            auto act = active_at(r.principal, r.day, r.hour);
            int cur = act.empty() ? -1 : act.back();
            if (r.kvno == cur) {
                verdict = "valid";
            } else if (in_cross_fade_at(r.principal, r.kvno, r.day, r.hour)) {
                verdict = "valid_cross_fade";
            } else {
                verdict = "downgrade_attempt";
                anomaly_kind = "downgrade_attempt"; anomaly_sev = "high";
            }
        }
        verdict_counts[verdict]++;
        if (anomaly_kind) record(*anomaly_kind, anomaly_sev, r.principal, r.kvno, r.day, r.hour);
        if (compromised.count(r.principal))
            record("compromised_principal_referenced", "critical", r.principal, r.kvno, r.day, r.hour);
        const PolicyVersion* pv = policy_at(r.day);
        json reqj;
        reqj["day"] = r.day;
        reqj["hour"] = r.hour;
        reqj["kvno"] = r.kvno;
        reqj["policy_version"] = pv ? pv->version : std::string("none");
        reqj["principal"] = r.principal;
        reqj["request_id"] = r.request_id;
        reqj["verdict"] = verdict;
        ticket_validity["requests"].push_back(reqj);
    }

    json rotation_compliance;
    rotation_compliance["principals"] = json::array();
    for (const auto& [n, p] : principals) {
        if (invalid_principal_names.count(n)) continue;
        json e;
        e["principal"] = n;
        e["tier"] = p.tier;
        e["exempt"] = p.exempt;
        if (p.exempt) {
            e["rotation_window_days"] = nullptr;
            e["last_rotation_day"] = nullptr;
            e["next_due_day"] = nullptr;
            e["status"] = "exempt";
        } else {
            int W = p.override_rotation_days ? *p.override_rotation_days : tier_windows.at(p.tier);
            e["rotation_window_days"] = W;
            const auto& adds = per_principal_adds[n];
            if (adds.empty()) {
                e["last_rotation_day"] = nullptr;
                e["next_due_day"] = nullptr;
                e["status"] = "never_rotated";
                record("never_rotated", "high", n, std::nullopt, current_day, 0);
            } else {
                int last_day = adds.back()->day;
                int next_due = last_day + W;
                e["last_rotation_day"] = last_day;
                e["next_due_day"] = next_due;
                if (next_due < current_day) {
                    e["status"] = "overdue";
                    record("missed_rotation", "medium", n, std::nullopt, current_day, 0);
                } else {
                    e["status"] = "compliant";
                }
                long long half_window = ((long long)W * 24 + 1) / 2;
                std::optional<std::tuple<int,int,std::string,int>> earliest_excess;
                for (size_t i = 1; i < adds.size(); i++) {
                    const auto* prev = adds[i-1];
                    const auto* cur = adds[i];
                    long long gap_h = (long long)cur->day * 24 + cur->hour
                                      - (long long)prev->day * 24 - prev->hour;
                    if (gap_h < half_window) {
                        std::tuple<int,int,std::string,int> key{cur->day, cur->hour, cur->event_id, cur->kvno};
                        if (!earliest_excess || key < *earliest_excess) earliest_excess = key;
                    }
                }
                if (earliest_excess) {
                    int d = std::get<0>(*earliest_excess);
                    int h = std::get<1>(*earliest_excess);
                    int kv = std::get<3>(*earliest_excess);
                    record("excessive_rotation", "low", n, kv, d, h);
                }
            }
        }
        rotation_compliance["principals"].push_back(e);
    }

    for (const auto& [n, st] : state) {
        if (invalid_principal_names.count(n)) continue;
        auto act = active_at(n, current_day, current_hour);
        if (act.empty()) continue;
        int cur = act.back();
        for (int k : act) {
            if (k == cur) continue;
            if (!in_cross_fade_at(n, k, current_day, current_hour))
                record("missed_retirement", "medium", n, k, current_day, current_hour);
        }
    }

    for (const auto& [n, st] : state) {
        if (invalid_principal_names.count(n)) continue;
        for (const auto& [k, r] : st) {
            if (r.final_state != "active") continue;
            if (!enctype_allowed_at(r.enctype, current_day))
                record("forbidden_enctype_active", "medium", n, k, current_day, 0);
        }
    }

    std::sort(anomalies.begin(), anomalies.end(),
        [](const Anomaly& a, const Anomaly& b){
            int sa = severity_rank(a.severity), sb = severity_rank(b.severity);
            if (sa != sb) return sa < sb;
            if (a.day != b.day) return a.day < b.day;
            if (a.hour != b.hour) return a.hour < b.hour;
            if (a.kind != b.kind) return a.kind < b.kind;
            if (a.principal != b.principal) return a.principal < b.principal;
            bool an = !a.kvno.has_value(), bn = !b.kvno.has_value();
            if (an != bn) return !an;
            if (!an && *a.kvno != *b.kvno) return *a.kvno < *b.kvno;
            return false;
        });

    json kvno_lifecycle;
    kvno_lifecycle["principals"] = json::array();
    for (const auto& [n, p] : principals) {
        if (invalid_principal_names.count(n)) continue;
        json e;
        e["exempt"] = p.exempt;
        e["kvno_events"] = json::array();
        auto sit = state.find(n);
        if (sit != state.end()) {
            for (const auto& [k, r] : sit->second) {
                json ke;
                ke["added_day"] = r.added_day;
                ke["added_hour"] = r.added_hour;
                ke["enctype"] = r.enctype;
                ke["final_state"] = r.final_state;
                ke["kvno"] = r.kvno;
                ke["retired_day"] = r.retired_day ? json(*r.retired_day) : json(nullptr);
                ke["retired_hour"] = r.retired_hour ? json(*r.retired_hour) : json(nullptr);
                ke["revoke_reason"] = r.revoke_reason ? json(*r.revoke_reason) : json(nullptr);
                ke["revoked_day"] = r.revoked_day ? json(*r.revoked_day) : json(nullptr);
                ke["revoked_hour"] = r.revoked_hour ? json(*r.revoked_hour) : json(nullptr);
                e["kvno_events"].push_back(ke);
            }
        }
        e["principal"] = n;
        e["tier"] = p.tier;
        kvno_lifecycle["principals"].push_back(e);
    }

    json anomalies_j;
    anomalies_j["anomalies"] = json::array();
    for (const auto& a : anomalies) {
        json e;
        e["day"] = a.day;
        e["details"] = anomaly_details(a);
        e["hour"] = a.hour;
        e["id"] = anomaly_id(a);
        e["kind"] = a.kind;
        e["kvno"] = a.kvno ? json(*a.kvno) : json(nullptr);
        e["principal"] = a.principal;
        e["severity"] = a.severity;
        anomalies_j["anomalies"].push_back(e);
    }

    json summary;
    summary["anomalies_per_severity"] = json::object();
    summary["anomalies_per_severity"]["critical"] = 0;
    summary["anomalies_per_severity"]["high"] = 0;
    summary["anomalies_per_severity"]["medium"] = 0;
    summary["anomalies_per_severity"]["low"] = 0;
    for (const auto& a : anomalies) summary["anomalies_per_severity"][a.severity] = summary["anomalies_per_severity"][a.severity].get<int>() + 1;
    summary["compromised_principals"] = json::array();
    for (const auto& c : compromised) summary["compromised_principals"].push_back(c);
    summary["current_day"] = current_day;
    summary["current_hour"] = current_hour;
    int exempt_count = 0;
    for (const auto& [n, p] : principals) if (p.exempt) exempt_count++;
    summary["exempt_principals"] = exempt_count;
    summary["invalid_keytab_events"] = invalid_keytab_events;
    summary["invalid_principals"] = static_cast<int>(invalid_principal_names.size());
    summary["invalid_tgs_requests"] = invalid_tgs_requests;
    summary["tickets_per_verdict"] = json::object();
    for (const auto& [k, v] : verdict_counts) summary["tickets_per_verdict"][k] = v;
    summary["total_keytab_events"] = total_keytab_events;
    summary["total_principals"] = static_cast<int>(principals.size());
    summary["total_tgs_requests"] = total_tgs_requests;

    write_json_atomic(OUT / "kvno_lifecycle.json", kvno_lifecycle);
    write_json_atomic(OUT / "rotation_compliance.json", rotation_compliance);
    write_json_atomic(OUT / "ticket_validity.json", ticket_validity);
    write_json_atomic(OUT / "anomalies.json", anomalies_j);
    write_json_atomic(OUT / "summary.json", summary);

    return 0;
}
CPPEOF

g++ -std=c++17 -O2 -o /tmp/oracle /tmp/oracle.cpp
/tmp/oracle
