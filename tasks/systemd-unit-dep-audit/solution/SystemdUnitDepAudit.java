import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Deque;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Systemd unit dependency audit oracle. */
public final class SystemdUnitDepAudit {

    private static final List<String> DEP_DIRECTIVES =
            Arrays.asList("Requires", "Wants", "BindsTo");
    private static final String ORDER_AFTER = "After";
    private static final String ORDER_BEFORE = "Before";
    private static final Pattern SECTION_PATTERN = Pattern.compile("^\\[(.+)\\]$");

    private SystemdUnitDepAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: SystemdUnitDepAudit <unitsDir> <reportPath>");
            System.exit(1);
        }
        Path unitsDir = Path.of(args[0]);
        Path reportPath = Path.of(args[1]);
        run(unitsDir, reportPath);
    }

    private static void run(Path unitsDir, Path reportPath) throws IOException {
        FilesystemScan scan = discoverFilesystem(unitsDir);

        if (scan.regularFiles.isEmpty() && scan.maskedSet.isEmpty()) {
            JsonObject empty = buildEmptyReport();
            writeReport(reportPath, empty);
            return;
        }

        Map<String, UnitFileParser> parsed =
                parseUnitFiles(scan.regularFiles, scan.dropinMap);

        DepGraphResult depResult =
                buildDepGraph(parsed, scan.templates, scan.regularFiles, scan.maskedSet);

        Map<String, Set<String>> orderGraph =
                buildOrderGraph(parsed, scan.templates, depResult.instances);

        List<List<String>> cycles = detectCycles(depResult.graph);

        List<Map<String, String>> missing =
                detectMissing(
                        depResult.graph,
                        scan.regularFiles,
                        scan.templates,
                        scan.maskedSet);

        List<List<String>> orderingConflicts = detectOrderingConflicts(orderGraph);

        List<Map<String, String>> maskedWarnings =
                detectMaskedWarnings(depResult.detail, scan.maskedSet);

        Set<String> trapped =
                computeCycleTrapped(
                        cycles,
                        depResult.graph,
                        scan.regularFiles,
                        scan.templates,
                        scan.maskedSet,
                        parsed);

        List<String> bootOrder =
                computeBootOrder(
                        scan.regularFiles,
                        scan.templates,
                        scan.maskedSet,
                        trapped,
                        orderGraph,
                        depResult.instances);

        Map<String, List<String>> impact =
                computeImpact(cycles, orderingConflicts, depResult.graph, scan.maskedSet);

        JsonObject report = new JsonObject();
        report.add("circular_dependencies", listOfListsToJson(cycles));
        report.add("effective_boot_order", stringListToJson(bootOrder));
        report.add("impact_analysis", impactToJson(impact));
        report.add("masked_dependency_warnings", maskedWarningsToJson(maskedWarnings));
        report.add("missing_dependencies", missingDepsToJson(missing));
        report.add("ordering_conflicts", listOfListsToJson(orderingConflicts));

        validateReport(report);
        writeReport(reportPath, report);
    }

    private static JsonObject buildEmptyReport() {
        JsonObject empty = new JsonObject();
        empty.add("circular_dependencies", new JsonArray());
        empty.add("effective_boot_order", new JsonArray());
        empty.add("impact_analysis", new JsonObject());
        empty.add("masked_dependency_warnings", new JsonArray());
        empty.add("missing_dependencies", new JsonArray());
        empty.add("ordering_conflicts", new JsonArray());
        return empty;
    }

    private static void writeReport(Path reportPath, JsonObject report) throws IOException {
        Gson gson =
                new GsonBuilder().setPrettyPrinting().disableHtmlEscaping().create();
        String text = gson.toJson(report);
        if (reportPath.getParent() != null) {
            Files.createDirectories(reportPath.getParent());
        }
        Files.writeString(reportPath, text, StandardCharsets.UTF_8);
    }

    private static JsonArray listOfListsToJson(List<List<String>> rows) {
        JsonArray outer = new JsonArray();
        for (List<String> row : rows) {
            JsonArray inner = new JsonArray();
            for (String item : row) {
                inner.add(item);
            }
            outer.add(inner);
        }
        return outer;
    }

    private static JsonArray stringListToJson(List<String> items) {
        JsonArray arr = new JsonArray();
        for (String item : items) {
            arr.add(item);
        }
        return arr;
    }

    private static JsonArray missingDepsToJson(List<Map<String, String>> entries) {
        JsonArray arr = new JsonArray();
        for (Map<String, String> entry : entries) {
            JsonObject obj = new JsonObject();
            obj.addProperty("source", entry.get("source"));
            obj.addProperty("target", entry.get("target"));
            arr.add(obj);
        }
        return arr;
    }

    private static JsonArray maskedWarningsToJson(List<Map<String, String>> entries) {
        JsonArray arr = new JsonArray();
        for (Map<String, String> entry : entries) {
            JsonObject obj = new JsonObject();
            obj.addProperty("directive", entry.get("directive"));
            obj.addProperty("masked_unit", entry.get("masked_unit"));
            obj.addProperty("source", entry.get("source"));
            arr.add(obj);
        }
        return arr;
    }

    private static JsonObject impactToJson(Map<String, List<String>> impact) {
        JsonObject obj = new JsonObject();
        for (Map.Entry<String, List<String>> e : impact.entrySet()) {
            obj.add(e.getKey(), stringListToJson(e.getValue()));
        }
        return obj;
    }

    private static void validateReport(JsonObject report) {
        Set<String> required =
                new TreeSet<>(
                        Arrays.asList(
                                "circular_dependencies",
                                "missing_dependencies",
                                "ordering_conflicts",
                                "masked_dependency_warnings",
                                "effective_boot_order",
                                "impact_analysis"));
        Set<String> actual = new TreeSet<>();
        for (String key : report.keySet()) {
            actual.add(key);
        }
        Set<String> extra = new TreeSet<>(actual);
        extra.removeAll(required);
        if (!extra.isEmpty()) {
            throw new IllegalArgumentException(
                    "Report contains unexpected top-level keys: " + extra);
        }
        for (String key : required) {
            if (!report.has(key)) {
                throw new IllegalArgumentException("Report is missing required key: " + key);
            }
        }
        if (!report.get("circular_dependencies").isJsonArray()
                || !report.get("missing_dependencies").isJsonArray()
                || !report.get("ordering_conflicts").isJsonArray()
                || !report.get("masked_dependency_warnings").isJsonArray()
                || !report.get("effective_boot_order").isJsonArray()
                || !report.get("impact_analysis").isJsonObject()) {
            throw new IllegalArgumentException("Report key has wrong type");
        }
    }

    private static final class FilesystemScan {
        final Map<String, Path> regularFiles = new TreeMap<>();
        final Set<String> maskedSet = new TreeSet<>();
        final Map<String, Path> templates = new TreeMap<>();
        final Map<String, List<Path>> dropinMap = new TreeMap<>();
    }

    private static final class DepGraphResult {
        final Map<String, Set<String>> graph = new TreeMap<>();
        final Map<String, Map<String, Set<String>>> detail = new TreeMap<>();
        final Set<String> allTargets = new TreeSet<>();
        final Set<String> instances = new TreeSet<>();
    }

    private static FilesystemScan discoverFilesystem(Path unitsDir) throws IOException {
        FilesystemScan scan = new FilesystemScan();
        if (!Files.isDirectory(unitsDir)) {
            return scan;
        }

        List<String> names = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(unitsDir)) {
            for (Path entry : stream) {
                names.add(entry.getFileName().toString());
            }
        }
        Collections.sort(names);

        for (String name : names) {
            Path entry = unitsDir.resolve(name);

            if (Files.isSymbolicLink(entry)) {
                String target = Files.readSymbolicLink(entry).toString();
                if ("/dev/null".equals(target)) {
                    scan.maskedSet.add(name);
                }
                continue;
            }

            if (Files.isDirectory(entry)) {
                if (name.endsWith(".d")) {
                    String parentName = name.substring(0, name.length() - 2);
                    List<Path> confs = new ArrayList<>();
                    try (DirectoryStream<Path> confStream =
                            Files.newDirectoryStream(entry, "*.conf")) {
                        for (Path conf : confStream) {
                            confs.add(conf);
                        }
                    }
                    Collections.sort(
                            confs,
                            (a, b) ->
                                    a.getFileName()
                                            .toString()
                                            .compareTo(b.getFileName().toString()));
                    if (!confs.isEmpty()) {
                        scan.dropinMap.put(parentName, confs);
                    }
                }
                continue;
            }

            if (Files.isRegularFile(entry)) {
                scan.regularFiles.put(name, entry);
                if (name.contains("@.")) {
                    scan.templates.put(name, entry);
                }
            }
        }

        return scan;
    }

    private static Map<String, UnitFileParser> parseUnitFiles(
            Map<String, Path> regularFiles, Map<String, List<Path>> dropinMap)
            throws IOException {
        Map<String, UnitFileParser> parsed = new TreeMap<>();
        for (String name : regularFiles.keySet()) {
            Path path = regularFiles.get(name);
            UnitFileParser parser = new UnitFileParser(path);

            if (dropinMap.containsKey(name)) {
                for (Path conf : dropinMap.get(name)) {
                    UnitFileParser overlay = new UnitFileParser(conf);
                    parser.mergeDropin(overlay);
                }
            }

            parsed.put(name, parser);
        }
        return parsed;
    }

    private static String templateForInstance(String instance, Map<String, Path> templates) {
        int atPos = instance.indexOf('@');
        if (atPos < 0) {
            return null;
        }
        int dotPos = instance.lastIndexOf('.');
        if (dotPos < 0 || dotPos <= atPos) {
            return null;
        }
        String prefix = instance.substring(0, atPos);
        String ext = instance.substring(dotPos);
        String tmpl = prefix + "@" + ext;
        return templates.containsKey(tmpl) ? tmpl : null;
    }

    private static boolean instanceHasTemplate(String name, Map<String, Path> templates) {
        return templateForInstance(name, templates) != null;
    }

    private static boolean unitExists(
            String name,
            Map<String, Path> regularFiles,
            Map<String, Path> templates,
            Set<String> maskedSet) {
        if (regularFiles.containsKey(name)) {
            return true;
        }
        if (maskedSet.contains(name)) {
            return true;
        }
        return instanceHasTemplate(name, templates);
    }

    private static List<String> getUnitDeps(
            String unitName,
            Map<String, UnitFileParser> parsed,
            Map<String, Path> templates,
            String directive) {
        if (parsed.containsKey(unitName)) {
            return parsed.get(unitName).getValues("Unit", directive);
        }
        String tmpl = templateForInstance(unitName, templates);
        if (tmpl != null && parsed.containsKey(tmpl)) {
            return parsed.get(tmpl).getValues("Unit", directive);
        }
        return Collections.emptyList();
    }

    private static List<String> getUnitOrdering(
            String unitName,
            Map<String, UnitFileParser> parsed,
            Map<String, Path> templates,
            String direction) {
        if (parsed.containsKey(unitName)) {
            return parsed.get(unitName).getValues("Unit", direction);
        }
        String tmpl = templateForInstance(unitName, templates);
        if (tmpl != null && parsed.containsKey(tmpl)) {
            return parsed.get(tmpl).getValues("Unit", direction);
        }
        return Collections.emptyList();
    }

    private static DepGraphResult buildDepGraph(
            Map<String, UnitFileParser> parsed,
            Map<String, Path> templates,
            Map<String, Path> regularFiles,
            Set<String> maskedSet) {
        DepGraphResult result = new DepGraphResult();
        Set<String> instances = new HashSet<>();

        for (Map.Entry<String, UnitFileParser> entry : parsed.entrySet()) {
            String unitName = entry.getKey();
            UnitFileParser unitParser = entry.getValue();
            for (String directive : DEP_DIRECTIVES) {
                for (String target : unitParser.getValues("Unit", directive)) {
                    result.allTargets.add(target);
                    result.graph.computeIfAbsent(unitName, k -> new TreeSet<>()).add(target);
                    result.detail
                            .computeIfAbsent(unitName, k -> new TreeMap<>())
                            .computeIfAbsent(target, k -> new TreeSet<>())
                            .add(directive);

                    if (instanceHasTemplate(target, templates)
                            && !regularFiles.containsKey(target)) {
                        instances.add(target);
                    }
                }
            }
        }

        Set<String> newInstances = new HashSet<>(instances);
        while (!newInstances.isEmpty()) {
            Set<String> batch = new HashSet<>(newInstances);
            newInstances.clear();
            for (String inst : batch) {
                String tmpl = templateForInstance(inst, templates);
                if (tmpl == null || !parsed.containsKey(tmpl)) {
                    continue;
                }
                UnitFileParser tmplParser = parsed.get(tmpl);
                for (String directive : DEP_DIRECTIVES) {
                    for (String target : tmplParser.getValues("Unit", directive)) {
                        result.allTargets.add(target);
                        Set<String> edges =
                                result.graph.computeIfAbsent(inst, k -> new TreeSet<>());
                        if (!edges.contains(target)) {
                            edges.add(target);
                            result.detail
                                    .computeIfAbsent(inst, k -> new TreeMap<>())
                                    .computeIfAbsent(target, k -> new TreeSet<>())
                                    .add(directive);

                            if (instanceHasTemplate(target, templates)
                                    && !regularFiles.containsKey(target)) {
                                if (!instances.contains(target)) {
                                    instances.add(target);
                                    newInstances.add(target);
                                }
                            }
                        }
                    }
                }
            }
        }

        result.instances.addAll(instances);
        return result;
    }

    private static Map<String, Set<String>> buildOrderGraph(
            Map<String, UnitFileParser> parsed,
            Map<String, Path> templates,
            Set<String> instances) {
        Map<String, Set<String>> afterMap = new TreeMap<>();

        for (Map.Entry<String, UnitFileParser> entry : parsed.entrySet()) {
            String unitName = entry.getKey();
            UnitFileParser unitParser = entry.getValue();

            for (String target : unitParser.getValues("Unit", ORDER_AFTER)) {
                afterMap.computeIfAbsent(unitName, k -> new TreeSet<>()).add(target);
            }
            for (String target : unitParser.getValues("Unit", ORDER_BEFORE)) {
                afterMap.computeIfAbsent(target, k -> new TreeSet<>()).add(unitName);
            }
        }

        for (String inst : instances) {
            String tmpl = templateForInstance(inst, templates);
            if (tmpl == null || !parsed.containsKey(tmpl)) {
                continue;
            }
            UnitFileParser tmplParser = parsed.get(tmpl);

            for (String target : tmplParser.getValues("Unit", ORDER_AFTER)) {
                afterMap.computeIfAbsent(inst, k -> new TreeSet<>()).add(target);
            }
            for (String target : tmplParser.getValues("Unit", ORDER_BEFORE)) {
                afterMap.computeIfAbsent(target, k -> new TreeSet<>()).add(inst);
            }
        }

        return afterMap;
    }

    private static List<List<String>> detectCycles(Map<String, Set<String>> depGraph) {
        Set<String> allNodes = new TreeSet<>(depGraph.keySet());
        for (Set<String> targets : depGraph.values()) {
            allNodes.addAll(targets);
        }

        TarjanScc tarjan = new TarjanScc(depGraph, allNodes);
        List<List<String>> sccs = tarjan.run();

        List<List<String>> cycles = new ArrayList<>();
        for (List<String> scc : sccs) {
            if (scc.size() > 1) {
                cycles.add(new ArrayList<>(scc));
            }
        }
        Collections.sort(cycles, SystemdUnitDepAudit::compareStringLists);
        return cycles;
    }

    private static int compareStringLists(List<String> a, List<String> b) {
        int n = Math.min(a.size(), b.size());
        for (int i = 0; i < n; i++) {
            int cmp = a.get(i).compareTo(b.get(i));
            if (cmp != 0) {
                return cmp;
            }
        }
        return Integer.compare(a.size(), b.size());
    }

    private static List<Map<String, String>> detectMissing(
            Map<String, Set<String>> depGraph,
            Map<String, Path> regularFiles,
            Map<String, Path> templates,
            Set<String> maskedSet) {
        List<Map<String, String>> missing = new ArrayList<>();

        for (String source : depGraph.keySet()) {
            for (String target : depGraph.get(source)) {
                if (regularFiles.containsKey(target)) {
                    continue;
                }
                if (maskedSet.contains(target)) {
                    continue;
                }
                if (instanceHasTemplate(target, templates)) {
                    continue;
                }
                Map<String, String> entry = new TreeMap<>();
                entry.put("source", source);
                entry.put("target", target);
                missing.add(entry);
            }
        }

        missing.sort(
                (a, b) -> {
                    int cmp = a.get("source").compareTo(b.get("source"));
                    if (cmp != 0) {
                        return cmp;
                    }
                    return a.get("target").compareTo(b.get("target"));
                });
        return missing;
    }

    private static List<List<String>> detectOrderingConflicts(
            Map<String, Set<String>> orderGraph) {
        List<List<String>> conflicts = new ArrayList<>();
        Set<String> checked = new HashSet<>();

        Set<String> allUnits = new TreeSet<>(orderGraph.keySet());
        for (Set<String> deps : orderGraph.values()) {
            allUnits.addAll(deps);
        }

        for (String unitA : allUnits) {
            Set<String> aAfters = orderGraph.getOrDefault(unitA, Collections.emptySet());
            for (String unitB : aAfters) {
                Set<String> bAfters = orderGraph.getOrDefault(unitB, Collections.emptySet());
                if (bAfters.contains(unitA)) {
                    List<String> pair = new ArrayList<>();
                    if (unitA.compareTo(unitB) <= 0) {
                        pair.add(unitA);
                        pair.add(unitB);
                    } else {
                        pair.add(unitB);
                        pair.add(unitA);
                    }
                    String key = pair.get(0) + "\0" + pair.get(1);
                    if (!checked.contains(key)) {
                        checked.add(key);
                        conflicts.add(pair);
                    }
                }
            }
        }

        Collections.sort(conflicts, SystemdUnitDepAudit::compareStringLists);
        return conflicts;
    }

    private static List<Map<String, String>> detectMaskedWarnings(
            Map<String, Map<String, Set<String>>> depDetail, Set<String> maskedSet) {
        List<Map<String, String>> warnings = new ArrayList<>();

        for (String source : depDetail.keySet()) {
            if (maskedSet.contains(source)) {
                continue;
            }
            Map<String, Set<String>> targets = depDetail.get(source);
            for (String target : targets.keySet()) {
                if (!maskedSet.contains(target)) {
                    continue;
                }
                for (String directive : targets.get(target)) {
                    Map<String, String> warning = new TreeMap<>();
                    warning.put("directive", directive);
                    warning.put("masked_unit", target);
                    warning.put("source", source);
                    warnings.add(warning);
                }
            }
        }

        warnings.sort(
                (a, b) -> {
                    int cmp = a.get("source").compareTo(b.get("source"));
                    if (cmp != 0) {
                        return cmp;
                    }
                    cmp = a.get("masked_unit").compareTo(b.get("masked_unit"));
                    if (cmp != 0) {
                        return cmp;
                    }
                    return a.get("directive").compareTo(b.get("directive"));
                });
        return warnings;
    }

    private static Set<String> computeCycleTrapped(
            List<List<String>> cycles,
            Map<String, Set<String>> depGraph,
            Map<String, Path> regularFiles,
            Map<String, Path> templates,
            Set<String> maskedSet,
            Map<String, UnitFileParser> parsed) {
        Set<String> trapped = new TreeSet<>();
        for (List<String> cycle : cycles) {
            trapped.addAll(cycle);
        }

        boolean changed = true;
        while (changed) {
            changed = false;
            Set<String> units = new TreeSet<>(regularFiles.keySet());
            units.addAll(depGraph.keySet());

            for (String unit : units) {
                if (trapped.contains(unit) || maskedSet.contains(unit)) {
                    continue;
                }

                Set<String> hardDeps = new TreeSet<>();
                if (parsed.containsKey(unit)) {
                    hardDeps.addAll(parsed.get(unit).getValues("Unit", "Requires"));
                    hardDeps.addAll(parsed.get(unit).getValues("Unit", "BindsTo"));
                } else {
                    String tmpl = templateForInstance(unit, templates);
                    if (tmpl != null && parsed.containsKey(tmpl)) {
                        hardDeps.addAll(parsed.get(tmpl).getValues("Unit", "Requires"));
                        hardDeps.addAll(parsed.get(tmpl).getValues("Unit", "BindsTo"));
                    }
                }

                for (String dep : hardDeps) {
                    if (trapped.contains(dep)) {
                        trapped.add(unit);
                        changed = true;
                        break;
                    }
                    if (maskedSet.contains(dep)) {
                        trapped.add(unit);
                        changed = true;
                        break;
                    }
                    if (!unitExists(dep, regularFiles, templates, maskedSet)) {
                        trapped.add(unit);
                        changed = true;
                        break;
                    }
                }
            }
        }

        return trapped;
    }

    private static List<String> computeBootOrder(
            Map<String, Path> regularFiles,
            Map<String, Path> templates,
            Set<String> maskedSet,
            Set<String> trapped,
            Map<String, Set<String>> orderGraph,
            Set<String> instances) {
        Set<String> bootable = new TreeSet<>();

        for (String name : regularFiles.keySet()) {
            if (!maskedSet.contains(name) && !trapped.contains(name)) {
                bootable.add(name);
            }
        }

        for (String inst : instances) {
            if (!trapped.contains(inst)) {
                bootable.add(inst);
            }
        }

        Map<String, Set<String>> adj = new TreeMap<>();
        for (String unit : bootable) {
            Set<String> deps = orderGraph.getOrDefault(unit, Collections.emptySet());
            for (String dep : deps) {
                if (bootable.contains(dep)) {
                    adj.computeIfAbsent(unit, k -> new TreeSet<>()).add(dep);
                }
            }
        }

        Map<String, Integer> inDegree = new TreeMap<>();
        Map<String, Set<String>> reverseAdj = new TreeMap<>();
        for (String unit : bootable) {
            inDegree.put(unit, 0);
        }

        for (Map.Entry<String, Set<String>> entry : adj.entrySet()) {
            String unit = entry.getKey();
            for (String dep : entry.getValue()) {
                reverseAdj.computeIfAbsent(dep, k -> new TreeSet<>()).add(unit);
                inDegree.put(unit, inDegree.get(unit) + 1);
            }
        }

        PriorityQueue<String> heap = new PriorityQueue<>();
        for (String unit : bootable) {
            if (inDegree.get(unit) == 0) {
                heap.add(unit);
            }
        }

        List<String> order = new ArrayList<>();
        Set<String> placed = new HashSet<>();
        while (!heap.isEmpty()) {
            String current = heap.poll();
            order.add(current);
            placed.add(current);
            Set<String> dependents =
                    reverseAdj.getOrDefault(current, Collections.emptySet());
            for (String dependent : dependents) {
                int next = inDegree.get(dependent) - 1;
                inDegree.put(dependent, next);
                if (next == 0) {
                    heap.add(dependent);
                }
            }
        }

        return order;
    }

    private static Map<String, Set<String>> buildReverseDepGraph(
            Map<String, Set<String>> depGraph) {
        Map<String, Set<String>> reverse = new TreeMap<>();
        for (Map.Entry<String, Set<String>> entry : depGraph.entrySet()) {
            for (String target : entry.getValue()) {
                reverse.computeIfAbsent(target, k -> new TreeSet<>()).add(entry.getKey());
            }
        }
        return reverse;
    }

    private static List<String> findDownstream(
            List<String> members,
            Map<String, Set<String>> reverseDep,
            Set<String> excluded) {
        Set<String> memberSet = new HashSet<>(members);
        Set<String> visited = new TreeSet<>();
        Deque<String> queue = new ArrayDeque<>(members);

        while (!queue.isEmpty()) {
            String node = queue.removeFirst();
            Set<String> dependents = reverseDep.getOrDefault(node, Collections.emptySet());
            for (String dependent : dependents) {
                if (visited.contains(dependent)) {
                    continue;
                }
                if (memberSet.contains(dependent)) {
                    continue;
                }
                if (excluded.contains(dependent)) {
                    continue;
                }
                visited.add(dependent);
                queue.addLast(dependent);
            }
        }

        return new ArrayList<>(visited);
    }

    private static Map<String, List<String>> computeImpact(
            List<List<String>> cycles,
            List<List<String>> conflicts,
            Map<String, Set<String>> depGraph,
            Set<String> maskedSet) {
        Map<String, Set<String>> reverse = buildReverseDepGraph(depGraph);
        Map<String, List<String>> result = new TreeMap<>();

        for (List<String> cycle : cycles) {
            List<String> sortedMembers = new ArrayList<>(cycle);
            Collections.sort(sortedMembers);
            String key = String.join(",", sortedMembers);
            List<String> downstream = findDownstream(sortedMembers, reverse, maskedSet);
            result.put(key, downstream);
        }

        for (List<String> conflict : conflicts) {
            List<String> sortedMembers = new ArrayList<>(conflict);
            Collections.sort(sortedMembers);
            String key = String.join(",", sortedMembers);
            List<String> downstream = findDownstream(sortedMembers, reverse, maskedSet);
            result.put(key, downstream);
        }

        return result;
    }

    private static final class UnitFileParser {
        private final Map<String, Map<String, List<String>>> sections = new HashMap<>();

        UnitFileParser(Path filepath) throws IOException {
            parse(filepath);
        }

        private void parse(Path filepath) {
            String currentSection = null;
            try {
                for (String raw : Files.readAllLines(filepath, StandardCharsets.UTF_8)) {
                    String line = raw.strip();
                    if (line.isEmpty() || line.startsWith("#") || line.startsWith(";")) {
                        continue;
                    }
                    Matcher sec = SECTION_PATTERN.matcher(line);
                    if (sec.matches()) {
                        currentSection = sec.group(1);
                        continue;
                    }
                    if (currentSection == null) {
                        continue;
                    }
                    int eq = line.indexOf('=');
                    if (eq < 0) {
                        continue;
                    }
                    String key = line.substring(0, eq).strip();
                    String val = line.substring(eq + 1).strip();
                    sections
                            .computeIfAbsent(currentSection, k -> new HashMap<>())
                            .computeIfAbsent(key, k -> new ArrayList<>())
                            .add(val);
                }
            } catch (IOException ignored) {
                // Match Python: swallow IO errors
            }
        }

        List<String> getValues(String section, String key) {
            Map<String, List<String>> sec = sections.get(section);
            if (sec == null) {
                return Collections.emptyList();
            }
            List<String> rawList = sec.getOrDefault(key, Collections.emptyList());
            List<String> result = new ArrayList<>();
            for (String entry : rawList) {
                for (String token : entry.split("\\s+")) {
                    token = token.strip();
                    if (!token.isEmpty()) {
                        result.add(token);
                    }
                }
            }
            return result;
        }

        void mergeDropin(UnitFileParser other) {
            for (Map.Entry<String, Map<String, List<String>>> sectionEntry :
                    other.sections.entrySet()) {
                String section = sectionEntry.getKey();
                for (Map.Entry<String, List<String>> directiveEntry :
                        sectionEntry.getValue().entrySet()) {
                    String key = directiveEntry.getKey();
                    List<String> valList = directiveEntry.getValue();
                    Map<String, List<String>> targetSection =
                            sections.computeIfAbsent(section, k -> new HashMap<>());
                    if (valList.size() == 1 && valList.get(0).isEmpty()) {
                        targetSection.put(key, new ArrayList<>());
                    } else {
                        targetSection
                                .computeIfAbsent(key, k -> new ArrayList<>())
                                .addAll(valList);
                    }
                }
            }
        }
    }

    private static final class TarjanScc {
        private final Map<String, Set<String>> graph;
        private final Set<String> allNodes;
        private final int[] indexCounter = {0};
        private final Deque<String> stack = new ArrayDeque<>();
        private final Set<String> onStack = new HashSet<>();
        private final Map<String, Integer> lowlink = new HashMap<>();
        private final Map<String, Integer> index = new HashMap<>();
        private final List<List<String>> sccs = new ArrayList<>();

        TarjanScc(Map<String, Set<String>> graph, Set<String> allNodes) {
            this.graph = graph;
            this.allNodes = allNodes;
        }

        List<List<String>> run() {
            for (String node : new TreeSet<>(allNodes)) {
                if (!index.containsKey(node)) {
                    strongConnect(node);
                }
            }
            return sccs;
        }

        private void strongConnect(String v) {
            index.put(v, indexCounter[0]);
            lowlink.put(v, indexCounter[0]);
            indexCounter[0]++;
            stack.addLast(v);
            onStack.add(v);

            Set<String> neighbors = graph.getOrDefault(v, Collections.emptySet());
            for (String w : new TreeSet<>(neighbors)) {
                if (!index.containsKey(w)) {
                    strongConnect(w);
                    lowlink.put(v, Math.min(lowlink.get(v), lowlink.get(w)));
                } else if (onStack.contains(w)) {
                    lowlink.put(v, Math.min(lowlink.get(v), index.get(w)));
                }
            }

            if (lowlink.get(v).equals(index.get(v))) {
                List<String> component = new ArrayList<>();
                while (true) {
                    String w = stack.removeLast();
                    onStack.remove(w);
                    component.add(w);
                    if (w.equals(v)) {
                        break;
                    }
                }
                if (component.size() > 1) {
                    Collections.sort(component);
                    sccs.add(component);
                }
            }
        }
    }
}
