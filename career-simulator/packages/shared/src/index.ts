/** Development phases — see README.md */
export const DEVELOPMENT_PHASES = [
  { id: 1, name: 'Project setup + folder structure', status: 'done' as const },
  { id: 2, name: 'Authentication system', status: 'done' as const },
  { id: 3, name: 'Resume parser + analyzer', status: 'done' as const },
  { id: 4, name: 'Job description matching engine', status: 'done' as const },
  { id: 5, name: 'AI Mentor chat system', status: 'done' as const },
  { id: 6, name: 'Project simulation engine', status: 'done' as const },
  { id: 7, name: 'Dashboard + progress tracking', status: 'done' as const },
  { id: 8, name: 'Portfolio generator', status: 'done' as const },
  { id: 9, name: 'Mock interview system', status: 'done' as const },
  { id: 10, name: 'Deployment (Vercel + Fly.io)', status: 'done' as const },
];

export type { SimRole } from './roles';
export { SIM_ROLES } from './roles';

export type HealthResponse = {
  ok: boolean;
  service: string;
  phase: number;
  timestamp: string;
  database?: 'connected' | 'disconnected' | 'skipped';
  auth?: 'ready' | 'needs_database';
  mentor?: 'ready' | 'needs_openai_key' | 'needs_database';
  simulation?: 'ready' | 'needs_database';
  portfolio?: 'ready' | 'needs_database';
  interview?: 'ready' | 'needs_database';
  deploy?: 'production_ready' | 'needs_database';
};

export type ApiError = {
  error: string;
  code?: string;
};

export * from './auth';
export * from './resume';
export * from './job';
export * from './mentor';
export * from './simulation';
export * from './progress';
export * from './portfolio';
export * from './interview';
