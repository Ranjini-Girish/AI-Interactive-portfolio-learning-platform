import type { JobMatchAnalysis, JobMatchRecord } from '@career-sim/shared';
import { getPool } from '../db/pool';

type SaveInput = {
  userId: string;
  resumeAnalysisId: string | null;
  sourceType: 'paste' | 'sample';
  sampleId?: string;
  jobTitle: string;
  rawJd: string;
  analysis: JobMatchAnalysis;
};

type DbRow = {
  id: string;
  source_type: string;
  sample_id: string | null;
  resume_analysis_id: string | null;
  job_title: string | null;
  analysis: JobMatchAnalysis;
  created_at: Date;
};

function toRecord(row: DbRow): JobMatchRecord {
  return {
    id: row.id,
    sourceType: row.source_type as JobMatchRecord['sourceType'],
    sampleId: row.sample_id,
    resumeAnalysisId: row.resume_analysis_id,
    jobTitle: row.job_title ?? row.analysis.jobTitle,
    analysis: row.analysis,
    createdAt: row.created_at.toISOString(),
  };
}

export async function saveJobMatch(input: SaveInput): Promise<JobMatchRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const { rows } = await pool.query<DbRow>(
    `INSERT INTO job_matches (user_id, resume_analysis_id, source_type, sample_id, job_title, raw_jd, analysis)
     VALUES ($1, $2, $3, $4, $5, $6, $7)
     RETURNING id, source_type, sample_id, resume_analysis_id, job_title, analysis, created_at`,
    [
      input.userId,
      input.resumeAnalysisId,
      input.sourceType,
      input.sampleId ?? null,
      input.jobTitle,
      input.rawJd,
      JSON.stringify(input.analysis),
    ],
  );

  const row = rows[0];
  if (!row) throw new Error('Failed to save job match');
  return toRecord(row);
}

export async function getLatestJobMatch(userId: string): Promise<JobMatchRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbRow>(
    `SELECT id, source_type, sample_id, resume_analysis_id, job_title, analysis, created_at
     FROM job_matches WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1`,
    [userId],
  );

  return rows[0] ? toRecord(rows[0]) : null;
}

export async function getJobMatchById(userId: string, id: string): Promise<JobMatchRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbRow>(
    `SELECT id, source_type, sample_id, resume_analysis_id, job_title, analysis, created_at
     FROM job_matches WHERE user_id = $1 AND id = $2 LIMIT 1`,
    [userId, id],
  );

  return rows[0] ? toRecord(rows[0]) : null;
}
