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

public final class LedgerEventReconAudit {
    private static final Gson GSON =
            new GsonBuilder()
                    .disableHtmlEscaping()
                    .serializeNulls()
                    .setPrettyPrinting()
                    .create();

    private LedgerEventReconAudit() {}

    private static final class Hold {
        int seq;
        int amountCents;
        int day;
    }

    private static final class AcctState {
        String id;
        String status;
        int balanceCents;
        int totalDepositsCents;
        int totalWithdrawalsCents;
        int nReversedEvents;
        final List<Hold> activeHolds = new ArrayList<>();
        final Map<Integer, Integer> dailyWithdraws = new HashMap<>();
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

    private static String severityForCode(String code) {
        if (code.startsWith("E_")) {
            return "error";
        }
        if (code.startsWith("W_")) {
            return "warning";
        }
        return "note";
    }

    private static int overdraftFloor(JsonObject account, JsonObject policy) {
        if ("credit".equals(account.get("account_type").getAsString())) {
            for (JsonElement el : policy.getAsJsonArray("overdraft_allowed_account_types")) {
                if ("credit".equals(el.getAsString())) {
                    return -policy.get("credit_account_credit_limit_cents").getAsInt();
                }
            }
        }
        return 0;
    }

    private static int activeDailyLimit(JsonObject account, JsonObject policy) {
        if (account.has("daily_withdraw_limit_cents")
                && !account.get("daily_withdraw_limit_cents").isJsonNull()) {
            return account.get("daily_withdraw_limit_cents").getAsInt();
        }
        return policy.get("default_daily_withdraw_limit_cents").getAsInt();
    }

    private static boolean statusBlocksCredit(String status, String action) {
        if ("active".equals(status)) {
            return false;
        }
        if ("block_all".equals(action)) {
            return true;
        }
        if ("allow_credits_only".equals(action)) {
            return false;
        }
        return true;
    }

    private static boolean statusBlocksDebit(String status, String action) {
        return !"active".equals(status);
    }

    private static String actionFor(String status, JsonObject policy) {
        if ("frozen".equals(status)) {
            return policy.get("frozen_account_action").getAsString();
        }
        if ("closed".equals(status)) {
            return policy.get("closed_account_action").getAsString();
        }
        return "";
    }

    private static String diagCodeForStatus(String status) {
        if ("frozen".equals(status)) {
            return "E_FROZEN_ACCOUNT";
        }
        if ("closed".equals(status)) {
            return "E_CLOSED_ACCOUNT";
        }
        return "";
    }

    private static int intOrZero(JsonObject o, String key) {
        if (!o.has(key) || o.get(key).isJsonNull()) {
            return 0;
        }
        return o.get(key).getAsInt();
    }

    private static Map<String, Object> runSimulation(
            List<JsonObject> accountsIn,
            List<JsonObject> eventsIn,
            Map<String, Integer> snapshots,
            JsonObject policy) {
        Map<String, Integer> severityRanks = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e :
                policy.getAsJsonObject("severity_ranks").entrySet()) {
            severityRanks.put(e.getKey(), e.getValue().getAsInt());
        }

        Map<String, JsonObject> accountsById = new TreeMap<>();
        for (JsonObject a : accountsIn) {
            accountsById.put(a.get("id").getAsString(), a);
        }

        Map<String, AcctState> states = new TreeMap<>();
        for (JsonObject a : accountsIn) {
            String id = a.get("id").getAsString();
            AcctState st = new AcctState();
            st.id = id;
            st.status = a.get("status").getAsString();
            st.balanceCents = a.get("opening_balance_cents").getAsInt();
            states.put(id, st);
        }

        List<Map<String, Object>> diagnostics = new ArrayList<>();

        List<JsonObject> eventsSorted = new ArrayList<>(eventsIn);
        eventsSorted.sort(Comparator.comparingInt(e -> e.get("seq").getAsInt()));
        Map<Integer, JsonObject> eventsBySeq = new HashMap<>();
        for (JsonObject e : eventsSorted) {
            eventsBySeq.put(e.get("seq").getAsInt(), e);
        }
        Set<Integer> reversedTargets = new HashSet<>();

        int maxEventDay = 0;
        int maxEventSeq = 0;
        if (!eventsSorted.isEmpty()) {
            for (JsonObject e : eventsSorted) {
                maxEventDay = Math.max(maxEventDay, e.get("day").getAsInt());
                maxEventSeq = Math.max(maxEventSeq, e.get("seq").getAsInt());
            }
        }

        for (JsonObject ev : eventsSorted) {
            String op = ev.get("op").getAsString();
            int seq = ev.get("seq").getAsInt();
            int day = ev.get("day").getAsInt();
            String acctId = ev.get("account").getAsString();
            if (!states.containsKey(acctId)) {
                continue;
            }
            AcctState srcState = states.get(acctId);
            JsonObject srcAcct = accountsById.get(acctId);
            int amount = intOrZero(ev, "amount_cents");

            if ("deposit".equals(op)) {
                if (!"active".equals(srcAcct.get("status").getAsString())) {
                    String action = actionFor(srcAcct.get("status").getAsString(), policy);
                    if (statusBlocksCredit(srcAcct.get("status").getAsString(), action)) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                diagCodeForStatus(srcAcct.get("status").getAsString()),
                                acctId,
                                seq,
                                new TreeMap<>());
                        continue;
                    }
                }
                srcState.balanceCents += amount;
                srcState.totalDepositsCents += amount;
                continue;
            }

            if ("withdraw".equals(op)) {
                if (!"active".equals(srcAcct.get("status").getAsString())) {
                    String action = actionFor(srcAcct.get("status").getAsString(), policy);
                    if (statusBlocksDebit(srcAcct.get("status").getAsString(), action)) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                diagCodeForStatus(srcAcct.get("status").getAsString()),
                                acctId,
                                seq,
                                new TreeMap<>());
                        continue;
                    }
                }
                int limit = activeDailyLimit(srcAcct, policy);
                int current = srcState.dailyWithdraws.getOrDefault(day, 0);
                int after = current + amount;
                if (after > limit) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("attempted_amount_cents", amount);
                    evidence.put("daily_total_after_cents", after);
                    evidence.put("limit_cents", limit);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_DAILY_LIMIT_EXCEEDED",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                int floor = overdraftFloor(srcAcct, policy);
                int newBal = srcState.balanceCents - amount;
                int held = holdTotal(srcState);
                int available = newBal - held;
                if (available < floor) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("attempted_amount_cents", amount);
                    evidence.put("available_cents", available);
                    evidence.put("floor_cents", floor);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INSUFFICIENT_FUNDS",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                srcState.balanceCents = newBal;
                srcState.totalWithdrawalsCents += amount;
                srcState.dailyWithdraws.put(day, after);
                continue;
            }

            if ("transfer".equals(op)) {
                String tgtId =
                        ev.has("target_account") && !ev.get("target_account").isJsonNull()
                                ? ev.get("target_account").getAsString()
                                : null;
                if (tgtId != null && tgtId.equals(acctId)) {
                    if ("error".equals(policy.get("transfer_self_action").getAsString())) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                "E_SELF_TRANSFER",
                                acctId,
                                seq,
                                new TreeMap<>());
                    }
                    continue;
                }
                if (tgtId == null || !states.containsKey(tgtId)) {
                    continue;
                }
                AcctState tgtState = states.get(tgtId);
                JsonObject tgtAcct = accountsById.get(tgtId);
                if (!"active".equals(srcAcct.get("status").getAsString())) {
                    String action = actionFor(srcAcct.get("status").getAsString(), policy);
                    if (statusBlocksDebit(srcAcct.get("status").getAsString(), action)) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                diagCodeForStatus(srcAcct.get("status").getAsString()),
                                acctId,
                                seq,
                                new TreeMap<>());
                        continue;
                    }
                }
                if (!"active".equals(tgtAcct.get("status").getAsString())) {
                    String action = actionFor(tgtAcct.get("status").getAsString(), policy);
                    if (statusBlocksCredit(tgtAcct.get("status").getAsString(), action)) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                diagCodeForStatus(tgtAcct.get("status").getAsString()),
                                tgtId,
                                seq,
                                new TreeMap<>());
                        continue;
                    }
                }
                int limit = activeDailyLimit(srcAcct, policy);
                int current = srcState.dailyWithdraws.getOrDefault(day, 0);
                int after = current + amount;
                if (after > limit) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("attempted_amount_cents", amount);
                    evidence.put("daily_total_after_cents", after);
                    evidence.put("limit_cents", limit);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_DAILY_LIMIT_EXCEEDED",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                int floor = overdraftFloor(srcAcct, policy);
                int newSrc = srcState.balanceCents - amount;
                int held = holdTotal(srcState);
                int available = newSrc - held;
                if (available < floor) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("attempted_amount_cents", amount);
                    evidence.put("available_cents", available);
                    evidence.put("floor_cents", floor);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INSUFFICIENT_FUNDS",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                srcState.balanceCents = newSrc;
                srcState.totalWithdrawalsCents += amount;
                srcState.dailyWithdraws.put(day, after);
                tgtState.balanceCents += amount;
                tgtState.totalDepositsCents += amount;
                continue;
            }

            if ("hold".equals(op)) {
                if (!"active".equals(srcAcct.get("status").getAsString())) {
                    String action = actionFor(srcAcct.get("status").getAsString(), policy);
                    if (statusBlocksDebit(srcAcct.get("status").getAsString(), action)) {
                        emitDiag(
                                diagnostics,
                                severityRanks,
                                diagCodeForStatus(srcAcct.get("status").getAsString()),
                                acctId,
                                seq,
                                new TreeMap<>());
                        continue;
                    }
                }
                int floor = overdraftFloor(srcAcct, policy);
                int held = holdTotal(srcState);
                int available = srcState.balanceCents - held - amount;
                if (available < floor) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("attempted_amount_cents", amount);
                    evidence.put("available_cents", available);
                    evidence.put("floor_cents", floor);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INSUFFICIENT_FUNDS",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                Hold h = new Hold();
                h.seq = seq;
                h.amountCents = amount;
                h.day = day;
                srcState.activeHolds.add(h);
                continue;
            }

            if ("release".equals(op)) {
                if (!ev.has("reverses_seq") || ev.get("reverses_seq").isJsonNull()) {
                    continue;
                }
                int targetSeq = ev.get("reverses_seq").getAsInt();
                for (int i = 0; i < srcState.activeHolds.size(); i++) {
                    if (srcState.activeHolds.get(i).seq == targetSeq) {
                        srcState.activeHolds.remove(i);
                        break;
                    }
                }
                continue;
            }

            if ("reverse".equals(op)) {
                Integer targetSeq =
                        ev.has("reverses_seq") && !ev.get("reverses_seq").isJsonNull()
                                ? ev.get("reverses_seq").getAsInt()
                                : null;
                if (targetSeq == null || !eventsBySeq.containsKey(targetSeq)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "target_not_found");
                    evidence.put("reverses_seq", targetSeq != null ? targetSeq : -1);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INVALID_REVERSAL",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                JsonObject orig = eventsBySeq.get(targetSeq);
                String origOp = orig.get("op").getAsString();
                if ("hold".equals(origOp) || "release".equals(origOp) || "reverse".equals(origOp)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "target_not_reversible");
                    evidence.put("reverses_seq", targetSeq);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INVALID_REVERSAL",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                if (reversedTargets.contains(targetSeq)) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "target_already_reversed");
                    evidence.put("reverses_seq", targetSeq);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INVALID_REVERSAL",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                if (day - orig.get("day").getAsInt() > policy.get("reversal_window_days").getAsInt()) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("reason", "outside_window");
                    evidence.put("reverses_seq", targetSeq);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "E_INVALID_REVERSAL",
                            acctId,
                            seq,
                            evidence);
                    continue;
                }
                int origAmount = intOrZero(orig, "amount_cents");
                if ("deposit".equals(origOp)) {
                    AcctState a = states.get(orig.get("account").getAsString());
                    a.balanceCents -= origAmount;
                    a.totalWithdrawalsCents += origAmount;
                    a.nReversedEvents += 1;
                } else if ("withdraw".equals(origOp)) {
                    AcctState a = states.get(orig.get("account").getAsString());
                    a.balanceCents += origAmount;
                    a.totalDepositsCents += origAmount;
                    a.nReversedEvents += 1;
                } else if ("transfer".equals(origOp)) {
                    AcctState s = states.get(orig.get("account").getAsString());
                    s.balanceCents += origAmount;
                    s.totalDepositsCents += origAmount;
                    s.nReversedEvents += 1;
                    String tId =
                            orig.has("target_account")
                                            && !orig.get("target_account").isJsonNull()
                                    ? orig.get("target_account").getAsString()
                                    : null;
                    if (tId != null && states.containsKey(tId)) {
                        AcctState t = states.get(tId);
                        t.balanceCents -= origAmount;
                        t.totalWithdrawalsCents += origAmount;
                        t.nReversedEvents += 1;
                    }
                }
                reversedTargets.add(targetSeq);
            }
        }

        List<String> sortedIds = new ArrayList<>(states.keySet());
        sortedIds.sort(String::compareTo);
        for (String aid : sortedIds) {
            AcctState st = states.get(aid);
            for (Hold h : st.activeHolds) {
                int age = maxEventDay - h.day;
                if (age > policy.get("hold_max_age_days").getAsInt()) {
                    Map<String, Object> evidence = new TreeMap<>();
                    evidence.put("age_days", age);
                    evidence.put("amount_cents", h.amountCents);
                    evidence.put("hold_seq", h.seq);
                    emitDiag(
                            diagnostics,
                            severityRanks,
                            "W_HOLD_EXPIRED",
                            aid,
                            maxEventSeq,
                            evidence);
                }
            }
        }

        for (JsonObject a : accountsIn) {
            String aid = a.get("id").getAsString();
            if (!snapshots.containsKey(aid)) {
                continue;
            }
            int expected = snapshots.get(aid);
            int actual = states.get(aid).balanceCents;
            int delta = actual - expected;
            if (delta != 0) {
                Map<String, Object> evidence = new TreeMap<>();
                evidence.put("actual_balance_cents", actual);
                evidence.put("delta_cents", delta);
                evidence.put("expected_balance_cents", expected);
                emitDiag(
                        diagnostics,
                        severityRanks,
                        "N_RECONCILIATION_MISMATCH",
                        aid,
                        maxEventSeq,
                        evidence);
            }
        }

        diagnostics.sort(
                Comparator.<Map<String, Object>>comparingInt(
                                r -> (Integer) r.get("severity_rank"))
                        .thenComparingInt(r -> (Integer) r.get("seq"))
                        .thenComparing(r -> (String) r.get("code"))
                        .thenComparing(r -> (String) r.get("account")));

        Map<String, Object> sim = new TreeMap<>();
        sim.put("states", states);
        sim.put("diagnostics", diagnostics);
        sim.put("max_event_seq", maxEventSeq);
        return sim;
    }

    private static int holdTotal(AcctState st) {
        int t = 0;
        for (Hold h : st.activeHolds) {
            t += h.amountCents;
        }
        return t;
    }

    private static void emitDiag(
            List<Map<String, Object>> diagnostics,
            Map<String, Integer> severityRanks,
            String code,
            String account,
            int seq,
            Map<String, Object> evidence) {
        String severity = severityForCode(code);
        Map<String, Object> row = new TreeMap<>();
        row.put("account", account);
        row.put("code", code);
        row.put("evidence", new TreeMap<>(evidence));
        row.put("seq", seq);
        row.put("severity", severity);
        row.put("severity_rank", severityRanks.getOrDefault(severity, 0));
        diagnostics.add(row);
    }

    private static Map<String, Object> buildAccountState(
            List<JsonObject> accountsIn, Map<String, AcctState> states) {
        List<Map<String, Object>> rows = new ArrayList<>();
        List<JsonObject> sorted = new ArrayList<>(accountsIn);
        sorted.sort(Comparator.comparing(a -> a.get("id").getAsString()));
        for (JsonObject a : sorted) {
            AcctState st = states.get(a.get("id").getAsString());
            List<Hold> holds = new ArrayList<>(st.activeHolds);
            holds.sort(Comparator.comparingInt(h -> h.seq));
            List<Map<String, Object>> holdRows = new ArrayList<>();
            int holdTotal = 0;
            for (Hold h : holds) {
                Map<String, Object> hr = new TreeMap<>();
                hr.put("amount_cents", h.amountCents);
                hr.put("day", h.day);
                hr.put("seq", h.seq);
                holdRows.add(hr);
                holdTotal += h.amountCents;
            }
            Map<String, Object> row = new TreeMap<>();
            row.put("active_holds", holdRows);
            row.put("balance_cents", st.balanceCents);
            row.put("hold_amount_total_cents", holdTotal);
            row.put("id", st.id);
            row.put("n_reversed_events", st.nReversedEvents);
            row.put("status", st.status);
            row.put("total_deposits_cents", st.totalDepositsCents);
            row.put("total_withdrawals_cents", st.totalWithdrawalsCents);
            rows.add(row);
        }
        return Map.of("accounts", rows);
    }

    private static Map<String, Object> buildDiagnostics(List<Map<String, Object>> diagnostics) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> d : diagnostics) {
            Map<String, Object> row = new TreeMap<>();
            row.put("account", d.get("account"));
            row.put("code", d.get("code"));
            row.put("evidence", d.get("evidence"));
            row.put("seq", d.get("seq"));
            row.put("severity", d.get("severity"));
            row.put("severity_rank", d.get("severity_rank"));
            out.add(row);
        }
        return Map.of("diagnostics", out);
    }

    private static Map<String, Object> buildReconciliation(
            List<JsonObject> accountsIn,
            Map<String, Integer> snapshots,
            Map<String, AcctState> states) {
        List<Map<String, Object>> rows = new ArrayList<>();
        List<JsonObject> sorted = new ArrayList<>(accountsIn);
        sorted.sort(Comparator.comparing(a -> a.get("id").getAsString()));
        for (JsonObject a : sorted) {
            String id = a.get("id").getAsString();
            int actual = states.get(id).balanceCents;
            Map<String, Object> row = new TreeMap<>();
            row.put("account", id);
            row.put("actual_balance_cents", actual);
            if (!snapshots.containsKey(id)) {
                row.put("delta_cents", null);
                row.put("expected_balance_cents", null);
                row.put("status", "unsnapshotted");
            } else {
                int expected = snapshots.get(id);
                int delta = actual - expected;
                row.put("delta_cents", delta);
                row.put("expected_balance_cents", expected);
                row.put("status", delta == 0 ? "matched" : "mismatched");
            }
            rows.add(row);
        }
        return Map.of("accounts", rows);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> buildSummary(
            List<JsonObject> accountsIn,
            List<JsonObject> eventsIn,
            Map<String, Integer> snapshots,
            JsonObject policy,
            Map<String, Object> sim) {
        Map<String, AcctState> states = (Map<String, AcctState>) sim.get("states");
        List<Map<String, Object>> diagnostics =
                (List<Map<String, Object>>) sim.get("diagnostics");

        Map<String, Integer> bySeverity = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e :
                policy.getAsJsonObject("severity_ranks").entrySet()) {
            bySeverity.put(e.getKey(), 0);
        }
        for (Map<String, Object> d : diagnostics) {
            String sev = (String) d.get("severity");
            if (bySeverity.containsKey(sev)) {
                bySeverity.put(sev, bySeverity.get(sev) + 1);
            }
        }
        int nActiveHolds = 0;
        int totalReversed = 0;
        int mismatched = 0;
        for (JsonObject a : accountsIn) {
            String id = a.get("id").getAsString();
            AcctState st = states.get(id);
            nActiveHolds += st.activeHolds.size();
            totalReversed += st.nReversedEvents;
            if (snapshots.containsKey(id)) {
                if (st.balanceCents - snapshots.get(id) != 0) {
                    mismatched++;
                }
            }
        }
        Map<String, Object> totals = new TreeMap<>();
        totals.put("accounts_total", accountsIn.size());
        totals.put("events_total", eventsIn.size());
        totals.put("mismatched_accounts", mismatched);
        totals.put("n_active_holds_total", nActiveHolds);
        totals.put("total_diagnostics", diagnostics.size());
        totals.put("total_reversed_events", totalReversed);
        Map<String, Object> out = new TreeMap<>();
        out.put("by_severity", bySeverity);
        out.put("totals", totals);
        return out;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: LedgerEventReconAudit <input_dir> <output_dir>");
            System.exit(1);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);

        JsonObject accountsDoc = readObject(inDir.resolve("accounts.json"));
        JsonObject eventsDoc = readObject(inDir.resolve("events.json"));
        JsonObject snapshotsDoc = readObject(inDir.resolve("snapshots.json"));
        JsonObject policy = readObject(inDir.resolve("policy.json"));

        List<JsonObject> accountsIn = new ArrayList<>();
        for (JsonElement el : accountsDoc.getAsJsonArray("accounts")) {
            accountsIn.add(el.getAsJsonObject());
        }
        List<JsonObject> eventsIn = new ArrayList<>();
        for (JsonElement el : eventsDoc.getAsJsonArray("events")) {
            eventsIn.add(el.getAsJsonObject());
        }
        Map<String, Integer> snapshots = new TreeMap<>();
        if (snapshotsDoc.has("expected_balances")) {
            JsonObject eb = snapshotsDoc.getAsJsonObject("expected_balances");
            for (Map.Entry<String, JsonElement> e : eb.entrySet()) {
                snapshots.put(e.getKey(), e.getValue().getAsInt());
            }
        }

        Map<String, Object> sim = runSimulation(accountsIn, eventsIn, snapshots, policy);
        @SuppressWarnings("unchecked")
        Map<String, AcctState> states = (Map<String, AcctState>) sim.get("states");
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> diagnostics =
                (List<Map<String, Object>>) sim.get("diagnostics");

        writeCanonical(
                outDir.resolve("account_state.json"),
                buildAccountState(accountsIn, states));
        writeCanonical(outDir.resolve("event_diagnostics.json"), buildDiagnostics(diagnostics));
        writeCanonical(
                outDir.resolve("reconciliation_report.json"),
                buildReconciliation(accountsIn, snapshots, states));
        writeCanonical(
                outDir.resolve("compliance_summary.json"),
                buildSummary(accountsIn, eventsIn, snapshots, policy, sim));
    }
}
