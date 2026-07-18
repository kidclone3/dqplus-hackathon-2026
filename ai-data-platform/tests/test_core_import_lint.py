"""Import-lint for the hexagonal core (spec §E).

`spindle/core/` is the one package with an enforced import rule: it may import
`spindle.ports` and stdlib, but **never** `spindle.adapters` or `asyncpg`. That
rule is the whole point of the I/O-free core — verify it cheaply here.

Two checks: a static AST scan of every `core/*.py` (catches a direct forbidden
import) and a transitive runtime check (importing the core in a fresh interpreter
must not drag `asyncpg`/`spindle.adapters` into `sys.modules`).
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parent.parent / "spindle" / "core"
_FORBIDDEN_PREFIXES = ("asyncpg", "spindle.adapters")


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def test_core_never_imports_adapters_or_asyncpg_statically():
    offenders: list[str] = []
    for py in sorted(_CORE.glob("*.py")):
        for mod in _imported_modules(py):
            if any(mod == p or mod.startswith(p + ".") for p in _FORBIDDEN_PREFIXES):
                offenders.append(f"{py.name} imports {mod}")
    assert not offenders, "core purity violated: " + "; ".join(offenders)


def test_core_never_pulls_adapters_or_asyncpg_transitively():
    repo_root = _CORE.parents[1]
    code = (
        "import sys; import importlib, pkgutil; "
        "import spindle.core as c; "
        "[importlib.import_module(m.name) for m in pkgutil.iter_modules(c.__path__, 'spindle.core.')]; "
        "bad = [m for m in sys.modules "
        "if m == 'asyncpg' or m.startswith('asyncpg.') or m.startswith('spindle.adapters')]; "
        "print(','.join(sorted(bad)))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=repo_root,
        capture_output=True, text=True, check=True,
    )
    leaked = out.stdout.strip()
    assert leaked == "", f"core transitively imported forbidden modules: {leaked}"
