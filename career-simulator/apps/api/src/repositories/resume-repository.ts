import type { ResumeAnalysis, ResumeAnalysisRecord } from '@career-sim/shared';
import { getPool } from '../db/pool';

type SaveInput = {
  userId: string;
  sourceType: 'upload' | 'paste' | 'sample';
  fileName?: string;
  sampleId?: string;
  rawText: string;
  analysis: ResumeAnalysis;
};

type DbRow = {
  id: string;
  source_type: string;
  file_name: string | null;
  sample_id: string | null;
  analysis: ResumeAnalysis;
  created_at: Date;
};

function toRecord(row: DbRow): ResumeAnalysisRecord {
  return {
    id: row.id,
    sourceType: row.source_type as ResumeAnalysisRecord['sourceType'],
    fileName: row.file_name,
    sampleId: row.sample_id,
    analysis: row.analysis,
    createdAt: row.created_at.toISOString(),
  };
}

export async function saveResumeAnalysis(input: SaveInput): Promise<ResumeAnalysisRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const { rows } = await pool.query<DbRow>(
    `INSERT INTO resume_analyses (user_id, source_type, file_name, sample_id, raw_text, analysis)
     VALUES ($1, $2, $3, $4, $5, $6)
     RETURNING id, source_type, file_name, sample_id, analysis, created_at`,
    [
      input.userId,
      input.sourceType,
      input.fileName ?? null,
      input.sampleId ?? null,
      input.rawText,
      JSON.stringify(input.analysis),
    ],
  );

  const row = rows[0];
  if (!row) throw new Error('Failed to save analysis');
  return toRecord(row);
}

export async function getLatestAnalysis(userId: string): Promise<ResumeAnalysisRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbRow>(
    `SELECT id, source_type, file_name, sample_id, analysis, created_at
     FROM resume_analyses
     WHERE user_id = $1
     ORDER BY created_at DESC
     LIMIT 1`,
    [userId],
  );

  return rows[0] ? toRecord(rows[0]) : null;
}

export async function getAnalysisById(
  userId: string,
  id: string,
): Promise<ResumeAnalysisRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbRow>(
    `SELECT id, source_type, file_name, sample_id, analysis, created_at
     FROM resume_analyses
     WHERE user_id = $1 AND id = $2
     LIMIT 1`,
    [userId, id],
  );

  return rows[0] ? toRecord(rows[0]) : null;
}
