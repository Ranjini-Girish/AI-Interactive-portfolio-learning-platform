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

public final class Replay {
    private static final Gson GSON =
            new GsonBuilder()
                    .disableHtmlEscaping()
                    .serializeNulls()
                    .setPrettyPrinting()
                    .create();

    private static final Map<String, String[]> KIND_REQUIRED = new TreeMap<>();

    static {
        KIND_REQUIRED.put("key_install", new String[] {"key_id", "algorithm", "max_uses"});
        KIND_REQUIRED.put("encrypt", new String[] {"key_id", "nonce"});
        KIND_REQUIRED.put("key_retire", new String[] {"key_id"});
        KIND_REQUIRED.put("key_compromise", new String[] {"key_id", "reason"});
        KIND_REQUIRED.put("tick", new String[] {});
    }

    private Replay() {}

    private static final class KeyState {
        String keyId;
        String algorithm;
        String state;
        int maxUses;
        int usesCount;
        int installedSeq;
        Integer retiredSeq;
        Integer exhaustedSeq;
        Integer compromisedSeq;
        int lastUseTick;
        boolean nearWarned;
        final Map<String, long[]> nonces = new HashMap<>();
    }

    private static Object jsonScalar(JsonElement el) {
        if (el == null || el.isJsonNull()) {
            return null;
        }
        if (!el.isJsonPrimitive()) {
            return el.getAsString();
        }
        var p = el.getAsJsonPrimitive();
        if (p.isBoolean()) {
            return p.getAsBoolean();
        }
        if (p.isString()) {
            return p.getAsString();
        }
        if (p.isNumber()) {
            long lv = p.getAsLong();
            if (lv >= Integer.MIN_VALUE && lv <= Integer.MAX_VALUE) {
                return (int) lv;
            }
            return lv;
        }
        return null;
    }

    private static String nonceKey(Object nonce) {
        return nonce instanceof Number ? "n:" + nonce : "s:" + String.valueOf(nonce);
    }

    private static JsonObject readObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
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

    private static void writeCanonical(Path path, Object value) throws IOException {
        JsonElement el = JsonParser.parseString(GSON.toJson(value));
        JsonElement sorted =
                el.isJsonObject() ? sortKeysRecursive(el.getAsJsonObject()) : el;
        Files.writeString(path, GSON.toJson(sorted) + "\n", StandardCharsets.UTF_8);
    }

    private static int severityRank(JsonObject policy, String severity) {
        return policy.getAsJsonObject("severity_ranks").get(severity).getAsInt();
    }

    private static void emit(
            List<Map<String, Object>> diags,
            int seq,
            String code,
            String severity,
            int severityRank,
            String keyId,
            Map<String, Object> evidence) {
        Map<String, Object> rec = new TreeMap<>();
        rec.put("seq", seq);
        rec.put("code", code);
        rec.put("severity", severity);
        rec.put("severity_rank", severityRank);
        rec.put("key_id", keyId);
        rec.put("evidence", new TreeMap<>(evidence));
        diags.add(rec);
    }

    private static void pushAudit(
            List<Map<String, Object>> audit,
            int seq,
            int tick,
            String keyId,
            String kind,
            Map<String, Object> evidence) {
        Map<String, Object> row = new TreeMap<>();
        row.put("seq", seq);
        row.put("tick", tick);
        row.put("key_id", keyId);
        row.put("kind", kind);
        row.put("evidence", new TreeMap<>(evidence));
        audit.add(row);
    }

    private static void idleRetireSweep(
            int now,
            int seq,
            Map<String, KeyState> keys,
            JsonObject policy,
            List<Map<String, Object>> diags,
            List<Map<String, Object>> audit) {
        int threshold = policy.get("idle_retire_ticks").getAsInt();
        List<String> ids = new ArrayList<>(keys.keySet());
        ids.sort(String::compareTo);
        for (String keyId : ids) {
            KeyState k = keys.get(keyId);
            if (!"ACTIVE".equals(k.state)) {
                continue;
            }
            if (now - k.lastUseTick >= threshold) {
                k.state = "RETIRED";
                k.retiredSeq = seq;
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("last_use_tick", k.lastUseTick);
                evidence.put("now", now);
                emit(
                        diags,
                        seq,
                        "N_KEY_IDLE_RETIRED",
                        "notice",
                        severityRank(policy, "notice"),
                        keyId,
                        evidence);
                pushAudit(audit, seq, now, keyId, "idle_retired", evidence);
            }
        }
    }

    private static Map<String, Object> simulate(
            JsonObject keysIn, JsonObject eventsIn, JsonObject policy) {
        Map<String, KeyState> keys = new TreeMap<>();
        List<Map<String, Object>> audit = new ArrayList<>();
        List<Map<String, Object>> diags = new ArrayList<>();
        List<Map<String, Object>> encryptions = new ArrayList<>();

        Set<String> allowed = new HashSet<>();
        for (JsonElement el : policy.getAsJsonArray("allowed_algorithms")) {
            allowed.add(el.getAsString());
        }
        JsonArray nearRatio = policy.getAsJsonArray("near_exhaustion_ratio");
        long nearNum = nearRatio.get(0).getAsLong();
        long nearDen = nearRatio.get(1).getAsLong();

        if (keysIn.has("keys")) {
            for (JsonElement el : keysIn.getAsJsonArray("keys")) {
                JsonObject k = el.getAsJsonObject();
                String keyId = k.get("key_id").getAsString();
                String algorithm = k.get("algorithm").getAsString();
                int maxUses = k.get("max_uses").getAsInt();
                KeyState st = new KeyState();
                st.keyId = keyId;
                st.algorithm = algorithm;
                st.state = "ACTIVE";
                st.maxUses = maxUses;
                st.installedSeq = 0;
                st.lastUseTick = 0;
                keys.put(keyId, st);
                Map<String, Object> ev = new TreeMap<>();
                ev.put("algorithm", algorithm);
                ev.put("max_uses", maxUses);
                pushAudit(audit, 0, 0, keyId, "installed", ev);
            }
        }

        List<JsonObject> events = new ArrayList<>();
        if (eventsIn.has("events")) {
            for (JsonElement el : eventsIn.getAsJsonArray("events")) {
                events.add(el.getAsJsonObject());
            }
        }
        events.sort(Comparator.comparingInt(e -> e.get("seq").getAsInt()));

        for (JsonObject ev : events) {
            int seq = ev.get("seq").getAsInt();
            int tick = ev.get("tick").getAsInt();
            String kind = ev.has("kind") ? ev.get("kind").getAsString() : "";

            idleRetireSweep(tick, seq, keys, policy, diags, audit);

            if (!KIND_REQUIRED.containsKey(kind)) {
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("reason", "unknown_kind");
                emit(
                        diags,
                        seq,
                        "E_INVALID_EVENT",
                        "error",
                        severityRank(policy, "error"),
                        null,
                        evidence);
                continue;
            }
            boolean missingField = false;
            for (String f : KIND_REQUIRED.get(kind)) {
                if (!ev.has(f)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "missing_field");
                    emit(
                            diags,
                            seq,
                            "E_INVALID_EVENT",
                            "error",
                            severityRank(policy, "error"),
                            null,
                            evidence);
                    missingField = true;
                    break;
                }
            }
            if (missingField) {
                continue;
            }

            if ("key_install".equals(kind)) {
                String keyId = ev.get("key_id").getAsString();
                String algorithm = ev.get("algorithm").getAsString();
                int maxUses = ev.get("max_uses").getAsInt();
                if (keys.containsKey(keyId)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("prior_state", keys.get(keyId).state);
                    emit(
                            diags,
                            seq,
                            "E_DUPLICATE_KEY",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            evidence);
                    continue;
                }
                if (!allowed.contains(algorithm)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("algorithm", algorithm);
                    emit(
                            diags,
                            seq,
                            "E_ALGORITHM_UNKNOWN",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            evidence);
                    continue;
                }
                if (maxUses <= 0) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "non_positive_max_uses");
                    emit(
                            diags,
                            seq,
                            "E_INVALID_EVENT",
                            "error",
                            severityRank(policy, "error"),
                            null,
                            evidence);
                    continue;
                }
                KeyState st = new KeyState();
                st.keyId = keyId;
                st.algorithm = algorithm;
                st.state = "ACTIVE";
                st.maxUses = maxUses;
                st.installedSeq = seq;
                st.lastUseTick = tick;
                keys.put(keyId, st);
                Map<String, Object> evd = new TreeMap<>();
                evd.put("algorithm", algorithm);
                evd.put("max_uses", maxUses);
                emit(
                        diags,
                        seq,
                        "N_KEY_INSTALLED",
                        "notice",
                        severityRank(policy, "notice"),
                        keyId,
                        evd);
                pushAudit(audit, seq, tick, keyId, "installed", evd);
            } else if ("encrypt".equals(kind)) {
                String keyId = ev.get("key_id").getAsString();
                Object nonce = jsonScalar(ev.get("nonce"));
                if (!keys.containsKey(keyId)) {
                    Map<String, Object> enc = new TreeMap<>();
                    enc.put("seq", seq);
                    enc.put("tick", tick);
                    enc.put("key_id", keyId);
                    enc.put("nonce", nonce);
                    enc.put("outcome", "rejected");
                    enc.put("reason", "UNKNOWN_KEY");
                    encryptions.add(enc);
                    emit(
                            diags,
                            seq,
                            "E_KEY_UNKNOWN",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                KeyState k = keys.get(keyId);
                if ("RETIRED".equals(k.state)) {
                    Map<String, Object> enc = encRow(seq, tick, keyId, nonce, "rejected", "RETIRED");
                    encryptions.add(enc);
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("key_state", "RETIRED");
                    emit(
                            diags,
                            seq,
                            "E_KEY_NOT_ACTIVE",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            evidence);
                    continue;
                }
                if ("EXHAUSTED".equals(k.state)) {
                    encryptions.add(encRow(seq, tick, keyId, nonce, "rejected", "EXHAUSTED"));
                    emit(
                            diags,
                            seq,
                            "E_KEY_EXHAUSTED",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                if ("COMPROMISED".equals(k.state)) {
                    encryptions.add(encRow(seq, tick, keyId, nonce, "rejected", "COMPROMISED"));
                    emit(
                            diags,
                            seq,
                            "E_KEY_COMPROMISED",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                if (k.nonces.containsKey(nonceKey(nonce))) {
                    long[] first = k.nonces.get(nonceKey(nonce));
                    encryptions.add(encRow(seq, tick, keyId, nonce, "rejected", "NONCE_REUSE"));
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("first_seq", (int) first[0]);
                    evidence.put("first_tick", (int) first[1]);
                    emit(
                            diags,
                            seq,
                            "E_NONCE_REUSE",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            evidence);
                    k.state = "COMPROMISED";
                    k.compromisedSeq = seq;
                    Map<String, Object> compEv = new TreeMap<>();
                    compEv.put("trigger", "nonce_reuse");
                    compEv.put("nonce", nonce);
                    emit(
                            diags,
                            seq,
                            "N_KEY_COMPROMISED",
                            "notice",
                            severityRank(policy, "notice"),
                            keyId,
                            compEv);
                    pushAudit(audit, seq, tick, keyId, "compromised", compEv);
                    continue;
                }
                k.nonces.put(nonceKey(nonce), new long[] {seq, tick});
                k.usesCount += 1;
                k.lastUseTick = tick;
                Map<String, Object> enc = encRow(seq, tick, keyId, nonce, "accepted", null);
                encryptions.add(enc);
                if (k.usesCount == k.maxUses) {
                    k.state = "EXHAUSTED";
                    k.exhaustedSeq = seq;
                    Map<String, Object> exEv = new TreeMap<>();
                    exEv.put("uses_count", k.usesCount);
                    exEv.put("max_uses", k.maxUses);
                    emit(
                            diags,
                            seq,
                            "N_KEY_EXHAUSTED",
                            "notice",
                            severityRank(policy, "notice"),
                            keyId,
                            exEv);
                    pushAudit(audit, seq, tick, keyId, "exhausted", exEv);
                } else if (k.usesCount * nearDen >= k.maxUses * nearNum && !k.nearWarned) {
                    k.nearWarned = true;
                    Map<String, Object> wEv = new TreeMap<>();
                    wEv.put("uses_count", k.usesCount);
                    wEv.put("max_uses", k.maxUses);
                    emit(
                            diags,
                            seq,
                            "W_KEY_NEAR_EXHAUSTION",
                            "warning",
                            severityRank(policy, "warning"),
                            keyId,
                            wEv);
                }
            } else if ("key_retire".equals(kind)) {
                String keyId = ev.get("key_id").getAsString();
                if (!keys.containsKey(keyId)) {
                    emit(
                            diags,
                            seq,
                            "E_RETIRE_UNKNOWN",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                KeyState k = keys.get(keyId);
                if ("RETIRED".equals(k.state)) {
                    emit(
                            diags,
                            seq,
                            "W_RETIRE_ALREADY_RETIRED",
                            "warning",
                            severityRank(policy, "warning"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                if ("EXHAUSTED".equals(k.state) || "COMPROMISED".equals(k.state)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("key_state", k.state);
                    emit(
                            diags,
                            seq,
                            "E_RETIRE_NOT_ACTIVE",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            evidence);
                    continue;
                }
                k.state = "RETIRED";
                k.retiredSeq = seq;
                Map<String, Object> retEv = new TreeMap<>();
                retEv.put("trigger", "key_retire");
                emit(
                        diags,
                        seq,
                        "N_KEY_RETIRED",
                        "notice",
                        severityRank(policy, "notice"),
                        keyId,
                        retEv);
                pushAudit(audit, seq, tick, keyId, "retired", retEv);
            } else if ("key_compromise".equals(kind)) {
                String keyId = ev.get("key_id").getAsString();
                String reason = ev.get("reason").getAsString();
                if (!keys.containsKey(keyId)) {
                    emit(
                            diags,
                            seq,
                            "E_COMPROMISE_UNKNOWN",
                            "error",
                            severityRank(policy, "error"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                KeyState k = keys.get(keyId);
                if ("COMPROMISED".equals(k.state)) {
                    emit(
                            diags,
                            seq,
                            "W_COMPROMISE_REDUNDANT",
                            "warning",
                            severityRank(policy, "warning"),
                            keyId,
                            new TreeMap<>());
                    continue;
                }
                k.state = "COMPROMISED";
                k.compromisedSeq = seq;
                Map<String, Object> compEv = new TreeMap<>();
                compEv.put("trigger", "key_compromise");
                compEv.put("reason", reason);
                emit(
                        diags,
                        seq,
                        "N_KEY_COMPROMISED",
                        "notice",
                        severityRank(policy, "notice"),
                        keyId,
                        compEv);
                pushAudit(audit, seq, tick, keyId, "compromised", compEv);
            }
        }

        return materialize(keys, audit, encryptions, diags, events.size());
    }

    private static Map<String, Object> encRow(
            int seq, int tick, String keyId, Object nonce, String outcome, String reason) {
        Map<String, Object> enc = new TreeMap<>();
        enc.put("seq", seq);
        enc.put("tick", tick);
        enc.put("key_id", keyId);
        enc.put("nonce", nonce);
        enc.put("outcome", outcome);
        enc.put("reason", reason);
        return enc;
    }

    private static Map<String, Object> materialize(
            Map<String, KeyState> keys,
            List<Map<String, Object>> audit,
            List<Map<String, Object>> encryptions,
            List<Map<String, Object>> diags,
            int eventsTotal) {
        List<Map<String, Object>> keyList = new ArrayList<>();
        for (KeyState k : keys.values()) {
            Map<String, Object> row = new TreeMap<>();
            row.put("algorithm", k.algorithm);
            row.put("compromised_seq", k.compromisedSeq);
            row.put("exhausted_seq", k.exhaustedSeq);
            row.put("installed_seq", k.installedSeq);
            row.put("key_id", k.keyId);
            row.put("last_use_tick", k.lastUseTick);
            row.put("max_uses", k.maxUses);
            row.put("retired_seq", k.retiredSeq);
            row.put("state", k.state);
            row.put("uses_count", k.usesCount);
            keyList.add(row);
        }
        keyList.sort(Comparator.comparing(r -> (String) r.get("key_id")));

        encryptions.sort(Comparator.comparingInt(r -> (Integer) r.get("seq")));
        audit.sort(
                Comparator.<Map<String, Object>>comparingInt(r -> (Integer) r.get("seq"))
                        .thenComparing(r -> (String) r.get("key_id")));

        diags.sort(
                Comparator.<Map<String, Object>>comparingInt(
                                r -> (Integer) r.get("severity_rank"))
                        .thenComparingInt(r -> (Integer) r.get("seq"))
                        .thenComparing(r -> (String) r.get("code"))
                        .thenComparing(
                                r ->
                                        r.get("key_id") == null
                                                ? ""
                                                : (String) r.get("key_id")));

        Map<String, Integer> sev = new TreeMap<>();
        sev.put("error", 0);
        sev.put("warning", 0);
        sev.put("notice", 0);
        for (Map<String, Object> d : diags) {
            sev.put((String) d.get("severity"), sev.get((String) d.get("severity")) + 1);
        }

        int encAccepted = 0;
        int encRejected = 0;
        for (Map<String, Object> e : encryptions) {
            if ("accepted".equals(e.get("outcome"))) {
                encAccepted++;
            } else {
                encRejected++;
            }
        }

        Map<String, Object> totals = new TreeMap<>();
        totals.put("encryptions_accepted", encAccepted);
        totals.put("encryptions_rejected", encRejected);
        totals.put("encryptions_total", encryptions.size());
        totals.put("errors", sev.get("error"));
        totals.put("events_total", eventsTotal);
        totals.put("keys_total", keyList.size());
        totals.put("notices", sev.get("notice"));
        totals.put("warnings", sev.get("warning"));

        Map<String, Object> out = new TreeMap<>();
        Map<String, Object> keyStates = new TreeMap<>();
        keyStates.put("keys", keyList);
        Map<String, Object> encLog = new TreeMap<>();
        encLog.put("encryptions", encryptions);
        Map<String, Object> auditDoc = new TreeMap<>();
        auditDoc.put("transitions", audit);
        Map<String, Object> diagDoc = new TreeMap<>();
        diagDoc.put("diagnostics", diags);
        Map<String, Object> summaryDoc = new TreeMap<>();
        summaryDoc.put("totals", totals);
        out.put("key_states", keyStates);
        out.put("encryption_log", encLog);
        out.put("audit_log", auditDoc);
        out.put("diagnostics", diagDoc);
        out.put("summary", summaryDoc);
        return out;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject keysIn = readObject(inDir.resolve("keys.json"));
        JsonObject eventsIn = readObject(inDir.resolve("events.json"));
        JsonObject policy = readObject(inDir.resolve("policy.json"));

        Map<String, Object> outputs = simulate(keysIn, eventsIn, policy);
        writeCanonical(outDir.resolve("key_states.json"), outputs.get("key_states"));
        writeCanonical(outDir.resolve("encryption_log.json"), outputs.get("encryption_log"));
        writeCanonical(outDir.resolve("audit_log.json"), outputs.get("audit_log"));
        writeCanonical(outDir.resolve("diagnostics.json"), outputs.get("diagnostics"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
