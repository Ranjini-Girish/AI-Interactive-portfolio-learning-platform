# Halstead Metrics Specification

Halstead metrics are computed per function from the `operators` and `operands` arrays.

## Base Measures

- `n1` = number of **unique** operators (distinct entries in the operators array)
- `n2` = number of **unique** operands (distinct entries in the operands array)
- `N1` = **total** number of operators (length of the operators array)
- `N2` = **total** number of operands (length of the operands array)

## Derived Measures

- **Vocabulary:** `η = n1 + n2`
- **Length:** `N = N1 + N2`
- **Volume:** `V = N × log₂(η)` — uses base-2 logarithm, NOT natural log or log₁₀
- **Difficulty:** `D = (n1 / 2) × (N2 / n2)` — when `n2 = 0`, set `D = 0`
- **Effort:** `E = D × V`
- **Time:** `T = E / 18` (Halstead's empirical constant: 18 elementary mental discriminations per second)
- **Bugs:** `B = V / 3000` (estimated delivered bugs)

## Rounding

All Halstead values must be rounded to 6 decimal places.

## Module-Level Aggregation

For module-level Halstead metrics:
- `total_volume`: sum of all function volumes in the module
- `avg_difficulty`: arithmetic mean of all function difficulties in the module
- `total_effort`: sum of all function efforts in the module
- `max_difficulty`: maximum difficulty across all functions

## Edge Cases

- If a function has zero operators or zero operands, Volume = 0, Difficulty = 0, Effort = 0
- `log₂(0)` should never occur because η ≥ 1 if there is at least one operator or operand
- If η = 0 (both arrays empty), all derived measures are 0
