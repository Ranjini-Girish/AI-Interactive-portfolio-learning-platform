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
  buildLogsSummary: string | null;
  difficultySummary: string | null;
  qualityCheckSummary: string | null;
  agentReviewSummary: string | null;
  testQualitySummary: string | null;
  reviewerFeedback: string | null;
  revisionReasons: string[];
  feedbackExpandCount: number;
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
  if (/Quality Check Results[\s\S]*❌\s*-/i.test(blob)) reasons.push('quality_check_failure');
  if (/❌\s*-\s*behavior_in_task_description/i.test(blob)) {
    reasons.push('behavior_not_in_task_description');
  }
  if (/❌\s*-\s*anti_cheating/i.test(blob)) reasons.push('anti_cheating_failure');
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
    [/❌\s*-\s*behavior_in_task_description/i, 'behavior_in_task_description'],
    [/❌\s*-\s*anti_cheating/i, 'anti_cheating'],
    [/❌\s*-\s*behavior_in_tests/i, 'behavior_in_tests'],
    [/❌\s*-\s*instruction_quality/i, 'instruction_quality'],
  ];
  for (const [re, label] of patterns) {
    if (re.test(summary)) failures.push(label);
  }
  return unique(failures);
}

const RAW_EXCERPT_LIMIT = 80_000;

/** Expand collapsed portal feedback before scraping innerText. */
export async function expandRevisionFeedbackSections(page: Page): Promise<number> {
  let expandedCount = 0;

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(300);

  // Ensure human reviewer panel is open (accordion may start collapsed).
  const reviewerToggle = page.getByRole('button', { name: /^Reviewer Feedback$/i });
  try {
    if (await reviewerToggle.isVisible()) {
      const expanded = await reviewerToggle.getAttribute('aria-expanded');
      if (expanded !== 'true') {
        await reviewerToggle.click({ timeout: 8_000 });
        expandedCount++;
        await page.waitForTimeout(300);
      }
    }
  } catch {
    // Optional panel.
  }

  for (let pass = 0; pass < 4; pass++) {
    const expandButtons = page.getByRole('button', { name: /^Expand$/i });
    const count = await expandButtons.count();
    let clickedThisPass = 0;

    for (let i = 0; i < count; i++) {
      const btn = expandButtons.nth(i);
      try {
        if (!(await btn.isVisible())) continue;
        await btn.scrollIntoViewIfNeeded();
        await btn.click({ timeout: 8_000 });
        clickedThisPass++;
        expandedCount++;
        await page.waitForTimeout(250);
      } catch {
        // Button may detach after a prior expand; continue.
      }
    }

    if (clickedThisPass === 0) break;
  }

  for (const label of [/Show Build Logs/i, /Download difficulty check results/i]) {
    const control = page.getByRole('button', { name: label }).first();
    try {
      if (await control.isVisible()) {
        await control.scrollIntoViewIfNeeded();
        await control.click({ timeout: 8_000 });
        expandedCount++;
        await page.waitForTimeout(500);
      }
    } catch {
      // Optional control — ignore.
    }
  }

  // Expand clicks on code editors can open modal dialogs — close them so later steps can scroll.
  for (let i = 0; i < 3; i++) {
    const closeDialog = page.getByRole('button', { name: /^Close$/i });
    if (!(await closeDialog.isVisible().catch(() => false))) break;
    await closeDialog.click({ timeout: 5_000 }).catch(() => undefined);
    await page.waitForTimeout(200);
  }

  await page.keyboard.press('Escape').catch(() => undefined);

  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(400);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(200);

  return expandedCount;
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
  const feedbackExpandCount = await expandRevisionFeedbackSections(page);
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
  const buildLogsSummary = extractSection(
    body,
    /Show Build Logs|Build Logs|CodeBuild/i,
    /Summary \(optional\)|Fast static checks/i,
  );
  const difficultySummary =
    extractSection(body, /Difficulty:\s*❌/i, /Download difficulty check/i) ??
    extractSection(body, /Summary \(optional\)/i, /Quality check summary/i);
  const qualityCheckSummary = extractSection(
    body,
    /Quality check summary/i,
    /Agent review \(optional\)/i,
  );
  const agentReviewSummary = extractSection(
    body,
    /Agent review \(optional\)/i,
    /Test Quality Report \(optional\)/i,
  );
  const testQualitySummary = extractSection(
    body,
    /Test Quality Report \(optional\)/i,
    /Comments for Reviewer \(optional\)/i,
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
    buildLogsSummary,
    difficultySummary,
    qualityCheckSummary,
    agentReviewSummary,
    testQualitySummary,
    reviewerFeedback,
    feedbackExpandCount,
    rawPageExcerpt: body.slice(0, RAW_EXCERPT_LIMIT),
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
