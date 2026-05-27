import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

public class QuotaAudit {
    static String dataDir() {
        return System.getenv().getOrDefault("QUOTA_DATA_DIR", "/app/quota_lab");
    }

    static String auditDir() {
        return System.getenv().getOrDefault("QUOTA_AUDIT_DIR", "/app/audit");
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> readJson(Path p) throws Exception {
        String s = Files.readString(p, StandardCharsets.UTF_8);
        return new com.google.gson.Gson().fromJson(s, Map.class);
    }

    static void writeJson(Path p, Object obj) throws Exception {
        com.google.gson.Gson gson = new com.google.gson.GsonBuilder().setPrettyPrinting().create();
        String text = gson.toJson(obj) + "\n";
        Files.writeString(p, text, StandardCharsets.UTF_8);
    }

    static int tierRank(String tier, List<String> order) {
        int i = order.indexOf(tier);
        return i >= 0 ? i : order.size();
    }

    public static void main(String[] args) throws Exception {
        Path data = Paths.get(dataDir());
        Path audit = Paths.get(auditDir());
        Files.createDirectories(audit);

        Map<String, Object> policy = readJson(data.resolve("policy.json"));
        Map<String, Object> events = readJson(data.resolve("events.json"));
        int day = ((Number) policy.get("audit_day")).intValue();
        @SuppressWarnings("unchecked")
        List<String> order = (List<String>) policy.get("tier_order");
        @SuppressWarnings("unchecked")
        Map<String, Number> capsNum = (Map<String, Number>) policy.get("tier_caps");
        Map<String, Integer> caps = new TreeMap<>();
        for (var e : capsNum.entrySet()) caps.put(e.getKey(), e.getValue().intValue());

        @SuppressWarnings("unchecked")
        List<Map<String, Object>> derates = (List<Map<String, Object>>) events.getOrDefault("tier_derates", List.of());
        for (Map<String, Object> d : derates) {
            int s = ((Number) d.get("start_day")).intValue();
            int e = ((Number) d.get("end_day")).intValue();
            if (s <= day && day <= e) {
                String t = (String) d.get("tier");
                if (caps.containsKey(t)) {
                    int bp = ((Number) d.get("factor_bp")).intValue();
                    caps.put(t, caps.get(t) * bp / 10000);
                }
            }
        }
        Set<String> frozen = new HashSet<>();
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> freezes = (List<Map<String, Object>>) events.getOrDefault("item_freezes", List.of());
        for (Map<String, Object> f : freezes) {
            int s = ((Number) f.get("start_day")).intValue();
            int e = ((Number) f.get("end_day")).intValue();
            if (s <= day && day <= e) frozen.add((String) f.get("item_id"));
        }

        List<Map<String, Object>> items = Files.list(data.resolve("items"))
            .filter(p -> p.toString().endsWith(".json"))
            .sorted()
            .map(p -> {
                try { return readJson(p); } catch (Exception ex) { throw new RuntimeException(ex); }
            })
            .collect(Collectors.toList());
        items.sort(Comparator
            .comparingInt((Map<String, Object> it) -> tierRank((String) it.get("tier"), order))
            .thenComparing(it -> (String) it.get("tier"))
            .thenComparing(it -> (String) it.get("item_id")));

        Map<String, Integer> tierRem = new HashMap<>(caps);
        List<Map<String, Object>> rows = new ArrayList<>();
        Map<String, Integer> sc = new LinkedHashMap<>();
        sc.put("frozen", 0); sc.put("ok", 0); sc.put("shortfall", 0);

        for (Map<String, Object> it : items) {
            String iid = (String) it.get("item_id");
            String tier = (String) it.get("tier");
            int demand = ((Number) it.get("demand")).intValue();
            if (frozen.contains(iid)) {
                rows.add(Map.of("item_id", iid, "tier", tier, "status", "frozen", "demand", demand, "allocated", 0));
                sc.put("frozen", sc.get("frozen") + 1);
                continue;
            }
            int left = tierRem.getOrDefault(tier, 0);
            int alloc = Math.min(demand, left);
            tierRem.put(tier, left - alloc);
            String st = alloc == demand ? "ok" : "shortfall";
            sc.put(st, sc.get(st) + 1);
            rows.add(Map.of("item_id", iid, "tier", tier, "status", st, "demand", demand, "allocated", alloc));
        }
        TreeSet<String> touched = new TreeSet<>();
        for (Map<String, Object> r : rows) {
            if (((Number) r.get("allocated")).intValue() > 0) touched.add((String) r.get("tier"));
        }
        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("audit_day", day);
        summary.put("items_processed", items.size());
        summary.put("frozen_items", sc.get("frozen"));
        summary.put("status_counts", sc);
        summary.put("tiers_touched", new ArrayList<>(touched));

        writeJson(audit.resolve("allocations.json"), Map.of("items", rows));
        writeJson(audit.resolve("summary.json"), summary);
    }
}
