from __future__ import annotations

from pathlib import Path


SPP_AGENT_ROOT = Path(__file__).resolve().parent.parent


def resolve_benchu_root(configured: str | Path) -> Path:
    """Resolve Bench-U repository root from config path."""
    candidate = Path(configured)
    if not candidate.is_absolute():
        candidate = (SPP_AGENT_ROOT / candidate).resolve()

    if (candidate / "Data" / "Player").is_dir():
        return candidate

    fallback = SPP_AGENT_ROOT.parent.parent.resolve()
    if (fallback / "Data" / "Player").is_dir():
        return fallback

    raise FileNotFoundError(
        f"Bench-U root not found at {candidate}. Expected Data/Player/ subdirectory."
    )


def resolve_results_dir(configured: str | Path) -> Path:
    path = Path(configured)
    if not path.is_absolute():
        path = (SPP_AGENT_ROOT / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
