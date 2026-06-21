import type { MentorMessage } from '@career-sim/shared';
import { getPool } from '../db/pool';

type DbRow = {
  id: string;
  role: string;
  content: string;
  created_at: Date;
};

function toMessage(row: DbRow): MentorMessage {
  return {
    id: row.id,
    role: row.role as MentorMessage['role'],
    content: row.content,
    createdAt: row.created_at.toISOString(),
  };
}

export async function getMentorHistory(userId: string, limit = 40): Promise<MentorMessage[]> {
  const pool = getPool();
  if (!pool) return [];

  const { rows } = await pool.query<DbRow>(
    `SELECT id, role, content, created_at FROM mentor_messages
     WHERE user_id = $1 ORDER BY created_at ASC LIMIT $2`,
    [userId, limit],
  );
  return rows.map(toMessage);
}

export async function appendMentorMessage(
  userId: string,
  role: MentorMessage['role'],
  content: string,
): Promise<void> {
  const pool = getPool();
  if (!pool) return;

  await pool.query(
    `INSERT INTO mentor_messages (user_id, role, content) VALUES ($1, $2, $3)`,
    [userId, role, content],
  );
}

export async function clearMentorHistory(userId: string): Promise<void> {
  const pool = getPool();
  if (!pool) return;
  await pool.query(`DELETE FROM mentor_messages WHERE user_id = $1`, [userId]);
}
