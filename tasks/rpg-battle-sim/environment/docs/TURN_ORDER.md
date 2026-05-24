# Turn Order Specification

## Priority Rules
1. Sort all alive entities by `speed` in descending order (highest speed acts first)
2. If two entities have the same speed, sort by `id` in ascending lexicographic order
3. Apply this ordering at the START of each round using current alive entities

## Dead Entity Handling
- An entity that dies during a round is immediately removed from the remaining turn queue
- If entity A kills entity B, and entity B had not yet acted this round, entity B does NOT get a turn
- Dead entities are never included in target selection

## Stun Interaction
- A stunned entity still appears in the turn order
- When a stunned entity's turn arrives, it is skipped and stun is consumed
- The stunned turn IS recorded in the turn log with skill="stunned"

## Speed Values
Speed values are integers. There is no speed modification from status effects.
