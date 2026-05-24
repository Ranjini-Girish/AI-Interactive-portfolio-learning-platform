# Resolution Examples

## Caret Constraint Examples

| Constraint | Expands To | Matches | Does NOT Match |
|---|---|---|---|
| ^1.2.3 | >=1.2.3, <2.0.0 | 1.2.3, 1.9.9 | 2.0.0, 1.2.2 |
| ^0.2.3 | >=0.2.3, <0.3.0 | 0.2.3, 0.2.9 | 0.3.0, 0.2.2 |
| ^0.0.3 | >=0.0.3, <0.0.4 | 0.0.3 | 0.0.4, 0.0.2 |

## Tilde Constraint Examples

| Constraint | Expands To | Matches | Does NOT Match |
|---|---|---|---|
| ~1.2.3 | >=1.2.3, <1.3.0 | 1.2.3, 1.2.9 | 1.3.0, 1.2.2 |
| ~0.2.3 | >=0.2.3, <0.3.0 | 0.2.3, 0.2.9 | 0.3.0, 0.2.2 |
| ~0.0.3 | >=0.0.3, <0.1.0 | 0.0.3, 0.0.9 | 0.1.0, 0.0.2 |

## Pre-release Comparison

Ordered lowest to highest:
1. 1.0.0-alpha
2. 1.0.0-alpha.1
3. 1.0.0-alpha.beta
4. 1.0.0-beta
5. 1.0.0-beta.2
6. 1.0.0-beta.11
7. 1.0.0-rc.1
8. 1.0.0

## Diamond Dependency Resolution

Given:
- A requires B@^1.0.0 and C@^1.0.0
- B@1.2.0 requires D@^1.1.0
- C@1.0.0 requires D@^1.3.0

Resolution of D:
- Constraint from B: ^1.1.0 → >=1.1.0, <2.0.0
- Constraint from C: ^1.3.0 → >=1.3.0, <2.0.0
- Intersection: >=1.3.0, <2.0.0
- Resolved: highest available version in range
