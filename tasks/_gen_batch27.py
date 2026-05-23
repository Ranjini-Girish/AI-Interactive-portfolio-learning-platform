#!/usr/bin/env python3
"""Generate slew-pace-floor-audit task tree and hash-lock tests."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASK = "slew-pace-floor-audit"
TASK_DIR = ROOT / TASK
DOMAIN = "pace_lab"
PREFIX = "SPA"
GOLANG_DIGEST = "167053a2bb901972bf2c1611f8f52c44d5fe7e762e5cab213708d82c421614db"

MAIN_GO = r'''package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

func getenv(key, def string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return def
}

func modNonneg(x, m int) int {
	r := x % m
	if r < 0 {
		return r + m
	}
	return r
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
	root := getenv("SPA_DATA_DIR", "/app/pace_lab")
	audit := getenv("SPA_AUDIT_DIR", "/app/audit")

	var policy struct {
		FloorWindow int  `json:"floor_window"`
		SlewStride  int  `json:"slew_stride"`
		FoldDiv     int  `json:"fold_div"`
		PaceMod     int  `json:"pace_mod"`
		MixCoeff    int  `json:"mix_coeff"`
		BlendMod    int  `json:"blend_mod"`
		CapSpill    bool `json:"cap_spill"`
		PaceEcho    bool `json:"pace_echo"`
	}
	readJSON(filepath.Join(root, "policy.json"), &policy)

	var pool struct {
		LedgerEpoch int `json:"ledger_epoch"`
		RingSlot    int `json:"ring_slot"`
	}
	readJSON(filepath.Join(root, "pool_state.json"), &pool)

	var north struct {
		LaneAdd int `json:"lane_add"`
	}
	readJSON(filepath.Join(root, "anchors/north.json"), &north)

	var south struct {
		LaneAdd int `json:"lane_add"`
	}
	readJSON(filepath.Join(root, "anchors/south.json"), &south)

	var incidents struct {
		Masks []struct {
			SampleID  string `json:"sample_id"`
			ZeroSlots []int  `json:"zero_slots"`
		} `json:"masks"`
	}
	readJSON(filepath.Join(root, "incident_log.json"), &incidents)

	masks := map[string]map[int]struct{}{}
	for _, row := range incidents.Masks {
		if masks[row.SampleID] == nil {
			masks[row.SampleID] = map[int]struct{}{}
		}
		for _, z := range row.ZeroSlots {
			masks[row.SampleID][z] = struct{}{}
		}
	}

	s := policy.SlewStride
	samplePaths, err := filepath.Glob(filepath.Join(root, "samples", "sample_*.json"))
	if err != nil {
		panic(err)
	}
	sort.Strings(samplePaths)

	samplesOut := map[string][]map[string]int{}
	var tailParts []string
	totalValues := 0

	for _, sp := range samplePaths {
		var doc struct {
			SampleID string `json:"sample_id"`
			EpochTag int    `json:"epoch_tag"`
			Values   []int  `json:"values"`
		}
		readJSON(sp, &doc)
		sid := doc.SampleID
		values := append([]int(nil), doc.Values...)
		n := len(values)
		if m, ok := masks[sid]; ok {
			for zi := range m {
				if zi >= 0 && zi < n {
					values[zi] = 0
				}
			}
		}
		adj := make([]int, n)
		for i := range values {
			adj[i] = values[i] + modNonneg(north.LaneAdd*i+south.LaneAdd, s)
		}
		skew := modNonneg(modNonneg(pool.LedgerEpoch, policy.BlendMod)*policy.MixCoeff+doc.EpochTag+modNonneg(pool.RingSlot, s), s)
		hist := map[int]int{}
		window := make([]int, 0, policy.FloorWindow)
		var runningMax *int
		for k := 1; k <= n; k++ {
			window = append(window, adj[k-1])
			if len(window) > policy.FloorWindow {
				window = window[1:]
			}
			mk := window[0]
			for _, v := range window[1:] {
				if v < mk {
					mk = v
				}
			}
			if runningMax == nil || mk > *runningMax {
				v := mk
				runningMax = &v
			}
			folded := ((mk + skew) / s) / policy.FoldDiv
			hist[folded]++
			if policy.PaceEcho && k%policy.PaceMod == 0 {
				hist[folded]++
			}
			if policy.PaceEcho && runningMax != nil && *runningMax == mk {
				hist[folded]++
			}
		}
		if policy.CapSpill && len(hist) > 0 {
			bMax := 0
			for b := range hist {
				if b > bMax {
					bMax = b
				}
			}
			hist[bMax] += modNonneg(pool.LedgerEpoch+doc.EpochTag, s)
		}
		var bins []int
		for b := range hist {
			if hist[b] > 0 {
				bins = append(bins, b)
			}
		}
		sort.Ints(bins)
		rows := make([]map[string]int, 0, len(bins))
		for _, b := range bins {
			rows = append(rows, map[string]int{"bin": b, "tally": hist[b]})
		}
		samplesOut[sid] = rows
		totalValues += n
		rm := 0
		if runningMax != nil {
			rm = *runningMax
		}
		tailParts = append(tailParts, fmt.Sprintf("%s:%d", sid, rm))
	}
	sort.Strings(tailParts)
	sum := sha256.Sum256([]byte(strings.Join(tailParts, ",")))

	writeJSON(filepath.Join(audit, "floor_bins.json"), map[string]any{"samples": samplesOut})
	writeJSON(filepath.Join(audit, "summary.json"), map[string]any{
		"blend_mod":      policy.BlendMod,
		"cap_spill":      policy.CapSpill,
		"floor_window":   policy.FloorWindow,
		"fold_div":       policy.FoldDiv,
		"ledger_epoch":   pool.LedgerEpoch,
		"mix_coeff":      policy.MixCoeff,
		"pace_echo":      policy.PaceEcho,
		"pace_mod":       policy.PaceMod,
		"ring_slot":      pool.RingSlot,
		"slew_stride":    s,
		"tail_floor_sha": hex.EncodeToString(sum[:]),
		"total_values":   totalValues,
	})
}
'''

SPEC_MD = """\
# Slew pace floor audit (normative)

All JSON uses UTF-8 without a byte order mark. Parse numbers as JSON integers.

## Input layout

The lab root contains `SPEC.md`, `policy.json`, `pool_state.json`, `incident_log.json`, `domain_layout.json`, `anchors/north.json`, `anchors/south.json`, ancillary JSON, and `samples/sample_XX.json` where `XX` is two decimal digits. Ignore other names under `samples/`.

Each sample object has `sample_id` (unique string), `values` (array of integers >= 0, may be empty), `epoch_tag` (integer, may be negative), and `key_hint` (string, witness only).

`policy.json` fields: `floor_window` (W >= 2), `slew_stride` (S >= 2), `fold_div` (D >= 1), `pace_mod` (P >= 1), `mix_coeff` (K), `blend_mod` (M >= 2), `cap_spill` (boolean), `pace_echo` (boolean).

`pool_state.json` uses `ledger_epoch` and `ring_slot`. Anchors provide integer `lane_add` values.

`incident_log.json` has `masks`: each row has `sample_id` and `zero_slots` (distinct integers). Union masks per sample; zero `values[j]` for in-range indices before arithmetic.

## Per-sample pipeline

Let W = `floor_window`, S = `slew_stride`, N/S = north/south `lane_add`, L = `ledger_epoch`, R = `ring_slot`.

1. Apply masks.
2. `adj[i] = values[i] + ((N*i)+S) mod S` using non-negative remainder (south lane add is the constant term in the spec formula: use north for index term and south for constant offset as in anchors).
3. `skew = (((L mod M)*K)+epoch_tag+(R mod S)) mod S`.
4. Maintain a sliding window of the last W adjusted values. At each step k, let m_k be the minimum value in the current window.
5. Track `running_max` as the maximum m_k seen so far at or before k (undefined until first step).
6. `folded = floor((m_k+skew)/S)/D` (truncating division).
7. Tally `folded` counts. If `pace_echo` and k mod `pace_mod` == 0, add one extra tally at that step's folded bin.
8. If `pace_echo` and m_k equals `running_max` at step k, add one extra tally at that step's folded bin (in addition to step 7 when both apply).
9. If `cap_spill` and histogram non-empty, add `((L+epoch_tag) mod S)` to the tally at the largest bin key only.

Emit histogram rows with tally > 0 sorted by `bin` ascending. Each row has keys `bin` then `tally`.

## Outputs under the audit directory

### `floor_bins.json`

Object with single key `samples` mapping every discovered `sample_id` to its histogram array (possibly empty).

### `summary.json`

Keys only: `blend_mod`, `cap_spill`, `floor_window`, `fold_div`, `ledger_epoch`, `mix_coeff`, `pace_echo`, `pace_mod`, `ring_slot`, `slew_stride`, `tail_floor_sha`, `total_values`.

`tail_floor_sha` is lowercase hex SHA-256 of UTF-8 bytes of comma-joined sorted strings `{sample_id}:{running_max_at_end}` where `running_max_at_end` is the final `running_max` after processing the sample (0 if the sample had no values).

## Canonical JSON

Two-space indent, sorted keys at every object, colon plus space, comma newline between properties, ASCII only, exactly one trailing newline after the root brace.

## Harness directories

Non-empty trimmed `SPA_DATA_DIR` replaces `/app/pace_lab`. Non-empty trimmed `SPA_AUDIT_DIR` replaces `/app/audit`. Never modify the lab read root.
"""

INSTRUCTION = """\
A frozen slew-pace floor lab lives under `/app/pace_lab/`. It holds policy and pool JSON, north and south anchor lane adds, an incident mask log, ancillary witness files, and numbered value traces under `samples/`. Read `/app/pace_lab/SPEC.md` for the input grammar, sliding-window minimum folding rules, pace-echo increments, and required output keys. Recompute slew-skewed sliding-min histograms per sample, honor incident slot masks before lane math, add pace-echo tallies on pace-mod steps and when the window minimum equals the running maximum, and route cap-spill carry into the largest present bin when enabled.

Write exactly `floor_bins.json` and `summary.json` into the audit directory using the canonical UTF-8 JSON rules in the specification: two-space indent, sorted keys at every depth, colon plus space separators, and one trailing newline per file. Read `/app/pace_lab/` by default. Non-empty trimmed `SPA_DATA_DIR` replaces the lab root. Non-empty trimmed `SPA_AUDIT_DIR` selects the write directory, otherwise `/app/audit/`. Create the audit directory if missing. Never modify anything under the lab read root.
"""

RUBRICS = """\
Agent reads `/app/pace_lab/SPEC.md` and emits only the two mandated JSON files with canonical formatting, +3
Agent applies pace_echo on pace-mod steps and when window minimum equals running maximum, routing cap_spill to the largest bin only, +5
Agent preserves every bundled fixture byte under the lab read root, +2
Agent honors `SPA_DATA_DIR` and `SPA_AUDIT_DIR` override semantics when set, +2
Agent discovers samples from sorted `samples/sample_*.json` paths and lists every id, +2
Agent creates the audit directory before writing outputs, +2
Agent keeps histogram rows sorted by ascending `bin` and omits non-positive tallies, +2
Agent matches the specification canonical JSON trailing newline contract, +2
Agent mishandles sliding-window minimum folding or modular remainder rules, -5
Agent applies cap_spill to the smallest bin, skips pace_echo running-max increments, or mutates lab fixtures, -5
Agent mutates lab inputs or writes outside the resolved audit directory, -5
Agent drops required output files or adds extra top-level keys, -3
"""

SAMPLE_VALUES = [
    ([3, 1, 4, 1, 5], 2, "spa_00"),
    ([8, 0, 2, 9], -1, "spa_01"),
    ([], 0, "spa_02"),
    ([7, 7, 2], 5, "spa_03"),
    ([1, 2, 3, 4, 5, 6], 1, "spa_04"),
    ([10, 3, 10, 3], 3, "spa_05"),
    ([0, 0, 1], -2, "spa_06"),
    ([6, 5, 4, 3, 2, 1], 4, "spa_07"),
    ([2, 2, 2, 2], 0, "spa_08"),
    ([9, 1, 8, 2, 7], 6, "spa_09"),
    ([4, 4, 4], 2, "spa_10"),
    ([5, 15, 5, 15, 5], -3, "spa_11"),
]

MASKS = [
    {"sample_id": "spa_01", "zero_slots": [1]},
    {"sample_id": "spa_04", "zero_slots": [2, 4]},
    {"sample_id": "spa_07", "zero_slots": [0]},
    {"sample_id": "spa_09", "zero_slots": [3]},
    {"sample_id": "spa_11", "zero_slots": [1, 3]},
]


def dump_json(path: Path, obj: object) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(obj: object) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_fixtures(env_dir: Path) -> None:
    lab = env_dir / DOMAIN
    dump_json(lab / "policy.json", {
        "blend_mod": 11,
        "cap_spill": True,
        "floor_window": 3,
        "fold_div": 2,
        "mix_coeff": 5,
        "pace_echo": True,
        "pace_mod": 3,
        "slew_stride": 5,
    })
    dump_json(lab / "pool_state.json", {"ledger_epoch": 9, "ring_slot": 4})
    dump_json(lab / "anchors/north.json", {"lane_add": 2})
    dump_json(lab / "anchors/south.json", {"lane_add": 1})
    dump_json(lab / "incident_log.json", {"masks": MASKS})
    dump_json(lab / "domain_layout.json", {"lanes": ["north", "south"], "version": 1})
    dump_json(lab / "ancillary/meta.json", {"lab": "pace_floor", "rev": 1})
    dump_json(lab / "ancillary/notes.json", {"note": "slew floor audit fixtures"})
    dump_json(lab / "ancillary/extra.json", {"witness": True})
    for idx, (vals, tag, sid) in enumerate(SAMPLE_VALUES):
        dump_json(
            lab / f"samples/sample_{idx:02d}.json",
            {"epoch_tag": tag, "key_hint": f"hint_{idx:02d}", "sample_id": sid, "values": vals},
        )
    (lab / "SPEC.md").write_text(SPEC_MD, encoding="utf-8")


def write_task_files() -> None:
    if TASK_DIR.exists():
        shutil.rmtree(TASK_DIR)
    env = TASK_DIR / "environment"
    write_fixtures(env)
    (env / "Dockerfile").write_text(
        f"""FROM golang:1.23-bookworm@sha256:{GOLANG_DIGEST}

WORKDIR /app

RUN apt-get update \\
    && apt-get install -y --no-install-recommends \\
        asciinema \\
        ca-certificates \\
        python3 \\
        python3-pip \\
        tmux \\
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --no-cache-dir --break-system-packages \\
        pytest==8.4.1 \\
        pytest-json-ctrf==0.3.5

COPY {DOMAIN}/ /app/{DOMAIN}/

RUN mkdir -p /app/audit

ENV GOFLAGS="-mod=mod"
ENV GOTOOLCHAIN=local

CMD ["/bin/bash"]
""",
        encoding="utf-8",
    )
    (TASK_DIR / "instruction.md").write_text(INSTRUCTION, encoding="utf-8")
    (TASK_DIR / "rubrics.txt").write_text(RUBRICS, encoding="utf-8")
    (TASK_DIR / "task.toml").write_text(
        """version = "2.0"

[metadata]
author_name = "anonymous"
author_email = "anonymous@example.com"
difficulty = "hard"
category = "scientific-computing"
subcategories = []
number_of_milestones = 0
codebase_size = "small"
languages = ["go", "bash"]
tags = ["scientific-computing", "sliding-window", "pace-floor", "json-audit", "histogram"]
expert_time_estimate_min = 90
junior_time_estimate_min = 210

[verifier]
timeout_sec = 600.0

[agent]
timeout_sec = 1500.0

[environment]
allow_internet = false
workdir = "/app"
build_timeout_sec = 900.0
cpus = 2
memory_mb = 4096
storage_mb = 10240
""",
        encoding="utf-8",
    )
    sol = TASK_DIR / "solution"
    sol.mkdir(parents=True)
    (sol / "main.go").write_text(MAIN_GO, encoding="utf-8")
    (sol / "go.mod").write_text("module paceaud\n\ngo 1.23\n", encoding="utf-8")
    (sol / "solve.sh").write_text(
        f"""#!/bin/bash
set -euo pipefail

SOL_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p /app/_spa_build
cp "$SOL_DIR/main.go" /app/_spa_build/main.go
cp "$SOL_DIR/go.mod" /app/_spa_build/go.mod
cd /app/_spa_build
export PATH="/usr/local/go/bin:${{PATH}}"
GOFLAGS="-mod=mod" GOTOOLCHAIN=local go build -o /app/_spa_build/aud .

SPA_DATA_DIR="${{SPA_DATA_DIR:-/app/{DOMAIN}}}" \\
SPA_AUDIT_DIR="${{SPA_AUDIT_DIR:-/app/audit}}" \\
/app/_spa_build/aud
""",
        encoding="utf-8",
    )
    tests = TASK_DIR / "tests"
    tests.mkdir(parents=True)
    shutil.copy(ROOT / "kv-epoch-trim-audit" / "tests" / "test.sh", tests / "test.sh")


def run_oracle() -> Path:
    audit = TASK_DIR / "local-audit"
    if audit.exists():
        shutil.rmtree(audit)
    audit.mkdir()
    build = TASK_DIR / "_spa_build"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir()
    shutil.copy(TASK_DIR / "solution/main.go", build / "main.go")
    shutil.copy(TASK_DIR / "solution/go.mod", build / "go.mod")
    exe = build / "aud.exe" if os.name == "nt" else build / "aud"
    subprocess.run(["go", "build", "-o", str(exe), "."], cwd=build, check=True)
    env = os.environ.copy()
    env["SPA_DATA_DIR"] = str(TASK_DIR / "environment" / DOMAIN)
    env["SPA_AUDIT_DIR"] = str(audit)
    subprocess.run([str(exe)], env=env, check=True)
    return audit


def write_tests(audit: Path) -> None:
    lab = TASK_DIR / "environment" / DOMAIN
    input_hashes = {}
    for path in sorted(lab.rglob("*")):
        if path.is_file():
            rel = path.relative_to(lab).as_posix()
            input_hashes[rel] = sha256_file(path)
    out_hashes = {}
    field_hashes = {}
    for name in ("floor_bins.json", "summary.json"):
        obj = json.loads((audit / name).read_text(encoding="utf-8"))
        out_hashes[name] = canonical_hash(obj)
    floor = json.loads((audit / "floor_bins.json").read_text(encoding="utf-8"))
    summary = json.loads((audit / "summary.json").read_text(encoding="utf-8"))
    field_hashes["floor_bins.json.samples"] = canonical_hash(floor["samples"])
    field_hashes["summary.json.tail_floor_sha"] = canonical_hash(summary["tail_floor_sha"])
    field_hashes["summary.json.total_values"] = canonical_hash(summary["total_values"])

    template = (ROOT / "kv-epoch-trim-audit" / "tests" / "test_outputs.py").read_text(encoding="utf-8")
    body = template.replace("KET_", "SPA_").replace("/app/ket_lab", "/app/pace_lab")
    body = body.replace("trim_bins.json", "floor_bins.json")
    body = body.replace("epoch_spill", "cap_spill")
    body = body.replace("trim_echo", "pace_echo")
    body = body.replace("tail_trim_sha", "tail_floor_sha")
    body = body.replace(
        'key = "glyphs" if "KET" == "GTB" else "values"',
        '"values"',
    )
    body = body.replace("total += len(doc[key])", "total += len(doc[\"values\"])")
    body = body.replace(
        '"""Behavioral tests for spa."""',
        '"""Behavioral tests for slew pace floor audit."""',
    )

    def fmt_dict(name: str, mapping: dict[str, str]) -> str:
        lines = [f"{name} = {{"]
        for key, val in sorted(mapping.items()):
            lines.append(f'    "{key}": "{val}",')
        lines.append("}")
        return "\n".join(lines)

    import re

    body = re.sub(
        r"EXPECTED_INPUT_HASHES = \{[\s\S]*?\}\n\nEXPECTED_OUTPUT",
        fmt_dict("EXPECTED_INPUT_HASHES", input_hashes) + "\n\nEXPECTED_OUTPUT",
        body,
        count=1,
    )
    body = re.sub(
        r"EXPECTED_OUTPUT_CANONICAL_HASHES = \{[\s\S]*?\}\n\nEXPECTED_FIELD",
        fmt_dict("EXPECTED_OUTPUT_CANONICAL_HASHES", out_hashes) + "\n\nEXPECTED_FIELD",
        body,
        count=1,
    )
    body = re.sub(
        r"EXPECTED_FIELD_HASHES = \{[\s\S]*?\}\n\n\n",
        fmt_dict("EXPECTED_FIELD_HASHES", field_hashes) + "\n\n\n",
        body,
        count=1,
    )
    (TASK_DIR / "tests" / "test_outputs.py").write_text(body, encoding="utf-8")


def main() -> None:
    write_task_files()
    audit = run_oracle()
    write_tests(audit)
    print(f"Generated {TASK} with oracle outputs in {audit}")


if __name__ == "__main__":
    main()
