# Turn Order Rules

## Computation
Turn order is recalculated at the start of each round using only alive characters.

1. Sort by `speed` stat in **descending** order (fastest first).
2. Break ties by character `name` in **ascending** alphabetical order.

## Important Notes

- Dead characters are excluded from turn order entirely.
- Turn order is fixed for the entire round — even if a character's speed changes during the round (e.g., via buff), it does not affect the current round's order.
- If a character dies during a round (from an attack or poison), characters later in the turn order still act. Their actions targeting the dead character are skipped.

## Example

Characters: archer (speed 25), healer (speed 25), mage (speed 20), knight (speed 10)

Turn order: archer, healer, mage, knight

Archer and healer both have speed 25. "archer" comes before "healer" alphabetically, so archer acts first.
