"""FastAPI read API + dashboard (spec §8, §13, Phase 3).

Read-only projections over Postgres for the dashboard, plus POST /runs to trigger
an outreach run. Endpoints (spec §8): /entities /matches /sagas /jobs /events
/workers /metrics /costs + POST /runs. The supervisor (python -m spine.supervisor
--drain) drains any jobs this enqueues; the API itself never touches agents.

Run: uv run uvicorn api.app:app --port 8000
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from apps.matchmaker.graph import build_graph, path_to_dict
from apps.matchmaker.matcher import embedding_matcher
from apps.matchmaker.store import MatchmakerStore as Store
from spine import telemetry

log = telemetry.get_logger("api")
_DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "index.html"

# Partner entity types (spec §5.1). Everything else is a startup.
PARTNER_TYPES = ["investor", "corporation", "university", "research_institution"]

# User profiles live in the separate backend DB; the platform fetches them from the
# extract service over HTTP (GET /extracted/:userId) for the by-user /matches routes.
EXTRACT_SERVICE_URL = os.environ.get("EXTRACT_SERVICE_URL", "http://extract:3003").rstrip("/")
_QUERY_WORDS = re.compile(r"[a-z0-9][a-z0-9_-]{1,}", re.I)


@asynccontextmanager
async def lifespan(app: FastAPI):
    telemetry.configure()
    app.state.store = await Store.connect(min_size=1, max_size=5)
    log.info("api_started")
    try:
        yield
    finally:
        await app.state.store.close()


app = FastAPI(title="Deal-flow Matchmaker", lifespan=lifespan)

# Permissive CORS: read-only API, no cookie auth — wildcard origin is safe only with
# allow_credentials=False (browsers reject "*" + credentials).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


def _pool(app: FastAPI):
    return app.state.store.pool


def _jsonable(v: Any) -> Any:
    """Normalize asyncpg row values: Decimal -> float, jsonb text -> parsed."""
    if isinstance(v, Decimal):
        return float(v)
    return v


def _row(record) -> dict:
    return {k: _jsonable(v) for k, v in dict(record).items()}


def _parse_jsonb(d: dict, *fields: str) -> dict:
    for f in fields:
        if isinstance(d.get(f), str):
            try:
                d[f] = json.loads(d[f])
            except (json.JSONDecodeError, TypeError):
                pass
    return d


# --------------------------------------------------------------------------- #
# dashboard — admin-only when JWT_SECRET is set (gateway-issued HS256 tokens).
# Admins exist only via direct DB update (UPDATE users SET role='admin'); the
# gateway never registers them. Data endpoints below stay public — the frontend
# match flow reads /matches directly.
# --------------------------------------------------------------------------- #

_JWT_SECRET = os.environ.get("JWT_SECRET", "")
_ADMIN_COOKIE = "vn_admin"


def _b64url_decode(seg: str) -> bytes:
    return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))


def _verify_admin_jwt(token: str) -> bool:
    """Verify a gateway HS256 JWT and require role=admin. stdlib-only on purpose:
    this service otherwise has no JWT dependency."""
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        if json.loads(_b64url_decode(header_b64)).get("alg") != "HS256":
            return False
        expected = hmac.new(
            _JWT_SECRET.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return False
        payload = json.loads(_b64url_decode(payload_b64))
        if payload.get("exp") is not None and time.time() >= float(payload["exp"]):
            return False
        return payload.get("role") == "admin"
    except Exception:
        return False


@app.get("/", include_in_schema=False)
async def dashboard(request: Request):
    if not _DASHBOARD.exists():
        raise HTTPException(404, "dashboard not built")
    if _JWT_SECRET:
        token = request.query_params.get("token")
        if token:
            if not _verify_admin_jwt(token):
                raise HTTPException(403, "admin role required")
            resp = RedirectResponse("/", status_code=303)
            resp.set_cookie(_ADMIN_COOKIE, token, httponly=True, samesite="lax")
            return resp
        auth = request.headers.get("authorization", "")
        token = auth.split(" ", 1)[1] if auth.lower().startswith("bearer ") else None
        token = token or request.cookies.get(_ADMIN_COOKIE)
        if not token:
            raise HTTPException(401, "admin token required: open /?token=<admin jwt>")
        if not _verify_admin_jwt(token):
            raise HTTPException(403, "admin role required")
    return FileResponse(_DASHBOARD)


# --------------------------------------------------------------------------- #
# entities
# --------------------------------------------------------------------------- #

@app.get("/entities")
async def entities(type: str | None = Query(None), status: str | None = Query(None)):
    clauses, args = [], []
    if type:
        args.append(type)
        clauses.append(f"type = ${len(args)}")
    if status:
        args.append(status)
        clauses.append(f"status = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await _pool(app).fetch(
        "SELECT e.id, e.type, e.name, e.status, "
        "(SELECT count(*) FROM matches m WHERE m.startup_id = e.id OR m.partner_id = e.id) "
        "AS match_count "
        f"FROM entities e {where} ORDER BY e.type, e.name",
        *args,
    )
    return [_row(r) for r in rows]


@app.get("/entities/{entity_id}")
async def entity(entity_id: str):
    pool = _pool(app)
    row = await pool.fetchrow(
        "SELECT id, type, name, status, profile, created_at, updated_at "
        "FROM entities WHERE id = $1",
        entity_id,
    )
    if row is None:
        raise HTTPException(404, "entity not found")
    # Relationship graph (§5.1 edges): outgoing from this entity + incoming resolved ones,
    # with the counterpart's display name when it has been onboarded.
    edge_rows = await pool.fetch(
        "SELECT e.src_id, e.dst_id, e.dst_name, e.dst_resolved, e.kind, e.source_url, "
        "s.name AS src_name, d.name AS dst_entity_name "
        "FROM edges e LEFT JOIN entities s ON s.id = e.src_id "
        "LEFT JOIN entities d ON d.id = e.dst_id AND e.dst_resolved "
        "WHERE e.src_id = $1 OR (e.dst_id = $1 AND e.dst_resolved) "
        "ORDER BY e.kind",
        entity_id,
    )
    out = _parse_jsonb(_row(row), "profile")
    out["edges"] = [
        {**_row(r), "direction": "out" if r["src_id"] == entity_id else "in"}
        for r in edge_rows
    ]
    return out


@app.get("/entities/{entity_id}/graph-matches")
async def graph_matches(entity_id: str, max_hops: int = Query(2, ge=1, le=3),
                        types: str | None = Query(
                            None,
                            description="Comma-separated target types, e.g. "
                                        "'investor,corporation'. Default: all partner types.")):
    """Relationship-graph discovery (spec §5.1: edges "consumed by future GraphRAG").

    Unlike GET /entities/{id}'s `edges` list (which only shows edges whose dst_id was
    already resolved at write time — rare in practice), this re-resolves edge targets by
    name against the full current entity set and BFS-traverses up to `max_hops`. Answers
    "which investors/corporations is this startup N hops from via a real relationship"
    (shared funding rounds, partnerships, pilots) — a signal the LlmJudgeMatcher never
    sees, since it only looks at one startup + its filtered candidate list at a time.
    """
    pool = _pool(app)
    if await pool.fetchval("SELECT 1 FROM entities WHERE id = $1", entity_id) is None:
        raise HTTPException(404, "entity not found")

    entity_rows = await pool.fetch("SELECT id, type, name FROM entities")
    edge_rows = await pool.fetch("SELECT src_id, dst_id, dst_name, kind, source_url FROM edges")

    graph = build_graph([dict(r) for r in entity_rows], [dict(r) for r in edge_rows])
    target_types = set(t.strip() for t in types.split(",") if t.strip()) if types else None
    paths = graph.find_paths(entity_id, max_hops=max_hops, target_types=target_types)
    return {"entity_id": entity_id, "max_hops": max_hops, "matches": [path_to_dict(p) for p in paths]}


# --------------------------------------------------------------------------- #
# matches
# --------------------------------------------------------------------------- #

@app.get("/matches")
async def matches(startup_id: str | None = Query(None),
                  partner_id: str | None = Query(None),
                  status: str | None = Query(None)):
    """Ranked matches, composite-desc. Filter by startup_id for a startup's ranked partners,
    or by partner_id for the reverse view (startups that matched to a partner) — A4."""
    clauses, args = [], []
    if startup_id:
        args.append(startup_id)
        clauses.append(f"m.startup_id = ${len(args)}")
    if partner_id:
        args.append(partner_id)
        clauses.append(f"m.partner_id = ${len(args)}")
    if status:
        args.append(status)
        clauses.append(f"m.status = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await _pool(app).fetch(
        "SELECT m.id, m.startup_id, s.name AS startup_name, "
        "m.partner_id, p.name AS partner_name, p.type AS partner_type, "
        "m.composite, m.semantic, m.sector_overlap, m.rationale_en, m.rationale_vi, "
        "m.draft_en, m.draft_vi, m.status, m.created_at "
        "FROM matches m LEFT JOIN entities p ON p.id = m.partner_id "
        "LEFT JOIN entities s ON s.id = m.startup_id "
        f"{where} ORDER BY m.startup_id, m.composite DESC NULLS LAST",
        *args,
    )
    return [_row(r) for r in rows]


def _profile_text(profile: Any) -> str:
    """Turn a sparse JSON profile into searchable text without assuming a schema."""
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except json.JSONDecodeError:
            return profile
    return json.dumps(profile or {}, ensure_ascii=False).lower()


def _terms(value: Any) -> set[str]:
    return set(_QUERY_WORDS.findall(_profile_text(value).lower()))


@app.get("/discover")
async def discover_investors(startup_id: str = Query(...), query: str = Query(""),
                             limit: int = Query(12, ge=1, le=30)):
    """Searchable investor discovery for the dashboard's matchmaking workspace.

    This is intentionally a transparent, fast shortlist rather than a replacement for
    the LLM ranking job: it combines profile overlap, location, natural-language query
    terms, and any already-ranked match. The user can immediately explore candidates,
    then use the normal outreach pipeline to create ranked/drafted matches.
    """
    pool = _pool(app)
    startup = await pool.fetchrow(
        "SELECT id, name, profile FROM entities WHERE id = $1 AND type = 'startup'", startup_id)
    if startup is None:
        raise HTTPException(404, "startup not found")

    candidates = await pool.fetch(
        "SELECT e.id, e.name, e.type, e.status, e.profile, m.composite, m.semantic, "
        "m.sector_overlap, m.rationale_en, m.status AS match_status "
        "FROM entities e LEFT JOIN matches m ON m.partner_id = e.id AND m.startup_id = $1 "
        "WHERE e.type = 'investor' ORDER BY e.name", startup_id)
    startup_profile = _profile_text(startup["profile"])
    startup_terms = _terms(startup_profile)
    query_terms = _terms(query)
    startup_country = ""
    try:
        startup_country = str((json.loads(startup["profile"]) if isinstance(startup["profile"], str)
                               else startup["profile"] or {}).get("country", "")).lower()
    except (json.JSONDecodeError, AttributeError):
        pass

    from apps.matchmaker.matcher.semantic import calculate_fit_score

    results = []
    for row in candidates:
        d = _parse_jsonb(_row(row), "profile")
        candidate_text = f"{d['name']} {_profile_text(d.get('profile'))}".lower()
        candidate_terms = _terms(candidate_text)
        query_hits = query_terms & candidate_terms

        # Semantic reciprocal fit score (spine.matcher.semantic). calculate_fit_score
        # is fully synchronous and may make blocking urllib LLM/embedding calls, so run
        # it off the event loop to avoid stalling the server.
        fit_result = await asyncio.to_thread(calculate_fit_score, startup_profile, candidate_text)
        score = fit_result["composite_score"]

        profile = d.get("profile") or {}
        signals = [str(profile[k]) for k in ("country", "note", "sectors", "focus", "stage") if profile.get(k)]
        results.append({
            "id": d["id"], "name": d["name"], "type": d["type"], "status": d["status"],
            "score": min(100, score), "query_hits": sorted(query_hits),
            "profile_hits": [], "signals": signals[:3],
            "existing_match": d.get("composite") is not None,
            "rationale": d.get("rationale_en"), "match_status": d.get("match_status"),
        })
    results.sort(key=lambda x: (-x["score"], x["name"]))
    return {"startup_id": startup["id"], "startup_name": startup["name"], "query": query,
            "results": results[:limit]}


@app.get("/matches_v2")
async def matches_v2(startup_id: str | None = Query(None),
                     partner_id: str | None = Query(None),
                     status: str | None = Query(None)):
    """Dry-run matches from the FPT-hosted re-rank (matches_v2). Same shape as /matches
    plus a `model` column; no draft columns. Filter by startup_id or partner_id."""
    clauses, args = [], []
    if startup_id:
        args.append(startup_id)
        clauses.append(f"m.startup_id = ${len(args)}")
    if partner_id:
        args.append(partner_id)
        clauses.append(f"m.partner_id = ${len(args)}")
    if status:
        args.append(status)
        clauses.append(f"m.status = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await _pool(app).fetch(
        "SELECT m.id, m.startup_id, s.name AS startup_name, "
        "m.partner_id, p.name AS partner_name, p.type AS partner_type, "
        "m.composite, m.semantic, m.sector_overlap, m.rationale_en, m.rationale_vi, "
        "m.model, m.status, m.created_at "
        "FROM matches_v2 m LEFT JOIN entities p ON p.id = m.partner_id "
        "LEFT JOIN entities s ON s.id = m.startup_id "
        f"{where} ORDER BY m.startup_id, m.composite DESC NULLS LAST",
        *args,
    )
    return [_row(r) for r in rows]


# --------------------------------------------------------------------------- #
# RAG match — pgvector match over the requester's normalized profile (POST body)
# --------------------------------------------------------------------------- #

def _target_types(default: list[str], types: str | None) -> list[str]:
    """Override the default target types with a comma list, else keep the default."""
    if types:
        parsed = [t.strip() for t in types.split(",") if t.strip()]
        if parsed:
            return parsed
    return default


async def _rag_match(user_id: str, role: str, query_profile: dict, default_types: list[str],
                     types: str | None, limit: int, rerank: bool,
                     sector: str | None, stage: str | None, region: str | None) -> dict:
    if not isinstance(query_profile, dict):
        raise HTTPException(400, "request body must be the requester's normalized profile (JSON object)")
    filters = {k: v for k, v in (("sector", sector), ("stage", stage), ("region", region)) if v}
    result = await embedding_matcher.match(
        _pool(app),
        query_profile=query_profile,
        target_types=_target_types(default_types, types),
        limit=limit,
        filters=filters,
        rerank=rerank,
    )
    return {"userId": user_id, "role": role, "matches": result["matches"]}


@app.post("/matches/founders/{user_id}/investors")
async def match_founder_to_investors(user_id: str, body: dict,
                                     limit: int = Query(10, ge=1, le=50),
                                     rerank: bool = Query(False),
                                     types: str | None = Query(
                                         None,
                                         description="Comma-separated target types to override "
                                                     "the default. Default: 'investor'; may broaden "
                                                     "to corporation,university,research_institution."),
                                     sector: str | None = Query(None),
                                     stage: str | None = Query(None),
                                     region: str | None = Query(None)):
    """RAG match a founder to partners. The requester's normalized profile is the JSON body;
    it is embedded and KNN-searched against the partner corpus, then attribute-rescored."""
    return await _rag_match(user_id, "founder", body, ["investor"], types, limit, rerank,
                            sector, stage, region)


@app.post("/matches/investors/{user_id}/founders")
async def match_investor_to_founders(user_id: str, body: dict,
                                     limit: int = Query(10, ge=1, le=50),
                                     rerank: bool = Query(False),
                                     types: str | None = Query(
                                         None,
                                         description="Comma-separated target types to override "
                                                     "the default. Default: 'startup'."),
                                     sector: str | None = Query(None),
                                     stage: str | None = Query(None),
                                     region: str | None = Query(None)):
    """RAG match an investor to startups. The requester's normalized profile is the JSON body;
    it is embedded and KNN-searched against the startup corpus, then attribute-rescored."""
    return await _rag_match(user_id, "investor", body, ["startup"], types, limit, rerank,
                            sector, stage, region)


# --- GET-by-user variants: the public interface the frontend calls (no body). ------- #
# nginx routes /api/matches/... here (replacing the old matching-engine); the requester's
# profile is self-fetched from extracted_profiles by gateway user id (shared DB).

def _norm_from_attrs(attrs: dict) -> dict:
    """Map an extract-agent attribute set (extracted_profiles.attributes) onto the
    `normalized` keys the matcher's attribute_score reads (founder uses `industry`)."""
    attrs = attrs or {}
    return {
        "sectors": attrs.get("sectors") or attrs.get("industry"),
        "stage": attrs.get("stage"),
        "stages": attrs.get("stages"),
        "target_regions": attrs.get("target_regions"),
        "geographies": attrs.get("geographies"),
        "funding_ask_usd": attrs.get("funding_ask_usd"),
        "check_size_usd": attrs.get("check_size_usd"),
        "looking_for": attrs.get("looking_for"),
        "description_en": attrs.get("product_description") or attrs.get("thesis"),
    }


def _fetch_extracted(user_id: str) -> dict | None:
    """GET the user's extracted profile from the extract service. None on 404."""
    import urllib.error
    import urllib.request

    req = urllib.request.Request(f"{EXTRACT_SERVICE_URL}/extracted/{user_id}",
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise HTTPException(502, f"extract service error: {exc.code}")
    except urllib.error.URLError as exc:
        raise HTTPException(502, f"extract service unreachable: {exc.reason}")


async def _rag_match_by_user(user_id: str, default_types: list[str], types: str | None,
                             limit: int, rerank: bool) -> dict:
    # Blocking urllib off the event loop; profiles come from the backend via extract.
    data = await asyncio.to_thread(_fetch_extracted, user_id)
    if data is None:
        # Same 404 as the old engine so the app's extract-then-retry flow still triggers.
        raise HTTPException(404, "No extracted profile for user; run extraction first")
    attrs = data.get("attributes") or {}
    if isinstance(attrs, str):
        attrs = json.loads(attrs or "{}")
    result = await embedding_matcher.match(
        _pool(app),
        query_text=data.get("embedding_text") or "",
        query_norm=_norm_from_attrs(attrs),
        target_types=_target_types(default_types, types),
        limit=limit,
        rerank=rerank,
    )
    return {"userId": user_id, "role": data.get("role"), "matches": result["matches"]}


@app.get("/matches/founders/{user_id}/investors")
async def matches_founder_to_partners(user_id: str,
                                      limit: int = Query(10, ge=1, le=50),
                                      rerank: bool = Query(False),
                                      types: str | None = Query(
                                          None,
                                          description="Comma-separated target types. Default: all "
                                                      "partner types (investor,corporation,"
                                                      "university,research_institution).")):
    return await _rag_match_by_user(user_id, PARTNER_TYPES, types, limit, rerank)


@app.get("/matches/investors/{user_id}/founders")
async def matches_investor_to_startups(user_id: str,
                                       limit: int = Query(10, ge=1, le=50),
                                       rerank: bool = Query(False),
                                       types: str | None = Query(
                                           None, description="Comma-separated target types. "
                                                             "Default: 'startup'.")):
    return await _rag_match_by_user(user_id, ["startup"], types, limit, rerank)


# --------------------------------------------------------------------------- #
# sagas / jobs / events
# --------------------------------------------------------------------------- #

@app.get("/sagas")
async def sagas(type: str | None = Query(None)):
    clauses, args = [], []
    if type:
        args.append(type)
        clauses.append(f"type = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await _pool(app).fetch(
        "SELECT saga_id, type, subject_id, current_step, status, trace_id, updated_at "
        f"FROM saga_instances {where} ORDER BY updated_at DESC",
        *args,
    )
    return [_row(r) for r in rows]


@app.get("/jobs")
async def jobs(status: str | None = Query(None), saga_id: str | None = Query(None)):
    clauses, args = [], []
    if status:
        args.append(status)
        clauses.append(f"status = ${len(args)}")
    if saga_id:
        args.append(saga_id)
        clauses.append(f"saga_id = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = await _pool(app).fetch(
        "SELECT id, saga_id, stage, target_id, agent, status, attempts, leased_by, "
        "lease_expires_at, queued_at, leased_at, done_at "
        f"FROM jobs {where} ORDER BY id DESC LIMIT 200",
        *args,
    )
    return [_row(r) for r in rows]


@app.get("/events")
async def events(saga_id: str | None = Query(None), limit: int = Query(50, le=500)):
    clauses, args = [], []
    if saga_id:
        args.append(saga_id)
        clauses.append(f"saga_id = ${len(args)}")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    args.append(limit)
    rows = await _pool(app).fetch(
        "SELECT id, saga_id, seq, kind, trace_id, payload, created_at "
        f"FROM events {where} ORDER BY id DESC LIMIT ${len(args)}",
        *args,
    )
    return [_parse_jsonb(_row(r), "payload") for r in rows]


@app.get("/workers")
async def workers():
    rows = await _pool(app).fetch(
        "SELECT worker_id, agent_type, runtime, pid, status, current_job_id, "
        "jobs_since_reset, restart_count, started_at, last_heartbeat_at "
        "FROM workers ORDER BY started_at DESC LIMIT 100"
    )
    return [_row(r) for r in rows]


# --------------------------------------------------------------------------- #
# observability: /metrics (pool + queue health) and /costs (llm_usage aggregates)
# --------------------------------------------------------------------------- #

@app.get("/metrics")
async def metrics():
    """§13.3 — pool health (workers by status) + queue health (jobs by stage/status)."""
    pool = _pool(app)
    worker_rows = await pool.fetch(
        "SELECT status, count(*) AS n FROM workers GROUP BY status"
    )
    job_rows = await pool.fetch(
        "SELECT stage, status, count(*) AS n FROM jobs GROUP BY stage, status "
        "ORDER BY stage, status"
    )
    saga_rows = await pool.fetch(
        "SELECT type, status, count(*) AS n FROM saga_instances GROUP BY type, status"
    )
    dead = await pool.fetchval("SELECT count(*) FROM jobs WHERE status = 'dead'")
    ready = await pool.fetchval("SELECT count(*) FROM jobs WHERE status = 'ready'")
    leased = await pool.fetchval("SELECT count(*) FROM jobs WHERE status = 'leased'")
    return {
        "workers": {r["status"]: r["n"] for r in worker_rows},
        "jobs_by_stage_status": [_row(r) for r in job_rows],
        "queue": {"ready": ready, "leased": leased, "dead_letter": dead},
        "sagas": [_row(r) for r in saga_rows],
    }


@app.get("/costs")
async def costs():
    """§13.2 — running LLM cost total + per-agent/saga/model breakdown, and the two
    headline demo numbers: cost-per-onboarded-entity and cost-per-match."""
    pool = _pool(app)
    totals = await pool.fetchrow(
        "SELECT COALESCE(SUM(cost_usd),0) AS cost_usd, COALESCE(SUM(tokens_in),0) AS tokens_in, "
        "COALESCE(SUM(tokens_out),0) AS tokens_out, count(*) AS turns FROM llm_usage"
    )
    by_agent = await pool.fetch(
        "SELECT agent, runtime, COALESCE(SUM(cost_usd),0) AS cost_usd, "
        "COALESCE(SUM(tokens_in),0) AS tokens_in, COALESCE(SUM(tokens_out),0) AS tokens_out, "
        "count(*) AS turns FROM llm_usage GROUP BY agent, runtime ORDER BY cost_usd DESC"
    )
    by_model = await pool.fetch(
        "SELECT model, COALESCE(SUM(cost_usd),0) AS cost_usd, count(*) AS turns "
        "FROM llm_usage GROUP BY model ORDER BY cost_usd DESC"
    )
    by_saga = await pool.fetch(
        "SELECT saga_id, COALESCE(SUM(cost_usd),0) AS cost_usd, count(*) AS turns "
        "FROM llm_usage GROUP BY saga_id ORDER BY cost_usd DESC LIMIT 50"
    )
    ready_entities = await pool.fetchval(
        "SELECT count(*) FROM entities WHERE status = 'ready'"
    )
    match_count = await pool.fetchval("SELECT count(*) FROM matches")
    total_cost = float(totals["cost_usd"])
    return {
        "total": {
            "cost_usd": total_cost,
            "tokens_in": totals["tokens_in"],
            "tokens_out": totals["tokens_out"],
            "turns": totals["turns"],
        },
        "cost_per_ready_entity": round(total_cost / ready_entities, 6) if ready_entities else None,
        "cost_per_match": round(total_cost / match_count, 6) if match_count else None,
        "by_agent": [_row(r) for r in by_agent],
        "by_model": [_row(r) for r in by_model],
        "by_saga": [_row(r) for r in by_saga],
    }


# --------------------------------------------------------------------------- #
# POST /runs — trigger an outreach run (R4)
# --------------------------------------------------------------------------- #

@app.post("/runs")
async def create_run(body: dict | None = None):
    """Trigger outreach for one startup (`startup_id`) or every ready startup (`all`).
    Enqueues jobs; the running supervisor (--drain) advances them. Returns the trace_id
    and the sagas started. Idempotent on saga/job keys — re-triggering is safe."""
    body = body or {}
    store: Store = app.state.store
    pool = store.pool
    trace_id = "run:" + uuid.uuid4().hex[:12]

    if body.get("all"):
        rows = await pool.fetch(
            "SELECT id FROM entities WHERE type = 'startup' AND status = 'ready' ORDER BY id"
        )
        ids = [r["id"] for r in rows]
    elif body.get("startup_id"):
        ids = [body["startup_id"]]
    else:
        raise HTTPException(400, "pass {\"startup_id\": <id>} or {\"all\": true}")

    if not ids:
        raise HTTPException(409, "no ready startups to run")

    sagas_started = []
    for sid in ids:
        saga_id = f"outreach:{sid}"
        await store.create_saga(saga_id, "outreach", sid,
                                current_step="filter", trace_id=trace_id)
        await store.enqueue_job(saga_id, "filter", target_id=sid, trace_id=trace_id)
        sagas_started.append(saga_id)
    log.info("run_triggered", trace_id=trace_id, count=len(sagas_started))
    return JSONResponse(
        status_code=202,
        content={"trace_id": trace_id, "sagas": sagas_started, "count": len(sagas_started)},
    )
