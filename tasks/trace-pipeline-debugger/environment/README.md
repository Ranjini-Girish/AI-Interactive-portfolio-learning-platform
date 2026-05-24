# Trace Analyzer

Distributed trace analysis tool that processes span data and generates diagnostic reports.

## Directory Layout

```
/app/
├── src/          # JavaScript source code
├── data/
│   ├── config.json
│   └── spans/    # JSONL span files (7 service files)
├── docs/         # Algorithm and format specifications
└── output/       # Report output directory
```

## Usage

```bash
node src/index.js
```

Output: `/app/output/trace_report.json`
