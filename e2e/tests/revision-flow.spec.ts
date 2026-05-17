import { test } from '@playwright/test';
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

    await runRevisionFlow(page, {
      taskId: resolveRevisionTaskId(),
      uploadZip: !!resolveRevisionTaskId() && !!process.env.SNORKEL_TASK_ZIP,
      regenerateRubric: process.env.SNORKEL_REGENERATE_RUBRIC === '1',
      runStaticChecks: process.env.SNORKEL_STATIC_CHECKS === '1',
      submitToPlatform: true,
    });
  });
});
