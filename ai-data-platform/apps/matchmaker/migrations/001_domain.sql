-- 001_domain.sql — matchmaker app-domain tables (spec §5.1, §F, Seam 3).
-- The app owns entities / relationship graph / matches; the platform (jobs/events/
-- sagas/artifacts) is oblivious to them. Applied after the platform migrations, so
-- matches' FK -> entities resolves within this file. Slug ids (R9), trace_id (R10),
-- dst_name/dst_resolved (R11). pgvector NOT required for v1 (LlmJudgeMatcher).

-- unified startups + partners
CREATE TABLE IF NOT EXISTS entities (
  id          TEXT PRIMARY KEY,                 -- R9: deterministic slug {type}:{slug(name)}
  type        TEXT NOT NULL,                    -- startup | investor | corporation | university | research_institution
  name        TEXT NOT NULL,
  profile     JSONB NOT NULL DEFAULT '{}'::jsonb, -- provenance-tracked fields ({value, source_url, confidence})
  status      TEXT NOT NULL DEFAULT 'seeded',   -- seeded | enriching | ready
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- relationships graph (captured from enrichment output from day 1; v1 matcher ignores it,
-- GraphRagMatcher + connection-viz consume it later)
CREATE TABLE IF NOT EXISTS edges (
  id            BIGSERIAL PRIMARY KEY,
  src_id        TEXT NOT NULL,                  -- entity id
  dst_id        TEXT NOT NULL,                  -- resolved entity id (may equal a slug not yet onboarded)
  dst_name      TEXT,                           -- R11: raw target name before resolution
  dst_resolved  BOOLEAN NOT NULL DEFAULT FALSE, -- R11: true once dst_name maps to an onboarded entity id
  kind          TEXT NOT NULL,                  -- invested_in | founded_by_alumni_of | pilot_with | co_invested | same_sector
  source_url    TEXT,                           -- provenance (same discipline as profiles)
  payload       JSONB,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (src_id, dst_id, kind)
);

-- domain results
CREATE TABLE IF NOT EXISTS matches (
  id             BIGSERIAL PRIMARY KEY,
  startup_id     TEXT REFERENCES entities(id),
  partner_id     TEXT REFERENCES entities(id),
  composite      REAL,
  semantic       REAL,
  sector_overlap REAL,
  rationale_en   TEXT,
  rationale_vi   TEXT,
  draft_en       TEXT,
  draft_vi       TEXT,
  trace_id       TEXT,                          -- R10
  status         TEXT NOT NULL DEFAULT 'ranked', -- ranked | draft_ready
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (startup_id, partner_id)
);
