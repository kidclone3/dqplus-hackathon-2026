"""Saga engine — pure event-fold helpers (spec §D.3, §5.4).

The saga projection (`current_step`, `status`) is a fold over the append-only
event log. The store computes the next sequence number inside the advance
transaction as ``MAX(seq)+1``; the arithmetic itself is pure and lives here so it
can be unit-tested apart from the SQL.

Pure: no I/O, no `asyncpg`.
"""
from __future__ import annotations

from typing import Iterable


def next_seq(existing_seqs: Iterable[int]) -> int:
    """Next monotonic event sequence for a saga: ``max(seqs) + 1``, or ``1`` for
    the first event. Mirrors the store's ``COALESCE(MAX(seq),0)+1`` verbatim so
    the pure engine and the transactional adapter agree."""
    return max(existing_seqs, default=0) + 1
