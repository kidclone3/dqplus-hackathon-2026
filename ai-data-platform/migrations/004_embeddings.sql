-- 004_embeddings.sql — pgvector embedding column + HNSW index on entities
-- Lands the embedding column deferred from 001_core.sql (EmbeddingMatcher); mirrors the
-- extract agent's hnsw (embedding vector_cosine_ops) index. vector(1024) = the native
-- width of the FPT-hosted embedders (multilingual-e5-large / Vietnamese_Embedding), which
-- spine/embedding.py also targets for its keyless feature-hash fallback.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE entities ADD COLUMN IF NOT EXISTS embedding vector(1024);

CREATE INDEX IF NOT EXISTS idx_entities_embedding
  ON entities USING hnsw (embedding vector_cosine_ops);
