#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const APP = "/app";
const OUT = path.join(APP, "output");
const DEC = 4;

function roundDec(v) {
  const m = Math.pow(10, DEC);
  return Math.round(v * m) / m;
}

function canonical(v) {
  if (v === null || typeof v !== "object") return JSON.stringify(v);
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  const keys = Object.keys(v).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
}

function expectedSig(secret, sentAt, body) {
  const payload = String(sentAt) + "." + canonical(body);
  return crypto.createHmac("sha256", secret).update(payload).digest("hex");
}

function normalizeForHash(buf) {
  let text = buf.toString("utf-8");
  text = text.replace(/\r\n/g, "\n");
  if (text.endsWith("\n")) text = text.slice(0, -1);
  return Buffer.from(text, "utf-8");
}

function sha256Hex(data) {
  return crypto.createHash("sha256").update(data).digest("hex");
}

function computeSourceHashes() {
  const dirs = ["config", "endpoints", "deliveries"];
  const hashes = {};
  for (const d of dirs) {
    const base = path.join(APP, d);
    for (const fn of fs.readdirSync(base).sort()) {
      const fp = path.join(base, fn);
      if (!fs.statSync(fp).isFile()) continue;
      const rel = d + "/" + fn;
      hashes[rel] = sha256Hex(normalizeForHash(fs.readFileSync(fp)));
    }
  }
  return Object.fromEntries(Object.keys(hashes).sort().map((k) => [k, hashes[k]]));
}

function harmonicMean(values) {
  if (!values.length) return 0;
  let s = 0;
  for (const v of values) {
    if (v <= 0) return 0;
    s += 1 / v;
  }
  return roundDec(values.length / s);
}

function geometricMean(values) {
  const pos = values.filter((v) => v > 0);
  if (!pos.length) return 0;
  const logSum = pos.reduce((a, v) => a + Math.log(v), 0);
  return roundDec(Math.exp(logSum / pos.length));
}

function riskScore(severity, attemptNum, policy) {
  const mult = policy.risk_score.severity_multiplier[severity];
  const base = policy.risk_score.depth_weight_base;
  return roundDec(mult * Math.pow(base, attemptNum));
}

function isFailedStatus(st) {
  return st === "failed" || st === "timeout";
}

function isTerminal(st, attemptNum, rp) {
  return st === "dead_letter" || (attemptNum >= rp.max_attempts && st !== "success");
}

function expectedRetryGap(failedAttempt, nextAttemptNumber, rp) {
  const jitter = failedAttempt.jitter_pct || 0;
  const exp = nextAttemptNumber - 2;
  const raw = rp.base_delay_ms * Math.pow(rp.multiplier, exp) * (1 + jitter / 100);
  return Math.min(rp.max_delay_ms, raw);
}

function auditEndpoint(ep, delLog, policy, retryPolicies) {
  const rp = retryPolicies[ep.retry_policy];
  const findings = [];
  const deliveryRows = [];
  let invalidSigCount = 0;
  const successAttemptCounts = [];
  let successCount = 0;

  const seenDeliveryIds = new Map();

  const deliveries = [...delLog.deliveries].sort((a, b) =>
    a.delivery_id.localeCompare(b.delivery_id)
  );

  for (const del of deliveries) {
    if (seenDeliveryIds.has(del.delivery_id)) {
      findings.push({
        endpoint_id: ep.endpoint_id,
        delivery_id: del.delivery_id,
        finding: "duplicate_delivery_id",
        severity: policy.finding_severity.duplicate_delivery_id,
        detail: `delivery_id ${del.delivery_id} appears more than once`,
        risk_score: riskScore(
          policy.finding_severity.duplicate_delivery_id,
          1,
          policy
        ),
      });
    }
    seenDeliveryIds.set(del.delivery_id, true);

    const attempts = [...del.attempts].sort((a, b) => a.attempt_number - b.attempt_number);
    const nums = attempts.map((a) => a.attempt_number);
    for (let i = 1; i <= attempts.length; i++) {
      if (!nums.includes(i)) {
        findings.push({
          endpoint_id: ep.endpoint_id,
          delivery_id: del.delivery_id,
          finding: "orphan_attempt_gap",
          severity: policy.finding_severity.orphan_attempt_gap,
          detail: `missing attempt_number ${i}`,
          risk_score: riskScore(policy.finding_severity.orphan_attempt_gap, i, policy),
        });
      }
    }

    let terminalSeen = false;
    const attemptRows = [];

    for (let i = 0; i < attempts.length; i++) {
      const a = attempts[i];
      const exp = expectedSig(ep.secret, a.sent_at, a.body);
      const sigOk = a.signature === exp;
      if (!sigOk) {
        invalidSigCount++;
        findings.push({
          endpoint_id: ep.endpoint_id,
          delivery_id: del.delivery_id,
          finding: "invalid_signature",
          severity: policy.finding_severity.invalid_signature,
          detail: `attempt ${a.attempt_number} signature mismatch`,
          risk_score: riskScore(policy.finding_severity.invalid_signature, a.attempt_number, policy),
        });
      }

      if (Math.abs(a.received_at - a.sent_at) > policy.clock_skew_ms) {
        findings.push({
          endpoint_id: ep.endpoint_id,
          delivery_id: del.delivery_id,
          finding: "clock_skew_exceeded",
          severity: policy.finding_severity.clock_skew_exceeded,
          detail: `attempt ${a.attempt_number} skew ${Math.abs(a.received_at - a.sent_at)}ms`,
          risk_score: riskScore(
            policy.finding_severity.clock_skew_exceeded,
            a.attempt_number,
            policy
          ),
        });
      }

      if (terminalSeen && a.status === "success") {
        findings.push({
          endpoint_id: ep.endpoint_id,
          delivery_id: del.delivery_id,
          finding: "success_after_terminal",
          severity: policy.finding_severity.success_after_terminal,
          detail: `success at attempt ${a.attempt_number} after terminal state`,
          risk_score: riskScore(
            policy.finding_severity.success_after_terminal,
            a.attempt_number,
            policy
          ),
        });
      }

      if (isTerminal(a.status, a.attempt_number, rp)) terminalSeen = true;

      if (i + 1 < attempts.length) {
        const next = attempts[i + 1];
        if (isFailedStatus(a.status)) {
          const expected = expectedRetryGap(a, next.attempt_number, rp);
          const actual = next.sent_at - a.sent_at;
          if (actual < expected - 1) {
            findings.push({
              endpoint_id: ep.endpoint_id,
              delivery_id: del.delivery_id,
              finding: "retry_schedule_violation",
              severity: policy.finding_severity.retry_schedule_violation,
              detail: `gap ${actual}ms < expected ${roundDec(expected)}ms after attempt ${a.attempt_number}`,
              risk_score: riskScore(
                policy.finding_severity.retry_schedule_violation,
                a.attempt_number,
                policy
              ),
            });
          }
        }
      }

      attemptRows.push({
        attempt_number: a.attempt_number,
        status: a.status,
        sent_at: a.sent_at,
        received_at: a.received_at,
        signature_valid: sigOk,
        expected_signature: exp,
        actual_signature: a.signature,
      });
    }

    const finalStatus = attempts.length ? attempts[attempts.length - 1].status : "unknown";
    const allSigValid = attemptRows.every((r) => r.signature_valid);
    if (finalStatus === "success") {
      successCount++;
      successAttemptCounts.push(attempts.length);
    }

    deliveryRows.push({
      delivery_id: del.delivery_id,
      attempt_count: attempts.length,
      final_status: finalStatus,
      signature_valid: allSigValid,
      attempts: attemptRows,
    });
  }

  const total = deliveryRows.length;
  const failureRate = total ? roundDec((total - successCount) / total) : 0;

  return {
    endpoint_id: ep.endpoint_id,
    name: ep.name,
    retry_policy: ep.retry_policy,
    metrics: {
      total_deliveries: total,
      success_count: successCount,
      failure_rate: failureRate,
      avg_attempts_to_success: harmonicMean(successAttemptCounts),
      invalid_signature_count: invalidSigCount,
    },
    deliveries: deliveryRows,
    findings,
  };
}

function sortFindings(findings, policy) {
  const ranks = policy.severity_ranks;
  return [...findings].sort((a, b) => {
    const sr = ranks[a.severity] - ranks[b.severity];
    if (sr !== 0) return sr;
    const e = a.endpoint_id.localeCompare(b.endpoint_id);
    if (e !== 0) return e;
    const d = a.delivery_id.localeCompare(b.delivery_id);
    if (d !== 0) return d;
    const f = a.finding.localeCompare(b.finding);
    if (f !== 0) return f;
    const da = (a.detail.match(/attempt (\d+)/) || [0, 0])[1];
    const db = (b.detail.match(/attempt (\d+)/) || [0, 0])[1];
    return Number(da) - Number(db);
  });
}

function main() {
  const policy = JSON.parse(fs.readFileSync(path.join(APP, "config/policy.json"), "utf-8"));
  const retryPolicies = JSON.parse(
    fs.readFileSync(path.join(APP, "config/retry_policies.json"), "utf-8")
  );

  const endpointAudits = [];
  const allFindings = [];

  const epFiles = fs.readdirSync(path.join(APP, "endpoints")).filter((f) => f.endsWith(".json")).sort();
  for (const fn of epFiles) {
    const ep = JSON.parse(fs.readFileSync(path.join(APP, "endpoints", fn), "utf-8"));
    const delLog = JSON.parse(fs.readFileSync(path.join(APP, "deliveries", fn), "utf-8"));
    const audit = auditEndpoint(ep, delLog, policy, retryPolicies);
    endpointAudits.push(audit);
    allFindings.push(...audit.findings);
  }

  const findings = sortFindings(allFindings, policy);
  const fbs = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
  for (const f of findings) fbs[f.severity] = (fbs[f.severity] || 0) + 1;

  const scores = findings.map((f) => f.risk_score).filter((s) => s > 0);
  const totalDeliveries = endpointAudits.reduce((s, a) => s + a.metrics.total_deliveries, 0);

  const report = {
    schema_version: 1,
    summary: {
      total_endpoints: endpointAudits.length,
      total_deliveries: totalDeliveries,
      total_findings: findings.length,
      findings_by_severity: fbs,
      aggregate_risk_score: geometricMean(scores),
    },
    source_hashes: computeSourceHashes(),
    endpoint_audits: endpointAudits.sort((a, b) => a.endpoint_id.localeCompare(b.endpoint_id)),
    findings,
  };

  fs.mkdirSync(OUT, { recursive: true });
  const reportJson = JSON.stringify(report, null, 2) + "\n";
  const outPath = path.join(OUT, "webhook_audit.json");
  fs.writeFileSync(outPath, reportJson, "utf-8");
  const digest = sha256Hex(Buffer.from(reportJson, "utf-8"));
  fs.writeFileSync(path.join(OUT, "checksum.sha256"), `${digest}  webhook_audit.json\n`, "utf-8");
  console.log(`Wrote ${outPath}`);
  console.log(`SHA-256: ${digest}`);
}

main();
