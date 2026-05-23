import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Ridge guard merge audit entrypoint. */
public final class RgmaAudit {

    private RgmaAudit() {}

    public static void main(String[] args) {
        if (run(args) != 0) {
            System.exit(1);
        }
    }

    private static int run(String[] args) {
        if (args.length != 2) {
            return 1;
        }
        Path dataDir = Path.of(args[0]);
        Path auditDir = Path.of(args[1]);
        try {
            compute(dataDir, auditDir);
            return 0;
        } catch (Exception ex) {
            return 1;
        }
    }

    private static JsonElement readJson(Path path) throws IOException {
        byte[] raw = Files.readAllBytes(path);
        return JsonParser.parseString(new String(raw, StandardCharsets.UTF_8));
    }

    private static void writeCanonical(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .serializeNulls()
                        .setPrettyPrinting()
                        .disableHtmlEscaping()
                        .create();
        String text = gson.toJson(root) + "\n";
        if (path.getParent() != null) {
            Files.createDirectories(path.getParent());
        }
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static long microFromScaled(double s) {
        String sStr = String.format(Locale.US, "%.17g", s);
        BigDecimal d = new BigDecimal(sStr);
        BigDecimal scaled = d.multiply(new BigDecimal("1000000"));
        return scaled.setScale(0, RoundingMode.HALF_EVEN).longValue();
    }

    private static long microFromCap(double cap) {
        String capStr = String.format(Locale.US, "%.17g", cap);
        BigDecimal d = new BigDecimal(capStr);
        BigDecimal scaled = d.multiply(new BigDecimal("1000000"));
        return scaled.setScale(0, RoundingMode.HALF_EVEN).longValue();
    }

    private static Double asFiniteDouble(JsonElement el) {
        if (el == null || el.isJsonNull()) {
            return null;
        }
        if (el.isJsonPrimitive() && el.getAsJsonPrimitive().isNumber()) {
            double v = el.getAsDouble();
            if (!Double.isFinite(v)) {
                return null;
            }
            return v;
        }
        return null;
    }

    private static JsonElement deepSort(JsonElement el) {
        if (el == null || el.isJsonNull()) {
            return el == null ? JsonNull.INSTANCE : el.deepCopy();
        }
        if (el.isJsonPrimitive()) {
            return el.deepCopy();
        }
        if (el.isJsonArray()) {
            JsonArray a = el.getAsJsonArray();
            JsonArray out = new JsonArray();
            for (JsonElement x : a) {
                out.add(deepSort(x));
            }
            return out;
        }
        JsonObject o = el.getAsJsonObject();
        TreeMap<String, JsonElement> sorted = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e : o.entrySet()) {
            sorted.put(e.getKey(), deepSort(e.getValue()));
        }
        JsonObject out = new JsonObject();
        for (Map.Entry<String, JsonElement> e : sorted.entrySet()) {
            out.add(e.getKey(), e.getValue());
        }
        return out;
    }

    private static String incidentCanon(JsonObject inc) {
        JsonElement sorted = deepSort(inc);
        Gson g = new GsonBuilder().disableHtmlEscaping().create();
        return g.toJson(sorted);
    }

    private static final class Host {
        String tier;
        double rawLambda;
        double biasSignal;
        boolean frozen;
    }

    private static final class Dsu {
        private final Map<String, String> parent = new HashMap<>();

        void makeSet(String x) {
            parent.putIfAbsent(x, x);
        }

        String find(String x) {
            parent.putIfAbsent(x, x);
            String p = parent.get(x);
            if (!p.equals(x)) {
                String r = find(p);
                parent.put(x, r);
                return r;
            }
            return p;
        }

        void union(String a, String b) {
            String ra = find(a);
            String rb = find(b);
            if (!ra.equals(rb)) {
                parent.put(rb, ra);
            }
        }
    }

    private static void compute(Path dataDir, Path auditDir) throws Exception {
        JsonObject policy = readJson(dataDir.resolve("policy.json")).getAsJsonObject();
        JsonObject layout = readJson(dataDir.resolve("domain_layout.json")).getAsJsonObject();
        JsonObject pool = readJson(dataDir.resolve("pool_state.json")).getAsJsonObject();
        JsonArray incidentsRaw = readJson(dataDir.resolve("incident_log.json")).getAsJsonArray();
        JsonObject window = readJson(dataDir.resolve("anchors/window.json")).getAsJsonObject();
        JsonObject dayFloor = readJson(dataDir.resolve("anchors/day_floor.json")).getAsJsonObject();
        JsonObject meta = readJson(dataDir.resolve("ancillary/meta.json")).getAsJsonObject();

        for (String k :
                new String[] {
                    "alias_guard",
                    "day_end",
                    "day_start",
                    "lambda_cap",
                    "signal_cutoff",
                    "tiers",
                }) {
            if (!policy.has(k)) {
                throw new IOException("missing policy key");
            }
        }
        if (!layout.has("hosts") || !layout.get("hosts").isJsonArray()) {
            throw new IOException("bad layout");
        }
        if (!pool.has("revision") || !pool.get("revision").isJsonPrimitive()) {
            throw new IOException("bad pool");
        }
        if (!window.has("start") || !window.has("end")) {
            throw new IOException("bad window");
        }
        if (!dayFloor.has("floor_day") || !dayFloor.get("floor_day").isJsonPrimitive()) {
            throw new IOException("bad day_floor");
        }
        if (!meta.has("alias_groups") || !meta.get("alias_groups").isJsonArray()) {
            throw new IOException("bad meta");
        }

        JsonObject tiers = policy.getAsJsonObject("tiers");
        for (String tname : new String[] {"gold", "silver", "bronze"}) {
            if (!tiers.has(tname)) {
                throw new IOException("missing tier");
            }
            Double tf = asFiniteDouble(tiers.get(tname));
            if (tf == null || tf <= 0.0) {
                throw new IOException("bad tier scale");
            }
        }

        long dayStart = policy.get("day_start").getAsLong();
        long dayEnd = policy.get("day_end").getAsLong();
        long floorDay = dayFloor.get("floor_day").getAsLong();
        long d0 = Math.max(dayStart, floorDay);
        long d1 = dayEnd;
        if (d1 < d0) {
            throw new IOException("invalid day window after floor");
        }

        long anchorStart = window.get("start").getAsLong();
        long anchorEnd = window.get("end").getAsLong();
        if (anchorEnd < anchorStart) {
            throw new IOException("bad anchor window");
        }

        boolean aliasGuard = policy.get("alias_guard").getAsBoolean();
        Double signalCutoff = asFiniteDouble(policy.get("signal_cutoff"));
        Double lambdaCap = asFiniteDouble(policy.get("lambda_cap"));
        if (signalCutoff == null || lambdaCap == null || signalCutoff < 0.0 || lambdaCap <= 0.0) {
            throw new IOException("bad policy bounds");
        }

        long overlapLow = Math.max(d0, anchorStart);
        long overlapHigh = Math.min(d1, anchorEnd);
        long overlapDays =
                overlapHigh >= overlapLow ? Math.max(0, overlapHigh - overlapLow + 1) : 0L;
        long k = Math.min(overlapDays, 5L);
        double fAnchor = 1.0 + 0.01 * (double) k;
        String anchorFmt = String.format(Locale.US, "%.12f", fAnchor);
        double anchorFactor = Double.parseDouble(anchorFmt);

        Path hostDir = dataDir.resolve("hosts");
        if (!Files.isDirectory(hostDir)) {
            throw new IOException("missing hosts dir");
        }
        List<Path> hostPaths = new ArrayList<>();
        try (var stream = Files.list(hostDir)) {
            stream.filter(p -> p.getFileName().toString().endsWith(".json")).sorted().forEach(hostPaths::add);
        }

        TreeMap<String, Host> hosts = new TreeMap<>();
        for (Path p : hostPaths) {
            JsonObject rec = readJson(p).getAsJsonObject();
            if (!rec.has("host_id") || !rec.get("host_id").isJsonPrimitive()) {
                throw new IOException("bad host");
            }
            String hid = rec.get("host_id").getAsString();
            if (hid.isEmpty()) {
                throw new IOException("empty host id");
            }
            if (!rec.has("tier") || !rec.get("tier").isJsonPrimitive()) {
                throw new IOException("bad tier");
            }
            String tier = rec.get("tier").getAsString();
            if (!tier.equals("gold") && !tier.equals("silver") && !tier.equals("bronze")) {
                throw new IOException("bad tier enum");
            }
            Double rawL = asFiniteDouble(rec.get("raw_lambda"));
            Double bias = asFiniteDouble(rec.get("bias_signal"));
            if (rawL == null || bias == null) {
                throw new IOException("bad host numbers");
            }
            if (hosts.containsKey(hid)) {
                throw new IOException("dup host");
            }
            Host h = new Host();
            h.tier = tier;
            h.rawLambda = rawL;
            h.biasSignal = bias;
            h.frozen = false;
            hosts.put(hid, h);
        }

        Set<String> expected = new TreeSet<>();
        for (JsonElement e : layout.getAsJsonArray("hosts")) {
            if (!e.isJsonPrimitive() || !e.getAsJsonPrimitive().isString()) {
                throw new IOException("bad layout host list");
            }
            expected.add(e.getAsString());
        }
        if (!expected.equals(hosts.keySet())) {
            throw new IOException("host set mismatch");
        }

        List<JsonObject> incidents = new ArrayList<>();
        for (JsonElement el : incidentsRaw) {
            if (!el.isJsonObject()) {
                throw new IOException("bad incident");
            }
            incidents.add(el.getAsJsonObject());
        }
        incidents.sort(
                Comparator.comparingLong((JsonObject o) -> o.get("seq").getAsLong())
                        .thenComparing(o -> o.get("kind").getAsString())
                        .thenComparing(
                                o ->
                                        o.has("host_id") && o.get("host_id").isJsonPrimitive()
                                                ? o.get("host_id").getAsString()
                                                : "")
                        .thenComparing(RgmaAudit::incidentCanon));

        for (JsonObject inc : incidents) {
            if (!inc.has("seq") || !inc.get("seq").isJsonPrimitive()) {
                throw new IOException("bad seq");
            }
            if (!inc.has("kind") || !inc.get("kind").isJsonPrimitive()) {
                throw new IOException("bad kind");
            }
            String kind = inc.get("kind").getAsString();
            switch (kind) {
                case "bump_lambda" -> {
                    if (!inc.has("host_id") || !inc.get("host_id").isJsonPrimitive()) {
                        throw new IOException("bad bump");
                    }
                    String hid = inc.get("host_id").getAsString();
                    Double d = asFiniteDouble(inc.get("delta"));
                    if (d == null) {
                        throw new IOException("bad delta");
                    }
                    Host h = hosts.get(hid);
                    if (h != null && !h.frozen) {
                        h.rawLambda += d;
                    }
                }
                case "freeze_host" -> {
                    if (!inc.has("host_id") || !inc.get("host_id").isJsonPrimitive()) {
                        throw new IOException("bad freeze");
                    }
                    String hid = inc.get("host_id").getAsString();
                    Host h = hosts.get(hid);
                    if (h != null) {
                        h.frozen = true;
                    }
                }
                case "lift_freeze" -> {
                    if (!inc.has("host_id") || !inc.get("host_id").isJsonPrimitive()) {
                        throw new IOException("bad lift");
                    }
                    String hid = inc.get("host_id").getAsString();
                    Host h = hosts.get(hid);
                    if (h != null) {
                        h.frozen = false;
                    }
                }
                default -> throw new IOException("unknown kind");
            }
        }

        long capMicro = microFromCap(lambdaCap);

        Map<String, Long> micros = new TreeMap<>();
        List<JsonObject> entries = new ArrayList<>();
        long frozenTotal = 0;

        for (Map.Entry<String, Host> e : hosts.entrySet()) {
            String hid = e.getKey();
            Host st = e.getValue();
            if (st.frozen) {
                frozenTotal++;
                micros.put(hid, null);
                JsonObject row = new JsonObject();
                row.addProperty("bias_class", "frozen");
                row.addProperty("host_id", hid);
                row.add("microlambda", JsonNull.INSTANCE);
                row.addProperty("tier", st.tier);
                entries.add(row);
                continue;
            }
            double tierScale = asFiniteDouble(tiers.get(st.tier));
            double s = st.rawLambda * tierScale * anchorFactor;
            long m = microFromScaled(s);
            micros.put(hid, m);
            String bclass;
            if (st.biasSignal > signalCutoff) {
                bclass = "high";
            } else if (st.biasSignal < -signalCutoff) {
                bclass = "low";
            } else {
                bclass = "mid";
            }
            JsonObject row = new JsonObject();
            row.addProperty("bias_class", bclass);
            row.addProperty("host_id", hid);
            row.addProperty("microlambda", m);
            row.addProperty("tier", st.tier);
            entries.add(row);
        }

        long mergedGroups = 0;
        if (aliasGuard) {
            JsonArray groups = meta.getAsJsonArray("alias_groups");
            for (JsonElement g : groups) {
                if (!g.isJsonArray()) {
                    throw new IOException("bad alias group");
                }
                List<String> live = new ArrayList<>();
                for (JsonElement id : g.getAsJsonArray()) {
                    if (!id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString()) {
                        continue;
                    }
                    String h = id.getAsString();
                    Host host = hosts.get(h);
                    if (host != null && !host.frozen) {
                        live.add(h);
                    }
                }
                if (live.size() >= 2) {
                    mergedGroups++;
                }
            }

            Dsu dsu = new Dsu();
            for (String hid : hosts.keySet()) {
                if (!hosts.get(hid).frozen) {
                    dsu.makeSet(hid);
                }
            }
            for (JsonElement g : groups) {
                JsonArray arr = g.getAsJsonArray();
                List<String> live = new ArrayList<>();
                for (JsonElement id : arr) {
                    if (!id.isJsonPrimitive() || !id.getAsJsonPrimitive().isString()) {
                        continue;
                    }
                    String h = id.getAsString();
                    Host host = hosts.get(h);
                    if (host != null && !host.frozen) {
                        live.add(h);
                    }
                }
                if (live.size() < 2) {
                    continue;
                }
                String base = live.get(0);
                for (int i = 1; i < live.size(); i++) {
                    dsu.union(base, live.get(i));
                }
            }

            Map<String, Long> compMax = new HashMap<>();
            for (String hid : hosts.keySet()) {
                Host host = hosts.get(hid);
                if (host.frozen || micros.get(hid) == null) {
                    continue;
                }
                String r = dsu.find(hid);
                long m = micros.get(hid);
                compMax.merge(r, m, Math::max);
            }

            Map<String, Integer> compSz = new HashMap<>();
            for (String hid : hosts.keySet()) {
                if (hosts.get(hid).frozen) {
                    continue;
                }
                String r = dsu.find(hid);
                compSz.merge(r, 1, Integer::sum);
            }

            for (String hid : hosts.keySet()) {
                Host host = hosts.get(hid);
                if (host.frozen || micros.get(hid) == null) {
                    continue;
                }
                String r = dsu.find(hid);
                if (compSz.getOrDefault(r, 0) >= 2) {
                    micros.put(hid, compMax.get(r));
                }
            }

            for (JsonObject row : entries) {
                if (row.get("microlambda") == null || row.get("microlambda").isJsonNull()) {
                    continue;
                }
                String hid = row.get("host_id").getAsString();
                row.addProperty("microlambda", micros.get(hid));
            }
        }

        for (JsonObject row : entries) {
            if (row.get("microlambda") == null || row.get("microlambda").isJsonNull()) {
                continue;
            }
            long m = row.get("microlambda").getAsLong();
            row.addProperty("microlambda", Math.min(m, capMicro));
        }

        entries.sort(Comparator.comparing(o -> o.get("host_id").getAsString()));

        JsonArray entryArr = new JsonArray();
        for (JsonObject row : entries) {
            entryArr.add(row);
        }

        JsonObject report = new JsonObject();
        report.addProperty("anchor_factor", anchorFactor);
        report.add("entries", entryArr);
        report.addProperty("schema_version", 1);

        JsonObject summary = new JsonObject();
        summary.addProperty("anchor_overlap_days", overlapDays);
        summary.addProperty("entries_total", hosts.size());
        summary.addProperty("frozen_total", frozenTotal);
        summary.addProperty("lambda_cap_micro", capMicro);
        summary.addProperty("merged_groups", mergedGroups);
        summary.addProperty("schema_version", 1);

        writeCanonical(auditDir.resolve("ridge_report.json"), report);
        writeCanonical(auditDir.resolve("summary.json"), summary);
    }
}
