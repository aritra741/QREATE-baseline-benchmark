"""Tests for ground-truth-free synthesis cache identities."""

from pathlib import Path

import pytest

from spp.cache_fingerprint import (
    ensure_compatible_scratch,
    synthesis_cache_fingerprint,
)


def _fingerprint(tmp_path: Path, *, source_text: str = "source") -> dict:
    source = tmp_path / "source"
    source.mkdir(exist_ok=True)
    (source / "document.txt").write_text(source_text, encoding="utf-8")
    workload = tmp_path / "workload.json"
    workload.write_text('[{"query_id":"q","text":"count records"}]')
    implementation = tmp_path / "implementation.py"
    implementation.write_text("VERSION = 1\n", encoding="utf-8")
    return synthesis_cache_fingerprint(
        dataset="synthetic",
        workload_path=workload,
        source_dir=source,
        implementation_paths=(implementation,),
    )


def test_matching_synthesis_cache_fingerprint_is_reusable(
    tmp_path: Path,
) -> None:
    fingerprint = _fingerprint(tmp_path)
    scratch = tmp_path / "scratch"
    marker = ensure_compatible_scratch(scratch, fingerprint)
    assert ensure_compatible_scratch(scratch, fingerprint) == marker


def test_source_change_rejects_stale_synthesis_cache(tmp_path: Path) -> None:
    first = _fingerprint(tmp_path, source_text="before")
    scratch = tmp_path / "scratch"
    ensure_compatible_scratch(scratch, first)
    second = _fingerprint(tmp_path, source_text="after")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        ensure_compatible_scratch(scratch, second)


def test_unversioned_synthesis_cache_is_not_silently_reused(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "legacy.sqlite").write_bytes(b"legacy")
    with pytest.raises(ValueError, match="unversioned"):
        ensure_compatible_scratch(scratch, _fingerprint(tmp_path))
