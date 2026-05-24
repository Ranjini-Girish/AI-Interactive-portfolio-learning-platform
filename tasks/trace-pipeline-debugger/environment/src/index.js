'use strict';

const fs = require('fs');
const path = require('path');
const config = require('./config');
const PipelineEngine = require('./pipeline/engine');
const { computeReportHash } = require('./stages/reporter');
const { hashString } = require('./utils/hash');

const DATA_DIR = '/app/data';
const OUTPUT_DIR = '/app/output';
const OUTPUT_FILE = path.join(OUTPUT_DIR, 'trace_report.json');

function loadSpans() {
    const spansDir = path.join(DATA_DIR, 'spans');
    const files = fs.readdirSync(spansDir)
        .filter(f => f.endsWith('.jsonl'))
        .sort();

    const allSpans = [];
    for (const file of files) {
        const content = fs.readFileSync(path.join(spansDir, file), 'utf-8');
        const lines = content.trim().split('\n').filter(Boolean);
        for (const line of lines) {
            allSpans.push(JSON.parse(line));
        }
    }
    return { spans: allSpans, fileCount: files.length };
}

function main() {
    const cfg = config.load(path.join(DATA_DIR, 'config.json'));
    const { spans, fileCount } = loadSpans();

    const engine = new PipelineEngine(cfg);
    const results = engine.run(spans);

    const report = {
        metadata: {
            generated_at: new Date().toISOString(),
            config_hash: hashString(JSON.stringify(cfg)),
            span_files_processed: fileCount,
            total_spans_parsed: spans.length
        },
        results,
        integrity: {}
    };

    report.integrity.results_hash = computeReportHash(report);

    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    fs.writeFileSync(OUTPUT_FILE, JSON.stringify(report, null, 2) + '\n');

    console.log(`Report written to ${OUTPUT_FILE}`);
    console.log(`Processed ${spans.length} spans from ${fileCount} files`);
    console.log(`Found ${results.trace_summary.total_traces} traces`);
}

main();
