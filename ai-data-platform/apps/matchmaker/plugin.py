"""Matchmaker plugin — the app's code-stage bodies, agent-stage handlers, named
ports, and store factory (spec §C/§F, Seam 1/2).

The platform imports this module at boot (``plugin: apps.matchmaker.plugin`` in
``app.yaml``); its module-level decorators register everything the generic
supervisor resolves by name. Handlers do the app-domain writes (entities / edges /
matches / the artifact blackboard) and return a declarative :class:`Advance` /
:class:`Reject` — the platform's DAG engine performs the queue-advance transaction
and reads the next stage from the manifest. So ``match``'s per-partner fan-out and
``verify``'s reject→retry are ordinary return values, not special cases.

Phase 5 inlines the deal-flow prompt/schema/domain bodies (formerly ``spine.sagas``
/ ``spine.outreach``) directly here, and the ranking port lives in
``apps.matchmaker.matcher``. The platform core (``spindle/``) holds no deal-flow
string either way.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from apps.matchmaker import cleanup
from apps.matchmaker.matcher import rule_filter
from apps.matchmaker.matcher.llm_judge import (
    LlmJudgeMatcher,
    _candidate_view,
    _startup_view,
    build_rank_prompt,
)
from apps.matchmaker.store import MatchmakerStore
from spine import config
from spine.ids import slugify
from spindle import registry
from spindle.app.context import Advance, AgentStageHandler, Reject, StageCtx

# ---------------------------------------------------------------- R3 schemas

_SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
_SCHEMAS = {
    "enrich": json.loads((_SCHEMA_DIR / "enrich.json").read_text()),
    "extract": json.loads((_SCHEMA_DIR / "extract.json").read_text()),
    "rank": json.loads((_SCHEMA_DIR / "rank.json").read_text()),
    "draft": json.loads((_SCHEMA_DIR / "draft.json").read_text()),
    "verify": json.loads((_SCHEMA_DIR / "verify.json").read_text()),
}

_ALLOWED_KINDS = ["raised_from", "invested_in", "pilot_with",
                  "founded_by_alumni_of", "partner_with"]

_REMINDER = ("\n\nIMPORTANT: your previous reply was not valid. Respond with ONLY a "
             "single fenced ```json block and nothing else — no prose, no explanation.")


def _validate(schema_key: str, data) -> bool:
    """R3 schema gate: the agent's terminal ```json block must match schemas/*.json."""
    schema = _SCHEMAS.get(schema_key)
    if schema is None or not isinstance(data, dict):
        return False
    try:
        jsonschema.validate(data, schema)
        return True
    except jsonschema.ValidationError:
        return False


class _Replay:
    """A pre-run RPC result — lets the ``match`` handler reuse the Matcher port's
    parse/map logic over data the supervisor already fetched (no second worker)."""

    __slots__ = ("success", "data")

    def __init__(self, data):
        self.success = True
        self.data = data


# ---------------------------------------------------------------- prompts

async def _enrich_prompt(ctx: StageCtx) -> str:
    ent = await ctx.store.get_entity(ctx.target_id)
    seed = ent["profile"] if ent else {}
    kinds = ", ".join(_ALLOWED_KINDS)
    return f"""You are enriching an entity for Vietnam's National Innovation Center (NIC) \
deal-flow database.

ENTITY
- type: {ent['type'] if ent else 'startup'}
- name: {ent['name'] if ent else ctx.target_id}
- country hint: {seed.get('country')}
- sector hints: {seed.get('sectors')}
- website hint: {seed.get('hint_website')}

Use your web_search and fetch_content tools to gather REAL public data from multiple \
sources (official site, Crunchbase/Dealroom, press, LinkedIn, startup.gov.vn / VnExpress \
for Vietnamese entities).

HARD RULES
- Every populated field MUST carry a real `source_url` you actually visited.
- A field you cannot find: set value null, "confidence":"unavailable", "source_url":null. \
Never invent data.
- For individuals never collect PII (DOB, ID/passport, tax id, personal phone/address).
- Surface relationships in a top-level "relationships" array. Each item: \
{{"kind": one of [{kinds}], "dst_name":"<org or person name>", "source_url":"<url>"}} \
where THIS entity is the subject (e.g. a startup "raised_from" a fund, or is \
"founded_by_alumni_of" a university).

OUTPUT (R3 contract)
Reply with ONLY a single fenced ```json block. Top-level keys: "entity_type", the \
provenance-tracked profile sections (each field as \
{{"value":..., "source_url":..., "confidence":...}}), "relationships", and \
"collection_summary". No prose before or after the JSON block."""


async def _extract_prompt(ctx: StageCtx) -> str:
    enrichment = await ctx.store.get_artifact(ctx.saga_id, "enrich", ctx.target_id) or {}
    ent = await ctx.store.get_entity(ctx.target_id)
    blob = json.dumps(enrichment, ensure_ascii=False)[:8000]
    return f"""You are normalizing an enriched profile into structured matching fields \
for a deal-flow matcher. Entity type: {ent['type'] if ent else 'startup'}.

ENRICHED DATA (JSON):
{blob}

Produce ONLY a single fenced ```json block with exactly these keys:
- "sectors": array of CANONICAL English sector tags. Normalize aggressively:
    enterprise_ai / ai_agents / automation → "ai"; clean_energy → "cleantech";
    "nông nghiệp" / agritech / foodtech-agri → "agritech"; healthcare / biotech / \
healthtech → "healthtech"; supply_chain / logistics → "supply_chain";
    keep fintech, robotics, semiconductor, iot, deep_tech as-is. Lowercase, underscored.
- "looking_for": array from ["funding","corporate_pilot","rd_collaboration","talent",\
"market_access","strategic_partnership"]. If unknown for a startup, use ["funding"].
- "stage": funding stage string (e.g. "seed","series_a") or null.
- "description_en": 1-2 sentence English summary, or null.
- "description_vi": 1-2 sentence Vietnamese summary, or null.

Derive ONLY from the enriched data above — do not invent facts. No prose outside the JSON."""


def _startup_block(startup: dict) -> dict:
    prof = startup.get("profile") or {}
    norm = prof.get("normalized") or {}
    return {
        "name": startup.get("name"),
        "sectors": norm.get("sectors"),
        "stage": norm.get("stage"),
        "looking_for": norm.get("looking_for") or ["funding"],
        "description_en": norm.get("description_en"),
        "description_vi": norm.get("description_vi"),
    }


def _partner_block(partner: dict) -> dict:
    prof = partner.get("profile") or {}
    norm = prof.get("normalized") or {}
    seed = prof.get("seed") or {}
    return {
        "name": partner.get("name"),
        "type": partner.get("type"),
        "sectors": norm.get("sectors") or seed.get("innovation_areas")
                   or seed.get("research_domains") or seed.get("sectors"),
        "description_en": norm.get("description_en") or seed.get("note"),
        "country": seed.get("country"),
    }


def _draft_prompt(startup: dict, partner: dict, match: dict, *,
                  verify_feedback: dict | None = None, retry: bool = False) -> str:
    partner_country = (partner.get("profile") or {}).get("seed", {}).get("country") or ""
    vn = "vietnam" in str(partner_country).lower()
    lead_lang = "Vietnamese" if vn else "English"
    fb = ""
    if verify_feedback:
        issues = verify_feedback.get("issues") or []
        fb = ("\n\nYOUR PREVIOUS DRAFT WAS REJECTED by the verifier. Fix these issues and "
              "regenerate BOTH languages:\n- " + "\n- ".join(str(i) for i in issues))
    reminder = ("\n\nIMPORTANT: reply with ONLY a single fenced ```json block."
                if retry else "")
    return f"""You are an outreach coordinator at Vietnam's National Innovation Center (NIC).

Write a personalized introduction email connecting this STARTUP with this PARTNER, in
BOTH Vietnamese and English. The partner is {partner_country or 'unknown'}-based, so the
primary language is {lead_lang} (still provide both).

STARTUP
{json.dumps(_startup_block(startup), ensure_ascii=False, indent=2)}

PARTNER
{json.dumps(_partner_block(partner), ensure_ascii=False, indent=2)}

WHY THIS MATCH (analyst rationale)
- EN: {match.get('rationale_en')}
- VI: {match.get('rationale_vi')}

REQUIREMENTS
- Tone: professional, warm, specific to this match. Under 150 words each.
- Explain why NIC is making the introduction and why the fit makes sense.
- Close with a clear next step. Use a NON-TIME call to action such as "NIC will
  coordinate a convenient time for a call" — do NOT propose or invent any specific
  date, time, or meeting slot (R15).
- Do NOT invent facts, metrics, funding figures, or past interactions beyond the data
  above. No personal (PII) details about individuals.{fb}

OUTPUT (R3 contract): reply with ONLY a single fenced ```json block:
{{"subject_en": "...", "subject_vi": "...", "draft_en": "...", "draft_vi": "..."}}
No prose before or after.{reminder}"""


def _verify_prompt(startup: dict, partner: dict, match: dict, *, retry: bool = False) -> str:
    reminder = ("\n\nIMPORTANT: reply with ONLY a single fenced ```json block."
                if retry else "")
    return f"""You are a strict compliance reviewer at Vietnam's National Innovation Center
(NIC). Judge the outreach DRAFTS below (LLM-as-judge). Approve ONLY if every check passes.

SOURCE OF TRUTH (the only facts the draft may rely on)
STARTUP: {json.dumps(_startup_block(startup), ensure_ascii=False)}
PARTNER: {json.dumps(_partner_block(partner), ensure_ascii=False)}
RATIONALE_EN: {match.get('rationale_en')}

DRAFTS TO REVIEW
--- English ---
{match.get('draft_en')}
--- Vietnamese ---
{match.get('draft_vi')}

CHECKS (all must pass):
1. facts_grounded — every claim about the startup/partner traces to the source above;
   no invented metrics, funding amounts, customers, or history.
2. no_pii — no personal data about individuals (DOB, ID, personal phone/address).
3. language_ok — the English draft is in English and the Vietnamese draft is in natural
   Vietnamese; both convey the same intent.
4. no_invented_times — no specific meeting date/time/slot is proposed (a non-time CTA
   like "NIC will coordinate a time" is REQUIRED and acceptable) (R15).

OUTPUT (R3 contract): reply with ONLY a single fenced ```json block:
{{"pass": true, "checks": {{"facts_grounded": true, "no_pii": true,
  "language_ok": true, "no_invented_times": true}}, "issues": []}}
Set "pass" false and list concrete, actionable "issues" if ANY check fails. No prose.{reminder}"""


# ---------------------------------------------------------------- code stages

# collection_summary verdicts that mean "we could not confirm this entity exists".
_DEAD_VERDICTS = {"not_found", "not found", "no_data", "unverifiable", "failed"}


def _count_populated(node) -> int:
    """Recursively count provenance fields ({value,...}) with a non-null value.
    Handles the enricher's varied nesting (top-level, profile.profile, contact, …)."""
    if isinstance(node, dict):
        if "value" in node and "confidence" in node:
            v = node.get("value")
            return 0 if v is None or v == [] or v == "" else 1
        return sum(_count_populated(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_populated(v) for v in node)
    return 0


def _enrichment_failed(enrichment: dict) -> bool:
    """True when enrichment yielded no real data — a dead/nonexistent seed.
    Gates such entities out of matching (which only pulls status='ready')."""
    summary = enrichment.get("collection_summary") or {}
    verdict = str(summary.get("status") or summary.get("verdict") or "").strip().lower()
    if verdict in _DEAD_VERDICTS:
        return True
    # No provenance field anywhere carries a value, and no relationships surfaced.
    data_only = {k: v for k, v in enrichment.items()
                 if k not in ("collection_summary", "seed", "normalized", "entity_type")}
    return _count_populated(data_only) == 0 and not (enrichment.get("relationships") or [])


@registry.stage("link")
async def link(ctx: StageCtx) -> Advance:
    """Merge enrich + extract artifacts → upsert the entity and write relationship
    edges. Idempotent (R9). Terminal onboarding stage. Entities whose enrichment
    found no verifiable data are marked status='unverified' so matching skips them."""
    ent = await ctx.store.get_entity(ctx.target_id)
    enrichment = await ctx.store.get_artifact(ctx.saga_id, "enrich", ctx.target_id) or {}
    extraction = await ctx.store.get_artifact(ctx.saga_id, "extract", ctx.target_id) or {}

    profile = dict(enrichment)
    profile["seed"] = ent["profile"] if ent else {}
    profile["normalized"] = extraction
    status = "unverified" if _enrichment_failed(enrichment) else "ready"
    await ctx.store.upsert_entity(ctx.target_id, ent["type"], ent["name"],
                                  profile=profile, status=status)

    for rel in enrichment.get("relationships") or []:
        dst_name, kind = rel.get("dst_name"), rel.get("kind")
        if not dst_name or not kind:
            continue
        await ctx.store.upsert_edge(
            ctx.target_id, f"name:{slugify(dst_name)}", kind,
            dst_name=dst_name, dst_resolved=False,
            source_url=rel.get("source_url"), payload=rel,
        )
    return Advance(event_kind="EntityReady",
                   event_payload={"entity_id": ctx.target_id}, next_targets=[])


@registry.stage("filter")
async def filter_partners(ctx: StageCtx) -> Advance:
    """Permissive rule-filter (R2) over ready partners → candidate handful, then
    advance to the agent-backed ``match`` stage (or end if nothing passes)."""
    startup = await ctx.store.get_entity(ctx.target_id)
    norm = (startup["profile"].get("normalized") or {}) if startup else {}
    startup_view = {
        "sectors": norm.get("sectors"),
        "looking_for": norm.get("looking_for") or ["funding"],
        "stage": norm.get("stage"),
    }
    partners = await ctx.store.list_ready_partners()
    candidates = rule_filter(startup_view, partners)
    candidates.sort(key=lambda c: (c["low_confidence_filter"], not c["purpose_match"]))
    candidates = candidates[: config.MATCH_MAX_CANDIDATES]

    await ctx.store.record_artifact(
        ctx.saga_id, "filter",
        {"candidates": candidates,
         "stats": {"partners": len(partners), "passed": len(candidates)}},
        entity_id=ctx.target_id, target_id=ctx.target_id, trace_id=ctx.trace_id,
    )
    return Advance(
        event_kind="FilterCompleted",
        event_payload={"startup_id": ctx.target_id, "candidates": len(candidates)},
        next_targets=[ctx.target_id] if candidates else [],
    )


@registry.stage("purge")
async def purge(ctx: StageCtx) -> Advance:
    """Cleanup code stage: delete verdicted-delete ids (prefix rail enforced here).
    The janitor can spare entities, never widen the blast radius."""
    prefix = ctx.target_id
    art = await ctx.store.get_artifact(ctx.saga_id, "audit", prefix) or {}
    verdicts = art.get("verdicts") or []
    delete_ids = [v["id"] for v in verdicts
                  if v.get("action") == "delete"
                  and isinstance(v.get("id"), str) and v["id"].startswith(prefix)]
    kept = [v["id"] for v in verdicts if v.get("action") == "keep"]
    counts = await ctx.store.delete_entities(delete_ids) if delete_ids else {}
    return Advance(
        event_kind="CleanupCompleted",
        event_payload={"prefix": prefix, "deleted": delete_ids, "kept": kept,
                       "rows_deleted": counts},
        next_targets=[],
    )


# ---------------------------------------------------------------- agent stages

@registry.agent_stage("enrich")
class EnrichStage(AgentStageHandler):
    """feynman web research → provenance-rich profile + relationships."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        prompt = await _enrich_prompt(ctx)
        return prompt + (_REMINDER if ctx.attempts > 1 else "")

    def validate(self, data) -> bool:
        return _validate("enrich", data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance:
        await ctx.store.record_artifact(ctx.saga_id, "enrich", data,
                                        entity_id=ctx.target_id, target_id=ctx.target_id,
                                        trace_id=ctx.trace_id)
        return Advance(event_kind="Enriched", event_payload={"target_id": ctx.target_id})


@registry.agent_stage("extract")
class ExtractStage(AgentStageHandler):
    """feynman normalize → canonical sectors (R2) + inferred looking_for."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        prompt = await _extract_prompt(ctx)
        return prompt + (_REMINDER if ctx.attempts > 1 else "")

    def validate(self, data) -> bool:
        return _validate("extract", data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance:
        await ctx.store.record_artifact(ctx.saga_id, "extract", data,
                                        entity_id=ctx.target_id, target_id=ctx.target_id,
                                        trace_id=ctx.trace_id)
        return Advance(event_kind="Extracted", event_payload={"target_id": ctx.target_id})


@registry.agent_stage("match")
class MatchStage(AgentStageHandler):
    """Agent-backed rank+explain via the ``matcher`` port (R12). Persist ranked
    matches, then fan out one ``draft`` job per top-k partner (Seam 2)."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        self._startup = await ctx.store.get_entity(ctx.target_id)
        art = await ctx.store.get_artifact(ctx.saga_id, "filter", ctx.target_id) or {}
        cand_ids = [c["partner_id"] for c in art.get("candidates", [])]
        cands = [await ctx.store.get_entity(pid) for pid in cand_ids]
        self._candidates = [c for c in cands if c is not None]
        return build_rank_prompt(
            _startup_view(self._startup),
            [_candidate_view(c) for c in self._candidates],
            top_k=config.MATCH_TOP_K, retry=ctx.attempts > 1,
        )

    def validate(self, data) -> bool:
        return _validate("rank", data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance:
        async def _runner(_prompt):
            return _Replay(data)

        matcher = ctx.port("matcher")(_runner, top_k=config.MATCH_TOP_K)
        scored = await matcher.rank(self._startup, self._candidates,
                                    {"retry": ctx.attempts > 1})
        top = scored[: config.MATCH_TOP_K]
        if not top:
            raise ValueError("match produced no ranked candidates")  # retryable
        for m in top:
            await ctx.store.upsert_match(
                startup_id=ctx.target_id, partner_id=m.partner_id,
                composite=m.composite, semantic=m.semantic,
                sector_overlap=m.sector_overlap, rationale_en=m.rationale_en,
                rationale_vi=m.rationale_vi, trace_id=ctx.trace_id, status="ranked",
            )
        return Advance(
            event_kind="MatchesRanked",
            event_payload={"startup_id": ctx.target_id,
                           "partners": [m.partner_id for m in top]},
            next_targets=[m.partner_id for m in top],
        )


@registry.agent_stage("draft")
class DraftStage(AgentStageHandler):
    """Per-match bilingual draft (pi). Carries verify feedback on retry (R5)."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        startup = await ctx.store.get_entity(ctx.subject_id)
        partner = await ctx.store.get_entity(ctx.target_id)
        match = await ctx.store.get_match(ctx.subject_id, ctx.target_id) or {}
        return _draft_prompt(startup, partner, match,
                             verify_feedback=ctx.retry_feedback,
                             retry=ctx.attempts > 1)

    def validate(self, data) -> bool:
        return _validate("draft", data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance:
        await ctx.store.set_match_draft(ctx.subject_id, ctx.target_id,
                                        data["draft_en"], data["draft_vi"])
        return Advance(event_kind="DraftReady",
                       event_payload={"partner_id": ctx.target_id})


@registry.agent_stage("verify")
class VerifyStage(AgentStageHandler):
    """Per-match verify (pi LLM-judge). pass → draft_ready + terminal; fail →
    Reject, which the DAG engine routes through the ``on_reject`` edge."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        startup = await ctx.store.get_entity(ctx.subject_id)
        partner = await ctx.store.get_entity(ctx.target_id)
        match = await ctx.store.get_match(ctx.subject_id, ctx.target_id) or {}
        return _verify_prompt(startup, partner, match, retry=ctx.attempts > 1)

    def validate(self, data) -> bool:
        return _validate("verify", data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance | Reject:
        if data.get("pass"):
            await ctx.store.set_match_status(ctx.subject_id, ctx.target_id, "draft_ready")
            return Advance(event_kind="Verified",
                           event_payload={"partner_id": ctx.target_id}, next_targets=[])
        return Reject(feedback={"partner_id": ctx.target_id,
                                "issues": data.get("issues") or [],
                                "checks": data.get("checks")})


@registry.agent_stage("audit")
class AuditStage(AgentStageHandler):
    """Cleanup audit (pi janitor): per-candidate evidence → delete/keep verdicts
    (R3, schemas/cleanup.json), then advance to the ``purge`` code stage."""

    async def build_prompt(self, ctx: StageCtx) -> str:
        cands = await cleanup.candidates(ctx.store, ctx.target_id)
        return cleanup.build_prompt(ctx.target_id, cands, retry=ctx.attempts > 1)

    def validate(self, data) -> bool:
        return cleanup.validate(data)

    async def persist_and_advance(self, ctx: StageCtx, data) -> Advance:
        await ctx.store.record_artifact(ctx.saga_id, "audit", data,
                                        target_id=ctx.target_id, trace_id=ctx.trace_id)
        deletes = sum(1 for v in data.get("verdicts", []) if v.get("action") == "delete")
        return Advance(
            event_kind="CleanupAudited",
            event_payload={"prefix": ctx.target_id,
                           "candidates": len(data.get("verdicts", [])),
                           "delete_verdicts": deletes},
        )


# ---------------------------------------------------------------- ports + store

# The Matcher is simply the first named port (spec §C): swap LlmJudgeMatcher for
# EmbeddingMatcher/GraphRagMatcher here with no saga change.
registry.port("matcher")(LlmJudgeMatcher)

# The app's data-access facade — the generic entrypoint builds it from the pool
# without naming the app (spec §A boundary).
registry.app_store(MatchmakerStore)
