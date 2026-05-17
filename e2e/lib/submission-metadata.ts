import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const METADATA_FILENAME = 'platform-submission.json';

function repoRoot(): string {
  return process.env.SNORKEL_E2E_REPO_ROOT ?? path.resolve(__dirname, '..', '..');
}

export type SubmissionFlowKind = 'new' | 'revision';

export type SubmissionRecord = {
  recordedAt: string;
  flow: SubmissionFlowKind;
  dryRun: boolean;
  submitted: boolean;
  submissionUrl: string;
  projectId: string | null;
  submissionSlug: string | null;
  assignmentId: string | null;
  revisionTaskId: string | null;
  zipPath: string;
  zipBytes: number | null;
  zipSha256: string | null;
  options: {
    sendToReviewer: boolean;
    regenerateRubric: boolean;
    staticChecks: boolean;
  };
};

export type TaskPlatformMetadata = {
  taskName: string;
  updatedAt: string;
  latest: SubmissionRecord;
  submissions: SubmissionRecord[];
};

export type SaveSubmissionMetadataInput = {
  taskName: string;
  flow: SubmissionFlowKind;
  dryRun: boolean;
  submitted: boolean;
  submissionUrl: string;
  zipPath: string;
  revisionTaskId?: string | null;
  options: SubmissionRecord['options'];
};

export function parseSubmissionUrl(submissionUrl: string): {
  projectId: string | null;
  submissionSlug: string | null;
  assignmentId: string | null;
} {
  let url: URL;
  try {
    url = new URL(submissionUrl);
  } catch {
    return { projectId: null, submissionSlug: null, assignmentId: null };
  }

  const projectMatch = url.pathname.match(/\/projects\/([^/]+)\//);
  const submissionMatch = url.pathname.match(/\/submission-([^/]+)\//);
  const assignmentId = url.searchParams.get('assignmentId');

  return {
    projectId: projectMatch?.[1] ?? null,
    submissionSlug: submissionMatch?.[1] ?? null,
    assignmentId,
  };
}

export function resolveTaskNameFromEnv(zipPath?: string): string | undefined {
  const fromDir = process.env.SNORKEL_TASK_DIR;
  if (fromDir) {
    const base = path.basename(path.resolve(repoRoot(), fromDir));
    if (base) return base;
  }

  const fromZip = zipPath ?? process.env.SNORKEL_TASK_ZIP;
  if (fromZip) {
    const base = path.basename(fromZip, '.zip');
    if (base) return base;
  }

  return undefined;
}

function zipFingerprint(zipPath: string): { zipBytes: number | null; zipSha256: string | null } {
  try {
    const buf = fs.readFileSync(zipPath);
    return {
      zipBytes: buf.length,
      zipSha256: createHash('sha256').update(buf).digest('hex'),
    };
  } catch {
    return { zipBytes: null, zipSha256: null };
  }
}

export function metadataPathForTask(taskName: string): string {
  return path.join(repoRoot(), 'tasks', taskName, METADATA_FILENAME);
}

/** Default on for live submit; dry run only when SNORKEL_SAVE_METADATA=1. */
export function shouldSaveSubmissionMetadata(submitted: boolean): boolean {
  if (process.env.SNORKEL_SAVE_METADATA === '0') return false;
  if (submitted) return true;
  return process.env.SNORKEL_SAVE_METADATA === '1';
}

export function buildSubmissionRecord(input: SaveSubmissionMetadataInput): SubmissionRecord {
  const parsed = parseSubmissionUrl(input.submissionUrl);
  const { zipBytes, zipSha256 } = zipFingerprint(input.zipPath);

  return {
    recordedAt: new Date().toISOString(),
    flow: input.flow,
    dryRun: input.dryRun,
    submitted: input.submitted,
    submissionUrl: input.submissionUrl,
    projectId: parsed.projectId,
    submissionSlug: parsed.submissionSlug,
    assignmentId: parsed.assignmentId,
    revisionTaskId: input.revisionTaskId ?? parsed.assignmentId ?? null,
    zipPath: input.zipPath,
    zipBytes,
    zipSha256,
    options: input.options,
  };
}

export function saveSubmissionMetadata(input: SaveSubmissionMetadataInput): string {
  const taskName = input.taskName || resolveTaskNameFromEnv(input.zipPath);
  if (!taskName) {
    throw new Error(
      'Cannot save submission metadata: set SNORKEL_TASK_DIR or SNORKEL_TASK_ZIP, or pass taskName.',
    );
  }

  const record = buildSubmissionRecord({ ...input, taskName });
  const outPath = metadataPathForTask(taskName);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });

  let existing: TaskPlatformMetadata | undefined;
  if (fs.existsSync(outPath)) {
    try {
      existing = JSON.parse(fs.readFileSync(outPath, 'utf8')) as TaskPlatformMetadata;
    } catch {
      existing = undefined;
    }
  }

  const submissions = [...(existing?.submissions ?? []), record];
  const doc: TaskPlatformMetadata = {
    taskName,
    updatedAt: record.recordedAt,
    latest: record,
    submissions,
  };

  fs.writeFileSync(outPath, `${JSON.stringify(doc, null, 2)}\n`, 'utf8');
  return outPath;
}
