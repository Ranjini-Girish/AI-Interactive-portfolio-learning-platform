-- Phase 3: resume uploads and analyses
CREATE TABLE IF NOT EXISTS resume_analyses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('upload', 'paste', 'sample')),
  file_name VARCHAR(255),
  sample_id VARCHAR(64),
  raw_text TEXT NOT NULL,
  analysis JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_resume_analyses_user_id ON resume_analyses (user_id);
CREATE INDEX IF NOT EXISTS idx_resume_analyses_created ON resume_analyses (user_id, created_at DESC);
