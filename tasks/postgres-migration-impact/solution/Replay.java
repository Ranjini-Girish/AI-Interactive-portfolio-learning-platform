import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonNull;
import com.google.gson.JsonParser;
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

/** Postgres migration impact oracle. */
public final class Replay {

    private static final Set<String> ALLOWED_KINDS =
            new TreeSet<>(
                    Arrays.asList("table", "view", "index", "function", "policy"));
    private static final List<String> ATTR_KEYS =
            Arrays.asList(
                    "kind", "version", "lock_class", "columns", "constraints", "depends_on");

    private Replay() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        run(Path.of(args[0]), Path.of(args[1]));
    }

    private static void run(Path dataDir, Path outDir) throws IOException {
        Files.createDirectories(outDir);

        Path baselinePath = dataDir.resolve("baseline-schema.json");
        Path currentPath = dataDir.resolve("current-schema.json");
        Path policyPath = dataDir.resolve("policy.json");
        Path queryMapPath = dataDir.resolve("query_object_map.json");

        SchemaIndex baselineIndex = loadSchemaIndex(baselinePath);
        SchemaIndex currentIndex = loadSchemaIndex(currentPath);

        DriftLists drift = buildDrift(baselineIndex.index, currentIndex.index);
        Set<String> changedSet = buildChangedFqnSet(drift);

        JsonObject driftPayload = new JsonObject();
        driftPayload.addProperty("schema_version", 1);
        driftPayload.addProperty("baseline_sha256", baselineIndex.sha256);
        driftPayload.addProperty("current_sha256", currentIndex.sha256);
        JsonObject summary = new JsonObject();
        summary.addProperty("added_count", drift.added.size());
        summary.addProperty("removed_count", drift.removed.size());
        summary.addProperty("modified_count", drift.modified.size());
        driftPayload.add("summary", summary);
        driftPayload.add("added", drift.added);
        driftPayload.add("removed", drift.removed);
        driftPayload.add("modified", drift.modified);

        JsonObject policyRaw = loadJsonObject(policyPath);
        JsonObject queryMapRaw = loadJsonObject(queryMapPath);

        List<Ref> requirePairs = new ArrayList<>();
        if (policyRaw.has("require") && policyRaw.get("require").isJsonArray()) {
            for (JsonElement el : policyRaw.getAsJsonArray("require")) {
                Ref ref = validateRef(el);
                if (ref != null) {
                    requirePairs.add(ref);
                }
            }
        }

        Map<Ref, Ref> replaceMap = new LinkedHashMap<>();
        if (policyRaw.has("replace") && policyRaw.get("replace").isJsonArray()) {
            for (JsonElement el : policyRaw.getAsJsonArray("replace")) {
                if (!el.isJsonObject()) {
                    continue;
                }
                JsonObject item = el.getAsJsonObject();
                Ref fromRef = validateRef(item.get("from"));
                Ref toRef = validateRef(item.get("to"));
                if (fromRef == null || toRef == null) {
                    continue;
                }
                replaceMap.putIfAbsent(fromRef, toRef);
            }
        }

        Set<Ref> excludeSet = new HashSet<>();
        if (policyRaw.has("exclude") && policyRaw.get("exclude").isJsonArray()) {
            for (JsonElement el : policyRaw.getAsJsonArray("exclude")) {
                Ref ref = validateRef(el);
                if (ref != null) {
                    excludeSet.add(ref);
                }
            }
        }

        Map<String, Integer> severityMap = new HashMap<>();
        if (policyRaw.has("lock_class_severity")
                && policyRaw.get("lock_class_severity").isJsonArray()) {
            for (JsonElement el : policyRaw.getAsJsonArray("lock_class_severity")) {
                if (!el.isJsonObject()) {
                    continue;
                }
                JsonObject item = el.getAsJsonObject();
                if (item.has("name")
                        && item.get("name").isJsonPrimitive()
                        && item.has("rank")
                        && item.get("rank").isJsonPrimitive()) {
                    String n = item.get("name").getAsString();
                    int r = item.get("rank").getAsInt();
                    severityMap.putIfAbsent(n, r);
                }
            }
        }

        List<WindowEntry> windows = new ArrayList<>();
        if (policyRaw.has("allowed_migration_windows")
                && policyRaw.get("allowed_migration_windows").isJsonArray()) {
            for (JsonElement el : policyRaw.getAsJsonArray("allowed_migration_windows")) {
                if (!el.isJsonObject()) {
                    continue;
                }
                JsonObject item = el.getAsJsonObject();
                if (item.has("name")
                        && item.get("name").isJsonPrimitive()
                        && item.has("min_lock_rank")
                        && item.get("min_lock_rank").isJsonPrimitive()) {
                    windows.add(
                            new WindowEntry(
                                    item.get("min_lock_rank").getAsInt(),
                                    item.get("name").getAsString()));
                }
            }
        }

        Map<String, List<Ref>> queries = new TreeMap<>();
        if (queryMapRaw.has("queries") && queryMapRaw.get("queries").isJsonObject()) {
            JsonObject queriesRaw = queryMapRaw.getAsJsonObject("queries");
            for (Map.Entry<String, JsonElement> e : queriesRaw.entrySet()) {
                String qid = e.getKey();
                if (qid.isEmpty()) {
                    continue;
                }
                if (!e.getValue().isJsonArray()) {
                    continue;
                }
                List<Ref> valid = new ArrayList<>();
                for (JsonElement item : e.getValue().getAsJsonArray()) {
                    Ref ref = validateRef(item);
                    if (ref != null) {
                        valid.add(ref);
                    }
                }
                queries.put(qid, valid);
            }
        }

        List<String> triggeredQueries = new ArrayList<>();
        for (String qid : queries.keySet()) {
            for (Ref ref : queries.get(qid)) {
                if (changedSet.contains(fqn(ref.schema, ref.name))) {
                    triggeredQueries.add(qid);
                    break;
                }
            }
        }

        Map<Ident, SchemaRecord> registryIndex = currentIndex.index;
        Set<Ident> registryKeys = new HashSet<>();
        for (SchemaRecord rec : registryIndex.values()) {
            registryKeys.add(new Ident(rec.schema, rec.name));
        }

        Map<Ident, SchemaRecord> selected = new LinkedHashMap<>();
        Set<String> missing = new TreeSet<>();
        Set<String> conflicts = new TreeSet<>();
        List<JsonObject> seedRows = new ArrayList<>();
        Set<String> seenSeedRows = new HashSet<>();

        for (Ref ref : requirePairs) {
            Ident post = resolveSeed(ref, replaceMap, excludeSet, registryKeys, missing, conflicts);
            if (post != null) {
                addToSelected(post, selected, registryIndex);
            }
        }

        for (String qid : triggeredQueries) {
            for (Ref ref : queries.get(qid)) {
                Ident post =
                        resolveSeed(ref, replaceMap, excludeSet, registryKeys, missing, conflicts);
                if (post == null) {
                    continue;
                }
                addToSelected(post, selected, registryIndex);
                SchemaRecord rec = registryIndex.get(post);
                String rowKey = qid + "\0" + fqn(post.schema, post.name) + "\0" + rec.version;
                if (!seenSeedRows.contains(rowKey)) {
                    seenSeedRows.add(rowKey);
                    JsonObject row = new JsonObject();
                    row.addProperty("query_id", qid);
                    row.addProperty("object", fqn(post.schema, post.name));
                    row.addProperty("version", rec.version);
                    seedRows.add(row);
                }
            }
        }

        boolean changedFlag;
        do {
            changedFlag = false;
            List<Ident> selectedKeys = new ArrayList<>(selected.keySet());
            for (Ident ident : selectedKeys) {
                SchemaRecord rec = selected.get(ident);
                for (Ref dep : normalizedDependsOn(rec.dependsOnRaw)) {
                    Ident depId = new Ident(dep.schema, dep.name);
                    if (excludeSet.contains(dep)) {
                        continue;
                    }
                    if (!registryKeys.contains(depId)) {
                        missing.add(fqn(dep.schema, dep.name));
                        continue;
                    }
                    if (!selected.containsKey(depId)) {
                        addToSelected(depId, selected, registryIndex);
                        changedFlag = true;
                    }
                }
            }
        } while (changedFlag);

        JsonObject curDoc = loadJsonObject(currentPath);
        Ident rootId = null;
        if (curDoc.has("root") && curDoc.get("root").isJsonObject()) {
            JsonObject rootObj = curDoc.getAsJsonObject("root");
            if (rootObj.has("schema")
                    && rootObj.get("schema").isJsonPrimitive()
                    && rootObj.has("name")
                    && rootObj.get("name").isJsonPrimitive()) {
                rootId =
                        new Ident(
                                rootObj.get("schema").getAsString().toLowerCase(),
                                rootObj.get("name").getAsString().toLowerCase());
            }
        }

        Map<Ident, SchemaRecord> buildSet = new LinkedHashMap<>();
        for (Map.Entry<Ident, SchemaRecord> e : selected.entrySet()) {
            if (rootId != null && e.getKey().equals(rootId)) {
                continue;
            }
            buildSet.put(e.getKey(), e.getValue());
        }

        Map<Ident, List<Ident>> edges = new TreeMap<>();
        for (Map.Entry<Ident, SchemaRecord> e : buildSet.entrySet()) {
            Set<Ident> out = new TreeSet<>();
            for (Ref dep : normalizedDependsOn(e.getValue().dependsOnRaw)) {
                Ident depId = new Ident(dep.schema, dep.name);
                if (buildSet.containsKey(depId)) {
                    out.add(depId);
                }
            }
            edges.put(e.getKey(), new ArrayList<>(out));
        }

        List<Ident> sortedNodes = new ArrayList<>(buildSet.keySet());
        sortedNodes.sort(Ident::compareTo);

        Map<Ident, Integer> indexMap = new HashMap<>();
        Map<Ident, Integer> lowlink = new HashMap<>();
        Set<Ident> onStack = new HashSet<>();
        List<Ident> stack = new ArrayList<>();
        List<List<Ident>> sccs = new ArrayList<>();
        int[] counter = {0};

        for (Ident v : sortedNodes) {
            if (!indexMap.containsKey(v)) {
                strongConnect(v, edges, indexMap, lowlink, onStack, stack, sccs, counter);
            }
        }

        Map<Ident, Integer> nodeToScc = new HashMap<>();
        List<List<Ident>> sccMembersSorted = new ArrayList<>();
        for (int sid = 0; sid < sccs.size(); sid++) {
            List<Ident> comp = sccs.get(sid);
            List<Ident> sortedComp = new ArrayList<>(comp);
            sortedComp.sort(Ident::compareTo);
            sccMembersSorted.add(sortedComp);
            for (Ident member : comp) {
                nodeToScc.put(member, sid);
            }
        }

        List<List<String>> cyclesFqn = new ArrayList<>();
        for (int sid = 0; sid < sccMembersSorted.size(); sid++) {
            List<Ident> members = sccMembersSorted.get(sid);
            boolean isCycle = false;
            if (members.size() > 1) {
                isCycle = true;
            } else if (members.size() == 1) {
                Ident m = members.get(0);
                List<Ident> mEdges = edges.get(m);
                if (mEdges != null && mEdges.contains(m)) {
                    isCycle = true;
                }
            }
            if (isCycle) {
                List<String> group = new ArrayList<>();
                for (Ident m : members) {
                    group.add(fqn(m.schema, m.name));
                }
                cyclesFqn.add(group);
            }
        }
        cyclesFqn.sort(Comparator.comparing(g -> g.isEmpty() ? "" : g.get(0)));

        Map<Integer, String> sccMinFqn = new HashMap<>();
        for (int sid = 0; sid < sccMembersSorted.size(); sid++) {
            List<Ident> members = sccMembersSorted.get(sid);
            sccMinFqn.put(sid, fqn(members.get(0).schema, members.get(0).name));
        }

        Map<Integer, Set<Integer>> sccDeps = new HashMap<>();
        for (int sid = 0; sid < sccMembersSorted.size(); sid++) {
            sccDeps.put(sid, new HashSet<>());
        }
        for (Map.Entry<Ident, List<Ident>> e : edges.entrySet()) {
            int sv = nodeToScc.get(e.getKey());
            for (Ident w : e.getValue()) {
                int sw = nodeToScc.get(w);
                if (sw != sv) {
                    sccDeps.get(sv).add(sw);
                }
            }
        }

        Map<Integer, Set<Integer>> remainingDeps = new HashMap<>();
        for (Map.Entry<Integer, Set<Integer>> e : sccDeps.entrySet()) {
            remainingDeps.put(e.getKey(), new HashSet<>(e.getValue()));
        }
        Set<Integer> emitted = new HashSet<>();
        List<List<String>> buildOrder = new ArrayList<>();

        while (true) {
            List<Integer> ready = new ArrayList<>();
            for (Map.Entry<Integer, Set<Integer>> e : remainingDeps.entrySet()) {
                int sid = e.getKey();
                if (!emitted.contains(sid) && e.getValue().isEmpty()) {
                    ready.add(sid);
                }
            }
            ready.sort(Comparator.comparing(sccMinFqn::get));
            if (ready.isEmpty()) {
                break;
            }
            int chosen = ready.get(0);
            List<Ident> members = sccMembersSorted.get(chosen);
            List<String> step = new ArrayList<>();
            for (Ident m : members) {
                step.add(fqn(m.schema, m.name));
            }
            buildOrder.add(step);
            emitted.add(chosen);
            for (Set<Integer> deps : remainingDeps.values()) {
                deps.remove(chosen);
            }
        }

        if (buildOrder.size() != sccMembersSorted.size()) {
            List<Integer> leftoverIds = new ArrayList<>();
            for (int sid = 0; sid < sccMembersSorted.size(); sid++) {
                if (!emitted.contains(sid)) {
                    leftoverIds.add(sid);
                }
            }
            leftoverIds.sort(Comparator.comparing(sccMinFqn::get));
            for (int sid : leftoverIds) {
                List<Ident> members = sccMembersSorted.get(sid);
                List<String> step = new ArrayList<>();
                for (Ident m : members) {
                    step.add(fqn(m.schema, m.name));
                }
                buildOrder.add(step);
            }
        }

        seedRows.sort(
                Comparator.comparing((JsonObject r) -> r.get("query_id").getAsString())
                        .thenComparing(r -> r.get("object").getAsString()));

        Map<Ident, Set<String>> impacted = new TreeMap<>();
        Map<String, Set<Ident>> perQuerySeeds = new HashMap<>();
        for (JsonObject row : seedRows) {
            String object = row.get("object").getAsString();
            int dot = object.indexOf('.');
            String schemaPart = object.substring(0, dot);
            String namePart = object.substring(dot + 1);
            String qid = row.get("query_id").getAsString();
            perQuerySeeds.computeIfAbsent(qid, k -> new TreeSet<>(Ident::compareTo))
                    .add(new Ident(schemaPart, namePart));
        }

        for (Map.Entry<String, Set<Ident>> e : perQuerySeeds.entrySet()) {
            String qid = e.getKey();
            Set<Ident> reach = new TreeSet<>(Ident::compareTo);
            for (Ident s : e.getValue()) {
                if (buildSet.containsKey(s)) {
                    reach.addAll(reachable(s, edges));
                }
            }
            for (Ident r : reach) {
                impacted.computeIfAbsent(r, k -> new TreeSet<>()).add(qid);
            }
        }

        JsonArray impactedSorted = new JsonArray();
        for (Ident ident : impacted.keySet()) {
            SchemaRecord rec = buildSet.get(ident);
            JsonObject entry = new JsonObject();
            entry.addProperty("schema", ident.schema);
            entry.addProperty("name", ident.name);
            entry.addProperty("kind", rec.kind);
            entry.addProperty("version", rec.version);
            entry.addProperty("lock_class", rec.lockClass);
            JsonArray triggers = new JsonArray();
            for (String t : new TreeSet<>(impacted.get(ident))) {
                triggers.add(t);
            }
            entry.add("triggered_by_queries", triggers);
            impactedSorted.add(entry);
        }

        Set<Ident> impactedSet = impacted.keySet();

        JsonObject resolverSummary = new JsonObject();
        resolverSummary.addProperty("selected_total", buildSet.size());
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
        resolverSummary.addProperty("cycle_group_count", cyclesFqn.size());

        JsonArray seedObjects = new JsonArray();
        for (JsonObject row : seedRows) {
            seedObjects.add(row);
        }

        JsonArray cyclesArr = new JsonArray();
        for (List<String> group : cyclesFqn) {
            JsonArray g = new JsonArray();
            for (String f : group) {
                g.add(f);
            }
            cyclesArr.add(g);
        }

        JsonArray buildOrderArr = new JsonArray();
        for (List<String> step : buildOrder) {
            JsonArray s = new JsonArray();
            for (String f : step) {
                s.add(f);
            }
            buildOrderArr.add(s);
        }

        JsonObject impactPayload = new JsonObject();
        impactPayload.add("resolver_summary", resolverSummary);
        impactPayload.add("seed_objects", seedObjects);
        impactPayload.add("impacted_objects", impactedSorted);
        impactPayload.add("cycles", cyclesArr);
        impactPayload.add("build_order", buildOrderArr);

        Map<String, Ident> nameToIdent = new HashMap<>();
        for (Ident ident : buildSet.keySet()) {
            nameToIdent.put(fqn(ident.schema, ident.name), ident);
        }

        JsonArray planSteps = new JsonArray();
        int stepIndex = 1;
        for (List<String> step : buildOrder) {
            List<Ident> keptIdents = new ArrayList<>();
            for (String m : step) {
                Ident ident = nameToIdent.get(m);
                if (ident != null && impactedSet.contains(ident)) {
                    keptIdents.add(ident);
                }
            }
            if (keptIdents.isEmpty()) {
                continue;
            }
            int maxRank = 0;
            for (Ident ident : keptIdents) {
                SchemaRecord rec = buildSet.get(ident);
                int rank = severityMap.getOrDefault(rec.lockClass, 0);
                if (rank > maxRank) {
                    maxRank = rank;
                }
            }
            String maxLockClass = "";
            for (Map.Entry<String, Integer> se : severityMap.entrySet()) {
                if (se.getValue() == maxRank) {
                    if (maxLockClass.isEmpty() || se.getKey().compareTo(maxLockClass) < 0) {
                        maxLockClass = se.getKey();
                    }
                }
            }
            Set<String> triggers = new TreeSet<>();
            for (Ident ident : keptIdents) {
                triggers.addAll(impacted.get(ident));
            }
            JsonObject planStep = new JsonObject();
            planStep.addProperty("step", stepIndex);
            JsonArray objects = new JsonArray();
            for (Ident ident : keptIdents) {
                objects.add(fqn(ident.schema, ident.name));
            }
            planStep.add("objects", objects);
            planStep.addProperty("lock_class", maxLockClass);
            planStep.addProperty("lock_rank", maxRank);
            planStep.addProperty("migration_window", selectWindow(maxRank, windows));
            JsonArray triggersArr = new JsonArray();
            for (String t : triggers) {
                triggersArr.add(t);
            }
            planStep.add("triggered_by_queries", triggersArr);
            planSteps.add(planStep);
            stepIndex++;
        }

        JsonObject planPayload = new JsonObject();
        planPayload.add("steps", planSteps);

        writeJson(outDir.resolve("schema_drift.json"), driftPayload);
        writeJson(outDir.resolve("object_impact.json"), impactPayload);
        writeJson(outDir.resolve("migration_plan.json"), planPayload);
    }

    private static String selectWindow(int stepMaxRank, List<WindowEntry> windows) {
        List<WindowEntry> eligible = new ArrayList<>();
        for (WindowEntry w : windows) {
            if (w.minLockRank <= stepMaxRank) {
                eligible.add(w);
            }
        }
        if (eligible.isEmpty()) {
            eligible = new ArrayList<>(windows);
        }
        eligible.sort(
                Comparator.<WindowEntry>comparingInt(w -> stepMaxRank - w.minLockRank)
                        .thenComparing(w -> w.name));
        return eligible.get(0).name;
    }

    private static Set<Ident> reachable(Ident start, Map<Ident, List<Ident>> edges) {
        Set<Ident> seen = new LinkedHashSet<>();
        seen.add(start);
        List<Ident> stk = new ArrayList<>();
        stk.add(start);
        while (!stk.isEmpty()) {
            Ident cur = stk.remove(stk.size() - 1);
            List<Ident> nxts = edges.get(cur);
            if (nxts == null) {
                continue;
            }
            for (Ident nxt : nxts) {
                if (!seen.contains(nxt)) {
                    seen.add(nxt);
                    stk.add(nxt);
                }
            }
        }
        return seen;
    }

    private static void strongConnect(
            Ident v,
            Map<Ident, List<Ident>> edges,
            Map<Ident, Integer> indexMap,
            Map<Ident, Integer> lowlink,
            Set<Ident> onStack,
            List<Ident> stack,
            List<List<Ident>> sccs,
            int[] counter) {
        indexMap.put(v, counter[0]);
        lowlink.put(v, counter[0]);
        counter[0]++;
        stack.add(v);
        onStack.add(v);
        List<Ident> neighbors = edges.getOrDefault(v, List.of());
        for (Ident w : neighbors) {
            if (!indexMap.containsKey(w)) {
                strongConnect(w, edges, indexMap, lowlink, onStack, stack, sccs, counter);
                lowlink.put(v, Math.min(lowlink.get(v), lowlink.get(w)));
            } else if (onStack.contains(w)) {
                lowlink.put(v, Math.min(lowlink.get(v), indexMap.get(w)));
            }
        }
        if (lowlink.get(v).equals(indexMap.get(v))) {
            List<Ident> comp = new ArrayList<>();
            while (true) {
                Ident w = stack.remove(stack.size() - 1);
                onStack.remove(w);
                comp.add(w);
                if (w.equals(v)) {
                    break;
                }
            }
            sccs.add(comp);
        }
    }

    private static Ident resolveSeed(
            Ref ref,
            Map<Ref, Ref> replaceMap,
            Set<Ref> excludeSet,
            Set<Ident> registryKeys,
            Set<String> missing,
            Set<String> conflicts) {
        Ref replaced = replaceMap.getOrDefault(ref, ref);
        Ident postId = new Ident(replaced.schema, replaced.name);
        if (excludeSet.contains(replaced)) {
            conflicts.add(fqn(replaced.schema, replaced.name));
            return null;
        }
        if (!registryKeys.contains(postId)) {
            missing.add(fqn(replaced.schema, replaced.name));
            return null;
        }
        return postId;
    }

    private static boolean addToSelected(
            Ident ident,
            Map<Ident, SchemaRecord> selected,
            Map<Ident, SchemaRecord> registryIndex) {
        if (selected.containsKey(ident)) {
            return false;
        }
        SchemaRecord rec = registryIndex.get(ident);
        if (rec == null) {
            return false;
        }
        selected.put(ident, rec);
        return true;
    }

    private static DriftLists buildDrift(
            Map<Ident, SchemaRecord> baseline, Map<Ident, SchemaRecord> current) {
        Set<Ident> baselineKeys = baseline.keySet();
        Set<Ident> currentKeys = current.keySet();

        List<Ident> addedKeys = new ArrayList<>();
        for (Ident k : currentKeys) {
            if (!baselineKeys.contains(k)) {
                addedKeys.add(k);
            }
        }
        addedKeys.sort(Ident::compareTo);

        List<Ident> removedKeys = new ArrayList<>();
        for (Ident k : baselineKeys) {
            if (!currentKeys.contains(k)) {
                removedKeys.add(k);
            }
        }
        removedKeys.sort(Ident::compareTo);

        List<Ident> commonKeys = new ArrayList<>();
        for (Ident k : baselineKeys) {
            if (currentKeys.contains(k)) {
                commonKeys.add(k);
            }
        }
        commonKeys.sort(Ident::compareTo);

        JsonArray added = new JsonArray();
        for (Ident k : addedKeys) {
            SchemaRecord rec = current.get(k);
            JsonObject entry = new JsonObject();
            entry.addProperty("schema", rec.schema);
            entry.addProperty("name", rec.name);
            entry.add("attributes", attributeView(rec));
            added.add(entry);
        }

        JsonArray removed = new JsonArray();
        for (Ident k : removedKeys) {
            SchemaRecord rec = baseline.get(k);
            JsonObject entry = new JsonObject();
            entry.addProperty("schema", rec.schema);
            entry.addProperty("name", rec.name);
            entry.add("attributes", attributeView(rec));
            removed.add(entry);
        }

        JsonArray modified = new JsonArray();
        for (Ident k : commonKeys) {
            SchemaRecord oldRec = baseline.get(k);
            SchemaRecord newRec = current.get(k);
            JsonObject oldView = attributeView(oldRec);
            JsonObject newView = attributeView(newRec);
            TreeSet<String> attrUnion = new TreeSet<>();
            for (String key : oldView.keySet()) {
                attrUnion.add(key);
            }
            for (String key : newView.keySet()) {
                attrUnion.add(key);
            }
            JsonObject changed = new JsonObject();
            for (String attr : attrUnion) {
                JsonElement ov = oldView.has(attr) ? oldView.get(attr) : null;
                JsonElement nv = newView.has(attr) ? newView.get(attr) : null;
                if (!jsonEqual(ov, nv)) {
                    JsonObject pair = new JsonObject();
                    pair.add("old_value", ov == null ? JsonNull.INSTANCE : ov.deepCopy());
                    pair.add("new_value", nv == null ? JsonNull.INSTANCE : nv.deepCopy());
                    changed.add(attr, pair);
                }
            }
            if (changed.size() > 0) {
                JsonObject entry = new JsonObject();
                entry.addProperty("schema", oldRec.schema);
                entry.addProperty("name", oldRec.name);
                entry.add("changed_attributes", changed);
                modified.add(entry);
            }
        }

        return new DriftLists(added, removed, modified);
    }

    private static boolean jsonEqual(JsonElement a, JsonElement b) {
        if (a == null && b == null) {
            return true;
        }
        if (a == null || b == null) {
            return false;
        }
        return a.equals(b);
    }

    private static Set<String> buildChangedFqnSet(DriftLists drift) {
        Set<String> refs = new HashSet<>();
        for (JsonElement el : drift.added) {
            JsonObject entry = el.getAsJsonObject();
            refs.add(fqn(entry.get("schema").getAsString(), entry.get("name").getAsString()));
        }
        for (JsonElement el : drift.removed) {
            JsonObject entry = el.getAsJsonObject();
            refs.add(fqn(entry.get("schema").getAsString(), entry.get("name").getAsString()));
        }
        for (JsonElement el : drift.modified) {
            JsonObject entry = el.getAsJsonObject();
            refs.add(fqn(entry.get("schema").getAsString(), entry.get("name").getAsString()));
        }
        return refs;
    }

    private static JsonObject attributeView(SchemaRecord record) {
        JsonObject view = new JsonObject();
        view.addProperty("kind", record.kind);
        view.addProperty("version", record.version);
        view.addProperty("lock_class", record.lockClass);
        view.add("columns", record.columns.deepCopy());
        view.add("constraints", record.constraints.deepCopy());
        JsonArray deps = new JsonArray();
        for (Ref r : normalizedDependsOn(record.dependsOnRaw)) {
            JsonObject dep = new JsonObject();
            dep.addProperty("schema", r.schema);
            dep.addProperty("name", r.name);
            dep.addProperty("kind", r.kind);
            deps.add(dep);
        }
        view.add("depends_on", deps);
        return view;
    }

    private static List<Ref> normalizedDependsOn(List<JsonElement> rawList) {
        List<Ref> out = new ArrayList<>();
        Set<Ref> seen = new HashSet<>();
        for (JsonElement item : rawList) {
            Ref ref = validateRef(item);
            if (ref == null) {
                continue;
            }
            if (seen.contains(ref)) {
                continue;
            }
            seen.add(ref);
            out.add(ref);
        }
        return out;
    }

    private static SchemaIndex loadSchemaIndex(Path path) throws IOException {
        byte[] bytes = Files.readAllBytes(path);
        String sha256 = sha256Hex(bytes);
        JsonObject raw = JsonParser.parseString(new String(bytes, StandardCharsets.UTF_8))
                .getAsJsonObject();
        Map<Ident, SchemaRecord> index = new LinkedHashMap<>();
        if (raw.has("objects") && raw.get("objects").isJsonArray()) {
            for (JsonElement el : raw.getAsJsonArray("objects")) {
                if (!el.isJsonObject()) {
                    continue;
                }
                JsonObject obj = el.getAsJsonObject();
                Ident ident =
                        normalizeIdentifier(
                                jsonString(obj, "schema"),
                                jsonString(obj, "name"),
                                obj.has("quoted") && !obj.get("quoted").isJsonNull()
                                        ? obj.get("quoted").getAsBoolean()
                                        : false);
                if (ident == null) {
                    continue;
                }
                String kind = jsonString(obj, "kind");
                if (kind == null || !ALLOWED_KINDS.contains(kind)) {
                    continue;
                }
                String version = jsonString(obj, "version");
                if (parseVersion(version) == null) {
                    continue;
                }
                if (index.containsKey(ident)) {
                    continue;
                }
                String lockClass =
                        jsonString(obj, "lock_class") != null
                                ? jsonString(obj, "lock_class")
                                : "ACCESS_SHARE";
                JsonArray columns =
                        obj.has("columns") && obj.get("columns").isJsonArray()
                                ? obj.getAsJsonArray("columns").deepCopy()
                                : new JsonArray();
                JsonArray constraints =
                        obj.has("constraints") && obj.get("constraints").isJsonArray()
                                ? obj.getAsJsonArray("constraints").deepCopy()
                                : new JsonArray();
                List<JsonElement> dependsOnRaw = new ArrayList<>();
                if (obj.has("depends_on") && obj.get("depends_on").isJsonArray()) {
                    for (JsonElement dep : obj.getAsJsonArray("depends_on")) {
                        dependsOnRaw.add(dep);
                    }
                }
                index.put(
                        ident,
                        new SchemaRecord(
                                ident.schema,
                                ident.name,
                                kind,
                                version,
                                lockClass,
                                columns,
                                constraints,
                                dependsOnRaw));
            }
        }
        return new SchemaIndex(index, sha256);
    }

    private static int[] parseVersion(String value) {
        if (value == null || value.isEmpty()) {
            return null;
        }
        String[] parts = value.split("\\.", -1);
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

    private static Ident normalizeIdentifier(String schema, String name, boolean quoted) {
        if (schema == null || schema.isEmpty() || name == null || name.isEmpty()) {
            return null;
        }
        if (quoted) {
            return new Ident(schema, name);
        }
        return new Ident(schema.toLowerCase(), name.toLowerCase());
    }

    private static Ref validateRef(JsonElement raw) {
        if (raw == null || !raw.isJsonObject()) {
            return null;
        }
        JsonObject obj = raw.getAsJsonObject();
        String schema = jsonString(obj, "schema");
        String name = jsonString(obj, "name");
        String kind = jsonString(obj, "kind");
        if (schema == null || schema.isEmpty() || name == null || name.isEmpty()) {
            return null;
        }
        if (kind == null || !ALLOWED_KINDS.contains(kind)) {
            return null;
        }
        return new Ref(schema.toLowerCase(), name.toLowerCase(), kind);
    }

    private static String jsonString(JsonObject obj, String key) {
        if (!obj.has(key) || obj.get(key).isJsonNull() || !obj.get(key).isJsonPrimitive()) {
            return null;
        }
        return obj.get(key).getAsString();
    }

    private static String fqn(String schema, String name) {
        return schema + "." + name;
    }

    private static JsonObject loadJsonObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
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

    private static final class Ident implements Comparable<Ident> {
        final String schema;
        final String name;

        Ident(String schema, String name) {
            this.schema = schema;
            this.name = name;
        }

        @Override
        public int compareTo(Ident o) {
            int c = schema.compareTo(o.schema);
            return c != 0 ? c : name.compareTo(o.name);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Ident other)) {
                return false;
            }
            return schema.equals(other.schema) && name.equals(other.name);
        }

        @Override
        public int hashCode() {
            return schema.hashCode() * 31 + name.hashCode();
        }
    }

    private static final class Ref {
        final String schema;
        final String name;
        final String kind;

        Ref(String schema, String name, String kind) {
            this.schema = schema;
            this.name = name;
            this.kind = kind;
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Ref other)) {
                return false;
            }
            return schema.equals(other.schema)
                    && name.equals(other.name)
                    && kind.equals(other.kind);
        }

        @Override
        public int hashCode() {
            int h = schema.hashCode();
            h = 31 * h + name.hashCode();
            h = 31 * h + kind.hashCode();
            return h;
        }
    }

    private static final class SchemaRecord {
        final String schema;
        final String name;
        final String kind;
        final String version;
        final String lockClass;
        final JsonArray columns;
        final JsonArray constraints;
        final List<JsonElement> dependsOnRaw;

        SchemaRecord(
                String schema,
                String name,
                String kind,
                String version,
                String lockClass,
                JsonArray columns,
                JsonArray constraints,
                List<JsonElement> dependsOnRaw) {
            this.schema = schema;
            this.name = name;
            this.kind = kind;
            this.version = version;
            this.lockClass = lockClass;
            this.columns = columns;
            this.constraints = constraints;
            this.dependsOnRaw = dependsOnRaw;
        }
    }

    private static final class SchemaIndex {
        final Map<Ident, SchemaRecord> index;
        final String sha256;

        SchemaIndex(Map<Ident, SchemaRecord> index, String sha256) {
            this.index = index;
            this.sha256 = sha256;
        }
    }

    private static final class DriftLists {
        final JsonArray added;
        final JsonArray removed;
        final JsonArray modified;

        DriftLists(JsonArray added, JsonArray removed, JsonArray modified) {
            this.added = added;
            this.removed = removed;
            this.modified = modified;
        }
    }

    private static final class WindowEntry {
        final int minLockRank;
        final String name;

        WindowEntry(int minLockRank, String name) {
            this.minLockRank = minLockRank;
            this.name = name;
        }
    }
}
