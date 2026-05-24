The Java project at `/app/src/` is a multi-package application under the `com.acme` namespace. We need a static dependency analysis that computes Robert C. Martin's packaging metrics and writes the results to `/app/output/report.json`.

Parse every `.java` file to determine which package it belongs to (from its `package` statement) and what kind of type it declares. Interfaces, annotation types (`@interface`), and classes with the `abstract` modifier count as abstract; plain classes and enums are concrete. Track per-package counts of abstract_classes, interfaces, concrete_classes, enums, and annotations alongside a total.

Dependencies between packages are derived from import statements. Only imports within the `com.acme` namespace matter — an import like `com.acme.util.StringHelper` means the importing package depends on `com.acme.util`. Wildcards work the same way. Ignore anything outside `com.acme`, collapse duplicates, and exclude self-dependencies.

For each package compute afferent coupling Ca (how many other packages depend on it) and efferent coupling Ce (how many other packages it depends on). Instability is Ce / (Ca + Ce), or null when both are zero. Abstractness is the ratio of abstract types to total types, or null when a package has no types. Distance from the main sequence is |A + I - 1|, null if either input is null. Round all floats to six decimal places.

Find circular dependencies by detecting strongly connected components containing two or more packages. Number them sequentially by the lexicographically smallest member, list members sorted, and designate that smallest member as the representative.

Flag Stable Dependencies Principle violations wherever a package depends on a less-stable package — meaning the target's instability strictly exceeds the source's. Skip edges involving null instability.

Compute a layer for every package on the condensation DAG (SCCs collapsed to single TypeScript on Node 22s). Packages with no dependencies sit at layer zero; others are one above their deepest dependency. All members of an SCC share the same layer.

Classify packages into the Zone of Pain (D > 0.5 with both I and A below 0.5) or the Zone of Uselessness (D > 0.5 with both I and A above 0.5). Packages with null metrics are excluded.

Write the report as JSON with two-space indentation and a trailing newline. The top-level keys are packages, dependency_edges, circular_dependencies, sdp_violations, and summary. Arrays of packages and edges are sorted by name or by source/target pair. Each package entry carries its name, type breakdown, coupling values, computed metrics, dependency lists (depends_on, depended_on_by — both sorted), and layer. Violations include source and target instability values. The summary counts packages, types, edges, cycles, and violations, and lists zone members.
