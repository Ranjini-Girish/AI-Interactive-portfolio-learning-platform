# Module Bundler Analyzer — Environment

## Data files

- `data/modules/*.json` — 14 module definitions (see `data/module_spec.md`)
- `data/config.json` — project and bundler configuration

## Specification documents

- `data/module_spec.md` — module JSON format reference
- `data/graph_rules.md` — graph construction and circular import detection
- `data/treeshake_rules.md` — tree-shaking and export usage analysis
- `data/chunking_rules.md` — chunk assignment and size computation
- `data/output_format.md` — required output JSON structure

## Output

The program writes `output/bundle_report.json`.
