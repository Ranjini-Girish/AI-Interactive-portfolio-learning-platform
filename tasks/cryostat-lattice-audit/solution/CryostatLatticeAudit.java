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
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Cryostat lattice readout audit oracle. */
public final class CryostatLatticeAudit {

    private CryostatLatticeAudit() {}

    public static void main(String[] args) throws IOException {
        Path dataDir;
        Path auditDir;
        if (args.length == 2) {
            dataDir = Path.of(args[0]);
            auditDir = Path.of(args[1]);
        } else if (args.length == 0) {
            dataDir = Path.of(envOr("CLR_DATA_DIR", "/app/cryostat"));
            auditDir = Path.of(envOr("CLR_AUDIT_DIR", "/app/audit"));
        } else {
            System.err.println("usage: CryostatLatticeAudit [<dataDir> <auditDir>]");
            System.exit(1);
            return;
        }
        run(dataDir, auditDir);
    }

    private static String envOr(String name, String def) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? def : v;
    }

    private static void run(Path root, Path auditDir) throws IOException {
        Files.createDirectories(auditDir);

        JsonObject pool = loadJson(root.resolve("pool_state.json"));
        int asOf = pool.get("as_of_day").getAsInt();
        int tolP = pool.get("tol_millic_primary").getAsInt();
        int tolS = pool.get("tol_millic_secondary").getAsInt();
        int driftGrace = pool.get("drift_grace_days").getAsInt();
        int driftPerDay = pool.get("drift_per_day").getAsInt();
        int k = pool.get("recent_window_k").getAsInt();
        boolean ovActive = false;
        int ovAdd = 0;
        Set<String> ovIds = new HashSet<>();
        if (pool.has("overlay") && !pool.get("overlay").isJsonNull()) {
            JsonObject ov = pool.getAsJsonObject("overlay");
            ovActive = ov.get("active").getAsBoolean();
            ovAdd = ov.get("add_millic").getAsInt();
            for (JsonElement el : ov.getAsJsonArray("sensor_ids")) {
                ovIds.add(el.getAsString());
            }
        }

        JsonObject lin = loadJson(root.resolve("calibration").resolve("linear.json"));
        int a = lin.get("a").getAsInt();
        int b = lin.get("b").getAsInt();

        JsonArray rawEdges = loadJsonArray(root.resolve("thermal").resolve("edges.json"));
        List<CanonEdge> edges = new ArrayList<>();
        for (JsonElement el : rawEdges) {
            JsonObject e = el.getAsJsonObject();
            String u = e.get("u").getAsString();
            String v = e.get("v").getAsString();
            if (u.compareTo(v) > 0) {
                String tmp = u;
                u = v;
                v = tmp;
            }
            edges.add(new CanonEdge(u, v, e.get("w").getAsInt()));
        }
        edges.sort(
                Comparator.comparing((CanonEdge e) -> e.a)
                        .thenComparing(e -> e.b));
        int edgeCount = edges.size();

        JsonArray readingsArr = loadJsonArray(root.resolve("readings").resolve("readings.json"));
        int readingRows = readingsArr.size();
        List<ReadingRow> readings = new ArrayList<>();
        for (JsonElement el : readingsArr) {
            JsonObject r = el.getAsJsonObject();
            readings.add(
                    new ReadingRow(
                            r.get("sensor_id").getAsString(),
                            r.get("day").getAsInt(),
                            r.get("adc").getAsInt()));
        }

        JsonArray incArr = loadJsonArray(root.resolve("incidents").resolve("incident_log.json"));
        List<Incident> incidents = new ArrayList<>();
        for (JsonElement el : incArr) {
            JsonObject o = el.getAsJsonObject();
            Incident inc = new Incident();
            inc.kind = o.get("kind").getAsString();
            inc.day = o.get("day").getAsInt();
            inc.accepted = !o.has("accepted") || o.get("accepted").getAsBoolean();
            if (o.has("strap_id") && !o.get("strap_id").isJsonNull()) {
                inc.strapId = o.get("strap_id").getAsString();
            }
            if (o.has("rig_id") && !o.get("rig_id").isJsonNull()) {
                inc.rigId = o.get("rig_id").getAsString();
            }
            if (o.has("delta_millic") && !o.get("delta_millic").isJsonNull()) {
                inc.deltaMillic = o.get("delta_millic").getAsInt();
            }
            if (o.has("seed_sensors") && o.get("seed_sensors").isJsonArray()) {
                inc.seedSensors = new ArrayList<>();
                for (JsonElement s : o.getAsJsonArray("seed_sensors")) {
                    inc.seedSensors.add(s.getAsString());
                }
            }
            incidents.add(inc);
        }

        Map<String, SensorRec> sensors = new TreeMap<>();
        List<String> sensorIds = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(root.resolve("sensors"))) {
            List<Path> files = new ArrayList<>();
            for (Path p : stream) {
                if (Files.isRegularFile(p) && p.toString().endsWith(".json")) {
                    files.add(p);
                }
            }
            files.sort(Comparator.comparing(p -> p.getFileName().toString()));
            for (Path p : files) {
                JsonObject rec = loadJson(p);
                SensorRec sr = new SensorRec();
                sr.sensorId = rec.get("sensor_id").getAsString();
                sr.strapId = rec.get("strap_id").getAsString();
                sr.rigId = rec.get("rig_id").getAsString();
                sr.tier = rec.get("tier").getAsString();
                sr.commissionedDay = rec.get("commissioned_day").getAsInt();
                sr.lastCalibrationDay = rec.get("last_calibration_day").getAsInt();
                JsonArray nr = rec.getAsJsonArray("nominal_range_millic");
                sr.nominalLow = nr.get(0).getAsInt();
                sr.nominalHigh = nr.get(1).getAsInt();
                sensors.put(sr.sensorId, sr);
                sensorIds.add(sr.sensorId);
            }
        }

        Map<String, List<ReadingRow>> bySensor = new TreeMap<>();
        for (String sid : sensorIds) {
            bySensor.put(sid, new ArrayList<>());
        }
        for (ReadingRow r : readings) {
            if (sensors.containsKey(r.sensorId)) {
                bySensor.get(r.sensorId).add(r);
            }
        }

        Map<String, ChosenReading> chosen = new TreeMap<>();
        Map<String, Boolean> hasAnyInWindow = new TreeMap<>();
        for (String sid : sensorIds) {
            SensorRec rec = sensors.get(sid);
            List<ReadingRow> inWindow = new ArrayList<>();
            for (ReadingRow r : bySensor.get(sid)) {
                if (r.day >= rec.commissionedDay && r.day <= asOf) {
                    inWindow.add(r);
                }
            }
            hasAnyInWindow.put(sid, !inWindow.isEmpty());
            List<ReadingRow> kept = new ArrayList<>();
            for (ReadingRow r : inWindow) {
                if (r.adc > 0) {
                    kept.add(r);
                }
            }
            if (kept.isEmpty()) {
                chosen.put(sid, new ChosenReading(false));
                continue;
            }
            kept.sort(
                    (x, y) -> {
                        if (x.day != y.day) {
                            return Integer.compare(y.day, x.day);
                        }
                        return Integer.compare(y.adc, x.adc);
                    });
            if (kept.size() > k) {
                kept = new ArrayList<>(kept.subList(0, k));
            }
            List<Integer> adcs = new ArrayList<>();
            int maxDay = kept.get(0).day;
            for (ReadingRow r : kept) {
                adcs.add(r.adc);
                if (r.day > maxDay) {
                    maxDay = r.day;
                }
            }
            chosen.put(sid, new ChosenReading(maxDay, medianInt(adcs), true));
        }

        Map<String, Set<String>> adj = new TreeMap<>();
        for (String sid : sensorIds) {
            adj.put(sid, new HashSet<>());
        }
        for (CanonEdge e : edges) {
            adj.get(e.a).add(e.b);
            adj.get(e.b).add(e.a);
        }

        Set<String> faultedCc = new HashSet<>();
        Map<String, Integer> strapDayByStrap = new HashMap<>();
        Set<Integer> latticeDays = new HashSet<>();
        for (Incident inc : incidents) {
            if (!inc.accepted || asOf < inc.day) {
                continue;
            }
            if ("lattice_fault".equals(inc.kind)) {
                faultedCc.addAll(componentsTouchingSeeds(inc.seedSensors, adj, sensors));
                latticeDays.add(inc.day);
            } else if ("strap_quench".equals(inc.kind)) {
                strapDayByStrap.put(inc.strapId, inc.day);
            }
        }
        List<Integer> latticeDayList = new ArrayList<>(latticeDays);
        latticeDayList.sort(Integer::compareTo);

        Map<String, Integer> preT = new TreeMap<>();
        Map<String, Set<String>> marksBySensor = new TreeMap<>();
        for (String sid : sensorIds) {
            marksBySensor.put(sid, new TreeSet<>());
        }

        for (String sid : sensorIds) {
            ChosenReading ch = chosen.get(sid);
            if (!ch.have) {
                continue;
            }
            SensorRec rec = sensors.get(sid);
            int t = a * ch.adc + b;
            for (Incident inc : incidents) {
                if (!inc.accepted || !"rig_warm".equals(inc.kind)) {
                    continue;
                }
                if (asOf < inc.day || ch.day < inc.day) {
                    continue;
                }
                if (!rec.rigId.equals(inc.rigId)) {
                    continue;
                }
                t += inc.deltaMillic;
                marksBySensor
                        .get(sid)
                        .add("rig_warm:" + inc.rigId + ":" + inc.day);
            }
            int gap = ch.day - rec.lastCalibrationDay;
            if (gap > driftGrace) {
                t += driftPerDay * (gap - driftGrace);
                marksBySensor.get(sid).add("calib_drift");
            }
            if (ovActive && ovIds.contains(sid)) {
                t += ovAdd;
                marksBySensor.get(sid).add("overlay");
            }
            preT.put(sid, t);
        }

        Map<String, Integer> work = new TreeMap<>(preT);
        Set<String> prevFrozen = new HashSet<>();
        for (int round = 1; round <= 3; round++) {
            for (CanonEdge e : edges) {
                Integer ta = work.get(e.a);
                Integer tb = work.get(e.b);
                if (ta == null || tb == null) {
                    continue;
                }
                int effW = e.w;
                if (round > 1) {
                    if (prevFrozen.contains(e.a)) {
                        effW = 0;
                    }
                    if (prevFrozen.contains(e.b)) {
                        effW = 0;
                    }
                }
                work.put(e.b, tb + floorDiv(effW * (ta - tb), 1000));
            }
            Set<String> newFrozen = new HashSet<>();
            for (Map.Entry<String, Integer> ent : work.entrySet()) {
                if (isFrozen(ent.getKey(), ent.getValue(), sensors, tolP, tolS)) {
                    newFrozen.add(ent.getKey());
                }
            }
            prevFrozen = newFrozen;
        }
        Map<String, Integer> relaxedAll = new TreeMap<>(work);

        for (String sid : faultedCc) {
            for (int d : latticeDayList) {
                marksBySensor.get(sid).add("lattice_fault:" + d);
            }
        }
        for (String sid : sensorIds) {
            String strapId = sensors.get(sid).strapId;
            if (strapDayByStrap.containsKey(strapId)) {
                marksBySensor.get(sid).add("strap_quench:" + strapDayByStrap.get(strapId));
            }
        }

        Map<String, Integer> verdictCounts = new TreeMap<>();
        JsonArray verdictRows = new JsonArray();

        for (String sid : sensorIds) {
            SensorRec rec = sensors.get(sid);
            ChosenReading ch = chosen.get(sid);
            Integer relaxedPtr = relaxedAll.get(sid);
            String verdict = "ok";
            Set<String> reasons = new TreeSet<>();

            if (faultedCc.contains(sid)) {
                verdict = "lattice_faulted";
                for (int d : latticeDayList) {
                    reasons.add("lattice_fault:" + d);
                }
            } else if (strapDayByStrap.containsKey(rec.strapId)) {
                verdict = "strap_quenched";
                reasons.add("strap_quench:" + strapDayByStrap.get(rec.strapId));
            } else if (!ch.have && hasAnyInWindow.get(sid)) {
                verdict = "missing_read";
            } else if (!ch.have && !bySensor.get(sid).isEmpty()) {
                verdict = "precommission";
            } else if (!ch.have) {
                verdict = "missing_read";
            } else if (ch.day < rec.lastCalibrationDay) {
                verdict = "stale_calibration";
            } else if (relaxedPtr != null
                    && (relaxedPtr < rec.nominalLow - tolFor(sid, rec, tolP, tolS)
                            || relaxedPtr > rec.nominalHigh + tolFor(sid, rec, tolP, tolS))) {
                verdict = "out_of_range";
            } else {
                verdict = "ok";
            }

            reasons.add(verdict);
            reasons.addAll(marksBySensor.get(sid));
            verdictCounts.merge(verdict, 1, Integer::sum);

            JsonObject row = new JsonObject();
            if (ch.have) {
                row.addProperty("reading_day", ch.day);
            } else {
                row.add("reading_day", JsonNull.INSTANCE);
            }
            JsonArray reasonList = new JsonArray();
            for (String rsn : reasons) {
                reasonList.add(rsn);
            }
            row.add("reasons", reasonList);
            if (relaxedPtr != null) {
                row.addProperty("relaxed_millic", relaxedPtr);
            } else {
                row.add("relaxed_millic", JsonNull.INSTANCE);
            }
            row.addProperty("rig_id", rec.rigId);
            row.addProperty("sensor_id", sid);
            row.addProperty("strap_id", rec.strapId);
            row.addProperty("tier", rec.tier);
            row.addProperty("verdict", verdict);
            verdictRows.add(row);
        }

        JsonObject temps = new JsonObject();
        for (Map.Entry<String, Integer> ent : relaxedAll.entrySet()) {
            temps.addProperty(ent.getKey(), ent.getValue());
        }

        JsonArray touchesOut = new JsonArray();
        for (String sid : sensorIds) {
            List<String> marks = new ArrayList<>(marksBySensor.get(sid));
            marks.sort(String::compareTo);
            JsonObject touch = new JsonObject();
            JsonArray marksArr = new JsonArray();
            for (String mk : marks) {
                marksArr.add(mk);
            }
            touch.add("marks", marksArr);
            touch.addProperty("sensor_id", sid);
            touchesOut.add(touch);
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("as_of_day", asOf);
        summary.addProperty("edge_count", edgeCount);
        summary.addProperty("reading_rows", readingRows);
        summary.addProperty("relax_rounds", 3);
        summary.addProperty("sensor_count", sensorIds.size());
        JsonObject vc = new JsonObject();
        for (Map.Entry<String, Integer> ent : verdictCounts.entrySet()) {
            vc.addProperty(ent.getKey(), ent.getValue());
        }
        summary.add("verdict_counts", vc);

        JsonObject verdictsDoc = new JsonObject();
        verdictsDoc.add("verdicts", verdictRows);
        JsonObject relaxedDoc = new JsonObject();
        relaxedDoc.add("temps", temps);
        JsonObject touchDoc = new JsonObject();
        touchDoc.add("touches", touchesOut);

        writeJson(auditDir.resolve("sensor_verdicts.json"), verdictsDoc);
        writeJson(auditDir.resolve("thermal_relaxed.json"), relaxedDoc);
        writeJson(auditDir.resolve("incident_touch.json"), touchDoc);
        writeJson(auditDir.resolve("summary.json"), summary);
    }

    private static int tolFor(String sid, SensorRec rec, int tolP, int tolS) {
        return "primary".equals(rec.tier) ? tolP : tolS;
    }

    private static boolean isFrozen(
            String sid, int t, Map<String, SensorRec> sensors, int tolP, int tolS) {
        SensorRec rec = sensors.get(sid);
        int tol = tolFor(sid, rec, tolP, tolS);
        return t < rec.nominalLow - tol || t > rec.nominalHigh + tol;
    }

    private static Set<String> componentsTouchingSeeds(
            List<String> seeds, Map<String, Set<String>> adj, Map<String, SensorRec> sensors) {
        Set<String> seedsSet = new HashSet<>();
        for (String s : seeds) {
            if (sensors.containsKey(s)) {
                seedsSet.add(s);
            }
        }
        Set<String> seen = new HashSet<>();
        Set<String> faulted = new HashSet<>();
        for (String seed : seedsSet) {
            if (seen.contains(seed)) {
                continue;
            }
            List<String> stack = new ArrayList<>();
            stack.add(seed);
            Set<String> comp = new HashSet<>();
            while (!stack.isEmpty()) {
                String x = stack.remove(stack.size() - 1);
                if (seen.contains(x)) {
                    continue;
                }
                seen.add(x);
                comp.add(x);
                for (String y : adj.getOrDefault(x, Set.of())) {
                    if (!seen.contains(y)) {
                        stack.add(y);
                    }
                }
            }
            boolean intersect = false;
            for (String x : comp) {
                if (seedsSet.contains(x)) {
                    intersect = true;
                    break;
                }
            }
            if (intersect) {
                faulted.addAll(comp);
            }
        }
        return faulted;
    }

    private static int floorDiv(int num, int den) {
        int q = num / den;
        int r = num % den;
        if (r != 0 && ((r < 0) != (den < 0))) {
            q--;
        }
        return q;
    }

    private static int medianInt(List<Integer> vals) {
        List<Integer> cp = new ArrayList<>(vals);
        cp.sort(Integer::compareTo);
        int n = cp.size();
        if (n % 2 == 1) {
            return cp.get(n / 2);
        }
        return floorDiv(cp.get(n / 2 - 1) + cp.get(n / 2), 2);
    }

    private static JsonObject loadJson(Path path) throws IOException {
        JsonElement el = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8));
        if (el.isJsonArray()) {
            throw new IOException("expected object at " + path);
        }
        return el.getAsJsonObject();
    }

    private static JsonArray loadJsonArray(Path path) throws IOException {
        JsonElement el = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8));
        if (!el.isJsonArray()) {
            throw new IOException("expected JSON array at " + path);
        }
        return el.getAsJsonArray();
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        Files.writeString(path, gson.toJson(deepSort(root)) + "\n", StandardCharsets.UTF_8);
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

    private static final class SensorRec {
        String sensorId;
        String strapId;
        String rigId;
        String tier;
        int commissionedDay;
        int lastCalibrationDay;
        int nominalLow;
        int nominalHigh;
    }

    private static final class ReadingRow {
        final String sensorId;
        final int day;
        final int adc;

        ReadingRow(String sensorId, int day, int adc) {
            this.sensorId = sensorId;
            this.day = day;
            this.adc = adc;
        }
    }

    private static final class ChosenReading {
        final int day;
        final int adc;
        final boolean have;

        ChosenReading(boolean have) {
            this.day = 0;
            this.adc = 0;
            this.have = have;
        }

        ChosenReading(int day, int adc, boolean have) {
            this.day = day;
            this.adc = adc;
            this.have = have;
        }
    }

    private static final class CanonEdge {
        final String a;
        final String b;
        final int w;

        CanonEdge(String a, String b, int w) {
            this.a = a;
            this.b = b;
            this.w = w;
        }
    }

    private static final class Incident {
        String kind;
        int day;
        boolean accepted = true;
        String strapId;
        String rigId;
        int deltaMillic;
        List<String> seedSensors;
    }
}
