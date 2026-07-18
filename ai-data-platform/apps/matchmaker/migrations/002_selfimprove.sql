-- 002_selfimprove.sql — self-improvement corroboration ledger + version registry.
--
-- The durable backing for the self-evolving loop (apps/matchmaker/selfimprove/). It
-- normalizes the {value, source_url, confidence} convention that entities.profile already
-- documents into a real multi-source ledger: one datum, many independent source origins.
--
-- NOT YET WIRED into the supervisor saga — P1/P2 are proven offline first
-- (tests/test_selfimprove_gate.py, tests/test_selfimprove_loop.py). These tables land the
-- schema so the live pi/feynman proposer and the Postgres gate can drop in behind the
-- same Proposer seam without a schema change. Apply after 001_domain.sql.

-- one asserted value for a field of an entity (the unit "correctness" is computed over)
CREATE TABLE IF NOT EXISTS datum (
  id           BIGSERIAL PRIMARY KEY,
  entity_id    TEXT NOT NULL REFERENCES entities(id),
  field        TEXT NOT NULL,                    -- e.g. 'funding_stage'
  value        TEXT NOT NULL,
  confidence   REAL NOT NULL DEFAULT 0,          -- derived from independent-origin count
  status       TEXT NOT NULL DEFAULT 'proposed', -- proposed | corroborated | conflict | noise
  version_id   BIGINT,                           -- the version that produced this datum
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (entity_id, field, version_id)          -- latest value per field per version
);

-- provenance for a datum. origin_key is the NORMALIZED origin, not the raw url, so
-- mirrors of one source collapse — independence is counted on distinct origin_key.
CREATE TABLE IF NOT EXISTS source (
  id           BIGSERIAL PRIMARY KEY,
  datum_id     BIGINT NOT NULL REFERENCES datum(id) ON DELETE CASCADE,
  url          TEXT NOT NULL,
  origin_key   TEXT NOT NULL,                    -- registered domain / upstream of the url
  fetched_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (datum_id, origin_key)                  -- one row per independent origin per datum
);

-- the version registry: every candidate pipeline/prompt/criterion, its gate verdict, and
-- its lineage. status transitions are the event-sourced audit of self-versioning.
CREATE TABLE IF NOT EXISTS version (
  id             BIGSERIAL PRIMARY KEY,
  parent_id      BIGINT REFERENCES version(id),
  kind           TEXT NOT NULL,                  -- matcher | prompt | criterion
  artifact       JSONB NOT NULL DEFAULT '{}'::jsonb,
  score          REAL,                           -- benchmark score at gate time
  held_out_score REAL,                           -- held-out score at gate time (regression guard)
  status         TEXT NOT NULL DEFAULT 'candidate', -- candidate | promoted | rejected
  reason         TEXT,                           -- gate verdict reason
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE datum
  ADD CONSTRAINT datum_version_fk FOREIGN KEY (version_id) REFERENCES version(id);

-- deterministic replay results, one per (version, frozen slice) — the P2 curve source.
CREATE TABLE IF NOT EXISTS eval_run (
  id               BIGSERIAL PRIMARY KEY,
  version_id       BIGINT NOT NULL REFERENCES version(id),
  benchmark_slice  TEXT NOT NULL,                -- 'bench' | 'held_out'
  score            REAL NOT NULL,
  breakdown        JSONB,                        -- per-entity correctness/confidence
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
