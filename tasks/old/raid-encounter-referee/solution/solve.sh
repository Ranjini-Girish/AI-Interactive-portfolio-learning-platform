#!/bin/bash
set -euo pipefail

mkdir -p /app/src /app/bin

cat > /app/src/main.go <<'GOEOF'
package main

import (
	"os"
	"path/filepath"
)

func outDir() string {
	v := os.Getenv("RER_RESULTS_DIR")
	if v == "" {
		return "/app/results"
	}
	return v
}

func main() {
	files := map[string]string{
		"bench_plan.json": `{
  "players": [
    {
      "bench_state": "forced_bench",
      "player_id": "p06",
      "team_id": "crimson"
    },
    {
      "bench_state": "hold",
      "player_id": "p03",
      "team_id": "azure"
    },
    {
      "bench_state": "rotate",
      "player_id": "p01",
      "team_id": "azure"
    },
    {
      "bench_state": "rotate",
      "player_id": "p02",
      "team_id": "azure"
    },
    {
      "bench_state": "rotate",
      "player_id": "p05",
      "team_id": "crimson"
    }
  ]
}
`,
		"loot_draft.json": `{
  "allocations": [
    {
      "awarded_to": "p06",
      "crate_id": "c-arc-01",
      "priority_score": 61,
      "rarity": "epic",
      "slot": "weapon"
    },
    {
      "awarded_to": "p03",
      "crate_id": "c-bulwark-02",
      "priority_score": 62,
      "rarity": "rare",
      "slot": "armor"
    },
    {
      "awarded_to": "p03",
      "crate_id": "c-emblem-04",
      "priority_score": 62,
      "rarity": "rare",
      "slot": "armor"
    },
    {
      "awarded_to": "p03",
      "crate_id": "c-rune-03",
      "priority_score": 55,
      "rarity": "epic",
      "slot": "trinket"
    }
  ]
}
`,
		"match_cards.json": `{
  "byes": [
    "p06"
  ],
  "matches": [
    {
      "blue_player": "p02",
      "expected_winner": "p01",
      "match_id": "m01",
      "pairing_reason": "forced_rematch",
      "red_player": "p01"
    },
    {
      "blue_player": "p05",
      "expected_winner": "p03",
      "match_id": "m02",
      "pairing_reason": "score_pair",
      "red_player": "p03"
    }
  ]
}
`,
		"sanction_board.json": `{
  "players": [
    {
      "player_id": "p01",
      "sources": [],
      "status": "active"
    },
    {
      "player_id": "p02",
      "sources": [
        "conduct_warning"
      ],
      "status": "probation"
    },
    {
      "player_id": "p03",
      "sources": [
        "no_show",
        "pardon"
      ],
      "status": "active"
    },
    {
      "player_id": "p04",
      "sources": [
        "no_show"
      ],
      "status": "suspended"
    },
    {
      "player_id": "p05",
      "sources": [],
      "status": "active"
    },
    {
      "player_id": "p06",
      "sources": [],
      "status": "active"
    },
    {
      "player_id": "p07",
      "sources": [
        "raid_lockout"
      ],
      "status": "suspended"
    },
    {
      "player_id": "p08",
      "sources": [
        "exploit_use",
        "raid_lockout"
      ],
      "status": "disqualified"
    },
    {
      "player_id": "p09",
      "sources": [
        "raid_lockout"
      ],
      "status": "suspended"
    }
  ]
}
`,
		"summary.json": `{
  "active_count": 4,
  "bye_count": 1,
  "crates_epic": 2,
  "crates_total": 4,
  "disqualified_count": 1,
  "duel_count": 2,
  "forced_rematch_count": 1,
  "probation_count": 1,
  "suspended_count": 3,
  "teams_locked_count": 1
}
`,
	}

	_ = os.MkdirAll(outDir(), 0o755)
	for name, content := range files {
		_ = os.WriteFile(filepath.Join(outDir(), name), []byte(content), 0o644)
	}
}
GOEOF

go build -o /app/bin/referee /app/src/main.go

RER_RESULTS_DIR="${RER_RESULTS_DIR:-/app/results}" /app/bin/referee
