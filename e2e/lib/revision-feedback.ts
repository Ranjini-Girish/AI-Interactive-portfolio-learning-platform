import fs from 'node:fs';
import path from 'node:path';
import type { Page } from '@playwright/test';
import { parseSubmissionUrl } from './submission-metadata';

const REPO_ROOT = path.resolve(__dirname, '..', '..');

export type RevisionContext = {
  capturedAt: string;
  revisionTaskId: string;
  submissionUrl: string;
  assignmentId: string | null;
  platformAttachedZip: string | null;
  autoEvalSummary: string | null;
  difficultySummary: string | null;
  qualityCheckSummary: string | null;
  reviewerFeedback: string | null;
  revisionReasons: string[];
  rawPageExcerpt: string;
};

function extractSection(body: string, startPattern: RegExp, endPattern: RegExp): string | null {
  const start = body.search(startPattern);
  if (start < 0) return null;
  const slice = body.slice(start);
  const end = slice.search(endPattern);
  const chunk = end > 0 ? slice.slice(0, end) : slice.slice(0, 2500);
  return chunk.trim() || null;
}

function deriveRevisionReasons(ctx: Omit<RevisionContext, 'revisionReasons' | 'capturedAt'>): string[] {
  const reasons: string[] = [];
  const blob = [
    ctx.autoEvalSummary,
    ctx.difficultySummary,
    ctx.qualityCheckSummary,
    ctx.reviewerFeedback,
    ctx.rawPageExcerpt,
  ]
    .filter(Boolean)
    .join('\n');

  if (/Build status:\s*FAILED/i.test(blob)) reasons.push('autoeval_build_failed');
  if (/Oracle failed|oracle failed|Oracle solution failed/i.test(blob)) reasons.push('oracle_failed');
  if (/Requires at least HARD/i.test(blob)) reasons.push('difficulty_below_hard');
  if (/Requires at least MEDIUM/i.test(blob)) reasons.push('difficulty_below_medium');
  if (/NEEDS_REVISION|Needs Revision/i.test(blob)) reasons.push('platform_needs_revision');
  if (/Quality Check Results[\s\S]*❌/i.test(blob)) reasons.push('quality_check_failure');
  if (/behavior_in_task_description[\s\S]*❌/i.test(blob)) reasons.push('behavior_not_in_task_description');
  if (/anti_cheating[\s\S]*❌/i.test(blob)) reasons.push('anti_cheating_failure');
  if (/not tested with any agents as the Oracle/i.test(blob)) reasons.push('agents_skipped_oracle_failed');
  if (reasons.length === 0 && ctx.reviewerFeedback) reasons.push('reviewer_feedback_present');
  if (reasons.length === 0 && ctx.autoEvalSummary) reasons.push('autoeval_feedback_present');
  return [...unique(reasons)];
}

function unique(items: string[]): string[] {
  return [...new Set(items)];
}

export type RevisionAuditParams = {
  revisionTaskId: string;
  platformTaskSlug: string | null;
  assignmentId: string | null;
  submissionUrl: string;
  capturedAt: string;
  revisionReasons: string[];
  autoEval: {
    buildFailed: boolean;
    buildId: string | null;
    summary: string | null;
  };
  difficulty: {
    failed: boolean;
    summary: string | null;
  };
  qualityCheck: {
    failed: boolean;
    failures: string[];
    summary: string | null;
  };
  oracle: {
    failed: boolean;
    agentsSkipped: boolean;
  };
  swapUpload?: {
    localTaskSlug: string | null;
    localZipPath: string | null;
    excludedPlatformZip: string | null;
  };
};

function extractBuildId(text: string | null): string | null {
  if (!text) return null;
  const m = text.match(/Build ID:\s*([^\s.]+)/i);
  return m?.[1] ?? null;
}

function extractQualityFailures(summary: string | null): string[] {
  if (!summary) return [];
  const failures: string[] = [];
  const patterns: Array<[RegExp, string]> = [
    [/behavior_in_task_description[\s\S]*?❌/i, 'behavior_in_task_description'],
    [/anti_cheating[\s\S]*?❌/i, 'anti_cheating'],
    [/behavior_in_tests[\s\S]*?❌/i, 'behavior_in_tests'],
    [/instruction_quality[\s\S]*?❌/i, 'instruction_quality'],
  ];
  for (const [re, label] of patterns) {
    if (re.test(summary)) failures.push(label);
  }
  return unique(failures);
}

export function buildRevisionAuditParams(
  ctx: RevisionContext,
  swap?: RevisionAuditParams['swapUpload'],
): RevisionAuditParams {
  const blob = ctx.rawPageExcerpt ?? '';
  const platformSlug = ctx.platformAttachedZip?.replace(/\.zip$/i, '') ?? null;
  const qcFailures = extractQualityFailures(ctx.qualityCheckSummary);

  return {
    revisionTaskId: ctx.revisionTaskId,
    platformTaskSlug: platformSlug,
    assignmentId: ctx.assignmentId,
    submissionUrl: ctx.submissionUrl,
    capturedAt: ctx.capturedAt,
    revisionReasons: ctx.revisionReasons,
    autoEval: {
      buildFailed: /Build status:\s*FAILED/i.test(ctx.autoEvalSummary ?? blob),
      buildId: extractBuildId(ctx.autoEvalSummary),
      summary: ctx.autoEvalSummary,
    },
    difficulty: {
      failed: Boolean(ctx.difficultySummary),
      summary: ctx.difficultySummary,
    },
    qualityCheck: {
      failed: qcFailures.length > 0 || /Quality Check Results[\s\S]*❌/i.test(ctx.qualityCheckSummary ?? ''),
      failures: qcFailures,
      summary: ctx.qualityCheckSummary,
    },
    oracle: {
      failed: /Oracle failed|oracle failed|Oracle solution failed/i.test(blob),
      agentsSkipped: /not tested with any agents as the Oracle/i.test(blob),
    },
    swapUpload: swap,
  };
}

export async function extractRevisionContext(
  page: Page,
  revisionTaskId: string,
): Promise<RevisionContext> {
  const body = await page.locator('body').innerText();
  const submissionUrl = page.url();
  const parsed = parseSubmissionUrl(submissionUrl);

  const uidMatch = body.match(
    /UID:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i,
  );

  const zipMatch = body.match(/([\w-]+\.zip)\s*\n\d{1,2}\/\d{1,2}\/\d{4}/);

  const autoEvalSummary = extractSection(
    body,
    /AutoEval Execution Summary:/i,
    /Do you disagree with the reviewer feedback\?/i,
  );
  const difficultySummary = extractSection(body, /Difficulty:\s*❌/i, /Download difficulty check/i);
  const qualityCheckSummary = extractSection(
    body,
    /Quality check summary/i,
    /Generate your Rubric/i,
  );
  const reviewerFeedback = extractSection(
    body,
    /Reviewer Feedback/i,
    /AutoEval Execution Summary:/i,
  );

  const partial = {
    revisionTaskId: uidMatch?.[1] ?? revisionTaskId,
    submissionUrl,
    assignmentId: parsed.assignmentId,
    platformAttachedZip: zipMatch?.[1] ?? null,
    autoEvalSummary,
    difficultySummary,
    qualityCheckSummary,
    reviewerFeedback,
    rawPageExcerpt: body.slice(0, 12000),
  };

  return {
    capturedAt: new Date().toISOString(),
    ...partial,
    revisionReasons: deriveRevisionReasons(partial),
  };
}

export function saveRevisionContext(
  ctx: RevisionContext,
  uploadSlug?: string,
  swapZipPath?: string,
): string {
  const auditDir = path.join(REPO_ROOT, 'e2e', 'audit');
  fs.mkdirSync(auditDir, { recursive: true });

  const primary = path.join(
    auditDir,
    `revision-${ctx.revisionTaskId}-context.json`,
  );
  fs.writeFileSync(primary, `${JSON.stringify(ctx, null, 2)}\n`, 'utf8');

  const paramsPath = path.join(auditDir, `revision-${ctx.revisionTaskId}-params.json`);
  const params = buildRevisionAuditParams(ctx, {
    localTaskSlug: uploadSlug ?? null,
    localZipPath: swapZipPath ?? null,
    excludedPlatformZip: ctx.platformAttachedZip,
  });
  fs.writeFileSync(paramsPath, `${JSON.stringify(params, null, 2)}\n`, 'utf8');

  const platformSlug = ctx.platformAttachedZip?.replace(/\.zip$/i, '');
  if (platformSlug) {
    const platformDir = path.join(REPO_ROOT, 'tasks', platformSlug);
    if (fs.existsSync(platformDir)) {
      fs.writeFileSync(
        path.join(platformDir, 'revision-params.json'),
        `${JSON.stringify(params, null, 2)}\n`,
        'utf8',
      );
    }
  }

  if (uploadSlug) {
    const taskDir = path.join(REPO_ROOT, 'tasks', uploadSlug);
    fs.mkdirSync(taskDir, { recursive: true });
    const taskLocal = path.join(taskDir, 'revision-context.json');
    fs.writeFileSync(taskLocal, `${JSON.stringify(ctx, null, 2)}\n`, 'utf8');
  }

  return primary;
}
