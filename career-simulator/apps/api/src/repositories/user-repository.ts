import bcrypt from 'bcryptjs';
import { getPool } from '../db/pool';
import type { DbUser, UserRow } from '../types/user';

const SALT_ROUNDS = 12;

export async function findUserByEmail(email: string): Promise<DbUser | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<DbUser>(
    `SELECT id, email, password_hash, full_name, clerk_id, created_at, updated_at
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

export async function verifyPassword(password: string, hash: string | null): Promise<boolean> {
  if (!hash) return false;
  return bcrypt.compare(password, hash);
}

export async function findUserByClerkId(clerkId: string): Promise<UserRow | null> {
  const pool = getPool();
  if (!pool) return null;

  const { rows } = await pool.query<UserRow>(
    `SELECT id, email, full_name, created_at
     FROM users WHERE clerk_id = $1 LIMIT 1`,
    [clerkId],
  );
  return rows[0] ?? null;
}

export async function linkClerkId(userId: string, clerkId: string): Promise<UserRow> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const { rows } = await pool.query<UserRow>(
    `UPDATE users SET clerk_id = $2, updated_at = NOW()
     WHERE id = $1
     RETURNING id, email, full_name, created_at`,
    [userId, clerkId],
  );

  const user = rows[0];
  if (!user) throw new Error('Failed to link Clerk account');
  return user;
}

export async function createClerkUser(
  email: string,
  fullName: string,
  clerkId: string,
): Promise<UserRow> {
  const pool = getPool();
  if (!pool) throw new Error('DATABASE_URL not configured');

  const { rows } = await pool.query<UserRow>(
    `INSERT INTO users (email, password_hash, full_name, clerk_id)
     VALUES (LOWER($1), NULL, $2, $3)
     RETURNING id, email, full_name, created_at`,
    [email.trim(), fullName.trim(), clerkId],
  );

  const user = rows[0];
  if (!user) throw new Error('Failed to create Clerk user');
  return user;
}
