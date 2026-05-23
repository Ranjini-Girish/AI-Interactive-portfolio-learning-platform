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
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/**
 * Oracle entrypoint for the breaker ledger audit task. Reads JSON inputs from
 * {@code CBSA_DATA_DIR} (default {@code /app/breakers}) and writes five audit
 * JSON files into {@code CBSA_AUDIT_DIR} (default {@code /app/audit}).
 */
public final class Main {

    private static final Gson GSON =
            new GsonBuilder().disableHtmlEscaping().setPrettyPrinting().create();

    private Main() {}

    public static void main(String[] args) {
        String dataDir = getenv("CBSA_DATA_DIR", "/app/breakers");
        String auditDir = getenv("CBSA_AUDIT_DIR", "/app/audit");
        try {
            run(dataDir, auditDir);
        } catch (Exception e) {
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static String getenv(String k, String def) {
        String v = System.getenv(k);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static void run(String dataDir, String auditDir) throws IOException {
        Path dataRoot = Path.of(dataDir);
        JsonObject pool = readJson(dataRoot.resolve("pool_state.json"));
        int currentDay = pool.get("current_day").getAsInt();

        JsonObject policy = readJson(dataRoot.resolve("policy.json"));
        int rollingWindowDays = policy.has("rolling_window_days")
                ? policy.get("rolling_window_days").getAsInt()
                : 1;
        if (rollingWindowDays < 1) {
            rollingWindowDays = 1;
        }

        JsonObject incidentLog = readJson(dataRoot.resolve("incident_log.json"));
        JsonArray events = incidentLog.getAsJsonArray("events");

        List<JsonObject> services = loadServices(dataRoot.resolve("services"));
        services.sort(Comparator.comparing(o -> o.get("service_id").getAsString()));

        Map<String, JsonObject> upstreams = loadUpstreams(dataRoot.resolve("upstreams"));

        List<JsonObject> candidates = new ArrayList<>();
        int ignored = 0;
        for (JsonElement el : events) {
            if (!el.isJsonObject()) {
                ignored++;
                continue;
            }
            JsonObject ev = el.getAsJsonObject();
            if (!boolVal(ev.get("accepted"))) {
                ignored++;
                continue;
            }
            int day = intVal(ev.get("day"));
            if (day > currentDay) {
                ignored++;
                continue;
            }
            candidates.add(ev);
        }
        candidates.sort(
                Comparator.comparingInt((JsonObject o) -> intVal(o.get("day")))
                        .thenComparing(o -> strVal(o.get("event_id"))));

        List<JsonObject> applied = new ArrayList<>();
        for (JsonObject ev : candidates) {
            String kind = strVal(ev.get("kind"));
            if (!incidentWellFormed(kind, ev)) {
                ignored++;
                continue;
            }
            applied.add(ev);
        }

        Map<String, Integer> deltaByTier = new HashMap<>();
        deltaByTier.put("bronze", 0);
        deltaByTier.put("gold", 0);
        deltaByTier.put("silver", 0);
        boolean silverSpike = false;
        Set<String> forceOpen = new HashSet<>();

        for (JsonObject ev : applied) {
            String kind = strVal(ev.get("kind"));
            switch (kind) {
                case "tier_threshold_delta":
                    String tt = strVal(ev.get("target_tier"));
                    deltaByTier.merge(tt, intVal(ev.get("delta")), Integer::sum);
                    break;
                case "silver_spike":
                    silverSpike = true;
                    break;
                case "force_open":
                    forceOpen.add(strVal(ev.get("service_id")));
                    break;
                default:
                    break;
            }
        }

        List<JsonObject> journal = new ArrayList<>();
        for (JsonObject ev : applied) {
            journal.add(journalEntry(ev));
        }
        journal.sort(
                Comparator.comparingInt((JsonObject o) -> intVal(o.get("day")))
                        .thenComparing(o -> strVal(o.get("event_id"))));

        JsonObject tiersOut = new JsonObject();
        for (String tier : List.of("bronze", "gold", "silver")) {
            int base = policy.getAsJsonObject("failure_thresholds_by_tier").get(tier).getAsInt();
            int ds = deltaByTier.getOrDefault(tier, 0);
            int adj = base + ds;
            if (adj < 1) {
                adj = 1;
            }
            JsonObject row = new JsonObject();
            row.addProperty("adjusted_threshold", adj);
            row.addProperty("base_threshold", base);
            row.addProperty("delta_sum", ds);
            tiersOut.add(tier, row);
        }

        int winStart = currentDay - (rollingWindowDays - 1);
        int goldPenaltyN =
                policy.has("gold_upstream_degraded_extra_failures")
                        ? policy.get("gold_upstream_degraded_extra_failures").getAsInt()
                        : 0;
        if (goldPenaltyN < 0) {
            goldPenaltyN = 0;
        }
        int silverExtra =
                policy.has("silver_spike_extra_failures")
                        ? policy.get("silver_spike_extra_failures").getAsInt()
                        : 0;
        if (silverExtra < 0) {
            silverExtra = 0;
        }

        int goldPenCount = 0;
        for (JsonObject sv : services) {
            String tier = sv.get("tier").getAsString();
            String upId = sv.get("upstream_id").getAsString();
            JsonObject up = upstreams.getOrDefault(upId, emptyUpstream(upId));
            if ("gold".equals(tier) && up.get("degraded").getAsBoolean() && goldPenaltyN > 0) {
                goldPenCount++;
            }
        }

        JsonArray svcOut = new JsonArray();
        int openN = 0;
        int trippedN = 0;

        for (JsonObject sv : services) {
            String sid = sv.get("service_id").getAsString();
            String tier = sv.get("tier").getAsString();
            String upId = sv.get("upstream_id").getAsString();
            JsonObject outcomes = sv.getAsJsonObject("outcomes_by_day");

            int raw = countFails(outcomes, winStart, currentDay);
            int rf = raw;
            for (JsonObject ev : applied) {
                if (!"fail_day_suppress".equals(strVal(ev.get("kind")))) {
                    continue;
                }
                if (!sid.equals(strVal(ev.get("service_id")))) {
                    continue;
                }
                for (int d : daySlice(ev.get("days"))) {
                    if (d < winStart || d > currentDay) {
                        continue;
                    }
                    String key = Integer.toString(d);
                    if (outcomes.has(key) && "fail".equals(outcomes.get(key).getAsString()) && rf > 0) {
                        rf--;
                    }
                }
            }
            if (rf < 0) {
                rf = 0;
            }

            JsonObject up = upstreams.getOrDefault(upId, emptyUpstream(upId));
            int eff = rf;
            if ("gold".equals(tier) && up.get("degraded").getAsBoolean() && goldPenaltyN > 0) {
                eff += goldPenaltyN;
            }
            if ("silver".equals(tier) && silverSpike) {
                eff += silverExtra;
            }

            int baseTh = policy.getAsJsonObject("failure_thresholds_by_tier").get(tier).getAsInt();
            int adjTh = baseTh + deltaByTier.getOrDefault(tier, 0);
            if (adjTh < 1) {
                adjTh = 1;
            }

            boolean forced = forceOpen.contains(sid);
            boolean numericTrip = eff >= adjTh;
            String state = "closed";
            boolean tripped = false;
            if (forced) {
                state = "open";
                tripped = true;
            } else if (numericTrip) {
                state = "open";
                tripped = true;
            }

            List<String> reasons = new ArrayList<>();
            if (forced) {
                reasons.add("force_open_incident");
            }
            if ("gold".equals(tier) && up.get("degraded").getAsBoolean() && goldPenaltyN > 0) {
                reasons.add("gold_upstream_degraded_penalty");
            }
            if ("silver".equals(tier) && silverSpike && silverExtra > 0) {
                reasons.add("silver_spike_active");
            }
            if (numericTrip) {
                reasons.add("threshold_exceeded");
            }
            reasons = uniqSort(reasons);

            if ("closed".equals(state)) {
                reasons = new ArrayList<>();
            }

            if ("open".equals(state)) {
                openN++;
            }
            if (tripped) {
                trippedN++;
            }

            JsonObject row = new JsonObject();
            row.addProperty("adjusted_threshold", adjTh);
            row.addProperty("computed_state", state);
            row.addProperty("effective_failures", eff);
            row.addProperty("raw_failures", raw);
            row.add("reasons", toJsonArray(reasons));
            row.addProperty("service_id", sid);
            row.addProperty("tier", tier);
            row.addProperty("tripped", tripped);
            row.addProperty("upstream_id", upId);
            svcOut.add(row);
        }

        Map<String, List<String>> touch = new TreeMap<>();
        for (JsonObject sv : services) {
            String upId = sv.get("upstream_id").getAsString();
            String sid = sv.get("service_id").getAsString();
            touch.computeIfAbsent(upId, k -> new ArrayList<>()).add(sid);
        }
        for (List<String> ss : touch.values()) {
            ss.sort(String::compareTo);
        }

        JsonObject upOut = new JsonObject();
        for (String k : touch.keySet()) {
            JsonObject u = upstreams.getOrDefault(k, emptyUpstream(k));
            JsonObject body = new JsonObject();
            body.addProperty("degraded", u.get("degraded").getAsBoolean());
            JsonArray refs = new JsonArray();
            for (String s : touch.get(k)) {
                refs.add(s);
            }
            body.add("referencing_services", refs);
            upOut.add(k, body);
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("applied_incident_events", journal.size());
        summary.addProperty("gold_services_with_upstream_penalty", goldPenCount);
        summary.addProperty("ignored_incident_events", ignored);
        summary.addProperty("open_services", openN);
        summary.addProperty("services_total", services.size());
        summary.addProperty("silver_spike_active", silverSpike);
        summary.addProperty("tripped_services", trippedN);

        Path outBase = Path.of(auditDir);
        Files.createDirectories(outBase);

        writeJson(outBase.resolve("service_verdicts.json"), wrap("services", svcOut));
        writeJson(outBase.resolve("tier_thresholds.json"), wrap("tiers", tiersOut));

        JsonArray appliedArr = new JsonArray();
        for (JsonObject j : journal) {
            appliedArr.add(j);
        }
        JsonObject ij = new JsonObject();
        ij.add("applied_events", appliedArr);
        writeJson(outBase.resolve("incident_journal.json"), ij);

        writeJson(outBase.resolve("upstream_touchpoints.json"), wrap("upstreams", upOut));
        writeJson(outBase.resolve("summary.json"), summary);
    }

    private static JsonObject wrap(String k, JsonElement v) {
        JsonObject o = new JsonObject();
        o.add(k, v);
        return o;
    }

    private static JsonObject emptyUpstream(String id) {
        JsonObject u = new JsonObject();
        u.addProperty("degraded", false);
        u.addProperty("upstream_id", id);
        return u;
    }

    private static JsonObject readJson(Path p) throws IOException {
        String s = Files.readString(p, StandardCharsets.UTF_8);
        return JsonParser.parseString(s).getAsJsonObject();
    }

    private static List<JsonObject> loadServices(Path dir) throws IOException {
        List<Path> files = new ArrayList<>();
        if (Files.isDirectory(dir)) {
            try (var stream = Files.list(dir)) {
                stream.filter(x -> x.toString().endsWith(".json")).sorted().forEach(files::add);
            }
        }
        List<JsonObject> out = new ArrayList<>();
        for (Path f : files) {
            JsonObject s = JsonParser.parseString(Files.readString(f, StandardCharsets.UTF_8)).getAsJsonObject();
            out.add(s);
        }
        return out;
    }

    private static Map<String, JsonObject> loadUpstreams(Path dir) throws IOException {
        Map<String, JsonObject> m = new HashMap<>();
        if (!Files.isDirectory(dir)) {
            return m;
        }
        try (var stream = Files.list(dir)) {
            for (Path p : stream.filter(x -> x.toString().endsWith(".json")).sorted().toList()) {
                String name = p.getFileName().toString();
                String stem = name.substring(0, name.length() - 5);
                try {
                    JsonObject u = JsonParser.parseString(Files.readString(p, StandardCharsets.UTF_8)).getAsJsonObject();
                    if (!u.has("degraded")) {
                        u.addProperty("degraded", false);
                    }
                    m.put(stem, u);
                } catch (Exception e) {
                    JsonObject u = new JsonObject();
                    u.addProperty("degraded", false);
                    u.addProperty("upstream_id", stem);
                    m.put(stem, u);
                }
            }
        }
        return m;
    }

    private static int countFails(JsonObject outcomes, int start, int end) {
        int n = 0;
        for (int d = start; d <= end; d++) {
            String key = Integer.toString(d);
            if (outcomes.has(key) && "fail".equals(outcomes.get(key).getAsString())) {
                n++;
            }
        }
        return n;
    }

    private static boolean incidentWellFormed(String kind, JsonObject ev) {
        return switch (kind) {
            case "tier_threshold_delta" -> {
                String tt = strVal(ev.get("target_tier"));
                if (!"gold".equals(tt) && !"silver".equals(tt) && !"bronze".equals(tt)) {
                    yield false;
                }
                yield ev.has("delta");
            }
            case "fail_day_suppress" -> !strVal(ev.get("service_id")).isEmpty() && ev.has("days");
            case "silver_spike" -> true;
            case "force_open" -> !strVal(ev.get("service_id")).isEmpty();
            default -> false;
        };
    }

    private static JsonObject journalEntry(JsonObject ev) {
        String kind = strVal(ev.get("kind"));
        JsonObject m = new JsonObject();
        m.addProperty("day", intVal(ev.get("day")));
        m.addProperty("event_id", strVal(ev.get("event_id")));
        m.addProperty("kind", kind);
        switch (kind) {
            case "tier_threshold_delta":
                m.addProperty("delta", intVal(ev.get("delta")));
                m.addProperty("target_tier", strVal(ev.get("target_tier")));
                break;
            case "fail_day_suppress":
                m.add("days", toJsonIntArray(daySlice(ev.get("days"))));
                m.addProperty("service_id", strVal(ev.get("service_id")));
                break;
            case "force_open":
                m.addProperty("service_id", strVal(ev.get("service_id")));
                break;
            default:
                break;
        }
        return sortKeysRecursive(m);
    }

    /** Recursively sort object keys lexicographically for deterministic output. */
    private static JsonObject sortKeysRecursive(JsonObject in) {
        JsonObject out = new JsonObject();
        List<String> keys = new ArrayList<>();
        for (Map.Entry<String, JsonElement> e : in.entrySet()) {
            keys.add(e.getKey());
        }
        keys.sort(String::compareTo);
        for (String k : keys) {
            JsonElement v = in.get(k);
            if (v.isJsonObject()) {
                out.add(k, sortKeysRecursive(v.getAsJsonObject()));
            } else if (v.isJsonArray()) {
                JsonArray arr = v.getAsJsonArray();
                JsonArray na = new JsonArray();
                for (JsonElement el : arr) {
                    if (el.isJsonObject()) {
                        na.add(sortKeysRecursive(el.getAsJsonObject()));
                    } else {
                        na.add(el);
                    }
                }
                out.add(k, na);
            } else {
                out.add(k, v);
            }
        }
        return out;
    }

    private static JsonArray toJsonArray(List<String> strings) {
        JsonArray a = new JsonArray();
        for (String s : strings) {
            a.add(s);
        }
        return a;
    }

    private static JsonArray toJsonIntArray(List<Integer> ints) {
        JsonArray a = new JsonArray();
        for (int i : ints) {
            a.add(i);
        }
        return a;
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        JsonObject sorted = sortKeysRecursive(root);
        String text = GSON.toJson(sorted) + "\n";
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        for (byte b : bytes) {
            if (b < 0) {
                throw new IOException("non-ASCII output");
            }
        }
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static boolean boolVal(JsonElement v) {
        return v != null && v.isJsonPrimitive() && v.getAsJsonPrimitive().isBoolean() && v.getAsBoolean();
    }

    private static String strVal(JsonElement v) {
        if (v == null || v.isJsonNull()) {
            return "";
        }
        if (v.isJsonPrimitive()) {
            return v.getAsString();
        }
        return v.toString();
    }

    private static int intVal(JsonElement v) {
        if (v == null || v.isJsonNull()) {
            return 0;
        }
        if (v.isJsonPrimitive()) {
            try {
                return v.getAsInt();
            } catch (Exception e) {
                try {
                    return (int) v.getAsDouble();
                } catch (Exception e2) {
                    return 0;
                }
            }
        }
        return 0;
    }

    private static List<Integer> daySlice(JsonElement v) {
        List<Integer> out = new ArrayList<>();
        if (v == null || !v.isJsonArray()) {
            return out;
        }
        for (JsonElement x : v.getAsJsonArray()) {
            out.add(intVal(x));
        }
        return out;
    }

    private static List<String> uniqSort(List<String> in) {
        TreeSet<String> ts = new TreeSet<>(in);
        return new ArrayList<>(ts);
    }
}
