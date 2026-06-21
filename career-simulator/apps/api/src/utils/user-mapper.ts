import type { UserPublic } from '@career-sim/shared';
import type { UserRow } from '../types/user';

export function toUserPublic(row: UserRow): UserPublic {
  return {
    id: row.id,
    email: row.email,
    fullName: row.full_name,
    createdAt: row.created_at.toISOString(),
  };
}
