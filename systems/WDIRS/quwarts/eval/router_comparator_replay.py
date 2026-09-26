"""Zero-token replay of a router probe journal with benchmark-consistent cell comparison.

Mirrors evaluation/comparators.py with the LLM comparator disabled (the default):
multi-valued cells are split on "||" and scored by lexical set F1, numbers must be
equal, strings compare case- and whitespace-insensitively. Reports, per attribute,
the expected cell-score loss of replacing a query-conditioned read with the shared
canonical read, the canonical self-noise, the number of informative pairs, and a
Wilson 95% interval on the share of pairs with loss > 0.5.

    python -m quwarts.eval.router_comparator_replay --corpus art
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

from quwarts.core.router.registry import RESULTS, get_corpus

_NULL = {"", "null", "none", "n/a", "na", "unknown"}


def is_null(value) -> bool:
    return value is None or str(value).strip().lower() in _NULL


def parts(value) -> list[str]:
    if isinstance(value, list):
        value = "||".join(map(str, value))
    return [p.strip().lower() for p in re.sub(r"\s+", " ", str(value)).split("||") if p.strip()]


def cell_f1(a, b, value_type: str) -> float:
    if is_null(a) and is_null(b):
        return 1.0
    if is_null(a) or is_null(b):
        return 0.0
    if value_type in ("int", "float"):
        try:
            return 1.0 if float(str(a).replace(",", "")) == float(str(b).replace(",", "")) else 0.0
        except ValueError:
            return 0.0
    pa, pb = parts(a), parts(b)
    if not pa or not pb:
        return 0.0
    matched = len(set(pa) & set(pb))
    p, r = matched / len(pa), matched / len(pb)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def wilson(k: int, n: int) -> tuple[float, float] | None:
    if n == 0:
        return None
    z = 1.96
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def fields(text: str) -> dict:
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        payload = json.loads(match.group(0)) if match else {}
    except json.JSONDecodeError:
        return {}
    return payload.get("fields", payload) if isinstance(payload, dict) else {}


def replay(corpus: str, journal: Path | None = None) -> dict:
    spec = get_corpus(corpus)
    journal = journal or RESULTS / "quwarts_router" / corpus / "probe" / "probe_journal.jsonl"
    types = {}
    for key, attrs in spec.benchmark_attribute_descriptions(purpose="scoring").items():
        table = next((t.sql_name for t in spec.tables if t.attributes_key == key), key)
        for name, record in attrs.items():
            types[(table, name)] = str(record.get("value_type", ""))
    by_doc: dict[tuple[str, str], dict[str, list]] = {}
    for line in journal.read_text().splitlines():
        row = json.loads(line)
        slot = by_doc.setdefault((row["table"], row["doc"]), {"C": [], "Q": []})
        slot["C" if row["kind"] == "canonical" else "Q"].append(fields(row["response"]))
    out = {}
    for (table, name), value_type in sorted(types.items()):
        noise, loss = [], []
        for (t, _doc), slot in by_doc.items():
            if t != table or len(slot["C"]) < 2 or name not in slot["C"][0]:
                continue
            c1, c2 = slot["C"][0].get(name), slot["C"][1].get(name)
            if not (is_null(c1) and is_null(c2)):
                noise.append(1 - cell_f1(c1, c2, value_type))
            for q in slot["Q"]:
                if name in q and not (is_null(c1) and is_null(q[name])):
                    loss.append(1 - cell_f1(c1, q[name], value_type))
        if not loss:
            continue
        out[f"{table}.{name}"] = {
            "value_type": value_type,
            "self_noise": sum(noise) / len(noise) if noise else 0.0,
            "share_loss": sum(loss) / len(loss),
            "n_pairs": len(loss),
            "ci_major_loss": wilson(sum(1 for x in loss if x > 0.5), len(loss)),
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", required=True)
    args = parser.parse_args()
    for name, row in replay(args.corpus).items():
        ci = row["ci_major_loss"]
        print(f"{name:34} {row['value_type']:10} noise={row['self_noise']:.2f} loss={row['share_loss']:.2f} "
              f"n={row['n_pairs']:<3} ci=({ci[0]:.2f}, {ci[1]:.2f})")


if __name__ == "__main__":
    main()
