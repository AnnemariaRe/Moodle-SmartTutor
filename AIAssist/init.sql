-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- IVFFlat index for fast approximate nearest-neighbour search
-- Created after table exists (handled by SQLAlchemy create_all on startup)
-- Run manually if needed:
-- CREATE INDEX IF NOT EXISTS course_chunks_embedding_idx
--   ON course_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
