package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

type Broker struct {
	BrokerID                 string `json:"broker_id"`
	AvailabilityZone         string `json:"availability_zone"`
	Region                   string `json:"region"`
	Pool                     string `json:"pool"`
	NominalCapacityMbps      int    `json:"nominal_capacity_mbps"`
	UtilizationOverheadPct   int    `json:"utilization_overhead_pct"`
	BackpressureThresholdPct int    `json:"backpressure_threshold_pct"`
}

type Topic struct {
	TopicID                           string         `json:"topic_id"`
	Partitions                        int            `json:"partitions"`
	Tier                              string         `json:"tier"`
	TargetLagMessages                 int            `json:"target_lag_messages"`
	CurrentThroughputMbpsPerPartition int            `json:"current_throughput_mbps_per_partition"`
	CurrentLagMessages                map[string]int `json:"current_lag_messages"`
	CurrentLeaderMap                  map[string]string `json:"current_leader_map"`
}

type ConsumerMember struct {
	MemberID                string `json:"member_id"`
	ConsumptionCapacityMbps int    `json:"consumption_capacity_mbps"`
}

type ConsumerGroup struct {
	GroupID      string           `json:"group_id"`
	Subscription string           `json:"subscription"`
	Members      []ConsumerMember `json:"members"`
}

type Policy struct {
	ReplicationFactorByTier map[string]int      `json:"replication_factor_by_tier"`
	AntiAffinity            map[string]string   `json:"anti_affinity"`
	TierEligiblePools       map[string][]string `json:"tier_eligible_pools"`
}

type RawEvent struct {
	EventID         string `json:"event_id"`
	Kind            string `json:"kind"`
	BrokerID        string `json:"broker_id"`
	EvacDay         *int   `json:"evac_day"`
	TopicID         string `json:"topic_id"`
	PartitionID     *int   `json:"partition_id"`
	NewCapacityMbps *int   `json:"new_capacity_mbps"`
	Day             int    `json:"day"`
	Accepted        bool   `json:"accepted"`
}

type IncidentLog struct {
	Events []RawEvent `json:"events"`
}

type Cluster struct {
	Brokers []Broker `json:"brokers"`
}

type PoolState struct {
	CurrentDay int `json:"current_day"`
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}

func die(err error) {
	fmt.Fprintln(os.Stderr, "rebalancer error:", err)
	os.Exit(1)
}

func mustReadJSON(path string, dst interface{}) {
	b, err := os.ReadFile(path)
	if err != nil {
		die(fmt.Errorf("read %s: %w", path, err))
	}
	if err := json.Unmarshal(b, dst); err != nil {
		die(fmt.Errorf("parse %s: %w", path, err))
	}
}

func writeJSON(path string, obj interface{}) {
	buf := &bytes.Buffer{}
	enc := json.NewEncoder(buf)
	enc.SetIndent("", "  ")
	enc.SetEscapeHTML(false)
	if err := enc.Encode(obj); err != nil {
		die(err)
	}
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		die(err)
	}
}

func loadTopics(clusterDir string) []Topic {
	dir := filepath.Join(clusterDir, "topics")
	var topics []Topic
	err := filepath.WalkDir(dir, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !strings.HasSuffix(p, ".json") {
			return nil
		}
		var t Topic
		mustReadJSON(p, &t)
		topics = append(topics, t)
		return nil
	})
	if err != nil {
		die(err)
	}
	sort.Slice(topics, func(i, j int) bool { return topics[i].TopicID < topics[j].TopicID })
	return topics
}

func loadConsumerGroups(clusterDir string) []ConsumerGroup {
	dir := filepath.Join(clusterDir, "consumers")
	var groups []ConsumerGroup
	err := filepath.WalkDir(dir, func(p string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() || !strings.HasSuffix(p, ".json") {
			return nil
		}
		var g ConsumerGroup
		mustReadJSON(p, &g)
		groups = append(groups, g)
		return nil
	})
	if err != nil {
		die(err)
	}
	sort.Slice(groups, func(i, j int) bool { return groups[i].GroupID < groups[j].GroupID })
	return groups
}

type AcceptedEvents struct {
	Quarantined        map[string]bool
	Frozen             map[string]bool
	CapacityOverride   map[string]int
	AcceptedCount      int
	IgnoredCount       int
}

func filterEvents(log IncidentLog, currentDay int, brokerIDs map[string]bool, topicByID map[string]*Topic) AcceptedEvents {
	out := AcceptedEvents{
		Quarantined:      map[string]bool{},
		Frozen:           map[string]bool{},
		CapacityOverride: map[string]int{},
	}
	events := append([]RawEvent(nil), log.Events...)
	sort.SliceStable(events, func(i, j int) bool {
		if events[i].Day != events[j].Day {
			return events[i].Day < events[j].Day
		}
		return events[i].EventID < events[j].EventID
	})

	for _, e := range events {
		if !e.Accepted || e.Day > currentDay {
			out.IgnoredCount++
			continue
		}
		switch e.Kind {
		case "broker_quarantine":
			if e.EvacDay == nil || *e.EvacDay > currentDay {
				out.IgnoredCount++
				continue
			}
			if !brokerIDs[e.BrokerID] {
				out.IgnoredCount++
				continue
			}
			out.Quarantined[e.BrokerID] = true
			out.AcceptedCount++
		case "partition_freeze":
			t, ok := topicByID[e.TopicID]
			if !ok || e.PartitionID == nil || *e.PartitionID < 0 || *e.PartitionID >= t.Partitions {
				out.IgnoredCount++
				continue
			}
			key := e.TopicID + ":" + strconv.Itoa(*e.PartitionID)
			out.Frozen[key] = true
			out.AcceptedCount++
		case "capacity_override":
			if !brokerIDs[e.BrokerID] || e.NewCapacityMbps == nil || *e.NewCapacityMbps <= 0 {
				out.IgnoredCount++
				continue
			}
			out.CapacityOverride[e.BrokerID] = *e.NewCapacityMbps
			out.AcceptedCount++
		default:
			out.IgnoredCount++
		}
	}
	return out
}

func hashSlot(topicID string, partitionID, slot int) uint64 {
	h := sha256.Sum256([]byte(topicID + ":" + strconv.Itoa(partitionID) + ":" + strconv.Itoa(slot)))
	return binary.BigEndian.Uint64(h[:8])
}

type Placement struct {
	TopicID         string
	PartitionID     int
	Tier            string
	LeaderBroker    string
	ReplicaBrokers  []string
	PlacementReason string
	Status          string
	Throughput      int
	Lag             int
	OriginalLeader  string
}

func placeOne(
	topicID string,
	partitionID int,
	rf int,
	eligiblePool []*Broker,
	excludeBroker string,
	antiAffinityViolations *int,
) (string, []string) {
	if len(eligiblePool) == 0 {
		return "", nil
	}
	available := make([]*Broker, 0, len(eligiblePool))
	for _, b := range eligiblePool {
		if b.BrokerID == excludeBroker {
			continue
		}
		available = append(available, b)
	}
	sort.Slice(available, func(i, j int) bool { return available[i].BrokerID < available[j].BrokerID })
	if len(available) == 0 {
		return "", nil
	}
	chosen := make([]*Broker, 0, rf)
	for s := 0; s < rf; s++ {
		h := hashSlot(topicID, partitionID, s)
		start := int(h % uint64(len(available)))
		usedAZs := map[string]bool{}
		usedRegions := map[string]bool{}
		usedIDs := map[string]bool{}
		for _, c := range chosen {
			usedAZs[c.AvailabilityZone] = true
			usedRegions[c.Region] = true
			usedIDs[c.BrokerID] = true
		}

		pickAZ, pickRegion, pickAny := -1, -1, -1
		for off := 0; off < len(available); off++ {
			idx := (start + off) % len(available)
			b := available[idx]
			if usedIDs[b.BrokerID] {
				continue
			}
			if pickAny < 0 {
				pickAny = idx
			}
			if !usedRegions[b.Region] && pickRegion < 0 {
				pickRegion = idx
			}
			if !usedAZs[b.AvailabilityZone] {
				pickAZ = idx
				break
			}
		}
		var pick int
		switch {
		case pickAZ >= 0:
			pick = pickAZ
		case pickRegion >= 0:
			pick = pickRegion
		default:
			pick = pickAny
			if len(chosen) > 0 {
				*antiAffinityViolations++
			}
		}
		if pick < 0 {
			return "", nil
		}
		chosen = append(chosen, available[pick])
	}
	leader := chosen[0].BrokerID
	replicas := make([]string, 0, len(chosen)-1)
	for _, b := range chosen[1:] {
		replicas = append(replicas, b.BrokerID)
	}
	sort.Strings(replicas)
	return leader, replicas
}

func effectiveCapacity(b Broker, override int, hasOverride bool) int {
	nominal := b.NominalCapacityMbps
	if hasOverride {
		nominal = override
	}
	return (nominal * (100 - b.UtilizationOverheadPct)) / 100
}

func overThreshold(loadMbps, effectiveCap, thresholdPct int) bool {
	return 100*loadMbps > thresholdPct*effectiveCap
}

func tierRank(tier string) int {
	switch tier {
	case "bronze":
		return 0
	case "silver":
		return 1
	case "gold":
		return 2
	}
	return 99
}

type partitionKey struct {
	TopicID     string
	PartitionID int
}

func main() {
	clusterDir := getenv("SSR_CLUSTER_DIR", "/app/cluster")
	planDir := getenv("SSR_PLAN_DIR", "/app/plan")
	if err := os.MkdirAll(planDir, 0o755); err != nil {
		die(err)
	}

	var cluster Cluster
	mustReadJSON(filepath.Join(clusterDir, "topology", "cluster.json"), &cluster)

	var policy Policy
	mustReadJSON(filepath.Join(clusterDir, "policy", "rebalance_policy.json"), &policy)

	var poolState PoolState
	mustReadJSON(filepath.Join(clusterDir, "pool_state.json"), &poolState)

	var incidents IncidentLog
	mustReadJSON(filepath.Join(clusterDir, "incidents", "incident_log.json"), &incidents)

	topics := loadTopics(clusterDir)
	groups := loadConsumerGroups(clusterDir)

	brokerByID := map[string]*Broker{}
	brokerIDs := map[string]bool{}
	for i := range cluster.Brokers {
		brokerByID[cluster.Brokers[i].BrokerID] = &cluster.Brokers[i]
		brokerIDs[cluster.Brokers[i].BrokerID] = true
	}
	topicByID := map[string]*Topic{}
	for i := range topics {
		topicByID[topics[i].TopicID] = &topics[i]
	}

	accepted := filterEvents(incidents, poolState.CurrentDay, brokerIDs, topicByID)

	allBrokerIDs := make([]string, 0, len(cluster.Brokers))
	for _, b := range cluster.Brokers {
		allBrokerIDs = append(allBrokerIDs, b.BrokerID)
	}
	sort.Strings(allBrokerIDs)

	tierPool := func(tier string) []*Broker {
		var pool []*Broker
		allowed := map[string]bool{}
		for _, p := range policy.TierEligiblePools[tier] {
			allowed[p] = true
		}
		for _, id := range allBrokerIDs {
			b := brokerByID[id]
			if !allowed[b.Pool] {
				continue
			}
			if accepted.Quarantined[b.BrokerID] {
				continue
			}
			pool = append(pool, b)
		}
		return pool
	}

	antiAffinityViolations := 0
	placements := []Placement{}

	for _, t := range topics {
		rf := policy.ReplicationFactorByTier[t.Tier]
		pool := tierPool(t.Tier)
		for p := 0; p < t.Partitions; p++ {
			leader, replicas := placeOne(t.TopicID, p, rf, pool, "", &antiAffinityViolations)
			pkey := strconv.Itoa(p)
			pl := Placement{
				TopicID:         t.TopicID,
				PartitionID:     p,
				Tier:            t.Tier,
				LeaderBroker:    leader,
				ReplicaBrokers:  replicas,
				PlacementReason: "hash_placement",
				Status:          "active",
				Throughput:      t.CurrentThroughputMbpsPerPartition,
				Lag:             t.CurrentLagMessages[pkey],
				OriginalLeader:  t.CurrentLeaderMap[pkey],
			}
			placements = append(placements, pl)
		}
	}

	placementIdx := map[partitionKey]int{}
	for i, pl := range placements {
		placementIdx[partitionKey{pl.TopicID, pl.PartitionID}] = i
	}

	frozenBrokers := map[string]bool{}
	for key := range accepted.Frozen {
		parts := strings.SplitN(key, ":", 2)
		topicID := parts[0]
		pid, _ := strconv.Atoi(parts[1])
		t := topicByID[topicID]
		origLeader := t.CurrentLeaderMap[strconv.Itoa(pid)]
		idx := placementIdx[partitionKey{topicID, pid}]
		placements[idx].LeaderBroker = origLeader
		placements[idx].Status = "frozen"
		if accepted.Quarantined[origLeader] {
			placements[idx].PlacementReason = "frozen_during_quarantine"
			frozenBrokers[origLeader] = true
		} else {
			placements[idx].PlacementReason = "frozen_by_event"
		}
	}

	brokerLeaders := map[string]map[partitionKey]bool{}
	for _, id := range allBrokerIDs {
		brokerLeaders[id] = map[partitionKey]bool{}
	}
	brokerLoad := map[string]int{}
	for _, pl := range placements {
		if pl.LeaderBroker == "" {
			continue
		}
		brokerLeaders[pl.LeaderBroker][partitionKey{pl.TopicID, pl.PartitionID}] = true
		brokerLoad[pl.LeaderBroker] += pl.Throughput
	}

	demotionsTotal := 0
	alreadyDemoted := map[partitionKey]bool{}
	for _, brokerID := range allBrokerIDs {
		if accepted.Quarantined[brokerID] {
			continue
		}
		b := brokerByID[brokerID]
		override, hasOverride := accepted.CapacityOverride[brokerID]
		effCap := effectiveCapacity(*b, override, hasOverride)
		for overThreshold(brokerLoad[brokerID], effCap, b.BackpressureThresholdPct) {
			var candidate *Placement
			var candidateIdx int
			for pk := range brokerLeaders[brokerID] {
				idx := placementIdx[pk]
				pl := &placements[idx]
				if pl.Status == "frozen" {
					continue
				}
				if pl.Tier == "gold" {
					continue
				}
				if alreadyDemoted[pk] {
					continue
				}
				if candidate == nil {
					candidate = pl
					candidateIdx = idx
					continue
				}
				cr := tierRank(candidate.Tier)
				pr := tierRank(pl.Tier)
				if pr < cr {
					candidate = pl
					candidateIdx = idx
					continue
				}
				if pr == cr {
					if pl.TopicID > candidate.TopicID {
						candidate = pl
						candidateIdx = idx
						continue
					}
					if pl.TopicID == candidate.TopicID && pl.PartitionID > candidate.PartitionID {
						candidate = pl
						candidateIdx = idx
					}
				}
			}
			if candidate == nil {
				break
			}
			pool := tierPool(candidate.Tier)
			newLeader, _ := placeOne(candidate.TopicID, candidate.PartitionID, 1, pool, brokerID, &antiAffinityViolations)
			if newLeader == "" || newLeader == brokerID {
				break
			}
			pk := partitionKey{candidate.TopicID, candidate.PartitionID}
			delete(brokerLeaders[brokerID], pk)
			brokerLoad[brokerID] -= candidate.Throughput
			brokerLeaders[newLeader][pk] = true
			brokerLoad[newLeader] += candidate.Throughput
			placements[candidateIdx].LeaderBroker = newLeader
			placements[candidateIdx].PlacementReason = "demoted_for_backpressure"
			alreadyDemoted[pk] = true
			demotionsTotal++
		}
	}

	type GroupOut struct {
		GroupID                    string
		SubscribedTopics           []string
		MemberAssignments          map[string][]map[string]interface{}
		UnassignedPartitions       []map[string]interface{}
		ProjectedMaxMemberLag      int
		ProjectedTotalThroughput   int
		LagStatus                  string
		ExceedingMembers           []string
	}

	groupOutputs := []GroupOut{}
	for _, g := range groups {
		var subscribed []string
		switch {
		case strings.HasPrefix(g.Subscription, "literal:"):
			lit := strings.TrimPrefix(g.Subscription, "literal:")
			if _, ok := topicByID[lit]; ok {
				subscribed = append(subscribed, lit)
			}
		case strings.HasPrefix(g.Subscription, "regex:"):
			pat := strings.TrimPrefix(g.Subscription, "regex:")
			re, err := regexp.Compile(pat)
			if err != nil {
				die(fmt.Errorf("bad regex in group %s: %w", g.GroupID, err))
			}
			for _, t := range topics {
				if loc := re.FindStringIndex(t.TopicID); loc != nil && loc[0] == 0 && loc[1] == len(t.TopicID) {
					subscribed = append(subscribed, t.TopicID)
				}
			}
		default:
			die(fmt.Errorf("unsupported subscription %q for group %s", g.Subscription, g.GroupID))
		}
		sort.Strings(subscribed)

		type partRef struct {
			TopicID     string
			PartitionID int
			Lag         int
			Throughput  int
			TargetLag   int
		}
		var eligible []partRef
		var unassigned []partRef
		for _, tid := range subscribed {
			t := topicByID[tid]
			for p := 0; p < t.Partitions; p++ {
				idx := placementIdx[partitionKey{tid, p}]
				pl := placements[idx]
				pr := partRef{
					TopicID:     tid,
					PartitionID: p,
					Lag:         pl.Lag,
					Throughput:  pl.Throughput,
					TargetLag:   t.TargetLagMessages,
				}
				if pl.Status == "frozen" {
					unassigned = append(unassigned, pr)
				} else {
					eligible = append(eligible, pr)
				}
			}
		}

		sort.SliceStable(eligible, func(i, j int) bool {
			if eligible[i].Lag != eligible[j].Lag {
				return eligible[i].Lag > eligible[j].Lag
			}
			if eligible[i].Throughput != eligible[j].Throughput {
				return eligible[i].Throughput > eligible[j].Throughput
			}
			if eligible[i].TopicID != eligible[j].TopicID {
				return eligible[i].TopicID < eligible[j].TopicID
			}
			return eligible[i].PartitionID < eligible[j].PartitionID
		})

		members := append([]ConsumerMember(nil), g.Members...)
		sort.Slice(members, func(i, j int) bool { return members[i].MemberID < members[j].MemberID })
		memberLag := map[string]int{}
		memberAssign := map[string][]partRef{}
		for _, m := range members {
			memberLag[m.MemberID] = 0
			memberAssign[m.MemberID] = []partRef{}
		}

		for _, pr := range eligible {
			var pickID string
			pickLag := -1
			for _, m := range members {
				lg := memberLag[m.MemberID]
				if pickLag < 0 || lg < pickLag {
					pickLag = lg
					pickID = m.MemberID
				}
			}
			memberLag[pickID] += pr.Lag
			memberAssign[pickID] = append(memberAssign[pickID], pr)
		}

		maxLag := 0
		for _, v := range memberLag {
			if v > maxLag {
				maxLag = v
			}
		}
		totalThroughput := 0
		for _, pr := range eligible {
			totalThroughput += pr.Throughput
		}

		assignedTargets := map[string]int{}
		for _, pr := range eligible {
			if cur, ok := assignedTargets[pr.TopicID]; !ok || pr.TargetLag < cur {
				assignedTargets[pr.TopicID] = pr.TargetLag
			}
		}
		minTarget := 0
		first := true
		for _, v := range assignedTargets {
			if first || v < minTarget {
				minTarget = v
				first = false
			}
		}

		var lagStatus string
		var exceeding []string
		switch {
		case minTarget == 0 || 5*maxLag < 4*minTarget:
			lagStatus = "within_target"
		case maxLag >= minTarget:
			lagStatus = "exceeded"
		default:
			lagStatus = "near_threshold"
		}
		if minTarget > 0 {
			for _, m := range members {
				if memberLag[m.MemberID] >= minTarget {
					exceeding = append(exceeding, m.MemberID)
				}
			}
			sort.Strings(exceeding)
		}

		memberAssignOut := map[string][]map[string]interface{}{}
		for _, m := range members {
			rows := memberAssign[m.MemberID]
			sort.SliceStable(rows, func(i, j int) bool {
				if rows[i].TopicID != rows[j].TopicID {
					return rows[i].TopicID < rows[j].TopicID
				}
				return rows[i].PartitionID < rows[j].PartitionID
			})
			out := []map[string]interface{}{}
			for _, r := range rows {
				out = append(out, map[string]interface{}{
					"partition_id": r.PartitionID,
					"topic_id":     r.TopicID,
				})
			}
			memberAssignOut[m.MemberID] = out
		}

		sort.SliceStable(unassigned, func(i, j int) bool {
			if unassigned[i].TopicID != unassigned[j].TopicID {
				return unassigned[i].TopicID < unassigned[j].TopicID
			}
			return unassigned[i].PartitionID < unassigned[j].PartitionID
		})
		unassignedOut := []map[string]interface{}{}
		for _, r := range unassigned {
			unassignedOut = append(unassignedOut, map[string]interface{}{
				"partition_id": r.PartitionID,
				"reason":       "frozen",
				"topic_id":     r.TopicID,
			})
		}

		groupOutputs = append(groupOutputs, GroupOut{
			GroupID:                  g.GroupID,
			SubscribedTopics:         subscribed,
			MemberAssignments:        memberAssignOut,
			UnassignedPartitions:     unassignedOut,
			ProjectedMaxMemberLag:    maxLag,
			ProjectedTotalThroughput: totalThroughput,
			LagStatus:                lagStatus,
			ExceedingMembers:         exceeding,
		})
	}

	sort.Slice(placements, func(i, j int) bool {
		if placements[i].TopicID != placements[j].TopicID {
			return placements[i].TopicID < placements[j].TopicID
		}
		return placements[i].PartitionID < placements[j].PartitionID
	})

	partitionRows := []map[string]interface{}{}
	for _, pl := range placements {
		row := map[string]interface{}{
			"leader_broker":    pl.LeaderBroker,
			"partition_id":     pl.PartitionID,
			"placement_reason": pl.PlacementReason,
			"replica_brokers":  pl.ReplicaBrokers,
			"status":           pl.Status,
			"tier":             pl.Tier,
			"topic_id":         pl.TopicID,
		}
		if row["replica_brokers"] == nil {
			row["replica_brokers"] = []string{}
		}
		partitionRows = append(partitionRows, row)
	}
	writeJSON(filepath.Join(planDir, "partition_assignment.json"), map[string]interface{}{
		"partitions": partitionRows,
	})

	consumerGroupsOut := []map[string]interface{}{}
	for _, go0 := range groupOutputs {
		consumerGroupsOut = append(consumerGroupsOut, map[string]interface{}{
			"group_id":              go0.GroupID,
			"member_assignments":    go0.MemberAssignments,
			"subscribed_topics":     go0.SubscribedTopics,
			"unassigned_partitions": go0.UnassignedPartitions,
		})
	}
	writeJSON(filepath.Join(planDir, "consumer_rebalance.json"), map[string]interface{}{
		"groups": consumerGroupsOut,
	})

	lagRows := []map[string]interface{}{}
	for _, go0 := range groupOutputs {
		exceeding := go0.ExceedingMembers
		if exceeding == nil {
			exceeding = []string{}
		}
		lagRows = append(lagRows, map[string]interface{}{
			"exceeding_members":                 exceeding,
			"group_id":                          go0.GroupID,
			"lag_status":                        go0.LagStatus,
			"projected_max_member_lag_messages": go0.ProjectedMaxMemberLag,
			"projected_total_throughput_mbps":   go0.ProjectedTotalThroughput,
		})
	}
	writeJSON(filepath.Join(planDir, "lag_report.json"), map[string]interface{}{
		"groups": lagRows,
	})

	finalLoad := map[string]int{}
	finalLeaders := map[string]map[partitionKey]bool{}
	for _, id := range allBrokerIDs {
		finalLeaders[id] = map[partitionKey]bool{}
	}
	for _, pl := range placements {
		if pl.LeaderBroker == "" {
			continue
		}
		finalLoad[pl.LeaderBroker] += pl.Throughput
		finalLeaders[pl.LeaderBroker][partitionKey{pl.TopicID, pl.PartitionID}] = true
	}

	brokerRows := []map[string]interface{}{}
	activeBrokers := 0
	quarantinedBrokers := 0
	frozenQuarantinedBrokers := 0
	capacityOverriddenBrokers := 0
	brokersOverThreshold := 0
	for _, id := range allBrokerIDs {
		b := brokerByID[id]
		override, hasOverride := accepted.CapacityOverride[id]
		effCap := effectiveCapacity(*b, override, hasOverride)
		load := finalLoad[id]
		over := overThreshold(load, effCap, b.BackpressureThresholdPct)

		var status string
		switch {
		case frozenBrokers[id]:
			status = "frozen_quarantined"
			frozenQuarantinedBrokers++
		case accepted.Quarantined[id]:
			status = "quarantined"
			quarantinedBrokers++
		case hasOverride:
			status = "capacity_overridden"
			capacityOverriddenBrokers++
		default:
			status = "active"
			activeBrokers++
		}
		if over {
			brokersOverThreshold++
		}

		evacuated := 0
		received := 0
		for _, t := range topics {
			for p := 0; p < t.Partitions; p++ {
				orig := t.CurrentLeaderMap[strconv.Itoa(p)]
				idx := placementIdx[partitionKey{t.TopicID, p}]
				finalLeader := placements[idx].LeaderBroker
				if orig == id && finalLeader != id {
					evacuated++
				}
				if finalLeader == id && orig != id {
					received++
				}
			}
		}

		brokerRows = append(brokerRows, map[string]interface{}{
			"broker_id":                  id,
			"effective_capacity_mbps":    effCap,
			"over_threshold":             over,
			"partitions_evacuated_count": evacuated,
			"partitions_received_count":  received,
			"post_rebalance_load_mbps":   load,
			"status":                     status,
		})
	}
	writeJSON(filepath.Join(planDir, "quarantine_status.json"), map[string]interface{}{
		"brokers": brokerRows,
	})

	frozenCount := 0
	for _, pl := range placements {
		if pl.Status == "frozen" {
			frozenCount++
		}
	}
	groupsExceeded := 0
	groupsWithinOrNear := 0
	for _, g := range groupOutputs {
		if g.LagStatus == "exceeded" {
			groupsExceeded++
		} else {
			groupsWithinOrNear++
		}
	}

	summary := map[string]interface{}{
		"accepted_incident_events":            accepted.AcceptedCount,
		"active_brokers":                      activeBrokers,
		"anti_affinity_violations_blocked":    antiAffinityViolations,
		"brokers_over_threshold":              brokersOverThreshold,
		"brokers_total":                       len(cluster.Brokers),
		"capacity_overridden_brokers":         capacityOverriddenBrokers,
		"consumer_groups_total":               len(groups),
		"demotions_total":                     demotionsTotal,
		"frozen_partitions":                   frozenCount,
		"frozen_quarantined_brokers":          frozenQuarantinedBrokers,
		"groups_with_lag_exceeded":            groupsExceeded,
		"groups_with_lag_within_target_or_near": groupsWithinOrNear,
		"ignored_incident_events":             accepted.IgnoredCount,
		"partitions_total":                    func() int { n := 0; for _, t := range topics { n += t.Partitions }; return n }(),
		"quarantined_brokers":                 quarantinedBrokers,
		"topics_total":                        len(topics),
	}
	writeJSON(filepath.Join(planDir, "summary.json"), summary)
}
