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
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Kerberos keytab rotation auditor (Java port of accepted C++ oracle). */
public final class KeytabRotationAudit {
    private static final Gson GSON_PRETTY =
            new GsonBuilder()
                    .disableHtmlEscaping()
                    .serializeNulls()
                    .setPrettyPrinting()
                    .create();
    private static final Gson GSON_COMPACT =
            new GsonBuilder().disableHtmlEscaping().serializeNulls().create();

    private static final Map<String, Integer> SEVERITY_RANK = new TreeMap<>();

    static {
        SEVERITY_RANK.put("critical", 0);
        SEVERITY_RANK.put("high", 1);
        SEVERITY_RANK.put("medium", 2);
        SEVERITY_RANK.put("low", 3);
    }

    private static final String[] VERDICTS = {
        "valid",
        "valid_cross_fade",
        "invalid_kvno_unknown",
        "invalid_kvno_revoked",
        "invalid_kvno_retired",
        "downgrade_attempt",
        "weak_enctype"
    };

    private KeytabRotationAudit() {}

    private static final class KvnoRecord {
        int kvno;
        int addedDay;
        int addedHour;
        String enctype;
        Integer revokedDay;
        Integer revokedHour;
        String revokeReason;
        Integer retiredDay;
        Integer retiredHour;
        String finalState = "active";
    }

    private static final class Anomaly {
        String kind;
        String severity;
        String principal;
        Integer kvno;
        int day;
        int hour;
    }

    private static final class PolicyVersion {
        String version;
        int effectiveDay;
        Set<String> allowed = new HashSet<>();
        Set<String> forbidden = new HashSet<>();
    }

    private static JsonObject readObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static List<JsonObject> readJsonl(Path path) throws IOException {
        List<JsonObject> out = new ArrayList<>();
        for (String line : Files.readString(path, StandardCharsets.UTF_8).split("\n")) {
            if (!line.isBlank()) {
                out.add(JsonParser.parseString(line).getAsJsonObject());
            }
        }
        return out;
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
        JsonElement el = JsonParser.parseString(GSON_PRETTY.toJson(value));
        JsonElement sorted =
                el.isJsonObject() ? sortKeysRecursive(el.getAsJsonObject()) : el;
        Files.writeString(path, GSON_PRETTY.toJson(sorted) + "\n", StandardCharsets.UTF_8);
    }

    private static String sha256Hex(byte[] data) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            StringBuilder sb = new StringBuilder();
            for (byte b : md.digest(data)) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException(e);
        }
    }

    private static String anomalyId(String kind, String principal, Integer kvno, int day, int hour) {
        JsonObject j = new JsonObject();
        j.addProperty("day", day);
        j.addProperty("hour", hour);
        j.addProperty("kind", kind);
        if (kvno == null) {
            j.add("kvno", null);
        } else {
            j.addProperty("kvno", kvno);
        }
        j.addProperty("principal", principal);
        JsonObject sorted = sortKeysRecursive(j);
        String blob = GSON_COMPACT.toJson(sorted);
        return sha256Hex(blob.getBytes(StandardCharsets.UTF_8));
    }

    private static String anomalyDetails(String kind, String principal, Integer kvno) {
        if (kvno == null) {
            return kind + " on " + principal;
        }
        return kind + " on " + principal + " kvno=" + kvno;
    }

    private static Map<String, Object> runAudit(Path dataDir) throws IOException {
        JsonObject pool = readObject(dataDir.resolve("pool_state.json"));
        int currentDay = pool.get("current_day").getAsInt();
        int currentHour = pool.get("current_hour").getAsInt();

        JsonObject rotpol = readObject(dataDir.resolve("policies/rotation_policy.json"));
        int crossFadeHours = rotpol.get("cross_fade_hours").getAsInt();
        Map<String, Integer> tierWindows = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e : rotpol.getAsJsonObject("tier_windows").entrySet()) {
            tierWindows.put(e.getKey(), e.getValue().getAsInt());
        }

        JsonObject encpol = readObject(dataDir.resolve("policies/enctype_policy.json"));
        List<PolicyVersion> policies = new ArrayList<>();
        for (JsonElement el : encpol.getAsJsonArray("versions")) {
            JsonObject v = el.getAsJsonObject();
            PolicyVersion pv = new PolicyVersion();
            pv.version = v.get("version").getAsString();
            pv.effectiveDay = v.get("effective_day").getAsInt();
            for (JsonElement a : v.getAsJsonArray("allowed_enctypes")) {
                pv.allowed.add(a.getAsString());
            }
            for (JsonElement f : v.getAsJsonArray("forbidden_enctypes")) {
                pv.forbidden.add(f.getAsString());
            }
            policies.add(pv);
        }
        policies.sort(Comparator.comparingInt(p -> p.effectiveDay));

        Map<String, JsonObject> principals = new TreeMap<>();
        try (var stream = Files.list(dataDir.resolve("principals"))) {
            for (Path p : stream.sorted().toList()) {
                if (Files.isRegularFile(p) && p.toString().endsWith(".json")) {
                    JsonObject j = readObject(p);
                    principals.put(j.get("principal").getAsString(), j);
                }
            }
        }

        List<JsonObject> rawKeytab = new ArrayList<>();
        try (var stream = Files.list(dataDir.resolve("events"))) {
            for (Path p : stream.sorted().toList()) {
                String name = p.getFileName().toString();
                if (name.startsWith("keytab_chunk_") && name.endsWith(".jsonl")) {
                    rawKeytab.addAll(readJsonl(p));
                }
            }
        }
        int totalKeytabEvents = rawKeytab.size();

        Set<String> kvalid = Set.of("add", "revoke", "retire");
        Set<String> rvalid =
                Set.of("compromise", "expired", "policy_violation", "administrative");
        Set<String> seenIds = new HashSet<>();
        List<JsonObject> allKeytab = new ArrayList<>();
        int invalidKeytabEvents = 0;
        for (JsonObject j : rawKeytab) {
            try {
                String eid = j.get("event_id").getAsString();
                String kind = j.get("kind").getAsString();
                String princ = j.get("principal").getAsString();
                int kvno = j.get("kvno").getAsInt();
                int day = j.get("day").getAsInt();
                int hour = j.get("hour").getAsInt();
                if (eid.isEmpty() || seenIds.contains(eid)) {
                    throw new IllegalArgumentException();
                }
                if (!kvalid.contains(kind) || !principals.containsKey(princ)) {
                    throw new IllegalArgumentException();
                }
                if (kvno < 1 || kvno > 99999 || day < 0 || hour < 0 || hour > 23) {
                    throw new IllegalArgumentException();
                }
                if (day > currentDay || (day == currentDay && hour > currentHour)) {
                    throw new IllegalArgumentException();
                }
                if (kind.equals("add")
                        && (!j.has("enctype") || j.get("enctype").getAsString().isEmpty())) {
                    throw new IllegalArgumentException();
                }
                if (kind.equals("revoke") && !rvalid.contains(j.get("reason").getAsString())) {
                    throw new IllegalArgumentException();
                }
                seenIds.add(eid);
                allKeytab.add(j);
            } catch (RuntimeException ex) {
                invalidKeytabEvents++;
            }
        }
        allKeytab.sort(
                Comparator.comparingInt((JsonObject e) -> e.get("day").getAsInt())
                        .thenComparingInt(e -> e.get("hour").getAsInt())
                        .thenComparing(e -> e.get("event_id").getAsString()));

        List<JsonObject> rawTgs = new ArrayList<>();
        try (var stream = Files.list(dataDir.resolve("events"))) {
            for (Path p : stream.sorted().toList()) {
                String name = p.getFileName().toString();
                if (name.startsWith("tgs_chunk_") && name.endsWith(".jsonl")) {
                    rawTgs.addAll(readJsonl(p));
                }
            }
        }
        int totalTgsRequests = rawTgs.size();
        Set<String> seenRids = new HashSet<>();
        List<JsonObject> allTgs = new ArrayList<>();
        int invalidTgsRequests = 0;
        for (JsonObject j : rawTgs) {
            try {
                String rid = j.get("request_id").getAsString();
                String princ = j.get("principal").getAsString();
                int kvno = j.get("kvno").getAsInt();
                int day = j.get("day").getAsInt();
                int hour = j.get("hour").getAsInt();
                if (rid.isEmpty() || seenRids.contains(rid) || !principals.containsKey(princ)) {
                    throw new IllegalArgumentException();
                }
                if (kvno < 1 || kvno > 99999 || day < 0 || hour < 0 || hour > 23) {
                    throw new IllegalArgumentException();
                }
                if (day > currentDay || (day == currentDay && hour > currentHour)) {
                    throw new IllegalArgumentException();
                }
                seenRids.add(rid);
                allTgs.add(j);
            } catch (RuntimeException ex) {
                invalidTgsRequests++;
            }
        }
        allTgs.sort(
                Comparator.comparingInt((JsonObject r) -> r.get("day").getAsInt())
                        .thenComparingInt(r -> r.get("hour").getAsInt())
                        .thenComparing(r -> r.get("request_id").getAsString()));

        Set<String> validNames = new TreeSet<>();
        Set<String> invalidNames = new TreeSet<>();
        for (Map.Entry<String, JsonObject> e : principals.entrySet()) {
            if (tierWindows.containsKey(e.getValue().get("tier").getAsString())) {
                validNames.add(e.getKey());
            } else {
                invalidNames.add(e.getKey());
            }
        }

        Map<String, Map<Integer, KvnoRecord>> state = new TreeMap<>();
        Map<String, List<JsonObject>> perAdds = new TreeMap<>();
        List<Anomaly> anomalies = new ArrayList<>();

        java.util.function.IntFunction<PolicyVersion> policyAt =
                d -> {
                    PolicyVersion best = null;
                    for (PolicyVersion pv : policies) {
                        if (pv.effectiveDay <= d) {
                            if (best == null || pv.effectiveDay > best.effectiveDay) {
                                best = pv;
                            }
                        }
                    }
                    return best;
                };

        java.util.function.BiPredicate<String, Integer> enctypeAllowedAt =
                (enc, d) -> {
                    PolicyVersion pv = policyAt.apply(d);
                    if (pv == null) {
                        return true;
                    }
                    if (pv.forbidden.contains(enc)) {
                        return false;
                    }
                    return pv.allowed.contains(enc);
                };

        java.util.function.Consumer<Anomaly> record =
                a -> anomalies.add(a);

        for (JsonObject e : allKeytab) {
            String princ = e.get("principal").getAsString();
            if (!validNames.contains(princ)) {
                continue;
            }
            Map<Integer, KvnoRecord> st = state.computeIfAbsent(princ, k -> new TreeMap<>());
            int kv = e.get("kvno").getAsInt();
            String kind = e.get("kind").getAsString();
            int day = e.get("day").getAsInt();
            int hour = e.get("hour").getAsInt();
            if (kind.equals("add")) {
                boolean exists = st.containsKey(kv);
                boolean notStrict = false;
                if (!exists && !st.isEmpty()) {
                    int mx = st.keySet().stream().max(Integer::compareTo).orElse(0);
                    if (kv <= mx) {
                        notStrict = true;
                    }
                }
                if (exists || notStrict) {
                    Anomaly a = new Anomaly();
                    a.kind = "kvno_non_monotonic";
                    a.severity = "high";
                    a.principal = princ;
                    a.kvno = kv;
                    a.day = day;
                    a.hour = hour;
                    record.accept(a);
                    continue;
                }
                KvnoRecord r = new KvnoRecord();
                r.kvno = kv;
                r.addedDay = day;
                r.addedHour = hour;
                r.enctype = e.get("enctype").getAsString();
                st.put(kv, r);
                perAdds.computeIfAbsent(princ, k -> new ArrayList<>()).add(e);
            } else if (kind.equals("revoke")) {
                if (!st.containsKey(kv)) {
                    Anomaly a = new Anomaly();
                    a.kind = "revoke_unknown_kvno";
                    a.severity = "medium";
                    a.principal = princ;
                    a.kvno = kv;
                    a.day = day;
                    a.hour = hour;
                    record.accept(a);
                    continue;
                }
                KvnoRecord r = st.get(kv);
                if (!"active".equals(r.finalState)) {
                    Anomaly a = new Anomaly();
                    a.kind = "revoke_already_terminal";
                    a.severity = "low";
                    a.principal = princ;
                    a.kvno = kv;
                    a.day = day;
                    a.hour = hour;
                    record.accept(a);
                    continue;
                }
                r.revokedDay = day;
                r.revokedHour = hour;
                r.revokeReason = e.get("reason").getAsString();
                r.finalState = "revoked";
            } else if (kind.equals("retire")) {
                if (!st.containsKey(kv)) {
                    Anomaly a = new Anomaly();
                    a.kind = "retire_unknown_kvno";
                    a.severity = "medium";
                    a.principal = princ;
                    a.kvno = kv;
                    a.day = day;
                    a.hour = hour;
                    record.accept(a);
                    continue;
                }
                KvnoRecord r = st.get(kv);
                if (!"active".equals(r.finalState)) {
                    Anomaly a = new Anomaly();
                    a.kind = "retire_already_terminal";
                    a.severity = "low";
                    a.principal = princ;
                    a.kvno = kv;
                    a.day = day;
                    a.hour = hour;
                    record.accept(a);
                    continue;
                }
                r.retiredDay = day;
                r.retiredHour = hour;
                r.finalState = "retired";
            }
        }

        Set<String> compromised = new TreeSet<>();
        for (Map.Entry<String, Map<Integer, KvnoRecord>> ent : state.entrySet()) {
            for (KvnoRecord r : ent.getValue().values()) {
                if ("revoked".equals(r.finalState) && "compromise".equals(r.revokeReason)) {
                    compromised.add(ent.getKey());
                    break;
                }
            }
        }

        java.util.function.BiFunction<String, int[], List<Integer>> activeAt =
                (princ, dh) -> {
                    Map<Integer, KvnoRecord> st = state.get(princ);
                    List<Integer> act = new ArrayList<>();
                    if (st == null) {
                        return act;
                    }
                    int d = dh[0];
                    int h = dh[1];
                    for (Map.Entry<Integer, KvnoRecord> e : st.entrySet()) {
                        KvnoRecord r = e.getValue();
                        if (r.addedDay > d || (r.addedDay == d && r.addedHour > h)) {
                            continue;
                        }
                        if (r.revokedDay != null
                                && (r.revokedDay < d
                                        || (r.revokedDay == d && r.revokedHour <= h))) {
                            continue;
                        }
                        if (r.retiredDay != null
                                && (r.retiredDay < d
                                        || (r.retiredDay == d && r.retiredHour <= h))) {
                            continue;
                        }
                        act.add(e.getKey());
                    }
                    act.sort(Integer::compareTo);
                    return act;
                };

        Map<String, Integer> verdictCounts = new TreeMap<>();
        for (String v : VERDICTS) {
            verdictCounts.put(v, 0);
        }
        List<Map<String, Object>> ticketRequests = new ArrayList<>();

        for (JsonObject r : allTgs) {
            String princ = r.get("principal").getAsString();
            if (!validNames.contains(princ)) {
                continue;
            }
            int kv = r.get("kvno").getAsInt();
            int d = r.get("day").getAsInt();
            int h = r.get("hour").getAsInt();
            Map<Integer, KvnoRecord> st = state.get(princ);
            KvnoRecord rec = st != null ? st.get(kv) : null;
            boolean unknown =
                    rec == null
                            || rec.addedDay > d
                            || (rec.addedDay == d && rec.addedHour > h);
            String verdict;
            String anomalyKind = null;
            String anomalySev = null;
            if (unknown) {
                verdict = "invalid_kvno_unknown";
                anomalyKind = "ticket_unknown_kvno";
                anomalySev = "high";
            } else if (rec.revokedDay != null
                    && (rec.revokedDay < d || (rec.revokedDay == d && rec.revokedHour <= h))) {
                verdict = "invalid_kvno_revoked";
                anomalyKind = "ticket_against_revoked";
                anomalySev = "critical";
            } else if (rec.retiredDay != null
                    && (rec.retiredDay < d || (rec.retiredDay == d && rec.retiredHour <= h))) {
                verdict = "invalid_kvno_retired";
                anomalyKind = "ticket_against_retired";
                anomalySev = "medium";
            } else if (!enctypeAllowedAt.test(rec.enctype, d)) {
                verdict = "weak_enctype";
                anomalyKind = "weak_enctype_in_use";
                anomalySev = "high";
            } else {
                List<Integer> act = activeAt.apply(princ, new int[] {d, h});
                int cur = act.isEmpty() ? -1 : act.get(act.size() - 1);
                if (kv == cur) {
                    verdict = "valid";
                } else if (!act.isEmpty()) {
                    KvnoRecord cr = state.get(princ).get(cur);
                    long tH = (long) d * 24 + h;
                    long addH = (long) cr.addedDay * 24 + cr.addedHour;
                    if (tH < addH + crossFadeHours) {
                        verdict = "valid_cross_fade";
                    } else {
                        verdict = "downgrade_attempt";
                        anomalyKind = "downgrade_attempt";
                        anomalySev = "high";
                    }
                } else {
                    verdict = "downgrade_attempt";
                    anomalyKind = "downgrade_attempt";
                    anomalySev = "high";
                }
            }
            verdictCounts.put(verdict, verdictCounts.get(verdict) + 1);
            if (anomalyKind != null) {
                Anomaly a = new Anomaly();
                a.kind = anomalyKind;
                a.severity = anomalySev;
                a.principal = princ;
                a.kvno = kv;
                a.day = d;
                a.hour = h;
                record.accept(a);
            }
            if (compromised.contains(princ)) {
                Anomaly a = new Anomaly();
                a.kind = "compromised_principal_referenced";
                a.severity = "critical";
                a.principal = princ;
                a.kvno = kv;
                a.day = d;
                a.hour = h;
                record.accept(a);
            }
            PolicyVersion pv = policyAt.apply(d);
            Map<String, Object> req = new TreeMap<>();
            req.put("day", d);
            req.put("hour", h);
            req.put("kvno", kv);
            req.put("policy_version", pv != null ? pv.version : "none");
            req.put("principal", princ);
            req.put("request_id", r.get("request_id").getAsString());
            req.put("verdict", verdict);
            ticketRequests.add(req);
        }

        List<Map<String, Object>> rotPrincipals = new ArrayList<>();
        for (Map.Entry<String, JsonObject> ent : principals.entrySet()) {
            String n = ent.getKey();
            if (invalidNames.contains(n)) {
                continue;
            }
            JsonObject p = ent.getValue();
            Map<String, Object> entry = new TreeMap<>();
            entry.put("principal", n);
            entry.put("tier", p.get("tier").getAsString());
            entry.put("exempt", p.get("exempt").getAsBoolean());
            if (p.get("exempt").getAsBoolean()) {
                entry.put("rotation_window_days", null);
                entry.put("last_rotation_day", null);
                entry.put("next_due_day", null);
                entry.put("status", "exempt");
            } else {
                int w;
                if (p.has("override_rotation_days") && !p.get("override_rotation_days").isJsonNull()) {
                    w = p.get("override_rotation_days").getAsInt();
                } else {
                    w = tierWindows.get(p.get("tier").getAsString());
                }
                List<JsonObject> adds = perAdds.getOrDefault(n, List.of());
                entry.put("rotation_window_days", w);
                if (adds.isEmpty()) {
                    entry.put("last_rotation_day", null);
                    entry.put("next_due_day", null);
                    entry.put("status", "never_rotated");
                    Anomaly a = new Anomaly();
                    a.kind = "never_rotated";
                    a.severity = "high";
                    a.principal = n;
                    a.kvno = null;
                    a.day = currentDay;
                    a.hour = 0;
                    record.accept(a);
                } else {
                    int lastDay = adds.get(adds.size() - 1).get("day").getAsInt();
                    int nextDue = lastDay + w;
                    entry.put("last_rotation_day", lastDay);
                    entry.put("next_due_day", nextDue);
                    if (nextDue < currentDay) {
                        entry.put("status", "overdue");
                        Anomaly a = new Anomaly();
                        a.kind = "missed_rotation";
                        a.severity = "medium";
                        a.principal = n;
                        a.kvno = null;
                        a.day = currentDay;
                        a.hour = 0;
                        record.accept(a);
                    } else {
                        entry.put("status", "compliant");
                    }
                    long half = ((long) w * 24 + 1) / 2;
                    JsonObject earliestAdd = null;
                    for (int i = 1; i < adds.size(); i++) {
                        JsonObject prev = adds.get(i - 1);
                        JsonObject cur = adds.get(i);
                        long gap =
                                (long) cur.get("day").getAsInt() * 24
                                        + cur.get("hour").getAsInt()
                                        - (long) prev.get("day").getAsInt() * 24
                                        - prev.get("hour").getAsInt();
                        if (gap < half) {
                            if (earliestAdd == null) {
                                earliestAdd = cur;
                            } else {
                                int d0 = earliestAdd.get("day").getAsInt();
                                int h0 = earliestAdd.get("hour").getAsInt();
                                String id0 = earliestAdd.get("event_id").getAsString();
                                int d1 = cur.get("day").getAsInt();
                                int h1 = cur.get("hour").getAsInt();
                                String id1 = cur.get("event_id").getAsString();
                                if (d1 < d0
                                        || (d1 == d0 && h1 < h0)
                                        || (d1 == d0 && h1 == h0 && id1.compareTo(id0) < 0)) {
                                    earliestAdd = cur;
                                }
                            }
                        }
                    }
                    if (earliestAdd != null) {
                        Anomaly a = new Anomaly();
                        a.kind = "excessive_rotation";
                        a.severity = "low";
                        a.principal = n;
                        a.kvno = earliestAdd.get("kvno").getAsInt();
                        a.day = earliestAdd.get("day").getAsInt();
                        a.hour = earliestAdd.get("hour").getAsInt();
                        record.accept(a);
                    }
                }
            }
            rotPrincipals.add(entry);
        }

        for (String n : state.keySet()) {
            if (invalidNames.contains(n)) {
                continue;
            }
            List<Integer> act = activeAt.apply(n, new int[] {currentDay, currentHour});
            if (act.isEmpty()) {
                continue;
            }
            int cur = act.get(act.size() - 1);
            for (int k : act) {
                if (k == cur) {
                    continue;
                }
                long tH = (long) currentDay * 24 + currentHour;
                KvnoRecord cr = state.get(n).get(cur);
                long addH = (long) cr.addedDay * 24 + cr.addedHour;
                if (tH >= addH + crossFadeHours) {
                    Anomaly a = new Anomaly();
                    a.kind = "missed_retirement";
                    a.severity = "medium";
                    a.principal = n;
                    a.kvno = k;
                    a.day = currentDay;
                    a.hour = currentHour;
                    record.accept(a);
                }
            }
        }

        for (Map.Entry<String, Map<Integer, KvnoRecord>> ent : state.entrySet()) {
            if (invalidNames.contains(ent.getKey())) {
                continue;
            }
            for (Map.Entry<Integer, KvnoRecord> ke : ent.getValue().entrySet()) {
                KvnoRecord r = ke.getValue();
                if ("active".equals(r.finalState)
                        && !enctypeAllowedAt.test(r.enctype, currentDay)) {
                    Anomaly a = new Anomaly();
                    a.kind = "forbidden_enctype_active";
                    a.severity = "medium";
                    a.principal = ent.getKey();
                    a.kvno = ke.getKey();
                    a.day = currentDay;
                    a.hour = 0;
                    record.accept(a);
                }
            }
        }

        anomalies.sort(
                Comparator.comparingInt((Anomaly a) -> SEVERITY_RANK.get(a.severity))
                        .thenComparingInt(a -> a.day)
                        .thenComparingInt(a -> a.hour)
                        .thenComparing(a -> a.kind)
                        .thenComparing(a -> a.principal)
                        .thenComparingInt(a -> a.kvno == null ? 1 : 0)
                        .thenComparingInt(a -> a.kvno == null ? 0 : a.kvno));

        List<Map<String, Object>> kvnoPrincipals = new ArrayList<>();
        for (Map.Entry<String, JsonObject> ent : principals.entrySet()) {
            String n = ent.getKey();
            if (invalidNames.contains(n)) {
                continue;
            }
            JsonObject p = ent.getValue();
            List<Map<String, Object>> events = new ArrayList<>();
            Map<Integer, KvnoRecord> st = state.get(n);
            if (st != null) {
                for (int k : new TreeSet<>(st.keySet())) {
                    KvnoRecord r = st.get(k);
                    Map<String, Object> ke = new TreeMap<>();
                    ke.put("added_day", r.addedDay);
                    ke.put("added_hour", r.addedHour);
                    ke.put("enctype", r.enctype);
                    ke.put("final_state", r.finalState);
                    ke.put("kvno", r.kvno);
                    ke.put("retired_day", r.retiredDay);
                    ke.put("retired_hour", r.retiredHour);
                    ke.put("revoke_reason", r.revokeReason);
                    ke.put("revoked_day", r.revokedDay);
                    ke.put("revoked_hour", r.revokedHour);
                    events.add(ke);
                }
            }
            Map<String, Object> row = new TreeMap<>();
            row.put("exempt", p.get("exempt").getAsBoolean());
            row.put("kvno_events", events);
            row.put("principal", n);
            row.put("tier", p.get("tier").getAsString());
            kvnoPrincipals.add(row);
        }

        List<Map<String, Object>> anomalyRows = new ArrayList<>();
        for (Anomaly a : anomalies) {
            Map<String, Object> row = new TreeMap<>();
            row.put("day", a.day);
            row.put("details", anomalyDetails(a.kind, a.principal, a.kvno));
            row.put("hour", a.hour);
            row.put("id", anomalyId(a.kind, a.principal, a.kvno, a.day, a.hour));
            row.put("kind", a.kind);
            row.put("kvno", a.kvno);
            row.put("principal", a.principal);
            row.put("severity", a.severity);
            anomalyRows.add(row);
        }

        Map<String, Integer> sevCounts = new TreeMap<>();
        sevCounts.put("critical", 0);
        sevCounts.put("high", 0);
        sevCounts.put("medium", 0);
        sevCounts.put("low", 0);
        for (Anomaly a : anomalies) {
            sevCounts.put(a.severity, sevCounts.get(a.severity) + 1);
        }

        int exemptCount = 0;
        for (JsonObject p : principals.values()) {
            if (p.get("exempt").getAsBoolean()) {
                exemptCount++;
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("anomalies_per_severity", sevCounts);
        summary.put("compromised_principals", new ArrayList<>(compromised));
        summary.put("current_day", currentDay);
        summary.put("current_hour", currentHour);
        summary.put("exempt_principals", exemptCount);
        summary.put("invalid_keytab_events", invalidKeytabEvents);
        summary.put("invalid_principals", invalidNames.size());
        summary.put("invalid_tgs_requests", invalidTgsRequests);
        summary.put("tickets_per_verdict", verdictCounts);
        summary.put("total_keytab_events", totalKeytabEvents);
        summary.put("total_principals", principals.size());
        summary.put("total_tgs_requests", totalTgsRequests);

        Map<String, Object> out = new TreeMap<>();
        Map<String, Object> kvnoDoc = new TreeMap<>();
        kvnoDoc.put("principals", kvnoPrincipals);
        Map<String, Object> rotDoc = new TreeMap<>();
        rotDoc.put("principals", rotPrincipals);
        Map<String, Object> ticketDoc = new TreeMap<>();
        ticketDoc.put("requests", ticketRequests);
        Map<String, Object> anomDoc = new TreeMap<>();
        anomDoc.put("anomalies", anomalyRows);
        out.put("kvno_lifecycle.json", kvnoDoc);
        out.put("rotation_compliance.json", rotDoc);
        out.put("ticket_validity.json", ticketDoc);
        out.put("anomalies.json", anomDoc);
        out.put("summary.json", summary);
        return out;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: KeytabRotationAudit <data_dir> <audit_dir>");
            System.exit(2);
        }
        Path dataDir = Path.of(args[0]);
        Path auditDir = Path.of(args[1]);
        Files.createDirectories(auditDir);
        for (Map.Entry<String, Object> e : runAudit(dataDir).entrySet()) {
            writeCanonical(auditDir.resolve(e.getKey()), e.getValue());
        }
    }
}
