"""Phase 2 unit tests — pure, no DB.

Prove the manifest loader yields the expected saga stage lists — the manifest is now
the single source of truth for the sagas that ``spine.sagas``/``spine.outreach`` used
to hardcode (Phase 5 removed those modules).
"""
from __future__ import annotations

from pathlib import Path

import jsonschema
import pytest

from spindle import registry
from spindle.manifest import load_manifest, parse_manifest, validate_manifest

_MANIFEST = Path(__file__).resolve().parent.parent / "apps" / "matchmaker" / "app.yaml"


@pytest.fixture(scope="module")
def manifest():
    return load_manifest(_MANIFEST)


# --- saga DAGs mirror today's hardcoded stage lists exactly --------------------

def test_onboarding_stage_list_matches_today(manifest):
    assert manifest.sagas["onboarding"].stage_names == ["enrich", "extract", "link"]


def test_outreach_stage_list_matches_today(manifest):
    assert manifest.sagas["outreach"].stage_names == ["filter", "match", "draft", "verify"]


def test_no_ingest_stage(manifest):
    assert "ingest" not in manifest.sagas["onboarding"].stage_names


# --- manifest identity + agents -----------------------------------------------

def test_app_identity(manifest):
    assert manifest.app_id == "matchmaker"
    assert manifest.plugin == "apps.matchmaker.plugin"


def test_agents_parsed_with_pool_keys(manifest):
    assert set(manifest.agents) == {"enricher", "extractor", "matcher", "drafter",
                                    "verifier", "janitor"}
    enricher = manifest.agents["enricher"]
    assert enricher.runtime == "feynman"
    assert enricher.pool_size == 2
    assert "web_search" in enricher.tools
    # pool key = (runtime, skill, model)
    assert enricher.pool_key == ("feynman", ".feynman/agent/skills/entity-enrichment", None)


# --- run resolution: code vs agent, ports, on_reject --------------------------

def test_stage_run_resolution(manifest):
    onboarding = {s.stage: s for s in manifest.sagas["onboarding"].stages}
    assert onboarding["enrich"].run == "enricher"
    assert onboarding["enrich"].is_code is False
    assert onboarding["extract"].run == "extractor"
    assert onboarding["link"].run == "code"
    assert onboarding["link"].is_code is True


def test_match_stage_exposes_matcher_port(manifest):
    match = next(s for s in manifest.sagas["outreach"].stages if s.stage == "match")
    assert match.port == "matcher"
    assert manifest.ports["matcher"] == "matchmaker.LlmJudgeMatcher"


def test_verify_on_reject_edge(manifest):
    verify = next(s for s in manifest.sagas["outreach"].stages if s.stage == "verify")
    assert verify.on_reject is not None
    assert verify.on_reject.retry == "draft"
    assert verify.on_reject.max == 3          # = config.MAX_ATTEMPTS
    assert verify.on_reject.then == "dead"


# --- schema validation is enforced --------------------------------------------

def _valid_doc() -> dict:
    return {
        "app_id": "x",
        "plugin": "x.plugin",
        "agents": {"a": {"runtime": "pi"}},
        "sagas": {"s": [{"stage": "one", "run": "code"}]},
    }


def test_valid_minimal_doc_passes():
    validate_manifest(_valid_doc())  # no raise


def test_missing_required_field_rejected():
    doc = _valid_doc()
    del doc["sagas"]
    with pytest.raises(jsonschema.ValidationError):
        parse_manifest(doc)


def test_stage_missing_run_rejected():
    doc = _valid_doc()
    doc["sagas"]["s"] = [{"stage": "one"}]
    with pytest.raises(jsonschema.ValidationError):
        parse_manifest(doc)


def test_unknown_key_rejected():
    doc = _valid_doc()
    doc["bogus"] = True
    with pytest.raises(jsonschema.ValidationError):
        parse_manifest(doc)


# --- plugin/port registry decorators ------------------------------------------

def test_registry_decorators_register_and_resolve():
    registry.clear()

    @registry.stage("link")
    def link(ctx):  # noqa: ARG001
        return "linked"

    @registry.agent_stage("enrich")
    class EnrichStage:
        pass

    @registry.port("matcher")
    class LlmJudgeMatcher:
        pass

    assert registry.get_stage("link") is link
    assert registry.get_agent_stage("enrich") is EnrichStage
    assert registry.get_port("matcher") is LlmJudgeMatcher
    registry.clear()


def test_registry_rejects_duplicate():
    registry.clear()

    @registry.stage("dup")
    def _a(ctx):  # noqa: ARG001
        pass

    with pytest.raises(ValueError):
        @registry.stage("dup")
        def _b(ctx):  # noqa: ARG001
            pass

    registry.clear()
