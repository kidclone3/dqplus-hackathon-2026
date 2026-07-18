CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS extracted_profiles (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL UNIQUE,
  role           TEXT NOT NULL CHECK (role IN ('founder', 'investor')),
  source         TEXT NOT NULL CHECK (source IN ('text', 'crawler', 'profile')),
  source_url     TEXT,
  raw_input      TEXT,
  attributes     JSONB NOT NULL DEFAULT '{}'::jsonb,
  embedding_text TEXT NOT NULL,
  embedding      vector(1536) NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_extracted_profiles_role
  ON extracted_profiles (role);

CREATE INDEX IF NOT EXISTS idx_extracted_profiles_embedding
  ON extracted_profiles USING hnsw (embedding vector_cosine_ops);
