-- Clerk authentication: link Clerk users to local profile rows
ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;

ALTER TABLE users ADD COLUMN IF NOT EXISTS clerk_id VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_clerk_id ON users (clerk_id)
  WHERE clerk_id IS NOT NULL;
