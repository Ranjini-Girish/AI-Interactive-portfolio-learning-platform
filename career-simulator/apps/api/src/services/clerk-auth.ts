import { createClerkClient, verifyToken } from '@clerk/backend';
import type { UserPublic } from '@career-sim/shared';
import { env } from '../config/env';
import { findUserByClerkId, findUserByEmail, linkClerkId, createClerkUser } from '../repositories/user-repository';
import { toUserPublic } from '../utils/user-mapper';

export function isClerkConfigured(): boolean {
  return Boolean(env.CLERK_SECRET_KEY);
}

let clerkClient: ReturnType<typeof createClerkClient> | null = null;

function getClerkClient() {
  if (!env.CLERK_SECRET_KEY) {
    throw new Error('CLERK_SECRET_KEY not configured');
  }
  if (!clerkClient) {
    clerkClient = createClerkClient({ secretKey: env.CLERK_SECRET_KEY });
  }
  return clerkClient;
}

export async function resolveUserFromClerkToken(token: string): Promise<UserPublic | null> {
  if (!isClerkConfigured()) return null;

  const payload = await verifyToken(token, {
    secretKey: env.CLERK_SECRET_KEY!,
  });

  const clerkId = payload.sub;
  if (!clerkId) return null;

  const existing = await findUserByClerkId(clerkId);
  if (existing) return toUserPublic(existing);

  const clerkUser = await getClerkClient().users.getUser(clerkId);
  const email = clerkUser.emailAddresses.find((e) => e.id === clerkUser.primaryEmailAddressId)
    ?.emailAddress
    ?? clerkUser.emailAddresses[0]?.emailAddress;

  if (!email) {
    throw new Error('Clerk user has no email address');
  }

  const fullName =
    [clerkUser.firstName, clerkUser.lastName].filter(Boolean).join(' ').trim() ||
    email.split('@')[0] ||
    'Learner';

  const byEmail = await findUserByEmail(email);
  if (byEmail) {
    const linked = await linkClerkId(byEmail.id, clerkId);
    return toUserPublic(linked);
  }

  const created = await createClerkUser(email, fullName, clerkId);
  return toUserPublic(created);
}
