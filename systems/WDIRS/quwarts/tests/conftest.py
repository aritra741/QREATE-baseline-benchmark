from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

WORKSPACE = ROOT / "quwarts_workspace"
CORPUS = WORKSPACE / "data" / "corpora" / "toy"
GOLD = WORKSPACE / "data" / "gold"


@pytest.fixture
def toy_corpus() -> Path:
    return CORPUS
