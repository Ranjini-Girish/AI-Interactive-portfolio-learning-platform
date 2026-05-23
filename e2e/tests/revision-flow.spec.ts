import { test } from '@playwright/test';
import {
  resolveRegenerateRubric,
  resolveSendToReviewer,
  resolveStaticChecks,
} from '../lib/submission-flow';
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
    const regenerateRubric = resolveRegenerateRubric();
    const staticChecks = resolveStaticChecks();
    const headed = process.argv.includes('--headed');
    const taskId = await openRevisionTask(page, resolveRevisionTaskId());
    await assertRevisionWorkspace(page, taskId);

    if (headed) {
      // Headed: replace zip (Remove → pick snapshot-retention-replay.zip), paste rubrics.txt, then Resume.
      await page.pause();
    }

    const result = await runRevisionFlow(page, {
      taskId,
      skipOpen: true,
      zipPath,
      uploadZip: !!zipPath && !headed && process.env.SNORKEL_SKIP_ZIP_UPLOAD !== '1',
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
