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
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;

/** Payments-ledger reconciliation audit oracle. */
public final class PayLedgerReconAudit {

    private static final Map<String, Integer> SEVERITY_RANKS =
            Map.of("critical", 0, "high", 1, "medium", 2, "low", 3);

    private static final Map<String, Integer> KIND_SIGNS =
            Map.of(
                    "auth", 0,
                    "capture", -1,
                    "refund", 1,
                    "chargeback", 1,
                    "fee", -1,
                    "hold", 0,
                    "release", 0);

    private PayLedgerReconAudit() {}

    public static void main(String[] args) throws Exception {
        String db = null;
        String policy = null;
        String out = null;
        for (int i = 0; i < args.length; i++) {
            switch (args[i]) {
                case "--db" -> db = args[++i];
                case "--policy" -> policy = args[++i];
                case "--out" -> out = args[++i];
                default -> {
                    System.err.println("unknown arg: " + args[i]);
                    System.exit(2);
                }
            }
        }
        if (db == null || policy == null || out == null) {
            System.err.println("usage: PayLedgerReconAudit --db <path> --policy <path> --out <path>");
            System.exit(2);
        }
        long started = System.nanoTime();
        JsonObject pol = loadPolicy(Path.of(policy));
        try (Connection conn = openDb(Path.of(db))) {
            JsonObject report = buildReport(conn, pol, 0.0);
            double elapsed = (System.nanoTime() - started) / 1_000_000_000.0;
            report.getAsJsonObject("summary")
                    .addProperty("audit_run_seconds", round6(elapsed));
            writeReport(report, Path.of(out));
        }
    }

    private static double round6(double v) {
        return Math.round(v * 1_000_000.0) / 1_000_000.0;
    }

    private static JsonObject loadPolicy(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static Connection openDb(Path dbPath) throws SQLException {
        String uri =
                "jdbc:sqlite:file:"
                        + dbPath.toAbsolutePath().normalize().toString().replace('\\', '/')
                        + "?mode=ro";
        return DriverManager.getConnection(uri);
    }

    private static Map<String, Object> rowToMap(ResultSet rs) throws SQLException {
        ResultSetMetaData md = rs.getMetaData();
        Map<String, Object> row = new LinkedHashMap<>();
        for (int i = 1; i <= md.getColumnCount(); i++) {
            row.put(md.getColumnLabel(i), rs.getObject(i));
        }
        return row;
    }

    private static List<Map<String, Object>> queryRows(Connection conn, String sql)
            throws SQLException {
        List<Map<String, Object>> rows = new ArrayList<>();
        try (var st = conn.createStatement(); ResultSet rs = st.executeQuery(sql)) {
            while (rs.next()) {
                rows.add(rowToMap(rs));
            }
        }
        return rows;
    }

    private static Map<String, Map<String, Object>> fetchTenants(Connection conn)
            throws SQLException {
        Map<String, Map<String, Object>> out = new HashMap<>();
        for (Map<String, Object> row :
                queryRows(
                        conn,
                        "SELECT tenant_id, jurisdiction, base_currency, "
                                + "audit_day_offset_min, minimum_balance_minor FROM tenants")) {
            out.put(str(row.get("tenant_id")), row);
        }
        return out;
    }

    private static List<Map<String, Object>> fetchAccounts(Connection conn) throws SQLException {
        return queryRows(
                conn,
                "SELECT account_id, tenant_id, currency, opened_day, closed_day, status "
                        + "FROM accounts");
    }

    private static List<Map<String, Object>> fetchTransactions(Connection conn)
            throws SQLException {
        return queryRows(
                conn,
                "SELECT tx_id, account_id, kind, amount_minor, currency, ts_utc, "
                        + "sequence_id, parent_tx_id, status, merchant_id, fx_micro "
                        + "FROM transactions");
    }

    private static List<Map<String, Object>> fetchHolds(Connection conn) throws SQLException {
        return queryRows(
                conn,
                "SELECT hold_id, account_id, amount_minor, placed_ts, expires_ts, "
                        + "released_ts, reason FROM holds");
    }

    private static Map<String, Map<String, Object>> fetchMerchants(Connection conn)
            throws SQLException {
        Map<String, Map<String, Object>> out = new HashMap<>();
        for (Map<String, Object> row :
                queryRows(
                        conn, "SELECT merchant_id, name, mcc, kyc_status FROM merchants")) {
            out.put(str(row.get("merchant_id")), row);
        }
        return out;
    }

    private static List<Map<String, Object>> fetchRules(Connection conn) throws SQLException {
        return queryRows(
                conn,
                "SELECT rule_id, priority, pattern, mcc, fee_bps FROM merchant_category_rules");
    }

    private static Map<List<Object>, Long> fetchFxRates(Connection conn) throws SQLException {
        Map<List<Object>, Long> out = new HashMap<>();
        for (Map<String, Object> row :
                queryRows(conn, "SELECT day, base, quote, rate_micro FROM fx_rates")) {
            out.put(
                    List.of(
                            ((Number) row.get("day")).intValue(),
                            str(row.get("base")),
                            str(row.get("quote"))),
                    ((Number) row.get("rate_micro")).longValue());
        }
        return out;
    }

    private static String str(Object o) {
        return o == null ? null : String.valueOf(o);
    }

    private static boolean isNonVoided(Map<String, Object> tx) {
        return !"voided".equals(tx.get("status"));
    }

    private static int bankerRound(long numerator, long denominator) {
        if (denominator == 0) {
            throw new IllegalArgumentException("denominator must be non-zero");
        }
        return BigDecimal.valueOf(numerator)
                .divide(BigDecimal.valueOf(denominator), 0, RoundingMode.HALF_EVEN)
                .intValue();
    }

    private static Map<String, Object> selectRule(
            List<Map<String, Object>> rules, Map<String, Object> merchant) {
        if (merchant == null) {
            return null;
        }
        String nameLower = str(merchant.get("name")).toLowerCase(Locale.ROOT);
        String mcc = str(merchant.get("mcc"));
        List<Map<String, Object>> candidates = new ArrayList<>();
        for (Map<String, Object> rule : rules) {
            if (!mcc.equals(str(rule.get("mcc")))) {
                continue;
            }
            String pattern = str(rule.get("pattern")).toLowerCase(Locale.ROOT);
            if (nameLower.contains(pattern)) {
                candidates.add(rule);
            }
        }
        if (candidates.isEmpty()) {
            return null;
        }
        candidates.sort(
                Comparator.comparingInt(
                                (Map<String, Object> r) ->
                                        ((Number) r.get("priority")).intValue())
                        .thenComparing(r -> str(r.get("rule_id"))));
        return candidates.get(0);
    }

    private static int[] expectedFeeForCapture(
            Map<String, Object> capture,
            Map<String, Object> merchant,
            List<Map<String, Object>> rules,
            JsonObject policy) {
        Map<String, Object> rule = selectRule(rules, merchant);
        long amount = ((Number) capture.get("amount_minor")).longValue();
        if (rule != null) {
            int bps = ((Number) rule.get("fee_bps")).intValue();
            return new int[] {bankerRound(amount * bps, 10000), ((Number) rule.get("priority")).intValue()};
        }
        int bps;
        if (merchant == null || "verified".equals(merchant.get("kyc_status"))) {
            bps = policy.get("default_fee_bps").getAsInt();
        } else {
            bps = policy.get("unverified_fee_bps").getAsInt();
        }
        return new int[] {bankerRound(amount * bps, 10000), -1};
    }

    private static JsonArray buildFeeAnomalies(
            List<Map<String, Object>> transactions,
            Map<String, Map<String, Object>> merchants,
            List<Map<String, Object>> rules,
            JsonObject policy) {
        Map<String, List<Map<String, Object>>> feesByParent = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            if (!"fee".equals(tx.get("kind"))) {
                continue;
            }
            if (tx.get("status") == null || "voided".equals(tx.get("status"))) {
                continue;
            }
            if (tx.get("parent_tx_id") == null) {
                continue;
            }
            feesByParent.computeIfAbsent(str(tx.get("parent_tx_id")), k -> new ArrayList<>()).add(tx);
        }

        List<JsonObject> anomalies = new ArrayList<>();
        for (Map<String, Object> tx : transactions) {
            if (!"capture".equals(tx.get("kind")) || !isNonVoided(tx)) {
                continue;
            }
            Map<String, Object> merchant =
                    tx.get("merchant_id") == null
                            ? null
                            : merchants.get(str(tx.get("merchant_id")));
            int[] exp = expectedFeeForCapture(tx, merchant, rules, policy);
            int expected = exp[0];
            Integer priority = exp[1] >= 0 ? exp[1] : null;
            List<Map<String, Object>> related = feesByParent.getOrDefault(str(tx.get("tx_id")), List.of());
            if (related.isEmpty()) {
                JsonObject a = new JsonObject();
                a.addProperty("tx_id", str(tx.get("tx_id")));
                a.addProperty("account_id", str(tx.get("account_id")));
                if (tx.get("merchant_id") != null) {
                    a.addProperty("merchant_id", str(tx.get("merchant_id")));
                } else {
                    a.add("merchant_id", JsonNull.INSTANCE);
                }
                a.addProperty("expected_fee_minor", expected);
                a.add("actual_fee_minor", JsonNull.INSTANCE);
                a.addProperty("finding_code", "fee_missing");
                if (priority != null) {
                    a.addProperty("priority", priority);
                } else {
                    a.add("priority", JsonNull.INSTANCE);
                }
                anomalies.add(a);
                continue;
            }
            long actual = 0;
            for (Map<String, Object> f : related) {
                actual += ((Number) f.get("amount_minor")).longValue();
            }
            if (actual != expected) {
                JsonObject a = new JsonObject();
                a.addProperty("tx_id", str(tx.get("tx_id")));
                a.addProperty("account_id", str(tx.get("account_id")));
                if (tx.get("merchant_id") != null) {
                    a.addProperty("merchant_id", str(tx.get("merchant_id")));
                } else {
                    a.add("merchant_id", JsonNull.INSTANCE);
                }
                a.addProperty("expected_fee_minor", expected);
                a.addProperty("actual_fee_minor", (int) actual);
                a.addProperty("finding_code", "fee_amount_mismatch");
                if (priority != null) {
                    a.addProperty("priority", priority);
                } else {
                    a.add("priority", JsonNull.INSTANCE);
                }
                anomalies.add(a);
            }
        }
        anomalies.sort(
                Comparator.comparing((JsonObject o) -> o.get("finding_code").getAsString())
                        .thenComparing(o -> o.get("tx_id").getAsString()));
        JsonArray arr = new JsonArray();
        anomalies.forEach(arr::add);
        return arr;
    }

    private static boolean isAccountClosed(Map<String, Object> account, int currentDay) {
        Object closed = account.get("closed_day");
        return closed != null && ((Number) closed).intValue() <= currentDay;
    }

    private static JsonArray buildStuckHolds(
            List<Map<String, Object>> holds,
            Map<String, Map<String, Object>> accounts,
            JsonObject policy) {
        long boundary = policy.get("current_day_end_utc_seconds").getAsLong();
        int currentDay = policy.get("current_day").getAsInt();
        List<JsonObject> rows = new ArrayList<>();
        for (Map<String, Object> hold : holds) {
            if (hold.get("released_ts") != null) {
                continue;
            }
            long expires = ((Number) hold.get("expires_ts")).longValue();
            if (expires >= boundary) {
                continue;
            }
            Map<String, Object> account = accounts.get(str(hold.get("account_id")));
            if (account != null && isAccountClosed(account, currentDay)) {
                continue;
            }
            String tenantId = account != null ? str(account.get("tenant_id")) : "";
            JsonObject row = new JsonObject();
            row.addProperty("hold_id", str(hold.get("hold_id")));
            row.addProperty("account_id", str(hold.get("account_id")));
            row.addProperty("tenant_id", tenantId);
            row.addProperty("amount_minor", ((Number) hold.get("amount_minor")).intValue());
            row.addProperty("placed_ts", ((Number) hold.get("placed_ts")).longValue());
            row.addProperty("expires_ts", expires);
            String reason = hold.get("reason") == null ? "" : str(hold.get("reason"));
            row.addProperty("reason", reason);
            rows.add(row);
        }
        rows.sort(
                Comparator.comparingLong((JsonObject r) -> r.get("expires_ts").getAsLong())
                        .thenComparing(r -> r.get("hold_id").getAsString()));
        JsonArray arr = new JsonArray();
        rows.forEach(arr::add);
        return arr;
    }

    private static Map<String, Integer> unclearedHoldsByAccount(
            List<Map<String, Object>> holds, JsonObject policy) {
        long boundary = policy.get("current_day_end_utc_seconds").getAsLong();
        Map<String, Integer> sums = new HashMap<>();
        for (Map<String, Object> hold : holds) {
            if (hold.get("released_ts") != null) {
                continue;
            }
            long expires = ((Number) hold.get("expires_ts")).longValue();
            if (expires < boundary) {
                continue;
            }
            String acct = str(hold.get("account_id"));
            int amt = ((Number) hold.get("amount_minor")).intValue();
            sums.merge(acct, amt, Integer::sum);
        }
        return sums;
    }

    private static Map<String, Integer> computeOpenBalances(List<Map<String, Object>> transactions) {
        Map<String, Integer> sums = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            if (!isNonVoided(tx)) {
                continue;
            }
            String kind = tx.get("kind") == null ? "" : str(tx.get("kind"));
            Integer sign = KIND_SIGNS.get(kind);
            if (sign == null) {
                sign = 0;
            }
            int amt = ((Number) tx.get("amount_minor")).intValue();
            String acct = str(tx.get("account_id"));
            sums.merge(acct, sign * amt, Integer::sum);
        }
        return sums;
    }

    private static Map<String, Integer> capturesTodayPerAccount(
            List<Map<String, Object>> transactions, int currentDay) {
        Map<String, Integer> counts = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            if (!isNonVoided(tx) || !"capture".equals(tx.get("kind"))) {
                continue;
            }
            long ts = ((Number) tx.get("ts_utc")).longValue();
            if (ts / 86400 != currentDay) {
                continue;
            }
            counts.merge(str(tx.get("account_id")), 1, Integer::sum);
        }
        return counts;
    }

    private static JsonArray buildAccountFindings(
            List<Map<String, Object>> accounts,
            List<Map<String, Object>> transactions,
            List<Map<String, Object>> holds,
            Map<String, Map<String, Object>> tenants,
            JsonObject policy) {
        Map<String, Integer> openBalances = computeOpenBalances(transactions);
        Map<String, Integer> uncleared = unclearedHoldsByAccount(holds, policy);
        int currentDay = policy.get("current_day").getAsInt();
        Map<String, Integer> captureCounts = capturesTodayPerAccount(transactions, currentDay);
        int severe = policy.get("severe_floor_breach_minor").getAsInt();
        int velocity = policy.get("velocity_threshold_per_day").getAsInt();

        List<JsonObject> findings = new ArrayList<>();
        for (Map<String, Object> account : accounts) {
            if (isAccountClosed(account, currentDay)) {
                continue;
            }
            Map<String, Object> tenant = tenants.get(str(account.get("tenant_id")));
            if (tenant == null) {
                continue;
            }
            String accountId = str(account.get("account_id"));
            int openBalance = openBalances.getOrDefault(accountId, 0);
            int unclearedAmount = uncleared.getOrDefault(accountId, 0);
            int available = openBalance - unclearedAmount;
            int floor = ((Number) tenant.get("minimum_balance_minor")).intValue();

            if (openBalance < 0) {
                JsonObject f = new JsonObject();
                f.addProperty("account_id", accountId);
                f.addProperty("tenant_id", str(account.get("tenant_id")));
                f.addProperty("finding_code", "negative_open_balance");
                f.addProperty("severity", "critical");
                JsonObject ev = new JsonObject();
                ev.addProperty("open_balance", openBalance);
                f.add("evidence", ev);
                findings.add(f);
            }
            if (available < floor) {
                int gap = floor - available;
                String severity = gap >= severe ? "high" : "medium";
                JsonObject f = new JsonObject();
                f.addProperty("account_id", accountId);
                f.addProperty("tenant_id", str(account.get("tenant_id")));
                f.addProperty("finding_code", "available_below_floor");
                f.addProperty("severity", severity);
                JsonObject ev = new JsonObject();
                ev.addProperty("available", available);
                ev.addProperty("floor", floor);
                ev.addProperty("gap", gap);
                f.add("evidence", ev);
                findings.add(f);
            }
            int capturesToday = captureCounts.getOrDefault(accountId, 0);
            if (capturesToday >= velocity) {
                JsonObject f = new JsonObject();
                f.addProperty("account_id", accountId);
                f.addProperty("tenant_id", str(account.get("tenant_id")));
                f.addProperty("finding_code", "velocity_breach");
                f.addProperty("severity", "medium");
                JsonObject ev = new JsonObject();
                ev.addProperty("captures_today", capturesToday);
                ev.addProperty("threshold", velocity);
                f.add("evidence", ev);
                findings.add(f);
            }
        }
        findings.sort(
                Comparator.comparingInt(
                                (JsonObject f) -> SEVERITY_RANKS.get(f.get("severity").getAsString()))
                        .thenComparing(f -> f.get("finding_code").getAsString())
                        .thenComparing(f -> f.get("tenant_id").getAsString())
                        .thenComparing(f -> f.get("account_id").getAsString()));
        JsonArray arr = new JsonArray();
        findings.forEach(arr::add);
        return arr;
    }

    private static class ChainResolve {
        final Map<String, String> txToRoot;
        final List<List<String>> cycles;

        ChainResolve(Map<String, String> txToRoot, List<List<String>> cycles) {
            this.txToRoot = txToRoot;
            this.cycles = cycles;
        }
    }

    private static ChainResolve resolveChains(List<Map<String, Object>> transactions) {
        Map<String, Map<String, Object>> byId = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            byId.put(str(tx.get("tx_id")), tx);
        }
        Map<String, String> txToRoot = new HashMap<>();
        List<List<String>> cycles = new ArrayList<>();
        Set<String> seenCycleKeys = new HashSet<>();

        for (String start : byId.keySet()) {
            if (txToRoot.containsKey(start)) {
                continue;
            }
            List<String> path = new ArrayList<>();
            Set<String> pathSet = new HashSet<>();
            String cur = start;
            while (cur != null) {
                if (txToRoot.containsKey(cur)) {
                    String resolved = txToRoot.get(cur);
                    for (String node : path) {
                        txToRoot.put(node, resolved);
                    }
                    break;
                }
                if (pathSet.contains(cur)) {
                    int cycleStart = path.indexOf(cur);
                    List<String> cycleMembers = new ArrayList<>(path.subList(cycleStart, path.size()));
                    Collections.sort(cycleMembers);
                    String key = String.join("\0", cycleMembers);
                    if (!seenCycleKeys.contains(key)) {
                        cycles.add(cycleMembers);
                        seenCycleKeys.add(key);
                    }
                    String cycleRoot = cycleMembers.get(0);
                    for (String node : path) {
                        txToRoot.put(node, cycleRoot);
                    }
                    break;
                }
                path.add(cur);
                pathSet.add(cur);
                Map<String, Object> tx = byId.get(cur);
                String parentId = tx.get("parent_tx_id") == null ? null : str(tx.get("parent_tx_id"));
                if (parentId == null || !byId.containsKey(parentId)) {
                    String root = cur;
                    for (String node : path) {
                        txToRoot.put(node, root);
                    }
                    cur = null;
                } else {
                    cur = parentId;
                }
            }
        }
        return new ChainResolve(txToRoot, cycles);
    }

    private static JsonArray buildChainAnomalies(
            List<Map<String, Object>> transactions,
            Map<String, Map<String, Object>> accounts) {
        Map<String, Map<String, Object>> byId = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            byId.put(str(tx.get("tx_id")), tx);
        }
        ChainResolve resolved = resolveChains(transactions);
        Map<String, String> txToRoot = resolved.txToRoot;
        Set<String> cycleMemberSet = new HashSet<>();
        for (List<String> cycle : resolved.cycles) {
            cycleMemberSet.addAll(cycle);
        }

        Map<String, List<String>> chainMembers = new HashMap<>();
        for (Map.Entry<String, String> e : txToRoot.entrySet()) {
            chainMembers.computeIfAbsent(e.getValue(), k -> new ArrayList<>()).add(e.getKey());
        }

        List<JsonObject> anomalies = new ArrayList<>();

        for (List<String> cycle : resolved.cycles) {
            JsonObject a = new JsonObject();
            a.addProperty("chain_root", cycle.get(0));
            a.addProperty("finding_code", "cycle_in_chain");
            a.add("tx_ids", stringListToJson(cycle));
            a.addProperty("severity", "critical");
            anomalies.add(a);
        }

        Map<List<Object>, List<String>> refundGroups = new HashMap<>();
        for (Map<String, Object> tx : transactions) {
            if (!"refund".equals(tx.get("kind")) || !isNonVoided(tx)) {
                continue;
            }
            if (cycleMemberSet.contains(str(tx.get("tx_id")))) {
                continue;
            }
            List<Object> key =
                    Arrays.asList(
                            str(tx.get("account_id")),
                            tx.get("parent_tx_id"),
                            ((Number) tx.get("amount_minor")).intValue());
            refundGroups.computeIfAbsent(key, k -> new ArrayList<>()).add(str(tx.get("tx_id")));
        }
        for (List<String> ids : refundGroups.values()) {
            if (ids.size() < 2) {
                continue;
            }
            Collections.sort(ids);
            String root = txToRoot.get(ids.get(0));
            JsonObject a = new JsonObject();
            a.addProperty("chain_root", root);
            a.addProperty("finding_code", "duplicate_refund");
            a.add("tx_ids", stringListToJson(ids));
            a.addProperty("severity", "high");
            anomalies.add(a);
        }

        for (Map.Entry<String, List<String>> entry : chainMembers.entrySet()) {
            String root = entry.getKey();
            List<String> members = entry.getValue();
            if (cycleMemberSet.contains(root)) {
                continue;
            }
            List<Map<String, Object>> memberTxs = new ArrayList<>();
            for (String m : members) {
                memberTxs.add(byId.get(m));
            }
            List<Map<String, Object>> nonVoided = new ArrayList<>();
            for (Map<String, Object> t : memberTxs) {
                if (isNonVoided(t)) {
                    nonVoided.add(t);
                }
            }
            boolean hasRefund = false;
            for (Map<String, Object> t : nonVoided) {
                if ("refund".equals(t.get("kind"))) {
                    hasRefund = true;
                    break;
                }
            }
            Set<String> memberSet = new HashSet<>(members);
            List<Map<String, Object>> chargebacks = new ArrayList<>();
            for (Map<String, Object> t : nonVoided) {
                if ("chargeback".equals(t.get("kind"))
                        && memberSet.contains(str(t.get("parent_tx_id")))) {
                    chargebacks.add(t);
                }
            }
            if (hasRefund && !chargebacks.isEmpty()) {
                List<String> sortedMembers = new ArrayList<>(members);
                Collections.sort(sortedMembers);
                JsonObject a = new JsonObject();
                a.addProperty("chain_root", root);
                a.addProperty("finding_code", "double_resolution");
                a.add("tx_ids", stringListToJson(sortedMembers));
                a.addProperty("severity", "critical");
                anomalies.add(a);
            }
        }

        for (Map.Entry<String, List<String>> entry : chainMembers.entrySet()) {
            String root = entry.getKey();
            List<String> members = entry.getValue();
            if (cycleMemberSet.contains(root)) {
                continue;
            }
            String accountId = str(byId.get(root).get("account_id"));
            Map<String, Object> account = accounts.get(accountId);
            if (account == null || account.get("closed_day") == null) {
                continue;
            }
            int closedDay = ((Number) account.get("closed_day")).intValue();
            List<Map<String, Object>> memberTxs = new ArrayList<>();
            for (String m : members) {
                memberTxs.add(byId.get(m));
            }
            List<Map<String, Object>> nonVoided = new ArrayList<>();
            for (Map<String, Object> t : memberTxs) {
                if (isNonVoided(t)) {
                    nonVoided.add(t);
                }
            }
            if (nonVoided.isEmpty()) {
                continue;
            }
            int resolutionDay = 0;
            for (Map<String, Object> t : nonVoided) {
                int day = (int) (((Number) t.get("ts_utc")).longValue() / 86400);
                resolutionDay = Math.max(resolutionDay, day);
            }
            if (resolutionDay > closedDay) {
                List<String> sortedMembers = new ArrayList<>(members);
                Collections.sort(sortedMembers);
                JsonObject a = new JsonObject();
                a.addProperty("chain_root", root);
                a.addProperty("finding_code", "post_close_chain_activity");
                a.add("tx_ids", stringListToJson(sortedMembers));
                a.addProperty("severity", "medium");
                anomalies.add(a);
            }
        }

        anomalies.sort(
                Comparator.comparingInt(
                                (JsonObject a) ->
                                        SEVERITY_RANKS.get(a.get("severity").getAsString()))
                        .thenComparing(a -> a.get("finding_code").getAsString())
                        .thenComparing(a -> a.get("chain_root").getAsString()));
        JsonArray arr = new JsonArray();
        anomalies.forEach(arr::add);
        return arr;
    }

    private static JsonArray buildFxFindings(
            List<Map<String, Object>> transactions,
            Map<String, Map<String, Object>> accounts,
            Map<String, Map<String, Object>> tenants,
            Map<List<Object>, Long> fxRates) {
        List<JsonObject> findings = new ArrayList<>();
        for (Map<String, Object> tx : transactions) {
            if (!isNonVoided(tx)) {
                continue;
            }
            Map<String, Object> account = accounts.get(str(tx.get("account_id")));
            if (account == null) {
                continue;
            }
            Map<String, Object> tenant = tenants.get(str(account.get("tenant_id")));
            if (tenant == null) {
                continue;
            }
            String base = str(tenant.get("base_currency"));
            String currency = str(tx.get("currency"));
            if (currency.equals(base)) {
                continue;
            }
            int offsetSeconds = ((Number) tenant.get("audit_day_offset_min")).intValue() * 60;
            long ts = ((Number) tx.get("ts_utc")).longValue();
            int expectedDay = (int) ((ts - offsetSeconds) / 86400);
            List<Object> key = List.of(expectedDay, currency, base);
            Long rate = fxRates.get(key);
            if (rate == null) {
                JsonObject f = new JsonObject();
                f.addProperty("tx_id", str(tx.get("tx_id")));
                f.addProperty("currency", currency);
                f.addProperty("base_currency", base);
                f.addProperty("expected_day", expectedDay);
                f.addProperty("finding_code", "fx_missing");
                f.addProperty("severity", "high");
                findings.add(f);
                continue;
            }
            Object recorded = tx.get("fx_micro");
            long recordedVal = recorded == null ? Long.MIN_VALUE : ((Number) recorded).longValue();
            if (recordedVal != rate) {
                JsonObject f = new JsonObject();
                f.addProperty("tx_id", str(tx.get("tx_id")));
                f.addProperty("currency", currency);
                f.addProperty("base_currency", base);
                f.addProperty("expected_micro", rate);
                if (recorded == null) {
                    f.add("recorded_micro", JsonNull.INSTANCE);
                } else {
                    f.addProperty("recorded_micro", recordedVal);
                }
                f.addProperty("finding_code", "fx_drift");
                f.addProperty("severity", "medium");
                findings.add(f);
            }
        }
        findings.sort(
                Comparator.comparingInt(
                                (JsonObject f) ->
                                        SEVERITY_RANKS.get(f.get("severity").getAsString()))
                        .thenComparing(f -> f.get("finding_code").getAsString())
                        .thenComparing(f -> f.get("tx_id").getAsString()));
        JsonArray arr = new JsonArray();
        findings.forEach(arr::add);
        return arr;
    }

    private static JsonObject buildDataQuality(
            Connection conn,
            List<Map<String, Object>> accounts,
            List<Map<String, Object>> transactions,
            List<Map<String, Object>> holds,
            Map<String, Map<String, Object>> tenants,
            JsonArray fxFindings,
            JsonObject policy) throws SQLException {
        int currentDay = policy.get("current_day").getAsInt();
        long boundary = policy.get("current_day_end_utc_seconds").getAsLong();

        Set<String> accountIds = new HashSet<>();
        for (Map<String, Object> acc : accounts) {
            accountIds.add(str(acc.get("account_id")));
        }
        Set<String> tenantIds = tenants.keySet();

        int orphanTenantAccounts = 0;
        for (Map<String, Object> acc : accounts) {
            if (!tenantIds.contains(str(acc.get("tenant_id")))) {
                orphanTenantAccounts++;
            }
        }
        int orphanHolds = 0;
        for (Map<String, Object> hold : holds) {
            if (!accountIds.contains(str(hold.get("account_id")))) {
                orphanHolds++;
            }
        }

        int unknownKindRows = 0;
        int negativeAmounts = 0;
        for (Map<String, Object> tx : transactions) {
            if (!isNonVoided(tx)) {
                continue;
            }
            String kind = tx.get("kind") == null ? null : str(tx.get("kind"));
            if (kind == null || !KIND_SIGNS.containsKey(kind)) {
                unknownKindRows++;
            }
            int amt = ((Number) tx.get("amount_minor")).intValue();
            if (amt < 0) {
                negativeAmounts++;
            }
        }

        int fxUnconvertible = 0;
        for (JsonElement el : fxFindings) {
            if ("fx_missing".equals(el.getAsJsonObject().get("finding_code").getAsString())) {
                fxUnconvertible++;
            }
        }

        Set<String> nonClosedAccounts = new HashSet<>();
        for (Map<String, Object> acc : accounts) {
            if (!isAccountClosed(acc, currentDay)) {
                nonClosedAccounts.add(str(acc.get("account_id")));
            }
        }

        Integer viewStalenessSeconds;
        boolean viewStale;
        if (nonClosedAccounts.isEmpty()) {
            viewStalenessSeconds = null;
            viewStale = true;
        } else {
            List<String> ids = new ArrayList<>(nonClosedAccounts);
            Collections.sort(ids);
            StringBuilder sql =
                    new StringBuilder("SELECT MAX(committed_ts) FROM mv_daily_balances WHERE account_id IN (");
            for (int i = 0; i < ids.size(); i++) {
                if (i > 0) {
                    sql.append(',');
                }
                sql.append('?');
            }
            sql.append(')');
            try (PreparedStatement ps = conn.prepareStatement(sql.toString())) {
                for (int i = 0; i < ids.size(); i++) {
                    ps.setString(i + 1, ids.get(i));
                }
                Long maxTs = null;
                try (ResultSet rs = ps.executeQuery()) {
                    if (rs.next() && rs.getObject(1) != null) {
                        maxTs = rs.getLong(1);
                    }
                }
                if (maxTs == null) {
                    viewStalenessSeconds = null;
                    viewStale = true;
                } else {
                    viewStalenessSeconds = (int) (boundary - maxTs);
                    int threshold = policy.get("balance_view_max_staleness_min").getAsInt() * 60;
                    viewStale = viewStalenessSeconds > threshold;
                }
            }
        }

        JsonObject dq = new JsonObject();
        dq.addProperty("fx_unconvertible_count", fxUnconvertible);
        dq.addProperty("negative_amounts", negativeAmounts);
        dq.addProperty("orphan_holds", orphanHolds);
        dq.addProperty("orphan_tenant_accounts", orphanTenantAccounts);
        dq.addProperty("unknown_kind_rows", unknownKindRows);
        dq.addProperty("view_stale", viewStale);
        if (viewStalenessSeconds == null) {
            dq.add("view_staleness_seconds", JsonNull.INSTANCE);
        } else {
            dq.addProperty("view_staleness_seconds", viewStalenessSeconds);
        }
        return dq;
    }

    private static JsonObject aggregateSummary(
            List<Map<String, Object>> accounts,
            Map<String, Map<String, Object>> tenants,
            JsonArray accountFindings,
            JsonArray feeAnomalies,
            JsonArray chainAnomalies,
            JsonArray fxFindings,
            double auditRunSeconds,
            JsonObject policy) {
        Map<String, Integer> bySeverity = new LinkedHashMap<>();
        bySeverity.put("critical", 0);
        bySeverity.put("high", 0);
        bySeverity.put("medium", 0);
        bySeverity.put("low", 0);
        Map<String, Integer> byCode = new TreeMap<>();

        for (JsonArray section :
                List.of(accountFindings, feeAnomalies, chainAnomalies, fxFindings)) {
            for (JsonElement el : section) {
                JsonObject finding = el.getAsJsonObject();
                if (finding.has("severity") && !finding.get("severity").isJsonNull()) {
                    String sev = finding.get("severity").getAsString();
                    bySeverity.merge(sev, 1, Integer::sum);
                }
                String code = finding.get("finding_code").getAsString();
                byCode.merge(code, 1, Integer::sum);
            }
        }

        int currentDay = policy.get("current_day").getAsInt();
        int nonClosed = 0;
        for (Map<String, Object> acc : accounts) {
            if (!isAccountClosed(acc, currentDay)) {
                nonClosed++;
            }
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("as_of_day", currentDay);
        summary.addProperty("audit_run_seconds", round6(auditRunSeconds));
        JsonObject byCodeJson = new JsonObject();
        for (Map.Entry<String, Integer> e : byCode.entrySet()) {
            byCodeJson.addProperty(e.getKey(), e.getValue());
        }
        summary.add("by_finding_code", byCodeJson);
        JsonObject bySevJson = new JsonObject();
        for (Map.Entry<String, Integer> e : bySeverity.entrySet()) {
            bySevJson.addProperty(e.getKey(), e.getValue());
        }
        summary.add("by_severity", bySevJson);
        summary.addProperty("non_closed_account_count", nonClosed);
        summary.addProperty("tenant_count", tenants.size());
        return summary;
    }

    private static JsonObject buildReport(Connection conn, JsonObject policy, double auditRunSeconds)
            throws SQLException {
        Map<String, Map<String, Object>> tenants = fetchTenants(conn);
        List<Map<String, Object>> accounts = fetchAccounts(conn);
        Map<String, Map<String, Object>> accountsById = new HashMap<>();
        for (Map<String, Object> a : accounts) {
            accountsById.put(str(a.get("account_id")), a);
        }
        List<Map<String, Object>> transactions = fetchTransactions(conn);
        List<Map<String, Object>> holds = fetchHolds(conn);
        Map<String, Map<String, Object>> merchants = fetchMerchants(conn);
        List<Map<String, Object>> rules = fetchRules(conn);
        Map<List<Object>, Long> fxRates = fetchFxRates(conn);

        JsonArray af =
                buildAccountFindings(accounts, transactions, holds, tenants, policy);
        JsonArray sh = buildStuckHolds(holds, accountsById, policy);
        JsonArray fa = buildFeeAnomalies(transactions, merchants, rules, policy);
        JsonArray ca = buildChainAnomalies(transactions, accountsById);
        JsonArray fxf = buildFxFindings(transactions, accountsById, tenants, fxRates);
        JsonObject dq = buildDataQuality(conn, accounts, transactions, holds, tenants, fxf, policy);
        JsonObject summary =
                aggregateSummary(
                        accounts, tenants, af, fa, ca, fxf, auditRunSeconds, policy);

        JsonObject report = new JsonObject();
        report.addProperty("schema_version", 1);
        report.addProperty("as_of_day", policy.get("current_day").getAsInt());
        report.add("summary", summary);
        report.add("account_findings", af);
        report.add("stuck_holds", sh);
        report.add("fee_anomalies", fa);
        report.add("chain_anomalies", ca);
        report.add("fx_findings", fxf);
        report.add("data_quality", dq);
        return report;
    }

    private static JsonArray stringListToJson(List<String> items) {
        JsonArray arr = new JsonArray();
        for (String s : items) {
            arr.add(s);
        }
        return arr;
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

    private static void writeReport(JsonObject report, Path outPath) throws IOException {
        Files.createDirectories(outPath.getParent());
        Gson gson = new GsonBuilder().setPrettyPrinting().serializeNulls().create();
        String text = gson.toJson(deepSort(report));
        if (!text.endsWith("\n")) {
            text = text + "\n";
        }
        Files.writeString(outPath, text, StandardCharsets.UTF_8);
    }
}

