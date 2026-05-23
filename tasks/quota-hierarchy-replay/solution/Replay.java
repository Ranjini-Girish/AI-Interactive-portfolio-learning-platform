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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class Replay {
    private static final String[] RESOURCES = {"cpu", "memory", "storage"};

    private static Map<String, Long> zeroRes() {
        Map<String, Long> m = new LinkedHashMap<>();
        for (String r : RESOURCES) {
            m.put(r, 0L);
        }
        return m;
    }

    private static Map<String, Long> addRes(Map<String, Long> a, Map<String, Long> b) {
        Map<String, Long> out = new LinkedHashMap<>();
        for (String r : RESOURCES) {
            out.put(r, a.get(r) + b.get(r));
        }
        return out;
    }

    private static Map<String, Long> subRes(Map<String, Long> a, Map<String, Long> b) {
        Map<String, Long> out = new LinkedHashMap<>();
        for (String r : RESOURCES) {
            out.put(r, a.get(r) - b.get(r));
        }
        return out;
    }

    private static Map<String, Long> resFromJson(JsonObject ev) {
        Map<String, Long> m = new LinkedHashMap<>();
        JsonObject res = ev.getAsJsonObject("resources");
        for (String r : RESOURCES) {
            m.put(r, res.get(r).getAsLong());
        }
        return m;
    }

    private static Map<String, Object> simulate(
            JsonObject nsData, JsonObject allocData, JsonObject config) throws IOException {
        JsonArray namespaces = nsData.getAsJsonArray("namespaces");
        JsonArray events = allocData.getAsJsonArray("events");

        Map<String, JsonObject> nodes = new TreeMap<>();
        Map<String, List<String>> children = new TreeMap<>();
        String root = null;
        for (JsonElement el : namespaces) {
            JsonObject n = el.getAsJsonObject();
            String name = n.get("name").getAsString();
            nodes.put(name, n);
            children.put(name, new ArrayList<>());
            if (n.get("parent").isJsonNull()) {
                root = name;
            } else {
                children.get(n.get("parent").getAsString()).add(name);
            }
        }
        for (List<String> ch : children.values()) {
            ch.sort(String::compareTo);
        }

        Map<String, Map<String, Long>> usedOwn = new TreeMap<>();
        Map<String, Map<String, Long>> usedSubtree = new TreeMap<>();
        for (String name : nodes.keySet()) {
            usedOwn.put(name, zeroRes());
            usedSubtree.put(name, zeroRes());
        }

        List<Map<String, Object>> decisions = new ArrayList<>();

        for (JsonElement evEl : events) {
            JsonObject ev = evEl.getAsJsonObject();
            String ns = ev.get("namespace").getAsString();
            String op = ev.get("op").getAsString();
            Map<String, Long> res = resFromJson(ev);
            Map<String, Object> base = new LinkedHashMap<>();
            base.put("event_id", ev.get("event_id").getAsString());
            base.put("ts_unix_ms", ev.get("ts_unix_ms").getAsLong());
            base.put("namespace", ns);
            base.put("op", op);

            if (!nodes.containsKey(ns)) {
                if ("allocate".equals(op)) {
                    base.put("decision", "rejected");
                    base.put("reason", "unknown_namespace");
                    base.put("blocking_namespace", null);
                    base.put("resources_granted", zeroRes());
                    decisions.add(base);
                } else {
                    String action = config.get("release_unknown_action").getAsString();
                    if ("ignore".equals(action)) {
                        base.put("decision", "ignored");
                        base.put("reason", "release_unknown_ignored");
                    } else {
                        base.put("decision", "rejected");
                        base.put("reason", "release_unknown_rejected");
                    }
                    base.put("blocking_namespace", null);
                    base.put("resources_granted", zeroRes());
                    decisions.add(base);
                }
                continue;
            }

            if ("allocate".equals(op)) {
                List<String> chain = ancestorsChain(nodes, ns);
                String blocking = null;
                for (String anc : chain) {
                    JsonObject limits = nodes.get(anc).getAsJsonObject("limits");
                    Map<String, Long> post = addRes(usedSubtree.get(anc), res);
                    if (overLimit(post, limits)) {
                        blocking = anc;
                        break;
                    }
                }
                if (blocking != null) {
                    base.put("decision", "rejected");
                    base.put("reason", "limit_exceeded");
                    base.put("blocking_namespace", blocking);
                    base.put("resources_granted", zeroRes());
                    decisions.add(base);
                    continue;
                }
                usedOwn.put(ns, addRes(usedOwn.get(ns), res));
                for (String anc : chain) {
                    usedSubtree.put(anc, addRes(usedSubtree.get(anc), res));
                }
                base.put("decision", "admitted");
                base.put("reason", "under_limits");
                base.put("blocking_namespace", null);
                base.put("resources_granted", new LinkedHashMap<>(res));
                decisions.add(base);
            } else {
                if (anyOver(res, usedOwn.get(ns))) {
                    base.put("decision", "rejected");
                    base.put("reason", "release_underflow");
                    base.put("blocking_namespace", ns);
                    base.put("resources_granted", zeroRes());
                    decisions.add(base);
                    continue;
                }
                usedOwn.put(ns, subRes(usedOwn.get(ns), res));
                for (String anc : ancestorsChain(nodes, ns)) {
                    usedSubtree.put(anc, subRes(usedSubtree.get(anc), res));
                }
                base.put("decision", "admitted");
                base.put("reason", "under_limits");
                base.put("blocking_namespace", null);
                base.put("resources_granted", new LinkedHashMap<>(res));
                decisions.add(base);
            }
        }

        decisions.sort(Comparator.comparing(d -> (String) d.get("event_id")));

        Map<String, Integer> descendantsCount = new HashMap<>();
        if (root != null) {
            countDesc(children, root, descendantsCount);
        }

        List<Map<String, Object>> namespaceUsage = new ArrayList<>();
        for (String name : nodes.keySet()) {
            JsonObject limits = nodes.get(name).getAsJsonObject("limits");
            Map<String, Long> usubtree = usedSubtree.get(name);
            Map<String, Long> headroom = new LinkedHashMap<>();
            for (String r : RESOURCES) {
                headroom.put(r, limits.get(r).getAsLong() - usubtree.get(r));
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("name", name);
            row.put("limits", limitsToMap(limits));
            row.put("used_own", new LinkedHashMap<>(usedOwn.get(name)));
            row.put("used_subtree", new LinkedHashMap<>(usubtree));
            row.put("headroom", headroom);
            row.put("descendant_count", descendantsCount.getOrDefault(name, 0));
            namespaceUsage.add(row);
        }

        List<Map<String, Object>> rollup = new ArrayList<>();
        if (root != null) {
            dfsRollup(children, usedSubtree, root, null, 0, rollup);
        }

        Map<String, JsonObject> byId = new HashMap<>();
        for (JsonElement evEl : events) {
            JsonObject ev = evEl.getAsJsonObject();
            byId.put(ev.get("event_id").getAsString(), ev);
        }
        List<Map<String, Object>> violations = new ArrayList<>();
        for (Map<String, Object> d : decisions) {
            if (!"rejected".equals(d.get("decision"))) {
                continue;
            }
            JsonObject ev = byId.get(d.get("event_id"));
            Map<String, Object> v = new LinkedHashMap<>(d);
            v.put("attempted_resources", resFromJson(ev));
            violations.add(v);
        }
        violations.sort(Comparator.comparing(v -> (String) v.get("event_id")));

        int admitted = 0, rejected = 0, ignored = 0, uk = 0, le = 0, ru = 0;
        for (Map<String, Object> d : decisions) {
            String dec = (String) d.get("decision");
            String reason = (String) d.get("reason");
            if ("admitted".equals(dec)) {
                admitted++;
            } else if ("rejected".equals(dec)) {
                rejected++;
            } else {
                ignored++;
            }
            if ("unknown_namespace".equals(reason)) {
                uk++;
            }
            if ("limit_exceeded".equals(reason)) {
                le++;
            }
            if ("release_underflow".equals(reason)) {
                ru++;
            }
        }

        String hottest = null;
        long best = -1;
        for (String name : nodes.keySet()) {
            long s = 0;
            for (String r : RESOURCES) {
                s += usedSubtree.get(name).get(r);
            }
            if (s > best) {
                best = s;
                hottest = name;
            }
        }
        if (best <= 0) {
            hottest = null;
        }

        Map<String, Object> summary = new LinkedHashMap<>();
        summary.put("total_events", decisions.size());
        summary.put("total_namespaces", nodes.size());
        summary.put("admitted_events", admitted);
        summary.put("rejected_events", rejected);
        summary.put("ignored_events", ignored);
        summary.put("unknown_namespace_rejects", uk);
        summary.put("limit_exceeded_rejects", le);
        summary.put("release_underflow_rejects", ru);
        summary.put("hottest_namespace", hottest);

        Map<String, Object> out = new LinkedHashMap<>();
        out.put("allocation_decisions", Map.of("decisions", decisions));
        out.put("namespace_usage", Map.of("namespaces", namespaceUsage));
        out.put("rollup_tree", Map.of("tree", rollup));
        out.put("violations", Map.of("violations", violations));
        out.put("summary", summary);
        return out;
    }

    private static boolean overLimit(Map<String, Long> post, JsonObject limits) {
        for (String r : RESOURCES) {
            if (post.get(r) > limits.get(r).getAsLong()) {
                return true;
            }
        }
        return false;
    }

    private static boolean anyOver(Map<String, Long> res, Map<String, Long> own) {
        for (String r : RESOURCES) {
            if (res.get(r) > own.get(r)) {
                return true;
            }
        }
        return false;
    }

    private static Map<String, Long> limitsToMap(JsonObject limits) {
        Map<String, Long> m = new LinkedHashMap<>();
        for (String r : RESOURCES) {
            m.put(r, limits.get(r).getAsLong());
        }
        return m;
    }

    private static List<String> ancestorsChain(Map<String, JsonObject> nodes, String name) {
        List<String> chain = new ArrayList<>();
        String cur = name;
        while (cur != null) {
            chain.add(cur);
            JsonElement p = nodes.get(cur).get("parent");
            cur = p.isJsonNull() ? null : p.getAsString();
        }
        return chain;
    }

    private static int countDesc(
            Map<String, List<String>> children, String node, Map<String, Integer> out) {
        int c = 0;
        for (String child : children.get(node)) {
            c += 1 + countDesc(children, child, out);
        }
        out.put(node, c);
        return c;
    }

    private static void dfsRollup(
            Map<String, List<String>> children,
            Map<String, Map<String, Long>> usedSubtree,
            String name,
            String parent,
            int depth,
            List<Map<String, Object>> rollup) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("name", name);
        row.put("parent", parent);
        row.put("depth", depth);
        row.put("children", new ArrayList<>(children.get(name)));
        row.put("used_subtree", new LinkedHashMap<>(usedSubtree.get(name)));
        rollup.add(row);
        for (String child : children.get(name)) {
            dfsRollup(children, usedSubtree, child, name, depth + 1, rollup);
        }
    }

    private static void writeCanonical(Path path, Object value) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        Files.writeString(path, gson.toJson(value) + "\n", StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: Replay <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject nsData =
                JsonParser.parseString(
                                Files.readString(
                                        inDir.resolve("namespaces.json"), StandardCharsets.UTF_8))
                        .getAsJsonObject();
        JsonObject allocData =
                JsonParser.parseString(
                                Files.readString(
                                        inDir.resolve("allocations.json"), StandardCharsets.UTF_8))
                        .getAsJsonObject();
        JsonObject config =
                JsonParser.parseString(
                                Files.readString(
                                        inDir.resolve("config.json"), StandardCharsets.UTF_8))
                        .getAsJsonObject();

        Map<String, Object> outputs = simulate(nsData, allocData, config);
        writeCanonical(outDir.resolve("allocation_decisions.json"), outputs.get("allocation_decisions"));
        writeCanonical(outDir.resolve("namespace_usage.json"), outputs.get("namespace_usage"));
        writeCanonical(outDir.resolve("rollup_tree.json"), outputs.get("rollup_tree"));
        writeCanonical(outDir.resolve("violations.json"), outputs.get("violations"));
        writeCanonical(outDir.resolve("summary.json"), outputs.get("summary"));
    }
}
