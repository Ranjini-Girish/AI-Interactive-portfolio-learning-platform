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

/** Home revision cards use data-testid="{assignmentId}-Terminus-2nd-Edition". */
function revisionCardReviseButtonByAssignmentId(page: Page, assignmentId: string) {
  return page
    .getByTestId(`${assignmentId}-Terminus-2nd-Edition`)
    .getByRole('button', { name: 'Revise' });
}

async function clickReviseAndWait(page: Page, revise: ReturnType<Page['getByRole']>): Promise<void> {
  await expect(revise).toBeVisible({ timeout: 30_000 });
  await revise.scrollIntoViewIfNeeded();
  await Promise.all([
    page.waitForURL(/\/projects\/[^/]+\/submission-[^/]+\//, { timeout: 60_000 }),
    revise.click(),
  ]);
}

/** Match revision cards by platform UID text when assignment test id differs. */
function revisionCardReviseButtonByUid(page: Page, uid: string) {
  return page
    .locator('div, article, li, section')
    .filter({ hasText: uid })
    .filter({ has: page.getByRole('button', { name: 'Revise' }) })
    .first()
    .getByRole('button', { name: 'Revise' });
}

function revisionCardReviseButtonByLabel(page: Page, label: string | RegExp) {
  return page
    .locator('motion-div, article, li, div')
    .filter({ hasText: label })
    .filter({ has: page.getByRole('button', { name: 'Revise' }) })
    .first()
    .getByRole('button', { name: 'Revise' });
}

async function extractAssignmentIdFromReviseButton(
  reviseButton: ReturnType<Page['getByRole']>,
): Promise<string> {
  return reviseButton.evaluate((el) => {
    let node: HTMLElement | null = el.parentElement;
    for (let depth = 0; depth < 12 && node; depth++, node = node.parentElement) {
      const match = (node.innerText || '').match(
        /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i,
      );
      if (match) return match[0];
    }
    return '';
  });
}

/**
 * Open a task in the revision queue.
 * Priority: explicit taskId arg → SNORKEL_REVISION_TASK_ID → SNORKEL_REVISION_TASK_NAME
 * → first "Revise" card on home.
 */
export async function openRevisionTask(page: Page, taskId?: string): Promise<string> {
  const id = taskId ?? process.env.SNORKEL_REVISION_TASK_ID;
  const name = process.env.SNORKEL_REVISION_TASK_NAME;
  await goToHome(page);

  if (id) {
    const byAssignment = revisionCardReviseButtonByAssignmentId(page, id);
    const byUid = revisionCardReviseButtonByUid(page, id);
  if (await byAssignment.count()) {
      await clickReviseAndWait(page, byAssignment);
      return id;
    }
    await clickReviseAndWait(page, byUid);
    return id;
  }

  if (name) {
    const revise = revisionCardReviseButtonByLabel(page, name);
    await expect(revise).toBeVisible({ timeout: 30_000 });
    const resolvedId = await extractAssignmentIdFromReviseButton(revise);
    await clickReviseAndWait(page, revise);
    return resolvedId;
  }

  const firstRevise = page.getByRole('button', { name: 'Revise' }).first();
  await expect(firstRevise).toBeVisible();
  const resolvedId = await extractAssignmentIdFromReviseButton(firstRevise);
  await clickReviseAndWait(page, firstRevise);
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
