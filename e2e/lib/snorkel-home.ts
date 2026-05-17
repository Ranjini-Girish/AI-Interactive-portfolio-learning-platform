import { expect, type Page } from '@playwright/test';

export const SNORKEL_HOME_PATH = '/home';
export const TERMINUS_PROJECT_LABEL = 'Terminus-2nd-Edition';

/** Index of the main Terminus-2nd-Edition Submission "Start" button on /home. */
export const TERMINUS_SUBMISSION_START_INDEX = 1;

export async function goToHome(page: Page): Promise<void> {
  await page.goto(SNORKEL_HOME_PATH, { waitUntil: 'domcontentloaded', timeout: 90_000 });
  await expect(page.getByRole('heading', { name: 'My projects' })).toBeVisible({
    timeout: 60_000,
  });
}

export async function openTerminusSubmissionStart(page: Page): Promise<void> {
  await goToHome(page);
  await Promise.all([
    page.waitForURL(/\/projects\/[^/]+\/submission-[^/]+\//, { timeout: 60_000 }),
    page.getByRole('button', { name: 'Start' }).nth(TERMINUS_SUBMISSION_START_INDEX).click(),
  ]);
  await waitForSubmissionWorkspace(page);
}

/**
 * Open a task in the revision queue. Uses SNORKEL_REVISION_TASK_ID when set;
 * otherwise clicks the first "Revise" card on home.
 */
export async function openRevisionTask(page: Page, taskId?: string): Promise<string> {
  const id = taskId ?? process.env.SNORKEL_REVISION_TASK_ID;
  await goToHome(page);

  if (id) {
    const revise = page
      .locator('motion-div, article, li, div')
      .filter({ hasText: id })
      .filter({ has: page.getByRole('button', { name: 'Revise' }) })
      .first()
      .getByRole('button', { name: 'Revise' });
    await expect(revise).toBeVisible({ timeout: 30_000 });
    await Promise.all([
      page.waitForURL(/\/projects\/[^/]+\/submission-[^/]+\//, { timeout: 60_000 }),
      revise.click(),
    ]);
    return id;
  }

  const firstRevise = page.getByRole('button', { name: 'Revise' }).first();
  await expect(firstRevise).toBeVisible();
  const resolvedId = await firstRevise.evaluate((el) => {
    let node: HTMLElement | null = el.parentElement;
    for (let depth = 0; depth < 12 && node; depth++, node = node.parentElement) {
      const match = (node.innerText || '').match(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
      );
      if (match) return match[0];
    }
    return '';
  });
  await Promise.all([
    page.waitForURL(/\/projects\/[^/]+\/submission-[^/]+\//, { timeout: 60_000 }),
    firstRevise.click(),
  ]);
  return resolvedId;
}

export async function waitForSubmissionWorkspace(page: Page): Promise<void> {
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText ?? '';
      return (
        text.includes('Terminal bench 2.0 task submission') &&
        text.includes('Submit') &&
        !text.includes('My projects')
      );
    },
    null,
    { timeout: 90_000 },
  );
}
