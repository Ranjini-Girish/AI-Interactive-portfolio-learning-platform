import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import java.util.stream.*;

@SuppressWarnings("unchecked")
public class RelayHopAudit {
    static String dataDir() {
        return System.getenv().getOrDefault("JRH_DATA_DIR", "/app/relayhop");
    }

    static String auditDir() {
        return System.getenv().getOrDefault("JRH_AUDIT_DIR", "/app/audit");
    }

    static Map<String, Object> readJson(Path p) throws Exception {
        return new Gson().fromJson(Files.readString(p, StandardCharsets.UTF_8), Map.class);
    }

    static void writeJson(Path p, Object obj) throws Exception {
        Gson gson = new GsonBuilder().setPrettyPrinting().create();
        Files.writeString(p, gson.toJson(obj) + "\n", StandardCharsets.UTF_8);
    }

    static List<Path> sortedGlob(Path dir, String suffix) throws Exception {
        if (!Files.isDirectory(dir)) return List.of();
        try (var st = Files.list(dir)) {
            return st.filter(x -> x.toString().endsWith(suffix)).sorted().toList();
        }
    }

    static int capCore(String h, Map<String, Integer> base, Map<String, Integer> delta,
                       Map<String, Boolean> halted) {
        if (halted.getOrDefault(h, false)) return 0;
        int v = base.get(h) + delta.get(h);
        return v < 1 ? 1 : v;
    }

    public static void main(String[] args) throws Exception {
        Path data = Paths.get(dataDir());
        Path audit = Paths.get(auditDir());
        Files.createDirectories(audit);

        Map<String, Object> pol = readJson(data.resolve("policy.json"));
        Map<String, Object> incFile = readJson(data.resolve("incidents.json"));
        int carryMax = ((Number) pol.get("carry_max")).intValue();
        List<Integer> epochs = (List<Integer>) pol.get("epochs");
        List<String> hopsOrder = (List<String>) pol.get("hops_order");

        Map<String, Integer> base = new HashMap<>();
        for (Path p : sortedGlob(data.resolve("hops"), ".json")) {
            Map<String, Object> hf = readJson(p);
            base.put((String) hf.get("hop_id"), ((Number) hf.get("base_cap")).intValue());
        }

        record Flow(String flowId, int epoch, String hopId, int bytes) {}
        List<Flow> flows = new ArrayList<>();
        for (Path p : sortedGlob(data.resolve("flows"), ".json")) {
            Map<String, Object> ff = readJson(p);
            flows.add(new Flow((String) ff.get("flow_id"), ((Number) ff.get("epoch")).intValue(),
                (String) ff.get("hop_id"), ((Number) ff.get("bytes")).intValue()));
        }

        Set<Integer> epochSet = new HashSet<>(epochs);
        for (Flow f : flows) {
            if (!epochSet.contains(f.epoch()) || !base.containsKey(f.hopId())) System.exit(1);
        }
        if (new HashSet<>(hopsOrder).size() != hopsOrder.size() || hopsOrder.size() != base.size()) {
            System.exit(1);
        }
        for (String h : base.keySet()) {
            if (!hopsOrder.contains(h)) System.exit(1);
        }

        Map<String, Integer> delta = new HashMap<>();
        Map<String, Integer> carry = new HashMap<>();
        Map<String, Boolean> halted = new HashMap<>();
        for (String h : hopsOrder) {
            delta.put(h, 0);
            carry.put(h, 0);
            halted.put(h, false);
        }

        List<Map<String, Object>> admissions = new ArrayList<>();
        List<Map<String, Object>> denials = new ArrayList<>();
        List<Map<String, Object>> ledgers = new ArrayList<>();

        for (int e : epochs) {
            for (Map<String, Object> inc : (List<Map<String, Object>>) incFile.get("incidents")) {
                if (((Number) inc.get("epoch")).intValue() != e) continue;
                String kind = (String) inc.get("kind");
                if ("noop".equals(kind)) continue;
                String h = (String) inc.get("hop_id");
                switch (kind) {
                    case "cap_add" -> delta.merge(h, ((Number) inc.get("delta")).intValue(), Integer::sum);
                    case "halt_hop" -> { halted.put(h, true); carry.put(h, 0); }
                    case "resume_hop" -> { halted.put(h, false); carry.put(h, 0); }
                    default -> System.exit(1);
                }
            }

            Map<String, Integer> cin = new HashMap<>();
            Map<String, Integer> used = new HashMap<>();
            for (String h : hopsOrder) {
                cin.put(h, carry.get(h));
                used.put(h, 0);
            }

            List<Flow> epochFlows = flows.stream().filter(f -> f.epoch() == e)
                .sorted(Comparator.comparing(Flow::hopId).thenComparing(Flow::flowId)).toList();

            for (Flow f : epochFlows) {
                String h = f.hopId();
                int b = f.bytes();
                int avail = capCore(h, base, delta, halted) + cin.get(h) - used.get(h);
                if (avail < 0) avail = 0;
                if (b <= avail) {
                    used.merge(h, b, Integer::sum);
                    admissions.add(Map.of("bytes", b, "epoch", e, "flow_id", f.flowId(), "hop_id", h));
                } else {
                    denials.add(Map.of("available", avail, "epoch", e, "flow_id", f.flowId(), "hop_id", h,
                        "requested", b));
                }
            }

            for (String h : hopsOrder) {
                int cc = capCore(h, base, delta, halted);
                int rem = cc + cin.get(h) - used.get(h);
                int cout = Math.min(carryMax, Math.max(0, rem));
                if (halted.get(h)) cout = 0;
                ledgers.add(Map.of("cap_core", cc, "carry_in", cin.get(h), "carry_out", cout,
                    "epoch", e, "hop_id", h, "used", used.get(h)));
                carry.put(h, cout);
            }
        }

        Comparator<Map<String, Object>> rowCmp = Comparator
            .comparingInt((Map<String, Object> m) -> (Integer) m.get("epoch"))
            .thenComparing(m -> (String) m.get("hop_id"))
            .thenComparing(m -> (String) m.get("flow_id"));
        admissions.sort(rowCmp);
        denials.sort(rowCmp);
        ledgers.sort(Comparator
            .comparingInt((Map<String, Object> m) -> (Integer) m.get("epoch"))
            .thenComparing(m -> (String) m.get("hop_id")));

        List<String> applied = ((List<Map<String, Object>>) incFile.get("incidents")).stream()
            .map(m -> (String) m.get("kind")).toList();
        int maxEp = 0;
        for (Map<String, Object> inc : (List<Map<String, Object>>) incFile.get("incidents")) {
            maxEp = Math.max(maxEp, ((Number) inc.get("epoch")).intValue());
        }
        for (Map<String, Object> a : admissions) maxEp = Math.max(maxEp, (Integer) a.get("epoch"));
        for (Map<String, Object> d : denials) maxEp = Math.max(maxEp, (Integer) d.get("epoch"));

        int totAdm = admissions.size();
        int totAdmBytes = admissions.stream().mapToInt(a -> (Integer) a.get("bytes")).sum();
        int totDen = denials.size();
        int totDenBytes = denials.stream().mapToInt(d -> (Integer) d.get("requested")).sum();

        writeJson(audit.resolve("admissions.json"), Map.of("admissions", admissions));
        writeJson(audit.resolve("denials.json"), Map.of("denials", denials));
        writeJson(audit.resolve("carry_ledgers.json"), Map.of("rows", ledgers));
        writeJson(audit.resolve("summary.json"), Map.of(
            "incidents_applied", applied,
            "max_epoch", maxEp,
            "total_admissions", totAdm,
            "total_admitted_bytes", totAdmBytes,
            "total_denials", totDen,
            "total_denied_bytes", totDenBytes));
    }
}
