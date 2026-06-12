"""Disk cache for LLM outputs used during population."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from utils.config import load_config
from utils.logging import setup_logger

logger = setup_logger("spp.llm_output_cache")

_CACHE: dict[str, Any] | None = None
_CACHE_PATH: Path | None = None


def _default_cache_path() -> Path:
    cfg = load_config()
    results_dir = Path(cfg["paths"]["results_dir"])
    return results_dir / "llm_output_cache" / "population.json"


def _digest(*parts: Any) -> str:
    payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _ensure_loaded() -> dict[str, Any]:
    global _CACHE, _CACHE_PATH
    if _CACHE is None:
        _CACHE_PATH = _default_cache_path()
        _CACHE = _load_cache(_CACHE_PATH)
    return _CACHE


def get_cached_json(namespace: str, key: str) -> Any | None:
    cache = _ensure_loaded()
    bucket = cache.get(namespace)
    if not isinstance(bucket, dict):
        return None
    hit = bucket.get(key)
    if hit is not None:
        logger.debug("LLM cache hit namespace=%s key=%s", namespace, key[:12])
    return hit


def put_cached_json(namespace: str, key: str, value: Any) -> None:
    global _CACHE, _CACHE_PATH
    cache = _ensure_loaded()
    bucket = cache.setdefault(namespace, {})
    if not isinstance(bucket, dict):
        bucket = {}
        cache[namespace] = bucket
    bucket[key] = value
    if _CACHE_PATH is not None:
        _save_cache(_CACHE_PATH, cache)


def cache_key(model_name: str, *parts: Any) -> str:
    return _digest(model_name, *parts)


# Backward-compatible norm helpers (used by population.py)
def get_norm_mapping(model_name: str, values: list[str]) -> dict[str, str] | None:
    key = cache_key(model_name, "norm", sorted({v for v in values if isinstance(v, str) and v.strip()}))
    hit = get_cached_json("norm", key)
    return hit if isinstance(hit, dict) else None


def put_norm_mapping(model_name: str, values: list[str], mapping: dict[str, str]) -> None:
    key = cache_key(model_name, "norm", sorted({v for v in values if isinstance(v, str) and v.strip()}))
    put_cached_json("norm", key, {str(k): str(v) for k, v in mapping.items()})
