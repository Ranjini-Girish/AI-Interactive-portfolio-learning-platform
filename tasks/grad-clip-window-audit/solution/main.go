package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

func getenv(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func round6(x float64) float64 {
	return math.Round(x*1e6) / 1e6
}

// pyFloat marshals whole-number floats with a trailing ".0" like Python json.
type pyFloat float64

func (f pyFloat) MarshalJSON() ([]byte, error) {
	v := float64(f)
	if v == 0 {
		return []byte("0"), nil
	}
	if v == float64(int64(v)) {
		return []byte(fmt.Sprintf("%.1f", v)), nil
	}
	return []byte(strconv.FormatFloat(v, 'f', -1, 64)), nil
}

func canonicalJSON(v any) []byte {
	var buf bytes.Buffer
	enc := json.NewEncoder(&buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		panic(err)
	}
	out := buf.Bytes()
	for len(out) > 0 && out[len(out)-1] == '\n' {
		out = out[:len(out)-1]
	}
	return append(out, '\n')
}

func writeJSON(path string, v any) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(path, canonicalJSON(v), 0o644); err != nil {
		panic(err)
	}
}

func readJSON(path string, out any) {
	b, err := os.ReadFile(path)
	if err != nil {
		panic(err)
	}
	if err := json.Unmarshal(b, out); err != nil {
		panic(fmt.Sprintf("%s: %v", path, err))
	}
}

func main() {
	dataDir := getenv("GCW_DATA_DIR", "/app/gradclip")
	auditDir := getenv("GCW_AUDIT_DIR", "/app/audit")

	var policy struct {
		WindowSize   int     `json:"window_size"`
		ClipCap      float64 `json:"clip_cap"`
		WarmupSteps  int     `json:"warmup_steps"`
		QuorumRatio  float64 `json:"quorum_ratio"`
	}
	readJSON(filepath.Join(dataDir, "policy.json"), &policy)

	var manifest struct {
		MonitorTag string `json:"monitor_tag"`
		RunTag     string `json:"run_tag"`
	}
	readJSON(filepath.Join(dataDir, "manifest.json"), &manifest)

	var epochs struct {
		CurrentEpoch int `json:"current_epoch"`
	}
	readJSON(filepath.Join(dataDir, "epochs.json"), &epochs)

	var stepsDoc struct {
		Steps []struct {
			Step     int     `json:"step"`
			ShardID  string  `json:"shard_id"`
			GradNorm float64 `json:"grad_norm"`
			Sign     string  `json:"sign"`
		} `json:"steps"`
	}
	readJSON(filepath.Join(dataDir, "steps.json"), &stepsDoc)

	window := policy.WindowSize
	clipCap := policy.ClipCap
	warmup := policy.WarmupSteps
	quorumRatio := policy.QuorumRatio
	currentEpoch := epochs.CurrentEpoch

	if manifest.MonitorTag != manifest.RunTag {
		clipCap = math.Max(1.0, clipCap*0.5)
	}

	shardPaths, err := filepath.Glob(filepath.Join(dataDir, "shards", "*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(shardPaths)

	shards := map[string]struct {
		ShardID string  `json:"shard_id"`
		Epoch   int     `json:"epoch"`
		Weight  float64 `json:"weight"`
	}{}
	for _, p := range shardPaths {
		var row struct {
			ShardID string  `json:"shard_id"`
			Epoch   int     `json:"epoch"`
			Weight  float64 `json:"weight"`
		}
		readJSON(p, &row)
		shards[row.ShardID] = row
	}

	active := map[string]struct{}{}
	var totalWeight float64
	for sid, row := range shards {
		if row.Epoch >= currentEpoch-1 {
			active[sid] = struct{}{}
			totalWeight += row.Weight
		}
	}

	steps := append([]struct {
		Step     int
		ShardID  string
		GradNorm float64
		Sign     string
	}{}, make([]struct {
		Step     int
		ShardID  string
		GradNorm float64
		Sign     string
	}, len(stepsDoc.Steps))...)
	for i, s := range stepsDoc.Steps {
		steps[i] = struct {
			Step     int
			ShardID  string
			GradNorm float64
			Sign     string
		}{s.Step, s.ShardID, s.GradNorm, s.Sign}
	}
	sort.Slice(steps, func(i, j int) bool {
		if steps[i].Step != steps[j].Step {
			return steps[i].Step < steps[j].Step
		}
		return steps[i].ShardID < steps[j].ShardID
	})

	history := map[string][]float64{}
	for sid := range shards {
		history[sid] = nil
	}

	var clipRows, voteRows, windowRows []map[string]any
	accepted, clipped, staleSkipped := 0, 0, 0

	for _, st := range steps {
		step, sid, norm, sign := st.Step, st.ShardID, st.GradNorm, st.Sign
		_, inActive := active[sid]
		stale := !inActive
		if stale {
			staleSkipped++
		}

		hist := history[sid]
		hist = append(hist, norm)
		if len(hist) > window {
			hist = hist[len(hist)-window:]
		}
		history[sid] = hist

		var sum float64
		for _, v := range hist {
			sum += v
		}
		windowMean := sum / float64(len(hist))

		var factor float64
		clippedFlag := false
		if step <= warmup {
			factor = 1.0
		} else if norm > 0 {
			factor = math.Min(1.0, clipCap/norm)
			clippedFlag = factor < 1.0
		} else {
			factor = 1.0
		}

		if !stale {
			clipRows = append(clipRows, map[string]any{
				"clip_factor": pyFloat(round6(factor)),
				"clipped":     clippedFlag,
				"grad_norm":   pyFloat(norm),
				"shard_id":    sid,
				"step":        step,
			})
		}

		var agreeWeight float64
		for _, x := range steps {
			if x.Step == step && x.Sign == sign {
				if _, ok := active[x.ShardID]; ok {
					agreeWeight += shards[x.ShardID].Weight
				}
			}
		}
		acceptedFlag := !stale && totalWeight > 0 && agreeWeight >= quorumRatio*totalWeight
		if acceptedFlag {
			accepted++
		}
		if clippedFlag && !stale {
			clipped++
		}

		voteRows = append(voteRows, map[string]any{
			"accepted":     acceptedFlag,
			"agree_weight": pyFloat(round6(agreeWeight)),
			"shard_id":     sid,
			"sign":         sign,
			"step":         step,
			"stale":        stale,
		})
		windowRows = append(windowRows, map[string]any{
			"shard_id":         sid,
			"step":             step,
			"window_mean_norm": pyFloat(round6(windowMean)),
			"window_size":      len(hist),
		})
	}

	var shardIDs []string
	for sid := range shards {
		shardIDs = append(shardIDs, sid)
	}
	sort.Strings(shardIDs)

	var shardStates []map[string]any
	for _, sid := range shardIDs {
		row := shards[sid]
		_, inActive := active[sid]
		shardStates = append(shardStates, map[string]any{
			"epoch":    row.Epoch,
			"shard_id": sid,
			"stale":    !inActive,
			"weight":   pyFloat(row.Weight),
		})
	}

	writeJSON(filepath.Join(auditDir, "shard_states.json"), map[string]any{"shards": shardStates})
	writeJSON(filepath.Join(auditDir, "clip_plan.json"), map[string]any{"entries": clipRows})
	writeJSON(filepath.Join(auditDir, "quorum_votes.json"), map[string]any{"votes": voteRows})
	writeJSON(filepath.Join(auditDir, "window_stats.json"), map[string]any{"windows": windowRows})
	writeJSON(filepath.Join(auditDir, "summary.json"), map[string]any{
		"accepted_total":      accepted,
		"clipped_total":       clipped,
		"current_epoch":       currentEpoch,
		"effective_clip_cap":  pyFloat(round6(clipCap)),
		"stale_skipped_total": staleSkipped,
		"step_total":          len(steps),
	})
}
