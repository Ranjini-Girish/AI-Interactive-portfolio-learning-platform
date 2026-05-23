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
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class Replay {
    private Replay() {}

    private static final Map<String, Integer> SEVERITY_RANK =
            Map.of("error", 0, "warning", 1, "note", 2);

    private static final Pattern DIAG_LINE =
            Pattern.compile(
                    "^\\s*\\|\\s*`?(?<code>[A-Z][A-Z0-9_]+)`?\\s*\\|\\s*"
                            + "(?<severity>error|warning|note)\\s*\\|");

    private static Map<String, String> loadDiagSeverity(Path docsPath) throws IOException {
        String text = Files.readString(docsPath, StandardCharsets.UTF_8);
        Map<String, String> severity = new TreeMap<>();
        for (String line : text.split("\n")) {
            Matcher m = DIAG_LINE.matcher(line);
            if (m.find()) {
                severity.put(m.group("code"), m.group("severity"));
            }
        }
        if (severity.isEmpty()) {
            throw new IOException("could not parse diagnostic codes from " + docsPath);
        }
        return severity;
    }

    private static int effective(Map<String, Object> ep, JsonObject policy, String key) {
        Object val = ep.get(key);
        if (val == null) {
            return policy.get("default_" + key).getAsInt();
        }
        return ((Number) val).intValue();
    }

    private static void addDiag(
            Map<Integer, List<Map<String, Object>>> diags,
            int seq,
            String code,
            String endpointId,
            Map<String, String> diagSeverity) {
        Map<String, Object> row = new TreeMap<>();
        row.put("code", code);
        row.put("endpoint_id", endpointId);
        row.put("severity", diagSeverity.get(code));
        diags.computeIfAbsent(seq, k -> new ArrayList<>()).add(row);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> newEndpoint(
            String id,
            JsonObject src,
            boolean fromEvent) {
        Map<String, Object> ep = new HashMap<>();
        ep.put("id", id);
        if (fromEvent) {
            ep.put(
                    "failure_threshold_pct",
                    jsonIntOrNull(src, "failure_threshold_pct"));
            ep.put("window_size", jsonIntOrNull(src, "window_size"));
            ep.put("half_open_max_probes", jsonIntOrNull(src, "half_open_max_probes"));
            ep.put("recovery_ticks", jsonIntOrNull(src, "recovery_ticks"));
        } else {
            ep.put(
                    "failure_threshold_pct",
                    jsonIntOrNull(src, "failure_threshold_pct"));
            ep.put("window_size", jsonIntOrNull(src, "window_size"));
            ep.put("half_open_max_probes", jsonIntOrNull(src, "half_open_max_probes"));
            ep.put("recovery_ticks", jsonIntOrNull(src, "recovery_ticks"));
        }
        ep.put("state", "CLOSED");
        ep.put("window", new ArrayDeque<String[]>());
        ep.put("probes_used", 0);
        ep.put("probe_successes", 0);
        ep.put("probe_failures", 0);
        ep.put("tick_entered_open", null);
        ep.put("last_state_change_seq", null);
        ep.put("state_transition_count", 0);
        ep.put("total_admitted", 0);
        ep.put("total_short_circuited", 0);
        ep.put("total_successes", 0);
        ep.put("total_failures", 0);
        ep.put("total_timeouts", 0);
        return ep;
    }

    private static Integer jsonIntOrNull(JsonObject obj, String key) {
        if (!obj.has(key) || obj.get(key).isJsonNull()) {
            return null;
        }
        return obj.get(key).getAsInt();
    }

    private static Map<String, Object> runSimulation(
            List<JsonObject> initialEndpoints,
            JsonArray events,
            JsonObject policy,
            Map<String, String> diagSeverity) {
        Map<String, Map<String, Object>> endpoints = new TreeMap<>();
        for (JsonObject e : initialEndpoints) {
            endpoints.put(e.get("id").getAsString(), newEndpoint(e.get("id").getAsString(), e, false));
        }

        List<Map<String, Object>> transitions = new ArrayList<>();
        List<Map<String, Object>> requests = new ArrayList<>();
        Map<Integer, List<Map<String, Object>>> diagnostics = new TreeMap<>();
        final int[] globalTick = {0};
        final int[] peakOpenEndpoints = {0};

        class Ctx {
            void emitTransition(
                    Map<String, Object> ep,
                    int seq,
                    int tick,
                    String fromState,
                    String toState,
                    String reason) {
                ep.put("state", toState);
                ep.put("last_state_change_seq", seq);
                ep.put("state_transition_count", ((Integer) ep.get("state_transition_count")) + 1);
                if (policy.get("track_state_transitions").getAsBoolean()) {
                    Map<String, Object> t = new TreeMap<>();
                    t.put("endpoint_id", ep.get("id"));
                    t.put("from_state", fromState);
                    t.put("reason", reason);
                    t.put("seq", seq);
                    t.put("tick", tick);
                    t.put("to_state", toState);
                    transitions.add(t);
                }
                String code;
                if ("OPEN".equals(toState)) {
                    code = "N_TRANSITION_TO_OPEN";
                } else if ("HALF_OPEN".equals(toState)) {
                    code = "N_TRANSITION_TO_HALF_OPEN";
                } else {
                    code = "N_TRANSITION_TO_CLOSED";
                }
                addDiag(diagnostics, seq, code, (String) ep.get("id"), diagSeverity);
            }

            void timeBasedPrune(Map<String, Object> ep) {
                if (!"time_based".equals(policy.get("sliding_strategy").getAsString())) {
                    return;
                }
                int ws = effective(ep, policy, "window_size");
                int cutoff = globalTick[0] - ws + 1;
                Deque<String[]> window = (Deque<String[]>) ep.get("window");
                while (!window.isEmpty() && Integer.parseInt(window.peekFirst()[1]) < cutoff) {
                    window.removeFirst();
                }
            }

            void thresholdCheck(Map<String, Object> ep, int seq, int tick) {
                if (!"CLOSED".equals(ep.get("state"))) {
                    return;
                }
                int ws = effective(ep, policy, "window_size");
                Deque<String[]> window = (Deque<String[]>) ep.get("window");
                if ("count_based".equals(policy.get("sliding_strategy").getAsString())) {
                    while (window.size() > ws) {
                        window.removeFirst();
                    }
                }
                int n = window.size();
                if (n < policy.get("min_window_observations").getAsInt()) {
                    return;
                }
                int fails = 0;
                for (String[] oc : window) {
                    if ("failure".equals(oc[0]) || "timeout".equals(oc[0])) {
                        fails++;
                    }
                }
                if ((fails * 100) / n >= effective(ep, policy, "failure_threshold_pct")) {
                    ep.put("tick_entered_open", tick);
                    emitTransition(ep, seq, tick, "CLOSED", "OPEN", "threshold_breach");
                }
            }

            void updatePeak() {
                int c = 0;
                for (Map<String, Object> ep : endpoints.values()) {
                    if ("OPEN".equals(ep.get("state"))) {
                        c++;
                    }
                }
                if (c > peakOpenEndpoints[0]) {
                    peakOpenEndpoints[0] = c;
                }
            }
        }
        Ctx ctx = new Ctx();

        for (JsonElement el : events) {
            JsonObject ev = el.getAsJsonObject();
            int seq = ev.get("seq").getAsInt();
            String op = ev.get("op").getAsString();

            if ("request".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                String outcome = ev.get("outcome").getAsString();
                Map<String, Object> ep = endpoints.get(eid);
                if (ep == null) {
                    addDiag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                if ("OPEN".equals(ep.get("state"))) {
                    ep.put("total_short_circuited", ((Integer) ep.get("total_short_circuited")) + 1);
                    Map<String, Object> req = new TreeMap<>();
                    req.put("admission", "short_circuited");
                    req.put("endpoint_id", eid);
                    req.put("outcome", outcome);
                    req.put("seq", seq);
                    req.put("state_at_admission", "OPEN");
                    requests.add(req);
                    addDiag(diagnostics, seq, "N_REQUEST_SHORT_CIRCUITED", eid, diagSeverity);
                } else if ("CLOSED".equals(ep.get("state"))) {
                    ctx.timeBasedPrune(ep);
                    Deque<String[]> window = (Deque<String[]>) ep.get("window");
                    window.addLast(new String[] {outcome, String.valueOf(globalTick[0])});
                    ep.put("total_admitted", ((Integer) ep.get("total_admitted")) + 1);
                    if ("success".equals(outcome)) {
                        ep.put("total_successes", ((Integer) ep.get("total_successes")) + 1);
                    } else if ("failure".equals(outcome)) {
                        ep.put("total_failures", ((Integer) ep.get("total_failures")) + 1);
                    } else {
                        ep.put("total_timeouts", ((Integer) ep.get("total_timeouts")) + 1);
                    }
                    Map<String, Object> req = new TreeMap<>();
                    req.put("admission", "admitted");
                    req.put("endpoint_id", eid);
                    req.put("outcome", outcome);
                    req.put("seq", seq);
                    req.put("state_at_admission", "CLOSED");
                    requests.add(req);
                    ctx.thresholdCheck(ep, seq, globalTick[0]);
                } else {
                    ep.put("total_admitted", ((Integer) ep.get("total_admitted")) + 1);
                    if ("success".equals(outcome)) {
                        ep.put("total_successes", ((Integer) ep.get("total_successes")) + 1);
                    } else if ("failure".equals(outcome)) {
                        ep.put("total_failures", ((Integer) ep.get("total_failures")) + 1);
                    } else {
                        ep.put("total_timeouts", ((Integer) ep.get("total_timeouts")) + 1);
                    }
                    Map<String, Object> req = new TreeMap<>();
                    req.put("admission", "probe_admitted");
                    req.put("endpoint_id", eid);
                    req.put("outcome", outcome);
                    req.put("seq", seq);
                    req.put("state_at_admission", "HALF_OPEN");
                    requests.add(req);
                    addDiag(diagnostics, seq, "N_PROBE_ADMITTED", eid, diagSeverity);
                    ep.put("probes_used", ((Integer) ep.get("probes_used")) + 1);
                    if ("success".equals(outcome)) {
                        ep.put("probe_successes", ((Integer) ep.get("probe_successes")) + 1);
                    } else {
                        ep.put("probe_failures", ((Integer) ep.get("probe_failures")) + 1);
                    }
                    if (((Integer) ep.get("probe_failures")) >= 1) {
                        ep.put("probes_used", 0);
                        ep.put("probe_successes", 0);
                        ep.put("probe_failures", 0);
                        ep.put("tick_entered_open", globalTick[0]);
                        ctx.emitTransition(
                                ep, seq, globalTick[0], "HALF_OPEN", "OPEN", "probe_failure");
                    } else if (((Integer) ep.get("probe_successes"))
                            >= effective(ep, policy, "half_open_max_probes")) {
                        ep.put("probes_used", 0);
                        ep.put("probe_successes", 0);
                        ep.put("probe_failures", 0);
                        ((Deque<String[]>) ep.get("window")).clear();
                        ctx.emitTransition(
                                ep,
                                seq,
                                globalTick[0],
                                "HALF_OPEN",
                                "CLOSED",
                                "probe_success_quota");
                    }
                }
                ctx.updatePeak();
                continue;
            }
            if ("tick".equals(op)) {
                globalTick[0]++;
                for (String eid : endpoints.keySet()) {
                    Map<String, Object> ep = endpoints.get(eid);
                    if ("OPEN".equals(ep.get("state"))) {
                        int rt = effective(ep, policy, "recovery_ticks");
                        Integer entered = (Integer) ep.get("tick_entered_open");
                        if (entered != null && globalTick[0] - entered >= rt) {
                            ep.put("tick_entered_open", null);
                            ep.put("probes_used", 0);
                            ep.put("probe_successes", 0);
                            ep.put("probe_failures", 0);
                            ctx.emitTransition(
                                    ep, seq, globalTick[0], "OPEN", "HALF_OPEN", "recovery_timeout");
                        }
                    }
                }
                for (Map<String, Object> ep : endpoints.values()) {
                    ctx.timeBasedPrune(ep);
                }
                ctx.updatePeak();
                continue;
            }
            if ("add_endpoint".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                if (endpoints.containsKey(eid)) {
                    addDiag(diagnostics, seq, "E_DUPLICATE_ENDPOINT", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                endpoints.put(eid, newEndpoint(eid, ev, true));
                ctx.updatePeak();
                continue;
            }
            if ("remove_endpoint".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                if (!endpoints.containsKey(eid)) {
                    addDiag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                endpoints.remove(eid);
                ctx.updatePeak();
                continue;
            }
            if ("config_update".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                if (!endpoints.containsKey(eid)) {
                    addDiag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                Map<String, Object> ep = endpoints.get(eid);
                for (String key :
                        List.of(
                                "failure_threshold_pct",
                                "window_size",
                                "half_open_max_probes",
                                "recovery_ticks")) {
                    ep.put(key, jsonIntOrNull(ev, key));
                }
                continue;
            }
            if ("force_open".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                Map<String, Object> ep = endpoints.get(eid);
                if (ep == null) {
                    addDiag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                if ("OPEN".equals(ep.get("state"))) {
                    addDiag(diagnostics, seq, "W_FORCED_OPEN_NOOP", eid, diagSeverity);
                    ep.put("probes_used", 0);
                    ep.put("probe_successes", 0);
                    ep.put("probe_failures", 0);
                    ep.put("tick_entered_open", globalTick[0]);
                    ctx.updatePeak();
                    continue;
                }
                String fromState = (String) ep.get("state");
                addDiag(diagnostics, seq, "W_FORCED_OPEN", eid, diagSeverity);
                ep.put("probes_used", 0);
                ep.put("probe_successes", 0);
                ep.put("probe_failures", 0);
                ep.put("tick_entered_open", globalTick[0]);
                ctx.emitTransition(ep, seq, globalTick[0], fromState, "OPEN", "manual_open");
                ctx.updatePeak();
                continue;
            }
            if ("force_close".equals(op)) {
                String eid = ev.get("endpoint_id").getAsString();
                Map<String, Object> ep = endpoints.get(eid);
                if (ep == null) {
                    addDiag(diagnostics, seq, "E_ENDPOINT_NOT_FOUND", eid, diagSeverity);
                    ctx.updatePeak();
                    continue;
                }
                if ("CLOSED".equals(ep.get("state"))) {
                    addDiag(diagnostics, seq, "W_FORCED_CLOSE_NOOP", eid, diagSeverity);
                    ep.put("probes_used", 0);
                    ep.put("probe_successes", 0);
                    ep.put("probe_failures", 0);
                    ((Deque<String[]>) ep.get("window")).clear();
                    ctx.updatePeak();
                    continue;
                }
                String fromState = (String) ep.get("state");
                addDiag(diagnostics, seq, "W_FORCED_CLOSE", eid, diagSeverity);
                ep.put("probes_used", 0);
                ep.put("probe_successes", 0);
                ep.put("probe_failures", 0);
                ep.put("tick_entered_open", null);
                ((Deque<String[]>) ep.get("window")).clear();
                ctx.emitTransition(ep, seq, globalTick[0], fromState, "CLOSED", "manual_close");
                ctx.updatePeak();
                continue;
            }
            throw new IllegalArgumentException("unknown op: " + op);
        }

        List<Map<String, Object>> finalEndpoints = new ArrayList<>();
        for (String eid : endpoints.keySet()) {
            Map<String, Object> ep = endpoints.get(eid);
            Map<String, Object> row = new TreeMap<>();
            row.put(
                    "current_failure_threshold_pct",
                    effective(ep, policy, "failure_threshold_pct"));
            row.put(
                    "current_half_open_max_probes",
                    effective(ep, policy, "half_open_max_probes"));
            row.put("current_recovery_ticks", effective(ep, policy, "recovery_ticks"));
            row.put("current_window_size", effective(ep, policy, "window_size"));
            row.put("id", ep.get("id"));
            row.put("last_state_change_seq", ep.get("last_state_change_seq"));
            row.put("probe_failures", ep.get("probe_failures"));
            row.put("probe_successes", ep.get("probe_successes"));
            row.put("probes_used", ep.get("probes_used"));
            row.put("state", ep.get("state"));
            row.put("state_transition_count", ep.get("state_transition_count"));
            row.put("tick_entered_open", ep.get("tick_entered_open"));
            row.put("total_admitted", ep.get("total_admitted"));
            row.put("total_failures", ep.get("total_failures"));
            row.put("total_short_circuited", ep.get("total_short_circuited"));
            row.put("total_successes", ep.get("total_successes"));
            row.put("total_timeouts", ep.get("total_timeouts"));
            finalEndpoints.add(row);
        }

        List<Map<String, Object>> transitionsSorted = new ArrayList<>(transitions);
        transitionsSorted.sort(
                Comparator.comparing((Map<String, Object> t) -> (Integer) t.get("seq"))
                        .thenComparing(t -> (String) t.get("endpoint_id")));

        List<Map<String, Object>> diagEvents = new ArrayList<>();
        for (Integer seq : diagnostics.keySet()) {
            List<Map<String, Object>> diags = new ArrayList<>(diagnostics.get(seq));
            diags.sort(
                    Comparator.comparing(
                                    (Map<String, Object> d) ->
                                            SEVERITY_RANK.get((String) d.get("severity")))
                            .thenComparing(d -> (String) d.get("code"))
                            .thenComparing(d -> (String) d.get("endpoint_id")));
            Map<String, Object> ev = new TreeMap<>();
            ev.put("diagnostics", diags);
            ev.put("seq", seq);
            diagEvents.add(ev);
        }

        int totalAdmitted = 0;
        int totalShortCircuited = 0;
        int totalSuccesses = 0;
        int totalFailures = 0;
        int totalTimeouts = 0;
        for (Map<String, Object> r : requests) {
            String adm = (String) r.get("admission");
            if ("admitted".equals(adm) || "probe_admitted".equals(adm)) {
                totalAdmitted++;
                String oc = (String) r.get("outcome");
                if ("success".equals(oc)) {
                    totalSuccesses++;
                } else if ("failure".equals(oc)) {
                    totalFailures++;
                } else {
                    totalTimeouts++;
                }
            } else if ("short_circuited".equals(adm)) {
                totalShortCircuited++;
            }
        }

        int totalToOpen = 0;
        int totalToHalf = 0;
        int totalToClosed = 0;
        for (Map<String, Object> t : transitionsSorted) {
            String to = (String) t.get("to_state");
            if ("OPEN".equals(to)) {
                totalToOpen++;
            } else if ("HALF_OPEN".equals(to)) {
                totalToHalf++;
            } else if ("CLOSED".equals(to)) {
                totalToClosed++;
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("endpoints_at_end", endpoints.size());
        summary.put("events_with_diagnostics", diagEvents.size());
        summary.put("global_tick_at_end", globalTick[0]);
        summary.put("peak_open_endpoints", peakOpenEndpoints[0]);
        summary.put("total_admitted", totalAdmitted);
        summary.put("total_events", events.size());
        summary.put("total_failures", totalFailures);
        summary.put("total_requests", totalAdmitted + totalShortCircuited);
        summary.put("total_short_circuited", totalShortCircuited);
        summary.put("total_state_transitions", transitionsSorted.size());
        summary.put("total_successes", totalSuccesses);
        summary.put("total_timeouts", totalTimeouts);
        summary.put("total_transitions_to_closed", totalToClosed);
        summary.put("total_transitions_to_half_open", totalToHalf);
        summary.put("total_transitions_to_open", totalToOpen);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("final_endpoints", Map.of("endpoints", finalEndpoints));
        out.put("state_transitions", Map.of("transitions", transitionsSorted));
        out.put("request_log", Map.of("requests", requests));
        out.put("diagnostics", Map.of("events", diagEvents));
        out.put("summary", summary);
        return out;
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

        Path docs = inDir.getParent().resolve("docs").resolve("diagnostics.md");
        if (!Files.isRegularFile(docs)) {
            docs = Path.of("/app/docs/diagnostics.md");
        }
        Map<String, String> diagSeverity = loadDiagSeverity(docs);

        JsonObject epsDoc = readObject(inDir.resolve("endpoints.json"));
        JsonObject evsDoc = readObject(inDir.resolve("events.json"));
        JsonObject polDoc = readObject(inDir.resolve("policy.json"));

        List<JsonObject> initial = new ArrayList<>();
        for (JsonElement el : epsDoc.getAsJsonArray("endpoints")) {
            initial.add(el.getAsJsonObject());
        }

        Map<String, Object> outputs =
                runSimulation(initial, evsDoc.getAsJsonArray("events"), polDoc, diagSeverity);

        writeCanonical(outDir.resolve("final_endpoints.json"), outputs.get("final_endpoints"));
        writeCanonical(outDir.resolve("state_transitions.json"), outputs.get("state_transitions"));
        writeCanonical(outDir.resolve("request_log.json"), outputs.get("request_log"));
        writeCanonical(outDir.resolve("diagnostics.json"), outputs.get("diagnostics"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
