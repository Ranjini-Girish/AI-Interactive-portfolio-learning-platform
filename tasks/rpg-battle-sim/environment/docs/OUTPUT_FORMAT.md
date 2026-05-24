# Output Format

The program must write a JSON file to `/app/output/battle_report.json`.

## Top-Level Structure
```json
{
  "battles": [ ... ],
  "summary": { ... }
}
```

## Battle Object
Each battle in the `battles` array:
```json
{
  "battle_id": "battle_01",
  "total_rounds": 3,
  "winner": "heroes",
  "rounds": [ ... ],
  "survivors": [ ... ],
  "stats": { ... }
}
```

### Round Object
```json
{
  "round": 1,
  "turns": [ ... ],
  "status_ticks": [ ... ],
  "deaths_this_round": ["goblin_a"]
}
```

### Turn Object
```json
{
  "actor": "aria",
  "skill": "flame_slash",
  "targets": ["goblin_a"],
  "damage_per_target": [67],
  "critical_per_target": [false],
  "effects_applied": ["burn"],
  "hp_after": {"goblin_a": 53}
}
```
For shield skills: `"damage_per_target": [0]`, `"effects_applied": ["shield"]`, `"hp_after"` shows caster HP unchanged.
For stunned entities: `{"actor": "entity_id", "skill": "stunned", "targets": [], "damage_per_target": [], "critical_per_target": [], "effects_applied": [], "hp_after": {}}`

### Status Tick Object
```json
{
  "entity": "goblin_a",
  "effect": "burn",
  "damage": 6,
  "hp_after": 47
}
```

### Survivor Object
```json
{"id": "aria", "hp": 178, "max_hp": 200}
```
Sorted by entity ID ascending.

### Stats Object
```json
{
  "critical_hits": 1,
  "hero_damage_dealt": 256,
  "enemy_damage_dealt": 45,
  "shields_created": 0,
  "status_effect_damage": 18,
  "stuns_applied": 0
}
```

## Summary Object
```json
{
  "enemy_wins": 1,
  "hero_wins": 5,
  "longest_battle_rounds": 7,
  "shortest_battle_rounds": 2,
  "total_battles": 6,
  "total_critical_hits": 8,
  "total_damage": 2500,
  "total_rounds": 25,
  "total_status_ticks": 15
}
```

## JSON Formatting Rules
- 2-space indentation
- All object keys sorted alphabetically at every nesting level
- Trailing newline at end of file
- Numbers are integers (no decimals)
- Booleans are lowercase `true`/`false`
