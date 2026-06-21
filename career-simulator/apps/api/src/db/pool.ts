import { Pool } from 'pg';
import { env } from '../config/env';

let pool: Pool | null = null;

export function getPool(): Pool | null {
  if (!env.DATABASE_URL) return null;
  if (!pool) {
    pool = new Pool({ connectionString: env.DATABASE_URL });
  }
  return pool;
}

export async function checkDatabase(): Promise<'connected' | 'disconnected' | 'skipped'> {
  const db = getPool();
  if (!db) return 'skipped';
  try {
    await db.query('SELECT 1');
    return 'connected';
  } catch {
    return 'disconnected';
  }
}
