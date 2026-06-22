import { z } from 'zod';
import dotenv from 'dotenv';
import path from 'path';

dotenv.config({ path: path.resolve(__dirname, '../../../.env') });
dotenv.config({ path: path.resolve(__dirname, '../.env') });

const envSchema = z.object({
  PORT: z.coerce.number().default(4000),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  DATABASE_URL: z.string().optional(),
  JWT_SECRET: z.string().default('dev-secret-change-in-production'),
  JWT_EXPIRES_IN: z.string().default('7d'),
  OPENAI_API_KEY: z.string().optional(),
  OPENAI_MODEL: z.string().default('gpt-4o-mini'),
  CORS_ORIGIN: z.string().default('http://localhost:3000'),
  /** Set on Render/Railway so health checks report public URL */
  PUBLIC_API_URL: z.string().optional(),
  /** Clerk — when set, API accepts Clerk session tokens (see CLERK-SETUP.md) */
  CLERK_SECRET_KEY: z.string().optional(),
});

export const env = envSchema.parse(process.env);
