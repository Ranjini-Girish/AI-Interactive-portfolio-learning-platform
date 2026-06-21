import type { AuthResponse, LoginRequest, RegisterRequest, UserPublic } from '@career-sim/shared';
import {
  createUser,
  findUserByEmail,
  findUserById,
  verifyPassword,
} from '../repositories/user-repository';
import { signToken } from '../services/jwt-service';
import { toUserPublic } from '../utils/user-mapper';

export class AuthError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code: string,
  ) {
    super(message);
  }
}

function assertDatabase(): void {
  // createUser throws if no pool; this gives a clearer message at route level
}

export async function registerUser(input: RegisterRequest): Promise<AuthResponse> {
  assertDatabase();

  const existing = await findUserByEmail(input.email);
  if (existing) {
    throw new AuthError('An account with this email already exists', 409, 'EMAIL_TAKEN');
  }

  const user = await createUser(input.email, input.password, input.fullName);
  const publicUser = toUserPublic(user);
  const token = signToken(user.id, user.email);

  return { token, user: publicUser };
}

export async function loginUser(input: LoginRequest): Promise<AuthResponse> {
  const user = await findUserByEmail(input.email);
  if (!user) {
    throw new AuthError('Invalid email or password', 401, 'INVALID_CREDENTIALS');
  }

  const valid = await verifyPassword(input.password, user.password_hash);
  if (!valid) {
    throw new AuthError('Invalid email or password', 401, 'INVALID_CREDENTIALS');
  }

  const publicUser = toUserPublic({
    id: user.id,
    email: user.email,
    full_name: user.full_name,
    created_at: user.created_at,
  });

  return { token: signToken(user.id, user.email), user: publicUser };
}

export async function getUserById(userId: string): Promise<UserPublic | null> {
  const user = await findUserById(userId);
  return user ? toUserPublic(user) : null;
}
