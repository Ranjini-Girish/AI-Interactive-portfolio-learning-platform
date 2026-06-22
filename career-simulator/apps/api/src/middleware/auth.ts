import type { NextFunction, Request, Response } from 'express';
import { verifyToken } from '../services/jwt-service';
import { getUserById } from '../services/auth-service';
import { isClerkConfigured, resolveUserFromClerkToken } from '../services/clerk-auth';

export async function requireAuth(req: Request, res: Response, next: NextFunction): Promise<void> {
  const header = req.headers.authorization;
  if (!header?.startsWith('Bearer ')) {
    res.status(401).json({ error: 'Authentication required', code: 'UNAUTHORIZED' });
    return;
  }

  const token = header.slice(7);

  if (isClerkConfigured()) {
    try {
      const user = await resolveUserFromClerkToken(token);
      if (user) {
        req.user = user;
        next();
        return;
      }
    } catch {
      res.status(401).json({ error: 'Invalid or expired Clerk session', code: 'INVALID_TOKEN' });
      return;
    }
  }

  try {
    const payload = verifyToken(token);
    const user = await getUserById(payload.sub);
    if (!user) {
      res.status(401).json({ error: 'User not found', code: 'UNAUTHORIZED' });
      return;
    }
    req.user = user;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid or expired token', code: 'INVALID_TOKEN' });
  }
}
