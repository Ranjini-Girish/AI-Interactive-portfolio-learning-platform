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

public final class Shaper {
    private static final Map<String, Integer> SEV_RANK = Map.of("error", 3, "warn", 2, "note", 1);

    private final Map<String, Bucket> buckets = new TreeMap<>();
    private final Map<String, Object> policy;
    private int nowTicks;
    private final List<JsonObject> admits = new ArrayList<>();
    private final List<JsonObject> diagnostics = new ArrayList<>();
    private long droppedBytesTotal;
    private long overflowDropsTotal;

    private Shaper(Map<String, Bucket> buckets, Map<String, Object> policy) {
        this.buckets.putAll(buckets);
        this.policy = policy;
    }

    private static final class Bucket {
        long capacityBytes;
        long leakBytesPerTick;
        long currentBytes;
    }

    private void diag(long seq, String code, String severity, String bucketId, String detail) {
        JsonObject row = new JsonObject();
        row.addProperty("seq", seq);
        row.addProperty("code", code);
        row.addProperty("severity", severity);
        row.addProperty("bucket_id", bucketId);
        row.addProperty("detail", detail);
        diagnostics.add(row);
    }

    private void step(JsonObject ev) {
        long seq = ev.get("seq").getAsLong();
        String type = ev.get("type").getAsString();
        if ("submit".equals(type)) {
            String bid = ev.get("bucket_id").getAsString();
            long sz = ev.get("size_bytes").getAsLong();
            if (!buckets.containsKey(bid)) {
                diag(seq, "E_UNKNOWN_BUCKET", "error", bid, "");
                return;
            }
            Bucket b = buckets.get(bid);
            if (b.currentBytes + sz <= b.capacityBytes) {
                b.currentBytes += sz;
                JsonObject admit = new JsonObject();
                admit.addProperty("bucket_id", bid);
                admit.addProperty("level_after", b.currentBytes);
                admit.addProperty("seq", seq);
                admit.addProperty("size_bytes", sz);
                admits.add(admit);
                diag(seq, "N_ADMITTED", "note", bid, Long.toString(sz));
            } else {
                diag(seq, "W_DROPPED_OVERFLOW", "warn", bid, Long.toString(sz));
                overflowDropsTotal += 1;
                if (Boolean.TRUE.equals(policy.get("count_dropped_bytes"))) {
                    droppedBytesTotal += sz;
                }
            }
            return;
        }
        if ("tick".equals(type)) {
            nowTicks += 1;
            for (Bucket b : buckets.values()) {
                b.currentBytes = Math.max(0, b.currentBytes - b.leakBytesPerTick);
            }
            return;
        }
        if ("reconfigure".equals(type)) {
            String bid = ev.get("bucket_id").getAsString();
            if (!buckets.containsKey(bid)) {
                throw new IllegalArgumentException("unknown bucket in reconfigure: " + bid);
            }
            long nc = ev.get("new_capacity_bytes").getAsLong();
            long nl = ev.get("new_leak_bytes_per_tick").getAsLong();
            Bucket b = buckets.get(bid);
            long oldCap = b.capacityBytes;
            long oldLeak = b.leakBytesPerTick;
            if (nc == oldCap && nl == oldLeak) {
                diag(seq, "W_RECONFIG_NOOP", "warn", bid, bid);
                return;
            }
            long oldLevel = b.currentBytes;
            b.capacityBytes = nc;
            b.leakBytesPerTick = nl;
            if (nc < oldLevel) {
                b.currentBytes = nc;
                diag(seq, "W_CAPACITY_REDUCED", "warn", bid, oldLevel + "->" + nc);
            }
        }
    }

    private Map<String, Object> finalizeOut(int nEvents) {
        List<Map<String, Object>> bs = new ArrayList<>();
        for (Map.Entry<String, Bucket> e : buckets.entrySet()) {
            Map<String, Object> row = new HashMap<>();
            row.put("bucket_id", e.getKey());
            row.put("capacity_bytes", e.getValue().capacityBytes);
            row.put("current_bytes", e.getValue().currentBytes);
            row.put("leak_bytes_per_tick", e.getValue().leakBytesPerTick);
            bs.add(row);
        }
        bs.sort(Comparator.comparing(r -> (String) r.get("bucket_id")));

        List<JsonObject> ad;
        if (Boolean.TRUE.equals(policy.get("track_admits"))) {
            ad = new ArrayList<>(admits);
            ad.sort(
                    Comparator.comparingLong((JsonObject o) -> o.get("seq").getAsLong())
                            .thenComparing(o -> o.get("bucket_id").getAsString()));
        } else {
            ad = List.of();
        }

        diagnostics.sort(
                Comparator.comparingLong((JsonObject d) -> d.get("seq").getAsLong())
                        .thenComparing(
                                (JsonObject d) ->
                                        -SEV_RANK.getOrDefault(d.get("severity").getAsString(), 0))
                        .thenComparing(d -> d.get("code").getAsString())
                        .thenComparing(d -> d.get("bucket_id").getAsString())
                        .thenComparing(d -> d.get("detail").getAsString()));

        long curTotal = buckets.values().stream().mapToLong(b -> b.currentBytes).sum();
        Map<String, Object> summary = new HashMap<>();
        summary.put("admits_total", admits.size());
        summary.put("buckets_total", buckets.size());
        summary.put("current_bytes_total", curTotal);
        summary.put("dropped_bytes_total", droppedBytesTotal);
        summary.put("events_total", nEvents);
        summary.put("max_seq", nEvents > 0 ? nEvents - 1 : null);
        summary.put("now_ticks_final", nowTicks);
        summary.put("overflow_drops_total", overflowDropsTotal);

        Map<String, Object> out = new HashMap<>();
        out.put("bucket_state", Map.of("buckets", bs));
        out.put("admits", Map.of("admits", ad));
        out.put("shaper_diagnostics", Map.of("diagnostics", diagnostics));
        out.put("summary", summary);
        return out;
    }

    private static JsonObject readObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static void writeCanonical(Path path, Object value) throws IOException {
        Gson pretty =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        String body = pretty.toJson(value);
        Files.writeString(path, body + "\n", StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Shaper <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject bucketsIn = readObject(inDir.resolve("buckets.json"));
        JsonObject eventsRoot = readObject(inDir.resolve("events.json"));
        JsonObject policyIn = readObject(inDir.resolve("policy.json"));

        Map<String, Bucket> state = new TreeMap<>();
        for (JsonElement el : bucketsIn.getAsJsonArray("buckets")) {
            JsonObject b = el.getAsJsonObject();
            Bucket bucket = new Bucket();
            bucket.capacityBytes = b.get("capacity_bytes").getAsLong();
            bucket.leakBytesPerTick = b.get("leak_bytes_per_tick").getAsLong();
            bucket.currentBytes = 0;
            state.put(b.get("bucket_id").getAsString(), bucket);
        }

        @SuppressWarnings("unchecked")
        Map<String, Object> policy = new Gson().fromJson(policyIn, Map.class);

        Shaper sim = new Shaper(state, policy);
        JsonArray events = eventsRoot.getAsJsonArray("events");
        for (JsonElement el : events) {
            sim.step(el.getAsJsonObject());
        }
        Map<String, Object> outputs = sim.finalizeOut(events.size());

        writeCanonical(outDir.resolve("bucket_state.json"), outputs.get("bucket_state"));
        writeCanonical(outDir.resolve("admits.json"), outputs.get("admits"));
        writeCanonical(
                outDir.resolve("shaper_diagnostics.json"), outputs.get("shaper_diagnostics"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
