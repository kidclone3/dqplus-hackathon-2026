"""Boot reconciler — pure survivor/orphan partition (spec §D.4, §5.2).

Postgres is the source of truth for desired + leased state; the supervisor is a
reconciler. The *decision* — which non-dead workers belong to a prior boot epoch
and are therefore orphans to kill — is pure and testable here; the adapter does
the SQL read + the kill.

Pure: no I/O, no `asyncpg`.
"""
from __future__ import annotations

from typing import Iterable, Mapping


def partition_orphans(workers: Iterable[Mapping], boot_epoch: str) -> tuple[list, list]:
    """Split worker rows into (survivors, orphans) for this ``boot_epoch``.

    Orphans are non-dead rows from a different epoch (a crashed prior supervisor's
    workers); survivors are this epoch's own. Callers mark orphans dead and reclaim
    their leases. Rows already ``status == 'dead'`` are neither.
    """
    survivors: list = []
    orphans: list = []
    for w in workers:
        if w.get("status") == "dead":
            continue
        (survivors if w.get("boot_epoch") == boot_epoch else orphans).append(w)
    return survivors, orphans
