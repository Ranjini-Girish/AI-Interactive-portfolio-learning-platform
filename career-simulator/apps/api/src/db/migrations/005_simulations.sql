-- Phase 6: job simulation sessions and task submissions
CREATE TABLE IF NOT EXISTS simulation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id VARCHAR(32) NOT NULL CHECK (role_id IN ('qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer')),
  status VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE (user_id, role_id)
);

CREATE TABLE IF NOT EXISTS simulation_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES simulation_sessions(id) ON DELETE CASCADE,
  task_id VARCHAR(64) NOT NULL,
  payload JSONB NOT NULL,
  score INTEGER NOT NULL DEFAULT 0,
  passed BOOLEAN NOT NULL DEFAULT FALSE,
  feedback JSONB NOT NULL DEFAULT '[]',
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_sim_sessions_user ON simulation_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_sim_submissions_session ON simulation_submissions (session_id);
