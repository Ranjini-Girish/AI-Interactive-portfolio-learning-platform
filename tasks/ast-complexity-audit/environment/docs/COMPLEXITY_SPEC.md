# Complexity Metrics Specification

## Cyclomatic Complexity (CC)

Cyclomatic complexity measures the number of linearly independent paths through a function.

**Formula:** `CC = 1 + D` where D is the number of decision points.

**Decision points** (each occurrence adds +1 to D):
- `if`
- `else_if`
- `for`
- `while`
- `do_while`
- `case` (each individual case in a switch — the `switch` itself is NOT a decision point)
- `catch`
- `ternary`
- `logical_and` (each `&&` occurrence)
- `logical_or` (each `||` occurrence)
- `nullish_coalesce` (each `??` occurrence)

**Not decision points:** `else`, `default`, `try`, `finally`, `switch` (the switch statement itself).

## Cognitive Complexity (CogC)

Cognitive complexity measures how difficult code is to understand. It differs from cyclomatic complexity in important ways.

### Structural Increments (each adds +1)

These nodes add a base increment of +1:
- `if`
- `else_if`
- `else`
- `for`, `while`, `do_while`
- `switch`
- `catch`
- `ternary`

### Nesting Bonus

In addition to the base +1, certain nodes receive a nesting bonus equal to their current nesting depth:
- `if`: +1 + nesting_depth
- `for`, `while`, `do_while`: +1 + nesting_depth
- `switch`: +1 + nesting_depth
- `catch`: +1 + nesting_depth
- `ternary`: +1 + nesting_depth

Nodes that get +1 but NO nesting bonus:
- `else_if`: always +1 only (it is a linear continuation, not nested)
- `else`: always +1 only

### Nesting Depth Rules

The nesting depth starts at 0. The following nodes increase nesting by +1 for their children:
- `if` (for its body)
- `else` (for its body)
- `for`, `while`, `do_while` (for their body)
- `switch` (for its cases' bodies)
- `catch` (for its body)
- `ternary` (for both branches)

Nodes that do NOT increase nesting:
- `else_if` (its body is at the same nesting level)
- `try` (does not increase nesting for its body)
- `finally` (does not change nesting)
- `default` (same as regular case, no extra nesting from default itself)

### Logical Operator Sequences

Logical operators in `condition` arrays use sequence-based counting:
- The **first** logical operator of any type adds +1
- **Subsequent** operators of the **same type** in the same condition add +0
- **Switching** to a different operator type adds +1

Examples:
- `[&&]` → +1
- `[&&, &&, &&]` → +1 (all same type)
- `[&&, ||]` → +2 (type switch)
- `[&&, &&, ||]` → +2 (first && = +1, second && = +0, first || = +1)
- `[||, ||]` → +1
- `[&&, ||, &&]` → +3 (type switches twice)
- `[??]` → +1

Logical operators do NOT receive nesting bonuses.

### Important Differences from Cyclomatic

1. `switch` counts for cognitive (+1 + nesting) but NOT for cyclomatic
2. `case` counts for cyclomatic (+1) but NOT for cognitive
3. `else` counts for cognitive (+1) but NOT for cyclomatic
4. `default` counts for neither
5. `else_if` has a nesting bonus in cyclomatic (N/A — cyclomatic ignores nesting) but NO nesting bonus in cognitive
6. Logical operators: cyclomatic counts each occurrence; cognitive groups by sequence
