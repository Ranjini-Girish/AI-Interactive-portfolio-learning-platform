import { expect, type Page } from '@playwright/test';
import path from 'node:path';
import { openRevisionTask, waitForSubmissionWorkspace } from './snorkel-home';
import { fillAgentRubric, resolveRubricPath } from './rubric';
import {
  resolveRegenerateRubric,
  resolveSendToReviewer,
  resolveStaticChecks,
  resolveTaskZipPath,
  runFastStaticChecks,
  setSendToReviewer,
  uploadSubmissionZip,
} from './submission-flow';

export type RevisionFlowOptions = {
  taskId?: string;
  /** When true, caller already opened the revision workspace (e.g. after page.pause()). */
  skipOpen?: boolean;
  zipPath?: string;
  /** Re-upload a revised task zip before other actions. */
  uploadZip?: boolean;
  /** Path to rubrics.txt; defaults from SNORKEL_RUBRIC_FILE or tasks/<name>/rubrics.txt. */
  rubricPath?: string;
  /** Paste rubric into Agent-generated rubric editor (default true when rubricPath resolves). */
  fillRubric?: boolean;
  /** Toggle "Send to reviewer?" (default true). */
  sendToReviewer?: boolean;
  /** Toggle "Click here to generate rubric(s)". */
  regenerateRubric?: boolean;
  runStaticChecks?: boolean;
  submitToPlatform?: boolean;
};

export type RevisionFlowResult = {
  revisionTaskId: string;
  submissionUrl: string;
  zipPath?: string;
  rubricPath?: string;
  submitted: boolean;
};

export async function assertRevisionWorkspace(page: Page, taskId?: string): Promise<void> {
  await waitForSubmissionWorkspace(page);
  await expect(page).toHaveURL(/\/projects\/[^/]+\/submission-[^/]+\/review/);
  await expect(page.getByText(/Reviewer Feedback|AutoEval|revision/i).first()).toBeVisible();
  await expect(page.getByRole('checkbox', { name: 'Send to reviewer?' })).toBeVisible();
  await expect(
    page.getByRole('checkbox', { name: /generate rubric/i }),
  ).toBeVisible();
  if (taskId) {
    await expect(page.getByText(taskId)).toBeVisible();
  }
}

export { setSendToReviewer } from './submission-flow';

export async function setRegenerateRubric(page: Page, enabled: boolean): Promise<void> {
  const box = page.getByRole('checkbox', { name: /generate rubric/i });
  await box.scrollIntoViewIfNeeded();
  if (enabled) {
    await box.check();
    await expect(box).toBeChecked();
  } else {
    await box.uncheck();
    await expect(box).not.toBeChecked();
  }
}

export async function runRevisionFlow(
  page: Page,
  options: RevisionFlowOptions = {},
): Promise<RevisionFlowResult> {
  let taskId = options.taskId ?? '';
  if (!options.skipOpen) {
    taskId = await openRevisionTask(page, options.taskId);
    await assertRevisionWorkspace(page, taskId);
  }

  const zipPath = options.zipPath ?? resolveTaskZipPath();
  if (options.uploadZip && zipPath) {
    await uploadSubmissionZip(page, zipPath);
  }

  const regenerateRubric = resolveRegenerateRubric(options.regenerateRubric);
  await setRegenerateRubric(page, regenerateRubric);

  const rubricPath = options.rubricPath ?? resolveRubricPath(zipPath);
  const shouldFillRubric =
    options.fillRubric ?? process.env.SNORKEL_SKIP_RUBRIC_FILL !== '1';
  if (shouldFillRubric && rubricPath) {
    await fillAgentRubric(page, rubricPath);
  }

  const sendToReviewer = resolveSendToReviewer(options.sendToReviewer);
  await setSendToReviewer(page, sendToReviewer);

  const staticChecks = resolveStaticChecks(options.runStaticChecks);
  if (staticChecks) {
    await runFastStaticChecks(page);
  }

  const submit = options.submitToPlatform ?? false;
  if (submit) {
    await page.getByRole('button', { name: 'Submit' }).click();
    await expect(page.getByText(/submitted|saving/i).first()).toBeVisible({
      timeout: 120_000,
    });
  }

  return {
    revisionTaskId: taskId,
    submissionUrl: page.url(),
    zipPath: zipPath ?? undefined,
    rubricPath: rubricPath ?? undefined,
    submitted: submit,
  };
}

export function resolveRevisionTaskId(): string | undefined {
  return process.env.SNORKEL_REVISION_TASK_ID;
}

export function resolveRevisionTaskName(): string | undefined {
  return process.env.SNORKEL_REVISION_TASK_NAME;
}
