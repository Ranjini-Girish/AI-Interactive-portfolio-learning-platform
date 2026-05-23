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
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class Replay {
    private Replay() {}

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

    private static Map<String, Object> simulate(JsonObject eventsDoc, JsonObject config)
            throws IOException {
        JsonArray events = eventsDoc.getAsJsonArray("events");
        int maxLevel = config.get("max_level").getAsInt();
        int minSegs = config.get("compaction_min_segments").getAsInt();

        Map<String, Map<String, Object>> state = new TreeMap<>();
        List<Map<String, Object>> audit = new ArrayList<>();
        List<Map<String, Object>> decisions = new ArrayList<>();

        for (JsonElement el : events) {
            JsonObject ev = el.getAsJsonObject();
            String eid = ev.get("event_id").getAsString();
            long ts = ev.get("ts_unix_ms").getAsLong();
            String t = ev.get("type").getAsString();
            JsonObject p = ev.getAsJsonObject("payload");

            Map<String, Object> row = new TreeMap<>();
            row.put("accepted", false);
            row.put("event_id", eid);
            row.put("payload", jsonObjectToSortedMap(p));
            row.put("reason_ignored", "none");
            row.put("ts_unix_ms", ts);
            row.put("type", t);

            if ("flush_memtable".equals(t)) {
                String sid = p.get("seg_id").getAsString();
                if (state.containsKey(sid)) {
                    row.put("reason_ignored", "duplicate_seg_id");
                } else {
                    Map<String, Object> seg = new TreeMap<>();
                    seg.put("created_at_unix_ms", ts);
                    seg.put("level", 0);
                    seg.put("merged_at_unix_ms", null);
                    seg.put("merged_into_event_id", null);
                    seg.put("seg_id", sid);
                    seg.put("size_bytes", p.get("size_bytes").getAsLong());
                    seg.put("status", "live");
                    state.put(sid, seg);
                    row.put("accepted", true);
                }
            } else if ("compact".equals(t)) {
                int level = p.get("level").getAsInt();
                if (level > maxLevel) {
                    row.put("reason_ignored", "level_out_of_range");
                } else if (level == maxLevel) {
                    row.put("reason_ignored", "top_level_compaction");
                } else {
                    List<Map<String, Object>> live = new ArrayList<>();
                    for (Map<String, Object> s : state.values()) {
                        if ("live".equals(s.get("status"))
                                && ((Number) s.get("level")).intValue() == level) {
                            live.add(s);
                        }
                    }
                    live.sort(Comparator.comparing(s -> (String) s.get("seg_id")));
                    if (live.size() < minSegs) {
                        row.put("reason_ignored", "level_below_threshold");
                    } else {
                        List<String> ids = new ArrayList<>();
                        long total = 0;
                        for (Map<String, Object> s : live) {
                            ids.add((String) s.get("seg_id"));
                            total += ((Number) s.get("size_bytes")).longValue();
                            s.put("merged_at_unix_ms", ts);
                            s.put("merged_into_event_id", eid);
                            s.put("status", "merged");
                        }
                        String newId = "merged_" + eid;
                        Map<String, Object> newSeg = new TreeMap<>();
                        newSeg.put("created_at_unix_ms", ts);
                        newSeg.put("level", level + 1);
                        newSeg.put("merged_at_unix_ms", null);
                        newSeg.put("merged_into_event_id", null);
                        newSeg.put("seg_id", newId);
                        newSeg.put("size_bytes", total);
                        newSeg.put("status", "live");
                        state.put(newId, newSeg);

                        Map<String, Object> dec = new TreeMap<>();
                        dec.put("event_id", eid);
                        dec.put("input_seg_ids", ids);
                        dec.put("level", level);
                        dec.put("output_level", level + 1);
                        dec.put("output_seg_id", newId);
                        dec.put("total_bytes", total);
                        dec.put("ts_unix_ms", ts);
                        decisions.add(dec);
                        row.put("accepted", true);
                    }
                }
            }
            audit.add(row);
        }

        List<Map<String, Object>> segsSorted = new ArrayList<>(state.values());
        segsSorted.sort(Comparator.comparing(s -> (String) s.get("seg_id")));

        List<Map<String, Object>> auditSorted = new ArrayList<>(audit);
        auditSorted.sort(Comparator.comparing(r -> (String) r.get("event_id")));

        List<Map<String, Object>> violations = new ArrayList<>();
        for (Map<String, Object> r : auditSorted) {
            if (!Boolean.TRUE.equals(r.get("accepted"))) {
                violations.add(new TreeMap<>(r));
            }
        }

        int accepted = 0;
        int flushesAcc = 0;
        int compsAcc = 0;
        for (Map<String, Object> r : audit) {
            if (Boolean.TRUE.equals(r.get("accepted"))) {
                accepted++;
                if ("flush_memtable".equals(r.get("type"))) {
                    flushesAcc++;
                } else if ("compact".equals(r.get("type"))) {
                    compsAcc++;
                }
            }
        }
        int live = 0;
        int merged = 0;
        for (Map<String, Object> s : state.values()) {
            if ("live".equals(s.get("status"))) {
                live++;
            } else if ("merged".equals(s.get("status"))) {
                merged++;
            }
        }

        Map<String, Integer> perLevel = new TreeMap<>();
        for (int L = 0; L <= maxLevel; L++) {
            perLevel.put(String.valueOf(L), 0);
        }
        for (Map<String, Object> s : state.values()) {
            if ("live".equals(s.get("status"))) {
                String lk = String.valueOf(((Number) s.get("level")).intValue());
                perLevel.put(lk, perLevel.getOrDefault(lk, 0) + 1);
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("events_accepted", accepted);
        summary.put("events_rejected", audit.size() - accepted);
        summary.put("live_segment_count", live);
        summary.put("merged_segment_count", merged);
        summary.put("per_level_live_counts", perLevel);
        summary.put("total_compactions_accepted", compsAcc);
        summary.put("total_events", events.size());
        summary.put("total_flushes_accepted", flushesAcc);
        summary.put("total_segments_ever", state.size());

        Map<String, Object> out = new HashMap<>();
        out.put("segment_states", Map.of("segments", segsSorted));
        out.put("compact_decisions", Map.of("decisions", decisions));
        out.put("event_audit", Map.of("events", auditSorted));
        out.put("violations", Map.of("violations", violations));
        out.put("summary", summary);
        return out;
    }

    @SuppressWarnings("unchecked")
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

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject eventsDoc = readObject(inDir.resolve("events.json"));
        JsonObject config = readObject(inDir.resolve("config.json"));
        Map<String, Object> outputs = simulate(eventsDoc, config);

        writeCanonical(outDir.resolve("segment_states.json"), outputs.get("segment_states"));
        writeCanonical(outDir.resolve("compact_decisions.json"), outputs.get("compact_decisions"));
        writeCanonical(outDir.resolve("event_audit.json"), outputs.get("event_audit"));
        writeCanonical(outDir.resolve("violations.json"), outputs.get("violations"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
