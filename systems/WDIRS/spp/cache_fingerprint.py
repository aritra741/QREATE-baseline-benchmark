"""Ground-truth-free fingerprints for reusable synthesis scratch state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping


CACHE_SCHEMA_VERSION = "offline-spp-nl-v2"
MARKER_FILENAME = "spp_cache_fingerprint.json"


def _hash_file(path: Path, digest: "hashlib._Hash") -> None:
    digest.update(str(path.name).encode("utf-8"))
    digest.update(b"\0")
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(b"\0")


def source_tree_sha256(source_dir: Path) -> str:
    """Hash source documents without consulting benchmark answers."""
    source_dir = Path(source_dir).expanduser().resolve()
    digest = hashlib.sha256()
    if not source_dir.is_dir():
        return digest.hexdigest()
    files = sorted(
        (path for path in source_dir.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(source_dir).as_posix(),
    )
    for path in files:
        digest.update(path.relative_to(source_dir).as_posix().encode("utf-8"))
        digest.update(b"\0")
        _hash_file(path, digest)
    return digest.hexdigest()


def synthesis_cache_fingerprint(
    *,
    dataset: str,
    workload_path: Path,
    source_dir: Path,
    implementation_paths: Iterable[Path] = (),
    parameters: Mapping[str, object] | None = None,
) -> dict:
    """Return the complete identity of reusable extraction state."""
    workload_path = Path(workload_path).expanduser().resolve()
    workload_digest = hashlib.sha256(workload_path.read_bytes()).hexdigest()
    implementation_digest = hashlib.sha256()
    for path in sorted(
        (Path(item).expanduser().resolve() for item in implementation_paths),
        key=str,
    ):
        implementation_digest.update(str(path.name).encode("utf-8"))
        implementation_digest.update(b"\0")
        implementation_digest.update(path.read_bytes())
        implementation_digest.update(b"\0")
    payload = {
        "version": CACHE_SCHEMA_VERSION,
        "dataset": str(dataset),
        "workload_sha256": workload_digest,
        "source_tree_sha256": source_tree_sha256(source_dir),
        "implementation_sha256": implementation_digest.hexdigest(),
        "parameters": dict(parameters or {}),
    }
    payload["fingerprint"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return payload


def ensure_compatible_scratch(scratch_dir: Path, fingerprint: dict) -> Path:
    """Refuse reuse when scratch contents were built for another pipeline."""
    scratch_dir = Path(scratch_dir).expanduser().resolve()
    scratch_dir.mkdir(parents=True, exist_ok=True)
    marker = scratch_dir / MARKER_FILENAME
    if marker.exists():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("fingerprint") != fingerprint.get("fingerprint"):
            raise ValueError(
                "backend scratch fingerprint mismatch; remove the scratch "
                f"directory or choose a new one: {scratch_dir}"
            )
        return marker
    legacy_entries = [path for path in scratch_dir.iterdir()]
    if legacy_entries:
        raise ValueError(
            "backend scratch contains unversioned artifacts; refusing unsafe "
            f"cache reuse: {scratch_dir}"
        )
    marker.write_text(
        json.dumps(fingerprint, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return marker
