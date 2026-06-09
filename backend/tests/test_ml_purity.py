"""Guards the ml/ package boundary: no SQLAlchemy, FastAPI, or app db/api/services
imports may appear in app/ml/*.py — including inside function bodies.

Implemented as an AST scan of the source (not a runtime __module__ heuristic),
so it catches plain `import sqlalchemy`, `from app.db import x`, and
function-local imports alike. A positive-control test proves the scanner fires.
"""
import ast
from pathlib import Path

ML_DIR = Path(__file__).resolve().parent.parent / "app" / "ml"
FORBIDDEN_PREFIXES = ("sqlalchemy", "fastapi", "app.db", "app.api", "app.services")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    mods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        # level == 0 means absolute import; relative imports inside ml/ are fine.
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
    return mods


def _forbidden_in(source: str) -> list[str]:
    return sorted(
        m for m in _imported_modules(source) if m.startswith(FORBIDDEN_PREFIXES)
    )


def test_ml_modules_have_no_forbidden_imports() -> None:
    py_files = sorted(ML_DIR.glob("*.py"))
    assert py_files, f"no ml modules found under {ML_DIR}"
    for path in py_files:
        offenders = _forbidden_in(path.read_text(encoding="utf-8"))
        assert offenders == [], f"{path.name} imports forbidden modules: {offenders}"


def test_purity_scanner_detects_violations() -> None:
    # Positive control: without these passing, the guard above is worthless.
    assert _forbidden_in("import sqlalchemy") == ["sqlalchemy"]
    assert _forbidden_in("from app.db import models") == ["app.db"]
    assert _forbidden_in("def f():\n    import fastapi\n") == ["fastapi"]
    assert _forbidden_in("from app.services.x import y") == ["app.services.x"]
    # Clean imports must NOT be flagged.
    assert _forbidden_in("import json\nfrom app.ml.types import GameFeatures") == []
