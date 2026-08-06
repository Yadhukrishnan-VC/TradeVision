"""M3 corrective batch — rule_engine layering regression guard.

Core deterministic components (rule_engine and below) must not depend on
``apps.backtesting``. Account routing for backtest replay is provided by the
generic ``core.execution_context`` abstraction instead, so a re-import of the
backtesting application from rule_engine would be a regression of the
previously-fixed layering violation.

This test statically scans every module in the ``apps.rule_engine`` package
for any import (including lazy imports) that references ``apps.backtesting``
or the bare ``backtesting`` module. It is intentionally dependency-free: it
never imports the package under test, so it cannot be defeated by import
ordering or by backtesting being unavailable.
"""

from __future__ import annotations

import ast
from pathlib import Path

RULE_ENGINE_PACKAGE = Path(__file__).resolve().parents[1]
FORBIDDEN_IMPORT_PREFIXES = ("apps.backtesting", "backtesting")


def _import_targets(tree: ast.Module) -> list[str]:
    """Return every module referenced by the file's import statements."""
    targets: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            targets.append(node.module)
    return targets


def _iter_python_files() -> list[Path]:
    return sorted(RULE_ENGINE_PACKAGE.rglob("*.py"))


def test_rule_engine_has_no_import_dependency_on_backtesting() -> None:
    offenders: list[str] = []
    for path in _iter_python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for target in _import_targets(tree):
            if target.startswith(FORBIDDEN_IMPORT_PREFIXES):
                offenders.append(
                    f"{path.relative_to(RULE_ENGINE_PACKAGE)}: imports {target!r}"
                )

    assert not offenders, (
        "apps.rule_engine must not import apps.backtesting; use "
        "core.execution_context instead.\n" + "\n".join(offenders)
    )


def test_rule_engine_package_contains_python_modules() -> None:
    assert _iter_python_files(), "rule_engine package must contain Python modules"
