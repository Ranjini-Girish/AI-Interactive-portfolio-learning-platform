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
import java.util.Arrays;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Cargo workspace bump planner oracle. */
public final class CargoWsBumpAudit {

    private static final Pattern GTE_LT =
            Pattern.compile("^>=(\\d+\\.\\d+\\.\\d+) <(\\d+\\.\\d+\\.\\d+)$");
    private static final Map<String, Integer> SEV_RANK =
            Map.of("low", 0, "medium", 1, "high", 2, "critical", 3);
    private static final Set<String> ACCEPTED_KINDS =
            Set.of("force_freeze", "forced_bump", "advisory_override");

    private CargoWsBumpAudit() {}

    public static void main(String[] args) throws IOException {
        Path data =
                Path.of(
                        System.getenv()
                                .getOrDefault("CWB_DATA_DIR", "/app/workspace"));
        Path plan =
                Path.of(System.getenv().getOrDefault("CWB_PLAN_DIR", "/app/plan"));
        run(data, plan);
    }

    private static void run(Path dataDir, Path planDir) throws IOException {
        Files.createDirectories(planDir);

        JsonObject manifest = loadJson(dataDir.resolve("workspace_manifest.json"));
        JsonObject pool = loadJson(dataDir.resolve("pool_state.json"));
        JsonObject lockRoot = loadJson(dataDir.resolve("current_lock.json"));
        JsonObject advisoriesRaw = loadJson(dataDir.resolve("advisories.json"));
        JsonObject incidentsRaw = loadJson(dataDir.resolve("incident_log.json"));

        TreeMap<String, String> lock = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e :
                lockRoot.getAsJsonObject("locks").entrySet()) {
            lock.put(e.getKey(), e.getValue().getAsString());
        }

        TreeMap<String, String> workspaceDependencies = new TreeMap<>();
        for (Map.Entry<String, JsonElement> e :
                manifest.getAsJsonObject("workspace_dependencies").entrySet()) {
            workspaceDependencies.put(e.getKey(), e.getValue().getAsString());
        }

        Ver workspaceMsrv = parseSemver(manifest.get("workspace_msrv").getAsString());
        int severityThreshold =
                SEV_RANK.get(manifest.get("severity_block_threshold").getAsString());
        boolean allowYankedPinned = manifest.get("allow_yanked_pinned").getAsBoolean();
        long currentDay = pool.get("current_day").getAsLong();

        TreeMap<String, Member> members = loadMembers(dataDir);
        TreeMap<String, CrateDoc> registry = loadRegistry(dataDir);

        List<Event> prelimAccepted = new ArrayList<>();
        long ignoredCount = 0;
        for (JsonElement rawEl : incidentsRaw.getAsJsonArray("events")) {
            JsonObject raw = rawEl.getAsJsonObject();
            if (!raw.has("accepted") || !raw.get("accepted").getAsBoolean()) {
                ignoredCount++;
                continue;
            }
            if (!raw.has("day") || raw.get("day").getAsLong() > currentDay) {
                ignoredCount++;
                continue;
            }
            String kind = raw.has("kind") ? raw.get("kind").getAsString() : "";
            if (!ACCEPTED_KINDS.contains(kind)) {
                ignoredCount++;
                continue;
            }
            prelimAccepted.add(parseEvent(raw));
        }

        TreeMap<String, Event> scopeBest = new TreeMap<>();
        for (Event e : prelimAccepted) {
            String key = eventScope(e);
            Event prev = scopeBest.get(key);
            boolean take =
                    prev == null
                            || e.day > prev.day
                            || (e.day == prev.day && e.eventId.compareTo(prev.eventId) < 0);
            if (take) {
                scopeBest.put(key, e);
            }
        }
        List<Event> acceptedEvents = new ArrayList<>(scopeBest.values());

        Set<String> forceFreezeCrates = new TreeSet<>();
        TreeMap<String, Event> forcedBumpMap = new TreeMap<>();
        Set<String> overriddenAdvisoryIds = new TreeSet<>();
        for (Event e : acceptedEvents) {
            switch (e.kind) {
                case "force_freeze" -> forceFreezeCrates.add(e.crateName);
                case "forced_bump" ->
                        forcedBumpMap.put(
                                memberCrateKey(e.member, e.crateName), e);
                case "advisory_override" -> overriddenAdvisoryIds.add(e.advisoryId);
                default -> {}
            }
        }
        Set<String> forcedBumpSet = new TreeSet<>(forcedBumpMap.keySet());

        TreeMap<String, Advisory> allAdvisoriesById = new TreeMap<>();
        TreeMap<String, List<Advisory>> activeAdvisoriesByCrate = new TreeMap<>();
        for (JsonElement aEl : advisoriesRaw.getAsJsonArray("advisories")) {
            JsonObject a = aEl.getAsJsonObject();
            Advisory adv =
                    new Advisory(
                            a.get("advisory_id").getAsString(),
                            a.get("crate").getAsString(),
                            a.get("severity").getAsString(),
                            SEV_RANK.get(a.get("severity").getAsString()),
                            parseRange(a.get("affected_range").getAsString()),
                            a.get("day_published").getAsLong());
            allAdvisoriesById.put(adv.advisoryId, adv);
            if (!overriddenAdvisoryIds.contains(adv.advisoryId)
                    && adv.sevRank >= severityThreshold) {
                activeAdvisoriesByCrate
                        .computeIfAbsent(adv.crateName, k -> new ArrayList<>())
                        .add(adv);
            }
        }

        PlannerCtx ctx =
                new PlannerCtx(
                        workspaceMsrv,
                        allowYankedPinned,
                        lock,
                        activeAdvisoriesByCrate,
                        members,
                        workspaceDependencies,
                        forcedBumpSet);

        TreeMap<String, CrateDecision> crateDecision = new TreeMap<>();
        TreeSet<String> allCratesInDeps = new TreeSet<>();
        for (Member m : members.values()) {
            allCratesInDeps.addAll(m.deps.keySet());
        }

        for (String crateName : allCratesInDeps) {
            if (!registry.containsKey(crateName)) {
                continue;
            }
            List<VersionInfo> versions = registry.get(crateName).versions;
            if (forceFreezeCrates.contains(crateName)) {
                String lockedStr = lock.get(crateName);
                VersionInfo chosen = null;
                List<String> blocking = new ArrayList<>();
                boolean freezeUnsafe = false;
                if (lockedStr != null) {
                    Ver lv = parseSemver(lockedStr);
                    for (VersionInfo vinfo : versions) {
                        if (vinfo.ver.equals(lv)) {
                            chosen = vinfo;
                            blocking = ctx.blockingActive(crateName, lv);
                            boolean yankedUnsafe =
                                    vinfo.yanked
                                            && !(allowYankedPinned
                                                    && lockedStr.equals(vinfo.verStr));
                            if (!blocking.isEmpty() || yankedUnsafe) {
                                freezeUnsafe = true;
                            }
                            break;
                        }
                    }
                }
                crateDecision.put(
                        crateName,
                        new CrateDecision(
                                chosen,
                                new ArrayList<>(),
                                new ArrayList<>(),
                                true,
                                blocking,
                                freezeUnsafe));
                continue;
            }

            List<String> sharingMembers = ctx.sharingSetFor(crateName);
            if (!sharingMembers.isEmpty()) {
                Range eff = parseRange(workspaceDependencies.get(crateName));
                List<VersionInfo> eligible = new ArrayList<>();
                for (VersionInfo v : versions) {
                    if (ctx.eligibilityBasic(crateName, v, eff, workspaceMsrv)) {
                        eligible.add(v);
                    }
                }
                SelectResult sel = plannerSelect(ctx, crateName, eligible, sharingMembers);
                crateDecision.put(
                        crateName,
                        new CrateDecision(
                                sel.chosen,
                                sel.dropped,
                                sharingMembers,
                                false,
                                new ArrayList<>(),
                                false));
            }
        }

        List<JsonObject> bumpPlanEntries = new ArrayList<>();
        List<JsonObject> featureConflictEvents = new ArrayList<>();
        TreeMap<String, List<ConsumerRec>> advisoryConsumers = new TreeMap<>();
        TreeMap<String, TreeSet<String>> mitigatedVersionsByAdvisory = new TreeMap<>();
        for (String aid : allAdvisoriesById.keySet()) {
            advisoryConsumers.put(aid, new ArrayList<>());
            mitigatedVersionsByAdvisory.put(aid, new TreeSet<>());
        }
        Set<String> stillOpenFrozen = new TreeSet<>();
        Set<String> hardConflictPerAdvisory = new TreeSet<>();

        List<String[]> allEntries = new ArrayList<>();
        for (String memberName : members.keySet()) {
            for (String crateName : members.get(memberName).deps.keySet()) {
                allEntries.add(new String[] {memberName, crateName});
            }
        }

        for (String[] pair : allEntries) {
            String memberName = pair[0];
            String crateName = pair[1];
            DepDecl dep = members.get(memberName).deps.get(crateName);
            String currentVersion = lock.get(crateName);

            VersionInfo chosenInfo;
            String action;
            String source;
            String sharing;

            if (forceFreezeCrates.contains(crateName)) {
                CrateDecision dec = crateDecision.get(crateName);
                sharing = dep.workspace ? "shared" : "per_member";
                source = "incident_log_force_freeze";
                chosenInfo = dec.chosen;
                if (chosenInfo == null) {
                    action = "block_no_safe_version";
                } else if (dec.freezeUnsafe) {
                    action = "freeze_unsafe";
                } else {
                    action = "freeze";
                }
            } else if (forcedBumpMap.containsKey(memberCrateKey(memberName, crateName))) {
                Event evt = forcedBumpMap.get(memberCrateKey(memberName, crateName));
                String pinnedStr = evt.pinnedVersion;
                Ver pinnedVer = parseSemver(pinnedStr);
                List<VersionInfo> versions =
                        registry.containsKey(crateName)
                                ? registry.get(crateName).versions
                                : List.of();
                Range eff = ctx.effectiveRangeFor(memberName, crateName);
                sharing = dep.workspace ? "forced_per_member" : "per_member";
                source = "incident_log_forced_bump";
                VersionInfo vinfo = null;
                for (VersionInfo v : versions) {
                    if (v.ver.equals(pinnedVer)) {
                        vinfo = v;
                        break;
                    }
                }
                Ver entryMsrv = ctx.effectiveMsrvFor(memberName, crateName);
                if (vinfo != null
                        && ctx.eligibilityBasic(crateName, vinfo, eff, entryMsrv)) {
                    action = "forced_bump";
                    chosenInfo = vinfo;
                } else {
                    action = "block_no_safe_version";
                    chosenInfo = null;
                }
            } else if (dep.workspace) {
                CrateDecision dec = crateDecision.get(crateName);
                sharing = "shared";
                source = "planner";
                chosenInfo = dec != null ? dec.chosen : null;
                action =
                        chosenInfo == null
                                ? "block_no_safe_version"
                                : classifyPlannerAction(lock, crateName, chosenInfo);
            } else {
                sharing = "per_member";
                source = "planner";
                Range eff = ctx.effectiveRangeFor(memberName, crateName);
                Ver entryMsrv = ctx.effectiveMsrvFor(memberName, crateName);
                List<VersionInfo> versions =
                        registry.containsKey(crateName)
                                ? registry.get(crateName).versions
                                : List.of();
                List<VersionInfo> eligible = new ArrayList<>();
                for (VersionInfo v : versions) {
                    if (ctx.eligibilityBasic(crateName, v, eff, entryMsrv)) {
                        eligible.add(v);
                    }
                }
                SelectResult sel =
                        plannerSelect(
                                ctx, crateName, eligible, List.of(memberName));
                chosenInfo = sel.chosen;
                action =
                        chosenInfo == null
                                ? "block_no_safe_version"
                                : classifyPlannerAction(lock, crateName, chosenInfo);
            }

            List<String> featureLossSet = new ArrayList<>();
            if (chosenInfo != null) {
                TreeSet<String> req = new TreeSet<>(dep.features);
                if (dep.defaultFeatures) {
                    req.addAll(chosenInfo.defaultFeatures);
                }
                for (String f : req) {
                    if (!chosenInfo.features.contains(f)) {
                        featureLossSet.add(f);
                    }
                }
            }

            String reason;
            if ("block_no_safe_version".equals(action)) {
                reason = "no_eligible_version";
            } else if ("freeze_unsafe".equals(action)) {
                reason = "freeze_advisory_conflict";
            } else if (!featureLossSet.isEmpty()) {
                reason = "feature_downgrade";
            } else {
                reason = "satisfied";
            }

            String chosenVersionStr = chosenInfo != null ? chosenInfo.verStr : null;

            JsonObject entry = new JsonObject();
            entry.addProperty("member", memberName);
            entry.addProperty("crate", crateName);
            if (currentVersion != null) {
                entry.addProperty("current_version", currentVersion);
            } else {
                entry.add("current_version", JsonNull.INSTANCE);
            }
            if (chosenVersionStr != null) {
                entry.addProperty("chosen_version", chosenVersionStr);
            } else {
                entry.add("chosen_version", JsonNull.INSTANCE);
            }
            entry.addProperty("action", action);
            entry.addProperty("reason", reason);
            JsonArray lossArr = new JsonArray();
            for (String f : featureLossSet) {
                lossArr.add(f);
            }
            entry.add("feature_loss_set", lossArr);
            entry.addProperty("sharing", sharing);
            entry.addProperty("source", source);
            bumpPlanEntries.add(entry);

            if (!featureLossSet.isEmpty()) {
                Set<String> required = new HashSet<>(dep.requiredFeatures);
                Set<String> lost = new HashSet<>(featureLossSet);
                boolean hardConflict = false;
                for (String f : lost) {
                    if (required.contains(f)) {
                        hardConflict = true;
                        break;
                    }
                }
                JsonObject fc = new JsonObject();
                fc.addProperty("member", memberName);
                fc.addProperty("crate", crateName);
                JsonArray lostArr = new JsonArray();
                for (String f : featureLossSet) {
                    lostArr.add(f);
                }
                fc.add("lost_features", lostArr);
                fc.addProperty("hard_conflict", hardConflict);
                fc.addProperty("forced_disable", hardConflict);
                featureConflictEvents.add(fc);
            }

            if (chosenVersionStr != null) {
                Ver cver = parseSemver(chosenVersionStr);
                for (Advisory adv : allAdvisoriesById.values()) {
                    if (!adv.crateName.equals(crateName)) {
                        continue;
                    }
                    boolean inRangeFlag = inRange(cver, adv.range);
                    boolean hardFlag = false;
                    if (!featureLossSet.isEmpty()) {
                        Set<String> required = new HashSet<>(dep.requiredFeatures);
                        for (String f : featureLossSet) {
                            if (required.contains(f)) {
                                hardFlag = true;
                                break;
                            }
                        }
                    }
                    advisoryConsumers
                            .get(adv.advisoryId)
                            .add(
                                    new ConsumerRec(
                                            memberName,
                                            chosenVersionStr,
                                            inRangeFlag,
                                            hardFlag));
                    mitigatedVersionsByAdvisory
                            .get(adv.advisoryId)
                            .add(chosenVersionStr);
                    if ("freeze_unsafe".equals(action)
                            && adv.sevRank >= severityThreshold
                            && !overriddenAdvisoryIds.contains(adv.advisoryId)
                            && inRangeFlag) {
                        stillOpenFrozen.add(adv.advisoryId);
                    }
                    if (adv.sevRank >= severityThreshold
                            && !overriddenAdvisoryIds.contains(adv.advisoryId)
                            && !featureLossSet.isEmpty()
                            && hardFlag) {
                        hardConflictPerAdvisory.add(adv.advisoryId);
                    }
                }
            } else {
                for (Advisory adv : allAdvisoriesById.values()) {
                    if (!adv.crateName.equals(crateName)) {
                        continue;
                    }
                    advisoryConsumers
                            .get(adv.advisoryId)
                            .add(new ConsumerRec(memberName, null, false, false));
                }
            }
        }

        bumpPlanEntries.sort(
                Comparator.comparing((JsonObject e) -> e.get("member").getAsString())
                        .thenComparing(e -> e.get("crate").getAsString()));

        List<JsonObject> msrvMembersJson = new ArrayList<>();
        long msrvInconsistentCount = 0;
        for (String memberName : members.keySet()) {
            Member m = members.get(memberName);
            Ver mm = parseSemver(m.memberMsrv);
            String status;
            String exceededBy;
            if (mm.compareTo(workspaceMsrv) > 0) {
                msrvInconsistentCount++;
                Ver diff = componentwiseDiff(mm, workspaceMsrv);
                status = "inconsistent";
                exceededBy = fmtVer(diff);
            } else {
                status = "compatible";
                exceededBy = "0.0.0";
            }

            TreeSet<String> blockedPairs = new TreeSet<>();
            for (String crateName : m.deps.keySet()) {
                if (!registry.containsKey(crateName)) {
                    continue;
                }
                Range eff = ctx.effectiveRangeFor(memberName, crateName);
                Ver entryMsrv = ctx.effectiveMsrvFor(memberName, crateName);
                for (VersionInfo vinfo : registry.get(crateName).versions) {
                    if (!inRange(vinfo.ver, eff)) {
                        continue;
                    }
                    if (vinfo.msrv.compareTo(entryMsrv) > 0) {
                        blockedPairs.add(crateName + "\0" + vinfo.verStr);
                    }
                }
            }

            JsonObject row = new JsonObject();
            row.addProperty("member", memberName);
            row.addProperty("member_msrv", m.memberMsrv);
            row.addProperty("status", status);
            row.addProperty("exceeded_by", exceededBy);
            row.addProperty("msrv_blocked_versions_count", blockedPairs.size());
            msrvMembersJson.add(row);
        }

        List<JsonObject> advisoryOut = new ArrayList<>();
        for (String aid : allAdvisoriesById.keySet()) {
            Advisory a = allAdvisoriesById.get(aid);
            List<ConsumerRec> consumers = advisoryConsumers.get(aid);
            boolean overridden = overriddenAdvisoryIds.contains(aid);

            String status;
            String mitigation;
            if (overridden) {
                status = "overridden";
                mitigation = "override";
            } else if (a.sevRank < severityThreshold) {
                status = "inactive_low_severity";
                mitigation = null;
            } else if (stillOpenFrozen.contains(aid)) {
                status = "still_open_frozen";
                mitigation = "frozen";
            } else if (hardConflictPerAdvisory.contains(aid)) {
                status = "mitigated_by_forced_disable";
                mitigation = "forced_disable";
            } else {
                boolean anyBlock =
                        consumers.stream().anyMatch(c -> c.chosenVersion == null);
                if (anyBlock) {
                    status = "still_open";
                    mitigation = null;
                } else {
                    boolean inRangeAny = consumers.stream().anyMatch(c -> c.inRange);
                    if (!inRangeAny) {
                        status = "resolved_by_bump";
                        mitigation = "bump";
                    } else {
                        status = "still_open";
                        mitigation = null;
                    }
                }
            }

            JsonArray mvJson = new JsonArray();
            for (String v : mitigatedVersionsByAdvisory.get(aid)) {
                mvJson.add(v);
            }

            JsonObject row = new JsonObject();
            row.addProperty("advisory_id", aid);
            row.addProperty("crate", a.crateName);
            row.addProperty("severity", a.severity);
            row.addProperty("status", status);
            if (mitigation != null) {
                row.addProperty("mitigation_method", mitigation);
            } else {
                row.add("mitigation_method", JsonNull.INSTANCE);
            }
            row.add("mitigated_versions", mvJson);
            row.addProperty("day_published", a.dayPublished);
            advisoryOut.add(row);
        }

        TreeMap<String, Long> actionCounts = new TreeMap<>();
        for (JsonObject e : bumpPlanEntries) {
            String key = e.get("action").getAsString();
            actionCounts.merge(key, 1L, Long::sum);
        }
        TreeMap<String, Long> advisoryCounts = new TreeMap<>();
        for (JsonObject a : advisoryOut) {
            String key = a.get("status").getAsString();
            advisoryCounts.merge(key, 1L, Long::sum);
        }

        Set<String> sharedCrates = new TreeSet<>();
        Set<String> perMemberCrates = new TreeSet<>();
        for (JsonObject e : bumpPlanEntries) {
            String crateName = e.get("crate").getAsString();
            String sharingVal = e.get("sharing").getAsString();
            if ("shared".equals(sharingVal)) {
                sharedCrates.add(crateName);
            } else if ("per_member".equals(sharingVal) || "forced_per_member".equals(sharingVal)) {
                perMemberCrates.add(crateName);
            }
        }

        long hardConflictCount =
                featureConflictEvents.stream()
                        .filter(e -> e.get("hard_conflict").getAsBoolean())
                        .count();

        JsonObject summary = new JsonObject();
        summary.addProperty("workspace_msrv", manifest.get("workspace_msrv").getAsString());
        summary.addProperty(
                "severity_block_threshold",
                manifest.get("severity_block_threshold").getAsString());
        summary.addProperty("total_members", members.size());
        summary.addProperty("total_crates_in_registry", registry.size());
        summary.addProperty("total_entries", bumpPlanEntries.size());
        summary.add("action_counts", longMapToJson(actionCounts));
        summary.addProperty("shared_crate_count", sharedCrates.size());
        summary.addProperty("per_member_crate_count", perMemberCrates.size());
        summary.addProperty("hard_conflict_count", hardConflictCount);
        summary.add("advisory_counts", longMapToJson(advisoryCounts));
        summary.addProperty("ignored_incident_events", ignoredCount);
        summary.addProperty("msrv_inconsistent_member_count", msrvInconsistentCount);

        JsonObject bumpPlan = new JsonObject();
        JsonArray entriesArr = new JsonArray();
        for (JsonObject e : bumpPlanEntries) {
            entriesArr.add(e);
        }
        bumpPlan.add("entries", entriesArr);

        JsonObject msrvOut = new JsonObject();
        msrvOut.addProperty("workspace_msrv", manifest.get("workspace_msrv").getAsString());
        JsonArray membersArr = new JsonArray();
        for (JsonObject m : msrvMembersJson) {
            membersArr.add(m);
        }
        msrvOut.add("members", membersArr);

        JsonObject fcOut = new JsonObject();
        JsonArray eventsArr = new JsonArray();
        for (JsonObject ev : featureConflictEvents) {
            eventsArr.add(ev);
        }
        fcOut.add("events", eventsArr);

        JsonObject advOut = new JsonObject();
        JsonArray advArr = new JsonArray();
        for (JsonObject a : advisoryOut) {
            advArr.add(a);
        }
        advOut.add("advisories", advArr);

        writeJson(planDir.resolve("bump_plan.json"), bumpPlan);
        writeJson(planDir.resolve("msrv_compatibility.json"), msrvOut);
        writeJson(planDir.resolve("feature_conflict_report.json"), fcOut);
        writeJson(planDir.resolve("advisory_status.json"), advOut);
        writeJson(planDir.resolve("summary.json"), summary);
    }

    private static SelectResult plannerSelect(
            PlannerCtx ctx,
            String crateName,
            List<VersionInfo> eligible,
            List<String> sharingMembers) {
        if (eligible.isEmpty()) {
            return new SelectResult(null, new ArrayList<>());
        }
        boolean useDefaults = sharedDefaultPref(crateName, ctx.members, sharingMembers);

        List<VersionInfo> eligibleDesc = new ArrayList<>(eligible);
        eligibleDesc.sort((a, b) -> b.ver.compareTo(a.ver));

        TreeSet<String> sharedFeatures = new TreeSet<>();
        for (String m : sharingMembers) {
            for (String f : ctx.members.get(m).deps.get(crateName).features) {
                sharedFeatures.add(f);
            }
        }

        for (VersionInfo v : eligibleDesc) {
            TreeSet<String> req = new TreeSet<>(sharedFeatures);
            if (useDefaults) {
                req.addAll(v.defaultFeatures);
            }
            if (req.stream().allMatch(f -> v.features.contains(f))) {
                return new SelectResult(v, new ArrayList<>());
            }
        }

        TreeSet<String> unionRequested = new TreeSet<>(sharedFeatures);
        if (useDefaults) {
            unionRequested.addAll(eligibleDesc.get(0).defaultFeatures);
        }

        List<String> dropped = new ArrayList<>();
        TreeSet<String> remaining = new TreeSet<>(unionRequested);
        while (true) {
            for (VersionInfo v : eligibleDesc) {
                if (remaining.stream().allMatch(f -> v.features.contains(f))) {
                    List<String> sorted = new ArrayList<>(dropped);
                    sorted.sort(String::compareTo);
                    return new SelectResult(v, sorted);
                }
            }
            List<String> notSupported = new ArrayList<>();
            for (String f : remaining) {
                boolean any =
                        eligibleDesc.stream().anyMatch(v -> v.features.contains(f));
                if (!any) {
                    notSupported.add(f);
                }
            }
            String pick;
            if (!notSupported.isEmpty()) {
                notSupported.sort(String::compareTo);
                pick = notSupported.get(0);
            } else {
                pick = remaining.first();
            }
            dropped.add(pick);
            remaining.remove(pick);
            if (remaining.isEmpty()) {
                List<String> sorted = new ArrayList<>(dropped);
                sorted.sort(String::compareTo);
                return new SelectResult(eligibleDesc.get(0), sorted);
            }
        }
    }

    private static boolean sharedDefaultPref(
            String crateName, TreeMap<String, Member> members, List<String> sharing) {
        for (String m : sharing) {
            if (members.get(m).deps.get(crateName).defaultFeatures) {
                return true;
            }
        }
        return false;
    }

    private static String classifyPlannerAction(
            TreeMap<String, String> lock, String crateName, VersionInfo ci) {
        String locked = lock.get(crateName);
        if (locked == null) {
            return "hold";
        }
        Ver lv = parseSemver(locked);
        if (ci.ver.equals(lv)) {
            return "hold";
        }
        if (ci.ver.compareTo(lv) > 0) {
            return "bump";
        }
        return "downgrade";
    }

    private static String eventScope(Event e) {
        return switch (e.kind) {
            case "force_freeze" -> "force_freeze\u001f" + e.crateName;
            case "forced_bump" ->
                    "forced_bump\u001f" + e.crateName + "\u001f" + e.member;
            case "advisory_override" -> "advisory_override\u001f" + e.advisoryId;
            default -> throw new IllegalArgumentException("bad event kind: " + e.kind);
        };
    }

    private static Event parseEvent(JsonObject v) {
        return new Event(
                v.has("event_id") ? v.get("event_id").getAsString() : "",
                v.has("day") ? v.get("day").getAsLong() : Long.MIN_VALUE,
                v.has("kind") ? v.get("kind").getAsString() : "",
                v.has("crate") && !v.get("crate").isJsonNull()
                        ? v.get("crate").getAsString()
                        : null,
                v.has("member") && !v.get("member").isJsonNull()
                        ? v.get("member").getAsString()
                        : null,
                v.has("pinned_version") && !v.get("pinned_version").isJsonNull()
                        ? v.get("pinned_version").getAsString()
                        : null,
                v.has("advisory_id") && !v.get("advisory_id").isJsonNull()
                        ? v.get("advisory_id").getAsString()
                        : null);
    }

    private static List<VersionInfo> collectVersions(JsonObject reg) {
        List<VersionInfo> out = new ArrayList<>();
        for (JsonElement vEl : reg.getAsJsonArray("versions")) {
            JsonObject v = vEl.getAsJsonObject();
            TreeSet<String> features = new TreeSet<>();
            for (JsonElement x : v.getAsJsonArray("features")) {
                features.add(x.getAsString());
            }
            TreeSet<String> defaultFeatures = new TreeSet<>();
            for (JsonElement x : v.getAsJsonArray("default_features")) {
                defaultFeatures.add(x.getAsString());
            }
            out.add(
                    new VersionInfo(
                            parseSemver(v.get("version").getAsString()),
                            v.get("version").getAsString(),
                            parseSemver(v.get("msrv").getAsString()),
                            features,
                            defaultFeatures,
                            v.get("yanked").getAsBoolean()));
        }
        out.sort(Comparator.comparing(v -> v.ver));
        return out;
    }

    private static TreeMap<String, Member> loadMembers(Path dataDir) throws IOException {
        TreeMap<String, Member> members = new TreeMap<>();
        List<Path> paths = new ArrayList<>();
        try (DirectoryStream<Path> ds =
                Files.newDirectoryStream(dataDir.resolve("members"), "*.json")) {
            for (Path p : ds) {
                paths.add(p);
            }
        }
        paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
        for (Path fp : paths) {
            JsonObject m = loadJson(fp);
            String name = m.get("name").getAsString();
            String memberMsrv = m.get("member_msrv").getAsString();
            TreeMap<String, DepDecl> deps = new TreeMap<>();
            for (Map.Entry<String, JsonElement> e : m.getAsJsonObject("deps").entrySet()) {
                JsonObject v = e.getValue().getAsJsonObject();
                List<String> features = new ArrayList<>();
                for (JsonElement x : v.getAsJsonArray("features")) {
                    features.add(x.getAsString());
                }
                List<String> requiredFeatures = new ArrayList<>();
                for (JsonElement x : v.getAsJsonArray("required_features")) {
                    requiredFeatures.add(x.getAsString());
                }
                String versionRange =
                        v.has("version_range") && !v.get("version_range").isJsonNull()
                                ? v.get("version_range").getAsString()
                                : null;
                deps.put(
                        e.getKey(),
                        new DepDecl(
                                v.get("workspace").getAsBoolean(),
                                versionRange,
                                features,
                                v.get("default_features").getAsBoolean(),
                                requiredFeatures));
            }
            members.put(name, new Member(memberMsrv, deps));
        }
        return members;
    }

    private static TreeMap<String, CrateDoc> loadRegistry(Path dataDir) throws IOException {
        TreeMap<String, CrateDoc> registry = new TreeMap<>();
        List<Path> paths = new ArrayList<>();
        try (DirectoryStream<Path> ds =
                Files.newDirectoryStream(dataDir.resolve("registry"), "*.json")) {
            for (Path p : ds) {
                paths.add(p);
            }
        }
        paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
        for (Path fp : paths) {
            JsonObject r = loadJson(fp);
            String name = r.get("name").getAsString();
            registry.put(name, new CrateDoc(collectVersions(r)));
        }
        return registry;
    }

    private static String memberCrateKey(String member, String crate) {
        return member + "\0" + crate;
    }

    private static Ver parseSemver(String s) {
        String[] parts = s.split("\\.");
        if (parts.length != 3) {
            throw new IllegalArgumentException("bad semver: " + s);
        }
        return new Ver(
                Integer.parseInt(parts[0]),
                Integer.parseInt(parts[1]),
                Integer.parseInt(parts[2]));
    }

    private static Range parseRange(String r) {
        r = r.trim();
        if (r.startsWith("=")) {
            Ver v = parseSemver(r.substring(1).trim());
            return new Range(v, new Ver(v.maj, v.min, v.patch + 1));
        }
        if (r.startsWith("^")) {
            String[] parts = r.substring(1).trim().split("\\.");
            if (parts.length != 2) {
                throw new IllegalArgumentException("bad ^range: " + r);
            }
            int x = Integer.parseInt(parts[0]);
            int y = Integer.parseInt(parts[1]);
            Ver lo = new Ver(x, y, 0);
            Ver hi = x >= 1 ? new Ver(x + 1, 0, 0) : new Ver(0, y + 1, 0);
            return new Range(lo, hi);
        }
        if (r.startsWith("~")) {
            String[] parts = r.substring(1).trim().split("\\.");
            if (parts.length != 2) {
                throw new IllegalArgumentException("bad ~range: " + r);
            }
            int x = Integer.parseInt(parts[0]);
            int y = Integer.parseInt(parts[1]);
            return new Range(new Ver(x, y, 0), new Ver(x, y + 1, 0));
        }
        String cleaned = r.replaceAll("\\s+", "");
        String[] parts = cleaned.split(",");
        if (parts.length != 2) {
            throw new IllegalArgumentException("bad range: " + r);
        }
        if (!parts[0].startsWith(">=") || !parts[1].startsWith("<")) {
            Matcher m = GTE_LT.matcher(r);
            if (m.matches()) {
                return new Range(parseSemver(m.group(1)), parseSemver(m.group(2)));
            }
            throw new IllegalArgumentException("bad range: " + r);
        }
        Ver lo = parseSemver(parts[0].substring(2));
        Ver hi = parseSemver(parts[1].substring(1));
        return new Range(lo, hi);
    }

    private static boolean inRange(Ver v, Range rng) {
        return v.compareTo(rng.lo) >= 0 && v.compareTo(rng.hi) < 0;
    }

    private static Ver componentwiseDiff(Ver a, Ver b) {
        return new Ver(
                Math.max(a.maj - b.maj, 0),
                Math.max(a.min - b.min, 0),
                Math.max(a.patch - b.patch, 0));
    }

    private static String fmtVer(Ver v) {
        return v.maj + "." + v.min + "." + v.patch;
    }

    private static JsonObject longMapToJson(TreeMap<String, Long> m) {
        JsonObject o = new JsonObject();
        for (Map.Entry<String, Long> e : m.entrySet()) {
            o.addProperty(e.getKey(), e.getValue());
        }
        return o;
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

    private static final class Ver implements Comparable<Ver> {
        final int maj;
        final int min;
        final int patch;

        Ver(int maj, int min, int patch) {
            this.maj = maj;
            this.min = min;
            this.patch = patch;
        }

        @Override
        public int compareTo(Ver other) {
            if (maj != other.maj) {
                return Integer.compare(maj, other.maj);
            }
            if (min != other.min) {
                return Integer.compare(min, other.min);
            }
            return Integer.compare(patch, other.patch);
        }

        @Override
        public boolean equals(Object o) {
            if (!(o instanceof Ver other)) {
                return false;
            }
            return maj == other.maj && min == other.min && patch == other.patch;
        }

        @Override
        public int hashCode() {
            return Arrays.hashCode(new int[] {maj, min, patch});
        }
    }

    private static final class Range {
        final Ver lo;
        final Ver hi;

        Range(Ver lo, Ver hi) {
            this.lo = lo;
            this.hi = hi;
        }
    }

    private static final class VersionInfo {
        final Ver ver;
        final String verStr;
        final Ver msrv;
        final TreeSet<String> features;
        final TreeSet<String> defaultFeatures;
        final boolean yanked;

        VersionInfo(
                Ver ver,
                String verStr,
                Ver msrv,
                TreeSet<String> features,
                TreeSet<String> defaultFeatures,
                boolean yanked) {
            this.ver = ver;
            this.verStr = verStr;
            this.msrv = msrv;
            this.features = features;
            this.defaultFeatures = defaultFeatures;
            this.yanked = yanked;
        }
    }

    private static final class Advisory {
        final String advisoryId;
        final String crateName;
        final String severity;
        final int sevRank;
        final Range range;
        final long dayPublished;

        Advisory(
                String advisoryId,
                String crateName,
                String severity,
                int sevRank,
                Range range,
                long dayPublished) {
            this.advisoryId = advisoryId;
            this.crateName = crateName;
            this.severity = severity;
            this.sevRank = sevRank;
            this.range = range;
            this.dayPublished = dayPublished;
        }
    }

    private static final class DepDecl {
        final boolean workspace;
        final String versionRange;
        final List<String> features;
        final boolean defaultFeatures;
        final List<String> requiredFeatures;

        DepDecl(
                boolean workspace,
                String versionRange,
                List<String> features,
                boolean defaultFeatures,
                List<String> requiredFeatures) {
            this.workspace = workspace;
            this.versionRange = versionRange;
            this.features = features;
            this.defaultFeatures = defaultFeatures;
            this.requiredFeatures = requiredFeatures;
        }
    }

    private static final class Member {
        final String memberMsrv;
        final TreeMap<String, DepDecl> deps;

        Member(String memberMsrv, TreeMap<String, DepDecl> deps) {
            this.memberMsrv = memberMsrv;
            this.deps = deps;
        }
    }

    private static final class CrateDoc {
        final List<VersionInfo> versions;

        CrateDoc(List<VersionInfo> versions) {
            this.versions = versions;
        }
    }

    private static final class Event {
        final String eventId;
        final long day;
        final String kind;
        final String crateName;
        final String member;
        final String pinnedVersion;
        final String advisoryId;

        Event(
                String eventId,
                long day,
                String kind,
                String crateName,
                String member,
                String pinnedVersion,
                String advisoryId) {
            this.eventId = eventId;
            this.day = day;
            this.kind = kind;
            this.crateName = crateName;
            this.member = member;
            this.pinnedVersion = pinnedVersion;
            this.advisoryId = advisoryId;
        }
    }

    private static final class CrateDecision {
        final VersionInfo chosen;
        final List<String> dropped;
        final List<String> sharingMembers;
        final boolean forceFreeze;
        final List<String> blocking;
        final boolean freezeUnsafe;

        CrateDecision(
                VersionInfo chosen,
                List<String> dropped,
                List<String> sharingMembers,
                boolean forceFreeze,
                List<String> blocking,
                boolean freezeUnsafe) {
            this.chosen = chosen;
            this.dropped = dropped;
            this.sharingMembers = sharingMembers;
            this.forceFreeze = forceFreeze;
            this.blocking = blocking;
            this.freezeUnsafe = freezeUnsafe;
        }
    }

    private static final class SelectResult {
        final VersionInfo chosen;
        final List<String> dropped;

        SelectResult(VersionInfo chosen, List<String> dropped) {
            this.chosen = chosen;
            this.dropped = dropped;
        }
    }

    private static final class ConsumerRec {
        final String member;
        final String chosenVersion;
        final boolean inRange;
        final boolean hardConflict;

        ConsumerRec(String member, String chosenVersion, boolean inRange, boolean hardConflict) {
            this.member = member;
            this.chosenVersion = chosenVersion;
            this.inRange = inRange;
            this.hardConflict = hardConflict;
        }
    }

    private static final class PlannerCtx {
        final Ver workspaceMsrv;
        final boolean allowYankedPinned;
        final TreeMap<String, String> lock;
        final TreeMap<String, List<Advisory>> activeAdvisoriesByCrate;
        final TreeMap<String, Member> members;
        final TreeMap<String, String> workspaceDependencies;
        final Set<String> forcedBumpSet;

        PlannerCtx(
                Ver workspaceMsrv,
                boolean allowYankedPinned,
                TreeMap<String, String> lock,
                TreeMap<String, List<Advisory>> activeAdvisoriesByCrate,
                TreeMap<String, Member> members,
                TreeMap<String, String> workspaceDependencies,
                Set<String> forcedBumpSet) {
            this.workspaceMsrv = workspaceMsrv;
            this.allowYankedPinned = allowYankedPinned;
            this.lock = lock;
            this.activeAdvisoriesByCrate = activeAdvisoriesByCrate;
            this.members = members;
            this.workspaceDependencies = workspaceDependencies;
            this.forcedBumpSet = forcedBumpSet;
        }

        boolean isBlocked(String crateName, Ver v) {
            List<Advisory> adv = activeAdvisoriesByCrate.get(crateName);
            if (adv == null) {
                return false;
            }
            for (Advisory a : adv) {
                if (inRange(v, a.range)) {
                    return true;
                }
            }
            return false;
        }

        List<String> blockingActive(String crateName, Ver v) {
            List<Advisory> adv = activeAdvisoriesByCrate.get(crateName);
            if (adv == null) {
                return new ArrayList<>();
            }
            List<String> out = new ArrayList<>();
            for (Advisory a : adv) {
                if (inRange(v, a.range)) {
                    out.add(a.advisoryId);
                }
            }
            return out;
        }

        boolean eligibilityBasic(
                String crateName, VersionInfo vinfo, Range eff, Ver effectiveMsrv) {
            if (!inRange(vinfo.ver, eff)) {
                return false;
            }
            if (vinfo.msrv.compareTo(effectiveMsrv) > 0) {
                return false;
            }
            if (vinfo.yanked) {
                if (!allowYankedPinned) {
                    return false;
                }
                String locked = lock.get(crateName);
                if (locked == null || !locked.equals(vinfo.verStr)) {
                    return false;
                }
            }
            return !isBlocked(crateName, vinfo.ver);
        }

        Ver effectiveMsrvFor(String memberName, String crateName) {
            DepDecl dep = members.get(memberName).deps.get(crateName);
            if (dep.workspace) {
                return workspaceMsrv;
            }
            Ver mm = parseSemver(members.get(memberName).memberMsrv);
            return mm.compareTo(workspaceMsrv) > 0 ? mm : workspaceMsrv;
        }

        Range effectiveRangeFor(String memberName, String crateName) {
            DepDecl dep = members.get(memberName).deps.get(crateName);
            if (dep.workspace) {
                return parseRange(workspaceDependencies.get(crateName));
            }
            return parseRange(dep.versionRange);
        }

        List<String> sharingSetFor(String crateName) {
            List<String> out = new ArrayList<>();
            for (String memberName : members.keySet()) {
                DepDecl dep = members.get(memberName).deps.get(crateName);
                if (dep != null
                        && dep.workspace
                        && !forcedBumpSet.contains(memberCrateKey(memberName, crateName))) {
                    out.add(memberName);
                }
            }
            return out;
        }
    }
}
