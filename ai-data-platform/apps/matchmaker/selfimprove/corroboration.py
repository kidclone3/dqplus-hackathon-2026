"""Independence-weighted corroboration — the anti-echo-chamber core.

Correctness cannot be verified against a single source (it may be stale, biased, or a
mirror). It is verified by agreement across INDEPENDENT source origins. The one field
that makes this real is the *origin* of a source, not its URL: ten Crunchbase mirrors
share one origin and must count once. ``origin_key`` normalizes a URL to its registered
domain (its origin); ``independent_origins`` counts distinct origins; ``confidence`` maps
that count to [0, 1].

This is intentionally the same discipline ``entities.profile`` already documents
({value, source_url, confidence}) — promoted from one source_url to many origins.
"""
from __future__ import annotations

# Known aggregators/mirrors mapped to the upstream origin they republish, so syndication
# collapses instead of faking independence. Extend as real mirror chains are discovered.
_SYNDICATION: dict[str, str] = {
    "finance.yahoo.com": "reuters.com",
    "news.google.com": "google-syndication",
}

# Public suffixes needing three labels for the registered domain (gov.vn, com.vn, ...).
_TWO_LABEL_SUFFIXES = frozenset({"vn", "uk", "au", "jp", "br", "in", "sg"})
_SECOND_LEVELS = frozenset({"com", "co", "gov", "org", "net", "edu", "ac"})


def origin_key(source: str) -> str:
    """Normalize a source to its ORIGIN. Mirrors of the same origin collapse to one key.

    A URL -> its registered domain (``a.b.crunchbase.com/x`` -> ``crunchbase.com``), with
    known syndication chains folded to the upstream. A non-URL source (e.g. a filing id)
    is lowercased and returned as-is so it still keys distinctly.
    """
    s = (source or "").strip().lower()
    if not s:
        return ""
    if "://" in s:
        s = s.split("://", 1)[1]
    host = s.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.split("@")[-1].split(":", 1)[0]  # drop any userinfo / port
    if host.startswith("www."):
        host = host[4:]
    if "." not in host:
        return host  # not a hostname (filing id, doc ref) — key as-is
    labels = host.split(".")
    if len(labels) >= 3 and labels[-1] in _TWO_LABEL_SUFFIXES and labels[-2] in _SECOND_LEVELS:
        reg = ".".join(labels[-3:])
    else:
        reg = ".".join(labels[-2:])
    return _SYNDICATION.get(host, _SYNDICATION.get(reg, reg))


def independent_origins(sources) -> int:
    """Number of DISTINCT origins among the sources. Mirrors count once; empty -> 0."""
    return len({k for k in (origin_key(s) for s in (sources or [])) if k})


def confidence(indep: int, k: int = 3) -> float:
    """Map an independent-origin count to a [0, 1] confidence.

    n=1 -> 0.0 (single-sourced is untrusted), n=2 -> 0.5, n>=k -> 1.0. ``k`` is the
    number of independent origins required for full confidence.
    """
    if indep < 2 or k <= 1:
        return 0.0 if indep < 2 else 1.0
    return min(1.0, (indep - 1) / (k - 1))
