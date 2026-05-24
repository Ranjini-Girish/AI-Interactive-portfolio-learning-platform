# Risk Scoring

## Formula

For each non-waived violation in a project's dependency tree:

    contribution = severity / (depth + 1)

The project risk score is the sum of all contributions, rounded to
4 decimal places.

## Depth Convention

Direct dependencies have depth 0. A transitive dependency one hop away
has depth 1, and so on.

## Severity Values

- allowed: 0 (no violation generated)
- restricted: 5
- banned: 10
- copyleft_propagation: 8 (from policy configuration)

## Example

A banned dependency at depth 1 contributes 10 / (1 + 1) = 5.0.
A copyleft propagation at depth 0 contributes 8 / (0 + 1) = 8.0.
