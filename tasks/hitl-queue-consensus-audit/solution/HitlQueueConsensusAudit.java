import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Human-in-the-loop queue consensus audit oracle. */
public final class HitlQueueConsensusAudit {

    private static final Gson GSON =
            new GsonBuilder()
                    .disableHtmlEscaping()
                    .serializeNulls()
                    .setPrettyPrinting()
                    .create();

    private HitlQueueConsensusAudit() {}

    public static void main(String[] args) {
        String dataDir = getenv("HCQ_DATA_DIR", "/app/hitl");
        String auditDir = getenv("HCQ_AUDIT_DIR", "/app/audit");
        try {
            run(Path.of(dataDir), Path.of(auditDir));
        } catch (Exception e) {
            e.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private static String getenv(String key, String def) {
        String v = System.getenv(key);
        return (v == null || v.isEmpty()) ? def : v;
    }

    private static void run(Path data, Path out) throws IOException {
        Files.createDirectories(out);

        JsonObject pool = readJson(data.resolve("pool_state.json"));
        JsonObject policy = readJson(data.resolve("policy.json"));
        JsonObject incidentRoot = readJson(data.resolve("incident_log.json"));
        JsonArray incidents =
                incidentRoot.has("incidents") && incidentRoot.get("incidents").isJsonArray()
                        ? incidentRoot.getAsJsonArray("incidents")
                        : new JsonArray();

        TreeMap<String, JsonObject> annotators = new TreeMap<>();
        for (JsonObject row : loadDir(data.resolve("annotators"))) {
            annotators.put(row.get("annotator_id").getAsString(), row);
        }

        TreeMap<String, JsonObject> batches = new TreeMap<>();
        for (JsonObject row : loadDir(data.resolve("batches"))) {
            batches.put(row.get("batch_id").getAsString(), row);
        }

        List<JsonObject> items = loadDir(data.resolve("items"));
        items.sort(Comparator.comparing(o -> o.get("item_id").getAsString()));

        long currentDay = pool.get("current_day").getAsLong();
        String auditVersion = pool.get("audit_version").getAsString();
        String abstain = policy.get("abstain_token").getAsString();
        long minDistinct = policy.get("min_distinct_labelers").getAsLong();
        long minWinnerWeight = policy.get("min_winner_weight").getAsLong();

        TreeMap<String, Long> tierWeight = new TreeMap<>();
        if (policy.has("tier_weight") && policy.get("tier_weight").isJsonObject()) {
            for (Map.Entry<String, JsonElement> e :
                    policy.getAsJsonObject("tier_weight").entrySet()) {
                tierWeight.put(e.getKey(), e.getValue().getAsLong());
            }
        }

        List<JsonObject> activeIncidents = new ArrayList<>();
        for (JsonElement el : incidents) {
            if (el.isJsonObject() && isActive(el.getAsJsonObject(), currentDay)) {
                activeIncidents.add(el.getAsJsonObject());
            }
        }
        int ignoredIncidents = incidents.size() - activeIncidents.size();

        TreeSet<String> frozenBatches = new TreeSet<>();
        for (JsonObject inc : activeIncidents) {
            if ("batch_freeze".equals(str(inc.get("kind")))
                    && currentDay < longVal(inc.get("thaw_day"))) {
                frozenBatches.add(str(inc.get("batch_id")));
            }
        }

        TreeSet<String> goldMismatch = new TreeSet<>();
        for (JsonObject it : items) {
            if (!bool(it.get("is_calibration_gold"))) {
                continue;
            }
            String goldLabel = str(it.get("gold_label"));
            for (JsonElement ve : it.getAsJsonArray("votes")) {
                JsonObject v = ve.getAsJsonObject();
                String lab = str(v.get("label"));
                if (abstain.equals(lab)) {
                    continue;
                }
                if (!goldLabel.equals(lab)) {
                    goldMismatch.add(str(v.get("annotator_id")));
                }
            }
        }

        List<JsonObject> consensusItems = new ArrayList<>();
        for (JsonObject it : items) {
            if (bool(it.get("is_calibration_gold"))) {
                consensusItems.add(resolveGold(it, frozenBatches));
            } else {
                consensusItems.add(
                        resolveOpen(
                                it,
                                frozenBatches,
                                annotators,
                                tierWeight,
                                activeIncidents,
                                goldMismatch,
                                abstain,
                                minDistinct,
                                minWinnerWeight));
            }
        }

        writeJson(out.resolve("consensus_report.json"), wrap("items", toJsonArray(consensusItems)));

        TreeMap<String, Long> byStatus = new TreeMap<>();
        for (JsonObject row : consensusItems) {
            String st = str(row.get("status"));
            byStatus.merge(st, 1L, Long::sum);
        }

        TreeMap<String, JsonObject> itemsById = new TreeMap<>();
        for (JsonObject it : items) {
            itemsById.put(it.get("item_id").getAsString(), it);
        }

        List<JsonObject> eligible = new ArrayList<>();
        for (JsonObject row : consensusItems) {
            String st = str(row.get("status"));
            if ("blocked_freeze".equals(st) || "insufficient_quorum".equals(st)) {
                continue;
            }
            String itemId = str(row.get("item_id"));
            JsonObject it = itemsById.get(itemId);
            String bid = str(it.get("batch_id"));
            long btier = batches.get(bid).get("business_tier").getAsLong();
            long eligibleDay = Long.MAX_VALUE;
            for (JsonElement ve : it.getAsJsonArray("votes")) {
                long d = ve.getAsJsonObject().get("day").getAsLong();
                eligibleDay = Math.min(eligibleDay, d);
            }
            if (eligibleDay == Long.MAX_VALUE) {
                eligibleDay = 0;
            }
            JsonObject e = new JsonObject();
            e.addProperty("batch_id", bid);
            e.addProperty("business_tier", btier);
            e.addProperty("eligible_day", eligibleDay);
            e.addProperty("item_id", itemId);
            eligible.add(e);
        }

        eligible.sort(
                Comparator.comparingLong((JsonObject o) -> o.get("eligible_day").getAsLong())
                        .thenComparingLong(o -> o.get("business_tier").getAsLong())
                        .thenComparing(o -> o.get("batch_id").getAsString())
                        .thenComparing(o -> o.get("item_id").getAsString()));

        List<JsonObject> backlog = new ArrayList<>();
        for (int i = 0; i < eligible.size(); i++) {
            JsonObject e = eligible.get(i);
            JsonObject row = new JsonObject();
            row.add("batch_id", e.get("batch_id"));
            row.add("business_tier", e.get("business_tier"));
            row.add("eligible_day", e.get("eligible_day"));
            row.add("item_id", e.get("item_id"));
            row.addProperty("rank", i + 1L);
            backlog.add(row);
        }
        writeJson(out.resolve("queue_order.json"), wrap("backlog", toJsonArray(backlog)));

        List<JsonObject> reliability = new ArrayList<>();
        for (Map.Entry<String, JsonObject> ent : annotators.entrySet()) {
            String aid = ent.getKey();
            JsonObject ann = ent.getValue();
            long gd = 0;
            for (JsonObject it : items) {
                if (!bool(it.get("is_calibration_gold"))) {
                    continue;
                }
                String gl = str(it.get("gold_label"));
                for (JsonElement ve : it.getAsJsonArray("votes")) {
                    JsonObject v = ve.getAsJsonObject();
                    if (!aid.equals(str(v.get("annotator_id")))) {
                        continue;
                    }
                    String lab = str(v.get("label"));
                    if (abstain.equals(lab)) {
                        continue;
                    }
                    if (!gl.equals(lab)) {
                        gd++;
                    }
                }
            }
            JsonObject row = new JsonObject();
            row.add("active_scalers", toJsonArray(activeScalersForAnnotator(activeIncidents, aid, currentDay)));
            row.addProperty("annotator_id", aid);
            row.addProperty("gold_disagreements", gd);
            row.addProperty("tier", str(ann.get("tier")));
            row.addProperty("weight_halved", goldMismatch.contains(aid));
            reliability.add(row);
        }
        writeJson(
                out.resolve("annotator_reliability.json"), wrap("annotators", toJsonArray(reliability)));

        List<JsonObject> flags = new ArrayList<>();
        for (JsonObject row : consensusItems) {
            String st = str(row.get("status"));
            String itemId = str(row.get("item_id"));
            if ("blocked_freeze".equals(st)) {
                String bid = str(row.get("batch_id"));
                JsonObject f = new JsonObject();
                f.addProperty("code", "freeze_active");
                f.addProperty("detail", "batch=" + bid);
                f.addProperty("item_id", itemId);
                flags.add(f);
            } else if ("insufficient_quorum".equals(st)) {
                long req = row.get("required_distinct").getAsLong();
                JsonObject f = new JsonObject();
                f.addProperty("code", "quorum_shortfall");
                f.addProperty("detail", "need>=" + req);
                f.addProperty("item_id", itemId);
                flags.add(f);
            }
        }
        flags.sort(
                Comparator.comparing((JsonObject o) -> str(o.get("code")))
                        .thenComparing(o -> str(o.get("item_id"))));
        writeJson(out.resolve("compliance_flags.json"), wrap("flags", toJsonArray(flags)));

        long openItems =
                items.stream().filter(it -> !bool(it.get("is_calibration_gold"))).count();
        long goldItems =
                items.stream().filter(it -> bool(it.get("is_calibration_gold"))).count();

        JsonArray blockedArr = new JsonArray();
        for (String b : frozenBatches) {
            blockedArr.add(b);
        }

        JsonObject totals = new JsonObject();
        totals.addProperty("active_incidents", (long) activeIncidents.size());
        totals.addProperty("gold_items", goldItems);
        totals.addProperty("items_total", (long) items.size());
        totals.addProperty("open_items", openItems);

        JsonObject byStatusJson = new JsonObject();
        for (Map.Entry<String, Long> e : byStatus.entrySet()) {
            byStatusJson.addProperty(e.getKey(), e.getValue());
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("audit_version", auditVersion);
        summary.add("blocked_batches", blockedArr);
        summary.add("by_status", byStatusJson);
        summary.addProperty("current_day", currentDay);
        summary.addProperty("ignored_incidents", ignoredIncidents);
        summary.add("totals", totals);
        writeJson(out.resolve("summary.json"), summary);
    }

    private static boolean kindSupported(String k) {
        return "weight_scaler".equals(k) || "quorum_bump".equals(k) || "batch_freeze".equals(k);
    }

    private static boolean isActive(JsonObject inc, long currentDay) {
        if (!bool(inc.get("accepted"))) {
            return false;
        }
        if (longVal(inc.get("day")) > currentDay) {
            return false;
        }
        return kindSupported(str(inc.get("kind")));
    }

    private static long extraQuorum(List<JsonObject> active, String batchId) {
        long extra = 0;
        for (JsonObject inc : active) {
            if (!"quorum_bump".equals(str(inc.get("kind")))) {
                continue;
            }
            JsonArray bids = inc.getAsJsonArray("batch_ids");
            if (bids == null) {
                continue;
            }
            boolean hit = false;
            for (JsonElement b : bids) {
                if (batchId.equals(b.getAsString())) {
                    hit = true;
                    break;
                }
            }
            if (hit) {
                extra += longVal(inc.get("extra_distinct"));
            }
        }
        return extra;
    }

    private static List<JsonObject> composeScalersForVote(
            List<JsonObject> active, String aid, long voteDay) {
        List<JsonObject> applied = new ArrayList<>();
        for (JsonObject inc : active) {
            if (!"weight_scaler".equals(str(inc.get("kind")))) {
                continue;
            }
            if (!aid.equals(str(inc.get("annotator_id")))) {
                continue;
            }
            if (voteDay < longVal(inc.get("effective_day"))) {
                continue;
            }
            applied.add(inc);
        }
        applied.sort(
                Comparator.comparingLong((JsonObject o) -> longVal(o.get("day")))
                        .thenComparing(o -> str(o.get("event_id"))));
        return applied;
    }

    private static List<JsonObject> activeScalersForAnnotator(
            List<JsonObject> active, String aid, long currentDay) {
        List<JsonObject> scalers = new ArrayList<>();
        for (JsonObject inc : active) {
            if (!"weight_scaler".equals(str(inc.get("kind")))) {
                continue;
            }
            if (!aid.equals(str(inc.get("annotator_id")))) {
                continue;
            }
            if (longVal(inc.get("effective_day")) > currentDay) {
                continue;
            }
            scalers.add(inc);
        }
        scalers.sort(
                Comparator.comparingLong((JsonObject o) -> longVal(o.get("day")))
                        .thenComparing(o -> str(o.get("event_id"))));
        List<JsonObject> out = new ArrayList<>();
        for (JsonObject x : scalers) {
            JsonObject row = new JsonObject();
            row.addProperty("event_id", str(x.get("event_id")));
            row.addProperty("pct_den", longVal(x.get("pct_den")));
            row.addProperty("pct_num", longVal(x.get("pct_num")));
            out.add(row);
        }
        return out;
    }

    private static long voteWeight(
            TreeMap<String, JsonObject> annotators,
            TreeMap<String, Long> tierWeight,
            List<JsonObject> active,
            Set<String> goldMismatch,
            String aid,
            long voteDay) {
        JsonObject ann = annotators.get(aid);
        String tier = str(ann.get("tier"));
        long w = tierWeight.get(tier);
        for (JsonObject inc : composeScalersForVote(active, aid, voteDay)) {
            long num = longVal(inc.get("pct_num"));
            long den = longVal(inc.get("pct_den"));
            w = w * num / den;
        }
        if (goldMismatch.contains(aid)) {
            w /= 2;
        }
        if (w == 0) {
            w = 1;
        }
        return w;
    }

    private static JsonObject resolveOpen(
            JsonObject it,
            Set<String> frozenBatches,
            TreeMap<String, JsonObject> annotators,
            TreeMap<String, Long> tierWeight,
            List<JsonObject> active,
            Set<String> goldMismatch,
            String abstain,
            long minDistinct,
            long minWinnerWeight) {
        String bid = str(it.get("batch_id"));
        String itemId = str(it.get("item_id"));
        if (frozenBatches.contains(bid)) {
            return frozenRow(itemId, bid);
        }

        long required = minDistinct + extraQuorum(active, bid);
        JsonArray votes = it.getAsJsonArray("votes");
        List<JsonObject> nonAbs = new ArrayList<>();
        for (JsonElement ve : votes) {
            JsonObject v = ve.getAsJsonObject();
            if (!abstain.equals(str(v.get("label")))) {
                nonAbs.add(v);
            }
        }

        TreeSet<String> distinct = new TreeSet<>();
        for (JsonObject v : nonAbs) {
            distinct.add(str(v.get("annotator_id")));
        }

        if (distinct.size() < required) {
            JsonObject row = new JsonObject();
            row.addProperty("batch_id", bid);
            row.addProperty("distinct_voters", (long) distinct.size());
            row.add("final_label", JsonNull.INSTANCE);
            row.addProperty("item_id", itemId);
            row.addProperty("required_distinct", required);
            row.add("runner_up_label", JsonNull.INSTANCE);
            row.addProperty("status", "insufficient_quorum");
            row.addProperty("winner_weight", 0L);
            return row;
        }

        TreeMap<String, Long> sums = new TreeMap<>();
        for (JsonObject v : nonAbs) {
            String lab = str(v.get("label"));
            String aid = str(v.get("annotator_id"));
            long voteDay = v.get("day").getAsLong();
            long w = voteWeight(annotators, tierWeight, active, goldMismatch, aid, voteDay);
            sums.merge(lab, w, Long::sum);
        }

        long maxSum = sums.values().stream().mapToLong(Long::longValue).max().orElse(0);
        List<String> winners = new ArrayList<>();
        for (Map.Entry<String, Long> e : sums.entrySet()) {
            if (e.getValue() == maxSum) {
                winners.add(e.getKey());
            }
        }
        winners.sort(String::compareTo);
        String winner = winners.get(0);
        long winnerSum = sums.get(winner);

        TreeSet<Long> uniqVals = new TreeSet<>((a, b) -> Long.compare(b, a));
        uniqVals.addAll(sums.values());
        List<Long> uniq = new ArrayList<>(uniqVals);

        JsonElement runner;
        if (uniq.size() < 2) {
            runner = JsonNull.INSTANCE;
        } else {
            long second = uniq.get(1);
            List<String> labs = new ArrayList<>();
            for (Map.Entry<String, Long> e : sums.entrySet()) {
                if (e.getValue() == second) {
                    labs.add(e.getKey());
                }
            }
            labs.sort(String::compareTo);
            runner = new com.google.gson.JsonPrimitive(labs.get(0));
        }

        String status = winnerSum < minWinnerWeight ? "low_confidence" : "resolved";

        JsonObject row = new JsonObject();
        row.addProperty("batch_id", bid);
        row.addProperty("distinct_voters", (long) distinct.size());
        row.addProperty("final_label", winner);
        row.addProperty("item_id", itemId);
        row.addProperty("required_distinct", required);
        row.add("runner_up_label", runner);
        row.addProperty("status", status);
        row.addProperty("winner_weight", winnerSum);
        return row;
    }

    private static JsonObject resolveGold(JsonObject it, Set<String> frozenBatches) {
        String bid = str(it.get("batch_id"));
        String itemId = str(it.get("item_id"));
        if (frozenBatches.contains(bid)) {
            return frozenRow(itemId, bid);
        }
        TreeSet<String> distinctAll = new TreeSet<>();
        for (JsonElement ve : it.getAsJsonArray("votes")) {
            distinctAll.add(str(ve.getAsJsonObject().get("annotator_id")));
        }
        JsonObject row = new JsonObject();
        row.addProperty("batch_id", bid);
        row.addProperty("distinct_voters", (long) distinctAll.size());
        row.addProperty("final_label", str(it.get("gold_label")));
        row.addProperty("item_id", itemId);
        row.addProperty("required_distinct", 0L);
        row.add("runner_up_label", JsonNull.INSTANCE);
        row.addProperty("status", "gold_locked");
        row.addProperty("winner_weight", 0L);
        return row;
    }

    private static JsonObject frozenRow(String itemId, String bid) {
        JsonObject row = new JsonObject();
        row.addProperty("batch_id", bid);
        row.addProperty("distinct_voters", 0L);
        row.add("final_label", JsonNull.INSTANCE);
        row.addProperty("item_id", itemId);
        row.addProperty("required_distinct", 0L);
        row.add("runner_up_label", JsonNull.INSTANCE);
        row.addProperty("status", "blocked_freeze");
        row.addProperty("winner_weight", 0L);
        return row;
    }

    private static JsonObject wrap(String key, JsonArray arr) {
        JsonObject root = new JsonObject();
        root.add(key, arr);
        return root;
    }

    private static JsonArray toJsonArray(List<JsonObject> rows) {
        JsonArray arr = new JsonArray();
        for (JsonObject row : rows) {
            arr.add(row);
        }
        return arr;
    }

    private static List<JsonObject> loadDir(Path dir) throws IOException {
        List<Path> paths = new ArrayList<>();
        if (!Files.isDirectory(dir)) {
            return List.of();
        }
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "*.json")) {
            for (Path p : stream) {
                paths.add(p);
            }
        }
        paths.sort(Comparator.comparing(Path::toString));
        List<JsonObject> rows = new ArrayList<>();
        for (Path p : paths) {
            rows.add(readJson(p));
        }
        return rows;
    }

    private static JsonObject readJson(Path path) throws IOException {
        String text = Files.readString(path, StandardCharsets.UTF_8);
        return JsonParser.parseString(text).getAsJsonObject();
    }

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

    private static void writeJson(Path path, JsonObject root) throws IOException {
        JsonObject sorted = sortKeysRecursive(root);
        String text = GSON.toJson(sorted) + "\n";
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static boolean bool(JsonElement v) {
        return v != null && v.isJsonPrimitive() && v.getAsJsonPrimitive().isBoolean() && v.getAsBoolean();
    }

    private static String str(JsonElement v) {
        return v.getAsString();
    }

    private static long longVal(JsonElement v) {
        if (v == null || v.isJsonNull()) {
            return 0;
        }
        return v.getAsLong();
    }
}
