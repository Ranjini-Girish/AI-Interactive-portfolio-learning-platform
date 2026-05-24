# Damage Formula Details

All intermediate values use integer arithmetic with truncation toward zero (Java's default integer division behavior).

## Step-by-Step Calculation

Given an attacker using ability with `power` against a defender:

1. **Effective attack** = `attacker.stats.attack`
2. **Effective defense** = `defender.stats.defense + sum(active defense buffs on defender)`
3. **Raw damage** = `power * effective_attack / effective_defense` (integer division)
4. **Element multiplier**: look up `[numerator, denominator]` from the element chart
   - Super effective: `[3, 2]`
   - Not very effective: `[1, 2]`
   - Normal: `[1, 1]`
5. **Adjusted damage** = `raw * numerator / denominator` (integer division)
6. **Final damage** = `max(min_damage, adjusted)` where `min_damage` comes from config

## Integer Division Gotcha

The order of operations matters. `raw * 3 / 2` is NOT the same as `raw * 1.5` cast to int for all values. Always use integer multiplication first, then integer division.

Example: if raw = 7, then `7 * 3 / 2 = 21 / 2 = 10` (integer), but `(int)(7 * 1.5) = (int)(10.5) = 10`. These happen to agree, but floating point introduces rounding risks for larger values.

## Minimum Damage

Final damage is always at least `min_damage` (from config.json, default 1). This ensures every non-immune attack deals some damage.
