# Element Chart

## Multipliers
- **Strong against**: 1.5x damage
- **Weak against**: 0.75x damage
- **Neutral/Same element**: 1.0x damage

## Relationships
| Attacker Element | Strong Against | Weak Against |
|-----------------|---------------|-------------|
| fire            | nature        | water       |
| water           | fire          | nature      |
| nature          | water         | fire        |
| light           | dark          | dark        |
| dark            | light         | light       |
| neutral         | (none)        | (none)      |

Note: Light and Dark are mutually strong against each other. Attacking a Light entity with a Dark skill deals 1.5x, and attacking a Dark entity with a Light skill also deals 1.5x. Neither is "weak" in the traditional sense; both deal boosted damage to the other.

## Lookup Rule
Given `skill.element` and `target.element`:
1. Look up `skill.element` in the chart
2. If `target.element == strong_against`: multiplier = 1.5
3. If `target.element == weak_against`: multiplier = 0.75
4. Otherwise: multiplier = 1.0

The multiplier is based on the SKILL's element, not the attacker's innate element.
