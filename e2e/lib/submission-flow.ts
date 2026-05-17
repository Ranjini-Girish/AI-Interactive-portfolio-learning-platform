import { expect, type Page } from '@playwright/test';
import path from 'node:path';
import { openTerminusSubmissionStart, waitForSubmissionWorkspace } from './snorkel-home';
import { resolveTaskZipPath } from './task-zip';

export type SubmissionFlowOptions = {
  /** Absolute path to a .zip task bundle. */
  zipPath: string;
  /** Check the required Prompt Check attestation (initial submission). */
  confirmPromptCheck?: boolean;
  /** Check "Click here to generate rubric(s)" when present (recommended for cycle-1 CI). */
  regenerateRubric?: boolean;
  /** Check "Send to reviewer?" when present (default true). */
  sendToReviewer?: boolean;
  /** Click Check feedback / fast static checks before final submit. */
  runStaticChecks?: boolean;
  /** Click the final Submit button (triggers platform CI). */
  submitToPlatform?: boolean;
};

export type NewTaskSubmissionResult = {
  zipPath: string;
  submissionUrl: string;
  submitted: boolean;
};

export { resolveTaskZipPath, resolveTaskZipPathOrThrow } from './task-zip';

export async function assertNewSubmissionForm(page: Page): Promise<void> {
  await expect(page).toHaveURL(/\/projects\/[^/]+\/submission-[^/]+\/review/);
  await expect(page.getByText('Terminal bench 2.0 task submission')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Submit' })).toBeVisible();
  await expect(
    page.getByText(/Upload terminal bench 2\.0 submission here/i).first(),
  ).toBeVisible();
  const promptCheck = page.getByRole('checkbox', {
    name: /confirm that the above is true/i,
  });
  if (await promptCheck.count()) {
    await expect(promptCheck).toBeVisible();
  }
}

export async function uploadSubmissionZip(page: Page, zipPath: string): Promise<void> {
  const fileInput = page.locator('input[type="file"]').first();
  await expect(fileInput).toBeAttached();
  await fileInput.setInputFiles(zipPath);
  await expect(page.getByText(path.basename(zipPath))).toBeVisible({ timeout: 120_000 });
}

export async function confirmPromptAttestation(page: Page): Promise<void> {
  const box = page.getByRole('checkbox', {
    name: /confirm that the above is true/i,
  });
  await expect(box).toBeVisible({ timeout: 30_000 });
  await box.check();
  await expect(box).toBeChecked();
}

async function setCheckboxIfPresent(
  page: Page,
  name: RegExp | string,
  checked: boolean,
): Promise<boolean> {
  const box = page.getByRole('checkbox', { name });
  if ((await box.count()) === 0) return false;
  await box.scrollIntoViewIfNeeded();
  if (checked) {
    await box.check();
    await expect(box).toBeChecked();
  } else {
    await box.uncheck();
    await expect(box).not.toBeChecked();
  }
  return true;
}

/** Cycle-1: enable rubric generation when the control is on the form. */
export async function setRegenerateRubric(page: Page, enabled: boolean): Promise<void> {
  await setCheckboxIfPresent(page, /generate rubric/i, enabled);
}

/** Check or uncheck "Send to reviewer?" when the control exists. */
export async function setSendToReviewer(page: Page, enabled: boolean): Promise<void> {
  await setCheckboxIfPresent(page, 'Send to reviewer?', enabled);
}

/** Default true; set SNORKEL_SEND_TO_REVIEWER=0 to force unchecked. */
export function resolveSendToReviewer(override?: boolean): boolean {
  if (override !== undefined) return override;
  return process.env.SNORKEL_SEND_TO_REVIEWER !== '0';
}

export async function runFastStaticChecks(page: Page): Promise<void> {
  await expect(page.getByText(/Fast static checks/i)).toBeVisible();
  const checkButton = page
    .getByRole('button', { name: /^Check feedback$/i })
    .or(page.getByRole('button', { name: /fast static/i }))
    .first();
  await expect(checkButton).toBeVisible();
  await checkButton.click();
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText ?? '';
      return (
        /static check|check complete|passed|failed|error|feedback/i.test(text) &&
        !text.includes('Complete required fields first')
      );
    },
    null,
    { timeout: 180_000 },
  );
}

export async function submitToPlatform(page: Page): Promise<void> {
  const submit = page.getByRole('button', { name: 'Submit' });
  await submit.scrollIntoViewIfNeeded();
  await expect(submit).toBeEnabled({ timeout: 60_000 });
  await submit.click();
  await expect(
    page.getByText(/submitted|saving|running|check feedback|evaluation/i).first(),
  ).toBeVisible({ timeout: 180_000 });
}

/**
 * Full new-task submission per Terminus Edition-2 cycle-1:
 * Home → Submission Start → upload zip → Prompt Check → rubric on → send-to-reviewer on
 * → optional static checks → optional Submit.
 */
export async function runNewTaskSubmission(
  page: Page,
  options: SubmissionFlowOptions,
): Promise<NewTaskSubmissionResult> {
  const confirmPrompt = options.confirmPromptCheck ?? true;
  const regenerateRubric = options.regenerateRubric ?? true;
  const sendToReviewer = resolveSendToReviewer(options.sendToReviewer);
  const staticChecks = options.runStaticChecks ?? false;
  const submit = options.submitToPlatform ?? false;

  await openTerminusSubmissionStart(page);
  await assertNewSubmissionForm(page);
  await uploadSubmissionZip(page, options.zipPath);

  if (confirmPrompt) {
    await confirmPromptAttestation(page);
  }

  if (regenerateRubric) {
    await setRegenerateRubric(page, true);
  }

  await setSendToReviewer(page, sendToReviewer);

  if (staticChecks) {
    await runFastStaticChecks(page);
  }

  if (submit) {
    await submitToPlatform(page);
  }

  return {
    zipPath: options.zipPath,
    submissionUrl: page.url(),
    submitted: submit,
  };
}

/** @deprecated Use runNewTaskSubmission with an explicit zipPath. */
export async function runSubmissionFlow(
  page: Page,
  options: Partial<SubmissionFlowOptions> & { zipPath?: string } = {},
): Promise<void> {
  const zipPath = options.zipPath ?? resolveTaskZipPath();
  if (!zipPath) {
    throw new Error('zipPath is required for runSubmissionFlow');
  }
  await runNewTaskSubmission(page, {
    zipPath,
    confirmPromptCheck: options.confirmPromptCheck,
    regenerateRubric: options.regenerateRubric,
    sendToReviewer: options.sendToReviewer,
    runStaticChecks: options.runStaticChecks,
    submitToPlatform: options.submitToPlatform,
  });
}

export { waitForSubmissionWorkspace };
