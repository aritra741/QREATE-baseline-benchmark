#!/usr/bin/env python3
"""Execute one query from a sealed SPP bundle (SQL only, no extraction)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WDIRS_ROOT = Path(__file__).resolve().parents[1]
if str(WDIRS_ROOT) not in sys.path:
    sys.path.insert(0, str(WDIRS_ROOT))

from spp.serving import OfflineQueryServer  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("query_id")
    args = parser.parse_args()
    server = OfflineQueryServer(args.bundle)
    rows = server.execute(args.query_id)
    print(json.dumps(rows, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
