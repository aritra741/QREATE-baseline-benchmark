"""Gold-vs-predicted cell classification. Eval-side only."""

from __future__ import annotations

import csv
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[4]
GOLD_DIR = ROOT / "Data"


def _norm_key(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    return re.sub(r"\s+", " ", text)


def _near_norm(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_null(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() in {"none", "null", "n/a", "na", "-1"}


def exact_match(gold: Any, pred: Any) -> bool:
    if is_null(gold) and is_null(pred):
        return True
    if is_null(gold) or is_null(pred):
        return False
    if _norm_key(gold) == _norm_key(pred):
        return True
    try:
        return float(str(gold).replace(",", "")) == float(str(pred).replace(",", ""))
    except (TypeError, ValueError):
        return False


def load_gold_csv(dataset: str) -> list[dict[str, Any]]:
    path = GOLD_DIR / dataset / f"{dataset}.csv"
    if not path.is_file():
        matches = list((GOLD_DIR / dataset).glob("*.csv"))
        if not matches:
            raise FileNotFoundError(f"no gold CSV under {GOLD_DIR / dataset}")
        path = matches[0]
    rows = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle, skipinitialspace=True):
            rows.append(
                {
                    str(key).strip().lower(): (
                        value.strip() if isinstance(value, str) else value
                    )
                    for key, value in row.items()
                }
            )
    return rows


def load_sqlite_rows(path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(path)
    try:
        tables = [
            name
            for (name,) in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        ]
        table = tables[0]
        cols = [info[1] for info in conn.execute(f'PRAGMA table_info("{table}")')]
        return [
            {str(col).lower(): value for col, value in zip(cols, row)}
            for row in conn.execute(f'SELECT * FROM "{table}"')
        ]
    finally:
        conn.close()


def align_rows(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
) -> dict[int, int]:
    by_name: dict[str, int] = {}
    by_id: dict[str, int] = {}
    for index, row in enumerate(pred):
        name = _norm_key(row.get("name"))
        if name:
            by_name.setdefault(name, index)
        raw = row.get("doc_id") or row.get("id")
        if raw not in (None, ""):
            stem = Path(str(raw)).stem
            by_id[_norm_key(stem)] = index
            try:
                by_id[str(int(stem))] = index
            except (TypeError, ValueError):
                pass
    mapping: dict[int, int] = {}
    for gi, grow in enumerate(gold):
        name = _norm_key(grow.get("name"))
        if name in by_name:
            mapping[gi] = by_name[name]
            continue
        gid = _norm_key(grow.get("id"))
        if gid in by_id:
            mapping[gi] = by_id[gid]
            continue
        try:
            mapping[gi] = by_id[str(int(gid))]
        except (TypeError, ValueError, KeyError):
            continue
    return mapping


def classify_cells(
    gold: list[dict[str, Any]],
    pred: list[dict[str, Any]],
    attributes: Iterable[str],
) -> dict[str, Any]:
    attrs = list(attributes)
    mapping = align_rows(gold, pred)
    counts = {attr: Counter() for attr in attrs}
    gold_nonnull = Counter()
    for gi, grow in enumerate(gold):
        prow = pred[mapping[gi]] if gi in mapping else None
        for attr in attrs:
            gv = grow.get(attr)
            gold_has = not is_null(gv)
            gold_nonnull[attr] += int(gold_has)
            if prow is None:
                bucket = "entity_miss"
            elif not gold_has:
                bucket = (
                    "gold_null_pred_null"
                    if is_null(prow.get(attr))
                    else "gold_null_pred_filled"
                )
            elif is_null(prow.get(attr)):
                bucket = "not_found"
            elif exact_match(gv, prow.get(attr)):
                bucket = "exact"
            elif _near_norm(gv) == _near_norm(prow.get(attr)) and _near_norm(gv):
                bucket = "near_miss"
            else:
                bucket = "wrong"
            counts[attr][bucket] += 1
    totals = Counter()
    per_attr = {}
    for attr in attrs:
        per_attr[attr] = dict(counts[attr])
        per_attr[attr]["gold_nonnull"] = gold_nonnull[attr]
        totals.update(counts[attr])
    errors = {
        "not_found": totals["not_found"],
        "near_miss": totals["near_miss"],
        "wrong": totals["wrong"],
        "entity_miss": totals["entity_miss"],
        "exact": totals["exact"],
    }
    drop = errors["not_found"] + errors["near_miss"]
    return {
        "aligned": len(mapping),
        "gold_rows": len(gold),
        "pred_rows": len(pred),
        "per_attribute": per_attr,
        "totals": dict(totals),
        "gold_nonnull_errors": errors,
        "gate": "not_found_near" if drop >= errors["wrong"] else "wrong",
    }


def tokens_from_evidence(evidence_dir: Path) -> dict[str, dict[str, int]]:
    import json

    by_attr: dict[str, dict[str, int]] = defaultdict(lambda: Counter())
    if not evidence_dir.is_dir():
        return {}
    for path in evidence_dir.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        attr = str(row.get("attribute") or "").split(".")[-1]
        if not attr:
            continue
        by_attr[attr]["tokens"] += int(row.get("tokens_spent") or 0)
        by_attr[attr]["records"] += 1
        by_attr[attr][row.get("null_reason") or "ok"] += 1
    return {name: dict(stats) for name, stats in by_attr.items()}
