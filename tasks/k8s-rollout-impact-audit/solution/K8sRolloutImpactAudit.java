import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.google.gson.JsonPrimitive;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
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
import org.yaml.snakeyaml.Yaml;

/** Kubernetes rollout impact audit oracle. */
public final class K8sRolloutImpactAudit {

    private static final List<String> HEAD_KEYS = Arrays.asList("kind", "image");
    private static final List<String> WORKLOAD_LEVEL_KEYS =
            Arrays.asList(
                    "replicas",
                    "ports",
                    "env",
                    "probes",
                    "resources",
                    "schedule",
                    "condition",
                    "volumeClaim");

    private K8sRolloutImpactAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: K8sRolloutImpactAudit <dataDir> <outputDir>");
            System.exit(1);
        }
        run(Path.of(args[0]), Path.of(args[1]));
    }

    private static void run(Path dataDir, Path outDir) throws IOException {
        Files.createDirectories(outDir);

        Path baselinePath = dataDir.resolve("baseline-manifests.yml");
        Path currentPath = dataDir.resolve("current-manifests.yml");
        Path chartsPath = dataDir.resolve("charts.json");
        Path releasePath = dataDir.resolve("release.json");
        Path mapPath = dataDir.resolve("workload_dependency_map.json");

        DriftResult drift = buildDriftReport(baselinePath, currentPath);
        ResolverResult resolver = runResolver(chartsPath, releasePath, mapPath, drift.changedRefs);

        writeJson(outDir.resolve("manifest_drift.json"), drift.report);
        writeJson(outDir.resolve("chart_impact.json"), resolver.chartImpact);
        writeJson(outDir.resolve("rollout_plan.json"), resolver.rolloutPlan);
    }

    private static DriftResult buildDriftReport(Path baselinePath, Path currentPath)
            throws IOException {
        Map<WorkloadKey, WorkloadRecord> baselineMap =
                collectWorkloadMap(loadManifests(baselinePath));
        Map<WorkloadKey, WorkloadRecord> currentMap =
                collectWorkloadMap(loadManifests(currentPath));

        Set<WorkloadKey> baselineIds = baselineMap.keySet();
        Set<WorkloadKey> currentIds = currentMap.keySet();

        JsonArray added = new JsonArray();
        JsonArray removed = new JsonArray();
        JsonArray modified = new JsonArray();

        TreeSet<WorkloadKey> addedIds = new TreeSet<>(currentIds);
        addedIds.removeAll(baselineIds);
        for (WorkloadKey identity : addedIds) {
            WorkloadRecord record = currentMap.get(identity);
            JsonObject row = new JsonObject();
            row.addProperty("workload_name", record.workloadName);
            row.addProperty("namespace", record.namespace);
            row.add("spec", record.spec);
            added.add(row);
        }

        TreeSet<WorkloadKey> removedIds = new TreeSet<>(baselineIds);
        removedIds.removeAll(currentIds);
        for (WorkloadKey identity : removedIds) {
            WorkloadRecord record = baselineMap.get(identity);
            JsonObject row = new JsonObject();
            row.addProperty("workload_name", record.workloadName);
            row.addProperty("namespace", record.namespace);
            row.add("spec", record.spec);
            removed.add(row);
        }

        TreeSet<WorkloadKey> common = new TreeSet<>(baselineIds);
        common.retainAll(currentIds);
        for (WorkloadKey identity : common) {
            WorkloadRecord oldRecord = baselineMap.get(identity);
            WorkloadRecord newRecord = currentMap.get(identity);
            JsonObject oldSpec = oldRecord.spec;
            JsonObject newSpec = newRecord.spec;

            TreeSet<String> unionKeys = new TreeSet<>();
            for (Map.Entry<String, JsonElement> e : oldSpec.entrySet()) {
                unionKeys.add(e.getKey());
            }
            for (Map.Entry<String, JsonElement> e : newSpec.entrySet()) {
                unionKeys.add(e.getKey());
            }

            JsonObject changedFields = new JsonObject();
            for (String key : unionKeys) {
                JsonElement oldValue =
                        oldSpec.has(key) ? oldSpec.get(key) : JsonNull.INSTANCE;
                JsonElement newValue =
                        newSpec.has(key) ? newSpec.get(key) : JsonNull.INSTANCE;
                if (!jsonEquals(oldValue, newValue)) {
                    JsonObject change = new JsonObject();
                    change.add("old_value", oldValue);
                    change.add("new_value", newValue);
                    changedFields.add(key, change);
                }
            }
            if (changedFields.size() > 0) {
                JsonObject row = new JsonObject();
                row.addProperty("workload_name", oldRecord.workloadName);
                row.addProperty("namespace", oldRecord.namespace);
                row.add("changed_fields", changedFields);
                modified.add(row);
            }
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("added_workloads_count", added.size());
        summary.addProperty("removed_workloads_count", removed.size());
        summary.addProperty("modified_workloads_count", modified.size());

        JsonObject report = new JsonObject();
        report.addProperty("schema_version", 1);
        report.addProperty("baseline_sha256", sha256Hex(Files.readAllBytes(baselinePath)));
        report.addProperty("current_sha256", sha256Hex(Files.readAllBytes(currentPath)));
        report.add("summary", summary);
        report.add("added_workloads", added);
        report.add("removed_workloads", removed);
        report.add("modified_workloads", modified);

        TreeSet<String> changedRefs = new TreeSet<>();
        for (JsonElement el : added) {
            changedRefs.add(workloadRef(el.getAsJsonObject()));
        }
        for (JsonElement el : removed) {
            changedRefs.add(workloadRef(el.getAsJsonObject()));
        }
        for (JsonElement el : modified) {
            changedRefs.add(workloadRef(el.getAsJsonObject()));
        }

        return new DriftResult(report, new ArrayList<>(changedRefs));
    }

    private static String workloadRef(JsonObject row) {
        return row.get("namespace").getAsString() + "::" + row.get("workload_name").getAsString();
    }

    private static ResolverResult runResolver(
            Path chartsPath,
            Path releasePath,
            Path mapPath,
            List<String> changedRefs)
            throws IOException {
        JsonElement rawCharts = JsonParser.parseString(Files.readString(chartsPath, StandardCharsets.UTF_8));
        JsonObject rawRelease =
                JsonParser.parseString(Files.readString(releasePath, StandardCharsets.UTF_8))
                        .getAsJsonObject();
        JsonElement rawMap = JsonParser.parseString(Files.readString(mapPath, StandardCharsets.UTF_8));

        Map<ChartPair, List<ChartPair>> registry = new LinkedHashMap<>();
        Map<String, List<String>> versionsByName = new HashMap<>();

        if (rawCharts.isJsonArray()) {
            for (JsonElement item : rawCharts.getAsJsonArray()) {
                ChartEntry validated = validateChartEntry(item);
                if (validated == null) {
                    continue;
                }
                ChartPair key = new ChartPair(validated.name, validated.version);
                if (registry.containsKey(key)) {
                    continue;
                }
                registry.put(key, validated.requirements);
                versionsByName.computeIfAbsent(validated.name, k -> new ArrayList<>())
                        .add(validated.version);
            }
        }

        for (Map.Entry<String, List<String>> e : versionsByName.entrySet()) {
            List<String> versions = e.getValue();
            versions.sort(K8sRolloutImpactAudit::compareVersion);
            List<String> deduped = new ArrayList<>();
            Set<String> seen = new HashSet<>();
            for (String version : versions) {
                if (seen.add(version)) {
                    deduped.add(version);
                }
            }
            e.setValue(deduped);
        }

        String releaseName = "";
        List<ChartPair> releaseRequire = new ArrayList<>();
        Map<ChartPair, ChartPair> replaceMap = new LinkedHashMap<>();
        Set<ChartPair> excludeSet = new HashSet<>();

        if (rawRelease.has("name") && rawRelease.get("name").isJsonPrimitive()) {
            releaseName = rawRelease.get("name").getAsString();
        }
        if (rawRelease.has("require") && rawRelease.get("require").isJsonArray()) {
            for (JsonElement item : rawRelease.getAsJsonArray("require")) {
                ChartPair pair = validateReqPair(item);
                if (pair != null) {
                    releaseRequire.add(pair);
                }
            }
        }
        if (rawRelease.has("replace") && rawRelease.get("replace").isJsonArray()) {
            for (JsonElement item : rawRelease.getAsJsonArray("replace")) {
                if (!item.isJsonObject()) {
                    continue;
                }
                JsonObject obj = item.getAsJsonObject();
                ChartPair fromPair = validateReqPair(obj.get("from"));
                ChartPair toPair = validateReqPair(obj.get("to"));
                if (fromPair == null || toPair == null) {
                    continue;
                }
                replaceMap.putIfAbsent(fromPair, toPair);
            }
        }
        if (rawRelease.has("exclude") && rawRelease.get("exclude").isJsonArray()) {
            for (JsonElement item : rawRelease.getAsJsonArray("exclude")) {
                ChartPair pair = validateReqPair(item);
                if (pair != null) {
                    excludeSet.add(pair);
                }
            }
        }

        Set<String> conflicts = new TreeSet<>();

        ResolverContext ctx =
                new ResolverContext(
                        registry,
                        versionsByName,
                        replaceMap,
                        excludeSet,
                        conflicts);

        List<ChartPair> seedPairs = new ArrayList<>(releaseRequire);
        if (rawMap.isJsonObject()) {
            JsonObject mapObj = rawMap.getAsJsonObject();
            for (String ref : changedRefs) {
                if (!mapObj.has(ref) || !mapObj.get(ref).isJsonArray()) {
                    continue;
                }
                for (JsonElement item : mapObj.getAsJsonArray(ref)) {
                    ChartPair pair = validateReqPair(item);
                    if (pair != null) {
                        seedPairs.add(pair);
                    }
                }
            }
        }

        Map<String, String> selected = new LinkedHashMap<>();
        Set<String> missing = new TreeSet<>();

        for (ChartPair pair : seedPairs) {
            ChartPair resolved = ctx.resolvePair(pair.name, pair.version);
            if (resolved != null) {
                updateSelected(selected, resolved.name, resolved.version);
            }
        }

        while (true) {
            boolean changed = false;
            List<Map.Entry<String, String>> snapshot = new ArrayList<>(selected.entrySet());
            for (Map.Entry<String, String> entry : snapshot) {
                String name = entry.getKey();
                String version = entry.getValue();
                List<ChartPair> requirements = registry.get(new ChartPair(name, version));
                if (requirements == null) {
                    missing.add(formatPair(name, version));
                    continue;
                }
                for (ChartPair requirement : requirements) {
                    ChartPair resolved =
                            ctx.resolvePair(requirement.name, requirement.version);
                    if (resolved != null && updateSelected(selected, resolved.name, resolved.version)) {
                        changed = true;
                    }
                }
            }
            if (!changed) {
                break;
            }
        }

        Map<String, String> buildVersions = new LinkedHashMap<>();
        for (Map.Entry<String, String> entry : selected.entrySet()) {
            String name = entry.getKey();
            String version = entry.getValue();
            if (name.equals(releaseName)) {
                continue;
            }
            if (registry.containsKey(new ChartPair(name, version))) {
                buildVersions.put(name, version);
            }
        }
        Set<String> buildSet = buildVersions.keySet();

        Map<String, List<String>> dependencyEdges = new TreeMap<>();
        for (String name : new TreeSet<>(buildSet)) {
            Set<String> edges = new TreeSet<>();
            List<ChartPair> requirements =
                    registry.get(new ChartPair(name, buildVersions.get(name)));
            for (ChartPair requirement : requirements) {
                ChartPair resolved =
                        ctx.resolvePair(requirement.name, requirement.version);
                if (resolved != null && buildSet.contains(resolved.name)) {
                    edges.add(resolved.name);
                }
            }
            dependencyEdges.put(name, new ArrayList<>(edges));
        }

        TarjanResult tarjan = runTarjan(buildSet, dependencyEdges);
        List<List<String>> cycles = tarjan.cycles;
        List<List<String>> buildOrder = tarjan.buildOrder;

        Map<String, Set<String>> workloadToSeedCharts = new HashMap<>();
        Set<SeedRow> seedRowsSet = new TreeSet<>();
        if (rawMap.isJsonObject()) {
            JsonObject mapObj = rawMap.getAsJsonObject();
            for (String ref : changedRefs) {
                if (!mapObj.has(ref) || !mapObj.get(ref).isJsonArray()) {
                    continue;
                }
                for (JsonElement item : mapObj.getAsJsonArray(ref)) {
                    ChartPair pair = validateReqPair(item);
                    if (pair == null) {
                        continue;
                    }
                    ChartPair resolved = ctx.resolvePair(pair.name, pair.version);
                    if (resolved == null) {
                        continue;
                    }
                    String chartName = resolved.name;
                    String selectedVersion = buildVersions.get(chartName);
                    if (selectedVersion == null) {
                        continue;
                    }
                    workloadToSeedCharts
                            .computeIfAbsent(ref, k -> new HashSet<>())
                            .add(chartName);
                    seedRowsSet.add(new SeedRow(ref, chartName, selectedVersion));
                }
            }
        }

        Map<String, Set<String>> chartTriggeredBy = new TreeMap<>();
        Set<String> impactedSet = new TreeSet<>();
        for (Map.Entry<String, Set<String>> e : workloadToSeedCharts.entrySet()) {
            String workloadRef = e.getKey();
            Set<String> reached = new HashSet<>();
            for (String seed : e.getValue()) {
                reached.addAll(reachableFromSeed(seed, dependencyEdges));
            }
            for (String chart : reached) {
                chartTriggeredBy.computeIfAbsent(chart, k -> new TreeSet<>()).add(workloadRef);
            }
            impactedSet.addAll(reached);
        }

        JsonArray seedRows = new JsonArray();
        for (SeedRow row : seedRowsSet) {
            JsonObject obj = new JsonObject();
            obj.addProperty("workload_ref", row.workloadRef);
            obj.addProperty("chart", row.chart);
            obj.addProperty("version", row.version);
            seedRows.add(obj);
        }

        JsonArray impactedCharts = new JsonArray();
        for (String chart : impactedSet) {
            JsonObject obj = new JsonObject();
            obj.addProperty("name", chart);
            obj.addProperty("version", buildVersions.get(chart));
            JsonArray triggers = new JsonArray();
            for (String ref : chartTriggeredBy.get(chart)) {
                triggers.add(ref);
            }
            obj.add("triggered_by", triggers);
            impactedCharts.add(obj);
        }

        JsonArray cyclesJson = new JsonArray();
        for (List<String> cycle : cycles) {
            JsonArray arr = new JsonArray();
            for (String member : cycle) {
                arr.add(member);
            }
            cyclesJson.add(arr);
        }

        JsonArray buildOrderJson = new JsonArray();
        for (List<String> step : buildOrder) {
            JsonArray arr = new JsonArray();
            for (String member : step) {
                arr.add(member);
            }
            buildOrderJson.add(arr);
        }

        JsonArray rolloutSteps = new JsonArray();
        int stepIndex = 1;
        for (List<String> step : buildOrder) {
            List<String> filtered = new ArrayList<>();
            for (String chart : step) {
                if (impactedSet.contains(chart)) {
                    filtered.add(chart);
                }
            }
            if (filtered.isEmpty()) {
                continue;
            }
            TreeSet<String> triggers = new TreeSet<>();
            for (String chart : filtered) {
                triggers.addAll(chartTriggeredBy.get(chart));
            }
            JsonObject stepObj = new JsonObject();
            stepObj.addProperty("step", stepIndex);
            JsonArray chartsArr = new JsonArray();
            for (String chart : filtered) {
                chartsArr.add(chart);
            }
            stepObj.add("charts", chartsArr);
            JsonArray triggersArr = new JsonArray();
            for (String ref : triggers) {
                triggersArr.add(ref);
            }
            stepObj.add("triggered_by", triggersArr);
            rolloutSteps.add(stepObj);
            stepIndex++;
        }

        JsonObject resolverSummary = new JsonObject();
        resolverSummary.addProperty("selected_total", buildVersions.size());
        JsonArray missingArr = new JsonArray();
        for (String m : missing) {
            missingArr.add(m);
        }
        resolverSummary.add("missing", missingArr);
        JsonArray conflictsArr = new JsonArray();
        for (String c : conflicts) {
            conflictsArr.add(c);
        }
        resolverSummary.add("conflicts", conflictsArr);
        resolverSummary.addProperty("cycle_group_count", cycles.size());

        JsonObject chartImpact = new JsonObject();
        chartImpact.add("resolver_summary", resolverSummary);
        chartImpact.add("seed_modules", seedRows);
        chartImpact.add("impacted_charts", impactedCharts);
        chartImpact.add("cycles", cyclesJson);
        chartImpact.add("build_order", buildOrderJson);

        JsonObject rolloutPlan = new JsonObject();
        rolloutPlan.add("steps", rolloutSteps);

        return new ResolverResult(chartImpact, rolloutPlan);
    }

    private static Set<String> reachableFromSeed(
            String seedChart, Map<String, List<String>> dependencyEdges) {
        Set<String> seen = new HashSet<>();
        List<String> stack = new ArrayList<>();
        stack.add(seedChart);
        while (!stack.isEmpty()) {
            String chart = stack.remove(stack.size() - 1);
            if (!seen.add(chart)) {
                continue;
            }
            List<String> deps = dependencyEdges.get(chart);
            if (deps != null) {
                for (String dep : deps) {
                    if (!seen.contains(dep)) {
                        stack.add(dep);
                    }
                }
            }
        }
        return seen;
    }

    private static TarjanResult runTarjan(
            Set<String> buildSet, Map<String, List<String>> dependencyEdges) {
        Map<String, Integer> index = new HashMap<>();
        Map<String, Integer> lowlink = new HashMap<>();
        List<String> stack = new ArrayList<>();
        Set<String> onStack = new HashSet<>();
        int[] currentIndex = {0};
        List<List<String>> sccs = new ArrayList<>();
        Map<String, Integer> nodeToScc = new HashMap<>();

        class StrongConnect {
            void visit(String node) {
                index.put(node, currentIndex[0]);
                lowlink.put(node, currentIndex[0]);
                currentIndex[0]++;
                stack.add(node);
                onStack.add(node);

                for (String neighbor : dependencyEdges.get(node)) {
                    if (!index.containsKey(neighbor)) {
                        visit(neighbor);
                        lowlink.put(node, Math.min(lowlink.get(node), lowlink.get(neighbor)));
                    } else if (onStack.contains(neighbor)) {
                        lowlink.put(node, Math.min(lowlink.get(node), index.get(neighbor)));
                    }
                }

                if (lowlink.get(node).equals(index.get(node))) {
                    List<String> component = new ArrayList<>();
                    while (true) {
                        String member = stack.remove(stack.size() - 1);
                        onStack.remove(member);
                        component.add(member);
                        if (member.equals(node)) {
                            break;
                        }
                    }
                    int sccId = sccs.size();
                    for (String member : component) {
                        nodeToScc.put(member, sccId);
                    }
                    sccs.add(component);
                }
            }
        }

        StrongConnect sc = new StrongConnect();
        for (String node : new TreeSet<>(buildSet)) {
            if (!index.containsKey(node)) {
                sc.visit(node);
            }
        }

        List<List<String>> cycles = new ArrayList<>();
        for (List<String> component : sccs) {
            List<String> members = new ArrayList<>(component);
            members.sort(String::compareTo);
            if (members.size() > 1) {
                cycles.add(members);
            } else if (!members.isEmpty()) {
                String only = members.get(0);
                List<String> deps = dependencyEdges.get(only);
                if (deps != null && deps.contains(only)) {
                    cycles.add(members);
                }
            }
        }
        cycles.sort(Comparator.comparing(c -> c.isEmpty() ? "" : c.get(0)));

        Map<Integer, List<String>> sccMembers = new HashMap<>();
        Map<Integer, String> sccMinName = new HashMap<>();
        for (int idx = 0; idx < sccs.size(); idx++) {
            List<String> sorted = new ArrayList<>(sccs.get(idx));
            sorted.sort(String::compareTo);
            sccMembers.put(idx, sorted);
            sccMinName.put(idx, sorted.isEmpty() ? "~" : sorted.get(0));
        }

        Map<Integer, Set<Integer>> condensationEdges = new HashMap<>();
        Map<Integer, Integer> indegree = new HashMap<>();
        for (int idx = 0; idx < sccs.size(); idx++) {
            condensationEdges.put(idx, new HashSet<>());
            indegree.put(idx, 0);
        }

        for (Map.Entry<String, List<String>> e : dependencyEdges.entrySet()) {
            String chart = e.getKey();
            int chartScc = nodeToScc.get(chart);
            for (String dep : e.getValue()) {
                int depScc = nodeToScc.get(dep);
                if (depScc == chartScc) {
                    continue;
                }
                Set<Integer> edges = condensationEdges.get(depScc);
                if (!edges.contains(chartScc)) {
                    edges.add(chartScc);
                    indegree.put(chartScc, indegree.get(chartScc) + 1);
                }
            }
        }

        List<Integer> ready = new ArrayList<>();
        for (Map.Entry<Integer, Integer> e : indegree.entrySet()) {
            if (e.getValue() == 0) {
                ready.add(e.getKey());
            }
        }
        ready.sort(
                Comparator.comparing((Integer sid) -> sccMinName.get(sid))
                        .thenComparingInt(sid -> sid));

        List<List<String>> buildOrder = new ArrayList<>();
        while (!ready.isEmpty()) {
            int sid = ready.remove(0);
            buildOrder.add(new ArrayList<>(sccMembers.get(sid)));
            List<Integer> nexts = new ArrayList<>(condensationEdges.get(sid));
            nexts.sort(
                    Comparator.comparing((Integer nid) -> sccMinName.get(nid))
                            .thenComparingInt(nid -> nid));
            for (int nxt : nexts) {
                int deg = indegree.get(nxt) - 1;
                indegree.put(nxt, deg);
                if (deg == 0) {
                    ready.add(nxt);
                }
            }
            ready.sort(
                    Comparator.comparing((Integer nid) -> sccMinName.get(nid))
                            .thenComparingInt(nid -> nid));
        }

        if (buildOrder.size() < sccs.size()) {
            Set<List<String>> emitted = new HashSet<>();
            for (List<String> step : buildOrder) {
                emitted.add(step);
            }
            List<List<String>> remaining = new ArrayList<>();
            for (List<String> members : sccMembers.values()) {
                if (!emitted.contains(members)) {
                    remaining.add(members);
                }
            }
            remaining.sort(
                    Comparator.comparing(m -> m.isEmpty() ? "~" : m.get(0)));
            buildOrder.addAll(remaining);
        }

        return new TarjanResult(cycles, buildOrder);
    }

    private static boolean updateSelected(
            Map<String, String> selected, String name, String version) {
        if (parseVersion(version) == null) {
            return false;
        }
        String existing = selected.get(name);
        if (existing == null || compareVersion(version, existing) > 0) {
            selected.put(name, version);
            return true;
        }
        return false;
    }

    private static Map<WorkloadKey, WorkloadRecord> collectWorkloadMap(List<Map<String, Object>> groups) {
        Map<WorkloadKey, WorkloadRecord> records = new LinkedHashMap<>();
        for (Map<String, Object> group : groups) {
            String namespace = normalizeNamespace(group);
            Object manifestsRaw = group.get("manifests");
            if (!(manifestsRaw instanceof List<?> manifests)) {
                continue;
            }
            for (Object manifestObj : manifests) {
                if (!(manifestObj instanceof Map<?, ?> manifestMap)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> manifest = (Map<String, Object>) manifestMap;
                WorkloadRecord record = extractWorkloadRecord(manifest, namespace);
                if (record == null) {
                    continue;
                }
                WorkloadKey identity =
                        new WorkloadKey(record.workloadName, record.namespace);
                records.putIfAbsent(identity, record);
            }
        }
        return records;
    }

    private static WorkloadRecord extractWorkloadRecord(
            Map<String, Object> manifest, String namespace) {
        Object rawName = manifest.get("name");
        String workloadName;
        if (rawName instanceof String nameStr && !nameStr.strip().isEmpty()) {
            workloadName = nameStr.strip();
        } else {
            Object rawImage = manifest.get("image");
            if (rawImage instanceof String imageStr && !imageStr.isEmpty()) {
                workloadName = imageStr;
            } else {
                return null;
            }
        }

        JsonObject spec = new JsonObject();
        for (String key : HEAD_KEYS) {
            if (manifest.containsKey(key)) {
                spec.add(key, toJsonElement(manifest.get(key)));
            }
        }
        for (String key : WORKLOAD_LEVEL_KEYS) {
            if (manifest.containsKey(key)) {
                spec.add(key, toJsonElement(manifest.get(key)));
            }
        }

        return new WorkloadRecord(workloadName, namespace, spec);
    }

    private static String normalizeNamespace(Map<String, Object> group) {
        Object raw = group.get("namespace");
        if (raw instanceof String ns && !ns.strip().isEmpty()) {
            return ns.strip();
        }
        return "default";
    }

    @SuppressWarnings("unchecked")
    private static List<Map<String, Object>> loadManifests(Path path) throws IOException {
        Yaml yaml = new Yaml();
        Object parsed = yaml.load(Files.readString(path, StandardCharsets.UTF_8));
        if (!(parsed instanceof List<?> list)) {
            return List.of();
        }
        List<Map<String, Object>> groups = new ArrayList<>();
        for (Object item : list) {
            if (item instanceof Map<?, ?> map) {
                groups.add((Map<String, Object>) map);
            }
        }
        return groups;
    }

    private static ChartPair validateReqPair(JsonElement raw) {
        if (raw == null || !raw.isJsonObject()) {
            return null;
        }
        JsonObject obj = raw.getAsJsonObject();
        String name = jsonString(obj, "name");
        String version = jsonString(obj, "version");
        if (name == null || name.isEmpty() || version == null || version.isEmpty()) {
            return null;
        }
        if (parseVersion(version) == null) {
            return null;
        }
        return new ChartPair(name, version);
    }

    private static ChartEntry validateChartEntry(JsonElement raw) {
        if (raw == null || !raw.isJsonObject()) {
            return null;
        }
        JsonObject obj = raw.getAsJsonObject();
        String name = jsonString(obj, "name");
        String version = jsonString(obj, "version");
        if (name == null || name.isEmpty() || version == null || version.isEmpty()) {
            return null;
        }
        if (parseVersion(version) == null) {
            return null;
        }
        List<ChartPair> requirements = new ArrayList<>();
        if (obj.has("require") && obj.get("require").isJsonArray()) {
            for (JsonElement item : obj.getAsJsonArray("require")) {
                ChartPair child = validateReqPair(item);
                if (child != null) {
                    requirements.add(child);
                }
            }
        }
        return new ChartEntry(name, version, requirements);
    }

    private static String jsonString(JsonObject obj, String key) {
        if (!obj.has(key) || obj.get(key).isJsonNull() || !obj.get(key).isJsonPrimitive()) {
            return null;
        }
        return obj.get(key).getAsString();
    }

    private static int[] parseVersion(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        String[] parts = value.split("\\.");
        if (parts.length != 3) {
            return null;
        }
        int[] triple = new int[3];
        try {
            for (int i = 0; i < 3; i++) {
                triple[i] = Integer.parseInt(parts[i]);
                if (triple[i] < 0) {
                    return null;
                }
            }
        } catch (NumberFormatException e) {
            return null;
        }
        return triple;
    }

    private static int compareVersion(String a, String b) {
        int[] pa = parseVersion(a);
        int[] pb = parseVersion(b);
        if (pa == null || pb == null) {
            throw new IllegalArgumentException("Invalid semver comparison");
        }
        for (int i = 0; i < 3; i++) {
            if (pa[i] < pb[i]) {
                return -1;
            }
            if (pa[i] > pb[i]) {
                return 1;
            }
        }
        return 0;
    }

    private static String formatPair(String name, String version) {
        return name + "@" + version;
    }

    private static boolean jsonEquals(JsonElement a, JsonElement b) {
        if (a == null || a.isJsonNull()) {
            return b == null || b.isJsonNull();
        }
        return a.equals(b);
    }

    private static JsonElement toJsonElement(Object value) {
        if (value == null) {
            return JsonNull.INSTANCE;
        }
        if (value instanceof String s) {
            return new JsonPrimitive(s);
        }
        if (value instanceof Boolean b) {
            return new JsonPrimitive(b);
        }
        if (value instanceof Integer i) {
            return new JsonPrimitive(i);
        }
        if (value instanceof Long l) {
            return new JsonPrimitive(l);
        }
        if (value instanceof Double d) {
            return new JsonPrimitive(d);
        }
        if (value instanceof Float f) {
            return new JsonPrimitive(f);
        }
        if (value instanceof Map<?, ?> map) {
            JsonObject obj = new JsonObject();
            for (Map.Entry<?, ?> e : map.entrySet()) {
                obj.add(String.valueOf(e.getKey()), toJsonElement(e.getValue()));
            }
            return obj;
        }
        if (value instanceof List<?> list) {
            JsonArray arr = new JsonArray();
            for (Object item : list) {
                arr.add(toJsonElement(item));
            }
            return arr;
        }
        return new JsonPrimitive(String.valueOf(value));
    }

    private static String sha256Hex(byte[] data) {
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            byte[] digest = md.digest(data);
            StringBuilder sb = new StringBuilder();
            for (byte b : digest) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException(e);
        }
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        String text = gson.toJson(root) + "\n";
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static final class ResolverContext {
        final Map<ChartPair, List<ChartPair>> registry;
        final Map<String, List<String>> versionsByName;
        final Map<ChartPair, ChartPair> replaceMap;
        final Set<ChartPair> excludeSet;
        final Set<String> conflicts;

        ResolverContext(
                Map<ChartPair, List<ChartPair>> registry,
                Map<String, List<String>> versionsByName,
                Map<ChartPair, ChartPair> replaceMap,
                Set<ChartPair> excludeSet,
                Set<String> conflicts) {
            this.registry = registry;
            this.versionsByName = versionsByName;
            this.replaceMap = replaceMap;
            this.excludeSet = excludeSet;
            this.conflicts = conflicts;
        }

        ChartPair resolvePair(String name, String version) {
            ChartPair replaced = replaceMap.get(new ChartPair(name, version));
            String currentName;
            String currentVersion;
            if (replaced != null) {
                currentName = replaced.name;
                currentVersion = replaced.version;
            } else {
                currentName = name;
                currentVersion = version;
            }

            if (excludeSet.contains(new ChartPair(currentName, currentVersion))) {
                String candidate = null;
                for (String availableVersion : versionsByName.getOrDefault(currentName, List.of())) {
                    if (compareVersion(availableVersion, currentVersion) <= 0) {
                        continue;
                    }
                    if (excludeSet.contains(new ChartPair(currentName, availableVersion))) {
                        continue;
                    }
                    candidate = availableVersion;
                    break;
                }
                if (candidate == null) {
                    conflicts.add(formatPair(currentName, currentVersion));
                    return null;
                }
                currentVersion = candidate;
            }

            return new ChartPair(currentName, currentVersion);
        }
    }

    private static final class ChartPair {
        final String name;
        final String version;

        ChartPair(String name, String version) {
            this.name = name;
            this.version = version;
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof ChartPair other)) {
                return false;
            }
            return name.equals(other.name) && version.equals(other.version);
        }

        @Override
        public int hashCode() {
            return name.hashCode() * 31 + version.hashCode();
        }
    }

    private static final class ChartEntry {
        final String name;
        final String version;
        final List<ChartPair> requirements;

        ChartEntry(String name, String version, List<ChartPair> requirements) {
            this.name = name;
            this.version = version;
            this.requirements = requirements;
        }
    }

    private static final class WorkloadKey implements Comparable<WorkloadKey> {
        final String workloadName;
        final String namespace;

        WorkloadKey(String workloadName, String namespace) {
            this.workloadName = workloadName;
            this.namespace = namespace;
        }

        @Override
        public int compareTo(WorkloadKey o) {
            int c = workloadName.compareTo(o.workloadName);
            return c != 0 ? c : namespace.compareTo(o.namespace);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof WorkloadKey other)) {
                return false;
            }
            return workloadName.equals(other.workloadName) && namespace.equals(other.namespace);
        }

        @Override
        public int hashCode() {
            return workloadName.hashCode() * 31 + namespace.hashCode();
        }
    }

    private static final class WorkloadRecord {
        final String workloadName;
        final String namespace;
        final JsonObject spec;

        WorkloadRecord(String workloadName, String namespace, JsonObject spec) {
            this.workloadName = workloadName;
            this.namespace = namespace;
            this.spec = spec;
        }
    }

    private static final class SeedRow implements Comparable<SeedRow> {
        final String workloadRef;
        final String chart;
        final String version;

        SeedRow(String workloadRef, String chart, String version) {
            this.workloadRef = workloadRef;
            this.chart = chart;
            this.version = version;
        }

        @Override
        public int compareTo(SeedRow o) {
            int c = workloadRef.compareTo(o.workloadRef);
            if (c != 0) {
                return c;
            }
            c = chart.compareTo(o.chart);
            return c != 0 ? c : version.compareTo(o.version);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof SeedRow other)) {
                return false;
            }
            return workloadRef.equals(other.workloadRef)
                    && chart.equals(other.chart)
                    && version.equals(other.version);
        }

        @Override
        public int hashCode() {
            int h = workloadRef.hashCode();
            h = 31 * h + chart.hashCode();
            h = 31 * h + version.hashCode();
            return h;
        }
    }

    private static final class DriftResult {
        final JsonObject report;
        final List<String> changedRefs;

        DriftResult(JsonObject report, List<String> changedRefs) {
            this.report = report;
            this.changedRefs = changedRefs;
        }
    }

    private static final class ResolverResult {
        final JsonObject chartImpact;
        final JsonObject rolloutPlan;

        ResolverResult(JsonObject chartImpact, JsonObject rolloutPlan) {
            this.chartImpact = chartImpact;
            this.rolloutPlan = rolloutPlan;
        }
    }

    private static final class TarjanResult {
        final List<List<String>> cycles;
        final List<List<String>> buildOrder;

        TarjanResult(List<List<String>> cycles, List<List<String>> buildOrder) {
            this.cycles = cycles;
            this.buildOrder = buildOrder;
        }
    }
}
