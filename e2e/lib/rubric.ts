import { expect, type Locator, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { resolveTaskNameFromEnv } from './submission-metadata';

const REPO_ROOT = path.resolve(__dirname, '..', '..');

/** Resolve rubrics.txt from SNORKEL_RUBRIC_FILE or tasks/<name>/rubrics.txt beside the zip. */
export function resolveRubricPath(zipPath?: string): string | undefined {
  const explicit = process.env.SNORKEL_RUBRIC_FILE;
  if (explicit) {
    const resolved = path.resolve(explicit);
    if (!fs.existsSync(resolved)) {
      throw new Error(`SNORKEL_RUBRIC_FILE not found: ${resolved}`);
    }
    return resolved;
  }

  const taskName = resolveTaskNameFromEnv(zipPath);
  if (!taskName) return undefined;

  const candidate = path.join(REPO_ROOT, 'tasks', taskName, 'rubrics.txt');
  if (fs.existsSync(candidate)) return candidate;
  return undefined;
}

function agentRubricEditor(page: Page): Locator {
  const heading = page.getByText('Agent-generated rubric(s):', { exact: false }).first();
  const scoped = heading
    .locator('xpath=ancestor::*[.//*[@role="textbox" and @aria-label="Editor content"]][1]')
    .getByRole('textbox', { name: 'Editor content' })
    .first();

  return scoped;
}

/** Paste local rubrics.txt into the Agent-generated rubric Monaco field. */
export async function fillAgentRubric(page: Page, rubricPath: string): Promise<void> {
  const text = fs.readFileSync(rubricPath, 'utf8').replace(/\r\n/g, '\n').trimEnd() + '\n';
  if (!text.trim()) {
    throw new Error(`Rubric file is empty: ${rubricPath}`);
  }

  await page.getByText('Generate your Rubric(s)', { exact: false }).first().scrollIntoViewIfNeeded();

  let editor = agentRubricEditor(page);
  if ((await editor.count()) === 0) {
    editor = page.getByRole('textbox', { name: 'Editor content' }).last();
  }

  await expect(editor).toBeVisible({ timeout: 30_000 });
  await editor.scrollIntoViewIfNeeded();
  await editor.click();
  await editor.fill(text);

  const marker = text.split('\n').find((line) => line.trim().length > 0) ?? '';
  if (marker.length > 0) {
    await expect(page.getByText(marker.slice(0, Math.min(marker.length, 48)), { exact: false }).first())
      .toBeVisible({ timeout: 30_000 });
  }
}
