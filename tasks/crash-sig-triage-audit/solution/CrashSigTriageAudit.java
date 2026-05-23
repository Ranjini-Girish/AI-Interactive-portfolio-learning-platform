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
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Pattern;

/** Crash-signature triage audit oracle. */
public final class CrashSigTriageAudit {

    private static final Pattern HEX64 = Pattern.compile("^[0-9a-f]{64}$");
    private static final Set<String> REPRO_VALUES =
            new LinkedHashSet<>(Arrays.asList("always", "intermittent", "once"));
    private static final List<String> SEVERITY_VALUES =
            Arrays.asList("low", "medium", "high", "critical");

    private CrashSigTriageAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: CrashSigTriageAudit <dataDir> <triageDir>");
            System.exit(1);
        }
        run(Path.of(args[0]), Path.of(args[1]));
    }

    private static void run(Path data, Path out) throws IOException {
        Files.createDirectories(out);

        JsonObject poolState = loadJson(data.resolve("pool_state.json"));
        JsonObject triageConfig = loadJson(data.resolve("triage_config.json"));
        JsonObject moduleMap = loadJson(data.resolve("module_map.json"));
        JsonObject incidentLog = loadJson(data.resolve("incident_log.json"));

        int currentDay = poolState.get("current_day").getAsInt();
        String triageVersion = poolState.get("triage_version").getAsString();
        int escalationThreshold = triageConfig.get("cluster_size_escalation_threshold").getAsInt();
        String defaultOwnerTeam = triageConfig.get("default_owner_team").getAsString();
        JsonArray severityOrderArr = triageConfig.getAsJsonArray("severity_order");
        List<String> severityOrder = new ArrayList<>();
        for (JsonElement el : severityOrderArr) {
            severityOrder.add(el.getAsString());
        }
        Map<String, Integer> severityRank = new HashMap<>();
        for (int i = 0; i < severityOrder.size(); i++) {
            severityRank.put(severityOrder.get(i), i);
        }

        List<JsonObject> rawReleases = loadDir(data, "releases");
        List<JsonObject> rawCrashes = loadDir(data, "crashes");

        List<Release> validReleases = new ArrayList<>();
        for (JsonObject r : rawReleases) {
            if (validateRelease(r, currentDay)) {
                validReleases.add(parseRelease(r));
            }
        }
        int invalidReleasesDropped = rawReleases.size() - validReleases.size();
        Map<String, Release> releasesByVersion = new HashMap<>();
        for (Release r : validReleases) {
            releasesByVersion.put(r.version, r);
        }

        List<Crash> validCrashes = new ArrayList<>();
        for (JsonObject c : rawCrashes) {
            if (validateCrash(c, currentDay)) {
                validCrashes.add(parseCrash(c));
            }
        }
        int invalidCrashesDropped = rawCrashes.size() - validCrashes.size();

        Map<String, String> initialClusterForCrash = new HashMap<>();
        Map<String, List<String>> initialClusters = new LinkedHashMap<>();
        for (Crash c : validCrashes) {
            String sig = canonicalSignature(c.frameStack);
            initialClusterForCrash.put(c.id, sig);
            initialClusters.computeIfAbsent(sig, k -> new ArrayList<>()).add(c.id);
        }

        int ignoredIncidentEvents = 0;
        List<JsonObject> pendingMerges = new ArrayList<>();
        List<JsonObject> pendingReassigns = new ArrayList<>();
        List<JsonObject> acceptedPoisonedBuilds = new ArrayList<>();

        JsonArray events =
                incidentLog.has("events") && incidentLog.get("events").isJsonArray()
                        ? incidentLog.getAsJsonArray("events")
                        : new JsonArray();
        for (JsonElement evEl : events) {
            if (!evEl.isJsonObject()) {
                ignoredIncidentEvents++;
                continue;
            }
            JsonObject ev = evEl.getAsJsonObject();
            String kind = ev.has("kind") && ev.get("kind").isJsonPrimitive()
                    ? ev.get("kind").getAsString()
                    : null;
            if (!Arrays.asList("poisoned_build", "owner_reassign", "cluster_merge")
                    .contains(kind)) {
                ignoredIncidentEvents++;
                continue;
            }
            if (!isIntIn(ev.get("day"), 0, currentDay)) {
                ignoredIncidentEvents++;
                continue;
            }
            if ("poisoned_build".equals(kind)) {
                JsonElement h = ev.get("diff_hash");
                JsonElement reason = ev.get("reason");
                if (!(isNonemptyString(h) && HEX64.matcher(h.getAsString()).matches())
                        || !isNonemptyString(reason)) {
                    ignoredIncidentEvents++;
                    continue;
                }
                acceptedPoisonedBuilds.add(ev);
            } else if ("owner_reassign".equals(kind)) {
                JsonElement evId = ev.get("event_id");
                JsonElement sig = ev.get("signature");
                JsonElement newOwner = ev.get("new_owner_team");
                if (!(isNonemptyString(evId)
                        && isNonemptyString(sig)
                        && isNonemptyString(newOwner))) {
                    ignoredIncidentEvents++;
                    continue;
                }
                if (!initialClusters.containsKey(sig.getAsString())) {
                    ignoredIncidentEvents++;
                    continue;
                }
                pendingReassigns.add(ev);
            } else if ("cluster_merge".equals(kind)) {
                JsonElement evId = ev.get("event_id");
                JsonElement src = ev.get("source_signature");
                JsonElement tgt = ev.get("target_signature");
                if (!(isNonemptyString(evId)
                        && isNonemptyString(src)
                        && isNonemptyString(tgt))) {
                    ignoredIncidentEvents++;
                    continue;
                }
                String srcS = src.getAsString();
                String tgtS = tgt.getAsString();
                if (srcS.equals(tgtS)) {
                    ignoredIncidentEvents++;
                    continue;
                }
                if (!initialClusters.containsKey(srcS) || !initialClusters.containsKey(tgtS)) {
                    ignoredIncidentEvents++;
                    continue;
                }
                pendingMerges.add(ev);
            }
        }

        Map<String, ClusterState> currentClusters = new LinkedHashMap<>();
        for (Map.Entry<String, List<String>> e : initialClusters.entrySet()) {
            ClusterState cs = new ClusterState();
            cs.crashes = new ArrayList<>(e.getValue());
            cs.mergedFrom = new ArrayList<>();
            currentClusters.put(e.getKey(), cs);
        }

        int mergedClustersCount = 0;
        pendingMerges.sort(
                Comparator.comparingInt((JsonObject e) -> e.get("day").getAsInt())
                        .thenComparing(e -> e.get("event_id").getAsString()));
        for (JsonObject ev : pendingMerges) {
            String src = ev.get("source_signature").getAsString();
            String tgt = ev.get("target_signature").getAsString();
            if (!currentClusters.containsKey(src) || !currentClusters.containsKey(tgt)) {
                ignoredIncidentEvents++;
                continue;
            }
            if (src.equals(tgt)) {
                ignoredIncidentEvents++;
                continue;
            }
            ClusterState tgtState = currentClusters.get(tgt);
            ClusterState srcState = currentClusters.get(src);
            tgtState.crashes.addAll(srcState.crashes);
            tgtState.mergedFrom.add(src);
            tgtState.mergedFrom.addAll(srcState.mergedFrom);
            currentClusters.remove(src);
            mergedClustersCount++;
        }

        for (ClusterState cs : currentClusters.values()) {
            Set<String> merged = new TreeSet<>(cs.mergedFrom);
            cs.mergedFrom = new ArrayList<>(merged);
        }

        List<JsonObject> validReassigns = new ArrayList<>();
        for (JsonObject ev : pendingReassigns) {
            String sig = ev.get("signature").getAsString();
            if (currentClusters.containsKey(sig)) {
                validReassigns.add(ev);
            } else {
                ignoredIncidentEvents++;
            }
        }

        Map<String, Crash> crashById = new HashMap<>();
        for (Crash c : validCrashes) {
            crashById.put(c.id, c);
        }

        Map<String, ClusterRecord> clusterRecords = new LinkedHashMap<>();
        for (Map.Entry<String, ClusterState> e : currentClusters.entrySet()) {
            String sig = e.getKey();
            ClusterState info = e.getValue();
            List<Crash> crashes = new ArrayList<>();
            for (String cid : info.crashes) {
                crashes.add(crashById.get(cid));
            }
            int firstSeen = crashes.stream().mapToInt(c -> c.reportedDay).min().orElse(0);
            int lastSeen = crashes.stream().mapToInt(c -> c.reportedDay).max().orElse(0);
            String observed =
                    crashes.stream()
                            .map(c -> c.severityObserved)
                            .max(Comparator.comparingInt(s -> severityRank.get(s)))
                            .orElse("low");
            boolean hasAlways =
                    crashes.stream().anyMatch(c -> "always".equals(c.reproducibility));
            int size = crashes.size();
            Release attributed = attributedReleaseFor(validReleases, firstSeen);
            ClusterRecord rec = new ClusterRecord();
            rec.signature = sig;
            rec.crashes = new ArrayList<>(info.crashes);
            rec.crashes.sort(String::compareTo);
            rec.firstSeenDay = firstSeen;
            rec.lastSeenDay = lastSeen;
            rec.mergedFrom = info.mergedFrom;
            rec.size = size;
            rec.observedSeverity = observed;
            rec.hasAlways = hasAlways;
            rec.attributed = attributed;
            rec.firstFrame = firstFrameOfSignature(sig);
            clusterRecords.put(sig, rec);
        }

        Set<String> poisonedDiffHashes = new HashSet<>();
        for (JsonObject ev : acceptedPoisonedBuilds) {
            poisonedDiffHashes.add(ev.get("diff_hash").getAsString());
        }
        Set<String> poisonedClustersSet = new TreeSet<>();
        for (Map.Entry<String, ClusterRecord> e : clusterRecords.entrySet()) {
            ClusterRecord rec = e.getValue();
            if (rec.attributed != null
                    && poisonedDiffHashes.contains(rec.attributed.diffHash)) {
                poisonedClustersSet.add(e.getKey());
            }
        }

        Map<String, List<JsonObject>> reassignsBySig = new HashMap<>();
        for (JsonObject ev : validReassigns) {
            String sig = ev.get("signature").getAsString();
            reassignsBySig.computeIfAbsent(sig, k -> new ArrayList<>()).add(ev);
        }

        List<JsonObject> clusterIndexOut = new ArrayList<>();
        List<JsonObject> attributionOut = new ArrayList<>();
        List<JsonObject> severityOut = new ArrayList<>();
        List<JsonObject> ownerOut = new ArrayList<>();

        Map<String, Integer> assignmentReasonCounts = new LinkedHashMap<>();
        assignmentReasonCounts.put("module_match", 0);
        assignmentReasonCounts.put("release_default", 0);
        assignmentReasonCounts.put("owner_reassign", 0);
        assignmentReasonCounts.put("poisoned_build_override", 0);
        assignmentReasonCounts.put("default_owner", 0);

        Map<String, Integer> attributionNoteCounts = new LinkedHashMap<>();
        attributionNoteCounts.put("release_match", 0);
        attributionNoteCounts.put("unattributed", 0);
        attributionNoteCounts.put("poisoned_build", 0);

        Map<String, Integer> severityCounts = new LinkedHashMap<>();
        for (String s : SEVERITY_VALUES) {
            severityCounts.put(s, 0);
        }

        List<String> sortedSigs = new ArrayList<>(clusterRecords.keySet());
        sortedSigs.sort(String::compareTo);

        for (String sig : sortedSigs) {
            ClusterRecord rec = clusterRecords.get(sig);

            JsonObject clusterEntry = new JsonObject();
            clusterEntry.addProperty("signature", sig);
            clusterEntry.add("crashes", stringListToJsonArray(rec.crashes));
            clusterEntry.addProperty("first_seen_day", rec.firstSeenDay);
            clusterEntry.addProperty("last_seen_day", rec.lastSeenDay);
            clusterEntry.add("merged_from", stringListToJsonArray(rec.mergedFrom));
            clusterIndexOut.add(clusterEntry);

            Release attr = rec.attributed;
            String note;
            String attributedVersion;
            String attributedHash;
            if (poisonedClustersSet.contains(sig)) {
                note = "poisoned_build";
                attributedVersion = attr.version;
                attributedHash = attr.diffHash;
            } else if (attr == null) {
                note = "unattributed";
                attributedVersion = null;
                attributedHash = null;
            } else {
                note = "release_match";
                attributedVersion = attr.version;
                attributedHash = attr.diffHash;
            }
            JsonObject attributionEntry = new JsonObject();
            attributionEntry.addProperty("signature", sig);
            if (attributedVersion == null) {
                attributionEntry.add("attributed_release", JsonNull.INSTANCE);
            } else {
                attributionEntry.addProperty("attributed_release", attributedVersion);
            }
            if (attributedHash == null) {
                attributionEntry.add("attributed_diff_hash", JsonNull.INSTANCE);
            } else {
                attributionEntry.addProperty("attributed_diff_hash", attributedHash);
            }
            attributionEntry.addProperty("attribution_note", note);
            attributionOut.add(attributionEntry);
            attributionNoteCounts.merge(note, 1, Integer::sum);

            String computed;
            String sevReason;
            if (poisonedClustersSet.contains(sig)) {
                computed = "critical";
                sevReason = "escalated_poisoned_build";
            } else if (rec.hasAlways) {
                computed = "critical";
                sevReason = "escalated_reproducibility_always";
            } else if (rec.size >= escalationThreshold) {
                computed = "critical";
                sevReason = "escalated_cluster_size_" + rec.size;
            } else {
                computed = rec.observedSeverity;
                sevReason = "max_observed_" + computed;
            }
            JsonObject severityEntry = new JsonObject();
            severityEntry.addProperty("signature", sig);
            severityEntry.addProperty("observed_severity", rec.observedSeverity);
            severityEntry.addProperty("computed_severity", computed);
            severityEntry.addProperty("severity_reason", sevReason);
            severityOut.add(severityEntry);
            severityCounts.merge(computed, 1, Integer::sum);

            String ownerTeam;
            String ownerReason;
            if (poisonedClustersSet.contains(sig)) {
                ownerTeam = "release-engineering";
                ownerReason = "poisoned_build_override";
            } else if (reassignsBySig.containsKey(sig)) {
                List<JsonObject> evs = reassignsBySig.get(sig);
                evs.sort(
                        Comparator.comparingInt((JsonObject e) -> e.get("day").getAsInt())
                                .reversed()
                                .thenComparing(e -> e.get("event_id").getAsString()));
                ownerTeam = evs.get(0).get("new_owner_team").getAsString();
                ownerReason = "owner_reassign";
            } else {
                ModuleMatch mm = moduleMatch(moduleMap, rec.firstFrame);
                if (mm != null) {
                    ownerTeam = mm.ownerTeam;
                    ownerReason = "module_match";
                } else if (attr != null) {
                    ownerTeam = attr.ownerTeam;
                    ownerReason = "release_default";
                } else {
                    ownerTeam = defaultOwnerTeam;
                    ownerReason = "default_owner";
                }
            }
            JsonObject ownerEntry = new JsonObject();
            ownerEntry.addProperty("signature", sig);
            ownerEntry.addProperty("assigned_owner_team", ownerTeam);
            ownerEntry.addProperty("assignment_reason", ownerReason);
            ownerOut.add(ownerEntry);
            assignmentReasonCounts.merge(ownerReason, 1, Integer::sum);
        }

        JsonObject summaryOut = new JsonObject();
        summaryOut.addProperty("current_day", currentDay);
        summaryOut.addProperty("triage_version", triageVersion);
        JsonObject totals = new JsonObject();
        totals.addProperty("crashes", validCrashes.size());
        totals.addProperty("clusters", clusterRecords.size());
        totals.addProperty("releases", validReleases.size());
        totals.addProperty("invalid_crashes_dropped", invalidCrashesDropped);
        totals.addProperty("invalid_releases_dropped", invalidReleasesDropped);
        totals.addProperty("ignored_incident_events", ignoredIncidentEvents);
        totals.addProperty("merged_clusters", mergedClustersCount);
        summaryOut.add("totals", totals);
        summaryOut.add("by_severity", intMapToJson(severityCounts));
        summaryOut.add("by_attribution_note", intMapToJson(attributionNoteCounts));
        summaryOut.add("by_assignment_reason", intMapToJson(assignmentReasonCounts));
        summaryOut.add("poisoned_clusters", stringListToJsonArray(new ArrayList<>(poisonedClustersSet)));

        JsonObject clusterIndexRoot = new JsonObject();
        clusterIndexRoot.add("clusters", listToJsonArray(clusterIndexOut));
        writeJson(out.resolve("cluster_index.json"), clusterIndexRoot);

        JsonObject attributionRoot = new JsonObject();
        attributionRoot.add("clusters", listToJsonArray(attributionOut));
        writeJson(out.resolve("attribution_report.json"), attributionRoot);

        JsonObject severityRoot = new JsonObject();
        severityRoot.add("clusters", listToJsonArray(severityOut));
        writeJson(out.resolve("severity_ranking.json"), severityRoot);

        JsonObject ownerRoot = new JsonObject();
        ownerRoot.add("clusters", listToJsonArray(ownerOut));
        writeJson(out.resolve("owner_assignment.json"), ownerRoot);

        writeJson(out.resolve("summary.json"), summaryOut);
    }

    private static String canonicalSignature(List<String> frames) {
        List<String> combined;
        if (frames.size() >= 4) {
            combined = new ArrayList<>(frames.subList(0, 3));
            combined.add(frames.get(frames.size() - 1));
        } else {
            combined = new ArrayList<>(frames);
        }
        Set<String> seen = new HashSet<>();
        List<String> deduped = new ArrayList<>();
        for (String f : combined) {
            if (!seen.contains(f)) {
                seen.add(f);
                deduped.add(f);
            }
        }
        return String.join("|", deduped);
    }

    private static String firstFrameOfSignature(String sig) {
        int idx = sig.indexOf('|');
        return idx == -1 ? sig : sig.substring(0, idx);
    }

    private static Release attributedReleaseFor(List<Release> validReleases, int firstSeenDay) {
        List<Release> candidates = new ArrayList<>();
        for (Release r : validReleases) {
            if (r.day >= firstSeenDay) {
                candidates.add(r);
            }
        }
        if (candidates.isEmpty()) {
            return null;
        }
        candidates.sort(
                Comparator.comparingInt((Release r) -> r.day).thenComparing(r -> r.version));
        return candidates.get(0);
    }

    private static ModuleMatch moduleMatch(JsonObject moduleMap, String firstFrame) {
        if (!moduleMap.has("modules") || !moduleMap.get("modules").isJsonArray()) {
            return null;
        }
        List<ModuleMatch> matches = new ArrayList<>();
        for (JsonElement el : moduleMap.getAsJsonArray("modules")) {
            if (!el.isJsonObject()) {
                continue;
            }
            JsonObject m = el.getAsJsonObject();
            if (!m.has("frame_prefix") || !m.has("owner_team")) {
                continue;
            }
            String prefix = m.get("frame_prefix").getAsString();
            if (firstFrame.startsWith(prefix)) {
                ModuleMatch mm = new ModuleMatch();
                mm.framePrefix = prefix;
                mm.ownerTeam = m.get("owner_team").getAsString();
                matches.add(mm);
            }
        }
        if (matches.isEmpty()) {
            return null;
        }
        matches.sort(
                Comparator.<ModuleMatch>comparingInt(m -> -m.framePrefix.length())
                        .thenComparing(m -> m.framePrefix));
        return matches.get(0);
    }

    private static boolean validateRelease(JsonObject r, int currentDay) {
        if (!isNonemptyString(r.get("version"))) {
            return false;
        }
        if (!isIntIn(r.get("day"), 0, currentDay)) {
            return false;
        }
        JsonElement h = r.get("diff_hash");
        if (!(isNonemptyString(h) && HEX64.matcher(h.getAsString()).matches())) {
            return false;
        }
        return isNonemptyString(r.get("owner_team"));
    }

    private static boolean validateCrash(JsonObject c, int currentDay) {
        if (!isNonemptyString(c.get("id"))) {
            return false;
        }
        if (!isIntIn(c.get("reported_day"), 0, currentDay)) {
            return false;
        }
        if (!isNonemptyString(c.get("reporter"))) {
            return false;
        }
        JsonElement framesEl = c.get("frame_stack");
        if (framesEl == null || !framesEl.isJsonArray()) {
            return false;
        }
        JsonArray frames = framesEl.getAsJsonArray();
        if (frames.size() == 0) {
            return false;
        }
        for (JsonElement f : frames) {
            if (!isNonemptyString(f)) {
                return false;
            }
        }
        JsonElement h = c.get("env_hash");
        if (!(isNonemptyString(h) && HEX64.matcher(h.getAsString()).matches())) {
            return false;
        }
        JsonElement repro = c.get("reproducibility");
        if (repro == null
                || !repro.isJsonPrimitive()
                || !REPRO_VALUES.contains(repro.getAsString())) {
            return false;
        }
        JsonElement sev = c.get("severity_observed");
        return sev != null
                && sev.isJsonPrimitive()
                && SEVERITY_VALUES.contains(sev.getAsString());
    }

    private static Release parseRelease(JsonObject r) {
        Release rel = new Release();
        rel.version = r.get("version").getAsString();
        rel.day = r.get("day").getAsInt();
        rel.diffHash = r.get("diff_hash").getAsString();
        rel.ownerTeam = r.get("owner_team").getAsString();
        return rel;
    }

    private static Crash parseCrash(JsonObject c) {
        Crash crash = new Crash();
        crash.id = c.get("id").getAsString();
        crash.reportedDay = c.get("reported_day").getAsInt();
        crash.reporter = c.get("reporter").getAsString();
        crash.frameStack = new ArrayList<>();
        for (JsonElement f : c.getAsJsonArray("frame_stack")) {
            crash.frameStack.add(f.getAsString());
        }
        crash.envHash = c.get("env_hash").getAsString();
        crash.reproducibility = c.get("reproducibility").getAsString();
        crash.severityObserved = c.get("severity_observed").getAsString();
        return crash;
    }

    private static List<JsonObject> loadDir(Path data, String subdir) throws IOException {
        Path p = data.resolve(subdir);
        List<JsonObject> out = new ArrayList<>();
        if (!Files.isDirectory(p)) {
            return out;
        }
        List<Path> files = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(p)) {
            for (Path f : stream) {
                if (Files.isRegularFile(f)
                        && f.getFileName().toString().endsWith(".json")) {
                    files.add(f);
                }
            }
        }
        files.sort(Comparator.comparing(path -> path.getFileName().toString()));
        for (Path f : files) {
            out.add(loadJson(f));
        }
        return out;
    }

    private static boolean isNonemptyString(JsonElement el) {
        return el != null
                && el.isJsonPrimitive()
                && el.getAsJsonPrimitive().isString()
                && !el.getAsString().isEmpty();
    }

    private static boolean isIntIn(JsonElement el, int lo, Integer hi) {
        if (el == null || !el.isJsonPrimitive()) {
            return false;
        }
        if (el.getAsJsonPrimitive().isBoolean()) {
            return false;
        }
        if (!el.getAsJsonPrimitive().isNumber()) {
            return false;
        }
        int v = el.getAsInt();
        if (v < lo) {
            return false;
        }
        return hi == null || v <= hi;
    }

    private static JsonObject loadJson(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        JsonElement sorted = deepSort(root);
        String text = gson.toJson(sorted) + "\n";
        Files.writeString(path, text, StandardCharsets.UTF_8);
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

    private static JsonArray stringListToJsonArray(List<String> items) {
        JsonArray arr = new JsonArray();
        for (String s : items) {
            arr.add(s);
        }
        return arr;
    }

    private static JsonArray listToJsonArray(List<JsonObject> items) {
        JsonArray arr = new JsonArray();
        for (JsonObject o : items) {
            arr.add(o);
        }
        return arr;
    }

    private static JsonObject intMapToJson(Map<String, Integer> map) {
        JsonObject o = new JsonObject();
        for (Map.Entry<String, Integer> e : map.entrySet()) {
            o.addProperty(e.getKey(), e.getValue());
        }
        return o;
    }

    private static final class Release {
        String version;
        int day;
        String diffHash;
        String ownerTeam;
    }

    private static final class Crash {
        String id;
        int reportedDay;
        String reporter;
        List<String> frameStack;
        String envHash;
        String reproducibility;
        String severityObserved;
    }

    private static final class ClusterState {
        List<String> crashes;
        List<String> mergedFrom;
    }

    private static final class ClusterRecord {
        String signature;
        List<String> crashes;
        int firstSeenDay;
        int lastSeenDay;
        List<String> mergedFrom;
        int size;
        String observedSeverity;
        boolean hasAlways;
        Release attributed;
        String firstFrame;
    }

    private static final class ModuleMatch {
        String framePrefix;
        String ownerTeam;
    }
}
