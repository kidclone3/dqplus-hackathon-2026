"""LlmJudgeMatcher parsing unit tests (R12). Fake runner — no real pi process.

Asserts: prompt built + sent, rank.json parsed to ScoredMatch, hallucinated partner ids
dropped, results sorted by composite desc, composite clamped 0-100.
"""
import pytest

from apps.matchmaker.matcher import ScoredMatch
from apps.matchmaker.matcher.llm_judge import LlmJudgeMatcher
from spine.transport import RpcResult


def _entity(pid, name, type_):
    return {"id": pid, "name": name, "type": type_,
            "profile": {"normalized": {"sectors": ["ai"], "description_en": name}}}


def _startup():
    return {"id": "startup:x", "name": "X",
            "profile": {"normalized": {"sectors": ["ai"], "looking_for": ["funding"],
                                       "description_en": "an ai startup"}}}


def _result(data):
    return RpcResult(id=1, text="", data=data)


async def test_rank_parses_and_sorts():
    candidates = [_entity("investor:a", "A", "investor"),
                  _entity("investor:b", "B", "investor")]
    captured = {}

    async def runner(prompt):
        captured["prompt"] = prompt
        return _result({"matches": [
            {"partner_id": "investor:a", "composite": 70, "semantic": 0.6,
             "sector_overlap": 0.5, "rationale_en": "ok", "rationale_vi": "được"},
            {"partner_id": "investor:b", "composite": 92, "semantic": 0.9,
             "sector_overlap": 1.0, "rationale_en": "great", "rationale_vi": "tốt"},
        ]})

    out = await LlmJudgeMatcher(runner).rank(_startup(), candidates, ctx={})
    assert [m.partner_id for m in out] == ["investor:b", "investor:a"]  # sorted desc
    assert isinstance(out[0], ScoredMatch)
    assert out[0].composite == 92.0 and out[0].partner_name == "B"
    assert "investor:a" in captured["prompt"]  # candidates rendered into the prompt


async def test_rank_drops_hallucinated_ids_and_clamps():
    candidates = [_entity("investor:a", "A", "investor")]

    async def runner(prompt):
        return _result({"matches": [
            {"partner_id": "investor:ghost", "composite": 80,
             "rationale_en": "x", "rationale_vi": "x"},          # not in candidate set
            {"partner_id": "investor:a", "composite": 150,
             "rationale_en": "x", "rationale_vi": "x"},          # clamp to 100
        ]})

    out = await LlmJudgeMatcher(runner).rank(_startup(), candidates, ctx={})
    assert [m.partner_id for m in out] == ["investor:a"]
    assert out[0].composite == 100.0


async def test_rank_empty_on_failure_or_bad_json():
    async def bad(prompt):
        return _result(None)

    async def errored(prompt):
        return RpcResult(id=1, text="", data={"matches": []}, stop_reason="error")

    assert await LlmJudgeMatcher(bad).rank(_startup(), [_entity("investor:a", "A", "investor")], ctx={}) == []
    assert await LlmJudgeMatcher(errored).rank(_startup(), [_entity("investor:a", "A", "investor")], ctx={}) == []


async def test_rank_no_candidates_short_circuits():
    async def runner(prompt):
        raise AssertionError("should not run pi with no candidates")

    assert await LlmJudgeMatcher(runner).rank(_startup(), [], ctx={}) == []
