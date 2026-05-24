# Damage Formula

Damage calculation proceeds in stages. Each stage applies `floor()` independently.

## Stage 1: Base Damage
```
raw_attack = floor(attacker.attack * skill.power / 100)
effective_defense = target.defense
if target has burn status:
    effective_defense = floor(target.defense * 0.8)
raw_defense = floor(effective_defense * 0.6)
base_damage = max(1, raw_attack - raw_defense)
```

**CRITICAL**: `floor()` is applied to `attack * power / 100` and `defense * 0.6` SEPARATELY, then subtracted. Do NOT compute `floor(attack * power / 100 - defense * 0.6)`.

## Stage 2: Elemental Multiplier
```
elemental_damage = floor(base_damage * element_multiplier)
```
See `ELEMENT_CHART.md` for multiplier values.

## Stage 3: Critical Hit
```
if is_critical_hit:
    final_damage = floor(elemental_damage * 1.75)
else:
    final_damage = elemental_damage
```
See `CRIT_SYSTEM.md` for critical hit determination.

## Stage 4: Shield Absorption
If the target has an active shield:
```
if final_damage <= shield_amount:
    shield_amount -= final_damage
    actual_hp_damage = 0
else:
    actual_hp_damage = final_damage - shield_amount
    shield_amount = 0  (shield is removed)
target.hp -= actual_hp_damage
```

## Self-Shield Skills
For skills with `effect: "shield"` and `target_type: "self"`:
```
shield_amount = floor(caster.defense * 1.5)
shield_duration = 2 rounds
```
No damage calculation occurs. The shield is applied to the caster.
