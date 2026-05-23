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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class Replay {
    private static final Gson GSON =
            new GsonBuilder()
                    .disableHtmlEscaping()
                    .serializeNulls()
                    .setPrettyPrinting()
                    .create();

    private static final Map<String, Integer> SEVERITY_RANK = new TreeMap<>();

    static {
        SEVERITY_RANK.put("error", 0);
        SEVERITY_RANK.put("warning", 1);
        SEVERITY_RANK.put("note", 2);
    }

    private static Map<String, String> diagSeverity;

    private Replay() {}

    private static final class Proc {
        String cmdline;
        Integer exitCode;
        String exitSignal;
        Integer exitTick;
        Integer exitSeq;
        int pid;
        int ppid;
        int startTick;
        String state;
        int uid;
    }

    private static final class Diag {
        String code;
        Integer pid;
        String severity;
    }

    private static final class Edge {
        final int from;
        final int to;
        final String type;

        Edge(int from, int to, String type) {
            this.from = from;
            this.to = to;
            this.type = type;
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Edge)) {
                return false;
            }
            Edge e = (Edge) o;
            return from == e.from && to == e.to && type.equals(e.type);
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(from) * 31 + Integer.hashCode(to) * 17 + type.hashCode();
        }
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

    private static void loadDiagCodes(Path docsPath) throws IOException {
        String text = Files.readString(docsPath, StandardCharsets.UTF_8);
        Map<String, String> severity = new TreeMap<>();
        Pattern pat =
                Pattern.compile(
                        "^\\s*\\|\\s*`?(?<code>[A-Z][A-Z0-9_]+)`?\\s*\\|\\s*"
                                + "(?<severity>error|warning|note)\\s*\\|",
                        Pattern.MULTILINE);
        Matcher m = pat.matcher(text);
        while (m.find()) {
            severity.put(m.group("code"), m.group("severity"));
        }
        if (severity.isEmpty()) {
            throw new IOException("could not parse diagnostic codes from " + docsPath);
        }
        diagSeverity = severity;
    }

    private static void diag(
            Map<Integer, List<Diag>> diagnostics, int seq, String code, Integer pid) {
        Diag d = new Diag();
        d.code = code;
        d.pid = pid;
        d.severity = diagSeverity.get(code);
        diagnostics.computeIfAbsent(seq, k -> new ArrayList<>()).add(d);
    }

    private static void runOrphanHarvestPipeline(
            Map<Integer, Proc> processes,
            int justDiedPid,
            int seq,
            int tick,
            JsonObject policy,
            Map<Integer, List<Diag>> diagnostics,
            List<Map<String, Object>> harvestLog,
            Set<Edge> lineageEdges,
            Map<String, Integer> counters) {
        List<Integer> children = new ArrayList<>();
        for (Proc p : processes.values()) {
            if (p.pid != justDiedPid
                    && p.ppid == justDiedPid
                    && ("RUNNING".equals(p.state) || "ZOMBIE".equals(p.state))) {
                children.add(p.pid);
            }
        }
        children.sort(Integer::compareTo);
        for (int child : children) {
            diag(diagnostics, seq, "W_ORPHANED", child);
            counters.put("orphans_reparented", counters.get("orphans_reparented") + 1);
            if ("reparent_to_init".equals(policy.get("orphan_handling").getAsString())) {
                processes.get(child).ppid = policy.get("init_pid").getAsInt();
                if (policy.get("track_lineage").getAsBoolean()) {
                    lineageEdges.add(
                            new Edge(
                                    policy.get("init_pid").getAsInt(),
                                    child,
                                    "reparent_init"));
                }
            }
        }

        if (policy.get("implicit_init_harvest").getAsBoolean()
                && "reparent_to_init".equals(policy.get("orphan_handling").getAsString())) {
            for (int child : children) {
                Proc p = processes.get(child);
                if (p == null) {
                    continue;
                }
                if ("ZOMBIE".equals(p.state) && p.ppid == policy.get("init_pid").getAsInt()) {
                    p.state = "EXITED";
                    harvestLog.add(
                            harvestRow(
                                    policy.get("init_pid").getAsInt(),
                                    child,
                                    seq,
                                    tick,
                                    "init_harvest"));
                    diag(diagnostics, seq, "N_AUTO_HARVESTED", child);
                }
            }
        }

        if (policy.get("implicit_init_harvest").getAsBoolean()) {
            Proc p = processes.get(justDiedPid);
            if (p != null
                    && "ZOMBIE".equals(p.state)
                    && p.ppid == policy.get("init_pid").getAsInt()) {
                p.state = "EXITED";
                harvestLog.add(
                        harvestRow(
                                policy.get("init_pid").getAsInt(),
                                justDiedPid,
                                seq,
                                tick,
                                "init_harvest"));
                diag(diagnostics, seq, "N_AUTO_HARVESTED", justDiedPid);
            }
        }
    }

    private static Map<String, Object> harvestRow(
            int parentPid, int pid, int seq, int tick, String trigger) {
        Map<String, Object> row = new TreeMap<>();
        row.put("parent_pid", parentPid);
        row.put("pid", pid);
        row.put("seq", seq);
        row.put("tick", tick);
        row.put("trigger", trigger);
        return row;
    }

    private static List<List<Integer>> computeSccs(List<Integer> nodes, Set<Long> dedupedPair) {
        Map<Integer, List<Integer>> outN = new TreeMap<>();
        for (int n : nodes) {
            outN.put(n, new ArrayList<>());
        }
        for (long e : dedupedPair) {
            int a = unpackA(e);
            int b = unpackB(e);
            if (outN.containsKey(a)) {
                outN.get(a).add(b);
            }
        }
        for (List<Integer> ch : outN.values()) {
            ch.sort(Integer::compareTo);
        }

        Map<Integer, Integer> indices = new HashMap<>();
        Map<Integer, Integer> lowlink = new HashMap<>();
        Map<Integer, Boolean> onStack = new HashMap<>();
        List<Integer> stack = new ArrayList<>();
        int[] idxCounter = {0};
        List<List<Integer>> sccs = new ArrayList<>();

        for (int start : nodes) {
            if (indices.containsKey(start)) {
                continue;
            }
            List<Long> callStack = new ArrayList<>();
            callStack.add(pack(start, 0));
            while (!callStack.isEmpty()) {
                long top = callStack.get(callStack.size() - 1);
                int cur = unpackA(top);
                int childPos = unpackB(top);
                if (childPos == 0) {
                    indices.put(cur, idxCounter[0]);
                    lowlink.put(cur, idxCounter[0]);
                    idxCounter[0]++;
                    stack.add(cur);
                    onStack.put(cur, true);
                }
                List<Integer> children = outN.getOrDefault(cur, List.of());
                if (childPos < children.size()) {
                    int w = children.get(childPos);
                    callStack.set(callStack.size() - 1, pack(cur, childPos + 1));
                    if (!indices.containsKey(w)) {
                        callStack.add(pack(w, 0));
                    } else if (Boolean.TRUE.equals(onStack.get(w))) {
                        lowlink.put(cur, Math.min(lowlink.get(cur), indices.get(w)));
                    }
                } else {
                    if (lowlink.get(cur).equals(indices.get(cur))) {
                        List<Integer> scc = new ArrayList<>();
                        while (true) {
                            int x = stack.remove(stack.size() - 1);
                            onStack.put(x, false);
                            scc.add(x);
                            if (x == cur) {
                                break;
                            }
                        }
                        if (scc.size() > 1) {
                            scc.sort(Integer::compareTo);
                            sccs.add(scc);
                        }
                    }
                    callStack.remove(callStack.size() - 1);
                    if (!callStack.isEmpty()) {
                        long pv = callStack.get(callStack.size() - 1);
                        int parent = unpackA(pv);
                        lowlink.put(parent, Math.min(lowlink.get(parent), lowlink.get(cur)));
                    }
                }
            }
        }

        sccs.sort(Comparator.comparing(c -> c.get(0)));
        return sccs;
    }

    private static long pack(int a, int b) {
        return ((long) a << 32) | (b & 0xffffffffL);
    }

    private static int unpackA(long v) {
        return (int) (v >> 32);
    }

    private static int unpackB(long v) {
        return (int) v;
    }

    private static Map<String, Object> runSimulation(
            List<JsonObject> initialProcs, List<JsonObject> events, JsonObject policy) {
        Map<Integer, Proc> processes = new TreeMap<>();
        for (JsonObject p : initialProcs) {
            Proc proc = new Proc();
            proc.cmdline = p.get("cmdline").getAsString();
            proc.pid = p.get("pid").getAsInt();
            proc.ppid = p.get("ppid").getAsInt();
            proc.startTick = p.get("start_tick").getAsInt();
            proc.state = "RUNNING";
            proc.uid = p.get("uid").getAsInt();
            processes.put(proc.pid, proc);
        }
        Set<Integer> seenPids = new HashSet<>(processes.keySet());
        Map<Integer, List<Diag>> diagnostics = new TreeMap<>();
        List<Map<String, Object>> harvestLog = new ArrayList<>();
        Set<Edge> lineageEdges = new HashSet<>();
        Map<String, Integer> counters = new TreeMap<>();
        counters.put("forks_succeeded", 0);
        counters.put("forks_rejected", 0);
        counters.put("killed_by_signal", 0);
        counters.put("orphans_reparented", 0);
        counters.put("max_concurrent_processes", 0);

        Runnable updateMax =
                () -> {
                    int c = 0;
                    for (Proc p : processes.values()) {
                        if ("RUNNING".equals(p.state) || "ZOMBIE".equals(p.state)) {
                            c++;
                        }
                    }
                    if (c > counters.get("max_concurrent_processes")) {
                        counters.put("max_concurrent_processes", c);
                    }
                };
        updateMax.run();

        for (JsonObject ev : events) {
            int seq = ev.get("seq").getAsInt();
            int tick = ev.get("tick").getAsInt();
            String op = ev.get("op").getAsString();

            if ("fork".equals(op)) {
                Integer parentPid =
                        ev.has("parent_pid") && !ev.get("parent_pid").isJsonNull()
                                ? ev.get("parent_pid").getAsInt()
                                : null;
                int newPid = ev.get("pid").getAsInt();
                if (parentPid == null || !isRunning(processes, parentPid)) {
                    diag(diagnostics, seq, "E_INVALID_PARENT", parentPid);
                    counters.put("forks_rejected", counters.get("forks_rejected") + 1);
                    continue;
                }
                if (seenPids.contains(newPid)) {
                    diag(diagnostics, seq, "E_PID_REUSED", newPid);
                    counters.put("forks_rejected", counters.get("forks_rejected") + 1);
                    continue;
                }
                String cmdline =
                        ev.has("cmdline") && !ev.get("cmdline").isJsonNull()
                                ? ev.get("cmdline").getAsString()
                                : processes.get(parentPid).cmdline;
                Proc np = new Proc();
                np.cmdline = cmdline;
                np.pid = newPid;
                np.ppid = parentPid;
                np.startTick = tick;
                np.state = "RUNNING";
                np.uid = processes.get(parentPid).uid;
                processes.put(newPid, np);
                seenPids.add(newPid);
                counters.put("forks_succeeded", counters.get("forks_succeeded") + 1);
                if (policy.get("track_lineage").getAsBoolean()) {
                    lineageEdges.add(new Edge(parentPid, newPid, "fork"));
                }
                updateMax.run();
            } else if ("exit".equals(op)) {
                int pid = ev.get("pid").getAsInt();
                if (!processes.containsKey(pid)) {
                    diag(diagnostics, seq, "E_INVALID_TARGET", pid);
                    continue;
                }
                if (!"RUNNING".equals(processes.get(pid).state)) {
                    diag(diagnostics, seq, "E_DOUBLE_EXIT", pid);
                    continue;
                }
                Proc p = processes.get(pid);
                p.state = "ZOMBIE";
                p.exitTick = tick;
                p.exitCode = ev.get("exit_code").getAsInt();
                p.exitSignal = null;
                p.exitSeq = seq;
                runOrphanHarvestPipeline(
                        processes,
                        pid,
                        seq,
                        tick,
                        policy,
                        diagnostics,
                        harvestLog,
                        lineageEdges,
                        counters);
                updateMax.run();
            } else if ("kill".equals(op)) {
                int issuer = ev.get("pid").getAsInt();
                Integer target =
                        ev.has("target_pid") && !ev.get("target_pid").isJsonNull()
                                ? ev.get("target_pid").getAsInt()
                                : null;
                if (!isRunning(processes, issuer)) {
                    diag(diagnostics, seq, "E_INVALID_TARGET", issuer);
                    continue;
                }
                if (target == null || !isRunning(processes, target)) {
                    diag(diagnostics, seq, "E_INVALID_TARGET", target);
                    continue;
                }
                String sig = ev.get("signal").getAsString();
                if ("SIGCHLD".equals(sig)) {
                    continue;
                }
                Proc p = processes.get(target);
                p.state = "ZOMBIE";
                p.exitTick = tick;
                p.exitCode = null;
                p.exitSignal = sig;
                p.exitSeq = seq;
                diag(diagnostics, seq, "W_KILLED_BY_SIGNAL", target);
                counters.put("killed_by_signal", counters.get("killed_by_signal") + 1);
                runOrphanHarvestPipeline(
                        processes,
                        target,
                        seq,
                        tick,
                        policy,
                        diagnostics,
                        harvestLog,
                        lineageEdges,
                        counters);
                updateMax.run();
            } else if ("wait".equals(op)) {
                int issuer = ev.get("pid").getAsInt();
                Integer target =
                        ev.has("target_pid") && !ev.get("target_pid").isJsonNull()
                                ? ev.get("target_pid").getAsInt()
                                : null;
                if (!isRunning(processes, issuer)) {
                    diag(diagnostics, seq, "E_INVALID_TARGET", issuer);
                    continue;
                }
                int resolved;
                if (target != null) {
                    if (!processes.containsKey(target)) {
                        diag(diagnostics, seq, "E_INVALID_TARGET", target);
                        continue;
                    }
                    if (processes.get(target).ppid != issuer) {
                        diag(diagnostics, seq, "E_NOT_CHILD", target);
                        continue;
                    }
                    if ("RUNNING".equals(processes.get(target).state)) {
                        if ("diagnostic"
                                .equals(policy.get("wait_on_living_child").getAsString())) {
                            diag(diagnostics, seq, "E_NOT_ZOMBIE", target);
                        }
                        continue;
                    }
                    if ("EXITED".equals(processes.get(target).state)) {
                        diag(diagnostics, seq, "E_INVALID_TARGET", target);
                        continue;
                    }
                    resolved = target;
                } else {
                    List<Integer> zombies = new ArrayList<>();
                    for (Proc pr : processes.values()) {
                        if (pr.ppid == issuer && "ZOMBIE".equals(pr.state)) {
                            zombies.add(pr.pid);
                        }
                    }
                    zombies.sort(Integer::compareTo);
                    if (zombies.isEmpty()) {
                        diag(diagnostics, seq, "E_NOT_ZOMBIE", null);
                        continue;
                    }
                    resolved = zombies.get(0);
                }
                processes.get(resolved).state = "EXITED";
                diag(diagnostics, seq, "N_HARVESTED", resolved);
                harvestLog.add(harvestRow(issuer, resolved, seq, tick, "wait"));
                updateMax.run();
            } else if ("exec".equals(op)) {
                int issuer = ev.get("pid").getAsInt();
                if (!isRunning(processes, issuer)) {
                    diag(diagnostics, seq, "E_INVALID_TARGET", issuer);
                    continue;
                }
                if (!ev.has("cmdline") || ev.get("cmdline").isJsonNull()) {
                    continue;
                }
                processes.get(issuer).cmdline = ev.get("cmdline").getAsString();
            }
        }

        for (Proc p : processes.values()) {
            if ("ZOMBIE".equals(p.state)) {
                int s = p.exitSeq != null ? p.exitSeq : 0;
                diag(diagnostics, s, "W_ZOMBIE_LEAK", p.pid);
            }
        }

        List<Map<String, Object>> procRows = new ArrayList<>();
        for (Proc p : processes.values()) {
            Map<String, Object> row = new TreeMap<>();
            row.put("cmdline", p.cmdline);
            row.put("exit_code", p.exitCode);
            row.put("exit_signal", p.exitSignal);
            row.put("exit_tick", p.exitTick);
            row.put("pid", p.pid);
            row.put("ppid", p.ppid);
            row.put("start_tick", p.startTick);
            row.put("state", p.state);
            row.put("uid", p.uid);
            procRows.add(row);
        }
        procRows.sort(Comparator.comparingInt(r -> (Integer) r.get("pid")));

        List<Map<String, Object>> diagEvents = new ArrayList<>();
        List<Integer> diagSeqs = new ArrayList<>(diagnostics.keySet());
        diagSeqs.sort(Integer::compareTo);
        for (int seq : diagSeqs) {
            List<Diag> diags = diagnostics.get(seq);
            diags.sort(
                    Comparator.<Diag>comparingInt(d -> SEVERITY_RANK.get(d.severity))
                            .thenComparing(d -> d.code)
                            .thenComparingInt(d -> d.pid == null ? -1 : 0)
                            .thenComparingInt(d -> d.pid == null ? 0 : d.pid));
            List<Map<String, Object>> diagRows = new ArrayList<>();
            for (Diag d : diags) {
                Map<String, Object> row = new TreeMap<>();
                row.put("code", d.code);
                row.put("pid", d.pid);
                row.put("severity", d.severity);
                diagRows.add(row);
            }
            Map<String, Object> evRow = new TreeMap<>();
            evRow.put("diagnostics", diagRows);
            evRow.put("seq", seq);
            diagEvents.add(evRow);
        }

        Map<String, Object> lineageDoc;
        if (policy.get("track_lineage").getAsBoolean()) {
            Set<Integer> nodesSet = new TreeSet<>(seenPids);
            List<Edge> edgesSorted = new ArrayList<>(lineageEdges);
            edgesSorted.sort(
                    Comparator.<Edge>comparingInt(e -> e.from)
                            .thenComparingInt(e -> e.to)
                            .thenComparing(e -> e.type));
            for (Edge e : edgesSorted) {
                nodesSet.add(e.from);
                nodesSet.add(e.to);
            }
            List<Integer> nodesSorted = new ArrayList<>(nodesSet);
            Set<Long> deduped = new HashSet<>();
            for (Edge e : edgesSorted) {
                deduped.add(pack(e.from, e.to));
            }
            Map<Integer, Integer> inCount = new TreeMap<>();
            Map<Integer, Integer> outCount = new TreeMap<>();
            for (int n : nodesSorted) {
                inCount.put(n, 0);
                outCount.put(n, 0);
            }
            for (long pair : deduped) {
                int a = unpackA(pair);
                int b = unpackB(pair);
                outCount.put(a, outCount.get(a) + 1);
                inCount.put(b, inCount.get(b) + 1);
            }
            List<Map<String, Object>> nodeArr = new ArrayList<>();
            for (int n : nodesSorted) {
                Map<String, Object> row = new TreeMap<>();
                row.put("id", n);
                row.put("in_degree", inCount.get(n));
                row.put("out_degree", outCount.get(n));
                nodeArr.add(row);
            }
            List<Map<String, Object>> edgeArr = new ArrayList<>();
            for (Edge e : edgesSorted) {
                Map<String, Object> row = new TreeMap<>();
                row.put("from", e.from);
                row.put("to", e.to);
                row.put("type", e.type);
                edgeArr.add(row);
            }
            List<List<Integer>> cycles = computeSccs(nodesSorted, deduped);
            lineageDoc = new TreeMap<>();
            lineageDoc.put("cycles", cycles);
            lineageDoc.put("edges", edgeArr);
            lineageDoc.put("nodes", nodeArr);
        } else {
            lineageDoc = new TreeMap<>();
            lineageDoc.put("cycles", List.of());
            lineageDoc.put("edges", List.of());
            lineageDoc.put("nodes", List.of());
        }

        int autoHarvested = 0;
        int explicitHarvested = 0;
        for (Map<String, Object> r : harvestLog) {
            if ("init_harvest".equals(r.get("trigger"))) {
                autoHarvested++;
            }
            if ("wait".equals(r.get("trigger"))) {
                explicitHarvested++;
            }
        }
        int finalAlive = 0;
        int zombies = 0;
        Set<Integer> users = new TreeSet<>();
        for (Proc p : processes.values()) {
            if ("RUNNING".equals(p.state)) {
                finalAlive++;
                users.add(p.uid);
            }
            if ("ZOMBIE".equals(p.state)) {
                zombies++;
            }
        }

        Map<String, Object> summary = new TreeMap<>();
        summary.put("auto_harvested", autoHarvested);
        summary.put("events_with_diagnostics", diagEvents.size());
        summary.put("explicit_harvested", explicitHarvested);
        summary.put("final_alive_count", finalAlive);
        summary.put("forks_rejected", counters.get("forks_rejected"));
        summary.put("forks_succeeded", counters.get("forks_succeeded"));
        summary.put("killed_by_signal", counters.get("killed_by_signal"));
        summary.put("max_concurrent_processes", counters.get("max_concurrent_processes"));
        summary.put("orphans_reparented", counters.get("orphans_reparented"));
        summary.put("total_events", events.size());
        summary.put("users_at_end", new ArrayList<>(users));
        summary.put("zombies_at_end", zombies);

        Map<String, Object> out = new TreeMap<>();
        out.put("process_state", Map.of("processes", procRows));
        out.put("harvest_log", Map.of("harvests", harvestLog));
        out.put("process_diagnostics", Map.of("events", diagEvents));
        out.put("lineage_graph", lineageDoc);
        out.put("summary", summary);
        return out;
    }

    private static boolean isRunning(Map<Integer, Proc> processes, Integer pid) {
        return pid != null && processes.containsKey(pid) && "RUNNING".equals(processes.get(pid).state);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        Path docs = inDir.getParent().resolve("docs").resolve("diagnostics.md");
        if (!Files.isRegularFile(docs)) {
            docs = Path.of("/app/docs/diagnostics.md");
        }
        loadDiagCodes(docs);

        JsonObject procsDoc = readObject(inDir.resolve("processes.json"));
        JsonObject eventsDoc = readObject(inDir.resolve("events.json"));
        JsonObject policy = readObject(inDir.resolve("policy.json"));

        List<JsonObject> initialProcs = new ArrayList<>();
        for (JsonElement el : procsDoc.getAsJsonArray("processes")) {
            initialProcs.add(el.getAsJsonObject());
        }
        List<JsonObject> events = new ArrayList<>();
        for (JsonElement el : eventsDoc.getAsJsonArray("events")) {
            events.add(el.getAsJsonObject());
        }

        Map<String, Object> outputs = runSimulation(initialProcs, events, policy);
        writeCanonical(outDir.resolve("process_state.json"), outputs.get("process_state"));
        writeCanonical(outDir.resolve("harvest_log.json"), outputs.get("harvest_log"));
        writeCanonical(
                outDir.resolve("process_diagnostics.json"), outputs.get("process_diagnostics"));
        writeCanonical(outDir.resolve("lineage_graph.json"), outputs.get("lineage_graph"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
