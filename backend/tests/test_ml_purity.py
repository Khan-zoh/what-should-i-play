import importlib
import sys

ML_MODULES = [
    "app.ml.types",
    "app.ml.weights",
    "app.ml.heuristic",
    "app.ml.explanations",
]
FORBIDDEN_PREFIXES = ("sqlalchemy", "fastapi", "app.db", "app.api", "app.services")


def test_ml_package_imports_no_io_or_orm() -> None:
    # Import each ml module, then assert none of the names it exposes were
    # pulled in from SQLAlchemy, FastAPI, or the app's db/api/services layers.
    for mod in ML_MODULES:
        importlib.import_module(mod)
    for mod in ML_MODULES:
        module = sys.modules[mod]
        for attr_name in dir(module):
            attr_mod = getattr(getattr(module, attr_name), "__module__", "")
            assert not str(attr_mod).startswith(FORBIDDEN_PREFIXES), (
                f"{mod}.{attr_name} comes from forbidden module {attr_mod}"
            )
