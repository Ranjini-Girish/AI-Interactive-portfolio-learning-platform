-- Phase 9: mock interview sessions and responses
CREATE TABLE IF NOT EXISTS interview_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_id VARCHAR(32) NOT NULL CHECK (role_id IN ('qa_tester', 'data_analyst', 'project_manager', 'ai_reviewer')),
  interview_type VARCHAR(16) NOT NULL CHECK (interview_type IN ('behavioral', 'technical', 'mixed')),
  status VARCHAR(20) NOT NULL DEFAULT 'in_progress' CHECK (status IN ('in_progress', 'completed')),
  overall_score INTEGER,
  questions_total INTEGER NOT NULL,
  question_ids JSONB NOT NULL,
  improvement_summary JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS interview_responses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  question_id VARCHAR(64) NOT NULL,
  question_type VARCHAR(16) NOT NULL,
  question_text TEXT NOT NULL,
  answer_text TEXT NOT NULL,
  score INTEGER NOT NULL,
  feedback JSONB NOT NULL,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (session_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_interview_sessions_user ON interview_sessions (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_interview_responses_session ON interview_responses (session_id);
