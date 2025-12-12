#!/usr/bin/env python3
"""
Utility script to strip null bytes from text files.

Usage:
    python scripts/remove_null_bytes.py path1 path2 ...

The script overwrites each file in place after removing any \x00 bytes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys


def scrub_file(path: Path, dry_run: bool) -> bool:
    data = path.read_bytes()
    if b"\x00" not in data:
        return False
    if dry_run:
        return True
    cleaned = data.replace(b"\x00", b"")
    path.write_bytes(cleaned)
    return True


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Remove null bytes from files.")
    parser.add_argument(
        "paths",
        nargs="+",
        help="File paths to process.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which files contain null bytes without modifying them.",
    )
    args = parser.parse_args(argv)

    modified = False
    for raw_path in args.paths:
        path = Path(raw_path).expanduser().resolve()
        if not path.exists():
            print(f"[skip] {path} (missing)")
            continue
        if path.is_dir():
            print(f"[skip] {path} (directory)")
            continue

        has_nulls = scrub_file(path, args.dry_run)
        if has_nulls:
            action = "would clean" if args.dry_run else "cleaned"
            print(f"[{action}] {path}")
            modified = True
        else:
            print(f"[ok] {path}")

    return 0 if modified else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

