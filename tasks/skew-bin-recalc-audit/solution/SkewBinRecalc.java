import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class SkewBinRecalc {

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: SkewBinRecalc <dataRoot> <auditDir>");
            System.exit(2);
        }
        Path root = Path.of(args[0]);
        Path audit = Path.of(args[1]);
        Files.createDirectories(audit);

        JsonObject policy = readObject(root.resolve("policy.json"));
        JsonObject pool = readObject(root.resolve("pool_state.json"));
        JsonObject east = readObject(root.resolve("anchors/east.json"));
        JsonObject west = readObject(root.resolve("anchors/west.json"));
        JsonObject incidents = readObject(root.resolve("incident_log.json"));

        long ledger = pool.get("ledger_serial").getAsLong();
        long quorum = pool.get("quorum_ring").getAsLong();
        int w = policy.get("bin_stride").getAsInt();
        int skewMix = policy.get("skew_mix").getAsInt();
        int blendMod = policy.get("blend_mod").getAsInt();
        int pairSpan = policy.get("pair_span").getAsInt();
        boolean anchorCross = policy.get("anchor_cross").getAsBoolean();
        int e = east.get("lane_add").getAsInt();
        int v = west.get("lane_add").getAsInt();

        TreeMap<String, TreeMap<Integer, Integer>> masks = new TreeMap<>();
        for (JsonElement row : incidents.getAsJsonArray("masks")) {
            JsonObject o = row.getAsJsonObject();
            String sid = o.get("sample_id").getAsString();
            TreeMap<Integer, Integer> slotSet = new TreeMap<>();
            for (JsonElement z : o.getAsJsonArray("zero_slots")) {
                slotSet.put(z.getAsInt(), 1);
            }
            masks.merge(sid, slotSet, (a, b) -> {
                a.putAll(b);
                return a;
            });
        }

        List<Path> sampleFiles = new ArrayList<>();
        try (DirectoryStream<Path> stream =
                Files.newDirectoryStream(root.resolve("samples"), "sample_*.json")) {
            for (Path p : stream) {
                sampleFiles.add(p);
            }
        }
        Collections.sort(sampleFiles);

        TreeMap<String, JsonArray> samplesOut = new TreeMap<>();
        long totalAssignments = 0;
        List<String> tailParts = new ArrayList<>();

        for (Path sp : sampleFiles) {
            JsonObject doc = readObject(sp);
            String sid = doc.get("sample_id").getAsString();
            int phase = doc.get("phase").getAsInt();
            JsonArray readingsArr = doc.getAsJsonArray("readings");
            int n = readingsArr.size();
            int[] readings = new int[n];
            for (int i = 0; i < n; i++) {
                readings[i] = readingsArr.get(i).getAsInt();
            }
            if (masks.containsKey(sid)) {
                for (int zi : masks.get(sid).keySet()) {
                    if (zi >= 0 && zi < n) {
                        readings[zi] = 0;
                    }
                }
            }

            int[] adj = new int[n];
            for (int i = 0; i < n; i++) {
                int lane = Math.floorMod(e * i + v, w);
                adj[i] = readings[i] + lane;
            }

            int skew =
                    Math.floorMod(
                            Math.floorMod(ledger, blendMod) * skewMix
                                    + phase
                                    + Math.floorMod(quorum, w),
                            w);

            TreeMap<Integer, Integer> hist = new TreeMap<>();
            long ssum = 0;
            for (int k = 1; k <= n; k++) {
                ssum += adj[k - 1];
                long rawBin = (ssum + skew) / w;
                int folded = (int) (rawBin / pairSpan);
                hist.merge(folded, 1, Integer::sum);
            }

            if (anchorCross && !hist.isEmpty()) {
                int bMin = hist.firstKey();
                int carry = Math.floorMod(e + v + phase, w);
                hist.merge(bMin, carry, Integer::sum);
            }

            JsonArray rows = new JsonArray();
            for (Map.Entry<Integer, Integer> en : hist.entrySet()) {
                if (en.getValue() > 0) {
                    JsonObject row = new JsonObject();
                    row.addProperty("bin", en.getKey());
                    row.addProperty("tally", en.getValue());
                    rows.add(row);
                }
            }
            samplesOut.put(sid, rows);
            totalAssignments += n;
            tailParts.add(sid + ":" + ssum);
        }

        Collections.sort(tailParts);
        String tailJoined = String.join(",", tailParts);
        String tailSha = sha256Hex(tailJoined.getBytes(StandardCharsets.UTF_8));

        JsonObject skewRoot = new JsonObject();
        JsonObject samplesJson = new JsonObject();
        for (Map.Entry<String, JsonArray> en : samplesOut.entrySet()) {
            samplesJson.add(en.getKey(), en.getValue());
        }
        skewRoot.add("samples", samplesJson);

        JsonObject summary = new JsonObject();
        summary.addProperty("anchor_cross", anchorCross);
        summary.addProperty("bin_stride", w);
        summary.addProperty("blend_mod", blendMod);
        summary.addProperty("ledger_serial", ledger);
        summary.addProperty("pair_span", pairSpan);
        summary.addProperty("quorum_ring", quorum);
        summary.addProperty("skew_mix", skewMix);
        summary.addProperty("tail_ledger_sha", tailSha);
        summary.addProperty("total_assignments", totalAssignments);

        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .disableHtmlEscaping()
                        .create();
        writeUtf8(audit.resolve("skew_bins.json"), gson.toJson(skewRoot) + "\n");
        writeUtf8(audit.resolve("summary.json"), gson.toJson(summary) + "\n");
    }

    private static JsonObject readObject(Path p) throws IOException {
        try (Reader r = Files.newBufferedReader(p, StandardCharsets.UTF_8)) {
            return JsonParser.parseReader(r).getAsJsonObject();
        }
    }

    private static void writeUtf8(Path p, String text) throws IOException {
        Files.writeString(p, text, StandardCharsets.UTF_8);
    }

    private static String sha256Hex(byte[] data) throws IOException {
        try {
            java.security.MessageDigest md =
                    java.security.MessageDigest.getInstance("SHA-256");
            byte[] dig = md.digest(data);
            StringBuilder sb = new StringBuilder(dig.length * 2);
            for (byte b : dig) {
                sb.append(String.format("%02x", b));
            }
            return sb.toString();
        } catch (java.security.NoSuchAlgorithmException ex) {
            throw new IOException(ex);
        }
    }
}
