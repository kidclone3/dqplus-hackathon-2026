import logging
import re

from openai import AsyncOpenAI

from app import config

logger = logging.getLogger(__name__)

HAS_KEY = bool(config.OPENAI_API_KEY)

client = AsyncOpenAI(api_key=config.OPENAI_API_KEY or "not-set", base_url=config.OPENAI_BASE_URL)

if not HAS_KEY:
    logger.warning(
        "OPENAI_API_KEY not set — using local feature-hash embeddings (lexical similarity, not semantic)"
    )

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)


# Keyless fallback: feature-hashed bag-of-words, L2-normalized. Cosine distance
# between these vectors measures term overlap instead of semantic similarity,
# which keeps the matching pipeline functional without an API key.
def local_embed(text: str, dim: int = config.EMBEDDING_DIM) -> list[float]:
    vec = [0.0] * dim
    tokens = _TOKEN_RE.findall(str(text).lower())
    for token in tokens:
        h = 2166136261
        for char in token:
            h ^= ord(char)
            h &= 0xFFFFFFFF
            h = (h * 16777619) & 0xFFFFFFFF
        idx = (h >> 1) % dim
        vec[idx] += 1.0 if (h & 1) else -1.0
    norm = sum(x * x for x in vec) ** 0.5 or 1
    return [x / norm for x in vec]


async def embed(text: str) -> list[float]:
    if not HAS_KEY:
        return local_embed(text)
    res = await client.embeddings.create(
        model=config.OPENAI_EMBEDDING_MODEL,
        input=text,
        dimensions=config.EMBEDDING_DIM,
    )
    return res.data[0].embedding
