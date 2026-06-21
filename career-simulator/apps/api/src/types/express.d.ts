import type { UserPublic } from '@career-sim/shared';

declare global {
  namespace Express {
    interface Request {
      user?: UserPublic;
    }
  }
}

export {};
