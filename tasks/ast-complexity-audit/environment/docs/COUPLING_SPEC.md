# Coupling Metrics Specification

## Afferent Coupling (Ca)

The number of other modules that **import** this module. Count each importing module once regardless of how many symbols it imports.

A module X has Ca = number of modules whose `imports` array contains X's module_name or a path that resolves to X.

Import matching rules:
- An import string matches a module if the module's `module_name` appears as the last path segment (after the last `/`). For example, import `"./crypto_utils"` matches module `"crypto_utils"`.
- External imports (strings not starting with `"./"` or `"../"`) do NOT count toward coupling — they are third-party dependencies.

## Efferent Coupling (Ce)

The number of **internal** modules that this module imports. Only count imports that match another module in the project. External/third-party imports are excluded.

## Instability (I)

```
I = Ce / (Ca + Ce)
```

When `Ca + Ce = 0`, instability = 0.0 (not NaN or undefined).

Round to 6 decimal places.

## Abstractness

Not computed in this analysis (reserved for future use). Set to `null` in output.

## Distance from Main Sequence

Not computed. Set to `null` in output.
