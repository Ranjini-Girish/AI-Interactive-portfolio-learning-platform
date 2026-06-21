import fs from 'fs';
import path from 'path';
import { getPool } from './pool';

export async function runMigrations(): Promise<void> {
  const pool = getPool();
  if (!pool) {
    console.warn('[db] DATABASE_URL not set — skipping migrations (auth will be unavailable)');
    return;
  }

  const migrationsDir = path.join(__dirname, 'migrations');
  if (!fs.existsSync(migrationsDir)) return;

  const files = fs
    .readdirSync(migrationsDir)
    .filter((f) => f.endsWith('.sql'))
    .sort();

  for (const file of files) {
    const sql = fs.readFileSync(path.join(migrationsDir, file), 'utf8');
    await pool.query(sql);
    console.log(`[db] Applied migration: ${file}`);
  }
}
