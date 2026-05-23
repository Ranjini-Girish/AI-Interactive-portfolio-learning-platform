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
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** npm monorepo bump arbitration oracle. */
public final class NpmMonoBumpAudit {

    private static final Pattern GTE_LT =
            Pattern.compile("^>=(\\d+\\.\\d+\\.\\d+) <(\\d+\\.\\d+\\.\\d+)$");
    private static final Map<String, Integer> SEV_RANK =
            Map.of("low", 0, "medium", 1, "high", 2, "critical", 3);
    private static final Set<String> ALLOWED_KINDS =
            Set.of("force_freeze", "dist_tag_pin", "advisory_override");
    private static final Map<String, String> MITIGATION_MAP =
            Map.of(
                    "resolved_by_bump", "bump",
                    "mitigated_by_exports_drop", "exports_drop",
                    "still_open_frozen", "frozen",
                    "unmitigated_pinned", "pinned",
                    "overridden", "override");

    private NpmMonoBumpAudit() {}

    public static void main(String[] args) throws IOException {
        Path data =
                Path.of(
                        System.getenv()
                                .getOrDefault("NMB_DATA_DIR", "/app/monorepo"));
        Path out =
                Path.of(
                        System.getenv()
                                .getOrDefault("NMB_ARB_DIR", "/app/arbitration"));
        run(data, out);
    }

    private static void run(Path data, Path out) throws IOException {
        Files.createDirectories(out);

        JsonObject manifest = loadJson(data.resolve("monorepo_manifest.json"));
        JsonObject policy = loadJson(data.resolve("governance").resolve("policy.json"));
        JsonObject lockRoot = loadJson(data.resolve("current_lock.json"));
        JsonObject lock = lockRoot.getAsJsonObject("locks");
        JsonArray incidentLog =
                loadJson(data.resolve("incident_log.json")).getAsJsonArray("events");
        JsonObject pool = loadJson(data.resolve("pool_state.json"));
        JsonArray advisories =
                loadJson(data.resolve("advisories.json")).getAsJsonArray("advisories");

        int currentDay = pool.get("current_day").getAsInt();
        Range wsEngines = parseRange(policy.get("engines_node_workspace").getAsString());
        int sevThresh = SEV_RANK.get(manifest.get("severity_block_threshold").getAsString());
        boolean allowYanked = manifest.get("allow_yanked_pinned").getAsBoolean();

        TreeMap<String, JsonObject> packages = new TreeMap<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(data.resolve("packages"), "*.json")) {
            List<Path> paths = new ArrayList<>();
            for (Path p : ds) {
                paths.add(p);
            }
            paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
            for (Path p : paths) {
                JsonObject d = loadJson(p);
                packages.put(d.get("name").getAsString(), d);
            }
        }

        TreeMap<String, JsonObject> registry = new TreeMap<>();
        try (DirectoryStream<Path> ds = Files.newDirectoryStream(data.resolve("registry"), "*.json")) {
            List<Path> paths = new ArrayList<>();
            for (Path p : ds) {
                paths.add(p);
            }
            paths.sort(Comparator.comparing(p -> p.getFileName().toString()));
            for (Path p : paths) {
                JsonObject d = loadJson(p);
                registry.put(d.get("name").getAsString(), d);
            }
        }

        List<JsonObject> filtered = new ArrayList<>();
        int ignored = 0;
        for (JsonElement evEl : incidentLog) {
            JsonObject ev = evEl.getAsJsonObject();
            if (!ev.has("accepted") || !ev.get("accepted").getAsBoolean()) {
                ignored++;
                continue;
            }
            if (ev.get("day").getAsInt() > currentDay) {
                ignored++;
                continue;
            }
            if (!ALLOWED_KINDS.contains(ev.get("kind").getAsString())) {
                ignored++;
                continue;
            }
            filtered.add(ev);
        }

        Map<List<Object>, List<JsonObject>> groups = new LinkedHashMap<>();
        for (JsonObject ev : filtered) {
            groups.computeIfAbsent(scopeKey(ev), k -> new ArrayList<>()).add(ev);
        }

        Map<List<Object>, JsonObject> acceptedEvents = new LinkedHashMap<>();
        for (Map.Entry<List<Object>, List<JsonObject>> e : groups.entrySet()) {
            List<JsonObject> evs = new ArrayList<>(e.getValue());
            evs.sort(
                    Comparator.comparing((JsonObject x) -> -x.get("day").getAsInt())
                            .thenComparing(x -> x.get("event_id").getAsString()));
            acceptedEvents.put(e.getKey(), evs.get(0));
        }

        Map<String, JsonObject> forceFreezes = new HashMap<>();
        Map<String, JsonObject> distTagPins = new HashMap<>();
        Set<String> overrideIds = new HashSet<>();
        for (Map.Entry<List<Object>, JsonObject> e : acceptedEvents.entrySet()) {
            String kind = (String) e.getKey().get(0);
            String key = (String) e.getKey().get(1);
            if ("force_freeze".equals(kind)) {
                forceFreezes.put(key, e.getValue());
            } else if ("dist_tag_pin".equals(kind)) {
                distTagPins.put(key, e.getValue());
            } else {
                overrideIds.add(key);
            }
        }

        Map<String, List<JsonObject>> advsByDep = new HashMap<>();
        for (JsonElement aEl : advisories) {
            JsonObject a = aEl.getAsJsonObject();
            advsByDep.computeIfAbsent(a.get("dep").getAsString(), k -> new ArrayList<>()).add(a);
        }

        Map<String, List<String>> freezeUnsafeAgainst = new HashMap<>();
        Map<String, List<String>> blockPinAgainst = new HashMap<>();

        List<JsonObject> entries = new ArrayList<>();
        for (String pkgName : packages.keySet()) {
            JsonObject pkg = packages.get(pkgName);
            List<DepInfo> deps = collectDeps(pkg);
            deps.sort(Comparator.comparing(d -> d.name));
            for (DepInfo di : deps) {
                String dep = di.name;
                JsonObject info = di.info;
                String rngStr = info.get("range").getAsString();
                List<String> exportsUsed = jsonStringList(info.getAsJsonArray("exports_used"));
                String scope = info.get("scope").getAsString();

                JsonObject entry = new JsonObject();
                entry.addProperty("package", pkgName);
                entry.addProperty("dep", dep);
                entry.addProperty("scope", scope);
                if (lock.has(dep) && !lock.get(dep).isJsonNull()) {
                    entry.addProperty("current_version", lock.get(dep).getAsString());
                } else {
                    entry.add("current_version", JsonNull.INSTANCE);
                }
                entry.add("exports_dropped_set", new JsonArray());

                if (rngStr.startsWith("workspace:")) {
                    entry.addProperty("resolution_kind", "workspace_protocol");
                    String variantTok = rngStr.split(":", 2)[1];
                    String variant =
                            switch (variantTok) {
                                case "*" -> "star";
                                case "^" -> "caret";
                                case "~" -> "tilde";
                                default -> null;
                            };
                    if (variant == null) {
                        entry.add("protocol_variant", JsonNull.INSTANCE);
                    } else {
                        entry.addProperty("protocol_variant", variant);
                    }
                    entry.addProperty("source", "planner");
                    if (packages.containsKey(dep)) {
                        String chosen = packages.get(dep).get("version").getAsString();
                        entry.addProperty("chosen_version", chosen);
                        String cv =
                                entry.has("current_version") && !entry.get("current_version").isJsonNull()
                                        ? entry.get("current_version").getAsString()
                                        : null;
                        if (cv == null) {
                            entry.addProperty("action", "hold");
                        } else if (parseVersion(chosen).compareTo(parseVersion(cv)) > 0) {
                            entry.addProperty("action", "bump");
                        } else if (parseVersion(chosen).compareTo(parseVersion(cv)) < 0) {
                            entry.addProperty("action", "downgrade");
                        } else {
                            entry.addProperty("action", "hold");
                        }
                        entry.addProperty("reason", "satisfied");
                    } else {
                        entry.add("chosen_version", JsonNull.INSTANCE);
                        entry.addProperty("action", "block_no_workspace_target");
                        entry.addProperty("reason", "no_workspace_target");
                    }
                    entries.add(entry);
                    continue;
                }

                entry.addProperty("resolution_kind", "registry");
                entry.add("protocol_variant", JsonNull.INSTANCE);

                if (forceFreezes.containsKey(dep)) {
                    entry.addProperty("source", "incident_log_force_freeze");
                    String locked = lock.has(dep) ? lock.get(dep).getAsString() : null;
                    JsonObject reg = registry.getOrDefault(dep, new JsonObject());
                    JsonObject vInfo = findVersion(reg, locked);
                    if (locked == null || vInfo == null) {
                        entry.add("chosen_version", JsonNull.INSTANCE);
                        entry.addProperty("action", "block_no_eligible_version");
                        entry.addProperty("reason", "no_eligible_version");
                        entries.add(entry);
                        continue;
                    }
                    entry.addProperty("chosen_version", locked);
                    boolean yankOk = !vInfo.get("yanked").getAsBoolean() || allowYanked;
                    List<String> blockers = advBlockersForVersion(dep, parseVersion(locked), advsByDep, overrideIds, sevThresh);
                    if (!yankOk || !blockers.isEmpty()) {
                        entry.addProperty("action", "freeze_unsafe");
                        entry.addProperty("reason", "freeze_advisory_conflict");
                        for (String b : blockers) {
                            freezeUnsafeAgainst.computeIfAbsent(b, k -> new ArrayList<>())
                                    .add(pkgName + "\0" + dep);
                        }
                    } else {
                        entry.addProperty("action", "freeze");
                        entry.addProperty("reason", "satisfied");
                    }
                    entries.add(entry);
                    continue;
                }

                if (distTagPins.containsKey(dep)) {
                    entry.addProperty("source", "incident_log_dist_tag_pin");
                    JsonObject ev = distTagPins.get(dep);
                    JsonObject reg = registry.getOrDefault(dep, new JsonObject());
                    String distTag = ev.get("dist_tag").getAsString();
                    String target = null;
                    if (reg.has("dist_tags") && reg.getAsJsonObject("dist_tags").has(distTag)) {
                        target = reg.getAsJsonObject("dist_tags").get(distTag).getAsString();
                    }
                    JsonObject vInfo = findVersion(reg, target);
                    if (target == null || vInfo == null) {
                        entry.add("chosen_version", JsonNull.INSTANCE);
                        entry.addProperty("action", "block_dist_tag_unsafe");
                        entry.addProperty("reason", "dist_tag_unsafe");
                        entries.add(entry);
                        continue;
                    }
                    Ver tVer = parseVersion(target);
                    boolean enginesOk =
                            rangeSuperset(parseRange(vInfo.get("engines_node").getAsString()), wsEngines);
                    boolean yankedOk =
                            !vInfo.get("yanked").getAsBoolean()
                                    || (allowYanked
                                            && target.equals(
                                                    lock.has(dep) ? lock.get(dep).getAsString() : null));
                    List<String> blockers = advBlockersForVersion(dep, tVer, advsByDep, overrideIds, sevThresh);
                    if (!(enginesOk && yankedOk && blockers.isEmpty())) {
                        entry.add("chosen_version", JsonNull.INSTANCE);
                        entry.addProperty("action", "block_dist_tag_unsafe");
                        entry.addProperty("reason", "dist_tag_unsafe");
                        for (String b : blockers) {
                            blockPinAgainst.computeIfAbsent(b, k -> new ArrayList<>())
                                    .add(pkgName + "\0" + dep);
                        }
                    } else {
                        entry.addProperty("chosen_version", target);
                        entry.addProperty("action", "dist_tag_pin");
                        entry.addProperty("reason", "satisfied");
                    }
                    entries.add(entry);
                    continue;
                }

                entry.addProperty("source", "planner");
                Range entryRng = parseRange(rngStr);
                List<JsonObject> elig = eligibleVersions(dep, entryRng, registry, wsEngines, lock, allowYanked, advsByDep, overrideIds, sevThresh);
                if (elig.isEmpty()) {
                    entry.add("chosen_version", JsonNull.INSTANCE);
                    entry.addProperty("action", "block_no_eligible_version");
                    entry.addProperty("reason", "no_eligible_version");
                    entries.add(entry);
                    continue;
                }
                elig.sort(
                        (a, b) ->
                                parseVersion(b.get("version").getAsString())
                                        .compareTo(parseVersion(a.get("version").getAsString())));
                JsonObject vMax = elig.get(0);
                JsonObject chosen = null;
                List<String> dropped = new ArrayList<>();
                if (supportsAll(vMax, exportsUsed)) {
                    chosen = vMax;
                } else {
                    for (JsonObject v : elig) {
                        if (supportsAll(v, exportsUsed)) {
                            chosen = v;
                            break;
                        }
                    }
                    if (chosen == null) {
                        List<String> conds = jsonStringList(vMax.getAsJsonArray("exports_conditions"));
                        List<String> dropPool = new ArrayList<>();
                        for (String c : exportsUsed) {
                            if (!conds.contains(c)) {
                                dropPool.add(c);
                            }
                        }
                        dropPool.sort(String::compareTo);
                        for (String c : dropPool) {
                            dropped.add(c);
                            List<String> remaining = new ArrayList<>();
                            for (String x : exportsUsed) {
                                if (!dropped.contains(x)) {
                                    remaining.add(x);
                                }
                            }
                            for (JsonObject v : elig) {
                                if (supportsAll(v, remaining)) {
                                    chosen = v;
                                    break;
                                }
                            }
                            if (chosen != null) {
                                break;
                            }
                        }
                        if (chosen == null) {
                            chosen = vMax;
                            dropped = new ArrayList<>(exportsUsed);
                            dropped.sort(String::compareTo);
                        }
                    }
                }
                entry.addProperty("chosen_version", chosen.get("version").getAsString());
                JsonArray droppedArr = new JsonArray();
                List<String> droppedSorted = new ArrayList<>(dropped);
                droppedSorted.sort(String::compareTo);
                for (String d : droppedSorted) {
                    droppedArr.add(d);
                }
                entry.add("exports_dropped_set", droppedArr);
                String cv =
                        entry.has("current_version") && !entry.get("current_version").isJsonNull()
                                ? entry.get("current_version").getAsString()
                                : null;
                String chosenVer = chosen.get("version").getAsString();
                if (cv == null || chosenVer.equals(cv)) {
                    entry.addProperty("action", "hold");
                } else if (parseVersion(chosenVer).compareTo(parseVersion(cv)) > 0) {
                    entry.addProperty("action", "bump");
                } else {
                    entry.addProperty("action", "downgrade");
                }
                entry.addProperty("reason", dropped.isEmpty() ? "satisfied" : "exports_downgrade");
                entries.add(entry);
            }
        }

        entries.sort(
                Comparator.comparing((JsonObject e) -> e.get("package").getAsString())
                        .thenComparing(e -> e.get("dep").getAsString()));

        JsonObject bumpOut = new JsonObject();
        JsonArray entriesArr = new JsonArray();
        for (JsonObject e : entries) {
            entriesArr.add(e);
        }
        bumpOut.add("entries", entriesArr);
        writeJson(out.resolve("bump_decisions.json"), bumpOut);

        Map<String, List<ConsumerRec>> peerBuckets = new TreeMap<>();
        for (JsonObject e : entries) {
            if (e.get("chosen_version").isJsonNull()) {
                continue;
            }
            if (!"registry".equals(e.get("resolution_kind").getAsString())) {
                continue;
            }
            String dep = e.get("dep").getAsString();
            String chosen = e.get("chosen_version").getAsString();
            JsonObject reg = registry.get(dep);
            if (reg == null) {
                continue;
            }
            JsonObject vInfo = findVersion(reg, chosen);
            if (vInfo == null) {
                continue;
            }
            if (!vInfo.has("peer_constraints")) {
                continue;
            }
            JsonObject peers = vInfo.getAsJsonObject("peer_constraints");
            for (Map.Entry<String, JsonElement> pe : peers.entrySet()) {
                String peerName = pe.getKey();
                ConsumerRec rec =
                        new ConsumerRec(
                                pe.getValue().getAsString(),
                                e.get("package").getAsString() + "::" + e.get("dep").getAsString(),
                                e.get("package").getAsString());
                peerBuckets.computeIfAbsent(peerName, k -> new ArrayList<>()).add(rec);
            }
        }

        List<JsonObject> peerLinks = new ArrayList<>();
        for (String peerName : peerBuckets.keySet()) {
            List<ConsumerRec> consumers = new ArrayList<>(peerBuckets.get(peerName));
            consumers.sort(
                    Comparator.comparing((ConsumerRec c) -> c.packageName)
                            .thenComparing(c -> c.depChain));
            Range intersection = null;
            for (ConsumerRec c : consumers) {
                Range rng = parseRange(c.declaredRange);
                if (intersection == null) {
                    intersection = rng;
                } else {
                    intersection = rangeIntersection(intersection, rng);
                }
                if (intersection == null) {
                    break;
                }
            }
            String resolved = resolvePeer(peerName, entries);
            String status;
            String intersectionStr;
            if (intersection == null) {
                status = "unsatisfiable_intersection";
                intersectionStr = null;
            } else if (resolved == null) {
                status = "peer_unresolved";
                intersectionStr = rangeToStr(intersection);
            } else if (versionInRange(parseVersion(resolved), intersection)) {
                status = "satisfied";
                intersectionStr = rangeToStr(intersection);
            } else {
                status = "outside_intersection";
                intersectionStr = rangeToStr(intersection);
            }
            JsonObject link = new JsonObject();
            JsonArray consumersArr = new JsonArray();
            for (ConsumerRec c : consumers) {
                JsonObject row = new JsonObject();
                row.addProperty("declared_range", c.declaredRange);
                row.addProperty("dep_chain", c.depChain);
                row.addProperty("package", c.packageName);
                consumersArr.add(row);
            }
            link.add("consumers", consumersArr);
            if (intersectionStr == null) {
                link.add("intersection_range", JsonNull.INSTANCE);
            } else {
                link.addProperty("intersection_range", intersectionStr);
            }
            link.addProperty("peer_name", peerName);
            link.addProperty("peer_status", status);
            if (resolved == null) {
                link.add("resolved_peer_version", JsonNull.INSTANCE);
            } else {
                link.addProperty("resolved_peer_version", resolved);
            }
            peerLinks.add(link);
        }

        JsonObject peerOut = new JsonObject();
        JsonArray peerArr = new JsonArray();
        for (JsonObject p : peerLinks) {
            peerArr.add(p);
        }
        peerOut.add("peer_links", peerArr);
        writeJson(out.resolve("peer_satisfaction_report.json"), peerOut);

        List<JsonObject> engPkgs = new ArrayList<>();
        for (String pkgName : packages.keySet()) {
            JsonObject pkg = packages.get(pkgName);
            Range pe = parseRange(pkg.get("engines_node").getAsString());
            boolean loViolated = pe.lo.compareTo(wsEngines.lo) < 0;
            boolean upViolated = pe.hi.compareTo(wsEngines.hi) > 0;
            String engStatus;
            if (loViolated && upViolated) {
                engStatus = "both_violated";
            } else if (loViolated) {
                engStatus = "lower_violated";
            } else if (upViolated) {
                engStatus = "upper_violated";
            } else {
                engStatus = "subrange";
            }
            Ver loEx = loViolated ? componentwiseDiff(wsEngines.lo, pe.lo) : new Ver(0, 0, 0);
            Ver upEx = upViolated ? componentwiseDiff(pe.hi, wsEngines.hi) : new Ver(0, 0, 0);
            JsonObject row = new JsonObject();
            row.addProperty("engines_blocked_versions_count", enginesBlockedCount(pkg, registry, lock, allowYanked, wsEngines, advsByDep, overrideIds, sevThresh));
            row.addProperty("lower_exceeded_by", fmtVersion(loEx));
            row.addProperty("package", pkgName);
            row.addProperty("package_engines_lower", fmtVersion(pe.lo));
            row.addProperty("package_engines_status", engStatus);
            row.addProperty("package_engines_upper", fmtVersion(pe.hi));
            row.addProperty("upper_exceeded_by", fmtVersion(upEx));
            engPkgs.add(row);
        }

        JsonObject enginesOut = new JsonObject();
        enginesOut.addProperty("engines_node_workspace_lower", fmtVersion(wsEngines.lo));
        enginesOut.addProperty("engines_node_workspace_upper", fmtVersion(wsEngines.hi));
        JsonArray engArr = new JsonArray();
        for (JsonObject p : engPkgs) {
            engArr.add(p);
        }
        enginesOut.add("packages", engArr);
        writeJson(out.resolve("engines_compatibility.json"), enginesOut);

        Set<String> freezeUnsafeSet = freezeUnsafeAgainst.keySet();
        Set<String> blockPinSet = blockPinAgainst.keySet();

        List<JsonObject> advisoryRows = new ArrayList<>();
        List<JsonObject> advSorted = new ArrayList<>();
        for (JsonElement aEl : advisories) {
            advSorted.add(aEl.getAsJsonObject());
        }
        advSorted.sort(Comparator.comparing(a -> a.get("advisory_id").getAsString()));

        for (JsonObject adv : advSorted) {
            String aid = adv.get("advisory_id").getAsString();
            String dep = adv.get("dep").getAsString();
            String sev = adv.get("severity").getAsString();
            Range vulnRng = parseRange(adv.get("vulnerable_range").getAsString());
            Range patchedRng = parseRange(adv.get("patched_range").getAsString());
            String status;
            if (overrideIds.contains(aid)) {
                status = "overridden";
            } else if (SEV_RANK.get(sev) < sevThresh) {
                status = "inactive_low_severity";
            } else if (freezeUnsafeSet.contains(aid)) {
                status = "still_open_frozen";
            } else if (blockPinSet.contains(aid)) {
                status = "unmitigated_pinned";
            } else {
                List<JsonObject> consuming = new ArrayList<>();
                for (JsonObject e : entries) {
                    if (dep.equals(e.get("dep").getAsString())) {
                        consuming.add(e);
                    }
                }
                boolean mitigated = false;
                for (JsonObject e : consuming) {
                    if (e.get("chosen_version").isJsonNull()) {
                        continue;
                    }
                    JsonArray droppedSet = e.getAsJsonArray("exports_dropped_set");
                    if (droppedSet.isEmpty()) {
                        continue;
                    }
                    Ver ct = parseVersion(e.get("chosen_version").getAsString());
                    if (!versionInRange(ct, vulnRng) && versionInRange(ct, patchedRng)) {
                        mitigated = true;
                        break;
                    }
                }
                if (mitigated) {
                    status = "mitigated_by_exports_drop";
                } else {
                    boolean allOk =
                            !consuming.isEmpty()
                                    && consuming.stream()
                                            .allMatch(
                                                    e -> {
                                                        if (e.get("chosen_version").isJsonNull()) {
                                                            return false;
                                                        }
                                                        Ver cv =
                                                                parseVersion(
                                                                        e.get("chosen_version")
                                                                                .getAsString());
                                                        return !versionInRange(cv, vulnRng)
                                                                && versionInRange(cv, patchedRng);
                                                    });
                    status = allOk ? "resolved_by_bump" : "still_open";
                }
            }

            Set<String> patchedVs = new HashSet<>();
            for (JsonObject e : entries) {
                if (!dep.equals(e.get("dep").getAsString()) || e.get("chosen_version").isJsonNull()) {
                    continue;
                }
                Ver cv = parseVersion(e.get("chosen_version").getAsString());
                if (versionInRange(cv, patchedRng)) {
                    patchedVs.add(e.get("chosen_version").getAsString());
                }
            }
            List<String> patchedVersions = new ArrayList<>(patchedVs);
            patchedVersions.sort(Comparator.comparing(NpmMonoBumpAudit::parseVersion));

            JsonObject row = new JsonObject();
            row.addProperty("advisory_id", aid);
            row.addProperty("day_published", adv.get("day_published").getAsInt());
            row.addProperty("dep", dep);
            String mitMethod = MITIGATION_MAP.get(status);
            if (mitMethod == null) {
                row.add("mitigation_method", JsonNull.INSTANCE);
            } else {
                row.addProperty("mitigation_method", mitMethod);
            }
            JsonArray pvArr = new JsonArray();
            for (String v : patchedVersions) {
                pvArr.add(v);
            }
            row.add("patched_versions", pvArr);
            row.addProperty("severity", sev);
            row.addProperty("status", status);
            advisoryRows.add(row);
        }

        JsonObject advOut = new JsonObject();
        JsonArray advArr = new JsonArray();
        for (JsonObject a : advisoryRows) {
            advArr.add(a);
        }
        advOut.add("advisories", advArr);
        writeJson(out.resolve("advisory_status.json"), advOut);

        TreeMap<String, Integer> actionCounts = new TreeMap<>();
        TreeMap<String, Integer> resolutionKindCounts = new TreeMap<>();
        for (JsonObject e : entries) {
            actionCounts.merge(e.get("action").getAsString(), 1, Integer::sum);
            resolutionKindCounts.merge(e.get("resolution_kind").getAsString(), 1, Integer::sum);
        }
        TreeMap<String, Integer> peerStatusCounts = new TreeMap<>();
        for (JsonObject p : peerLinks) {
            peerStatusCounts.merge(p.get("peer_status").getAsString(), 1, Integer::sum);
        }
        TreeMap<String, Integer> advisoryCounts = new TreeMap<>();
        for (JsonObject a : advisoryRows) {
            advisoryCounts.merge(a.get("status").getAsString(), 1, Integer::sum);
        }

        Set<String> driftDeps = new HashSet<>();
        for (JsonObject e : entries) {
            if (e.get("chosen_version").isJsonNull()) {
                continue;
            }
            String dep = e.get("dep").getAsString();
            String lv = lock.has(dep) ? lock.get(dep).getAsString() : null;
            String chosen = e.get("chosen_version").getAsString();
            if (lv == null || !chosen.equals(lv)) {
                driftDeps.add(dep);
            }
        }

        int enginesBlockedTotal = 0;
        for (JsonObject p : engPkgs) {
            enginesBlockedTotal += p.get("engines_blocked_versions_count").getAsInt();
        }

        JsonObject summary = new JsonObject();
        summary.add("action_counts", intMapToJson(actionCounts));
        summary.add("advisory_counts", intMapToJson(advisoryCounts));
        summary.addProperty("engines_blocked_versions_total", enginesBlockedTotal);
        summary.addProperty("engines_node_workspace_lower", fmtVersion(wsEngines.lo));
        summary.addProperty("engines_node_workspace_upper", fmtVersion(wsEngines.hi));
        summary.addProperty("ignored_incident_events", ignored);
        summary.addProperty("lockfile_drift_count", driftDeps.size());
        summary.add("peer_status_counts", intMapToJson(peerStatusCounts));
        summary.add("resolution_kind_counts", intMapToJson(resolutionKindCounts));
        summary.addProperty("total_entries", entries.size());
        summary.addProperty("total_external_deps", registry.size());
        summary.addProperty("total_packages", packages.size());
        writeJson(out.resolve("summary.json"), summary);
    }

    private static JsonObject intMapToJson(TreeMap<String, Integer> m) {
        JsonObject o = new JsonObject();
        for (Map.Entry<String, Integer> e : m.entrySet()) {
            o.addProperty(e.getKey(), e.getValue());
        }
        return o;
    }

    private static List<Object> scopeKey(JsonObject ev) {
        String k = ev.get("kind").getAsString();
        if ("force_freeze".equals(k) || "dist_tag_pin".equals(k)) {
            return Arrays.asList(k, ev.get("dep").getAsString());
        }
        return Arrays.asList(k, ev.get("advisory_id").getAsString());
    }

    private static boolean advActive(JsonObject adv, Set<String> overrideIds, int sevThresh) {
        if (overrideIds.contains(adv.get("advisory_id").getAsString())) {
            return false;
        }
        return SEV_RANK.get(adv.get("severity").getAsString()) >= sevThresh;
    }

    private static List<String> advBlockersForVersion(
            String dep,
            Ver vTuple,
            Map<String, List<JsonObject>> advsByDep,
            Set<String> overrideIds,
            int sevThresh) {
        List<String> blockers = new ArrayList<>();
        for (JsonObject adv : advsByDep.getOrDefault(dep, List.of())) {
            if (!advActive(adv, overrideIds, sevThresh)) {
                continue;
            }
            if (versionInRange(vTuple, parseRange(adv.get("vulnerable_range").getAsString()))) {
                blockers.add(adv.get("advisory_id").getAsString());
            }
        }
        return blockers;
    }

    private static List<JsonObject> eligibleVersions(
            String dep,
            Range rng,
            Map<String, JsonObject> registry,
            Range wsEngines,
            JsonObject lock,
            boolean allowYanked,
            Map<String, List<JsonObject>> advsByDep,
            Set<String> overrideIds,
            int sevThresh) {
        List<JsonObject> out = new ArrayList<>();
        JsonObject reg = registry.get(dep);
        if (reg == null) {
            return out;
        }
        for (JsonElement vEl : reg.getAsJsonArray("versions")) {
            JsonObject v = vEl.getAsJsonObject();
            Ver vT = parseVersion(v.get("version").getAsString());
            if (!versionInRange(vT, rng)) {
                continue;
            }
            if (!rangeSuperset(parseRange(v.get("engines_node").getAsString()), wsEngines)) {
                continue;
            }
            if (v.get("yanked").getAsBoolean()) {
                if (!(allowYanked
                        && lock.has(dep)
                        && v.get("version").getAsString().equals(lock.get(dep).getAsString()))) {
                    continue;
                }
            }
            if (!advBlockersForVersion(dep, vT, advsByDep, overrideIds, sevThresh).isEmpty()) {
                continue;
            }
            out.add(v);
        }
        return out;
    }

    private static int enginesBlockedCount(
            JsonObject pkg,
            Map<String, JsonObject> registry,
            JsonObject lock,
            boolean allowYanked,
            Range wsEngines,
            Map<String, List<JsonObject>> advsByDep,
            Set<String> overrideIds,
            int sevThresh) {
        Set<String> seen = new HashSet<>();
        for (DepInfo di : collectDeps(pkg)) {
            String dep = di.name;
            String rngStr = di.info.get("range").getAsString();
            if (rngStr.startsWith("workspace:")) {
                continue;
            }
            if (!registry.containsKey(dep)) {
                continue;
            }
            Range rng = parseRange(rngStr);
            for (JsonElement vEl : registry.get(dep).getAsJsonArray("versions")) {
                JsonObject v = vEl.getAsJsonObject();
                Ver vT = parseVersion(v.get("version").getAsString());
                if (!versionInRange(vT, rng)) {
                    continue;
                }
                if (v.get("yanked").getAsBoolean()) {
                    if (!(allowYanked
                            && lock.has(dep)
                            && v.get("version").getAsString().equals(lock.get(dep).getAsString()))) {
                        continue;
                    }
                }
                if (!advBlockersForVersion(dep, vT, advsByDep, overrideIds, sevThresh).isEmpty()) {
                    continue;
                }
                if (!rangeSuperset(parseRange(v.get("engines_node").getAsString()), wsEngines)) {
                    seen.add(dep + "\0" + v.get("version").getAsString());
                }
            }
        }
        return seen.size();
    }

    private static String resolvePeer(String peerName, List<JsonObject> entries) {
        List<Ver> cands = new ArrayList<>();
        for (JsonObject e : entries) {
            if (!peerName.equals(e.get("dep").getAsString())) {
                continue;
            }
            if (e.get("chosen_version").isJsonNull()) {
                continue;
            }
            cands.add(parseVersion(e.get("chosen_version").getAsString()));
        }
        if (cands.isEmpty()) {
            return null;
        }
        Ver max = cands.get(0);
        for (Ver v : cands) {
            if (v.compareTo(max) > 0) {
                max = v;
            }
        }
        return fmtVersion(max);
    }

    private static List<DepInfo> collectDeps(JsonObject pkg) {
        List<DepInfo> items = new ArrayList<>();
        if (pkg.has("dependencies")) {
            for (Map.Entry<String, JsonElement> e : pkg.getAsJsonObject("dependencies").entrySet()) {
                items.add(new DepInfo(e.getKey(), e.getValue().getAsJsonObject()));
            }
        }
        if (pkg.has("dev_dependencies")) {
            for (Map.Entry<String, JsonElement> e :
                    pkg.getAsJsonObject("dev_dependencies").entrySet()) {
                items.add(new DepInfo(e.getKey(), e.getValue().getAsJsonObject()));
            }
        }
        return items;
    }

    private static boolean supportsAll(JsonObject vInfo, List<String> conditions) {
        List<String> conds = jsonStringList(vInfo.getAsJsonArray("exports_conditions"));
        for (String c : conditions) {
            if (!conds.contains(c)) {
                return false;
            }
        }
        return true;
    }

    private static JsonObject findVersion(JsonObject reg, String version) {
        if (version == null || !reg.has("versions")) {
            return null;
        }
        for (JsonElement vEl : reg.getAsJsonArray("versions")) {
            JsonObject v = vEl.getAsJsonObject();
            if (version.equals(v.get("version").getAsString())) {
                return v;
            }
        }
        return null;
    }

    private static List<String> jsonStringList(JsonArray arr) {
        List<String> out = new ArrayList<>();
        for (JsonElement el : arr) {
            out.add(el.getAsString());
        }
        return out;
    }

    private static Ver parseVersion(String s) {
        String[] parts = s.split("\\.");
        return new Ver(Integer.parseInt(parts[0]), Integer.parseInt(parts[1]), Integer.parseInt(parts[2]));
    }

    private static String fmtVersion(Ver v) {
        return v.maj + "." + v.min + "." + v.patch;
    }

    private static Range parseRange(String s) {
        s = s.strip();
        if (s.startsWith("^")) {
            Ver v = parseVersion(s.substring(1));
            if (v.maj >= 1) {
                return new Range(v, new Ver(v.maj + 1, 0, 0));
            }
            if (v.min > 0) {
                return new Range(v, new Ver(0, v.min + 1, 0));
            }
            return new Range(v, new Ver(0, 0, v.patch + 1));
        }
        if (s.startsWith("~")) {
            Ver v = parseVersion(s.substring(1));
            return new Range(v, new Ver(v.maj, v.min + 1, 0));
        }
        if (s.startsWith(">=")) {
            Matcher m = GTE_LT.matcher(s);
            if (!m.matches()) {
                throw new IllegalArgumentException("invalid range " + s);
            }
            return new Range(parseVersion(m.group(1)), parseVersion(m.group(2)));
        }
        Ver v = parseVersion(s);
        return new Range(v, new Ver(v.maj, v.min, v.patch + 1));
    }

    private static boolean versionInRange(Ver v, Range rng) {
        return v.compareTo(rng.lo) >= 0 && v.compareTo(rng.hi) < 0;
    }

    private static boolean rangeSuperset(Range outer, Range inner) {
        return outer.lo.compareTo(inner.lo) <= 0 && outer.hi.compareTo(inner.hi) >= 0;
    }

    private static Range rangeIntersection(Range a, Range b) {
        Ver lo = maxVer(a.lo, b.lo);
        Ver hi = minVer(a.hi, b.hi);
        if (lo.compareTo(hi) >= 0) {
            return null;
        }
        return new Range(lo, hi);
    }

    private static Ver maxVer(Ver a, Ver b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    private static Ver minVer(Ver a, Ver b) {
        return a.compareTo(b) <= 0 ? a : b;
    }

    private static String rangeToStr(Range rng) {
        return ">=" + fmtVersion(rng.lo) + " <" + fmtVersion(rng.hi);
    }

    private static Ver componentwiseDiff(Ver a, Ver b) {
        return new Ver(
                Math.max(a.maj - b.maj, 0),
                Math.max(a.min - b.min, 0),
                Math.max(a.patch - b.patch, 0));
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
    }

    private static final class Range {
        final Ver lo;
        final Ver hi;

        Range(Ver lo, Ver hi) {
            this.lo = lo;
            this.hi = hi;
        }
    }

    private static final class DepInfo {
        final String name;
        final JsonObject info;

        DepInfo(String name, JsonObject info) {
            this.name = name;
            this.info = info;
        }
    }

    private static final class ConsumerRec {
        final String declaredRange;
        final String depChain;
        final String packageName;

        ConsumerRec(String declaredRange, String depChain, String packageName) {
            this.declaredRange = declaredRange;
            this.depChain = depChain;
            this.packageName = packageName;
        }
    }
}
