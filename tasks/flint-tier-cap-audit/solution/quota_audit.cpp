#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <nlohmann/json.hpp>
#include <set>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using json = nlohmann::json;

static std::string env_or(const char* key, const char* defv) {
  if (const char* v = std::getenv(key)) return v;
  return defv;
}

static int tier_rank(const std::string& tier, const std::vector<std::string>& order) {
  for (size_t i = 0; i < order.size(); ++i) {
    if (order[i] == tier) return static_cast<int>(i);
  }
  return static_cast<int>(order.size());
}

int main() {
  fs::path data = env_or("QUOTA_DATA_DIR", "/app/quota_lab");
  fs::path audit = env_or("QUOTA_AUDIT_DIR", "/app/audit");
  fs::create_directories(audit);

  json policy = json::parse(std::ifstream(data / "policy.json"));
  json events = json::parse(std::ifstream(data / "events.json"));
  int day = policy.at("audit_day").get<int>();
  std::vector<std::string> order = policy.at("tier_order").get<std::vector<std::string>>();
  std::map<std::string, int> caps;
  for (auto& [k, v] : policy.at("tier_caps").items()) caps[k] = v.get<int>();

  if (events.contains("tier_derates")) {
    for (const auto& d : events.at("tier_derates")) {
      int s = d.at("start_day").get<int>();
      int e = d.at("end_day").get<int>();
      if (s <= day && day <= e) {
        std::string t = d.at("tier").get<std::string>();
        if (caps.count(t)) caps[t] = caps[t] * d.at("factor_bp").get<int>() / 10000;
      }
    }
  }
  std::set<std::string> frozen;
  if (events.contains("item_freezes")) {
    for (const auto& f : events.at("item_freezes")) {
      int s = f.at("start_day").get<int>();
      int e = f.at("end_day").get<int>();
      if (s <= day && day <= e) frozen.insert(f.at("item_id").get<std::string>());
    }
  }

  std::vector<json> items;
  for (const auto& ent : fs::directory_iterator(data / "items")) {
    if (ent.path().extension() == ".json") {
      items.push_back(json::parse(std::ifstream(ent.path())));
    }
  }
  std::sort(items.begin(), items.end(), [&](const json& a, const json& b) {
    int ra = tier_rank(a.at("tier").get<std::string>(), order);
    int rb = tier_rank(b.at("tier").get<std::string>(), order);
    if (ra != rb) return ra < rb;
    std::string ta = a.at("tier").get<std::string>();
    std::string tb = b.at("tier").get<std::string>();
    if (ta != tb) return ta < tb;
    return a.at("item_id").get<std::string>() < b.at("item_id").get<std::string>();
  });

  std::map<std::string, int> tier_rem = caps;
  json rows = json::array();
  std::map<std::string, int> sc{{"frozen", 0}, {"ok", 0}, {"shortfall", 0}};

  for (const auto& it : items) {
    std::string iid = it.at("item_id").get<std::string>();
    std::string tier = it.at("tier").get<std::string>();
    int demand = it.at("demand").get<int>();
    if (frozen.count(iid)) {
      rows.push_back({{"item_id", iid}, {"tier", tier}, {"status", "frozen"}, {"demand", demand}, {"allocated", 0}});
      sc["frozen"]++;
      continue;
    }
    int left = tier_rem.count(tier) ? tier_rem[tier] : 0;
    int alloc = std::min(demand, left);
    tier_rem[tier] = left - alloc;
    std::string st = (alloc == demand) ? "ok" : "shortfall";
    sc[st]++;
    rows.push_back({{"item_id", iid}, {"tier", tier}, {"status", st}, {"demand", demand}, {"allocated", alloc}});
  }
  std::set<std::string> touched;
  for (const auto& r : rows) {
    if (r.at("allocated").get<int>() > 0) touched.insert(r.at("tier").get<std::string>());
  }
  json summary = {
      {"audit_day", day},
      {"items_processed", static_cast<int>(items.size())},
      {"frozen_items", sc["frozen"]},
      {"status_counts", sc},
      {"tiers_touched", touched},
  };
  std::ofstream(audit / "allocations.json") << json{{"items", rows}}.dump(2) << "\n";
  std::ofstream(audit / "summary.json") << summary.dump(2) << "\n";
  return 0;
}
