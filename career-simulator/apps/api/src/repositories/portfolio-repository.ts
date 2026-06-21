import type { PortfolioContent, PortfolioRecord } from '@career-sim/shared';
import { getPool } from '../db/pool';

type DbRow = {
  id: string;
  content: PortfolioContent;
  created_at: Date;
};

function toRecord(row: DbRow): PortfolioRecord {
  return {
    id: row.id,
    content: row.content,
    createdAt: row.created_at.toISOString(),
  };
}

export async function savePortfolio(
  userId: string,
  content: PortfolioContent,
): Promise<PortfolioRecord> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const { rows } = await pool.query<DbRow>(
    `INSERT INTO portfolio_generations (user_id, content)
     VALUES ($1, $2)
     RETURNING id, content, created_at`,
    [userId, JSON.stringify(content)],
  );

  const row = rows[0];
  if (!row) throw new Error('Failed to save portfolio');
  return toRecord(row);
}

export async function getLatestPortfolio(userId: string): Promise<PortfolioRecord | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbRow>(
    `SELECT id, content, created_at FROM portfolio_generations
     WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1`,
    [userId],
  );

  return rows[0] ? toRecord(rows[0]) : null;
}

export async function hasPortfolio(userId: string): Promise<boolean> {
  const pool = getPool();
  if (!pool) return false;

  const { rows } = await pool.query<{ exists: boolean }>(
    `SELECT EXISTS(SELECT 1 FROM portfolio_generations WHERE user_id = $1) AS exists`,
    [userId],
  );

  return rows[0]?.exists ?? false;
}
