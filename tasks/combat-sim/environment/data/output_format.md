# Output Format

Produce `/app/output/combat_log.json` with two-space indent and trailing newline.

## Top-Level Structure
- `schema_version` — integer 1
- `battle_results` — array sorted by battle name ascending
- `summary` — aggregate statistics

## Battle Result Entry
- `battle` — battle name string
- `winner` — `"A"`, `"B"`, or `"draw"`
- `rounds_played` — number of rounds executed
- `events` — array of event objects in execution order
- `final_characters` — array of character state objects sorted by name ascending

## Event Types

**attack**: `{"round", "actor", "type": "attack", "ability", "target", "damage", "effectiveness", "target_hp"}`
- `effectiveness` is one of `"super_effective"`, `"not_very_effective"`, `"normal"`
- `target_hp` is the target's HP after damage (clamped to 0)

**heal**: `{"round", "actor", "type": "heal", "ability", "target", "heal_amount", "target_hp"}`
- `heal_amount` is actual HP restored (clamped to max_hp)
- `target_hp` is the target's HP after healing

**buff**: `{"round", "actor", "type": "buff", "ability", "target", "stat", "value", "duration"}`

**stunned**: `{"round", "actor", "type": "stunned"}`

**poison_tick**: `{"round", "actor", "type": "poison_tick", "damage", "hp_after"}`

**skip**: `{"round", "actor", "type": "skip", "reason"}` where reason is `"target_dead"` or `"actor_dead"`

## Final Character State
`{"name", "team", "hp", "max_hp", "alive"}`

## Summary
- `total_battles` — integer
- `team_a_wins` — integer
- `team_b_wins` — integer
- `draws` — integer
- `total_rounds` — sum of rounds_played
- `total_damage` — sum of all attack damage
- `total_healing` — sum of all heal_amount
- `total_kills` — count of characters reduced to 0 HP
