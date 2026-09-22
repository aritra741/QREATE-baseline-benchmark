"""Fail-closed verified cache for retrieval-aware extraction."""

from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

_FIELDS = (
    "corpus_id",
    "source_document_hash",
    "entity_identity",
    "attribute_bundle",
    "context_mode",
    "context_hashes",
    "schema_hash",
    "prompt_hash",
    "model_id",
    "configuration_hash",
    "operator",
    "tier",
)


def cache_key(manifest: dict[str, Any]) -> str | None:
    values = {}
    for name in _FIELDS:
        value = manifest.get(name)
        if value in (None, "", [], {}):
            return None
        values[name] = value
    payload = json.dumps(values, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


class VerifiedCache:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lookups = 0
        self.hits = 0
        self.misses = 0
        self.rejected = 0
        self._lock = threading.Lock()
        self._memory: dict[str, dict[str, Any]] = {}

    def get(self, manifest: dict[str, Any]) -> dict[str, Any] | None:
        key = cache_key(manifest)
        with self._lock:
            self.lookups += 1
            if key is None:
                self.rejected += 1
                return None
            if key in self._memory:
                self.hits += 1
                return self._memory[key]
            path = self.root / f"{key}.json"
            if not path.is_file():
                self.misses += 1
                return None
            payload = json.loads(path.read_text())
            stored = payload.get("manifest") or {}
            if any(stored.get(name) != manifest.get(name) for name in _FIELDS):
                self.rejected += 1
                return None
            self.hits += 1
            self._memory[key] = payload
            return payload

    def put(self, manifest: dict[str, Any], record: dict[str, Any]) -> str | None:
        key = cache_key(manifest)
        if key is None:
            return None
        payload = {"manifest": {name: manifest[name] for name in _FIELDS}, "record": record}
        with self._lock:
            self._memory[key] = payload
            (self.root / f"{key}.json").write_text(json.dumps(payload, indent=2, default=str))
        return key

    def hit_rate(self) -> float | str:
        if self.lookups == 0:
            return "not_applicable"
        return self.hits / self.lookups
