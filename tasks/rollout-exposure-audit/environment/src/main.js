import { loadData } from "./loader.js";
import { buildReport } from "./aggregator.js";

// BUGGY: uses first-touch attribution and ignores mutex groups
const data = loadData();
const report = buildReport(data);
import { writeFileSync, mkdirSync } from "fs";
mkdirSync("/app/output", { recursive: true });
writeFileSync("/app/output/rollout_audit.json", JSON.stringify(report, null, 2) + "\n");
