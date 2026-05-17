import { test } from '@playwright/test';
import { runNewTaskSubmission } from '../lib/submission-flow';
import { resolveTaskZipPathOrThrow } from '../lib/task-zip';

/**
 * End-to-end: submit a new Terminus-2nd-Edition task on experts.snorkel-ai.com.
 *
 * Requires auth setup (saved session) and a task bundle:
 *   SNORKEL_TASK_DIR=tasks/export-batch-window-audit
 *   or SNORKEL_TASK_ZIP=C:\path\to\task.zip
 *
 * Dry run (upload + form only, no platform Submit):
 *   SNORKEL_DRY_RUN=1 npm run submit:new
 *
 * Live submit (cycle-1: static checks + Submit, Send to reviewer ON):
 *   SNORKEL_TASK_DIR=tasks/my-task npm run submit:new:live
 */
test.describe('Submit new Terminus task (E2E)', () => {
  test('upload and prepare new submission (dry run)', async ({ page }) => {
    test.skip(process.env.SNORKEL_DRY_RUN !== '1', 'Set SNORKEL_DRY_RUN=1 for dry run');
    test.setTimeout(300_000);

    const zipPath = resolveTaskZipPathOrThrow();
    const result = await runNewTaskSubmission(page, {
      zipPath,
      confirmPromptCheck: true,
      regenerateRubric: true,
      runStaticChecks: false,
      submitToPlatform: false,
    });

    test.info().attach('submission-url', { body: result.submissionUrl });
  });

  test('submit new task to platform (cycle 1)', async ({ page }) => {
    test.skip(process.env.SNORKEL_SUBMIT !== '1', 'Set SNORKEL_SUBMIT=1 for live platform submit');

    test.setTimeout(600_000);

    const zipPath = resolveTaskZipPathOrThrow();
    const runStaticChecks = process.env.SNORKEL_STATIC_CHECKS !== '0';

    const result = await runNewTaskSubmission(page, {
      zipPath,
      confirmPromptCheck: true,
      regenerateRubric: process.env.SNORKEL_REGENERATE_RUBRIC !== '0',
      runStaticChecks,
      submitToPlatform: true,
    });

    console.log('Submitted:', result.zipPath);
    console.log('URL:', result.submissionUrl);
    test.info().attach('submission-url', { body: result.submissionUrl });
  });
});
