"""End-to-end check (AUDIT: scores with gold): substitute a count column with synthesized-regex counts.

Takes the K regex candidates probe 2 synthesized for a column (gold-free), applies them to the full
text of every document, uses the per-document median over usable candidates as the value (the
incumbent read value is kept where no candidate is usable), writes a copy of the per-attribute
database with only that column replaced, and scores all queries. Rule fixed before scoring: adopt
only if the mean product over the INPUT queries that use the column increases AND more of those
queries improve than get worse.

    python -m quwarts.eval.router_count_substitute --corpus legal --column legal_basis_num
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sqlite3
import statistics
import sys

from quwarts.core.router.corpus_features import list_documents, read_document
from quwarts.core.router.registry import RESULTS, get_corpus
from quwarts.eval.router_count_probe2 import parse_json, regex_count
from quwarts.eval.router_execute_v3 import DATASET, score
from quwarts.eval.router_shared_read_run import subset, workload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--column", required=True)
    parser.add_argument("--probe", default="count_probe2")
    args = parser.parse_args(argv)
    spec = get_corpus(args.corpus)
    table = spec.tables[0].sql_name
    base_dir = RESULTS / "quwarts_router_v3" / spec.name / "shared_read_per_attribute"
    probe = RESULTS / "quwarts_router_v3" / spec.name / args.probe
    candidates = []
    for line in (probe / "calls.jsonl").read_text().splitlines():
        rec = json.loads(line)
        if rec["key"][0] == "synth" and rec["key"][1] == args.column:
            pats = (parse_json(rec["response"]) or {}).get("patterns")
            if isinstance(pats, list):
                candidates.append([p for p in pats if isinstance(p, str)])
    out = RESULTS / "quwarts_router_v3" / spec.name / f"substitute_{args.column}_{args.probe}"
    out.mkdir(parents=True, exist_ok=True)
    db = out / "read_first.db"
    shutil.copyfile(base_dir / "read_first.db", db)

    values: dict[str, str | None] = {}
    for path in list_documents(spec.table(table)):
        text = read_document(path)
        counts = [c for c in (regex_count(p, text) for p in candidates) if c is not None]
        values[path.name] = str(int(statistics.median(counts))) if counts else None
    conn = sqlite3.connect(db)
    kept = 0
    for doc_id, value in values.items():
        if value is None:
            kept += 1
            continue
        conn.execute(f'UPDATE "{table}" SET "{args.column}" = ? WHERE doc_id = ?', (value, doc_id))
        conn.execute(f'UPDATE fact SET "{table}.{args.column}" = ? WHERE doc_id = ?', (value, doc_id))
    conn.commit()
    conn.close()
    (out / "values.json").write_text(json.dumps({"candidates": candidates, "values": values, "kept_incumbent": kept}, indent=2))

    # Gold is read only below.
    train, test = workload(spec.name)
    all_q = {r["query_id"]: r["sql"] for r in train + test}
    result = score(DATASET[spec.name], all_q, {q: str(db) for q in all_q}, db)
    base = {r["query_id"]: r for r in json.loads((base_dir / "score.json").read_text())["read_first"]["per_query"]}
    new = {r["query_id"]: r for r in result["per_query"]}
    uses = {q for q, s in all_q.items() if re.search(rf"\b{re.escape(args.column)}\b", s)}
    train_ids, test_ids = {r["query_id"] for r in train}, {r["query_id"] for r in test}

    def paired(ids: set[str]) -> dict:
        d = [new[q]["product"] - base[q]["product"] for q in sorted(ids)]
        return {"n": len(d), "base": sum(base[q]["product"] for q in ids) / len(ids),
                "new": sum(new[q]["product"] for q in ids) / len(ids),
                "better": sum(x > 1e-12 for x in d), "worse": sum(x < -1e-12 for x in d), "same": sum(abs(x) <= 1e-12 for x in d)}

    report = {
        "column": args.column, "candidates": len(candidates), "kept_incumbent": kept,
        "input_using_column": paired(uses & train_ids),
        "held_out_using_column": paired(uses & test_ids),
        "input_all": {"base": subset(list(base.values()), train_ids)["product"], "new": subset(result["per_query"], train_ids)["product"]},
        "held_out_all": {"base": subset(list(base.values()), test_ids)["product"], "new": subset(result["per_query"], test_ids)["product"]},
        "all80": {"base": subset(list(base.values()), set(all_q))["product"], "new": subset(result["per_query"], set(all_q))["product"]},
        "per_query_changes": {q: [round(base[q]["product"], 4), round(new[q]["product"], 4)] for q in sorted(uses)
                              if abs(new[q]["product"] - base[q]["product"]) > 1e-12},
    }
    iu = report["input_using_column"]
    report["adopt"] = bool(iu["new"] > iu["base"] and iu["better"] > iu["worse"])
    (out / "score.json").write_text(json.dumps({**report, "per_query": result["per_query"]}, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
