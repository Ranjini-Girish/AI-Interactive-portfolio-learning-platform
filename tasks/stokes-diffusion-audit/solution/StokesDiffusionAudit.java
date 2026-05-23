import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
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

/** Stokes diffusion audit oracle. */
public final class StokesDiffusionAudit {

    private static final double BOLTZMANN_J_PER_K = 1.380649e-23;
    private static final int DRIFT_WINDOW_DAYS = 6;
    private static final Set<String> ALLOWED_KINDS =
            new TreeSet<>(
                    Set.of(
                            "sensor_drift",
                            "probe_stiction",
                            "solvent_recall",
                            "bench_correction",
                            "recall_lift"));

    private StokesDiffusionAudit() {}

    public static void main(String[] args) throws IOException {
        Path dataDir;
        Path auditDir;
        if (args.length == 2) {
            dataDir = Path.of(args[0]);
            auditDir = Path.of(args[1]);
        } else if (args.length == 0) {
            dataDir = Path.of(envOr("SDA_DATA_DIR", "/app/stokes_lab"));
            auditDir = Path.of(envOr("SDA_AUDIT_DIR", "/app/audit"));
        } else {
            System.err.println("usage: StokesDiffusionAudit [<dataDir> <auditDir>]");
            System.exit(1);
            return;
        }
        run(dataDir, auditDir);
    }

    private static String envOr(String name, String def) {
        String v = System.getenv(name);
        return v == null || v.isEmpty() ? def : v;
    }

    private static void run(Path dataDir, Path auditDir) throws IOException {
        Files.createDirectories(auditDir);

        JsonObject pool = loadJson(dataDir.resolve("pool_state.json"));
        double kelvinOffset = pool.get("kelvin_offset_global").getAsDouble();
        Double radiusFloor = jsonDoubleOrNull(pool, "radius_floor_nm");
        Double radiusCeiling = jsonDoubleOrNull(pool, "radius_ceiling_nm");
        Double driftCapK = jsonDoubleOrNull(pool, "drift_cap_K");
        Integer stictionLookback = jsonIntOrNull(pool, "stiction_lookback_days");

        JsonObject incDoc = loadJson(dataDir.resolve("incident_log.json"));
        List<RawEvent> events = parseEvents(incDoc.getAsJsonArray("events"));

        Map<String, List<ViscosityPoint>> solvents = loadSolvents(dataDir.resolve("solvents"));
        List<Measurement> measurements = loadMeasurements(dataDir.resolve("measurements"));

        Set<String> corpusProbes = new HashSet<>();
        Set<String> corpusSolvents = new HashSet<>();
        for (Measurement m : measurements) {
            corpusProbes.add(m.probeId);
            corpusSolvents.add(m.solventId);
        }

        int ignored = 0;
        for (RawEvent ev : events) {
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)) {
                ignored++;
            }
        }

        int lowEx = 0;
        int highEx = 0;
        int okCount = 0;
        int probeVoid = 0;
        int solventVoid = 0;
        int radiusClamped = 0;
        int driftCapped = 0;

        List<JsonObject> entries = new ArrayList<>();

        List<List<String>> driftContribIds = new ArrayList<>();
        List<RawEvent> benchWinner = new ArrayList<>();
        List<String> statuses = new ArrayList<>();
        List<List<Integer>> recallWinnerIdx = new ArrayList<>();
        List<List<Integer>> liftWinnerIdx = new ArrayList<>();
        List<Boolean> recallActiveForMeas = new ArrayList<>();

        for (Measurement m : measurements) {
            List<String> contribIds = new ArrayList<>();
            double deltaRaw = driftWindowContributors(events, m, corpusProbes, corpusSolvents, contribIds);
            driftContribIds.add(contribIds);
            boolean wasCapped = false;
            double deltaD = deltaRaw;
            if (driftCapK != null) {
                double[] capped = capDrift(deltaRaw, driftCapK);
                deltaD = capped[0];
                wasCapped = capped[1] > 0;
            }
            if (wasCapped) {
                driftCapped++;
            }

            int rFloor = solventRecallFloorDay(events, m, corpusProbes, corpusSolvents);
            RawEvent bw = selectBenchDelta(events, m, corpusProbes, corpusSolvents, rFloor);
            benchWinner.add(bw);

            DayWinners rWin = recallLatestDay(events, m, corpusProbes, corpusSolvents);
            int rMaxDay = rWin.maxDay;
            List<Integer> rWinners = rWin.winners;

            DayWinners lWin = liftLatestDay(events, m, corpusProbes, corpusSolvents);
            int lMaxDay = lWin.maxDay;
            List<Integer> lWinners = lWin.winners;

            recallWinnerIdx.add(rWinners);
            liftWinnerIdx.add(lWinners);

            boolean recallApplies = false;
            if (rMaxDay >= 0 && (lMaxDay < 0 || rMaxDay > lMaxDay)) {
                recallApplies = true;
            }
            recallActiveForMeas.add(recallApplies);

            boolean direct = directStictionActive(events, m, corpusProbes, corpusSolvents, stictionLookback);

            String status = "ok";
            if (direct) {
                status = "probe_void";
            } else if (recallApplies) {
                status = "solvent_void";
            }
            statuses.add(status);

            double tBase = m.tempReportedK + kelvinOffset;
            double deltaBench = bw != null ? bw.deltaK : 0.0;
            double tEff = tBase + deltaD + deltaBench;

            double origR = m.hydrodynamicRadiusNm;
            double rClamped = clampRadiusNm(origR, radiusFloor, radiusCeiling);
            if (Double.doubleToLongBits(rClamped) != Double.doubleToLongBits(origR)) {
                radiusClamped++;
            }

            JsonElement tempOut = JsonNull.INSTANCE;
            JsonElement viscOut = JsonNull.INSTANCE;
            JsonElement dOut = JsonNull.INSTANCE;
            JsonElement rUsedOut = JsonNull.INSTANCE;

            if ("ok".equals(status)) {
                List<ViscosityPoint> points = solvents.getOrDefault(m.solventId, List.of());
                int[] exCounts = new int[] {lowEx, highEx};
                double etaCp = viscosityFor(tBase + deltaD, points, exCounts);
                lowEx = exCounts[0];
                highEx = exCounts[1];
                double etaPas = etaCp * 1e-3;
                double rM = rClamped * 1e-9;
                double dSi = diffusionSi(tEff, etaPas, rM);
                double dNm2s = dSi * 1e18;

                tempOut = toJsonNumber(roundHalfEven(tEff, 3));
                viscOut = toJsonNumber(roundHalfEven(etaCp, 6));
                dOut = toJsonNumber(roundHalfEven(dNm2s, 6));
                rUsedOut = toJsonNumber(roundHalfEven(rClamped, 6));
                okCount++;
            } else if ("probe_void".equals(status)) {
                probeVoid++;
            } else if ("solvent_void".equals(status)) {
                solventVoid++;
            }

            JsonObject row = new JsonObject();
            row.add("d_stokes_nm2_per_s", dOut);
            row.add("hydrodynamic_radius_nm_used", rUsedOut);
            row.addProperty("measurement_id", m.measurementId);
            row.addProperty("probe_id", m.probeId);
            row.addProperty("solute_id", m.soluteId);
            row.addProperty("solvent_id", m.solventId);
            row.addProperty("status", status);
            row.add("temp_effective_K", tempOut);
            row.add("viscosity_cP_used", viscOut);
            entries.add(row);
        }

        Set<String> applied = new HashSet<>();

        for (int i = 0; i < measurements.size(); i++) {
            if (!"ok".equals(statuses.get(i))) {
                continue;
            }
            for (String eid : driftContribIds.get(i)) {
                applied.add(eid);
            }
            if (benchWinner.get(i) != null) {
                applied.add(benchWinner.get(i).eventId);
            }
        }

        for (Measurement m : measurements) {
            for (RawEvent ev : events) {
                if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                        || !"probe_stiction".equals(ev.kind)
                        || !m.probeId.equals(ev.probeId)
                        || ev.day > m.runDay) {
                    continue;
                }
                applied.add(ev.eventId);
            }
        }

        for (int i = 0; i < measurements.size(); i++) {
            if (!recallActiveForMeas.get(i)) {
                continue;
            }
            for (int idx : recallWinnerIdx.get(i)) {
                applied.add(events.get(idx).eventId);
            }
        }

        for (int i = 0; i < measurements.size(); i++) {
            if (recallWinnerIdx.get(i).isEmpty() || liftWinnerIdx.get(i).isEmpty()) {
                continue;
            }
            int rMaxDay = events.get(recallWinnerIdx.get(i).get(0)).day;
            int lMaxDay = events.get(liftWinnerIdx.get(i).get(0)).day;
            if (lMaxDay < rMaxDay) {
                continue;
            }
            for (int idx : liftWinnerIdx.get(i)) {
                applied.add(events.get(idx).eventId);
            }
        }

        List<String> appliedList = new ArrayList<>(applied);
        appliedList.sort(String::compareTo);

        JsonObject summary = new JsonObject();
        summary.addProperty("drift_capped_count", driftCapped);
        summary.addProperty("ignored_incident_events", ignored);
        summary.addProperty("measurements_total", measurements.size());
        summary.addProperty("ok_count", okCount);
        summary.addProperty("probe_void_count", probeVoid);
        summary.addProperty("radius_clamped_count", radiusClamped);
        summary.addProperty("solvent_void_count", solventVoid);
        summary.addProperty("viscosity_extrapolation_high_count", highEx);
        summary.addProperty("viscosity_extrapolation_low_count", lowEx);

        JsonObject resultsDoc = new JsonObject();
        JsonArray entriesArr = new JsonArray();
        for (JsonObject row : entries) {
            entriesArr.add(row);
        }
        resultsDoc.add("entries", entriesArr);

        JsonObject anomDoc = new JsonObject();
        JsonArray appliedArr = new JsonArray();
        for (String id : appliedList) {
            appliedArr.add(id);
        }
        anomDoc.add("applied_events", appliedArr);

        writeJson(auditDir.resolve("diffusion_results.json"), resultsDoc);
        writeJson(auditDir.resolve("anomalies.json"), anomDoc);
        writeJson(auditDir.resolve("summary.json"), summary);
    }

    private static double driftWindowContributors(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents,
            List<String> contribOut) {
        double sum = 0.0;
        int low = m.runDay - DRIFT_WINDOW_DAYS;
        for (RawEvent ev : events) {
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"sensor_drift".equals(ev.kind)
                    || !m.probeId.equals(ev.probeId)
                    || ev.day < low
                    || ev.day > m.runDay) {
                continue;
            }
            sum += ev.deltaK;
            contribOut.add(ev.eventId);
        }
        return sum;
    }

    private static int solventRecallFloorDay(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents) {
        int best = -1;
        for (RawEvent ev : events) {
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"solvent_recall".equals(ev.kind)
                    || !m.solventId.equals(ev.solventId)
                    || ev.day > m.runDay) {
                continue;
            }
            if (ev.day > best) {
                best = ev.day;
            }
        }
        return best;
    }

    private static double[] capDrift(double raw, double capK) {
        if (raw > capK) {
            return new double[] {capK, 1};
        }
        if (raw < -capK) {
            return new double[] {-capK, 1};
        }
        return new double[] {raw, 0};
    }

    private static RawEvent selectBenchDelta(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents,
            int rFloor) {
        List<Cand> cands = new ArrayList<>();
        for (int i = 0; i < events.size(); i++) {
            RawEvent ev = events.get(i);
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"bench_correction".equals(ev.kind)
                    || !m.probeId.equals(ev.probeId)
                    || ev.day > m.runDay) {
                continue;
            }
            if (rFloor >= 0 && ev.day <= rFloor) {
                continue;
            }
            if (ev.solventId != null
                    && !ev.solventId.isEmpty()
                    && !ev.solventId.equals(m.solventId)) {
                continue;
            }
            cands.add(new Cand(i, ev.day, ev));
        }
        if (cands.isEmpty()) {
            return null;
        }
        Cand best = cands.get(0);
        for (int j = 1; j < cands.size(); j++) {
            Cand c = cands.get(j);
            if (c.day > best.day || (c.day == best.day && c.idx > best.idx)) {
                best = c;
            }
        }
        return best.ev;
    }

    private static boolean directStictionActive(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents,
            Integer lookback) {
        for (RawEvent ev : events) {
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"probe_stiction".equals(ev.kind)
                    || !m.probeId.equals(ev.probeId)
                    || ev.day > m.runDay) {
                continue;
            }
            if (lookback != null && ev.day < m.runDay - lookback) {
                continue;
            }
            return true;
        }
        return false;
    }

    private static DayWinners recallLatestDay(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents) {
        int best = -1;
        List<Integer> winners = new ArrayList<>();
        for (int i = 0; i < events.size(); i++) {
            RawEvent ev = events.get(i);
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"solvent_recall".equals(ev.kind)
                    || !m.solventId.equals(ev.solventId)
                    || ev.day > m.runDay) {
                continue;
            }
            if (ev.day > best) {
                best = ev.day;
                winners = new ArrayList<>();
                winners.add(i);
            } else if (ev.day == best) {
                winners.add(i);
            }
        }
        return new DayWinners(best, winners);
    }

    private static DayWinners liftLatestDay(
            List<RawEvent> events,
            Measurement m,
            Set<String> corpusProbes,
            Set<String> corpusSolvents) {
        int best = -1;
        List<Integer> winners = new ArrayList<>();
        for (int i = 0; i < events.size(); i++) {
            RawEvent ev = events.get(i);
            if (isIgnoredEvent(ev, corpusProbes, corpusSolvents)
                    || !"recall_lift".equals(ev.kind)
                    || !m.solventId.equals(ev.solventId)
                    || ev.day > m.runDay) {
                continue;
            }
            if (ev.probeId != null && !ev.probeId.isEmpty() && !ev.probeId.equals(m.probeId)) {
                continue;
            }
            if (ev.day > best) {
                best = ev.day;
                winners = new ArrayList<>();
                winners.add(i);
            } else if (ev.day == best) {
                winners.add(i);
            }
        }
        return new DayWinners(best, winners);
    }

    private static double viscosityFor(
            double t, List<ViscosityPoint> points, int[] exCounts) {
        if (points.isEmpty()) {
            return Double.NaN;
        }
        if (t < points.get(0).tempK) {
            exCounts[0]++;
            return points.get(0).viscosityCp;
        }
        ViscosityPoint last = points.get(points.size() - 1);
        if (t > last.tempK) {
            exCounts[1]++;
            return last.viscosityCp;
        }
        for (int j = 0; j < points.size() - 1; j++) {
            double t0 = points.get(j).tempK;
            double t1 = points.get(j + 1).tempK;
            if (t >= t0 && t <= t1) {
                double v0 = points.get(j).viscosityCp;
                double v1 = points.get(j + 1).viscosityCp;
                if (t1 == t0) {
                    return v0;
                }
                double w = (t - t0) / (t1 - t0);
                return v0 + (v1 - v0) * w;
            }
        }
        return last.viscosityCp;
    }

    private static double diffusionSi(double t, double etaPas, double rM) {
        return (BOLTZMANN_J_PER_K * t) / (6 * Math.PI * etaPas * rM);
    }

    private static double clampRadiusNm(double orig, Double floorNm, Double ceilingNm) {
        Double fl = floorNm;
        Double ce = ceilingNm;
        if (fl != null && ce != null && fl > ce) {
            double tmp = fl;
            fl = ce;
            ce = tmp;
        }
        double r = orig;
        if (fl != null && r < fl) {
            r = fl;
        }
        if (ce != null && r > ce) {
            r = ce;
        }
        return r;
    }

    private static boolean isIgnoredEvent(
            RawEvent ev, Set<String> corpusProbes, Set<String> corpusSolvents) {
        if (!ev.accepted) {
            return true;
        }
        if (!ALLOWED_KINDS.contains(ev.kind)) {
            return true;
        }
        return switch (ev.kind) {
            case "sensor_drift" ->
                    ev.probeId == null
                            || ev.probeId.isEmpty()
                            || !corpusProbes.contains(ev.probeId)
                            || Double.isNaN(ev.deltaK);
            case "probe_stiction" ->
                    ev.probeId == null
                            || ev.probeId.isEmpty()
                            || !corpusProbes.contains(ev.probeId);
            case "solvent_recall" ->
                    ev.solventId == null
                            || ev.solventId.isEmpty()
                            || !corpusSolvents.contains(ev.solventId);
            case "bench_correction" ->
                    ev.probeId == null
                            || ev.probeId.isEmpty()
                            || !corpusProbes.contains(ev.probeId)
                            || Double.isNaN(ev.deltaK)
                            || (ev.solventId != null
                                    && !ev.solventId.isEmpty()
                                    && !corpusSolvents.contains(ev.solventId));
            case "recall_lift" ->
                    ev.solventId == null
                            || ev.solventId.isEmpty()
                            || !corpusSolvents.contains(ev.solventId)
                            || (ev.probeId != null
                                    && !ev.probeId.isEmpty()
                                    && !corpusProbes.contains(ev.probeId));
            default -> true;
        };
    }

    private static double roundHalfEven(double x, int places) {
        BigDecimal bd = BigDecimal.valueOf(x);
        return bd.setScale(places, RoundingMode.HALF_EVEN).doubleValue();
    }

    private static JsonElement toJsonNumber(double v) {
        BigDecimal bd = BigDecimal.valueOf(v).stripTrailingZeros();
        try {
            return new com.google.gson.JsonPrimitive(bd.longValueExact());
        } catch (ArithmeticException ex) {
            return new com.google.gson.JsonPrimitive(bd);
        }
    }

    private static JsonObject loadJson(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static Double jsonDoubleOrNull(JsonObject o, String key) {
        if (!o.has(key) || o.get(key).isJsonNull()) {
            return null;
        }
        return o.get(key).getAsDouble();
    }

    private static Integer jsonIntOrNull(JsonObject o, String key) {
        if (!o.has(key) || o.get(key).isJsonNull()) {
            return null;
        }
        return o.get(key).getAsInt();
    }

    private static List<RawEvent> parseEvents(JsonArray arr) {
        List<RawEvent> out = new ArrayList<>();
        for (JsonElement el : arr) {
            JsonObject o = el.getAsJsonObject();
            RawEvent ev = new RawEvent();
            ev.eventId = o.get("event_id").getAsString();
            ev.kind = o.get("kind").getAsString();
            if (o.has("accepted") && !o.get("accepted").isJsonNull()) {
                ev.accepted = o.get("accepted").getAsBoolean();
            } else {
                ev.accepted = true;
            }
            ev.day = o.get("day").getAsInt();
            if (o.has("probe_id") && !o.get("probe_id").isJsonNull()) {
                ev.probeId = o.get("probe_id").getAsString();
            }
            if (o.has("solvent_id") && !o.get("solvent_id").isJsonNull()) {
                ev.solventId = o.get("solvent_id").getAsString();
            }
            if (o.has("delta_K") && !o.get("delta_K").isJsonNull()) {
                ev.deltaK = o.get("delta_K").getAsDouble();
            } else {
                ev.deltaK = Double.NaN;
            }
            out.add(ev);
        }
        return out;
    }

    private static Map<String, List<ViscosityPoint>> loadSolvents(Path dir) throws IOException {
        Map<String, List<ViscosityPoint>> out = new TreeMap<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "*.json")) {
            List<Path> paths = new ArrayList<>();
            for (Path p : stream) {
                paths.add(p);
            }
            paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
            for (Path p : paths) {
                JsonObject sf = loadJson(p);
                String sid = sf.get("solvent_id").getAsString();
                List<ViscosityPoint> pts = new ArrayList<>();
                for (JsonElement el : sf.getAsJsonArray("viscosity_points")) {
                    JsonObject vp = el.getAsJsonObject();
                    pts.add(
                            new ViscosityPoint(
                                    vp.get("temp_K").getAsDouble(),
                                    vp.get("viscosity_cP").getAsDouble()));
                }
                out.put(sid, pts);
            }
        }
        return out;
    }

    private static List<Measurement> loadMeasurements(Path dir) throws IOException {
        List<Measurement> out = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(dir, "*.json")) {
            List<Path> paths = new ArrayList<>();
            for (Path p : stream) {
                paths.add(p);
            }
            paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
            for (Path p : paths) {
                JsonObject o = loadJson(p);
                Measurement m = new Measurement();
                m.measurementId = o.get("measurement_id").getAsString();
                m.probeId = o.get("probe_id").getAsString();
                m.solventId = o.get("solvent_id").getAsString();
                m.soluteId = o.get("solute_id").getAsString();
                m.hydrodynamicRadiusNm = o.get("hydrodynamic_radius_nm").getAsDouble();
                m.tempReportedK = o.get("temp_reported_K").getAsDouble();
                m.runDay = o.get("run_day").getAsInt();
                out.add(m);
            }
        }
        out.sort(Comparator.comparing(m -> m.measurementId));
        return out;
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        String text = gson.toJson(deepSort(root)) + "\n";
        Files.writeString(path, text, StandardCharsets.UTF_8);
    }

    private static JsonElement deepSort(JsonElement el) {
        if (el == null || el.isJsonNull()) {
            return el == null ? JsonNull.INSTANCE : el.deepCopy();
        }
        if (el.isJsonPrimitive() || el.isJsonArray()) {
            if (el.isJsonArray()) {
                JsonArray a = el.getAsJsonArray();
                JsonArray out = new JsonArray();
                for (JsonElement x : a) {
                    out.add(deepSort(x));
                }
                return out;
            }
            return el.deepCopy();
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

    private static final class RawEvent {
        String eventId;
        String kind;
        boolean accepted = true;
        int day;
        String probeId;
        String solventId;
        double deltaK = Double.NaN;
    }

    private static final class Measurement {
        String measurementId;
        String probeId;
        String solventId;
        String soluteId;
        double hydrodynamicRadiusNm;
        double tempReportedK;
        int runDay;
    }

    private static final class ViscosityPoint {
        final double tempK;
        final double viscosityCp;

        ViscosityPoint(double tempK, double viscosityCp) {
            this.tempK = tempK;
            this.viscosityCp = viscosityCp;
        }
    }

    private static final class Cand {
        final int idx;
        final int day;
        final RawEvent ev;

        Cand(int idx, int day, RawEvent ev) {
            this.idx = idx;
            this.day = day;
            this.ev = ev;
        }
    }

    private static final class DayWinners {
        final int maxDay;
        final List<Integer> winners;

        DayWinners(int maxDay, List<Integer> winners) {
            this.maxDay = maxDay;
            this.winners = winners;
        }
    }
}
