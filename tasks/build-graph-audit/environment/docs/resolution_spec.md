# Import Resolution Specification

## Module Loading

Modules are defined as JSON files in the `modules/` directory. Each module
has a unique `name`, a list of `imports`, a list of `exports`, and an
optional list of `re_exports`.

## Direct vs Resolved Dependencies

An **import** declares that module A references specifiers from module B.
A **resolved dependency** is the actual module that provides the specifier
after re-export chains are followed.

### Re-export Resolution Algorithm

When module A imports specifier `X` from module B:

1. Check if B's `re_exports` list contains an entry whose `specifiers`
   include `X`.
2. If yes, the re-export entry names a `source` module C. The resolved
   dependency for that specifier is **A → C** (not A → B).
3. If no, specifier `X` is B's own export. The resolved dependency is
   **A → B**.
4. Re-export chains may be multi-hop: if C also re-exports `X` from D,
   then the resolved dependency is A → D. Follow until the specifier
   is an own-export of the terminal module.

If A imports multiple specifiers from B, each specifier is resolved
independently. A may end up depending on B (for its own exports) **and**
on C (for re-exported specifiers) from the same import statement.

### Side-effect Imports

When `specifiers` is an empty array (`[]`), the import is a side-effect
import. The resolved dependency is always **A → B** regardless of
re-exports, because no specific specifier is being imported.

## Dependency Graph

The **resolved dependency graph** is a directed graph where each edge
`(A, B)` means A has at least one resolved dependency on B. Duplicate
edges are collapsed — if A depends on B through two specifiers, there
is still only one edge A → B.

The graph is built from resolved dependencies only. Declared import
sources that are fully resolved through re-exports to other modules
do **not** appear as edges unless A also imports own-exports from them.
