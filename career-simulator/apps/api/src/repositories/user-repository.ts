import bcrypt from 'bcryptjs';
import { getPool } from '../db/pool';
import type { DbUser, UserRow } from '../types/user';

const SALT_ROUNDS = 12;

export async function findUserByEmail(email: string): Promise<DbUser | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbUser>(
    `SELECT id, email, password_hash, full_name, created_at, updated_at
     FROM users WHERE LOWER(email) = LOWER($1) LIMIT 1`,
    [email.trim()],
  );
  return rows[0] ?? null;
}

export async function findUserById(id: string): Promise<UserRow | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<UserRow>(
    `SELECT id, email, full_name, created_at
     FROM users WHERE id = $1 LIMIT 1`,
    [id],
  );
  return rows[0] ?? null;
}

export async function createUser(
  email: string,
  password: string,
  fullName: string,
): Promise<UserRow> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const passwordHash = await bcrypt.hash(password, SALT_ROUNDS);
  const { rows } = await pool.query<UserRow>(
    `INSERT INTO users (email, password_hash, full_name)
     VALUES (LOWER($1), $2, $3)
     RETURNING id, email, full_name, created_at`,
    [email.trim(), passwordHash, fullName.trim()],
  );

  const user = rows[0];
  if (!user) throw new Error('Failed to create user');
  return user;
}

export async function verifyPassword(password: string, hash: string): Promise<boolean> {
  return bcrypt.compare(password, hash);
}
