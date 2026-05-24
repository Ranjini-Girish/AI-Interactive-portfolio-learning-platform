# Shield Specification

## Creating a Shield
When an entity uses a skill with `effect: "shield"` and `target_type: "self"`:
```
shield_amount = floor(caster.defense * 1.5)
shield_duration = 2
```
The shield replaces any existing shield on the caster.

## Damage Absorption
When a shielded entity takes damage:
```
if damage <= shield_amount:
    shield_amount -= damage
    hp_damage = 0
else:
    hp_damage = damage - shield_amount
    shield_amount = 0
    shield_duration = 0  (shield removed)
entity.hp -= hp_damage
```

## Duration
- Shield duration decrements by 1 at end of each round (after status ticks)
- When duration reaches 0, shield_amount is set to 0

## Reapplication
Using a shield skill while a shield is already active replaces the old shield entirely with a new one. The new shield gets the full amount and duration.

## Interaction with Status Effects
- Shields absorb all incoming damage BEFORE HP is affected
- Status effect tick damage (burn/poison) is NOT absorbed by shields; it goes directly to HP
