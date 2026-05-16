import { mkdirSync } from "node:fs";
mkdirSync(process.env.FRLA_AUDIT_DIR ?? "/app/audit", { recursive: true });
console.error("replace this scaffold with the rollout auditor");
