import { test } from '@playwright/test';
import { resolveSendToReviewer } from '../lib/submission-flow';
import {
  resolveTaskNameFromEnv,
  saveSubmissionMetadata,
  shouldSaveSubmissionMetadata,
} from '../lib/submission-metadata';
import { resolveTaskZipPath } from '../lib/task-zip';
import {
  assertRevisionWorkspace,
  resolveRevisionTaskId,
  runRevisionFlow,
  setRegenerateRubric,
  setSendToReviewer,
} from '../lib/revision-flow';
import { openRevisionTask } from '../lib/snorkel-home';

test.describe('Snorkel Experts — Revision flow', () => {
  test('opens a revision task from home', async ({ page }) => {
    const taskId = await openRevisionTask(page, resolveRevisionTaskId());
    await assertRevisionWorkspace(page, taskId || undefined);
  });

  test('revision iteration defaults: send-to-reviewer on, rubric unchecked', async ({ page }) => {
    await runRevisionFlow(page, {
      taskId: resolveRevisionTaskId(),
      regenerateRubric: false,
      submitToPlatform: false,
    });
  });

  test('can stage rubric regenerate toggle with send-to-reviewer on', async ({ page }) => {
    await openRevisionTask(page, resolveRevisionTaskId());
    await assertRevisionWorkspace(page);

    await setSendToReviewer(page, true);
    await setRegenerateRubric(page, true);
    await setRegenerateRubric(page, false);
    await setSendToReviewer(page, true);
  });

  test('full revise submit when SNORKEL_SUBMIT=1', async ({ page }) => {
    test.skip(process.env.SNORKEL_SUBMIT !== '1', 'Set SNORKEL_SUBMIT=1 to run live platform submit');

    const zipPath = resolveTaskZipPath();
    const regenerateRubric = process.env.SNORKEL_REGENERATE_RUBRIC === '1';
    const staticChecks = process.env.SNORKEL_STATIC_CHECKS === '1';
    const result = await runRevisionFlow(page, {
      taskId: resolveRevisionTaskId(),
      zipPath,
      uploadZip: !!zipPath,
      regenerateRubric,
      runStaticChecks: staticChecks,
      submitToPlatform: true,
    });

    if (shouldSaveSubmissionMetadata(result.submitted) && zipPath) {
      const metaPath = saveSubmissionMetadata({
        taskName: resolveTaskNameFromEnv(zipPath) ?? '',
        flow: 'revision',
        dryRun: false,
        submitted: true,
        submissionUrl: result.submissionUrl,
        zipPath,
        revisionTaskId: result.revisionTaskId,
        options: {
          sendToReviewer: resolveSendToReviewer(),
          regenerateRubric,
          staticChecks,
        },
      });
      console.log('Saved metadata:', metaPath);
      test.info().attach('platform-metadata', { body: metaPath });
    }

    test.info().attach('submission-url', { body: result.submissionUrl });
  });
});
