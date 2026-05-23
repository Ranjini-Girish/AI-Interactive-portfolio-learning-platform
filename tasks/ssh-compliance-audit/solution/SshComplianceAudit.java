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
import java.nio.file.attribute.PosixFilePermission;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.PriorityQueue;
import java.util.Set;
import java.util.TreeMap;
/** SSH compliance audit oracle. */
public final class SshComplianceAudit {

    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();

    private static final Map<String, Integer> SEVERITY_RANK =
            Map.of("critical", 0, "high", 1, "medium", 2, "low", 3);

    private static final Map<String, Integer> ACTION_PRIORITY =
            Map.of(
                    "disable", 0,
                    "remove-sudo", 1,
                    "revoke-delegation", 2,
                    "revoke-key", 3,
                    "enforce-mfa", 4,
                    "rotate-password", 5,
                    "create-home", 6,
                    "lock-password", 7,
                    "rotate-key", 8,
                    "none", 9);

    private static final Map<String, String[]> FINDING_TO_ACTION = new LinkedHashMap<>();

    static {
        FINDING_TO_ACTION.put(
                "interactive_service_account",
                new String[] {"disable", "service account has interactive shell"});
        FINDING_TO_ACTION.put(
                "unauthorized_sudo",
                new String[] {"remove-sudo", "sudo membership is not allowlisted"});
        FINDING_TO_ACTION.put(
                "delegated_admin_exposure",
                new String[] {
                    "revoke-delegation", "transitive admin delegation is not allowed"
                });
        FINDING_TO_ACTION.put(
                "delegation_cycle",
                new String[] {"revoke-delegation", "delegation cycle must be broken"});
        FINDING_TO_ACTION.put(
                "escalation_chain_risk",
                new String[] {"revoke-delegation", "delegating user has high blast radius"});
        FINDING_TO_ACTION.put(
                "unrotated_compromised_key",
                new String[] {"revoke-key", "compromised key has not been rotated"});
        FINDING_TO_ACTION.put("mfa_disabled", new String[] {"enforce-mfa", "mfa is not enabled"});
        FINDING_TO_ACTION.put(
                "missing_mfa_state", new String[] {"enforce-mfa", "mfa state data is missing"});
        FINDING_TO_ACTION.put(
                "dormant_admin", new String[] {"lock-password", "admin account is dormant"});
        FINDING_TO_ACTION.put(
                "stale_password", new String[] {"rotate-password", "password age exceeds policy"});
        FINDING_TO_ACTION.put(
                "missing_password_state",
                new String[] {"rotate-password", "password state data is missing"});
        FINDING_TO_ACTION.put(
                "missing_home", new String[] {"create-home", "home directory is missing"});
        FINDING_TO_ACTION.put(
                "inactive_human", new String[] {"lock-password", "human account is inactive"});
        FINDING_TO_ACTION.put(
                "missing_login_history",
                new String[] {"lock-password", "login history data is missing"});
        FINDING_TO_ACTION.put(
                "stale_ssh_key", new String[] {"rotate-key", "ssh keys fail policy checks"});
        FINDING_TO_ACTION.put(
                "empty_ssh_key", new String[] {"rotate-key", "ssh keys fail policy checks"});
        FINDING_TO_ACTION.put(
                "missing_ssh_inventory",
                new String[] {"rotate-key", "ssh inventory data is missing"});
    }

    private static final List<String> ORDERED_ACTIONS =
            Arrays.asList(
                    "disable",
                    "remove-sudo",
                    "revoke-delegation",
                    "revoke-key",
                    "enforce-mfa",
                    "rotate-password",
                    "create-home",
                    "lock-password",
                    "rotate-key");

    private static final Map<String, String> SECTION_FOR_ACTION = Map.of(
            "disable", "# Disable service accounts with interactive shells",
            "remove-sudo", "# Remove unauthorized sudo access",
            "revoke-delegation", "# Revoke unauthorized admin delegations",
            "revoke-key", "# Revoke compromised SSH keys",
            "enforce-mfa", "# Enforce MFA enrollment",
            "rotate-password", "# Force password rotation at next login",
            "create-home", "# Create missing home directories",
            "lock-password", "# Lock inactive or dormant accounts",
            "rotate-key", "# Rotate stale or missing SSH keys");

    private static final Map<String, List<String>> CMD_TEMPLATES = Map.of(
            "disable",
                    Arrays.asList(
                            "usermod -L {u} || true", "usermod -s /usr/sbin/nologin {u} || true"),
            "remove-sudo", List.of("gpasswd -d {u} sudo 2>/dev/null || true"),
            "revoke-delegation", List.of("echo \"revoke delegations for {u}\" >/dev/null"),
            "revoke-key", List.of("echo \"revoke compromised key for {u}\" >/dev/null"),
            "enforce-mfa", List.of("echo \"require mfa enrollment for {u}\" >/dev/null"),
            "rotate-password", List.of("chage -d 0 {u} || true"),
            "create-home",
                    Arrays.asList(
                            "install -d -m 700 /home/{u} || true",
                            "chown {u}:{u} /home/{u} 2>/dev/null || true"),
            "lock-password", List.of("passwd -l {u} 2>/dev/null || true"),
            "rotate-key", List.of("echo \"rotate ssh keys for {u}\" >/dev/null"));

    private SshComplianceAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: SshComplianceAudit <dataDir> <auditDir>");
            System.exit(1);
        }
        run(Path.of(args[0]), Path.of(args[1]));
    }

    private static void run(Path dataDir, Path auditDir) throws IOException {
        Files.createDirectories(auditDir);

        JsonObject policy = loadJson(dataDir.resolve("policy.json"));
        List<Map<String, String>> accounts = loadCsv(dataDir.resolve("accounts.csv"));
        List<Map<String, String>> passwordRows = loadCsv(dataDir.resolve("password_state.csv"));
        List<Map<String, String>> loginRows = loadCsv(dataDir.resolve("login_history.csv"));
        List<Map<String, String>> sshRows = loadCsv(dataDir.resolve("ssh_keys.csv"));
        List<Map<String, String>> mfaRows = loadCsv(dataDir.resolve("mfa_state.csv"));
        List<Map<String, String>> keyAuditRows = loadCsv(dataDir.resolve("key_audit_log.csv"));
        List<Map<String, String>> waiverRows = loadCsv(dataDir.resolve("waivers.csv"));
        List<Map<String, String>> delegationRows = loadCsv(dataDir.resolve("delegations.csv"));
        JsonObject groupMembership = loadJson(dataDir.resolve("group_membership.json"));

        ComputeState state =
                computeFindings(
                        policy,
                        accounts,
                        passwordRows,
                        loginRows,
                        sshRows,
                        mfaRows,
                        keyAuditRows,
                        groupMembership,
                        waiverRows,
                        delegationRows,
                        null);

        writeOutputs(
                auditDir,
                policy,
                accounts,
                passwordRows,
                loginRows,
                sshRows,
                mfaRows,
                keyAuditRows,
                groupMembership,
                waiverRows,
                delegationRows,
                state);
    }

    private static void writeOutputs(
            Path auditDir,
            JsonObject policy,
            List<Map<String, String>> accounts,
            List<Map<String, String>> passwordRows,
            List<Map<String, String>> loginRows,
            List<Map<String, String>> sshRows,
            List<Map<String, String>> mfaRows,
            List<Map<String, String>> keyAuditRows,
            JsonObject groupMembership,
            List<Map<String, String>> waiverRows,
            List<Map<String, String>> delegationRows,
            ComputeState state)
            throws IOException {
        List<Finding> findings = state.findings;
        JsonObject severityWeights = policy.getAsJsonObject("severity_weights");
        JsonObject rules = state.rules;
        int currentDay = policy.get("current_day").getAsInt();
        JsonObject snapshotMin = policy.getAsJsonObject("snapshot_min_day");
        List<String> nonExemptUsers = state.nonExemptUsers;

        JsonArray findingsPublic = new JsonArray();
        for (Finding f : findings) {
            JsonObject row = new JsonObject();
            row.addProperty("username", f.username);
            row.addProperty("finding_code", f.findingCode);
            row.addProperty("severity", f.severity);
            row.addProperty("evidence", f.evidence);
            findingsPublic.add(row);
        }
        JsonObject findingsDoc = new JsonObject();
        findingsDoc.add("findings", findingsPublic);
        writeJson(auditDir.resolve("findings.json"), findingsDoc);

        JsonArray exposures = new JsonArray();
        for (Finding f : findings) {
            if (!"delegated_admin_exposure".equals(f.findingCode)) {
                continue;
            }
            ExposureInfo info = state.exposureInfo.get(f.username);
            JsonObject row = new JsonObject();
            row.addProperty("username", f.username);
            row.addProperty("source", info.source);
            JsonArray pathArr = new JsonArray();
            for (String p : info.path) {
                pathArr.add(p);
            }
            row.add("path", pathArr);
            row.addProperty("hops", info.hops);
            row.addProperty("weight", info.weight);
            exposures.add(row);
        }
        List<JsonObject> exposureList = new ArrayList<>();
        for (JsonElement el : exposures) {
            exposureList.add(el.getAsJsonObject());
        }
        exposureList.sort(Comparator.comparing(o -> o.get("username").getAsString()));
        JsonArray exposuresSorted = new JsonArray();
        for (JsonObject o : exposureList) {
            exposuresSorted.add(o);
        }
        JsonObject exposureDoc = new JsonObject();
        exposureDoc.add("exposures", exposuresSorted);
        writeJson(auditDir.resolve("exposure_paths.json"), exposureDoc);

        List<Map.Entry<String, List<String>>> blastEntries = new ArrayList<>();
        for (Map.Entry<String, List<String>> e : state.blastRadius.entrySet()) {
            blastEntries.add(e);
        }
        blastEntries.sort(
                (a, b) -> {
                    int cmp = Integer.compare(b.getValue().size(), a.getValue().size());
                    if (cmp != 0) {
                        return cmp;
                    }
                    return a.getKey().compareTo(b.getKey());
                });
        JsonArray blastArr = new JsonArray();
        for (Map.Entry<String, List<String>> e : blastEntries) {
            JsonObject row = new JsonObject();
            row.addProperty("username", e.getKey());
            row.addProperty("downstream_count", e.getValue().size());
            JsonArray downstream = new JsonArray();
            for (String u : e.getValue()) {
                downstream.add(u);
            }
            row.add("downstream", downstream);
            blastArr.add(row);
        }
        JsonObject blastDoc = new JsonObject();
        blastDoc.add("blast_radius", blastArr);
        writeJson(auditDir.resolve("blast_radius.json"), blastDoc);

        Map<String, List<Finding>> findingsByUser = new HashMap<>();
        Map<String, Integer> riskScore = new HashMap<>();
        Map<String, Integer> bySeverity = new HashMap<>();
        Map<String, Integer> byCode = new TreeMap<>();
        for (Finding f : findings) {
            findingsByUser.computeIfAbsent(f.username, k -> new ArrayList<>()).add(f);
            bySeverity.merge(f.severity, 1, Integer::sum);
            byCode.merge(f.findingCode, 1, Integer::sum);
            int sw = severityWeights.get(f.severity).getAsInt();
            int rw = rules.getAsJsonObject(f.ruleName).get("risk_weight").getAsInt();
            riskScore.merge(f.username, sw * rw, Integer::sum);
        }
        List<JsonObject> riskRows = new ArrayList<>();
        for (Map.Entry<String, Integer> e : riskScore.entrySet()) {
            if (e.getValue() > 0) {
                JsonObject row = new JsonObject();
                row.addProperty("username", e.getKey());
                row.addProperty("score", e.getValue());
                riskRows.add(row);
            }
        }
        riskRows.sort(
                (a, b) -> {
                    int cmp =
                            Integer.compare(
                                    b.get("score").getAsInt(), a.get("score").getAsInt());
                    if (cmp != 0) {
                        return cmp;
                    }
                    return a.get("username")
                            .getAsString()
                            .compareTo(b.get("username").getAsString());
                });
        int riskThresholdHigh = policy.get("risk_threshold_high").getAsInt();
        List<String> highRisk = new ArrayList<>();
        for (JsonObject row : riskRows) {
            if (row.get("score").getAsInt() >= riskThresholdHigh) {
                highRisk.add(row.get("username").getAsString());
            }
        }
        StringBuilder highRiskText = new StringBuilder();
        for (String u : highRisk) {
            highRiskText.append(u).append('\n');
        }
        Files.writeString(
                auditDir.resolve("high_risk_users.txt"),
                highRiskText.toString(),
                StandardCharsets.UTF_8);

        JsonObject bySeverityObj = new JsonObject();
        bySeverityObj.addProperty("critical", bySeverity.getOrDefault("critical", 0));
        bySeverityObj.addProperty("high", bySeverity.getOrDefault("high", 0));
        bySeverityObj.addProperty("medium", bySeverity.getOrDefault("medium", 0));
        bySeverityObj.addProperty("low", bySeverity.getOrDefault("low", 0));

        JsonObject byCodeObj = new JsonObject();
        for (Map.Entry<String, Integer> e : byCode.entrySet()) {
            byCodeObj.addProperty(e.getKey(), e.getValue());
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("total_users", nonExemptUsers.size());
        summary.addProperty("violating_users", riskRows.size());
        summary.addProperty("total_findings", findings.size());
        summary.addProperty("waived_findings", state.waived);
        summary.add("by_severity", bySeverityObj);
        summary.add("by_finding_code", byCodeObj);
        JsonArray riskScoresArr = new JsonArray();
        for (JsonObject row : riskRows) {
            riskScoresArr.add(row);
        }
        summary.add("risk_scores", riskScoresArr);
        writeJson(auditDir.resolve("summary.json"), summary);

        Map<String, Integer> futureSnapshotCounts = new LinkedHashMap<>();
        futureSnapshotCounts.put(
                "password_state", countFutureSnapshots(passwordRows, currentDay));
        futureSnapshotCounts.put(
                "login_history", countFutureSnapshots(loginRows, currentDay));
        futureSnapshotCounts.put("ssh_keys", countFutureSnapshots(sshRows, currentDay));
        futureSnapshotCounts.put("mfa_state", countFutureSnapshots(mfaRows, currentDay));

        JsonObject futureSnapshots = new JsonObject();
        for (Map.Entry<String, Integer> e : futureSnapshotCounts.entrySet()) {
            futureSnapshots.addProperty(e.getKey(), e.getValue());
        }

        JsonObject missingEffective = new JsonObject();
        missingEffective.add(
                "password_state",
                toJsonArray(sortedMissing(nonExemptUsers, state.pwEff)));
        missingEffective.add(
                "login_history",
                toJsonArray(sortedMissing(nonExemptUsers, state.loginEff)));
        missingEffective.add(
                "ssh_keys", toJsonArray(sortedMissing(nonExemptUsers, state.sshEff)));
        missingEffective.add(
                "mfa_state", toJsonArray(sortedMissing(nonExemptUsers, state.mfaEff)));

        JsonObject dataQuality = new JsonObject();
        dataQuality.add("future_snapshots", futureSnapshots);
        dataQuality.add("missing_effective_rows", missingEffective);
        dataQuality.addProperty("ignored_waiver_rows", state.ignoredWaiverRows);
        dataQuality.addProperty("invalid_delegation_rows", state.invalidDelegationRows);
        dataQuality.addProperty("active_delegation_edges", state.edges.size());
        dataQuality.addProperty("invalid_key_audit_rows", state.invalidKeyAuditRows);
        writeJson(auditDir.resolve("data_quality.json"), dataQuality);

        JsonArray compromisedArr = new JsonArray();
        for (Finding f : findings) {
            if (!"unrotated_compromised_key".equals(f.findingCode)) {
                continue;
            }
            KeyEvent ev = state.revokedInWindow.get(f.username).get(0);
            Map<String, String> ssh = state.sshEff.get(f.username);
            JsonObject row = new JsonObject();
            row.addProperty("username", f.username);
            row.addProperty("day", ev.day);
            row.addProperty("key_fingerprint", ev.keyFingerprint);
            Integer keyCount = toInt(ssh.get("key_count"));
            row.addProperty("key_count", keyCount == null ? 0 : keyCount);
            compromisedArr.add(row);
        }
        List<JsonObject> compromisedList = new ArrayList<>();
        for (JsonElement el : compromisedArr) {
            compromisedList.add(el.getAsJsonObject());
        }
        compromisedList.sort(Comparator.comparing(o -> o.get("username").getAsString()));
        JsonArray compromisedSorted = new JsonArray();
        for (JsonObject o : compromisedList) {
            compromisedSorted.add(o);
        }
        JsonObject compromisedDoc = new JsonObject();
        compromisedDoc.add("compromised", compromisedSorted);
        writeJson(auditDir.resolve("key_audit_findings.json"), compromisedDoc);

        JsonArray historyDays = policy.getAsJsonArray("history_days");
        List<Integer> days = new ArrayList<>();
        for (JsonElement el : historyDays) {
            days.add(el.getAsInt());
        }
        JsonArray checkpoints = new JsonArray();
        Set<String> prevSet = null;
        for (int d : days) {
            ComputeState sub =
                    computeFindings(
                            policy,
                            accounts,
                            passwordRows,
                            loginRows,
                            sshRows,
                            mfaRows,
                            keyAuditRows,
                            groupMembership,
                            waiverRows,
                            delegationRows,
                            d);
            Set<String> curSet = new HashSet<>();
            Map<String, Integer> sevCounts = new HashMap<>();
            for (Finding f : sub.findings) {
                curSet.add(f.username + "\0" + f.findingCode);
                sevCounts.merge(f.severity, 1, Integer::sum);
            }
            List<String[]> newPairs;
            List<String[]> resolvedPairs;
            if (prevSet == null) {
                newPairs = List.of();
                resolvedPairs = List.of();
            } else {
                newPairs = new ArrayList<>();
                for (String key : curSet) {
                    if (!prevSet.contains(key)) {
                        String[] parts = key.split("\0", 2);
                        newPairs.add(parts);
                    }
                }
                newPairs.sort(
                        Comparator.comparing((String[] p) -> p[1])
                                .thenComparing(p -> p[0]));
                resolvedPairs = new ArrayList<>();
                for (String key : prevSet) {
                    if (!curSet.contains(key)) {
                        String[] parts = key.split("\0", 2);
                        resolvedPairs.add(parts);
                    }
                }
                resolvedPairs.sort(
                        Comparator.comparing((String[] p) -> p[1])
                                .thenComparing(p -> p[0]));
            }
            JsonObject cp = new JsonObject();
            cp.addProperty("as_of_day", d);
            cp.addProperty("total_findings", sub.findings.size());
            JsonObject cpSev = new JsonObject();
            cpSev.addProperty("critical", sevCounts.getOrDefault("critical", 0));
            cpSev.addProperty("high", sevCounts.getOrDefault("high", 0));
            cpSev.addProperty("medium", sevCounts.getOrDefault("medium", 0));
            cpSev.addProperty("low", sevCounts.getOrDefault("low", 0));
            cp.add("by_severity", cpSev);
            cp.add("new_findings", pairsToJson(newPairs));
            cp.add("resolved_findings", pairsToJson(resolvedPairs));
            checkpoints.add(cp);
            prevSet = curSet;
        }
        JsonObject historyDoc = new JsonObject();
        historyDoc.add("checkpoints", checkpoints);
        writeJson(auditDir.resolve("audit_history.json"), historyDoc);

        List<Map<String, String>> actionRows = new ArrayList<>();
        Map<String, List<String>> actionsByType = new TreeMap<>();
        for (String user : nonExemptUsers) {
            List<Finding> userFindings = findingsByUser.getOrDefault(user, List.of());
            if (userFindings.isEmpty()) {
                Map<String, String> row = new LinkedHashMap<>();
                row.put("username", user);
                row.put("action", "none");
                row.put("reason", "compliant");
                row.put("priority", "");
                actionRows.add(row);
                continue;
            }
            int bestSev = Integer.MAX_VALUE;
            int bestActionPri = Integer.MAX_VALUE;
            String bestAction = null;
            String bestReason = null;
            for (Finding f : userFindings) {
                String[] mapping = FINDING_TO_ACTION.get(f.findingCode);
                String action = mapping[0];
                String reason = mapping[1];
                int sevRank = SEVERITY_RANK.get(f.severity);
                int actionPri = ACTION_PRIORITY.get(action);
                if (bestAction == null
                        || sevRank < bestSev
                        || (sevRank == bestSev && actionPri < bestActionPri)) {
                    bestSev = sevRank;
                    bestActionPri = actionPri;
                    bestAction = action;
                    bestReason = reason;
                }
            }
            Map<String, String> row = new LinkedHashMap<>();
            row.put("username", user);
            row.put("action", bestAction);
            row.put("reason", bestReason);
            row.put("priority", String.valueOf(bestSev));
            actionRows.add(row);
            actionsByType.computeIfAbsent(bestAction, k -> new ArrayList<>()).add(user);
        }
        actionRows.sort(Comparator.comparing(r -> r.get("username")));
        for (List<String> users : actionsByType.values()) {
            users.sort(String::compareTo);
        }
        writeAccountActions(auditDir.resolve("account_actions.csv"), actionRows);

        List<String> lines = new ArrayList<>();
        lines.add("#!/bin/bash");
        lines.add("set -euo pipefail");
        lines.add("");
        boolean firstSection = true;
        for (String action : ORDERED_ACTIONS) {
            List<String> users = actionsByType.get(action);
            if (users == null || users.isEmpty()) {
                continue;
            }
            if (!firstSection) {
                lines.add("");
            }
            firstSection = false;
            lines.add(SECTION_FOR_ACTION.get(action));
            for (String user : users) {
                for (String cmd : CMD_TEMPLATES.get(action)) {
                    lines.add(cmd.replace("{u}", user));
                }
            }
        }
        String remediation = String.join("\n", lines).stripTrailing() + "\n";
        Path remediationPath = auditDir.resolve("remediation.sh");
        Files.writeString(remediationPath, remediation, StandardCharsets.UTF_8);
        try {
            Set<PosixFilePermission> perms = new HashSet<>();
            perms.add(PosixFilePermission.OWNER_READ);
            perms.add(PosixFilePermission.OWNER_WRITE);
            perms.add(PosixFilePermission.OWNER_EXECUTE);
            perms.add(PosixFilePermission.GROUP_READ);
            perms.add(PosixFilePermission.GROUP_EXECUTE);
            perms.add(PosixFilePermission.OTHERS_READ);
            perms.add(PosixFilePermission.OTHERS_EXECUTE);
            Files.setPosixFilePermissions(remediationPath, perms);
        } catch (UnsupportedOperationException ignored) {
            // Windows local dev
        }
    }

    private static JsonArray pairsToJson(List<String[]> pairs) {
        JsonArray arr = new JsonArray();
        for (String[] p : pairs) {
            JsonObject row = new JsonObject();
            row.addProperty("username", p[0]);
            row.addProperty("finding_code", p[1]);
            arr.add(row);
        }
        return arr;
    }

    private static JsonArray toJsonArray(List<String> items) {
        JsonArray arr = new JsonArray();
        for (String s : items) {
            arr.add(s);
        }
        return arr;
    }

    private static List<String> sortedMissing(
            List<String> users, Map<String, Map<String, String>> eff) {
        List<String> missing = new ArrayList<>();
        for (String u : users) {
            if (eff.get(u) == null) {
                missing.add(u);
            }
        }
        missing.sort(String::compareTo);
        return missing;
    }

    private static int countFutureSnapshots(List<Map<String, String>> rows, int currentDay) {
        int count = 0;
        for (Map<String, String> row : rows) {
            Integer snap = toInt(row.get("snapshot_day"));
            int val = snap == null ? Integer.MIN_VALUE / 2 : snap;
            if (val > currentDay) {
                count++;
            }
        }
        return count;
    }

    private static ComputeState computeFindings(
            JsonObject policy,
            List<Map<String, String>> accounts,
            List<Map<String, String>> passwordRows,
            List<Map<String, String>> loginRows,
            List<Map<String, String>> sshRows,
            List<Map<String, String>> mfaRows,
            List<Map<String, String>> keyAuditRows,
            JsonObject groupMembership,
            List<Map<String, String>> waiverRows,
            List<Map<String, String>> delegationRows,
            Integer currentDayOverride) {
        JsonObject rules = policy.getAsJsonObject("rules");
        Set<String> exemptUsers = new HashSet<>();
        for (JsonElement el : policy.getAsJsonArray("exempt_users")) {
            exemptUsers.add(el.getAsString());
        }
        int currentDay =
                currentDayOverride != null
                        ? currentDayOverride
                        : policy.get("current_day").getAsInt();
        JsonObject snapshotMin = policy.getAsJsonObject("snapshot_min_day");
        int incidentStart = policy.get("incident_window_start_day").getAsInt();
        int delegationCap = policy.get("delegation_max_trust_cost").getAsInt();

        Set<String> knownUsers = new HashSet<>();
        for (Map<String, String> a : accounts) {
            String u = a.get("username");
            if (u != null && !u.isEmpty()) {
                knownUsers.add(u);
            }
        }

        Map<String, Map<String, String>> accByUser = new LinkedHashMap<>();
        List<String> nonExemptUsers = new ArrayList<>();
        for (Map<String, String> a : accounts) {
            String u = a.get("username");
            if (u == null || u.isEmpty() || exemptUsers.contains(u)) {
                continue;
            }
            accByUser.put(u, a);
            nonExemptUsers.add(u);
        }
        nonExemptUsers.sort(String::compareTo);

        Map<String, Map<String, String>> pwEff = new HashMap<>();
        Map<String, Map<String, String>> loginEff = new HashMap<>();
        Map<String, Map<String, String>> sshEff = new HashMap<>();
        Map<String, Map<String, String>> mfaEff = new HashMap<>();
        for (String u : nonExemptUsers) {
            pwEff.put(
                    u,
                    effectiveRow(
                            passwordRows,
                            u,
                            currentDay,
                            snapshotMin.get("password_state").getAsInt()));
            loginEff.put(
                    u,
                    effectiveRow(
                            loginRows,
                            u,
                            currentDay,
                            snapshotMin.get("login_history").getAsInt()));
            sshEff.put(
                    u,
                    effectiveRow(
                            sshRows, u, currentDay, snapshotMin.get("ssh_keys").getAsInt()));
            mfaEff.put(
                    u,
                    effectiveRow(
                            mfaRows, u, currentDay, snapshotMin.get("mfa_state").getAsInt()));
        }

        Set<String> sudoMembers = new HashSet<>();
        for (String username : groupMembership.keySet()) {
            JsonElement groupsEl = groupMembership.get(username);
            if (groupsEl != null && groupsEl.isJsonArray()) {
                for (JsonElement g : groupsEl.getAsJsonArray()) {
                    if ("sudo".equals(g.getAsString())) {
                        sudoMembers.add(username);
                        break;
                    }
                }
            }
        }

        JsonObject unauthorizedSudoRule = rules.getAsJsonObject("unauthorized_sudo");
        Set<String> allowlistedSudo = new HashSet<>();
        for (JsonElement el : unauthorizedSudoRule.getAsJsonArray("allowed_users")) {
            allowlistedSudo.add(el.getAsString());
        }
        List<String> seedUsers = new ArrayList<>();
        for (String u : sudoMembers) {
            if (allowlistedSudo.contains(u)) {
                seedUsers.add(u);
            }
        }
        seedUsers.sort(String::compareTo);

        GraphBuild graph = buildActiveGraph(delegationRows, knownUsers, currentDay);
        Map<String, PathResult> bestPaths = shortestPaths(graph.edges, seedUsers);
        Set<String> cycleSet = cycleMembers(graph.edges);
        Map<String, Integer> outDeg = outDegrees(graph.edges);

        Map<String, List<String>> blastRadius = new LinkedHashMap<>();
        for (String s : seedUsers) {
            Set<String> downstream = reachableFrom(graph.edges, s);
            if (!downstream.isEmpty()) {
                List<String> sorted = new ArrayList<>(downstream);
                sorted.sort(String::compareTo);
                blastRadius.put(s, sorted);
            }
        }

        KeyAuditParse keyParse = parseKeyAudit(keyAuditRows, knownUsers);
        Map<String, List<KeyEvent>> revokedInWindow = new HashMap<>();
        for (KeyEvent ev : keyParse.valid) {
            if (!"revoked".equals(ev.eventType)) {
                continue;
            }
            if (ev.day < incidentStart || ev.day > currentDay) {
                continue;
            }
            revokedInWindow.computeIfAbsent(ev.username, k -> new ArrayList<>()).add(ev);
        }
        for (List<KeyEvent> events : revokedInWindow.values()) {
            events.sort(
                    Comparator.comparingInt((KeyEvent e) -> e.day)
                            .thenComparing(e -> e.keyFingerprint));
        }

        WaiverParse waivers = parseWaivers(waiverRows, knownUsers, exemptUsers, currentDay);

        List<Finding> raw = new ArrayList<>();
        Map<String, ExposureInfo> exposureInfo = new HashMap<>();

        for (String user : nonExemptUsers) {
            Map<String, String> account = accByUser.get(user);
            String acctType = nz(account.get("account_type")).toLowerCase();
            if (!"human".equals(acctType)) {
                continue;
            }
            if (allowlistedSudo.contains(user) || sudoMembers.contains(user)) {
                continue;
            }
            Map<String, String> pw = pwEff.get(user);
            boolean pwOpen = pw == null || toInt(pw.get("is_locked")) == 0;
            if (!pwOpen) {
                continue;
            }
            PathResult bp = bestPaths.get(user);
            if (bp == null || bp.hops <= 0 || bp.weight > delegationCap) {
                continue;
            }
            exposureInfo.put(
                    user,
                    new ExposureInfo(bp.source, bp.path, bp.hops, bp.weight, bp.pathString));
        }

        for (String user : nonExemptUsers) {
            Map<String, String> account = accByUser.get(user);
            String acctType = nz(account.get("account_type")).toLowerCase();
            String shell = nz(account.get("shell"));
            String home = nz(account.get("home"));
            Set<String> groups = new HashSet<>();
            if (groupMembership.has(user) && groupMembership.get(user).isJsonArray()) {
                for (JsonElement g : groupMembership.getAsJsonArray(user)) {
                    groups.add(g.getAsString());
                }
            }

            Map<String, String> pw = pwEff.get(user);
            Map<String, String> login = loginEff.get(user);
            Map<String, String> ssh = sshEff.get(user);
            Map<String, String> mfa = mfaEff.get(user);

            boolean pwOpen = false;
            if (pw == null) {
                pwOpen = true;
                addFinding(
                        raw,
                        user,
                        "missing_password_state",
                        "password_state snapshot is missing",
                        rules);
            } else {
                Integer isLocked = toInt(pw.get("is_locked"));
                pwOpen = isLocked != null && isLocked == 0;
                if (pwOpen) {
                    Integer age = toInt(pw.get("password_age_days"));
                    int maxDays = rules.getAsJsonObject("stale_password").get("max_days").getAsInt();
                    if (age != null && age > maxDays) {
                        addFinding(
                                raw,
                                user,
                                "stale_password",
                                "password_age_days="
                                        + age
                                        + " exceeds max_days="
                                        + maxDays,
                                rules);
                    }
                }
            }

            if ("human".equals(acctType)) {
                if (login == null) {
                    addFinding(
                            raw,
                            user,
                            "missing_login_history",
                            "login_history snapshot is missing",
                            rules);
                } else if (pwOpen) {
                    Integer lastLogin = toInt(login.get("last_login_days"));
                    int maxDays =
                            rules.getAsJsonObject("inactive_human").get("max_days").getAsInt();
                    if (lastLogin != null && lastLogin > maxDays) {
                        addFinding(
                                raw,
                                user,
                                "inactive_human",
                                "last_login_days="
                                        + lastLogin
                                        + " exceeds max_days="
                                        + maxDays,
                                rules);
                    }
                }
            }

            if ("service".equals(acctType)) {
                Set<String> allowedShells = new HashSet<>();
                for (JsonElement el :
                        rules.getAsJsonObject("interactive_service_account")
                                .getAsJsonArray("allowed_shells")) {
                    allowedShells.add(el.getAsString());
                }
                if (!allowedShells.contains(shell)) {
                    addFinding(
                            raw,
                            user,
                            "interactive_service_account",
                            "service shell '" + shell + "' is not in allowed_shells",
                            rules);
                }
            }

            if (home.isEmpty()) {
                addFinding(raw, user, "missing_home", "home field is empty", rules);
            }

            if (groups.contains("sudo") && !allowlistedSudo.contains(user)) {
                addFinding(
                        raw,
                        user,
                        "unauthorized_sudo",
                        "user is in sudo group but not allowlisted",
                        rules);
            }

            if (ssh == null) {
                addFinding(
                        raw,
                        user,
                        "missing_ssh_inventory",
                        "ssh_keys snapshot is missing",
                        rules);
            } else {
                Integer keyCount = toInt(ssh.get("key_count"));
                Integer keyAge = toInt(ssh.get("key_age_days"));
                int maxAge = rules.getAsJsonObject("stale_ssh_key").get("max_age_days").getAsInt();
                if (keyCount != null
                        && keyCount > 0
                        && keyAge != null
                        && keyAge > maxAge) {
                    addFinding(
                            raw,
                            user,
                            "stale_ssh_key",
                            "key_age_days=" + keyAge + " exceeds max_age_days=" + maxAge,
                            rules);
                }
                if ("human".equals(acctType) && keyCount != null && keyCount == 0 && pwOpen) {
                    addFinding(
                            raw,
                            user,
                            "empty_ssh_key",
                            "human account has zero SSH keys",
                            rules);
                }
                if ("human".equals(acctType)
                        && keyCount != null
                        && keyCount > 0
                        && revokedInWindow.containsKey(user)) {
                    KeyEvent ev = revokedInWindow.get(user).get(0);
                    addFinding(
                            raw,
                            user,
                            "unrotated_compromised_key",
                            "revoked key event on day="
                                    + ev.day
                                    + " but key_count="
                                    + keyCount
                                    + " > 0",
                            rules);
                }
            }

            if (mfa == null) {
                addFinding(
                        raw,
                        user,
                        "missing_mfa_state",
                        "mfa_state snapshot is missing",
                        rules);
            } else if ("human".equals(acctType)) {
                Integer mfaEnabled = toInt(mfa.get("mfa_enabled"));
                if (mfaEnabled != null && mfaEnabled == 0 && pwOpen) {
                    addFinding(
                            raw,
                            user,
                            "mfa_disabled",
                            "mfa_enabled=0 and password is missing or unlocked",
                            rules);
                }
            }

            if (exposureInfo.containsKey(user)) {
                ExposureInfo info = exposureInfo.get(user);
                addFinding(
                        raw,
                        user,
                        "delegated_admin_exposure",
                        "active delegation path from "
                                + info.source
                                + " to "
                                + user
                                + ": "
                                + info.pathString
                                + " (weight="
                                + info.weight
                                + ")",
                        rules);
            }

            if (cycleSet.contains(user)) {
                addFinding(
                        raw,
                        user,
                        "delegation_cycle",
                        "user participates in delegation cycle",
                        rules);
            }

            if (bestPaths.containsKey(user)) {
                int minOut =
                        rules.getAsJsonObject("escalation_chain_risk")
                                .get("min_out_degree")
                                .getAsInt();
                if (outDeg.getOrDefault(user, 0) >= minOut) {
                    addFinding(
                            raw,
                            user,
                            "escalation_chain_risk",
                            "out_degree="
                                    + outDeg.getOrDefault(user, 0)
                                    + " reachable from seed; min_out_degree="
                                    + minOut,
                            rules);
                }
            }
        }

        for (String s : seedUsers) {
            Map<String, String> sLogin =
                    effectiveRow(
                            loginRows,
                            s,
                            currentDay,
                            snapshotMin.get("login_history").getAsInt());
            if (sLogin == null) {
                continue;
            }
            Integer lastLogin = toInt(sLogin.get("last_login_days"));
            int maxDays = rules.getAsJsonObject("dormant_admin").get("max_days").getAsInt();
            if (lastLogin == null || lastLogin <= maxDays) {
                continue;
            }
            addFinding(
                    raw,
                    s,
                    "dormant_admin",
                    "seed last_login_days=" + lastLogin + " exceeds max_days=" + maxDays,
                    rules);
        }

        int waivedCount = 0;
        List<Finding> findings = new ArrayList<>();
        for (Finding f : raw) {
            if (isWaived(f.username, f.findingCode, f.severity, waivers.active)) {
                waivedCount++;
            } else {
                findings.add(f);
            }
        }
        findings.sort(
                Comparator.comparingInt((Finding f) -> SEVERITY_RANK.get(f.severity))
                        .thenComparing(f -> f.findingCode)
                        .thenComparing(f -> f.username));

        ComputeState state = new ComputeState();
        state.findings = findings;
        state.waived = waivedCount;
        state.exposureInfo = exposureInfo;
        state.blastRadius = blastRadius;
        state.invalidDelegationRows = graph.invalid;
        state.invalidKeyAuditRows = keyParse.invalid;
        state.ignoredWaiverRows = waivers.ignored;
        state.pwEff = pwEff;
        state.loginEff = loginEff;
        state.sshEff = sshEff;
        state.mfaEff = mfaEff;
        state.edges = graph.edges;
        state.seedUsers = seedUsers;
        state.nonExemptUsers = nonExemptUsers;
        state.revokedInWindow = revokedInWindow;
        state.rules = rules;
        state.allowlistedSudo = allowlistedSudo;
        return state;
    }

    private static void addFinding(
            List<Finding> raw,
            String username,
            String ruleName,
            String evidence,
            JsonObject rules) {
        JsonObject rule = rules.getAsJsonObject(ruleName);
        Finding f = new Finding();
        f.username = username;
        f.findingCode = rule.get("finding_code").getAsString();
        f.severity = rule.get("severity").getAsString();
        f.evidence = evidence;
        f.ruleName = ruleName;
        raw.add(f);
    }

    private static boolean isWaived(
            String username,
            String findingCode,
            String severity,
            Map<String, List<WaiverEntry>> activeWaivers) {
        int rank = SEVERITY_RANK.get(severity);
        List<WaiverEntry> entries = activeWaivers.getOrDefault(username, List.of());
        for (WaiverEntry w : entries) {
            if (rank < w.minRank) {
                continue;
            }
            if (w.code.equals(findingCode)) {
                return true;
            }
            if ("*".equals(w.code) && !"critical".equals(severity)) {
                return true;
            }
        }
        return false;
    }

    private static WaiverParse parseWaivers(
            List<Map<String, String>> waiverRows,
            Set<String> knownUsers,
            Set<String> exemptUsers,
            int currentDay) {
        Map<String, List<WaiverEntry>> active = new HashMap<>();
        int ignored = 0;
        for (Map<String, String> row : waiverRows) {
            String username = nz(row.get("username"));
            String code = nz(row.get("finding_code"));
            Integer expires = toInt(row.get("expires_day"));
            String minSev = nz(row.get("min_severity"));
            if (username.isEmpty() || code.isEmpty()) {
                ignored++;
                continue;
            }
            if (!knownUsers.contains(username) || exemptUsers.contains(username)) {
                ignored++;
                continue;
            }
            if (expires == null || expires < currentDay) {
                ignored++;
                continue;
            }
            int minRank = SEVERITY_RANK.containsKey(minSev) ? SEVERITY_RANK.get(minSev) : 0;
            active.computeIfAbsent(username, k -> new ArrayList<>())
                    .add(new WaiverEntry(code, minRank));
        }
        WaiverParse result = new WaiverParse();
        result.active = active;
        result.ignored = ignored;
        return result;
    }

    private static KeyAuditParse parseKeyAudit(
            List<Map<String, String>> rows, Set<String> knownUsers) {
        int invalid = 0;
        List<KeyEvent> valid = new ArrayList<>();
        for (Map<String, String> row : rows) {
            String username = nz(row.get("username"));
            String eventType = nz(row.get("event_type"));
            Integer day = toInt(row.get("day"));
            String fingerprint = nz(row.get("key_fingerprint"));
            if (username.isEmpty() || !knownUsers.contains(username)) {
                invalid++;
                continue;
            }
            if (eventType.isEmpty()) {
                invalid++;
                continue;
            }
            if (day == null) {
                invalid++;
                continue;
            }
            KeyEvent ev = new KeyEvent();
            ev.username = username;
            ev.eventType = eventType;
            ev.day = day;
            ev.keyFingerprint = fingerprint;
            valid.add(ev);
        }
        KeyAuditParse result = new KeyAuditParse();
        result.valid = valid;
        result.invalid = invalid;
        return result;
    }

    private static Map<String, Integer> outDegrees(Map<String, Integer> edges) {
        Map<String, Integer> deg = new HashMap<>();
        for (String key : edges.keySet()) {
            String a = key.split("\0", 2)[0];
            deg.merge(a, 1, Integer::sum);
        }
        return deg;
    }

    private static Set<String> cycleMembers(Map<String, Integer> edges) {
        Map<String, List<String>> adjacency = new HashMap<>();
        Set<String> nodes = new HashSet<>();
        for (String key : edges.keySet()) {
            String[] parts = key.split("\0", 2);
            String a = parts[0];
            String b = parts[1];
            adjacency.computeIfAbsent(a, k -> new ArrayList<>()).add(b);
            nodes.add(a);
            nodes.add(b);
        }
        for (List<String> list : adjacency.values()) {
            list.sort(String::compareTo);
        }

        Map<String, Integer> indices = new HashMap<>();
        Map<String, Integer> lowlink = new HashMap<>();
        Set<String> onStack = new HashSet<>();
        List<String> stack = new ArrayList<>();
        Set<String> members = new HashSet<>();
        int[] indexRef = {0};

        List<String> sortedNodes = new ArrayList<>(nodes);
        sortedNodes.sort(String::compareTo);
        for (String start : sortedNodes) {
            if (indices.containsKey(start)) {
                continue;
            }
            strongConnect(
                    start, adjacency, edges, indexRef, indices, lowlink, onStack, stack, members);
        }
        return members;
    }

    private static void strongConnect(
            String start,
            Map<String, List<String>> adjacency,
            Map<String, Integer> edges,
            int[] indexRef,
            Map<String, Integer> indices,
            Map<String, Integer> lowlink,
            Set<String> onStack,
            List<String> stack,
            Set<String> members) {
        List<Object[]> work = new ArrayList<>();
        work.add(new Object[] {start, adjacency.getOrDefault(start, List.of()).iterator(), 0});
        indices.put(start, indexRef[0]);
        lowlink.put(start, indexRef[0]);
        indexRef[0]++;
        stack.add(start);
        onStack.add(start);

        while (!work.isEmpty()) {
            Object[] frame = work.get(work.size() - 1);
            String v = (String) frame[0];
            @SuppressWarnings("unchecked")
            java.util.Iterator<String> it = (java.util.Iterator<String>) frame[1];
            if (it.hasNext()) {
                String w = it.next();
                if (!indices.containsKey(w)) {
                    indices.put(w, indexRef[0]);
                    lowlink.put(w, indexRef[0]);
                    indexRef[0]++;
                    stack.add(w);
                    onStack.add(w);
                    work.add(
                            new Object[] {
                                w, adjacency.getOrDefault(w, List.of()).iterator(), 0
                            });
                } else if (onStack.contains(w)) {
                    lowlink.put(v, Math.min(lowlink.get(v), indices.get(w)));
                }
            } else {
                if (lowlink.get(v).equals(indices.get(v))) {
                    List<String> component = new ArrayList<>();
                    while (true) {
                        String w = stack.remove(stack.size() - 1);
                        onStack.remove(w);
                        component.add(w);
                        if (w.equals(v)) {
                            break;
                        }
                    }
                    if (component.size() > 1) {
                        members.addAll(component);
                    } else if (!component.isEmpty()
                            && edges.containsKey(component.get(0) + "\0" + component.get(0))) {
                        members.add(component.get(0));
                    }
                }
                work.remove(work.size() - 1);
                if (!work.isEmpty()) {
                    String parentV = (String) work.get(work.size() - 1)[0];
                    lowlink.put(parentV, Math.min(lowlink.get(parentV), lowlink.get(v)));
                }
            }
        }
    }

    private static Set<String> reachableFrom(Map<String, Integer> edges, String source) {
        Map<String, List<String>> adjacency = new HashMap<>();
        for (String key : edges.keySet()) {
            String[] parts = key.split("\0", 2);
            adjacency.computeIfAbsent(parts[0], k -> new ArrayList<>()).add(parts[1]);
        }
        Set<String> seen = new HashSet<>();
        seen.add(source);
        List<String> stack = new ArrayList<>();
        stack.add(source);
        while (!stack.isEmpty()) {
            String node = stack.remove(stack.size() - 1);
            for (String nxt : adjacency.getOrDefault(node, List.of())) {
                if (!seen.contains(nxt)) {
                    seen.add(nxt);
                    stack.add(nxt);
                }
            }
        }
        seen.remove(source);
        return seen;
    }

    private static Map<String, PathResult> shortestPaths(
            Map<String, Integer> edges, List<String> seeds) {
        Map<String, List<Edge>> adjacency = new HashMap<>();
        Set<String> nodes = new HashSet<>();
        for (Map.Entry<String, Integer> e : edges.entrySet()) {
            String[] parts = e.getKey().split("\0", 2);
            String a = parts[0];
            String b = parts[1];
            int w = e.getValue();
            adjacency.computeIfAbsent(a, k -> new ArrayList<>()).add(new Edge(b, w));
            nodes.add(a);
            nodes.add(b);
        }
        for (List<Edge> list : adjacency.values()) {
            list.sort(Comparator.comparing(e -> e.to));
        }
        for (String s : seeds) {
            nodes.add(s);
        }

        Map<String, PathResult> best = new HashMap<>();
        PriorityQueue<HeapEntry> heap = new PriorityQueue<>();
        for (String s : seeds) {
            List<String> path = List.of(s);
            PathResult pr = new PathResult(0, 0, path, s, String.join("->", path));
            best.put(s, pr);
            heap.offer(new HeapEntry(0, 0, pr.pathString, path, s));
        }

        while (!heap.isEmpty()) {
            HeapEntry entry = heap.poll();
            int weight = entry.weight;
            int hops = entry.hops;
            List<String> path = entry.path;
            String source = entry.source;
            String node = path.get(path.size() - 1);
            PathResult cur = best.get(node);
            if (cur != null && comparePathKeys(weight, hops, path, cur.weight, cur.hops, cur.path) > 0) {
                continue;
            }
            for (Edge edge : adjacency.getOrDefault(node, List.of())) {
                int candWeight = weight + edge.weight;
                int candHops = hops + 1;
                List<String> candPath = new ArrayList<>(path);
                candPath.add(edge.to);
                PathResult curNxt = best.get(edge.to);
                if (curNxt == null
                        || comparePathKeys(
                                        candWeight, candHops, candPath,
                                        curNxt.weight, curNxt.hops, curNxt.path)
                                < 0) {
                    String pathString = String.join("->", candPath);
                    best.put(
                            edge.to,
                            new PathResult(candWeight, candHops, candPath, source, pathString));
                    heap.offer(
                            new HeapEntry(
                                    candWeight, candHops, pathString, candPath, source));
                }
            }
        }
        return best;
    }

    private static int comparePathKeys(
            int w1, int h1, List<String> p1, int w2, int h2, List<String> p2) {
        int cmp = Integer.compare(w1, w2);
        if (cmp != 0) {
            return cmp;
        }
        cmp = Integer.compare(h1, h2);
        if (cmp != 0) {
            return cmp;
        }
        return String.join("->", p1).compareTo(String.join("->", p2));
    }

    private static GraphBuild buildActiveGraph(
            List<Map<String, String>> delegationRows, Set<String> knownUsers, int currentDay) {
        int invalid = 0;
        Map<String, Integer> edges = new HashMap<>();
        for (Map<String, String> row : delegationRows) {
            String grantor = nz(row.get("grantor"));
            String grantee = nz(row.get("grantee"));
            Integer startDay = toInt(row.get("start_day"));
            Integer endDay = toInt(row.get("end_day"));
            String weightRaw = row.get("weight");
            int weight;
            if (weightRaw == null || weightRaw.trim().isEmpty()) {
                weight = 1;
            } else {
                Integer w = toInt(weightRaw);
                weight = w == null ? 1 : w;
            }
            if (grantor.isEmpty() || grantee.isEmpty()) {
                invalid++;
                continue;
            }
            if (!knownUsers.contains(grantor) || !knownUsers.contains(grantee)) {
                invalid++;
                continue;
            }
            if (startDay == null || endDay == null) {
                invalid++;
                continue;
            }
            if (startDay > endDay) {
                invalid++;
                continue;
            }
            if (startDay > currentDay || currentDay > endDay) {
                continue;
            }
            String key = grantor + "\0" + grantee;
            if (!edges.containsKey(key) || weight < edges.get(key)) {
                edges.put(key, weight);
            }
        }
        GraphBuild g = new GraphBuild();
        g.edges = edges;
        g.invalid = invalid;
        return g;
    }

    private static Map<String, String> effectiveRow(
            List<Map<String, String>> rows,
            String username,
            int currentDay,
            int minDay) {
        Integer bestSnap = null;
        Map<String, String> best = null;
        for (Map<String, String> row : rows) {
            if (!username.equals(row.get("username"))) {
                continue;
            }
            Integer snap = toInt(row.get("snapshot_day"));
            if (snap == null || snap < minDay || snap > currentDay) {
                continue;
            }
            if (bestSnap == null || snap > bestSnap) {
                bestSnap = snap;
                best = row;
            }
        }
        return best;
    }

    private static Integer toInt(String value) {
        if (value == null) {
            return null;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String nz(String value) {
        return value == null ? "" : value.trim();
    }

    private static JsonObject loadJson(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static List<Map<String, String>> loadCsv(Path path) throws IOException {
        List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
        if (lines.isEmpty()) {
            return new ArrayList<>();
        }
        String[] headers = lines.get(0).split(",", -1);
        List<Map<String, String>> rows = new ArrayList<>();
        for (int i = 1; i < lines.size(); i++) {
            if (lines.get(i).isBlank()) {
                continue;
            }
            String[] vals = lines.get(i).split(",", -1);
            Map<String, String> row = new LinkedHashMap<>();
            for (int j = 0; j < headers.length; j++) {
                row.put(headers[j], j < vals.length ? vals[j] : "");
            }
            rows.add(row);
        }
        return rows;
    }

    private static void writeJson(Path path, JsonObject obj) throws IOException {
        Files.writeString(path, GSON.toJson(obj) + "\n", StandardCharsets.UTF_8);
    }

    private static void writeAccountActions(Path path, List<Map<String, String>> rows)
            throws IOException {
        List<String> headers = Arrays.asList("username", "action", "reason", "priority");
        StringBuilder sb = new StringBuilder();
        sb.append(String.join(",", headers)).append('\n');
        for (Map<String, String> row : rows) {
            List<String> vals = new ArrayList<>();
            for (String h : headers) {
                vals.add(row.getOrDefault(h, ""));
            }
            sb.append(String.join(",", vals)).append('\n');
        }
        Files.writeString(path, sb.toString(), StandardCharsets.UTF_8);
    }

    private static final class Finding {
        String username;
        String findingCode;
        String severity;
        String evidence;
        String ruleName;
    }

    private static final class ExposureInfo {
        final String source;
        final List<String> path;
        final int hops;
        final int weight;
        final String pathString;

        ExposureInfo(String source, List<String> path, int hops, int weight, String pathString) {
            this.source = source;
            this.path = path;
            this.hops = hops;
            this.weight = weight;
            this.pathString = pathString;
        }
    }

    private static final class PathResult {
        final int weight;
        final int hops;
        final List<String> path;
        final String source;
        final String pathString;

        PathResult(int weight, int hops, List<String> path, String source, String pathString) {
            this.weight = weight;
            this.hops = hops;
            this.path = path;
            this.source = source;
            this.pathString = pathString;
        }
    }

    private static final class HeapEntry implements Comparable<HeapEntry> {
        final int weight;
        final int hops;
        final String pathString;
        final List<String> path;
        final String source;

        HeapEntry(int weight, int hops, String pathString, List<String> path, String source) {
            this.weight = weight;
            this.hops = hops;
            this.pathString = pathString;
            this.path = path;
            this.source = source;
        }

        @Override
        public int compareTo(HeapEntry o) {
            int cmp = Integer.compare(weight, o.weight);
            if (cmp != 0) {
                return cmp;
            }
            cmp = Integer.compare(hops, o.hops);
            if (cmp != 0) {
                return cmp;
            }
            return pathString.compareTo(o.pathString);
        }
    }

    private static final class Edge {
        final String to;
        final int weight;

        Edge(String to, int weight) {
            this.to = to;
            this.weight = weight;
        }
    }

    private static final class GraphBuild {
        Map<String, Integer> edges = new HashMap<>();
        int invalid;
    }

    private static final class KeyEvent {
        String username;
        String eventType;
        int day;
        String keyFingerprint;
    }

    private static final class KeyAuditParse {
        List<KeyEvent> valid = new ArrayList<>();
        int invalid;
    }

    private static final class WaiverEntry {
        final String code;
        final int minRank;

        WaiverEntry(String code, int minRank) {
            this.code = code;
            this.minRank = minRank;
        }
    }

    private static final class WaiverParse {
        Map<String, List<WaiverEntry>> active = new HashMap<>();
        int ignored;
    }

    private static final class ComputeState {
        List<Finding> findings = new ArrayList<>();
        int waived;
        Map<String, ExposureInfo> exposureInfo = new HashMap<>();
        Map<String, List<String>> blastRadius = new HashMap<>();
        int invalidDelegationRows;
        int invalidKeyAuditRows;
        int ignoredWaiverRows;
        Map<String, Map<String, String>> pwEff = new HashMap<>();
        Map<String, Map<String, String>> loginEff = new HashMap<>();
        Map<String, Map<String, String>> sshEff = new HashMap<>();
        Map<String, Map<String, String>> mfaEff = new HashMap<>();
        Map<String, Integer> edges = new HashMap<>();
        List<String> seedUsers = new ArrayList<>();
        List<String> nonExemptUsers = new ArrayList<>();
        Map<String, List<KeyEvent>> revokedInWindow = new HashMap<>();
        JsonObject rules;
        Set<String> allowlistedSudo = new HashSet<>();
    }
}
