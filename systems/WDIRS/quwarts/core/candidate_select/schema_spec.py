"""Compile official schema semantics. No workload predicate literals in the spec surface."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quwarts.core.shared_bundle.inventory import AttributeRecord

_DOMAIN = re.compile(r"choose(?:\s+only)?(?:\s+one(?:\s+or\s+more)?)?\s+from\s*\[([^\]]+)\]", re.I)
_ITEM = re.compile(r"'([^']+)'|\"([^\"]+)\"")


@dataclass
class AttrSpec:
    name: str
    official_description: str
    sql_type: str
    dtype: str
    usage: str
    is_fixed: bool
    schema_domain: list[str]
    roles: dict[str, int]
    n_expressions: int
    n_queries: int
    allows_sum: bool
    requires_usd: bool
    target_currency: str | None
    unit_percent: bool
    task_class: str
    normalization: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "official_description": self.official_description,
            "sql_type": self.sql_type,
            "dtype": self.dtype,
            "usage": self.usage,
            "is_fixed": self.is_fixed,
            "schema_domain": list(self.schema_domain),
            "roles": dict(self.roles),
            "n_expressions": self.n_expressions,
            "n_queries": self.n_queries,
            "allows_sum": self.allows_sum,
            "requires_usd": self.requires_usd,
            "target_currency": self.target_currency,
            "unit_percent": self.unit_percent,
            "task_class": self.task_class,
            "normalization": list(self.normalization),
        }


def load_official_catalog(path: Path) -> dict[str, dict[str, Any]]:
    raw = json.loads(path.read_text())
    out: dict[str, dict[str, Any]] = {}
    tables = raw.values() if isinstance(raw, dict) else []
    for attrs in tables:
        if not isinstance(attrs, dict):
            continue
        if any(isinstance(v, dict) and "description" in v for v in attrs.values()):
            items = attrs.items()
        else:
            continue
        for name, spec in items:
            if isinstance(spec, dict):
                key = str(name).strip()
                out[key] = spec
                out[key.lower()] = spec
    if not out:
        raise SystemExit(f"official schema at {path} has no attribute descriptions")
    return out


def parse_schema_domain(description: str) -> list[str]:
    match = _DOMAIN.search(description or "")
    if not match:
        return []
    found = [a or b for a, b in _ITEM.findall(match.group(1))]
    return list(dict.fromkeys(item.strip() for item in found if item.strip()))


def parse_normalization(description: str) -> list[str]:
    text = (description or "").lower()
    out: list[str] = []
    if "enter a number" in text:
        out.append("numeric")
    if re.search(r"convert to\s+[a-z]{3,}|exchange rate", text):
        out.append("fx_if_rate_available")
    if "percent" in text or "unit: percent" in text or "(%)" in text:
        out.append("percent")
    if "sum all segments" in text or "sum all" in text:
        out.append("sum_segments")
    if "negative number for loss" in text:
        out.append("signed_loss")
    if "||" in text:
        out.append("multi_value_join")
    return out


def resolve_catalog(catalog: dict[str, dict[str, Any]], name: str) -> dict[str, Any]:
    folded = {re.sub(r"[^a-z0-9]+", "", key.lower()): spec for key, spec in catalog.items()}
    hit = folded.get(re.sub(r"[^a-z0-9]+", "", name.lower()))
    if hit is None:
        raise SystemExit(f"official schema missing description for {name}")
    return hit


def compile_specs(
    catalog: dict[str, dict[str, Any]],
    records: dict[str, AttributeRecord],
) -> dict[str, AttrSpec]:
    specs: dict[str, AttrSpec] = {}
    for name, rec in records.items():
        info = resolve_catalog(catalog, name)
        description = str(info.get("description") or "").strip()
        if not description:
            raise SystemExit(f"official schema description empty for {name}")
        domain = parse_schema_domain(description)
        norms = parse_normalization(description)
        usage = str(info.get("usage") or "")
        value_type = str(info.get("value_type") or rec.sql_type).lower()
        dtype = "numeric" if value_type in {"int", "integer", "float", "number", "real"} or rec.dtype == "numeric" else "string"
        task = "classification" if domain else "extractive"
        fx = re.search(r"convert to\s+([A-Za-z]{3,})", description, re.I)
        specs[name] = AttrSpec(
            name=name,
            official_description=description,
            sql_type=rec.sql_type,
            dtype=dtype,
            usage=usage,
            is_fixed=bool(info.get("is_fixed")),
            schema_domain=domain,
            roles=dict(rec.roles),
            n_expressions=len(rec.expressions),
            n_queries=rec.n_queries,
            allows_sum="sum_segments" in norms,
            requires_usd="fx_if_rate_available" in norms,
            target_currency=(fx.group(1).lower() if fx else None),
            unit_percent="percent" in norms,
            task_class=task,
            normalization=norms,
        )
    return specs


def specs_hash(specs: dict[str, AttrSpec]) -> str:
    payload = {name: specs[name].as_dict() for name in sorted(specs)}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
