# Module Graph Analyzer

Analyze a JavaScript codebase to produce a module dependency graph report.

## Environment Layout

```
/app/
├── data/
│   ├── project_config.json     # Analysis configuration
│   └── modules/                # JavaScript source files to analyze
│       ├── index.js            # Entry point
│       ├── app.js .. admin.js  # Application modules (17 total)
├── docs/                       # Specification documents
│   ├── parsing_spec.md
│   ├── graph_spec.md
│   ├── tree_shaking_spec.md
│   ├── metrics_spec.md
│   ├── re_export_spec.md
│   └── output_format.md
├── src/
│   └── main.js                 # Entry point for the analyzer (stub)
├── package.json
└── output/                     # Write results here
```
