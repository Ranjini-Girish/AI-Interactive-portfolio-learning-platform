# Maintainability Index Specification

## Formula

The Maintainability Index (MI) for a function is computed as:

```
MI = max(0, (171 - 5.2 × ln(V) - 0.23 × CC - 16.2 × ln(LOC)) × 100 / 171)
```

Where:
- `V` = Halstead Volume for the function
- `CC` = Cyclomatic Complexity for the function
- `LOC` = lines of code for the function (from the `lines` field)
- `ln` = **natural logarithm** (base e), NOT log₂ or log₁₀

## Important Details

1. The formula uses **natural logarithm** (`ln` / `Math.log` in JavaScript)
2. The result is clamped to a minimum of 0 via `max(0, ...)`
3. The scaling factor is `100 / 171` — this normalizes the index to roughly 0–100
4. When `V = 0`, use `ln(1) = 0` instead (to avoid `ln(0)`)
5. When `LOC = 0`, use `ln(1) = 0` instead
6. Round to 6 decimal places

## Module-Level Maintainability

The module-level maintainability index is the **arithmetic mean** of all function MIs in the module, rounded to 6 decimal places.

## Classification

Based on `thresholds.json`:
- MI ≥ high threshold: "high" maintainability
- MI ≥ moderate threshold: "moderate" maintainability
- MI ≥ low threshold: "low" maintainability
- MI < low threshold: "very_low" maintainability
