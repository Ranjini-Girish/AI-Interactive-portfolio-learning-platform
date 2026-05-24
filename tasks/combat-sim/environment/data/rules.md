# Combat Rules

## Turn Order
At the start of each round, sort all alive characters by speed descending. Break ties by character name ascending (alphabetical). Recompute turn order each round.

## Round Flow
For each character in turn order:
1. If dead (HP <= 0), skip entirely (no effects processed).
2. If the character has a "stun" status, remove it and skip their action. Still process end-of-turn effects (step 4).
3. Execute the character's planned action for this round. If the target is dead, the action is skipped (no retargeting).
4. **End of turn**: if the character has "poison", they lose `floor(max_hp / poison_divisor)` HP. HP is clamped to 0 minimum.

After all characters have acted, decrement all active buff durations by 1. Remove any buffs whose duration reaches 0.

Check win condition: if all characters on one team are dead, the other team wins. If max rounds are exhausted, the result is a draw.

## Damage Formula
All arithmetic uses integer division (truncation toward zero).

```
effective_defense = base_defense + sum(active defense buff values)
raw = floor(power * attack / effective_defense)
```

Apply element multiplier as integer fraction `[numerator, denominator]`:
```
adjusted = floor(raw * numerator / denominator)
final_damage = max(min_damage, adjusted)
```

Super effective: multiply by 3, divide by 2.
Not very effective: divide by 2.
Normal: no change.

## Element Chart
Four elements form a cycle: fire beats wind, wind beats earth, earth beats water, water beats fire.

- Attacker's element beats defender's element: **super effective** (×3/2)
- Defender's element beats attacker's element: **not very effective** (×1/2)
- Same non-neutral element vs itself: **not very effective** (×1/2)
- If either element is neutral: **normal** (×1)

## Healing
```
target.hp = min(target.max_hp, target.hp + ability.power)
```
Cannot heal dead characters. If the target is dead, the action is skipped.

## Buff Mechanics
Buffs add a flat value to the specified stat. Duration is tracked in full rounds. At the end of each round (after all characters act), decrement all buff durations by 1. Buffs with duration 0 are removed. Multiple buffs on the same stat stack additively.

## Status Effects
- **poison**: Applied by abilities with `"applies": "poison"`. At the end of the poisoned character's turn, they lose `floor(max_hp / poison_divisor)` HP. Poison lasts indefinitely.
- **stun**: Applied by abilities with `"applies": "stun"`. On the stunned character's next turn, remove the stun and skip their action. The character still processes end-of-turn effects (e.g., poison).

## Attack with Status
Abilities that have both `power > 0` and an `applies` field deal damage AND apply the status effect (if the target survives the damage).
