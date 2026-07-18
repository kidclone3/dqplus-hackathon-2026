"""Manifest loader (spec §C, Phase 2).

Reads an app's ``app.yaml``, validates it against the platform JSON Schema, and
builds **in-memory data** the platform consumes: saga DAGs (ordered stage lists,
each carrying its ``run``/``port``/``on_reject``) and ``AgentSpec``s (pool key =
``(runtime, skill, model)``). Pure — no DB, no I/O beyond reading the two files.

No deal-flow strings land here: everything domain-specific is data the manifest
declares.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jsonschema
import yaml

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"
_SCHEMA = json.loads(_SCHEMA_PATH.read_text())


@dataclass(slots=True, frozen=True)
class AgentSpec:
    """Declarative agent registry entry. Pool key = (runtime, skill, model)."""

    name: str
    runtime: str
    skill: str = ""
    tools: tuple[str, ...] = ()
    pool_size: int = 1
    model: str | None = None

    @property
    def pool_key(self) -> tuple[str, str, str | None]:
        return (self.runtime, self.skill, self.model)


@dataclass(slots=True, frozen=True)
class OnReject:
    """Declarative retry edge: rearm ``retry`` up to ``max``, else ``then``."""

    retry: str
    max: int
    then: str


@dataclass(slots=True, frozen=True)
class Stage:
    """One node in a saga DAG."""

    stage: str
    run: str  # "code" | agent name
    port: str | None = None
    on_reject: OnReject | None = None

    @property
    def is_code(self) -> bool:
        return self.run == "code"


@dataclass(slots=True, frozen=True)
class Saga:
    """An ordered list of stages forming a saga DAG."""

    name: str
    stages: tuple[Stage, ...]

    @property
    def stage_names(self) -> list[str]:
        return [s.stage for s in self.stages]


@dataclass(slots=True, frozen=True)
class Manifest:
    """A loaded, validated app manifest as in-memory data."""

    app_id: str
    plugin: str
    agents: dict[str, AgentSpec] = field(default_factory=dict)
    ports: dict[str, str] = field(default_factory=dict)
    sagas: dict[str, Saga] = field(default_factory=dict)


def validate_manifest(doc: dict[str, Any]) -> None:
    """Validate a raw manifest dict against the platform JSON Schema.

    Raises ``jsonschema.ValidationError`` on any violation.
    """
    jsonschema.validate(doc, _SCHEMA)


def _build_agent(name: str, a: dict[str, Any]) -> AgentSpec:
    return AgentSpec(
        name=name,
        runtime=a["runtime"],
        skill=a.get("skill", ""),
        tools=tuple(a.get("tools", [])),
        pool_size=int(a.get("pool_size", 1)),
        model=a.get("model"),
    )


def _build_stage(s: dict[str, Any]) -> Stage:
    oj = s.get("on_reject")
    on_reject = (
        OnReject(retry=oj["retry"], max=int(oj["max"]), then=oj["then"])
        if oj is not None
        else None
    )
    return Stage(stage=s["stage"], run=s["run"], port=s.get("port"), on_reject=on_reject)


def parse_manifest(doc: dict[str, Any]) -> Manifest:
    """Validate then build a :class:`Manifest` from a raw dict."""
    validate_manifest(doc)
    agents = {name: _build_agent(name, a) for name, a in doc["agents"].items()}
    ports = dict(doc.get("ports", {}))
    sagas = {
        name: Saga(name=name, stages=tuple(_build_stage(s) for s in stages))
        for name, stages in doc["sagas"].items()
    }
    return Manifest(
        app_id=doc["app_id"],
        plugin=doc["plugin"],
        agents=agents,
        ports=ports,
        sagas=sagas,
    )


def load_manifest(path: str | Path) -> Manifest:
    """Load, validate, and build a manifest from an ``app.yaml`` file."""
    doc = yaml.safe_load(Path(path).read_text())
    return parse_manifest(doc)
