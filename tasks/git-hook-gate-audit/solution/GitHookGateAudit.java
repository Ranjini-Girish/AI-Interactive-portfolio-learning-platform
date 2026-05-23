import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.DirectoryStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Pattern;

/** Git hook gate audit oracle. */
public final class GitHookGateAudit {

    private static final Set<String> ALLOWED_HOOK_KINDS =
            new TreeSet<>(Arrays.asList("pre-commit", "commit-msg", "pre-push"));
    private static final Set<String> ALLOWED_INCIDENT_KINDS =
            new TreeSet<>(
                    Arrays.asList("emergency_waiver", "compromise", "audit_override"));

    private GitHookGateAudit() {}

    public static void main(String[] args) throws IOException {
        if (args.length != 2) {
            System.err.println("usage: GitHookGateAudit <dataDir> <auditDir>");
            System.exit(1);
        }
        run(Path.of(args[0]), Path.of(args[1]));
    }

    private static void run(Path dataDir, Path auditDir) throws IOException {
        Files.createDirectories(auditDir);

        JsonObject pool = loadJson(dataDir.resolve("pool_state.json"));
        int currentDay = pool.get("current_day").getAsInt();
        String policyVersion = pool.get("policy_version").getAsString();

        JsonObject baseline = loadJson(dataDir.resolve("baseline.json"));
        JsonArray globalRules = baseline.getAsJsonArray("hook_policy");
        JsonObject branchProtection = baseline.getAsJsonObject("branch_protection");
        JsonObject cmCfg = baseline.getAsJsonObject("commit_msg");

        Path reposDir = dataDir.resolve("repos");
        List<String> repoNames = new ArrayList<>();
        try (DirectoryStream<Path> stream = Files.newDirectoryStream(reposDir)) {
            for (Path p : stream) {
                if (Files.isDirectory(p)) {
                    repoNames.add(p.getFileName().toString());
                }
            }
        }
        repoNames.sort(String::compareTo);

        Map<String, RepoData> repoData = new TreeMap<>();
        for (String r : repoNames) {
            Path repoPath = reposDir.resolve(r);
            JsonObject prof = loadJson(repoPath.resolve("profile.json"));
            JsonObject hooks = loadJson(repoPath.resolve("hooks_installed.json"));
            JsonObject commitsDoc = loadJson(repoPath.resolve("recent_commits.json"));
            JsonArray commits =
                    commitsDoc.has("commits") && !commitsDoc.get("commits").isJsonNull()
                            ? commitsDoc.getAsJsonArray("commits")
                            : new JsonArray();
            repoData.put(r, new RepoData(prof, hooks, commits));
        }

        JsonObject incidentsDoc = loadJson(dataDir.resolve("incident_log.json"));
        JsonArray events =
                incidentsDoc.has("events") && !incidentsDoc.get("events").isJsonNull()
                        ? incidentsDoc.getAsJsonArray("events")
                        : new JsonArray();

        Set<String> known = new HashSet<>(repoNames);
        List<JsonObject> acceptedEvents = new ArrayList<>();
        int ignored = 0;

        for (JsonElement evEl : events) {
            if (!evEl.isJsonObject()) {
                ignored++;
                continue;
            }
            JsonObject ev = evEl.getAsJsonObject();
            String kind = jsonStringOrNull(ev, "kind");
            if (kind == null || !ALLOWED_INCIDENT_KINDS.contains(kind)) {
                ignored++;
                continue;
            }
            Integer day = jsonIntStrict(ev, "day");
            if (day == null) {
                ignored++;
                continue;
            }
            if (day > currentDay) {
                ignored++;
                continue;
            }
            String repo = jsonStringOrNull(ev, "repo");
            if (repo == null || !known.contains(repo)) {
                ignored++;
                continue;
            }
            if ("emergency_waiver".equals(kind)) {
                String hk = jsonStringOrNull(ev, "hook_kind");
                Integer dur = jsonIntStrict(ev, "duration_days");
                if (hk == null || !ALLOWED_HOOK_KINDS.contains(hk)) {
                    ignored++;
                    continue;
                }
                if (dur == null || dur <= 0) {
                    ignored++;
                    continue;
                }
            }
            if ("audit_override".equals(kind)) {
                String tgt = jsonStringOrNull(ev, "target_compliance");
                if (tgt == null
                        || (!"compliant".equals(tgt) && !"non_compliant".equals(tgt))) {
                    ignored++;
                    continue;
                }
            }
            acceptedEvents.add(ev);
        }

        Map<String, List<JsonObject>> waiversByRepo = new TreeMap<>();
        Map<String, List<Integer>> compromiseDaysByRepo = new TreeMap<>();
        Map<String, List<OverrideEntry>> overridesByRepo = new TreeMap<>();
        for (String r : repoNames) {
            waiversByRepo.put(r, new ArrayList<>());
            compromiseDaysByRepo.put(r, new ArrayList<>());
            overridesByRepo.put(r, new ArrayList<>());
        }

        for (int idx = 0; idx < acceptedEvents.size(); idx++) {
            JsonObject ev = acceptedEvents.get(idx);
            String repo = ev.get("repo").getAsString();
            String kind = ev.get("kind").getAsString();
            if ("emergency_waiver".equals(kind)) {
                waiversByRepo.get(repo).add(ev);
            } else if ("compromise".equals(kind)) {
                compromiseDaysByRepo.get(repo).add(ev.get("day").getAsInt());
            } else if ("audit_override".equals(kind)) {
                overridesByRepo.get(repo).add(new OverrideEntry(idx, ev));
            }
        }

        JsonArray protectedBranches = branchProtection.getAsJsonArray("protected_branches");
        Set<String> protectedBranchSet = new HashSet<>();
        for (JsonElement b : protectedBranches) {
            protectedBranchSet.add(b.getAsString());
        }

        JsonObject reqHooksPerBranch =
                branchProtection.getAsJsonObject("required_hooks_per_branch");

        JsonObject typeWlPerTier = cmCfg.getAsJsonObject("type_whitelist_per_tier");
        JsonObject maxLenPerTier = cmCfg.getAsJsonObject("max_length_per_tier");
        JsonObject requireIssuePerTier = cmCfg.getAsJsonObject("require_issue_ref_per_tier");
        Pattern issueRefPat = Pattern.compile(cmCfg.get("issue_ref_pattern").getAsString());

        List<JsonObject> repoComplianceEntries = new ArrayList<>();
        List<JsonObject> installActions = new ArrayList<>();
        List<JsonObject> branchEntries = new ArrayList<>();
        List<JsonObject> commitReviewEntries = new ArrayList<>();
        int summaryActiveWaivers = 0;

        Map<String, Integer> byCompliance = new TreeMap<>();
        byCompliance.put("compliant", 0);
        byCompliance.put("non_compliant", 0);
        byCompliance.put("quarantine", 0);

        Map<String, Integer> byCommitStatus = new TreeMap<>();
        byCommitStatus.put("valid", 0);
        byCommitStatus.put("type_not_allowed", 0);
        byCommitStatus.put("length_exceeded", 0);
        byCommitStatus.put("missing_issue_ref", 0);
        byCommitStatus.put("protected_branch_violation", 0);
        byCommitStatus.put("needs_review", 0);

        Set<String> compromised = new TreeSet<>();

        for (String repo : repoNames) {
            RepoData rd = repoData.get(repo);
            JsonObject prof = rd.profile;
            String tier = prof.get("tier").getAsString();
            JsonArray installed =
                    rd.hooks.has("installed") && !rd.hooks.get("installed").isJsonNull()
                            ? rd.hooks.getAsJsonArray("installed")
                            : new JsonArray();

            Map<String, JsonObject> installedByKind = new HashMap<>();
            for (JsonElement hEl : installed) {
                JsonObject h = hEl.getAsJsonObject();
                installedByKind.put(h.get("kind").getAsString(), h);
            }

            List<JsonObject> eff = effectivePolicy(globalRules, prof);
            List<JsonObject> requiredForRepo = new ArrayList<>();
            for (JsonObject r : eff) {
                JsonArray tiers = r.getAsJsonArray("required_for_tiers");
                for (JsonElement t : tiers) {
                    if (tier.equals(t.getAsString())) {
                        requiredForRepo.add(r);
                        break;
                    }
                }
            }
            TreeSet<String> requiredKinds = new TreeSet<>();
            for (JsonObject r : requiredForRepo) {
                requiredKinds.add(r.get("kind").getAsString());
            }

            List<JsonObject> activeWaiversForRepo = new ArrayList<>();
            for (JsonObject w : waiversByRepo.get(repo)) {
                if (isActiveWaiver(w, currentDay)) {
                    activeWaiversForRepo.add(w);
                }
            }
            Set<String> activeWaiverKinds = new HashSet<>();
            for (JsonObject w : activeWaiversForRepo) {
                activeWaiverKinds.add(w.get("hook_kind").getAsString());
            }

            List<JsonObject> activeWaiversList = new ArrayList<>();
            for (JsonObject w : activeWaiversForRepo) {
                JsonObject entry = new JsonObject();
                entry.addProperty("hook", w.get("hook_kind").getAsString());
                entry.addProperty("expires_day", expiresDay(w));
                activeWaiversList.add(entry);
            }
            activeWaiversList.sort(
                    Comparator.comparing((JsonObject x) -> x.get("hook").getAsString())
                            .thenComparingInt(x -> x.get("expires_day").getAsInt()));
            summaryActiveWaivers += activeWaiversList.size();

            List<String> missingHooks = new ArrayList<>();
            for (String k : requiredKinds) {
                if (!installedByKind.containsKey(k)) {
                    missingHooks.add(k);
                }
            }
            List<String> missingHooksSorted = new ArrayList<>(missingHooks);
            missingHooksSorted.sort(String::compareTo);

            List<JsonObject> missingChecks = new ArrayList<>();
            for (JsonObject r : requiredForRepo) {
                String k = r.get("kind").getAsString();
                if (installedByKind.containsKey(k)) {
                    Set<String> present = new HashSet<>();
                    JsonArray checksPresent =
                            installedByKind.get(k).getAsJsonArray("checks_present");
                    for (JsonElement c : checksPresent) {
                        present.add(c.getAsString());
                    }
                    for (JsonElement chkEl : r.getAsJsonArray("required_checks")) {
                        String chk = chkEl.getAsString();
                        if (!present.contains(chk)) {
                            JsonObject mc = new JsonObject();
                            mc.addProperty("hook", k);
                            mc.addProperty("check", chk);
                            missingChecks.add(mc);
                        }
                    }
                }
            }
            missingChecks.sort(
                    Comparator.comparing((JsonObject x) -> x.get("hook").getAsString())
                            .thenComparing(x -> x.get("check").getAsString()));

            List<String> effMissingHooksNoWaiver = new ArrayList<>();
            for (String k : missingHooksSorted) {
                if (!activeWaiverKinds.contains(k)) {
                    effMissingHooksNoWaiver.add(k);
                }
            }
            List<JsonObject> effMissingChecksNoWaiver = new ArrayList<>();
            for (JsonObject c : missingChecks) {
                if (!activeWaiverKinds.contains(c.get("hook").getAsString())) {
                    effMissingChecksNoWaiver.add(c);
                }
            }

            String preliminary;
            if (effMissingHooksNoWaiver.isEmpty() && effMissingChecksNoWaiver.isEmpty()) {
                preliminary = "compliant";
            } else {
                preliminary = "non_compliant";
            }

            List<Integer> compDays = compromiseDaysByRepo.get(repo);
            boolean isQuarantined = !compDays.isEmpty();
            Integer compromiseDay = isQuarantined ? compDays.stream().min(Integer::compareTo).get() : null;

            String level;
            if (isQuarantined) {
                level = "quarantine";
                compromised.add(repo);
            } else {
                List<OverrideEntry> ovs = overridesByRepo.get(repo);
                if (!ovs.isEmpty()) {
                    ovs.sort(
                            Comparator.comparingInt((OverrideEntry t) -> t.event.get("day").getAsInt())
                                    .thenComparingInt(t -> t.index));
                    OverrideEntry winner = ovs.get(ovs.size() - 1);
                    level = winner.event.get("target_compliance").getAsString();
                } else {
                    level = preliminary;
                }
            }

            JsonObject repoEntry = new JsonObject();
            repoEntry.addProperty("repo", repo);
            repoEntry.addProperty("tier", tier);
            repoEntry.addProperty("compliance_level", level);
            repoEntry.add("missing_hooks", stringListToJson(missingHooksSorted));
            repoEntry.add("missing_checks", missingChecksToJson(missingChecks));
            repoEntry.add("active_waivers", waiverListToJson(activeWaiversList));
            if (compromiseDay != null) {
                repoEntry.addProperty("compromise_day", compromiseDay);
            } else {
                repoEntry.add("compromise_day", JsonNull.INSTANCE);
            }
            repoComplianceEntries.add(repoEntry);

            byCompliance.put(level, byCompliance.get(level) + 1);

            if (isQuarantined) {
                for (String k : requiredKinds) {
                    JsonObject action = new JsonObject();
                    action.addProperty("repo", repo);
                    action.addProperty("hook", k);
                    action.addProperty("action", "force_reinstall");
                    action.addProperty("reason", "compromise_quarantine");
                    installActions.add(action);
                }
            } else {
                for (String k : effMissingHooksNoWaiver) {
                    JsonObject action = new JsonObject();
                    action.addProperty("repo", repo);
                    action.addProperty("hook", k);
                    action.addProperty("action", "install");
                    action.addProperty("reason", "missing_required");
                    installActions.add(action);
                }
            }

            for (Map.Entry<String, JsonElement> branchEntry : reqHooksPerBranch.entrySet()) {
                String branch = branchEntry.getKey();
                if (!protectedBranchSet.contains(branch)) {
                    continue;
                }
                JsonArray reqHooksArr = branchEntry.getValue().getAsJsonArray();
                List<String> reqHooksSorted = new ArrayList<>();
                for (JsonElement h : reqHooksArr) {
                    reqHooksSorted.add(h.getAsString());
                }
                reqHooksSorted.sort(String::compareTo);

                List<String> missingB = new ArrayList<>();
                for (String h : reqHooksSorted) {
                    if (!installedByKind.containsKey(h)) {
                        missingB.add(h);
                    }
                }

                String bpStatus;
                if (isQuarantined) {
                    bpStatus = "quarantined";
                } else if (missingB.isEmpty()) {
                    bpStatus = "compliant";
                } else if (missingB.stream().allMatch(activeWaiverKinds::contains)) {
                    bpStatus = "waivered";
                } else {
                    bpStatus = "missing_hook";
                }

                JsonObject be = new JsonObject();
                be.addProperty("repo", repo);
                be.addProperty("branch", branch);
                be.add("required_hooks", stringListToJson(reqHooksSorted));
                be.add("missing_hooks", stringListToJson(missingB));
                be.addProperty("status", bpStatus);
                branchEntries.add(be);
            }

            JsonArray typeWl = typeWlPerTier.getAsJsonArray(tier);
            Set<String> typeWlSet = new HashSet<>();
            for (JsonElement t : typeWl) {
                typeWlSet.add(t.getAsString());
            }
            int maxLen = maxLenPerTier.get(tier).getAsInt();
            boolean requireIssue = requireIssuePerTier.get(tier).getAsBoolean();

            for (JsonElement cEl : rd.commits) {
                JsonObject c = cEl.getAsJsonObject();
                String sha = c.get("sha").getAsString();
                String branch = c.get("branch").getAsString();
                String mtype = c.get("msg_type").getAsString();
                String subj = c.get("msg_subject").getAsString();
                String iref = c.has("issue_ref") && !c.get("issue_ref").isJsonNull()
                        ? c.get("issue_ref").getAsString()
                        : null;
                int cday = c.get("day").getAsInt();

                String status;
                if (protectedBranchSet.contains(branch) && "wip".equals(mtype)) {
                    status = "protected_branch_violation";
                } else if (!typeWlSet.contains(mtype)) {
                    status = "type_not_allowed";
                } else if (subj.length() > maxLen) {
                    status = "length_exceeded";
                } else if (requireIssue
                        && (iref == null || !issueRefPat.matcher(iref).matches())) {
                    status = "missing_issue_ref";
                } else {
                    status = "valid";
                }

                if (isQuarantined && cday >= compromiseDay) {
                    status = "needs_review";
                }

                JsonObject cr = new JsonObject();
                cr.addProperty("sha", sha);
                cr.addProperty("repo", repo);
                cr.addProperty("branch", branch);
                cr.addProperty("status", status);
                commitReviewEntries.add(cr);
                byCommitStatus.put(status, byCommitStatus.get(status) + 1);
            }
        }

        repoComplianceEntries.sort(Comparator.comparing(x -> x.get("repo").getAsString()));
        installActions.sort(
                Comparator.comparing((JsonObject x) -> x.get("repo").getAsString())
                        .thenComparing(x -> x.get("hook").getAsString()));
        branchEntries.sort(
                Comparator.comparing((JsonObject x) -> x.get("repo").getAsString())
                        .thenComparing(x -> x.get("branch").getAsString()));
        commitReviewEntries.sort(
                Comparator.comparing((JsonObject x) -> x.get("repo").getAsString())
                        .thenComparing(x -> x.get("sha").getAsString()));

        JsonObject repoCompliance = new JsonObject();
        repoCompliance.add("repos", listToJsonArray(repoComplianceEntries));
        writeJson(auditDir.resolve("repo_compliance.json"), repoCompliance);

        JsonObject hookInstallPlan = new JsonObject();
        hookInstallPlan.add("actions", listToJsonArray(installActions));
        writeJson(auditDir.resolve("hook_install_plan.json"), hookInstallPlan);

        JsonObject commitReview = new JsonObject();
        commitReview.add("commits", listToJsonArray(commitReviewEntries));
        writeJson(auditDir.resolve("commit_review.json"), commitReview);

        JsonObject branchProtectionOut = new JsonObject();
        branchProtectionOut.add("entries", listToJsonArray(branchEntries));
        writeJson(auditDir.resolve("branch_protection.json"), branchProtectionOut);

        int totalCommits = 0;
        for (String r : repoNames) {
            totalCommits += repoData.get(r).commits.size();
        }

        JsonObject summary = new JsonObject();
        summary.addProperty("current_day", currentDay);
        summary.addProperty("policy_version", policyVersion);
        summary.addProperty("total_repos", repoNames.size());
        summary.addProperty("total_commits", totalCommits);
        summary.addProperty("ignored_incident_events", ignored);
        summary.add("by_compliance", intMapToJson(byCompliance));
        summary.add("by_commit_status", intMapToJson(byCommitStatus));
        summary.addProperty("active_waivers", summaryActiveWaivers);
        summary.add("compromised_repos", stringListToJson(new ArrayList<>(compromised)));
        writeJson(auditDir.resolve("summary.json"), summary);
    }

    private static List<JsonObject> effectivePolicy(JsonArray globalRules, JsonObject prof) {
        JsonArray overrides =
                prof.has("override_rules") && !prof.get("override_rules").isJsonNull()
                        ? prof.getAsJsonArray("override_rules")
                        : new JsonArray();

        Map<String, JsonObject> lastByKind = new HashMap<>();
        for (JsonElement rEl : overrides) {
            JsonObject r = rEl.getAsJsonObject();
            lastByKind.put(r.get("kind").getAsString(), r);
        }

        List<JsonObject> kept = new ArrayList<>();
        for (JsonElement rEl : globalRules) {
            JsonObject r = rEl.getAsJsonObject();
            if (!lastByKind.containsKey(r.get("kind").getAsString())) {
                kept.add(r);
            }
        }
        kept.addAll(lastByKind.values());
        return kept;
    }

    private static boolean isActiveWaiver(JsonObject ev, int currentDay) {
        int start = ev.get("day").getAsInt();
        int end = ev.get("day").getAsInt() + ev.get("duration_days").getAsInt() - 1;
        return start <= currentDay && currentDay <= end;
    }

    private static int expiresDay(JsonObject ev) {
        return ev.get("day").getAsInt() + ev.get("duration_days").getAsInt() - 1;
    }

    private static JsonObject loadJson(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static void writeJson(Path path, JsonObject root) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        JsonElement sorted = deepSort(root);
        String text = gson.toJson(sorted) + "\n";
        Files.writeString(path, text, StandardCharsets.UTF_8);
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

    private static JsonArray listToJsonArray(List<JsonObject> items) {
        JsonArray arr = new JsonArray();
        for (JsonObject item : items) {
            arr.add(item);
        }
        return arr;
    }

    private static JsonArray stringListToJson(List<String> items) {
        JsonArray arr = new JsonArray();
        for (String item : items) {
            arr.add(item);
        }
        return arr;
    }

    private static JsonArray missingChecksToJson(List<JsonObject> items) {
        JsonArray arr = new JsonArray();
        for (JsonObject item : items) {
            arr.add(item);
        }
        return arr;
    }

    private static JsonArray waiverListToJson(List<JsonObject> items) {
        JsonArray arr = new JsonArray();
        for (JsonObject item : items) {
            arr.add(item);
        }
        return arr;
    }

    private static JsonObject intMapToJson(Map<String, Integer> map) {
        JsonObject obj = new JsonObject();
        for (Map.Entry<String, Integer> e : map.entrySet()) {
            obj.addProperty(e.getKey(), e.getValue());
        }
        return obj;
    }

    private static String jsonStringOrNull(JsonObject obj, String key) {
        if (!obj.has(key) || obj.get(key).isJsonNull()) {
            return null;
        }
        JsonElement el = obj.get(key);
        if (!el.isJsonPrimitive() || !el.getAsJsonPrimitive().isString()) {
            return null;
        }
        return el.getAsString();
    }

    private static Integer jsonIntStrict(JsonObject obj, String key) {
        if (!obj.has(key) || obj.get(key).isJsonNull()) {
            return null;
        }
        JsonElement el = obj.get(key);
        if (!el.isJsonPrimitive()) {
            return null;
        }
        if (el.getAsJsonPrimitive().isBoolean()) {
            return null;
        }
        if (!el.getAsJsonPrimitive().isNumber()) {
            return null;
        }
        BigDecimal bd = el.getAsBigDecimal();
        try {
            return bd.intValueExact();
        } catch (ArithmeticException ex) {
            return null;
        }
    }

    private static final class RepoData {
        final JsonObject profile;
        final JsonObject hooks;
        final JsonArray commits;

        RepoData(JsonObject profile, JsonObject hooks, JsonArray commits) {
            this.profile = profile;
            this.hooks = hooks;
            this.commits = commits;
        }
    }

    private static final class OverrideEntry {
        final int index;
        final JsonObject event;

        OverrideEntry(int index, JsonObject event) {
            this.index = index;
            this.event = event;
        }
    }
}
