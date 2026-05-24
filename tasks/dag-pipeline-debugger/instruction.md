A TypeScript on Node 22 application at `/app/src/` processes sensor events through a weighted DAG pipeline and generates an audit report. The application reads `/app/data/pipeline.json` (pipeline graph definition) and `/app/data/events.json` (sensor events), then writes `/app/output/pipeline_report.json`.

The program currently produces incorrect output. Fix the bugs in the TypeScript source files so the program generates the correct report as specified in `/app/docs/SPEC.md`. Apply only targeted fixes to the existing code — do not rewrite entire files.

You must implement the solution in TypeScript using the existing TypeScript on Node 22 codebase. Output JSON must use 2-space indentation and end with a trailing newline.
