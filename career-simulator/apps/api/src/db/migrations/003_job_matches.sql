-- Phase 4: job description match results
CREATE TABLE IF NOT EXISTS job_matches (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_analysis_id UUID REFERENCES resume_analyses(id) ON DELETE SET NULL,
  source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('paste', 'sample')),
  sample_id VARCHAR(64),
  job_title VARCHAR(255),
  raw_jd TEXT NOT NULL,
  analysis JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_matches_user_id ON job_matches (user_id, created_at DESC);
