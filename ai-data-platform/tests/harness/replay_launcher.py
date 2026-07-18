"""Fake RuntimeLauncher for the offline North Star harness.

Returns scripted, schema-valid agent JSON keyed by spec.stage so the full saga
machinery runs with no LLM/web/cost. Implements the RuntimeLauncher Protocol
(spine/transport.py:283): spawn(spec, worker_id[, on_usage]) -> RpcChannel-like.
"""
from __future__ import annotations

import re

from spine.transport import RpcResult, TurnUsage

_PARTNER_ID_RE = re.compile(r'"partner_id":\s*"([^"]+)"')


def _enrich(prompt: str) -> dict:
    # Provenance-shaped profile + one relationship (feeds edges → A2).
    return {
        "entity_type": "startup",
        "name": {"value": "Fixture Co", "source_url": "https://example.org/a", "confidence": "high"},
        "country": {"value": "VN", "source_url": "https://example.org/a", "confidence": "high"},
        "website": {"value": None, "confidence": "unavailable", "source_url": None},
        "relationships": [
            {"kind": "raised_from", "dst_name": "Seed Capital VN",
             "source_url": "https://example.org/round"},
        ],
        "collection_summary": {"sources_visited": 2},
    }


def _extract(prompt: str) -> dict:
    # Broad looking_for so investor + corporation + university all pass the
    # permissive filter → A3 cohort spans partner types.
    return {
        "sectors": ["ai"],
        "looking_for": ["funding", "corporate_pilot", "rd_collaboration"],
        "stage": "seed",
        "description_en": "Fixture startup building applied AI.",
        "description_vi": "Công ty khởi nghiệp AI ứng dụng.",
    }


def _rank(prompt: str) -> dict:
    # NOTE: this regex also matches the OUTPUT example inside build_rank_prompt
    # (llm_judge.py); harmless because LlmJudgeMatcher drops out-of-set ids via
    # by_id, but keep it in mind if the prompt format ever changes.
    ids = list(dict.fromkeys(_PARTNER_ID_RE.findall(prompt)))  # de-dup, keep order
    matches = []
    for i, pid in enumerate(ids):
        matches.append({
            "partner_id": pid,
            "composite": max(10, 95 - i * 5),
            "semantic": 0.8, "sector_overlap": 0.9,
            "rationale_en": f"Strong sector alignment with {pid}. Clear value; modest stage risk.",
            "rationale_vi": f"Phù hợp lĩnh vực với {pid}. Giá trị rõ ràng; rủi ro giai đoạn.",
        })
    return {"matches": matches}


def _draft(prompt: str) -> dict:
    return {
        "subject_en": "Introduction", "subject_vi": "Giới thiệu",
        "draft_en": "Hi — we think there is a strong fit worth exploring together.",
        "draft_vi": "Xin chào — chúng tôi thấy có sự phù hợp đáng để cùng khám phá.",
    }


def _verify(prompt: str) -> dict:
    return {"pass": True, "issues": [], "checks": {"grounded": True, "bilingual": True}}


def always_reject_verify(prompt: str) -> dict:
    """Verify that never passes — drives the on_reject retry budget → dead-letter path
    end-to-end (which the happy-path gate never exercises). Schema-valid per verify.json."""
    return {"pass": False, "issues": ["fixture-forced rejection"], "checks": {"grounded": False}}


STAGE_RESPONSES = {
    "enrich": _enrich, "extract": _extract,
    "match": _rank, "draft": _draft, "verify": _verify,
}


class ReplayChannel:
    def __init__(self, gen):
        self._gen = gen
        self._proc = None

    async def prompt(self, message: str, *, timeout: float = 300.0) -> RpcResult:
        return RpcResult(
            id=1, text="", data=self._gen(message),
            usages=[TurnUsage(tokens_in=0, tokens_out=0, cost_usd=0.0)],
            stop_reason="settled",
        )

    async def new_session(self) -> None:
        pass

    async def close(self) -> None:
        pass


class ReplayLauncher:
    """Deterministic fake: RpcResult.data is schema-valid canned JSON per stage.

    `overrides` swaps a stage's response generator (e.g. inject a failing verify to
    drive the reject/retry/dead-letter path the happy-path gate never touches)."""

    def __init__(self, overrides: dict | None = None):
        self.calls: list[str] = []
        self._responses = {**STAGE_RESPONSES, **(overrides or {})}

    async def spawn(self, spec, worker_id, on_usage=None) -> ReplayChannel:
        self.calls.append(spec.stage)
        gen = self._responses.get(spec.stage)
        if gen is None:
            raise AssertionError(f"no canned response for stage {spec.stage!r}")
        return ReplayChannel(gen)
