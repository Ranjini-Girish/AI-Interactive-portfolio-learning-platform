import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { loadPipeline } from "./pipeline.js";
import { loadEvents } from "./events.js";
import { processEvents } from "./processor.js";
import { computeNodeStats } from "./stats.js";
import { computeSinkStats } from "./window.js";
import { computeCategoryStats } from "./category.js";
import { computeLatencySummary } from "./latency.js";
import { computeIntegrityHash } from "./hash.js";
import { buildReport } from "./report.js";

const DATA_DIR = "/app/data";
const OUT_DIR = "/app/output";

function main() {
  mkdirSync(OUT_DIR, { recursive: true });

  const pipeline = loadPipeline(`${DATA_DIR}/pipeline.json`);
  const events = loadEvents(`${DATA_DIR}/events.json`);

  const processed = processEvents(pipeline, events);
  const nodeStats = computeNodeStats(processed, pipeline);
  const sinkStats = computeSinkStats(processed, pipeline);
  const categoryStats = computeCategoryStats(processed, pipeline);
  const latencySummary = computeLatencySummary(processed);
  const integrityHash = computeIntegrityHash(processed);

  const report = buildReport(
    pipeline, processed, nodeStats, sinkStats,
    categoryStats, latencySummary, integrityHash
  );

  writeFileSync(
    `${OUT_DIR}/pipeline_report.json`,
    JSON.stringify(report, null, 2) + "\n",
    "utf-8"
  );
}

main();
