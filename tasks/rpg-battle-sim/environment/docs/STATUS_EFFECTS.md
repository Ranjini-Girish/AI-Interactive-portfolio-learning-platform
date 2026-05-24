# Status Effects

## Poison
- **Tick damage**: `floor(entity.max_hp * 0.08)` per round
- **Duration**: 3 rounds
- **Stacking**: Reapplying poison resets the duration to 3. Damage does not stack.
- **Tick timing**: End of round, after all entities have acted

## Burn
- **Tick damage**: `floor(entity.max_hp * 0.05)` per round
- **Duration**: 3 rounds
- **Defense reduction**: While burn is active, effective defense = `floor(defense * 0.8)`
- **Stacking**: Reapplying burn resets the duration to 3. Effects do not stack.
- **Tick timing**: End of round, after all entities have acted

## Stun
- **Effect**: The stunned entity skips its next turn entirely
- **Duration**: 1 round (consumed when the entity's turn is skipped)
- **Stacking**: Reapplying stun resets duration to 1. Cannot accumulate multiple stuns.
- **Note**: Stun is consumed at the START of the entity's turn. The entity does not act, and the stun is removed.

## End-of-Round Tick Order
Status effects tick in this order:
1. **Burn** ticks first (alphabetical by effect name)
2. **Poison** ticks second

If an entity dies from burn damage, poison does NOT tick for that entity. Dead entities do not receive status ticks.

## Status Effect Duration
Duration decrements by 1 at the end of each round (AFTER tick damage is applied). When duration reaches 0, the effect is removed.
