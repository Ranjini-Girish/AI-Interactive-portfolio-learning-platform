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
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

public final class Replay {
    private Replay() {}

    private static final String[] VALID_CODES = {
        "D_CYCLE_DETECTED",
        "D_FUTURE_TIMESTAMP",
        "D_INCOMPLETE_TRACE",
        "D_MULTI_ROOT",
        "D_ORPHAN_SPAN"
    };

    private static int sha256Bucket(String hashSeed, String traceId) throws Exception {
        MessageDigest md = MessageDigest.getInstance("SHA-256");
        byte[] digest = md.digest((hashSeed + ":" + traceId).getBytes(StandardCharsets.UTF_8));
        long val = 0;
        for (int i = 0; i < 8; i++) {
            val = (val << 8) | (digest[i] & 0xffL);
        }
        return (int) Long.remainderUnsigned(val, 1000);
    }

    private static Object[] evaluatePolicies(
            JsonArray policies, List<JsonObject> traceSpans, String traceId) throws Exception {
        Set<String> statuses = new HashSet<>();
        Set<String> services = new HashSet<>();
        for (JsonObject s : traceSpans) {
            statuses.add(s.get("status").getAsString());
            services.add(s.get("service").getAsString());
        }
        for (JsonElement pel : policies) {
            JsonObject p = pel.getAsJsonObject();
            String t = p.get("type").getAsString();
            if ("status_match".equals(t)) {
                boolean okStatus = false;
                for (JsonElement se : p.getAsJsonArray("statuses")) {
                    if (statuses.contains(se.getAsString())) {
                        okStatus = true;
                        break;
                    }
                }
                boolean okSvc = true;
                if (p.has("services")) {
                    okSvc = false;
                    for (JsonElement se : p.getAsJsonArray("services")) {
                        if (services.contains(se.getAsString())) {
                            okSvc = true;
                            break;
                        }
                    }
                }
                if (okStatus && okSvc) {
                    return new Object[] {p, p.get("action").getAsString()};
                }
            } else if ("latency".equals(t)) {
                String mode = p.get("mode").getAsString();
                int thr = p.get("threshold_ms").getAsInt();
                boolean matched = false;
                if ("any_span".equals(mode)) {
                    for (JsonObject s : traceSpans) {
                        if (s.get("duration_ms").getAsInt() >= thr) {
                            matched = true;
                            break;
                        }
                    }
                } else if ("root_span".equals(mode)) {
                    List<JsonObject> roots = new ArrayList<>();
                    for (JsonObject s : traceSpans) {
                        if (s.get("parent_span_id").isJsonNull()) {
                            roots.add(s);
                        }
                    }
                    if (roots.size() == 1) {
                        matched = roots.get(0).get("duration_ms").getAsInt() >= thr;
                    }
                } else if ("trace_total".equals(mode)) {
                    if (!traceSpans.isEmpty()) {
                        long maxEnd = Long.MIN_VALUE;
                        long minStart = Long.MAX_VALUE;
                        for (JsonObject s : traceSpans) {
                            long start = s.get("start_unix_ms").getAsLong();
                            long end = start + s.get("duration_ms").getAsLong();
                            maxEnd = Math.max(maxEnd, end);
                            minStart = Math.min(minStart, start);
                        }
                        matched = (maxEnd - minStart) >= thr;
                    }
                }
                if (matched) {
                    return new Object[] {p, p.get("action").getAsString()};
                }
            } else if ("attribute".equals(t)) {
                String key = p.get("key").getAsString();
                Set<String> values = new HashSet<>();
                for (JsonElement ve : p.getAsJsonArray("values")) {
                    values.add(ve.getAsString());
                }
                boolean hit = false;
                for (JsonObject s : traceSpans) {
                    JsonObject attrs = s.getAsJsonObject("attributes");
                    if (attrs.has(key) && values.contains(attrs.get(key).getAsString())) {
                        hit = true;
                        break;
                    }
                }
                if (hit) {
                    return new Object[] {p, p.get("action").getAsString()};
                }
            } else if ("service".equals(t)) {
                boolean hit = false;
                for (JsonElement se : p.getAsJsonArray("services")) {
                    if (services.contains(se.getAsString())) {
                        hit = true;
                        break;
                    }
                }
                if (hit) {
                    return new Object[] {p, p.get("action").getAsString()};
                }
            } else if ("probabilistic".equals(t)) {
                int bucket = sha256Bucket(p.get("hash_seed").getAsString(), traceId);
                String action =
                        bucket < p.get("sampling_rate_per_mille").getAsInt() ? "keep" : "drop";
                return new Object[] {p, action};
            }
        }
        return new Object[] {null, "drop"};
    }

    private static Map<String, Object> simulate(
            JsonObject spansIn, JsonObject policiesIn, JsonObject config) throws Exception {
        JsonObject severityRanks = config.getAsJsonObject("severity_ranks");
        long nowUnixMs = config.get("now_unix_ms").getAsLong();
        int futureThresh = config.get("future_timestamp_threshold_ms").getAsInt();
        int minSpans = config.get("min_spans_per_trace").getAsInt();

        Map<String, List<JsonObject>> byTrace = new TreeMap<>();
        for (JsonElement el : spansIn.getAsJsonArray("spans")) {
            JsonObject sp = el.getAsJsonObject();
            String tid = sp.get("trace_id").getAsString();
            byTrace.computeIfAbsent(tid, k -> new ArrayList<>()).add(sp);
        }

        List<Map<String, Object>> decisions = new ArrayList<>();
        List<Map<String, Object>> diagnostics = new ArrayList<>();

        Map<String, Integer> polMatch = new TreeMap<>();
        Map<String, Integer> polKeep = new TreeMap<>();
        Map<String, Integer> polDrop = new TreeMap<>();
        for (JsonElement pel : policiesIn.getAsJsonArray("policies")) {
            String name = pel.getAsJsonObject().get("name").getAsString();
            polMatch.put(name, 0);
            polKeep.put(name, 0);
            polDrop.put(name, 0);
        }

        for (String traceId : byTrace.keySet()) {
            List<JsonObject> traceSpans = new ArrayList<>(byTrace.get(traceId));
            traceSpans.sort(
                    Comparator.comparing((JsonObject s) -> s.get("start_unix_ms").getAsLong())
                            .thenComparing(s -> s.get("span_id").getAsString()));
            Set<String> spanIds = new HashSet<>();
            for (JsonObject s : traceSpans) {
                spanIds.add(s.get("span_id").getAsString());
            }
            List<JsonObject> roots = new ArrayList<>();
            Map<String, String> parentOf = new TreeMap<>();
            for (JsonObject s : traceSpans) {
                if (s.get("parent_span_id").isJsonNull()) {
                    roots.add(s);
                }
                parentOf.put(
                        s.get("span_id").getAsString(),
                        s.get("parent_span_id").isJsonNull()
                                ? null
                                : s.get("parent_span_id").getAsString());
            }

            Set<String> cycleMembers = new HashSet<>();
            for (String sid : spanIds) {
                Set<String> seen = new HashSet<>();
                List<String> visited = new ArrayList<>();
                String cur = sid;
                while (cur != null && parentOf.containsKey(cur)) {
                    if (seen.contains(cur)) {
                        int idx = visited.indexOf(cur);
                        cycleMembers.addAll(visited.subList(idx, visited.size()));
                        break;
                    }
                    seen.add(cur);
                    visited.add(cur);
                    cur = parentOf.get(cur);
                }
            }
            boolean hasCycle = !cycleMembers.isEmpty();

            List<String[]> orphanPairs = new ArrayList<>();
            for (JsonObject s : traceSpans) {
                if (!s.get("parent_span_id").isJsonNull()) {
                    String p = s.get("parent_span_id").getAsString();
                    if (!spanIds.contains(p)) {
                        orphanPairs.add(
                                new String[] {s.get("span_id").getAsString(), p});
                    }
                }
            }

            boolean hasMultiRoot = roots.size() >= 2;
            boolean isIncomplete = traceSpans.size() < minSpans;

            String reason;
            String decision;
            String matchedPolicy = null;

            if (hasCycle) {
                reason = "cycle_detected";
                decision = config.get("cycle_action").getAsString();
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("cycle_span_ids", new ArrayList<>(cycleMembers));
                ((List<String>) evidence.get("cycle_span_ids")).sort(String::compareTo);
                addDiag(
                        diagnostics,
                        "D_CYCLE_DETECTED",
                        "error",
                        traceId,
                        null,
                        evidence,
                        severityRanks);
            } else if (hasMultiRoot) {
                reason = "multi_root";
                decision = config.get("multi_root_action").getAsString();
            } else if (isIncomplete) {
                reason = "incomplete_trace";
                decision = config.get("incomplete_action").getAsString();
            } else if (!orphanPairs.isEmpty()) {
                reason = "orphan_span";
                decision = config.get("orphan_action").getAsString();
            } else {
                Object[] eval =
                        evaluatePolicies(
                                policiesIn.getAsJsonArray("policies"), traceSpans, traceId);
                JsonObject matched = (JsonObject) eval[0];
                if (matched != null) {
                    reason = "policy_match";
                    matchedPolicy = matched.get("name").getAsString();
                    decision = (String) eval[1];
                    polMatch.put(matchedPolicy, polMatch.get(matchedPolicy) + 1);
                    if ("keep".equals(decision)) {
                        polKeep.put(matchedPolicy, polKeep.get(matchedPolicy) + 1);
                    } else {
                        polDrop.put(matchedPolicy, polDrop.get(matchedPolicy) + 1);
                    }
                } else {
                    reason = "no_policy_matched";
                    decision = "drop";
                }
            }

            if (hasMultiRoot) {
                List<String> rootIds = new ArrayList<>();
                for (JsonObject r : roots) {
                    rootIds.add(r.get("span_id").getAsString());
                }
                rootIds.sort(String::compareTo);
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("root_span_ids", rootIds);
                addDiag(
                        diagnostics,
                        "D_MULTI_ROOT",
                        "warn",
                        traceId,
                        null,
                        evidence,
                        severityRanks);
            }
            if (isIncomplete) {
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("actual_spans", traceSpans.size());
                evidence.put("min_required", minSpans);
                addDiag(
                        diagnostics,
                        "D_INCOMPLETE_TRACE",
                        "info",
                        traceId,
                        null,
                        evidence,
                        severityRanks);
            }
            for (String[] pair : orphanPairs) {
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("missing_parent_span_id", pair[1]);
                addDiag(
                        diagnostics,
                        "D_ORPHAN_SPAN",
                        "warn",
                        traceId,
                        pair[0],
                        evidence,
                        severityRanks);
            }

            for (JsonObject s : traceSpans) {
                long skew = s.get("start_unix_ms").getAsLong() - nowUnixMs;
                if (skew > futureThresh) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("now_unix_ms", nowUnixMs);
                    evidence.put("skew_ms", skew);
                    evidence.put("start_unix_ms", s.get("start_unix_ms").getAsLong());
                    addDiag(
                            diagnostics,
                            "D_FUTURE_TIMESTAMP",
                            "warn",
                            traceId,
                            s.get("span_id").getAsString(),
                            evidence,
                            severityRanks);
                }
            }

            Map<String, Object> decRow = new TreeMap<>();
            decRow.put("decision", decision);
            decRow.put("matched_policy", matchedPolicy);
            decRow.put("reason", reason);
            decRow.put("trace_id", traceId);
            decisions.add(decRow);
        }

        decisions.sort(Comparator.comparing(d -> (String) d.get("trace_id")));

        diagnostics.sort(
                Comparator.comparing((Map<String, Object> d) -> (Integer) d.get("severity_rank"))
                        .thenComparing(d -> (String) d.get("trace_id"))
                        .thenComparing(d -> (String) d.get("code"))
                        .thenComparing(
                                d -> {
                                    String sid = (String) d.get("span_id");
                                    return sid == null ? "" : sid;
                                }));

        List<Map<String, Object>> polStats = new ArrayList<>();
        for (JsonElement pel : policiesIn.getAsJsonArray("policies")) {
            JsonObject p = pel.getAsJsonObject();
            String name = p.get("name").getAsString();
            Map<String, Object> row = new TreeMap<>();
            row.put("dropped_count", polDrop.get(name));
            row.put("kept_count", polKeep.get(name));
            row.put("matched_count", polMatch.get(name));
            row.put("name", name);
            row.put("type", p.get("type").getAsString());
            polStats.add(row);
        }
        polStats.sort(Comparator.comparing(r -> (String) r.get("name")));

        Map<String, String> decisionsByTrace = new TreeMap<>();
        for (Map<String, Object> d : decisions) {
            decisionsByTrace.put((String) d.get("trace_id"), (String) d.get("decision"));
        }

        Map<String, Long> traceTotalDur = new TreeMap<>();
        for (Map.Entry<String, List<JsonObject>> e : byTrace.entrySet()) {
            List<JsonObject> ts = e.getValue();
            if (ts.isEmpty()) {
                traceTotalDur.put(e.getKey(), 0L);
                continue;
            }
            long maxEnd = Long.MIN_VALUE;
            long minStart = Long.MAX_VALUE;
            for (JsonObject s : ts) {
                long start = s.get("start_unix_ms").getAsLong();
                long end = start + s.get("duration_ms").getAsLong();
                maxEnd = Math.max(maxEnd, end);
                minStart = Math.min(minStart, start);
            }
            traceTotalDur.put(e.getKey(), maxEnd - minStart);
        }

        Map<String, Map<String, Object>> servicesSeen = new TreeMap<>();
        Map<String, Set<String>> serviceTraces = new TreeMap<>();
        for (JsonElement el : spansIn.getAsJsonArray("spans")) {
            JsonObject sp = el.getAsJsonObject();
            String svc = sp.get("service").getAsString();
            Map<String, Object> entry =
                    servicesSeen.computeIfAbsent(
                            svc,
                            k -> {
                                Map<String, Object> m = new TreeMap<>();
                                m.put("dropped_traces", 0);
                                m.put("error_spans", 0);
                                m.put("kept_traces", 0);
                                m.put("max_trace_duration_ms", 0);
                                m.put("service", svc);
                                m.put("span_count", 0);
                                m.put("timeout_spans", 0);
                                m.put("trace_count", 0);
                                return m;
                            });
            entry.put("span_count", ((Integer) entry.get("span_count")) + 1);
            if ("error".equals(sp.get("status").getAsString())) {
                entry.put("error_spans", ((Integer) entry.get("error_spans")) + 1);
            }
            if ("timeout".equals(sp.get("status").getAsString())) {
                entry.put("timeout_spans", ((Integer) entry.get("timeout_spans")) + 1);
            }
            serviceTraces.computeIfAbsent(svc, k -> new HashSet<>()).add(sp.get("trace_id").getAsString());
        }

        for (Map.Entry<String, Set<String>> e : serviceTraces.entrySet()) {
            String svc = e.getKey();
            Set<String> traces = e.getValue();
            Map<String, Object> entry = servicesSeen.get(svc);
            entry.put("trace_count", traces.size());
            int kept = 0;
            int dropped = 0;
            long maxDur = 0;
            for (String t : traces) {
                if ("keep".equals(decisionsByTrace.get(t))) {
                    kept++;
                } else if ("drop".equals(decisionsByTrace.get(t))) {
                    dropped++;
                }
                maxDur = Math.max(maxDur, traceTotalDur.getOrDefault(t, 0L));
            }
            entry.put("kept_traces", kept);
            entry.put("dropped_traces", dropped);
            entry.put("max_trace_duration_ms", maxDur);
        }

        List<Map<String, Object>> serviceStats = new ArrayList<>(servicesSeen.values());
        serviceStats.sort(Comparator.comparing(r -> (String) r.get("service")));

        int spansTotal = spansIn.getAsJsonArray("spans").size();
        int tracesTotal = byTrace.size();
        int keptTraces = 0;
        for (Map<String, Object> d : decisions) {
            if ("keep".equals(d.get("decision"))) {
                keptTraces++;
            }
        }
        int tracesDropped = tracesTotal - keptTraces;

        Map<String, Integer> codeCounts = new TreeMap<>();
        for (String c : VALID_CODES) {
            codeCounts.put(c, 0);
        }
        for (Map<String, Object> d : diagnostics) {
            String code = (String) d.get("code");
            codeCounts.put(code, codeCounts.get(code) + 1);
        }

        String hottest = null;
        if (spansTotal != 0) {
            int bestSpan = -1;
            for (Map<String, Object> x : serviceStats) {
                int sc = (Integer) x.get("span_count");
                String svc = (String) x.get("service");
                if (sc > bestSpan || (sc == bestSpan && (hottest == null || svc.compareTo(hottest) < 0))) {
                    hottest = svc;
                    bestSpan = sc;
                }
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("anomaly_counts", codeCounts);
        summary.put("hottest_service", hottest);
        summary.put("kept_traces", keptTraces);
        summary.put("spans_total", spansTotal);
        summary.put("traces_dropped", tracesDropped);
        summary.put("traces_total", tracesTotal);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("sampling_decisions", Map.of("decisions", decisions));
        out.put("policy_stats", Map.of("policies", polStats));
        out.put("service_stats", Map.of("services", serviceStats));
        out.put("trace_diagnostics", Map.of("diagnostics", diagnostics));
        out.put("summary", summary);
        return out;
    }

    private static void addDiag(
            List<Map<String, Object>> diagnostics,
            String code,
            String severity,
            String traceId,
            String spanId,
            Map<String, Object> evidence,
            JsonObject severityRanks) {
        Map<String, Object> row = new TreeMap<>();
        row.put("code", code);
        row.put("evidence", evidence);
        row.put("severity", severity);
        row.put("severity_rank", severityRanks.get(severity).getAsInt());
        row.put("span_id", spanId);
        row.put("trace_id", traceId);
        diagnostics.add(row);
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

        JsonObject spans = readObject(inDir.resolve("spans.json"));
        JsonObject policies = readObject(inDir.resolve("policies.json"));
        JsonObject config = readObject(inDir.resolve("config.json"));
        Map<String, Object> outputs = simulate(spans, policies, config);

        writeCanonical(outDir.resolve("sampling_decisions.json"), outputs.get("sampling_decisions"));
        writeCanonical(outDir.resolve("service_stats.json"), outputs.get("service_stats"));
        writeCanonical(outDir.resolve("policy_stats.json"), outputs.get("policy_stats"));
        writeCanonical(outDir.resolve("trace_diagnostics.json"), outputs.get("trace_diagnostics"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
