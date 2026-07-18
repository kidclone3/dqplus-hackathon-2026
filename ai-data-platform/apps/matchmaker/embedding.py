"""Embedding for the pgvector RAG matcher (EmbeddingMatcher).

Mirrors the extract agent's embedding contract (backend/agent/extract/app/services/
embedding.py) so the query vector and the stored corpus vectors live in ONE space:
same env var names, same FPT-compatible `/embeddings` endpoint, same EMBEDDING_DIM.

With OPENAI_API_KEY set it calls the endpoint over stdlib urllib (no openai SDK — kept
dependency-free — wrapped in a thread so the event loop is never blocked). Keyless, it
falls back to a DETERMINISTIC feature-hash embedding built with hashlib (NOT the builtin
hash(), which is per-process salted): these vectors are persisted in Postgres and must
reproduce byte-for-byte across processes.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import urllib.request

# Reuse extract's env var names so the query vector and corpus vectors share one space.
# Pinned to 1024 to match the fixed `entities.embedding vector(1024)` column and its HNSW
# index (migrations/004_embeddings.sql) — a mismatched dim would break inserts and KNN.
# 1024 is the native width of the FPT-hosted embedders (multilingual-e5-large /
# Vietnamese_Embedding); the keyless feature-hash fallback also emits this width.
EMBEDDING_DIM = 1024
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL") or "https://mkp-api.fptcloud.com"
OPENAI_EMBEDDING_MODEL = os.environ.get("OPENAI_EMBEDDING_MODEL") or "multilingual-e5-large"

# The FPT gateway sits behind Cloudflare, which 403s (error 1010) the default
# Python-urllib User-Agent. A browser UA is required on every FPT request.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


def entity_text(entity: dict) -> str:
    """Build a searchable string from an entity (or a bare requester profile).

    Modeled on llm_judge._candidate_view: name + normalized sectors / stage /
    looking_for / description_en / thesis, with a seed fallback. Accepts a full entity
    ``{"name": ..., "profile": {"normalized": {...}, "seed": {...}}}``, a caller-supplied
    ``{"profile": {...}}`` wrapper whose profile is the normalized dict itself, or a bare
    normalized dict passed straight in.
    """
    entity = entity or {}
    prof = entity.get("profile")
    if isinstance(prof, dict):
        norm = prof.get("normalized") if isinstance(prof.get("normalized"), dict) else prof
        seed = prof.get("seed") or {}
    else:
        norm = entity
        seed = entity.get("seed") or {}
    norm = norm or {}

    name = entity.get("name") or norm.get("name") or ""
    sectors = list(norm.get("sectors") or []) or (
        seed.get("innovation_areas") or seed.get("research_domains") or seed.get("sectors") or []
    )
    looking_for = norm.get("looking_for") or []
    desc = norm.get("description_en") or norm.get("description_vi") or seed.get("note") or ""
    thesis = norm.get("thesis") or ""

    parts = [
        str(name),
        " ".join(str(s) for s in sectors),
        str(norm.get("stage") or ""),
        " ".join(str(x) for x in looking_for),
        str(desc),
        str(thesis),
    ]
    text = " ".join(p.strip() for p in parts if p and p.strip())
    return text or str(name)


async def embed_text(text: str) -> list[float]:
    """Return EXACTLY EMBEDDING_DIM floats for `text`.

    With a key, hits the FPT-compatible endpoint (blocking urllib in a thread); keyless,
    a deterministic feature-hash embedding so the match flow works offline.
    """
    if OPENAI_API_KEY:
        return await asyncio.to_thread(_embed_via_api, text)
    return _feature_hash(text)


def _embed_via_api(text: str) -> list[float]:
    # No "dimensions" param: the FPT embedders are fixed-width (1024) and reject it.
    payload = json.dumps({"model": OPENAI_EMBEDDING_MODEL, "input": text}).encode()
    req = urllib.request.Request(
        f"{OPENAI_BASE_URL}/embeddings",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "User-Agent": _UA,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    return _fit([float(x) for x in result["data"][0]["embedding"]])


# Keyless fallback: feature-hashed bag-of-words, L2-normalized — same layout as extract's
# local_embed (idx = (h >> 1) % dim, sign from h & 1), but the hash is hashlib.blake2b so
# it is stable across processes (builtin hash() is salted per interpreter run).
def _feature_hash(text: str) -> list[float]:
    vec = [0.0] * EMBEDDING_DIM
    for token in _TOKEN_RE.findall(str(text).lower()):
        h = int.from_bytes(hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest(), "big")
        idx = (h >> 1) % EMBEDDING_DIM
        vec[idx] += 1.0 if (h & 1) else -1.0
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _fit(vec: list[float]) -> list[float]:
    """Guarantee EXACTLY EMBEDDING_DIM floats (pad with zeros / truncate)."""
    if len(vec) == EMBEDDING_DIM:
        return vec
    if len(vec) > EMBEDDING_DIM:
        return vec[:EMBEDDING_DIM]
    return vec + [0.0] * (EMBEDDING_DIM - len(vec))
