package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
)

type policyFile struct {
	ChainMaxHops      int            `json:"chain_max_hops"`
	CurrentDay        int            `json:"current_day"`
	HotCooloffDays    int            `json:"hot_cooloff_days"`
	PartyTier         string         `json:"party_tier"`
	RearmCooldownDays int            `json:"rearm_cooldown_days"`
	TierDisarmCap     map[string]int `json:"tier_disarm_cap"`
}

type incidentFile struct {
	Events []struct {
		Day    int    `json:"day"`
		Kind   string `json:"kind"`
		RoomID string `json:"room_id"`
		TrapID string `json:"trap_id"`
	} `json:"events"`
}

type linksFile struct {
	Edges []struct {
		A string `json:"a"`
		B string `json:"b"`
	} `json:"edges"`
}

type roomsFile struct {
	Rooms []struct {
		RoomID  string   `json:"room_id"`
		TrapIDs []string `json:"trap_ids"`
	} `json:"rooms"`
}

type trapFile struct {
	Armed           bool `json:"armed"`
	Difficulty      int  `json:"difficulty"`
	InitialPulse    bool `json:"initial_pulse"`
	LastTriggerDay  *int `json:"last_trigger_day"`
	RoomID          string `json:"room_id"`
	TrapID          string `json:"trap_id"`
}

type trapState struct {
	Armed          bool
	Difficulty     int
	InitialPulse   bool
	LastTriggerDay *int
	RoomID         string
	TrapID         string
	Sealed         bool
	Triggered      bool
	ChainHops      int
	FinalState     string
	DisarmStatus   string
}

func readJSON(path string, dst any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, dst); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func jsonString(s string) string {
	var b bytes.Buffer
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '"':
			b.WriteString(`\"`)
		case '\\':
			b.WriteString(`\\`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			if r < 0x20 {
				b.WriteString(fmt.Sprintf(`\u%04x`, r))
			} else {
				b.WriteRune(r)
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}

func writeCanonical(w *bytes.Buffer, v any, indent int) {
	sp := bytes.Repeat([]byte(" "), indent)
	switch t := v.(type) {
	case nil:
		w.WriteString("null")
	case bool:
		if t {
			w.WriteString("true")
		} else {
			w.WriteString("false")
		}
	case int:
		w.WriteString(strconv.Itoa(t))
	case string:
		w.WriteString(jsonString(t))
	case []any:
		if len(t) == 0 {
			w.WriteString("[]")
			return
		}
		w.WriteString("[\n")
		for i, it := range t {
			w.Write(sp)
			w.WriteString("  ")
			writeCanonical(w, it, indent+2)
			if i+1 < len(t) {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.Write(sp)
		w.WriteByte(']')
	case map[string]any:
		if len(t) == 0 {
			w.WriteString("{}")
			return
		}
		keys := make([]string, 0, len(t))
		for k := range t {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		w.WriteString("{\n")
		for i, k := range keys {
			w.Write(sp)
			w.WriteString("  ")
			w.WriteString(jsonString(k))
			w.WriteString(": ")
			writeCanonical(w, t[k], indent+2)
			if i+1 < len(keys) {
				w.WriteString(",\n")
			} else {
				w.WriteByte('\n')
			}
		}
		w.Write(sp)
		w.WriteByte('}')
	default:
		panic(fmt.Sprintf("unsupported type %T", v))
	}
}

func writeJSONFile(path string, root map[string]any) {
	var buf bytes.Buffer
	writeCanonical(&buf, root, 0)
	buf.WriteByte('\n')
	if err := os.WriteFile(path, buf.Bytes(), 0o644); err != nil {
		panic(err)
	}
}

func neighbors(id string, adj map[string][]string) []string {
	ns := append([]string{}, adj[id]...)
	sort.Strings(ns)
	return ns
}

func main() {
	dataDir := os.Getenv("TGC_DATA_DIR")
	if dataDir == "" {
		dataDir = "/app/trapgrid"
	}
	auditDir := os.Getenv("TGC_AUDIT_DIR")
	if auditDir == "" {
		auditDir = "/app/audit"
	}
	if err := os.MkdirAll(auditDir, 0o755); err != nil {
		panic(err)
	}

	var pol policyFile
	readJSON(filepath.Join(dataDir, "policy.json"), &pol)

	var inc incidentFile
	readJSON(filepath.Join(dataDir, "incidents.json"), &inc)

	var links linksFile
	readJSON(filepath.Join(dataDir, "links.json"), &links)

	var rooms roomsFile
	readJSON(filepath.Join(dataDir, "rooms.json"), &rooms)

	traps := map[string]*trapState{}
	entries, err := os.ReadDir(filepath.Join(dataDir, "traps"))
	if err != nil {
		panic(err)
	}
	for _, ent := range entries {
		if ent.IsDir() || filepath.Ext(ent.Name()) != ".json" {
			continue
		}
		var tf trapFile
		readJSON(filepath.Join(dataDir, "traps", ent.Name()), &tf)
		traps[tf.TrapID] = &trapState{
			Armed:          tf.Armed,
			Difficulty:     tf.Difficulty,
			InitialPulse:   tf.InitialPulse,
			LastTriggerDay: tf.LastTriggerDay,
			RoomID:         tf.RoomID,
			TrapID:         tf.TrapID,
			ChainHops:      -1,
		}
	}

	sealedRooms := map[string]struct{}{}
	forcePulse := map[string]struct{}{}
	boost := false
	type incRow struct {
		day    int
		kind   string
		roomID string
		trapID string
	}
	var applied []incRow
	for _, ev := range inc.Events {
		if ev.Day > pol.CurrentDay {
			continue
		}
		switch ev.Kind {
		case "room_seal":
			sealedRooms[ev.RoomID] = struct{}{}
			applied = append(applied, incRow{ev.Day, ev.Kind, ev.RoomID, ""})
		case "force_pulse":
			forcePulse[ev.TrapID] = struct{}{}
			applied = append(applied, incRow{ev.Day, ev.Kind, "", ev.TrapID})
		case "disarm_boost":
			if ev.Day == pol.CurrentDay {
				boost = true
			}
			applied = append(applied, incRow{ev.Day, ev.Kind, "", ""})
		}
	}

	for _, st := range traps {
		if _, ok := sealedRooms[st.RoomID]; ok {
			st.Sealed = true
		}
	}

	effectiveCap := pol.TierDisarmCap[pol.PartyTier]
	if boost {
		effectiveCap++
	}

	adj := map[string][]string{}
	for _, e := range links.Edges {
		adj[e.A] = append(adj[e.A], e.B)
		adj[e.B] = append(adj[e.B], e.A)
	}

	onCooldown := func(st *trapState) bool {
		if st.LastTriggerDay == nil {
			return false
		}
		return pol.CurrentDay-*st.LastTriggerDay < pol.RearmCooldownDays
	}

	forced := func(id string) bool {
		_, ok := forcePulse[id]
		return ok
	}

	var wave0 []string
	for id, st := range traps {
		if st.Sealed || !st.Armed {
			continue
		}
		want := st.InitialPulse || forced(id)
		if !want {
			continue
		}
		if onCooldown(st) && !forced(id) {
			continue
		}
		wave0 = append(wave0, id)
	}
	sort.Strings(wave0)

	triggered := map[string]int{}
	for _, id := range wave0 {
		triggered[id] = 0
		traps[id].ChainHops = 0
	}

	waves := [][]string{wave0}
	prev := wave0
	for hop := 1; hop <= pol.ChainMaxHops; hop++ {
		var nxt []string
		seen := map[string]struct{}{}
		for _, id := range prev {
			for _, nb := range neighbors(id, adj) {
				if _, ok := seen[nb]; ok {
					continue
				}
				st, ok := traps[nb]
				if !ok || st.Sealed || !st.Armed {
					continue
				}
				if _, already := triggered[nb]; already {
					continue
				}
				seen[nb] = struct{}{}
				nxt = append(nxt, nb)
			}
		}
		if len(nxt) == 0 {
			break
		}
		sort.Strings(nxt)
		for _, id := range nxt {
			triggered[id] = hop
			traps[id].ChainHops = hop
		}
		waves = append(waves, nxt)
		prev = nxt
	}

	for _, st := range traps {
		if st.Sealed {
			st.FinalState = "sealed"
			continue
		}
		if _, ok := triggered[st.TrapID]; ok {
			st.Triggered = true
			st.FinalState = "triggered"
			continue
		}
		if st.Armed && st.InitialPulse && onCooldown(st) && !forced(st.TrapID) {
			st.FinalState = "cooldown_suppressed"
			continue
		}
		if !st.Armed {
			st.FinalState = "disarmed_idle"
			continue
		}
		st.FinalState = "armed_idle"
	}

	triggerDay := func(st *trapState) int {
		if st.LastTriggerDay != nil {
			return *st.LastTriggerDay
		}
		return pol.CurrentDay
	}

	ids := make([]string, 0, len(traps))
	for id := range traps {
		ids = append(ids, id)
	}
	sort.Strings(ids)

	disarmedTotal := 0
	cooldownSuppressed := 0
	triggeredTotal := 0
	sealedTotal := 0

	disarmEntries := make([]any, 0, len(ids))
	for _, id := range ids {
		st := traps[id]
		switch st.FinalState {
		case "sealed":
			sealedTotal++
		case "triggered":
			triggeredTotal++
		case "cooldown_suppressed":
			cooldownSuppressed++
		}

		status := "disarmed"
		if st.Sealed {
			status = "blocked_sealed"
		} else if !st.Armed {
			status = "not_applicable"
		} else if st.FinalState == "triggered" {
			if pol.CurrentDay-triggerDay(st) < pol.HotCooloffDays {
				status = "blocked_hot"
			} else if st.Difficulty > effectiveCap {
				status = "blocked_difficulty"
			} else {
				status = "disarmed"
			}
		} else if st.Difficulty > effectiveCap {
			status = "blocked_difficulty"
		} else {
			status = "disarmed"
		}
		st.DisarmStatus = status
		if status == "disarmed" {
			disarmedTotal++
		}
		disarmEntries = append(disarmEntries, map[string]any{
			"difficulty":     st.Difficulty,
			"disarm_status":  status,
			"trap_id":        id,
		})
	}

	roomTrapIDs := map[string][]string{}
	for _, rm := range rooms.Rooms {
		roomTrapIDs[rm.RoomID] = append([]string{}, rm.TrapIDs...)
	}

	hazardousRooms := 0
	roomRows := make([]any, 0, len(rooms.Rooms))
	for _, rm := range rooms.Rooms {
		rid := rm.RoomID
		status := "partial"
		if _, sealed := sealedRooms[rid]; sealed {
			status = "sealed"
		} else {
			haz := false
			allIdle := true
			for _, tid := range rm.TrapIDs {
				st, ok := traps[tid]
				if !ok {
					continue
				}
				if st.FinalState == "triggered" {
					haz = true
				}
				if st.FinalState != "armed_idle" && st.FinalState != "disarmed_idle" {
					allIdle = false
				}
			}
			if haz {
				status = "hazardous"
				hazardousRooms++
			} else if allIdle {
				status = "cleared"
			}
		}
		roomRows = append(roomRows, map[string]any{
			"room_id": rid,
			"status":  status,
		})
	}
	sort.Slice(roomRows, func(i, j int) bool {
		return roomRows[i].(map[string]any)["room_id"].(string) < roomRows[j].(map[string]any)["room_id"].(string)
	})

	trapRows := make([]any, 0, len(ids))
	for _, id := range ids {
		st := traps[id]
		trapRows = append(trapRows, map[string]any{
			"chain_hops":   st.ChainHops,
			"difficulty":   st.Difficulty,
			"final_state":  st.FinalState,
			"room_id":      st.RoomID,
			"trap_id":      id,
		})
	}

	waveAny := make([]any, 0, len(waves))
	for _, w := range waves {
		row := make([]any, len(w))
		for i, id := range w {
			row[i] = id
		}
		waveAny = append(waveAny, row)
	}

	writeJSONFile(filepath.Join(auditDir, "trap_states.json"), map[string]any{
		"current_day": pol.CurrentDay,
		"traps":       trapRows,
	})
	writeJSONFile(filepath.Join(auditDir, "trigger_plan.json"), map[string]any{
		"waves": waveAny,
	})
	writeJSONFile(filepath.Join(auditDir, "disarm_plan.json"), map[string]any{
		"effective_disarm_cap": effectiveCap,
		"entries":              disarmEntries,
	})
	writeJSONFile(filepath.Join(auditDir, "room_status.json"), map[string]any{
		"rooms": roomRows,
	})
	writeJSONFile(filepath.Join(auditDir, "summary.json"), map[string]any{
		"cooldown_suppressed_total": cooldownSuppressed,
		"current_day":               pol.CurrentDay,
		"disarmed_total":            disarmedTotal,
		"hazardous_rooms":           hazardousRooms,
		"sealed_total":              sealedTotal,
		"trap_total":                len(traps),
		"triggered_total":           triggeredTotal,
	})

	_ = applied
}
