-- 005_platform_appid.sql — platform multi-app tenancy (spec §B, Phase 1)
-- Scopes the platform-owned tables (jobs/events/saga_instances/artifacts) by app_id and
-- adds the `apps` registry, so one supervisor can host arbitrary apps. The matchmaker is
-- app #1: existing rows backfill to 'matchmaker'.
--
-- INVARIANT (why this migration touches no Python): today's spine/store.py is app-unaware.
-- Its inserts omit app_id (filled by the DEFAULT below) and its ON CONFLICT arbiters name
-- the NARROW tuples — (saga_id, stage, target_id) / (saga_id, seq) / (saga_id, step,
-- target_id) / (saga_id). Postgres infers an ON CONFLICT arbiter only from an index whose
-- columns match the specification EXACTLY, so a 4-column (app_id, ...) index cannot serve a
-- 3-column ON CONFLICT. The pre-existing narrow UNIQUEs (from 001/002) are therefore left in
-- place as those arbiters; the app-scoped WIDE unique indexes are ADDED alongside them. While
-- there is a single app the narrow key equals the app-scoped key (app_id is constant), so the
-- wide index is the forward bridge: the later phase that makes store.py app-aware rewrites the
-- ON CONFLICT clauses to (app_id, ...) and drops the narrow arbiters, at which point the wide
-- index takes over. This ordering keeps the North Star harness green with store.py untouched.

-- app registry
CREATE TABLE IF NOT EXISTS apps (
  app_id        TEXT PRIMARY KEY,
  name          TEXT NOT NULL,
  manifest_sha  TEXT,                                 -- NULL until a manifest is registered (Phase 2+)
  registered_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO apps (app_id, name) VALUES ('matchmaker', 'matchmaker')
  ON CONFLICT (app_id) DO NOTHING;

-- app_id on the platform-owned tables. NOT NULL DEFAULT 'matchmaker' backfills every
-- existing row to 'matchmaker' and lets app-unaware inserts keep omitting the column.
ALTER TABLE jobs           ADD COLUMN IF NOT EXISTS app_id TEXT NOT NULL DEFAULT 'matchmaker';
ALTER TABLE events         ADD COLUMN IF NOT EXISTS app_id TEXT NOT NULL DEFAULT 'matchmaker';
ALTER TABLE saga_instances ADD COLUMN IF NOT EXISTS app_id TEXT NOT NULL DEFAULT 'matchmaker';
ALTER TABLE artifacts      ADD COLUMN IF NOT EXISTS app_id TEXT NOT NULL DEFAULT 'matchmaker';

-- Widened, app-scoped idempotency keys (spec §B). Added alongside the retained narrow
-- UNIQUEs (see INVARIANT above); saga_instances keeps saga_id as its PK per spec §B.
CREATE UNIQUE INDEX IF NOT EXISTS jobs_app_saga_stage_target_key
  ON jobs (app_id, saga_id, stage, target_id);
CREATE UNIQUE INDEX IF NOT EXISTS events_app_saga_seq_key
  ON events (app_id, saga_id, seq);
CREATE UNIQUE INDEX IF NOT EXISTS artifacts_app_saga_step_target_key
  ON artifacts (app_id, saga_id, step, target_id);
