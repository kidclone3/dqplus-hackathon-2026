"""Compatibility re-export — the supervisor moved to ``spindle.app.supervisor``.

Phase 4 (spec §D) extracted the reconciler into the domain-agnostic platform core
at ``spindle/app/supervisor.py``: it now reads every stage name, saga shape, pool
key, and retry edge from loaded app manifests, holding no deal-flow strings.

This shim keeps ``from spine.supervisor import Supervisor`` and
``python -m spine.supervisor`` working for callers that predate the move (the
crash-recovery + North Star harnesses, the README run commands).
"""
from __future__ import annotations

import asyncio

from spindle.app.supervisor import Supervisor, main

__all__ = ["Supervisor", "main"]


if __name__ == "__main__":
    asyncio.run(main())
