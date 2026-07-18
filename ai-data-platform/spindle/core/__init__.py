"""Platform core — pure orchestration logic (spec §E).

Saga engine, DAG advance, and the boot reconciler as I/O-free functions the
supervisor (the composition root) wires to real adapters in Phase 4. This
package may import `spindle.ports` and stdlib **only** — never `adapters/` and
never `asyncpg`. That rule is enforced by `tests/test_core_import_lint.py`; it
is the whole point of the hexagonal split.
"""
