import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const ZIP_TOOL = path.join(REPO_ROOT, 'tools', 'terminus-task-tools', 'terminus_zip.py');

/** Build a flat submission zip from a task folder using terminus_zip.py. */
export function buildTaskZip(taskDir: string): string {
  const resolved = path.isAbsolute(taskDir)
    ? taskDir
    : path.resolve(REPO_ROOT, taskDir);

  if (!fs.existsSync(resolved)) {
    throw new Error(`Task directory not found: ${resolved}`);
  }

  if (!fs.existsSync(ZIP_TOOL)) {
    throw new Error(`Zip tool not found: ${ZIP_TOOL}`);
  }

  const py = process.env.PYTHON ?? 'python';
  execSync(`"${py}" "${ZIP_TOOL}" clean "${resolved}"`, {
    stdio: 'inherit',
    cwd: REPO_ROOT,
  });
  execSync(`"${py}" "${ZIP_TOOL}" build "${resolved}"`, {
    stdio: 'inherit',
    cwd: REPO_ROOT,
  });

  const zipPath = path.join(path.dirname(resolved), `${path.basename(resolved)}.zip`);
  if (!fs.existsSync(zipPath)) {
    throw new Error(`Expected zip was not created: ${zipPath}`);
  }
  return zipPath;
}

/**
 * Resolve the task zip to upload.
 * - SNORKEL_TASK_ZIP — path to an existing .zip
 * - SNORKEL_TASK_DIR — task folder; builds ../tasks/<name>.zip first
 */
export function resolveTaskZipPath(required = false): string | undefined {
  const fromZip = process.env.SNORKEL_TASK_ZIP;
  if (fromZip) {
    const resolved = path.resolve(fromZip);
    if (!fs.existsSync(resolved)) {
      throw new Error(`SNORKEL_TASK_ZIP not found: ${resolved}`);
    }
    return resolved;
  }

  const fromDir = process.env.SNORKEL_TASK_DIR;
  if (fromDir) {
    return buildTaskZip(fromDir);
  }

  if (required) {
    throw new Error(
      'Set SNORKEL_TASK_ZIP (path to .zip) or SNORKEL_TASK_DIR (task folder name/path).',
    );
  }
  return undefined;
}

export function resolveTaskZipPathOrThrow(): string {
  return resolveTaskZipPath(true)!;
}
