"""Plugin/port registry (spec §C, Seam 1).

A plugin module registers its code-stage bodies, agent-stage handlers, and named
ports by name via these decorators; the platform resolves ``stage -> {run, port?}``
from the manifest and looks the implementation up here at dispatch time.

The ``Matcher`` port stops being special: it is simply the first named port, and
this generic registry is the real generalization of the old hardcoded wiring.
"""
from __future__ import annotations

from typing import Callable, TypeVar

_T = TypeVar("_T")

# name -> implementation
_STAGES: dict[str, Callable] = {}
_AGENT_STAGES: dict[str, type] = {}
_PORTS: dict[str, type] = {}
# the app-facing store factory: pool -> store (registered by the plugin so the
# generic entrypoint builds the app store without naming the app in platform code).
_APP_STORE: list[Callable] = []


def stage(name: str) -> Callable[[_T], _T]:
    """Register a ``run: code`` stage body under ``name``."""

    def deco(fn: _T) -> _T:
        if name in _STAGES:
            raise ValueError(f"stage {name!r} already registered")
        _STAGES[name] = fn  # type: ignore[assignment]
        return fn

    return deco


def agent_stage(name: str) -> Callable[[_T], _T]:
    """Register an ``AgentStageHandler`` class for an agent-backed stage."""

    def deco(cls: _T) -> _T:
        if name in _AGENT_STAGES:
            raise ValueError(f"agent_stage {name!r} already registered")
        _AGENT_STAGES[name] = cls  # type: ignore[assignment]
        return cls

    return deco


def port(name: str) -> Callable[[_T], _T]:
    """Register a named, app-swappable component class under ``name``."""

    def deco(cls: _T) -> _T:
        if name in _PORTS:
            raise ValueError(f"port {name!r} already registered")
        _PORTS[name] = cls  # type: ignore[assignment]
        return cls

    return deco


def app_store(factory: _T) -> _T:
    """Register the app-facing store factory ``(pool) -> store``. The generic
    entrypoint resolves it to build the app store, so no app is named in platform
    code (spec §A boundary)."""
    _APP_STORE[:] = [factory]  # type: ignore[list-item]
    return factory


def get_app_store() -> Callable:
    if not _APP_STORE:
        raise LookupError("no app store factory registered (load an app plugin first)")
    return _APP_STORE[0]


def get_stage(name: str) -> Callable:
    return _STAGES[name]


def get_agent_stage(name: str) -> type:
    return _AGENT_STAGES[name]


def get_port(name: str) -> type:
    return _PORTS[name]


def clear() -> None:
    """Reset all registries (test isolation)."""
    _STAGES.clear()
    _AGENT_STAGES.clear()
    _PORTS.clear()
    _APP_STORE.clear()
