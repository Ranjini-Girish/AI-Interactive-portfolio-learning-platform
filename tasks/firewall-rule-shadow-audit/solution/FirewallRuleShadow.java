import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

/** Firewall rule shadow audit oracle. */
public final class FirewallRuleShadow {
    private FirewallRuleShadow() {}

    @SuppressWarnings("unchecked")
    private static Map<String, Object> ruleFromJson(JsonObject r) {
        return new Gson().fromJson(r, Map.class);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> flowFromJson(JsonObject f) {
        return new Gson().fromJson(f, Map.class);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> policyFromJson(JsonObject p) {
        return new Gson().fromJson(p, Map.class);
    }

    private static long parseIpv4(String ip) {
        String[] parts = ip.split("\\.");
        if (parts.length != 4) {
            return -1;
        }
        long v = 0;
        try {
            for (String part : parts) {
                int o = Integer.parseInt(part);
                if (o < 0 || o > 255) {
                    return -1;
                }
                v = (v << 8) | o;
            }
        } catch (NumberFormatException e) {
            return -1;
        }
        return v;
    }

    private static String formatIpv4(long ip) {
        return ((ip >> 24) & 255)
                + "."
                + ((ip >> 16) & 255)
                + "."
                + ((ip >> 8) & 255)
                + "."
                + (ip & 255);
    }

    private static String normalizeCidr(String value) {
        if ("any".equals(value)) {
            return "any";
        }
        try {
            int slash = value.indexOf('/');
            if (slash < 0) {
                return null;
            }
            int prefix = Integer.parseInt(value.substring(slash + 1));
            if (prefix < 0 || prefix > 32) {
                return null;
            }
            long ip = parseIpv4(value.substring(0, slash));
            if (ip < 0) {
                return null;
            }
            long mask =
                    prefix == 0 ? 0 : (0xFFFFFFFFL << (32 - prefix)) & 0xFFFFFFFFL;
            long net = ip & mask;
            return formatIpv4(net) + "/" + prefix;
        } catch (Exception e) {
            return null;
        }
    }

    private static boolean cidrContains(String ruleCidr, String ipStr) {
        if ("any".equals(ruleCidr)) {
            return true;
        }
        long addr = parseIpv4(ipStr);
        if (addr < 0) {
            return false;
        }
        int slash = ruleCidr.indexOf('/');
        if (slash < 0) {
            return false;
        }
        try {
            int prefix = Integer.parseInt(ruleCidr.substring(slash + 1));
            long net = parseIpv4(ruleCidr.substring(0, slash));
            if (net < 0) {
                return false;
            }
            long mask =
                    prefix == 0 ? 0 : (0xFFFFFFFFL << (32 - prefix)) & 0xFFFFFFFFL;
            return (addr & mask) == (net & mask);
        } catch (Exception e) {
            return false;
        }
    }

    @SuppressWarnings("unchecked")
    private static boolean portInRanges(Object portSpec, int port) {
        if ("any".equals(portSpec)) {
            return true;
        }
        if (!(portSpec instanceof List<?> list) || list.isEmpty()) {
            return false;
        }
        for (Object entry : list) {
            if (!(entry instanceof Map<?, ?> m)) {
                continue;
            }
            Object start = m.get("start");
            Object end = m.get("end");
            if (start instanceof Number s && end instanceof Number e) {
                int st = s.intValue();
                int en = e.intValue();
                if (st > en) {
                    continue;
                }
                if (st <= port && port <= en) {
                    return true;
                }
            }
        }
        return false;
    }

    private static boolean predicateIsUnsatisfiable(Map<String, Object> rule) {
        if (normalizeCidr((String) rule.get("source")) == null) {
            return true;
        }
        if (normalizeCidr((String) rule.get("destination")) == null) {
            return true;
        }
        for (String key : List.of("src_ports", "dst_ports")) {
            Object spec = rule.get(key);
            if ("any".equals(spec)) {
                continue;
            }
            if (!(spec instanceof List<?> list) || list.isEmpty()) {
                return true;
            }
            boolean valid = false;
            for (Object entry : list) {
                if (entry instanceof Map<?, ?> m) {
                    Object start = m.get("start");
                    Object end = m.get("end");
                    if (start instanceof Number s && end instanceof Number e) {
                        if (s.intValue() <= e.intValue()) {
                            valid = true;
                            break;
                        }
                    }
                }
            }
            if (!valid) {
                return true;
            }
        }
        return false;
    }

    private static boolean ruleMatchesFlow(
            Map<String, Object> rule, Map<String, Object> flow, Map<String, Object> policy) {
        if (predicateIsUnsatisfiable(rule)) {
            return false;
        }
        if (Boolean.TRUE.equals(policy.get("enable_directionality"))) {
            if (!rule.get("direction").equals(flow.get("direction"))) {
                return false;
            }
        }
        String srcCidr = normalizeCidr((String) rule.get("source"));
        String dstCidr = normalizeCidr((String) rule.get("destination"));
        if (srcCidr == null || dstCidr == null) {
            return false;
        }
        if (!cidrContains(srcCidr, (String) flow.get("src_ip"))) {
            return false;
        }
        if (!cidrContains(dstCidr, (String) flow.get("dst_ip"))) {
            return false;
        }
        if (!"any".equals(rule.get("protocol"))
                && !rule.get("protocol").equals(flow.get("protocol"))) {
            return false;
        }
        String proto = (String) flow.get("protocol");
        if ("tcp".equals(proto) || "udp".equals(proto)) {
            if (!portInRanges(rule.get("src_ports"), ((Number) flow.get("src_port")).intValue())) {
                return false;
            }
            if (!portInRanges(rule.get("dst_ports"), ((Number) flow.get("dst_port")).intValue())) {
                return false;
            }
        }
        return true;
    }

    private static List<Map<String, Object>> evaluationOrder(
            List<Map<String, Object>> rules, Map<String, Object> policy) {
        String tb = (String) policy.get("tie_breaker");
        List<Map<String, Object>> copy = new ArrayList<>(rules);
        if ("priority_then_id".equals(tb)) {
            copy.sort(
                    Comparator.<Map<String, Object>>comparingInt(
                                    r -> -((Number) r.get("priority")).intValue())
                            .thenComparing(r -> (String) r.get("id")));
        } else if ("priority_lowest_wins".equals(tb)) {
            copy.sort(
                    Comparator.<Map<String, Object>>comparingInt(
                                    r -> ((Number) r.get("priority")).intValue())
                            .thenComparing(r -> (String) r.get("id")));
        } else if ("id_only".equals(tb)) {
            copy.sort(Comparator.comparing(r -> (String) r.get("id")));
        } else {
            throw new IllegalArgumentException("unknown tie_breaker: " + tb);
        }
        return copy;
    }

    private static Map<String, Object> evaluateFlow(
            Map<String, Object> flow,
            List<Map<String, Object>> orderedRules,
            Map<String, Object> policy) {
        List<String> evaluated = new ArrayList<>();
        for (Map<String, Object> rule : orderedRules) {
            evaluated.add((String) rule.get("id"));
            if (ruleMatchesFlow(rule, flow, policy)) {
                Map<String, Object> out = new TreeMap<>();
                out.put("evaluated_rule_ids", new ArrayList<>(evaluated));
                out.put("id", flow.get("id"));
                out.put("matched_rule_id", rule.get("id"));
                out.put("verdict", rule.get("action"));
                return out;
            }
        }
        Map<String, Object> out = new TreeMap<>();
        out.put("evaluated_rule_ids", evaluated);
        out.put("id", flow.get("id"));
        out.put("matched_rule_id", null);
        out.put("verdict", "default");
        return out;
    }

    private static List<String> matchedFlowIds(
            Map<String, Object> rule, List<Map<String, Object>> flows, Map<String, Object> policy) {
        List<String> ids = new ArrayList<>();
        for (Map<String, Object> f : flows) {
            if (ruleMatchesFlow(rule, f, policy)) {
                ids.add((String) f.get("id"));
            }
        }
        ids.sort(String::compareTo);
        return ids;
    }

    private static List<List<String>> combinations(List<String> sorted, int k) {
        List<List<String>> out = new ArrayList<>();
        combine(sorted, k, 0, new ArrayList<>(), out);
        return out;
    }

    private static void combine(
            List<String> sorted,
            int k,
            int start,
            List<String> cur,
            List<List<String>> out) {
        if (cur.size() == k) {
            out.add(new ArrayList<>(cur));
            return;
        }
        for (int i = start; i < sorted.size(); i++) {
            cur.add(sorted.get(i));
            combine(sorted, k, i + 1, cur, out);
            cur.remove(cur.size() - 1);
        }
    }

    private static List<String> lexSmallestMinCover(
            List<String> target,
            List<String> candidateIds,
            Map<String, Set<String>> candidateSets) {
        Set<String> targetSet = new HashSet<>(target);
        if (targetSet.isEmpty()) {
            return List.of();
        }
        List<String> sortedCandidates = new ArrayList<>(candidateIds);
        sortedCandidates.sort(String::compareTo);
        int n = sortedCandidates.size();
        for (int k = 1; k <= n; k++) {
            List<String> best = null;
            for (List<String> combo : combinations(sortedCandidates, k)) {
                Set<String> union = new HashSet<>();
                for (String cid : combo) {
                    union.addAll(candidateSets.get(cid));
                    if (targetSet.stream().allMatch(union::contains)) {
                        break;
                    }
                }
                if (targetSet.stream().allMatch(union::contains)) {
                    if (best == null || comboLexLess(combo, best)) {
                        best = combo;
                    }
                }
            }
            if (best != null) {
                return best;
            }
        }
        return List.of();
    }

    private static boolean comboLexLess(List<String> a, List<String> b) {
        for (int i = 0; i < Math.min(a.size(), b.size()); i++) {
            int c = a.get(i).compareTo(b.get(i));
            if (c != 0) {
                return c < 0;
            }
        }
        return a.size() < b.size();
    }

    private static String coverageString(int matchedCount, int total) {
        if (total == 0) {
            return "0.00";
        }
        BigDecimal pct =
                BigDecimal.valueOf(matchedCount)
                        .multiply(BigDecimal.valueOf(100))
                        .divide(BigDecimal.valueOf(total), 10, RoundingMode.HALF_EVEN);
        return pct.setScale(2, RoundingMode.HALF_EVEN).toPlainString();
    }

    private static Map.Entry<List<Map<String, Object>>, Map<String, Map<String, Object>>> classifyRules(
            List<Map<String, Object>> rules,
            List<Map<String, Object>> flows,
            Map<String, Object> policy) {
        List<Map<String, Object>> ordered = evaluationOrder(rules, policy);
        Map<String, List<String>> matched = new TreeMap<>();
        Map<String, Set<String>> matchedSets = new TreeMap<>();
        for (Map<String, Object> r : rules) {
            String rid = (String) r.get("id");
            List<String> mf = matchedFlowIds(r, flows, policy);
            matched.put(rid, mf);
            matchedSets.put(rid, new HashSet<>(mf));
        }
        Map<String, Integer> posInOrder = new HashMap<>();
        for (int i = 0; i < ordered.size(); i++) {
            posInOrder.put((String) ordered.get(i).get("id"), i);
        }
        List<Map<String, Object>> fullVerdicts = new ArrayList<>();
        for (Map<String, Object> f : flows) {
            fullVerdicts.add(evaluateFlow(f, ordered, policy));
        }
        Map<String, Object[]> basePair = new TreeMap<>();
        for (Map<String, Object> v : fullVerdicts) {
            basePair.put((String) v.get("id"), new Object[] {v.get("verdict"), v.get("matched_rule_id")});
        }
        String defaultAction = (String) policy.get("default_action");
        Map<String, String> baseNormalized = new TreeMap<>();
        for (Map.Entry<String, Object[]> e : basePair.entrySet()) {
            String v = (String) e.getValue()[0];
            baseNormalized.put(e.getKey(), "default".equals(v) ? defaultAction : v);
        }
        List<Map<String, Object>> analysis = new ArrayList<>();
        for (Map<String, Object> rule : rules) {
            String rid = (String) rule.get("id");
            List<String> mf = matched.get(rid);
            if (mf.isEmpty()) {
                Map<String, Object> row = new TreeMap<>();
                row.put("coverage_percent", coverageString(0, flows.size()));
                row.put("id", rid);
                row.put("matched_flows", List.of());
                row.put("shadowed_by", List.of());
                row.put("status", "unreachable");
                analysis.add(row);
                continue;
            }
            int idx = posInOrder.get(rid);
            List<String> earlierIds = new ArrayList<>();
            for (int i = 0; i < idx; i++) {
                earlierIds.add((String) ordered.get(i).get("id"));
            }
            Set<String> earlierUnion = new HashSet<>();
            for (String eid : earlierIds) {
                earlierUnion.addAll(matchedSets.get(eid));
            }
            Set<String> targetSet = matchedSets.get(rid);
            if (earlierUnion.containsAll(targetSet)) {
                List<String> cover =
                        lexSmallestMinCover(
                                new ArrayList<>(targetSet), earlierIds, matchedSets);
                Map<String, Object> row = new TreeMap<>();
                row.put("coverage_percent", coverageString(mf.size(), flows.size()));
                row.put("id", rid);
                row.put("matched_flows", new ArrayList<>(mf));
                row.put("shadowed_by", cover);
                row.put("status", "shadowed");
                analysis.add(row);
                continue;
            }
            List<Map<String, Object>> rulesWithout = new ArrayList<>();
            for (Map<String, Object> r : rules) {
                if (!rid.equals(r.get("id"))) {
                    rulesWithout.add(r);
                }
            }
            List<Map<String, Object>> orderedWithout = evaluationOrder(rulesWithout, policy);
            boolean redundant = true;
            for (Map<String, Object> f : flows) {
                String fid = (String) f.get("id");
                String newNorm =
                        normalizeVerdict(
                                (String) evaluateFlow(f, orderedWithout, policy).get("verdict"),
                                defaultAction);
                if (!newNorm.equals(baseNormalized.get(fid))) {
                    redundant = false;
                    break;
                }
            }
            Map<String, Object> row = new TreeMap<>();
            row.put("coverage_percent", coverageString(mf.size(), flows.size()));
            row.put("id", rid);
            row.put("matched_flows", new ArrayList<>(mf));
            row.put("shadowed_by", List.of());
            row.put("status", redundant ? "redundant" : "effective");
            analysis.add(row);
        }
        analysis.sort(Comparator.comparing(r -> (String) r.get("id")));
        Map<String, Map<String, Object>> byId = new TreeMap<>();
        for (Map<String, Object> entry : analysis) {
            byId.put((String) entry.get("id"), entry);
        }
        return Map.entry(analysis, byId);
    }

    private static String normalizeVerdict(String v, String defaultAction) {
        return "default".equals(v) ? defaultAction : v;
    }

    private static Map.Entry<List<String>, List<String>> computeEquivalenceClasses(
            List<Map<String, Object>> rules,
            List<Map<String, Object>> flows,
            Map<String, Object> policy) {
        List<Map<String, Object>> baseOrdered = evaluationOrder(rules, policy);
        Map<String, Object[]> basePairs = new TreeMap<>();
        for (Map<String, Object> f : flows) {
            Map<String, Object> v = evaluateFlow(f, baseOrdered, policy);
            basePairs.put((String) f.get("id"), new Object[] {v.get("verdict"), v.get("matched_rule_id")});
        }
        List<Map<String, Object>> remaining = new ArrayList<>(rules);
        List<String> removed = new ArrayList<>();
        boolean changed = true;
        while (changed) {
            changed = false;
            List<String> ids = new ArrayList<>();
            for (Map<String, Object> r : remaining) {
                ids.add((String) r.get("id"));
            }
            ids.sort(String::compareTo);
            for (String rid : ids) {
                List<Map<String, Object>> candidate = new ArrayList<>();
                for (Map<String, Object> r : remaining) {
                    if (!rid.equals(r.get("id"))) {
                        candidate.add(r);
                    }
                }
                List<Map<String, Object>> candOrdered = evaluationOrder(candidate, policy);
                boolean ok = true;
                for (Map<String, Object> f : flows) {
                    Map<String, Object> v = evaluateFlow(f, candOrdered, policy);
                    Object[] bp = basePairs.get(f.get("id"));
                    if (!v.get("verdict").equals(bp[0]) || !objectsEqual(v.get("matched_rule_id"), bp[1])) {
                        ok = false;
                        break;
                    }
                }
                if (ok) {
                    remaining = candidate;
                    removed.add(rid);
                    changed = true;
                    break;
                }
            }
        }
        List<String> minimal = new ArrayList<>();
        for (Map<String, Object> r : remaining) {
            minimal.add((String) r.get("id"));
        }
        minimal.sort(String::compareTo);
        removed.sort(String::compareTo);
        return Map.entry(minimal, removed);
    }

    private static boolean objectsEqual(Object a, Object b) {
        if (a == null && b == null) {
            return true;
        }
        if (a == null || b == null) {
            return false;
        }
        return a.equals(b);
    }

    private static List<Map<String, String>> computeEscalationWarnings(
            Map<String, Map<String, Object>> analysisById,
            List<Map<String, Object>> rules,
            Map<String, Object> policy) {
        List<Map<String, Object>> ordered = evaluationOrder(rules, policy);
        Map<String, Integer> pos = new HashMap<>();
        for (int i = 0; i < ordered.size(); i++) {
            pos.put((String) ordered.get(i).get("id"), i);
        }
        List<Map<String, String>> warnings = new ArrayList<>();
        for (Map<String, Object> denyRule : rules) {
            if (!"deny".equals(denyRule.get("action"))) {
                continue;
            }
            String denyId = (String) denyRule.get("id");
            String denyStatus = (String) analysisById.get(denyId).get("status");
            if ("unreachable".equals(denyStatus) || "redundant".equals(denyStatus)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Set<String> denySet =
                    new HashSet<>((List<String>) analysisById.get(denyId).get("matched_flows"));
            if (denySet.isEmpty()) {
                continue;
            }
            int denyPos = pos.get(denyId);
            for (Map<String, Object> allowRule : rules) {
                if (!"allow".equals(allowRule.get("action"))) {
                    continue;
                }
                String allowId = (String) allowRule.get("id");
                if (pos.get(allowId) >= denyPos) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Set<String> allowSet =
                        new HashSet<>((List<String>) analysisById.get(allowId).get("matched_flows"));
                Set<String> inter = new HashSet<>(denySet);
                inter.retainAll(allowSet);
                if (!inter.isEmpty()) {
                    Map<String, String> w = new TreeMap<>();
                    w.put("earlier_rule_id", allowId);
                    w.put("rule_id", denyId);
                    w.put("type", "deny_after_allow");
                    warnings.add(w);
                }
            }
        }
        warnings.sort(
                Comparator.comparing((Map<String, String> w) -> w.get("rule_id"))
                        .thenComparing(w -> w.get("earlier_rule_id")));
        return warnings;
    }

    private static List<Map<String, Object>> computeRuleDependencies(
            List<Map<String, Object>> rules,
            List<Map<String, Object>> flows,
            Map<String, Object> policy,
            Map<String, Map<String, Object>> baseAnalysisById,
            Map<String, Object[]> baseFlowPairs) {
        String defaultAction = (String) policy.get("default_action");
        Map<String, String> baseNormalized = new TreeMap<>();
        for (Map.Entry<String, Object[]> e : baseFlowPairs.entrySet()) {
            baseNormalized.put(
                    e.getKey(),
                    normalizeVerdict((String) e.getValue()[0], defaultAction));
        }
        Map<String, String> baseStatusById = new TreeMap<>();
        for (Map.Entry<String, Map<String, Object>> e : baseAnalysisById.entrySet()) {
            baseStatusById.put(e.getKey(), (String) e.getValue().get("status"));
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> rule : rules) {
            String rid = (String) rule.get("id");
            List<Map<String, Object>> reduced = new ArrayList<>();
            for (Map<String, Object> r : rules) {
                if (!rid.equals(r.get("id"))) {
                    reduced.add(r);
                }
            }
            List<Map<String, Object>> reducedOrdered = evaluationOrder(reduced, policy);
            List<String> flowsChanged = new ArrayList<>();
            List<Map<String, String>> verdictChanges = new ArrayList<>();
            for (Map<String, Object> f : flows) {
                String fid = (String) f.get("id");
                Map<String, Object> v = evaluateFlow(f, reducedOrdered, policy);
                Object[] bp = baseFlowPairs.get(fid);
                Object[] newPair = new Object[] {v.get("verdict"), v.get("matched_rule_id")};
                if (!newPair[0].equals(bp[0]) || !objectsEqual(newPair[1], bp[1])) {
                    flowsChanged.add(fid);
                }
                String newNorm = normalizeVerdict((String) v.get("verdict"), defaultAction);
                if (!newNorm.equals(baseNormalized.get(fid))) {
                    Map<String, String> ch = new TreeMap<>();
                    ch.put("flow_id", fid);
                    ch.put("from_verdict", baseNormalized.get(fid));
                    ch.put("to_verdict", newNorm);
                    verdictChanges.add(ch);
                }
            }
            flowsChanged.sort(String::compareTo);
            verdictChanges.sort(Comparator.comparing(c -> c.get("flow_id")));
            List<String> promoted = new ArrayList<>();
            if (!reduced.isEmpty()) {
                Map<String, Map<String, Object>> newById = classifyRules(reduced, flows, policy).getValue();
                for (Map.Entry<String, Map<String, Object>> e : newById.entrySet()) {
                    String qid = e.getKey();
                    if (qid.equals(rid)) {
                        continue;
                    }
                    if ("effective".equals(e.getValue().get("status"))
                            && !"effective".equals(baseStatusById.get(qid))) {
                        promoted.add(qid);
                    }
                }
            }
            promoted.sort(String::compareTo);
            String crit;
            if (!verdictChanges.isEmpty()) {
                crit = "critical";
            } else if (!flowsChanged.isEmpty()) {
                crit = "important";
            } else if (!promoted.isEmpty()) {
                crit = "minor";
            } else {
                crit = "none";
            }
            Map<String, Object> row = new TreeMap<>();
            row.put("criticality", crit);
            row.put("flows_changed", flowsChanged);
            row.put("id", rid);
            row.put("promoted_rules", promoted);
            row.put("verdict_changes", verdictChanges);
            out.add(row);
        }
        out.sort(Comparator.comparing(r -> (String) r.get("id")));
        return out;
    }

    private static Map<String, Object> computePerturbationGraph(
            List<Map<String, Object>> rules, List<Map<String, Object>> deps) {
        List<String> ruleIds = new ArrayList<>();
        for (Map<String, Object> r : rules) {
            ruleIds.add((String) r.get("id"));
        }
        Map<String, List<String>> promotedBy = new TreeMap<>();
        for (Map<String, Object> entry : deps) {
            @SuppressWarnings("unchecked")
            List<String> pr = (List<String>) entry.get("promoted_rules");
            promotedBy.put((String) entry.get("id"), new ArrayList<>(pr));
        }
        List<String[]> edges = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        for (Map.Entry<String, List<String>> e : promotedBy.entrySet()) {
            String src = e.getKey();
            for (String tgt : e.getValue()) {
                if (src.equals(tgt)) {
                    continue;
                }
                String key = src + "\0" + tgt;
                if (seen.contains(key)) {
                    continue;
                }
                seen.add(key);
                edges.add(new String[] {src, tgt});
            }
        }
        edges.sort(
                Comparator.comparing((String[] x) -> x[0]).thenComparing(x -> x[1]));
        Map<String, Set<String>> outN = new TreeMap<>();
        Map<String, Set<String>> inN = new TreeMap<>();
        for (String rid : ruleIds) {
            outN.put(rid, new TreeSet<>());
            inN.put(rid, new TreeSet<>());
        }
        for (String[] e : edges) {
            outN.get(e[0]).add(e[1]);
            inN.get(e[1]).add(e[0]);
        }
        List<Map<String, Object>> nodes = new ArrayList<>();
        for (String rid : new TreeSet<>(ruleIds)) {
            Map<String, Object> row = new TreeMap<>();
            row.put("id", rid);
            row.put("in_degree", inN.get(rid).size());
            row.put("out_degree", outN.get(rid).size());
            nodes.add(row);
        }
        Map<String, Integer> indexOf = new HashMap<>();
        for (int i = 0; i < ruleIds.size(); i++) {
            indexOf.put(ruleIds.get(i), i);
        }
        int[] indices = new int[ruleIds.size()];
        java.util.Arrays.fill(indices, -1);
        int[] lowlink = new int[ruleIds.size()];
        boolean[] onStack = new boolean[ruleIds.size()];
        List<Integer> stack = new ArrayList<>();
        int[] idxCounter = {0};
        List<List<String>> sccs = new ArrayList<>();
        for (int v = 0; v < ruleIds.size(); v++) {
            if (indices[v] != -1) {
                continue;
            }
            List<int[]> callStack = new ArrayList<>();
            callStack.add(new int[] {v, 0});
            while (!callStack.isEmpty()) {
                int[] frame = callStack.get(callStack.size() - 1);
                int cur = frame[0];
                int childPos = frame[1];
                if (childPos == 0) {
                    indices[cur] = idxCounter[0];
                    lowlink[cur] = idxCounter[0];
                    idxCounter[0]++;
                    stack.add(cur);
                    onStack[cur] = true;
                }
                List<String> children = new ArrayList<>(outN.get(ruleIds.get(cur)));
                children.sort(String::compareTo);
                if (childPos < children.size()) {
                    frame[1] = childPos + 1;
                    int w = indexOf.get(children.get(childPos));
                    if (indices[w] == -1) {
                        callStack.add(new int[] {w, 0});
                    } else if (onStack[w]) {
                        lowlink[cur] = Math.min(lowlink[cur], indices[w]);
                    }
                } else {
                    if (lowlink[cur] == indices[cur]) {
                        List<String> scc = new ArrayList<>();
                        while (true) {
                            int w = stack.remove(stack.size() - 1);
                            onStack[w] = false;
                            scc.add(ruleIds.get(w));
                            if (w == cur) {
                                break;
                            }
                        }
                        scc.sort(String::compareTo);
                        sccs.add(scc);
                    }
                    callStack.remove(callStack.size() - 1);
                    if (!callStack.isEmpty()) {
                        int pv = callStack.get(callStack.size() - 1)[0];
                        lowlink[pv] = Math.min(lowlink[pv], lowlink[cur]);
                    }
                }
            }
        }
        List<List<String>> cycles = new ArrayList<>();
        for (List<String> s : sccs) {
            if (s.size() > 1) {
                cycles.add(new ArrayList<>(s));
            }
        }
        cycles.sort(Comparator.comparing(c -> c.get(0)));
        Map<String, Integer> sccOf = new HashMap<>();
        for (int i = 0; i < sccs.size(); i++) {
            for (String rid : sccs.get(i)) {
                sccOf.put(rid, i);
            }
        }
        Map<Integer, Set<Integer>> condOut = new HashMap<>();
        Map<Integer, Integer> condIn = new HashMap<>();
        for (int i = 0; i < sccs.size(); i++) {
            condOut.put(i, new HashSet<>());
            condIn.put(i, 0);
        }
        for (String[] e : edges) {
            int si = sccOf.get(e[0]);
            int ti = sccOf.get(e[1]);
            if (si != ti) {
                if (!condOut.get(si).contains(ti)) {
                    condOut.get(si).add(ti);
                    condIn.put(ti, condIn.get(ti) + 1);
                }
            }
        }
        List<List<String>> layers = new ArrayList<>();
        Set<Integer> placed = new HashSet<>();
        Map<Integer, Integer> indeg = new HashMap<>(condIn);
        while (placed.size() < sccs.size()) {
            List<Integer> current = new ArrayList<>();
            for (int i = 0; i < sccs.size(); i++) {
                if (!placed.contains(i) && indeg.get(i) == 0) {
                    current.add(i);
                }
            }
            current.sort(Comparator.comparing(i -> sccs.get(i).get(0)));
            if (current.isEmpty()) {
                break;
            }
            List<String> idsInLayer = new ArrayList<>();
            for (int i : current) {
                idsInLayer.addAll(sccs.get(i));
                placed.add(i);
            }
            idsInLayer.sort(String::compareTo);
            layers.add(idsInLayer);
            for (int i : current) {
                for (int j : condOut.get(i)) {
                    indeg.put(j, indeg.get(j) - 1);
                }
            }
        }
        List<Map<String, Object>> edgeArr = new ArrayList<>();
        for (String[] e : edges) {
            Map<String, Object> row = new TreeMap<>();
            row.put("from", e[0]);
            row.put("to", e[1]);
            edgeArr.add(row);
        }
        Map<String, Object> graph = new TreeMap<>();
        graph.put("cycles", cycles);
        graph.put("edges", edgeArr);
        graph.put("nodes", nodes);
        graph.put("topological_layers", layers);
        return graph;
    }

    private static Map<String, Object> runSimulation(
            JsonObject rulesDoc, JsonObject flowsDoc, JsonObject policyDoc) {
        List<Map<String, Object>> rules = new ArrayList<>();
        for (JsonElement el : rulesDoc.getAsJsonArray("rules")) {
            rules.add(ruleFromJson(el.getAsJsonObject()));
        }
        List<Map<String, Object>> flows = new ArrayList<>();
        for (JsonElement el : flowsDoc.getAsJsonArray("flows")) {
            flows.add(flowFromJson(el.getAsJsonObject()));
        }
        Map<String, Object> policy = policyFromJson(policyDoc);
        List<Map<String, Object>> ordered = evaluationOrder(rules, policy);
        List<Map<String, Object>> flowVerdicts = new ArrayList<>();
        for (Map<String, Object> f : flows) {
            flowVerdicts.add(evaluateFlow(f, ordered, policy));
        }
        flowVerdicts.sort(Comparator.comparing(v -> (String) v.get("id")));
        var classified = classifyRules(rules, flows, policy);
        List<Map<String, Object>> analysis = classified.getKey();
        Map<String, Map<String, Object>> byId = classified.getValue();
        Map<String, Integer> counts = new TreeMap<>();
        for (String s : List.of("effective", "redundant", "shadowed", "unreachable")) {
            counts.put(s, 0);
        }
        for (Map<String, Object> entry : analysis) {
            counts.merge((String) entry.get("status"), 1, Integer::sum);
        }
        int defaultUses = 0;
        for (Map<String, Object> v : flowVerdicts) {
            if ("default".equals(v.get("verdict"))) {
                defaultUses++;
            }
        }
        List<Map<String, String>> warnings = computeEscalationWarnings(byId, rules, policy);
        Map<String, Object> summary = new TreeMap<>();
        summary.put("default_action_uses", defaultUses);
        summary.put("effective", counts.get("effective"));
        summary.put("escalation_warnings", warnings);
        summary.put("redundant", counts.get("redundant"));
        summary.put("shadowed", counts.get("shadowed"));
        summary.put("total_rules", rules.size());
        summary.put("unreachable", counts.get("unreachable"));
        var equiv = computeEquivalenceClasses(rules, flows, policy);
        Map<String, Object[]> baseFlowPairs = new TreeMap<>();
        for (Map<String, Object> v : flowVerdicts) {
            baseFlowPairs.put(
                    (String) v.get("id"),
                    new Object[] {v.get("verdict"), v.get("matched_rule_id")});
        }
        List<Map<String, Object>> deps =
                computeRuleDependencies(rules, flows, policy, byId, baseFlowPairs);
        Map<String, Object> perturbationGraph = computePerturbationGraph(rules, deps);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("flow_verdicts", Map.of("flows", flowVerdicts));
        out.put("rule_analysis", Map.of("rules", analysis));
        out.put("policy_summary", summary);
        out.put(
                "equivalence_classes",
                Map.of(
                        "minimal_rule_ids", equiv.getKey(),
                        "removed_rule_ids", equiv.getValue(),
                        "verdict_invariant", true));
        out.put("rule_dependencies", Map.of("rules", deps));
        out.put("perturbation_graph", perturbationGraph);
        return out;
    }

    private static JsonObject readObject(Path path) throws IOException {
        return JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8))
                .getAsJsonObject();
    }

    private static void writeCanonical(Path path, Object value) throws IOException {
        Gson gson =
                new GsonBuilder()
                        .setPrettyPrinting()
                        .serializeNulls()
                        .disableHtmlEscaping()
                        .create();
        Files.writeString(path, gson.toJson(value) + "\n", StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            System.err.println("usage: FirewallRuleShadow <input_dir> <output_dir>");
            System.exit(2);
        }
        Path inDir = Path.of(args[0]);
        Path outDir = Path.of(args[1]);
        Files.createDirectories(outDir);
        JsonObject rulesDoc = readObject(inDir.resolve("rules.json"));
        JsonObject flowsDoc = readObject(inDir.resolve("flows.json"));
        JsonObject policyDoc = readObject(inDir.resolve("policy.json"));
        Map<String, Object> outputs = runSimulation(rulesDoc, flowsDoc, policyDoc);
        writeCanonical(outDir.resolve("flow_verdicts.json"), outputs.get("flow_verdicts"));
        writeCanonical(outDir.resolve("rule_analysis.json"), outputs.get("rule_analysis"));
        writeCanonical(outDir.resolve("policy_summary.json"), outputs.get("policy_summary"));
        writeCanonical(
                outDir.resolve("equivalence_classes.json"), outputs.get("equivalence_classes"));
        writeCanonical(outDir.resolve("rule_dependencies.json"), outputs.get("rule_dependencies"));
        writeCanonical(
                outDir.resolve("perturbation_graph.json"), outputs.get("perturbation_graph"));
    }
}
