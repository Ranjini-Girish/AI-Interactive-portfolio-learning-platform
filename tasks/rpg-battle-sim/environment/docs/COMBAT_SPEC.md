# Combat Specification

## Turn Order
Each round, all alive entities are sorted by `speed` descending. Ties are broken by entity `id` ascending (lexicographic). Entities act in this order. An entity that dies during a round is immediately removed from the remaining turn queue for that round.

## Skill Rotation
Each entity selects a skill based on the current round number: `skill_index = (round - 1) % num_skills` where `round` starts at 1 and `num_skills` is the length of the entity's skill array. A stunned entity skips its turn but the round number still advances for skill selection purposes.

## Target Selection
- **Single-target offensive skills**: Target the alive opponent with the lowest current HP. Ties broken by entity `id` ascending (lexicographic).
- **AoE skills**: Target ALL alive opponents. Each target takes the full calculated damage (damage is NOT split among targets).
- **Self-targeting skills** (shield): Target the caster.

## Battle End
A battle ends when all heroes are dead OR all enemies are dead. Check after each individual action and after end-of-round status ticks. If both sides die simultaneously (e.g., from status ticks), the side that still had alive members when the last action was taken wins.

## Round Structure
1. Determine turn order for this round
2. Each entity acts in turn order (skip if dead or stunned)
3. After ALL entities have acted, apply end-of-round status effect ticks
4. Remove expired status effects
5. Check battle end condition
