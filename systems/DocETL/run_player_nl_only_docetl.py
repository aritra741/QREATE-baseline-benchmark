"""Create a sealed DocETL bundle from NL questions and opaque text only."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import shutil
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
for path in (ROOT / "systems" / "docetl-main", ROOT / "systems" / "WDIRS", ROOT):
    sys.path.insert(0, str(path))

logger = logging.getLogger(__name__)
FORBIDDEN_PARTS = {
    "answers", "data", "evaluation", "ground_truth", "oracle", "reference",
}
AGGREGATES = {"count", "sum", "avg", "min", "max"}
OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "between", "in", "is_not_null"}
TYPES = {"string", "number"}
NULLS = {"", "null", "none", "unknown", "n/a", "na"}


@dataclass(frozen=True)
class SourceDocument:
    document_id: str
    text: str
    content_sha256: str


@dataclass(frozen=True)
class FilterPlan:
    field: str
    semantic_type: str
    operator: str
    value: str = ""
    upper_value: str = ""


@dataclass(frozen=True)
class QueryPlan:
    query_id: str
    text: str
    record_entity: str
    group_field: str
    group_type: str
    group_alias: str
    aggregate: str
    measure_field: str
    measure_type: str
    measure_alias: str
    filters: Tuple[FilterPlan, ...] = ()
    having_operator: str = ""
    having_value: float = 0.0


class TokenTracker:
    def __init__(self) -> None:
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def add(self, prompt: int, completion: int) -> None:
        self.prompt_tokens += max(0, int(prompt))
        self.completion_tokens += max(0, int(completion))


def _usage(response: Any) -> Optional[Tuple[int, int]]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    get = usage.get if isinstance(usage, Mapping) else lambda key: getattr(usage, key, None)
    prompt, completion = get("prompt_tokens"), get("completion_tokens")
    return None if prompt is None or completion is None else (int(prompt), int(completion))


def _patch_tokens(tracker: TokenTracker) -> None:
    from docetl.operations.utils.api import APIWrapper
    from token_counter import GLOBAL_COUNTER

    original = APIWrapper._call_llm_with_cache
    if getattr(original, "_nl_only_patch", False):
        return

    def wrapped(self, *args, **kwargs):  # noqa: ANN001
        response = original(self, *args, **kwargs)
        usage = _usage(response)
        if usage is None:
            raise RuntimeError("DocETL provider response omitted token usage")
        tracker.add(*usage)
        GLOBAL_COUNTER.record(
            input_tokens=usage[0], output_tokens=usage[1], operation="docetl_nl"
        )
        return response

    wrapped._nl_only_patch = True  # type: ignore[attr-defined]
    APIWrapper._call_llm_with_cache = wrapped


def _allowed(path: Path, kind: str) -> Path:
    resolved = path.expanduser().resolve()
    bad = sorted(part for part in resolved.parts if part.lower() in FORBIDDEN_PARTS)
    if bad or resolved.suffix.lower() == ".csv":
        raise ValueError(f"{kind} path crosses forbidden synthesis namespace")
    return resolved


def load_nl_workload(path: Path) -> List[Dict[str, str]]:
    payload = json.loads(_allowed(path, "NL workload").read_text())
    rows = payload.get("queries", []) if isinstance(payload, Mapping) else payload
    if not isinstance(rows, list):
        raise ValueError("NL workload must be an array")
    forbidden = {
        "answer", "expected", "expected_answer", "gold", "oracle",
        "reference_sql", "sql", "sql_query",
    }
    output = []
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError("NL workload rows must be objects")
        leaks = sorted(str(key) for key in row if str(key).lower() in forbidden)
        if leaks:
            raise ValueError("NL-only workload contains forbidden fields: " + ", ".join(leaks))
        query_id = str(row.get("query_id", f"q{index}")).strip()
        text = str(row.get("text") or row.get("nl_query") or "").strip()
        if not query_id or not text:
            raise ValueError(f"invalid NL workload row {index}")
        output.append({"query_id": query_id, "text": text})
    if not output or len({row["query_id"] for row in output}) != len(output):
        raise ValueError("empty workload or duplicate query IDs")
    return output


def load_opaque_documents(root: Path) -> List[SourceDocument]:
    payloads = []
    for path in _allowed(root, "source corpus").glob("**/*.txt"):
        text = path.read_text(encoding="utf-8", errors="replace")
        payloads.append((hashlib.sha256(text.encode()).hexdigest(), text))
    occurrences: Dict[str, int] = {}
    output = []
    for digest, text in sorted(payloads):
        occurrence = occurrences.get(digest, 0)
        occurrences[digest] = occurrence + 1
        output.append(SourceDocument(f"doc-{digest[:24]}-{occurrence}", text, digest))
    if not output:
        raise ValueError("source corpus has no text documents")
    return output


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str))
    temporary.replace(path)


def _run_map(
    name: str,
    rows: Sequence[Mapping[str, Any]],
    prompt: str,
    schema: Mapping[str, str],
    work_dir: Path,
    *,
    model: str,
    base_url: str,
    threads: int,
    timeout: int,
    retries: int,
) -> List[Dict[str, Any]]:
    from docetl.api import Dataset, MapOp, Pipeline, PipelineOutput, PipelineStep

    work_dir.mkdir(parents=True, exist_ok=True)
    output = work_dir / "pipeline_output.json"
    pipeline = Pipeline(
        name=name,
        datasets={"raw": Dataset(type="memory", path=[dict(row) for row in rows], source="local")},
        operations=[MapOp(
            name=name, type="map", prompt=prompt, output={"schema": dict(schema)},
            model=model, skip_on_error=True, timeout=timeout,
            max_retries_per_timeout=retries,
        )],
        steps=[PipelineStep(name=f"{name}_step", input="raw", operations=[name])],
        output=PipelineOutput(
            type="file", path=str(output),
            intermediate_dir=str(work_dir / "docetl_intermediate"),
        ),
        default_model=model,
        default_lm_api_base=base_url,
        default_embedding_api_base=base_url,
        bypass_cache=True,
    )
    previous = os.getcwd()
    try:
        os.chdir(work_dir)
        pipeline.run(max_threads=threads)
    finally:
        os.chdir(previous)
    if not output.is_file():
        raise RuntimeError(f"DocETL did not write {output}")
    result = json.loads(output.read_text())
    if not isinstance(result, list):
        raise RuntimeError("DocETL map output must be an array")
    return [dict(row) for row in result if isinstance(row, Mapping)]


def _symbol(value: Any) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")
    if value.endswith("ies") and len(value) > 4:
        return f"{value[:-3]}y"
    if value.endswith("s") and not value.endswith("ss") and len(value) > 3:
        return value[:-1]
    return value


def _filters(value: Any) -> Tuple[FilterPlan, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = []
    output = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, Mapping):
            continue
        field, operator = _symbol(row.get("field")), str(row.get("operator") or "").lower()
        semantic_type = str(row.get("semantic_type") or "string").lower()
        if field and operator in OPERATORS:
            output.append(FilterPlan(
                field, semantic_type if semantic_type in TYPES else "string", operator,
                str(row.get("value") or ""), str(row.get("upper_value") or ""),
            ))
    return tuple(output)


def validate_plan(row: Mapping[str, Any]) -> QueryPlan:
    aggregate = str(row.get("aggregate") or "").lower()
    if aggregate not in AGGREGATES:
        raise ValueError(f"unsupported aggregate: {aggregate}")
    query_id, text, entity = (
        str(row.get("query_id") or "").strip(),
        str(row.get("text") or "").strip(),
        _symbol(row.get("record_entity")),
    )
    if not query_id or not text or not entity:
        raise ValueError("incomplete independent plan")
    group_field = _symbol(row.get("group_field")) or "group"
    measure_field = _symbol(row.get("measure_field")) or "record"
    group_type = str(row.get("group_type") or "string").lower()
    measure_type = str(row.get("measure_type") or "number").lower()
    having = str(row.get("having_operator") or "").strip()
    if having not in {"", "=", "!=", ">", ">=", "<", "<="}:
        having = ""
    try:
        having_value = float(row.get("having_value") or 0)
    except (TypeError, ValueError):
        having_value = 0.0
    return QueryPlan(
        query_id, text, entity, group_field,
        group_type if group_type in TYPES else "string",
        _symbol(row.get("group_alias")) or group_field,
        aggregate, measure_field,
        measure_type if measure_type in TYPES else "number",
        _symbol(row.get("measure_alias")) or f"{aggregate}_{measure_field}",
        _filters(row.get("filters")), having, having_value,
    )


def infer_plans(queries: Sequence[Mapping[str, str]], work: Path, **runtime) -> List[QueryPlan]:
    prompt = """
Independently plan this analytical question using only its natural-language
text. Choose the primary record entity whose documents contribute one record,
one grouping field, and one COUNT/SUM/AVG/MIN/MAX aggregate. COUNT uses
measure_field record. Filters use =, !=, >, >=, <, <=, between, in, or
is_not_null. Filter values are strings; IN is comma-separated and BETWEEN uses
value plus upper_value. Types are string or number. HAVING is only a grouped
record-count restriction. Infer concise snake_case aliases. Do not assume a
database schema. Use 2026 only for an explicitly required date calculation.

Question: {{ input.text }}
""".strip()
    rows = _run_map(
        "plan_nl_query", queries, prompt, {
            "record_entity": "string", "group_field": "string",
            "group_type": "string", "group_alias": "string",
            "aggregate": "string", "measure_field": "string",
            "measure_type": "string", "measure_alias": "string",
            "filters": (
                "list[{field: string, semantic_type: string, operator: string, "
                "value: string, upper_value: string}]"
            ),
            "having_operator": "string", "having_value": "number",
        }, work, **runtime,
    )
    by_id = {str(row.get("query_id")): row for row in rows}
    missing = [query["query_id"] for query in queries if query["query_id"] not in by_id]
    if missing:
        raise RuntimeError(f"DocETL planner omitted queries: {missing}")
    return [validate_plan(by_id[query["query_id"]]) for query in queries]


def classify_documents(
    documents: Sequence[SourceDocument], entities: Sequence[str], work: Path, **runtime
) -> List[Dict[str, Any]]:
    labels = ", ".join(entities)
    prompt = f"""
Classify the primary subject using exactly one workload-derived label: {labels}.
Later related entities are not the primary subject. Return its identity and an
exact supporting quote. Return an empty label when unsupported.

Document: {{{{ input.text }}}}
""".strip()
    return _run_map(
        "classify_primary_subject",
        [{"document_id": doc.document_id, "text": doc.text} for doc in documents],
        prompt,
        {"document_entity": "string", "record_identity": "string", "evidence": "string"},
        work, **runtime,
    )


def route_documents(
    documents: Sequence[SourceDocument],
    classifications: Sequence[Mapping[str, Any]],
    entities: Sequence[str],
) -> Dict[str, List[SourceDocument]]:
    labels = {_symbol(entity): entity for entity in entities}
    by_id = {doc.document_id: doc for doc in documents}
    routes = {entity: [] for entity in entities}
    for row in classifications:
        doc, entity = by_id.get(str(row.get("document_id") or "")), labels.get(
            _symbol(row.get("document_entity"))
        )
        if doc is not None and entity is not None:
            routes[entity].append(doc)
    return routes


def extract_records(
    plan: QueryPlan, documents: Sequence[SourceDocument], work: Path, **runtime
) -> List[Dict[str, Any]]:
    if not documents:
        return []
    prompt = f"""
Extract one query-conditioned record using this independently generated plan:
{json.dumps(asdict(plan), indent=2)}

Set supported=true only when the document's primary subject is a
{plan.record_entity} and supports the group value. Return its identity. For
non-COUNT aggregates, measure_value must be the requested quantity, never a
nearby year or rank. For each filter i return has_filter_i and its raw value.
Unknown values set the corresponding has flag false. Evidence must be an exact
short quote. Use 2026 only when the question requires a date calculation.

Document: {{{{ input.text }}}}
""".strip()
    schema = {
        "supported": "boolean", "record_identity": "string",
        "group_value": plan.group_type, "has_measure": "boolean",
        "measure_value": "number", "evidence": "string",
    }
    for index, item in enumerate(plan.filters):
        schema[f"has_filter_{index}"] = "boolean"
        schema[f"filter_{index}_value"] = item.semantic_type
    return _run_map(
        f"extract_{_symbol(plan.query_id)}",
        [{"document_id": doc.document_id, "text": doc.text} for doc in documents],
        prompt, schema, work, **runtime,
    )


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(str(value).strip().replace(",", ""))
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _text(value: Any) -> Optional[str]:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return None if value.casefold() in NULLS else value


def _typed(value: Any, kind: str) -> Any:
    return _number(value) if kind == "number" else _text(value)


def _compare(actual: Any, rule: FilterPlan) -> bool:
    actual = _typed(actual, rule.semantic_type)
    if rule.operator == "is_not_null":
        return actual is not None
    if actual is None:
        return False
    if rule.operator == "in":
        expected = [_typed(item, rule.semantic_type) for item in rule.value.split(",")]
        if isinstance(actual, str):
            return actual.casefold() in {
                str(item).casefold() for item in expected if item is not None
            }
        return actual in expected
    expected = _typed(rule.value, rule.semantic_type)
    if expected is None:
        return False
    if rule.operator == "between":
        upper = _typed(rule.upper_value, rule.semantic_type)
        return upper is not None and expected <= actual <= upper
    left, right = (
        (actual.casefold(), expected.casefold())
        if isinstance(actual, str) and isinstance(expected, str)
        else (actual, expected)
    )
    if rule.operator == "=":
        return left == right
    if rule.operator == "!=":
        return left != right
    if rule.operator == ">":
        return left > right
    if rule.operator == ">=":
        return left >= right
    if rule.operator == "<":
        return left < right
    return left <= right


def _having(count: int, operator: str, threshold: float) -> bool:
    if not operator:
        return True
    return {
        "=": count == threshold, "!=": count != threshold,
        ">": count > threshold, ">=": count >= threshold,
        "<": count < threshold, "<=": count <= threshold,
    }[operator]


def aggregate_records(plan: QueryPlan, records: Sequence[Mapping[str, Any]]) -> List[dict]:
    unique: Dict[str, Mapping[str, Any]] = {}
    for row in records:
        identity = _text(row.get("record_identity"))
        group = _typed(row.get("group_value"), plan.group_type)
        filters_pass = all(
            bool(row.get(f"has_filter_{index}"))
            and _compare(row.get(f"filter_{index}_value"), rule)
            for index, rule in enumerate(plan.filters)
        )
        if bool(row.get("supported")) and identity and group is not None and filters_pass:
            unique.setdefault(identity.casefold(), row)
    groups: Dict[Any, List[Mapping[str, Any]]] = {}
    for row in unique.values():
        groups.setdefault(_typed(row.get("group_value"), plan.group_type), []).append(row)
    output = []
    for group, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        if not _having(len(rows), plan.having_operator, plan.having_value):
            continue
        if plan.aggregate == "count":
            value: Any = len(rows)
        else:
            values = [
                _number(row.get("measure_value"))
                for row in rows if bool(row.get("has_measure"))
            ]
            values = [item for item in values if item is not None]
            if not values:
                value = None
            elif plan.aggregate == "sum":
                value = sum(values)
            elif plan.aggregate == "avg":
                value = statistics.mean(values)
            elif plan.aggregate == "min":
                value = min(values)
            else:
                value = max(values)
        if isinstance(group, float) and group.is_integer():
            group = int(group)
        if (
            isinstance(value, float) and value.is_integer()
            and plan.aggregate != "avg"
        ):
            value = int(value)
        output.append({plan.group_alias: group, plan.measure_alias: value})
    return output


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def seal_bundle(
    bundle: Path,
    *,
    queries: Sequence[Mapping[str, str]],
    plans: Sequence[QueryPlan],
    routing: Mapping[str, Sequence[str]],
    evidence: Mapping[str, Sequence[Mapping[str, Any]]],
    results: Mapping[str, Sequence[Mapping[str, Any]]],
    tracker: TokenTracker,
    model: str,
    corpus_fingerprint: str,
) -> Path:
    if bundle.exists() and any(bundle.iterdir()):
        raise FileExistsError(bundle)
    bundle.mkdir(parents=True, exist_ok=True)
    _write_json(bundle / "plans.json", [asdict(plan) for plan in plans])
    _write_json(bundle / "routing.json", routing)
    for query_id, rows in evidence.items():
        _write_json(bundle / "evidence" / f"{query_id}.json", rows)
    for query_id, rows in results.items():
        _write_json(bundle / "query_tables" / f"{query_id}.json", rows)
    tokens = {
        "prompt_tokens": tracker.prompt_tokens,
        "completion_tokens": tracker.completion_tokens,
        "total_tokens": tracker.prompt_tokens + tracker.completion_tokens,
    }
    _write_json(bundle / "token_ledger.json", tokens)
    artifacts = {
        str(path.relative_to(bundle)): _sha(path)
        for path in sorted(bundle.rglob("*")) if path.is_file()
    }
    by_id = {plan.query_id: plan for plan in plans}
    manifest = {
        "version": 1, "method": "docetl_independent_nl", "model": model,
        "corpus_fingerprint": corpus_fingerprint,
        "construction_tokens": tokens["total_tokens"], "artifacts": artifacts,
        "queries": [{
            "query_id": query["query_id"],
            "natural_language_query": query["text"],
            "record_entity": by_id[query["query_id"]].record_entity,
            "result_path": f"query_tables/{query['query_id']}.json",
            "evidence_path": f"evidence/{query['query_id']}.json",
        } for query in queries],
    }
    _write_json(bundle / "manifest.json", manifest)
    (bundle / "SEALED").write_text(_sha(bundle / "manifest.json") + "\n")
    return bundle / "manifest.json"


def main() -> int:
    from token_counter import ensure_precise_tokenizer_ready

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="qwen2.5:7b-instruct")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--fresh", action="store_true")
    args = parser.parse_args()

    output = args.out.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        if not args.fresh:
            raise FileExistsError(output)
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(output / "docetl_nl.log"), logging.StreamHandler()],
    )
    ensure_precise_tokenizer_ready()
    model = args.model if args.model.startswith("ollama/") else f"ollama/{args.model}"
    runtime = {
        "model": model, "base_url": args.ollama_base_url,
        "threads": args.threads, "timeout": args.timeout, "retries": args.retries,
    }
    tracker = TokenTracker()
    _patch_tokens(tracker)
    queries = load_nl_workload(args.workload)
    documents = load_opaque_documents(args.source)
    plans = infer_plans(queries, output / "work" / "planning", **runtime)
    entities = tuple(dict.fromkeys(plan.record_entity for plan in plans))
    classifications = classify_documents(
        documents, entities, output / "work" / "classification", **runtime
    )
    routes = route_documents(documents, classifications, entities)
    logger.info("Content-only routes: %s", {k: len(v) for k, v in routes.items()})
    evidence, results = {}, {}
    for index, plan in enumerate(plans, 1):
        logger.info("[%d/%d] %s", index, len(plans), plan.query_id)
        records = extract_records(
            plan, routes.get(plan.record_entity, ()),
            output / "work" / "queries" / plan.query_id, **runtime,
        )
        evidence[plan.query_id] = records
        results[plan.query_id] = aggregate_records(plan, records)
    fingerprint = hashlib.sha256(json.dumps(
        sorted(doc.content_sha256 for doc in documents)
    ).encode()).hexdigest()
    manifest = seal_bundle(
        output / "serving_bundle", queries=queries, plans=plans,
        routing={key: [doc.document_id for doc in value] for key, value in routes.items()},
        evidence=evidence, results=results, tracker=tracker, model=model,
        corpus_fingerprint=fingerprint,
    )
    logger.info("Sealed bundle: %s", manifest.parent)
    logger.info("Construction tokens: %d", tracker.prompt_tokens + tracker.completion_tokens)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
