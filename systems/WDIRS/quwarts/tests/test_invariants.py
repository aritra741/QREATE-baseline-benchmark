from __future__ import annotations

import ast
from pathlib import Path

import pytest

from quwarts.core.guards import assert_not_gold
from quwarts.core.ledger import BudgetExhausted, TokenLedger


CORE = Path(__file__).resolve().parents[1] / "core"


def test_core_does_not_import_eval() -> None:
    offenders = []
    for path in CORE.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("quwarts.eval"):
                        offenders.append(f"{path}: import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.startswith("quwarts.eval"):
                    offenders.append(f"{path}: from {module}")
    assert offenders == []


def test_core_guard_rejects_gold_path() -> None:
    with pytest.raises(PermissionError):
        assert_not_gold("data/gold/answers.csv")


def test_ledger_enforces_theta() -> None:
    ledger = TokenLedger(theta=10, seed=1)
    ledger.spend(4, "extract")
    with pytest.raises(BudgetExhausted):
        ledger.spend(7, "extract")
    assert ledger.spent == 4
