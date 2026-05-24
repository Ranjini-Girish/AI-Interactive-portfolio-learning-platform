# Critical Hit System

## Pseudo-Random Number Generator (PRNG)
Each battle uses a deterministic Linear Congruential Generator (LCG) seeded per battle:

```
next_seed = (current_seed * 1103515245 + 12345) & 0x7FFFFFFF
```

The `& 0x7FFFFFFF` masks to 31 bits (values 0 to 2147483647).

## Critical Hit Check
Before each damage calculation (not shield applications), advance the PRNG once:
```
seed = lcg_next(seed)
roll = seed % 100
if roll < attacker.crit_rate:
    is_critical = true
else:
    is_critical = false
```

The PRNG is advanced once per damage calculation, including each target of an AoE skill. For an AoE hitting 3 targets, the PRNG advances 3 times (once per target, in target ID ascending order).

## Critical Damage
```
critical_damage = floor(elemental_damage * 1.75)
```

## PRNG Sequence
The seed advances in strict order:
1. Turn order within a round (by speed descending, then ID ascending)
2. For each acting entity, one advance per damage calculation
3. AoE targets are processed in ID ascending order
4. Shield skills do NOT advance the PRNG
