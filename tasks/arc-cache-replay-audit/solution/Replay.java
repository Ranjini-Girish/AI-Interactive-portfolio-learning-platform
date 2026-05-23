import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public final class Replay {
    private Replay() {}

    private static final class WARC {
        final int c;
        final List<String[]> t1 = new ArrayList<>();
        final List<String[]> t2 = new ArrayList<>();
        final List<String[]> b1 = new ArrayList<>();
        final List<String[]> b2 = new ArrayList<>();
        int p = 0;
        final Set<String> observed = new HashSet<>();
        long weightAdmitted = 0;

        WARC(int capacity) {
            this.c = capacity;
        }

        static int find(List<String[]> lst, String x) {
            for (int i = 0; i < lst.size(); i++) {
                if (lst.get(i)[0].equals(x)) {
                    return i;
                }
            }
            return -1;
        }

        String[] popWeighted(List<String[]> lst) {
            int minW = Integer.MAX_VALUE;
            for (String[] e : lst) {
                minW = Math.min(minW, Integer.parseInt(e[1]));
            }
            for (int i = lst.size() - 1; i >= 0; i--) {
                if (Integer.parseInt(lst.get(i)[1]) == minW) {
                    return lst.remove(i);
                }
            }
            throw new AssertionError("unreachable");
        }

        String[] replace(boolean inB2) {
            int t1n = t1.size();
            if (t1n >= 1 && ((inB2 && t1n == p) || t1n > p)) {
                String[] e = popWeighted(t1);
                b1.add(0, e);
                return new String[] {e[0], "t1", e[1]};
            }
            String[] e = popWeighted(t2);
            b2.add(0, e);
            return new String[] {e[0], "t2", e[1]};
        }

        Object[] access(String x, int w) {
            observed.add(x);
            weightAdmitted += w;
            String repK = null;
            String repF = null;
            String repW = null;
            String dropK = null;
            String dropF = null;
            String dropW = null;

            int i = find(t1, x);
            if (i >= 0) {
                String[] e = t1.remove(i);
                int newW = Integer.parseInt(e[1]) + w;
                t2.add(0, new String[] {x, String.valueOf(newW)});
                return new Object[] {
                    "hit_t1", repK, repF, repW, dropK, dropF, dropW, newW
                };
            }
            i = find(t2, x);
            if (i >= 0) {
                String[] e = t2.remove(i);
                int newW = Integer.parseInt(e[1]) + w;
                t2.add(0, new String[] {x, String.valueOf(newW)});
                return new Object[] {
                    "hit_t2", repK, repF, repW, dropK, dropF, dropW, newW
                };
            }
            i = find(b1, x);
            if (i >= 0) {
                int delta = Math.max(b2.size() / b1.size(), 1);
                p = Math.min(p + delta, c);
                String[] rep = replace(false);
                repK = rep[0];
                repF = rep[1];
                repW = rep[2];
                b1.remove(find(b1, x));
                t2.add(0, new String[] {x, String.valueOf(w)});
                return new Object[] {
                    "ghost_hit_b1", repK, repF, repW, dropK, dropF, dropW, w
                };
            }
            i = find(b2, x);
            if (i >= 0) {
                int delta = Math.max(b1.size() / b2.size(), 1);
                p = Math.max(p - delta, 0);
                String[] rep = replace(true);
                repK = rep[0];
                repF = rep[1];
                repW = rep[2];
                b2.remove(find(b2, x));
                t2.add(0, new String[] {x, String.valueOf(w)});
                return new Object[] {
                    "ghost_hit_b2", repK, repF, repW, dropK, dropF, dropW, w
                };
            }

            int t1n = t1.size();
            int b1n = b1.size();
            int total = t1n + t2.size() + b1n + b2.size();
            if (t1n + b1n == c) {
                if (t1n < c) {
                    String[] e = b1.remove(b1.size() - 1);
                    dropK = e[0];
                    dropF = "b1";
                    dropW = e[1];
                    String[] rep = replace(false);
                    repK = rep[0];
                    repF = rep[1];
                    repW = rep[2];
                } else {
                    String[] e = popWeighted(t1);
                    dropK = e[0];
                    dropF = "t1";
                    dropW = e[1];
                }
            } else if (t1n + b1n < c && total >= c) {
                if (total == 2 * c) {
                    String[] e = b2.remove(b2.size() - 1);
                    dropK = e[0];
                    dropF = "b2";
                    dropW = e[1];
                }
                String[] rep = replace(false);
                repK = rep[0];
                repF = rep[1];
                repW = rep[2];
            }
            t1.add(0, new String[] {x, String.valueOf(w)});
            return new Object[] {
                "miss", repK, repF, repW, dropK, dropF, dropW, w
            };
        }

        boolean evict(String x) {
            int i = find(t1, x);
            if (i >= 0) {
                t1.remove(i);
                return true;
            }
            i = find(t2, x);
            if (i >= 0) {
                t2.remove(i);
                return true;
            }
            return false;
        }

        boolean clear() {
            if (t1.isEmpty() && t2.isEmpty() && b1.isEmpty() && b2.isEmpty()) {
                return false;
            }
            t1.clear();
            t2.clear();
            b1.clear();
            b2.clear();
            p = 0;
            return true;
        }
    }

    private static List<Map<String, Object>> residentEntries(List<String[]> lst) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (String[] e : lst) {
            Map<String, Object> row = new TreeMap<>();
            row.put("cum_weight", Integer.parseInt(e[1]));
            row.put("key", e[0]);
            out.add(row);
        }
        return out;
    }

    private static List<Map<String, Object>> ghostEntries(List<String[]> lst) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (String[] e : lst) {
            Map<String, Object> row = new TreeMap<>();
            row.put("entry_weight", Integer.parseInt(e[1]));
            row.put("key", e[0]);
            out.add(row);
        }
        return out;
    }

    private static Map<String, Object> simulate(JsonObject eventsDoc, JsonObject cfg) {
        WARC arc = new WARC(cfg.get("cache_size").getAsInt());
        List<Map<String, Object>> audit = new ArrayList<>();
        List<Map<String, Object>> decisions = new ArrayList<>();
        Map<String, Integer> counts = new TreeMap<>();
        String[] countKeys = {
            "total_accesses", "total_evicts", "total_clears",
            "accesses_accepted", "evicts_accepted", "evicts_rejected",
            "clears_accepted", "clears_rejected",
            "hits_t1", "hits_t2", "ghost_hits_b1", "ghost_hits_b2", "misses"
        };
        for (String k : countKeys) {
            counts.put(k, 0);
        }

        for (JsonElement el : eventsDoc.getAsJsonArray("events")) {
            JsonObject ev = el.getAsJsonObject();
            String evId = ev.get("event_id").getAsString();
            long ts = ev.get("ts_unix_ms").getAsLong();
            String ty = ev.get("type").getAsString();
            JsonObject p = ev.getAsJsonObject("payload");
            boolean accepted = false;
            String reason = null;
            Map<String, Object> decision = null;

            if ("access".equals(ty)) {
                counts.put("total_accesses", counts.get("total_accesses") + 1);
                Object[] res = arc.access(p.get("key").getAsString(), p.get("weight").getAsInt());
                accepted = true;
                counts.put("accesses_accepted", counts.get("accesses_accepted") + 1);
                String outcome = (String) res[0];
                Map<String, String> outcomeToCount = new TreeMap<>();
                outcomeToCount.put("hit_t1", "hits_t1");
                outcomeToCount.put("hit_t2", "hits_t2");
                outcomeToCount.put("ghost_hit_b1", "ghost_hits_b1");
                outcomeToCount.put("ghost_hit_b2", "ghost_hits_b2");
                outcomeToCount.put("miss", "misses");
                counts.put(
                        outcomeToCount.get(outcome),
                        counts.get(outcomeToCount.get(outcome)) + 1);
                decision = new TreeMap<>();
                decision.put("b1_size", arc.b1.size());
                decision.put("b2_size", arc.b2.size());
                decision.put("cum_weight_after", res[7]);
                decision.put("dropped_from", res[5]);
                decision.put("dropped_key", res[4]);
                decision.put("dropped_weight", parseIntOrNull((String) res[6]));
                decision.put("event_id", evId);
                decision.put("key", p.get("key").getAsString());
                decision.put("outcome", outcome);
                decision.put("p_after", arc.p);
                decision.put("replaced_from", res[2]);
                decision.put("replaced_key", res[1]);
                decision.put("replaced_weight", parseIntOrNull((String) res[3]));
                decision.put("t1_size", arc.t1.size());
                decision.put("t2_size", arc.t2.size());
                decision.put("type", "access");
            } else if ("evict".equals(ty)) {
                counts.put("total_evicts", counts.get("total_evicts") + 1);
                if (arc.evict(p.get("key").getAsString())) {
                    accepted = true;
                    counts.put("evicts_accepted", counts.get("evicts_accepted") + 1);
                    decision = evictClearDecision(evId, p.get("key").getAsString(), arc, "evicted", "evict");
                } else {
                    counts.put("evicts_rejected", counts.get("evicts_rejected") + 1);
                    reason = "unknown_resident";
                }
            } else {
                counts.put("total_clears", counts.get("total_clears") + 1);
                if (arc.clear()) {
                    accepted = true;
                    counts.put("clears_accepted", counts.get("clears_accepted") + 1);
                    decision = evictClearDecision(evId, null, arc, "cleared", "clear");
                } else {
                    counts.put("clears_rejected", counts.get("clears_rejected") + 1);
                    reason = "cache_empty";
                }
            }

            Map<String, Object> auditRow = new TreeMap<>();
            auditRow.put("accepted", accepted);
            auditRow.put("event_id", evId);
            auditRow.put("payload", jsonObjectToSortedMap(p));
            auditRow.put("reason_ignored", reason);
            auditRow.put("ts_unix_ms", ts);
            auditRow.put("type", ty);
            audit.add(auditRow);
            if (decision != null) {
                decisions.add(decision);
            }
        }

        List<Map<String, Object>> auditSorted = new ArrayList<>(audit);
        auditSorted.sort(Comparator.comparing(r -> (String) r.get("event_id")));
        List<Map<String, Object>> violSorted = new ArrayList<>();
        for (Map<String, Object> r : auditSorted) {
            if (!Boolean.TRUE.equals(r.get("accepted"))) {
                violSorted.add(new TreeMap<>(r));
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("accesses_accepted", counts.get("accesses_accepted"));
        summary.put("clears_accepted", counts.get("clears_accepted"));
        summary.put("clears_rejected", counts.get("clears_rejected"));
        summary.put("evicts_accepted", counts.get("evicts_accepted"));
        summary.put("evicts_rejected", counts.get("evicts_rejected"));
        summary.put("final_b1_weight_sum", sumWeights(arc.b1));
        summary.put("final_b2_weight_sum", sumWeights(arc.b2));
        summary.put("final_p", arc.p);
        summary.put("final_t1_weight_sum", sumWeights(arc.t1));
        summary.put("final_t2_weight_sum", sumWeights(arc.t2));
        summary.put("ghost_hits_b1", counts.get("ghost_hits_b1"));
        summary.put("ghost_hits_b2", counts.get("ghost_hits_b2"));
        summary.put("hits_t1", counts.get("hits_t1"));
        summary.put("hits_t2", counts.get("hits_t2"));
        summary.put("misses", counts.get("misses"));
        summary.put("total_accesses", counts.get("total_accesses"));
        summary.put("total_clears", counts.get("total_clears"));
        summary.put("total_distinct_keys", arc.observed.size());
        summary.put("total_events", eventsDoc.getAsJsonArray("events").size());
        summary.put("total_evicts", counts.get("total_evicts"));
        summary.put("total_weight_admitted", arc.weightAdmitted);

        Map<String, Object> cacheState = new TreeMap<>();
        cacheState.put("b1", ghostEntries(arc.b1));
        cacheState.put("b2", ghostEntries(arc.b2));
        cacheState.put("p", arc.p);
        cacheState.put("t1", residentEntries(arc.t1));
        cacheState.put("t2", residentEntries(arc.t2));

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("cache_state", cacheState);
        out.put("decisions", Map.of("decisions", decisions));
        out.put("event_audit", Map.of("events", auditSorted));
        out.put("violations", Map.of("violations", violSorted));
        out.put("summary", summary);
        return out;
    }

    private static Map<String, Object> evictClearDecision(
            String evId, String key, WARC arc, String outcome, String type) {
        Map<String, Object> d = new TreeMap<>();
        d.put("b1_size", arc.b1.size());
        d.put("b2_size", arc.b2.size());
        d.put("cum_weight_after", null);
        d.put("dropped_from", null);
        d.put("dropped_key", null);
        d.put("dropped_weight", null);
        d.put("event_id", evId);
        d.put("key", key);
        d.put("outcome", outcome);
        d.put("p_after", arc.p);
        d.put("replaced_from", null);
        d.put("replaced_key", null);
        d.put("replaced_weight", null);
        d.put("t1_size", arc.t1.size());
        d.put("t2_size", arc.t2.size());
        d.put("type", type);
        return d;
    }

    private static Integer parseIntOrNull(String s) {
        return s == null ? null : Integer.parseInt(s);
    }

    private static int sumWeights(List<String[]> lst) {
        int s = 0;
        for (String[] e : lst) {
            s += Integer.parseInt(e[1]);
        }
        return s;
    }

    private static Map<String, Object> jsonObjectToSortedMap(JsonObject obj) {
        Map<String, Object> m = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e : obj.entrySet()) {
            JsonElement v = e.getValue();
            if (v.isJsonNull()) {
                m.put(e.getKey(), null);
            } else if (v.isJsonPrimitive()) {
                if (v.getAsJsonPrimitive().isNumber()) {
                    m.put(e.getKey(), v.getAsLong());
                } else if (v.getAsJsonPrimitive().isBoolean()) {
                    m.put(e.getKey(), v.getAsBoolean());
                } else {
                    m.put(e.getKey(), v.getAsString());
                }
            } else if (v.isJsonObject()) {
                m.put(e.getKey(), jsonObjectToSortedMap(v.getAsJsonObject()));
            } else {
                m.put(e.getKey(), v.toString());
            }
        }
        return m;
    }

    private static JsonObject readObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static void writeCanonical(Path path, Object value) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        Files.writeString(path, gson.toJson(value) + "\n", StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject eventsDoc = readObject(inDir.resolve("events.json"));
        JsonObject cfg = readObject(inDir.resolve("config.json"));
        Map<String, Object> outputs = simulate(eventsDoc, cfg);

        writeCanonical(outDir.resolve("cache_state.json"), outputs.get("cache_state"));
        writeCanonical(outDir.resolve("decisions.json"), outputs.get("decisions"));
        writeCanonical(outDir.resolve("event_audit.json"), outputs.get("event_audit"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
        writeCanonical(outDir.resolve("violations.json"), outputs.get("violations"));
    }
}
