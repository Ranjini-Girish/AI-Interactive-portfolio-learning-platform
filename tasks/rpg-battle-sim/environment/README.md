# RPG Battle Simulator

A turn-based RPG combat engine that reads battle configurations and simulates each battle according to precise game mechanics.

## Directory Structure
- `/app/data/element_chart.json` — Element weakness/resistance relationships
- `/app/data/battles/` — Six battle configuration files (battle_01 through battle_06)
- `/app/docs/` — Detailed specification documents:
  - `COMBAT_SPEC.md` — Turn order, skill rotation, target selection, round structure
  - `DAMAGE_FORMULA.md` — Multi-stage damage calculation with floor operations
  - `ELEMENT_CHART.md` — Elemental multiplier lookup rules
  - `STATUS_EFFECTS.md` — Poison, burn, stun, shield mechanics and tick ordering
  - `CRIT_SYSTEM.md` — Deterministic LCG-based critical hit system
  - `OUTPUT_FORMAT.md` — Required JSON output schema

## Requirements
- Java 21 (provided by base image)
- Gson library available at `/app/lib/gson.jar`
- Output: `/app/output/battle_report.json`

## Key Implementation Notes
- The damage formula has TWO separate `floor()` operations that must not be combined
- Status effects tick at end-of-round in alphabetical order (burn before poison)
- AoE deals full damage to each target, not split damage
- Critical hits use a deterministic LCG PRNG seeded per battle
- Shield absorbs damage before HP is reduced
