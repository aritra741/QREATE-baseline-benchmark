"""Fresh Legal θ50 query-expert arm with a hard, budget-aware retry pool.

The prior preflight issued no model calls. This runner does not read that journal
or any stored DocETL completion as an answer. max_tokens=256 is the only request
change from the reconstructed DocETL map call.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined
from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI, RateLimitError

ROOT = Path("/Users/aritramazumder/Documents/UDA-Bench-main")
sys.path[:0] = [str(ROOT / "systems" / "WDIRS"), str(ROOT / "systems" / "docetl-main"), str(ROOT)]

from quwarts.core.llm.openrouter import OPENROUTER_URL, load_env_file
from quwarts.core.retrieve_extract.tokens import count_tokens

_ORIGINAL_OPEN = builtins.open

GATE = ROOT / "results" / "quwarts_legal_expert_set_cover"
SCHEDULE = ROOT / "results" / "quwarts_legal_expert_budget" / "schedule_frozen.json"
FROZEN = ROOT / "results" / "quwarts_legal_expert_fresh_theta50"
OUT = FROZEN / "arm"
EXTRACT_ROOT = ROOT / "results" / "docetl_legal_case80" / "docetl_pipelines"
PLUMBING = ROOT / "results" / "quwarts_legal_plumbing" / "artifacts" / "databases" / "legal_plumbing.db"
MANIFEST = ROOT / "results" / "docetl_legal_case80" / "query_manifest.json"
EXPECTED_SCHEDULE = "ac8c43797d845d270a4a43e3ae694e396d6c6bd12260036def5a643bca01794d"
EXPECTED_ROUTING = "90cf224fa3bac73f4fc28bf6925af06b647b795beee472db21a92f0dbd6ec2db"
PREFIX = [
    "legal_multiagg20:q18",
    "legal_multiagg20:q4",
    "legal_agg20:q11",
    "legal_agg20:q13",
    "legal_agg20:q14",
    "legal_agg20:q17",
]
THETA25 = 12_610_011
THETA50 = 25_220_022
MAX_TOKENS = 256
MAX_ATTEMPTS = 3
WORKERS = 4
DOCETL_PRODUCT = 0.12350932750098194
EXPECTED_PROMPT = {"theta25": 10_952_871, "theta50": 21_799_615}
EXPECTED_PRIMARY = {"theta25": 11_390_631, "theta50": 22_675_135}
API_MODEL = "qwen/qwen-2.5-7b-instruct"


def sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def measure_historical_completions() -> dict[str, Any]:
    framed_max = 0
    argument_max = 0
    rows = 0
    for qdir in sorted(path for path in EXTRACT_ROOT.iterdir() if path.is_dir()):
        payload = json.loads((qdir / "table_legal/docetl_intermediate/extract_step/extract_fields.json").read_text())
        for row in payload:
            args = {key: value for key, value in row.items() if key not in {"text", "doc_id"}}
            arguments = json.dumps(args, ensure_ascii=False, sort_keys=True)
            envelope = json.dumps({"name": "send_output", "arguments": arguments}, ensure_ascii=False)
            framed = "<tool_call>\n" + envelope + "\n</tool_call>"
            argument_max = max(argument_max, count_tokens(arguments))
            framed_max = max(framed_max, count_tokens(framed), count_tokens(envelope))
            rows += 1
    return {
        "valid_rows": rows,
        "max_argument_tokens": argument_max,
        "max_framed_tokens": framed_max,
        "cap": MAX_TOKENS,
        "fits": framed_max <= MAX_TOKENS and argument_max <= MAX_TOKENS,
    }


def stop(reason: str, payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"conclusion": "run invalid", "reason": reason, **payload, "model_calls": 0}
    (OUT / "stopped.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2), flush=True)
    raise SystemExit(0)


class Ledger:
    def __init__(self, ceiling: int, charged: int, unissued: int) -> None:
        self.ceiling = ceiling
        self.charged = charged
        self.unissued = unissued
        self.lock = threading.Lock()

    def pool(self) -> int:
        return self.ceiling - self.unissued - self.charged

    def start_primary(self, reserve: int) -> None:
        with self.lock:
            if self.unissued < reserve or self.charged + reserve > self.ceiling:
                raise RuntimeError("primary reservation exceeded the checkpoint ceiling")
            self.unissued -= reserve
            self.charged += reserve

    def start_retry(self, reserve: int) -> bool:
        with self.lock:
            if self.pool() < reserve:
                return False
            self.charged += reserve
            return True

    def reconcile(self, reserved: int, actual: int) -> None:
        with self.lock:
            delta = actual - reserved
            if self.charged + delta > self.ceiling:
                raise RuntimeError(
                    f"reconciled usage {actual} exceeds the checkpoint ceiling from reserve {reserved}"
                )
            self.charged += delta


class Journal:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lines = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.lines.append(json.loads(line))

    def append(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.lines.append(row)
            with self.path.open("a") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                handle.flush()
                os.fsync(handle.fileno())

    def attempts(self, key: tuple[str, str]) -> list[dict[str, Any]]:
        with self.lock:
            return [row for row in self.lines if (row["query_id"], row["doc_id"]) == key]

    def charged(self) -> int:
        return sum(int(row["charged"]) for row in self.lines)


def classify(exc: Exception) -> str:
    status = getattr(exc, "status_code", None)
    if isinstance(exc, (APITimeoutError, TimeoutError)) or "timeout" in str(exc).lower():
        return "timeout"
    if isinstance(exc, RateLimitError) or status == 429:
        return "rate_limit"
    if isinstance(exc, APIConnectionError):
        return "connection"
    if status is not None and 500 <= int(status) <= 599:
        return "http_5xx"
    return "other"


def normalize(arguments: dict[str, Any], schema: dict[str, str]) -> dict[str, Any] | None:
    if not isinstance(arguments, dict):
        return None
    output: dict[str, Any] = {}
    for name, kind in schema.items():
        if name not in arguments:
            return None
        value = arguments[name]
        if kind == "number":
            if isinstance(value, bool) or value is None:
                return None
            if isinstance(value, str):
                text = value.strip().replace(",", "")
                if text == "":
                    return None
                try:
                    value = float(text) if "." in text else int(text)
                except ValueError:
                    return None
            if not isinstance(value, (int, float)):
                return None
            if value == -1:
                output[name] = None
            else:
                output[name] = int(value) if float(value).is_integer() else value
        else:
            if value is None:
                return None
            if not isinstance(value, str):
                value = str(value)
            output[name] = None if value == "" else value
    return output


def parse_response(response: Any, schema: dict[str, str]) -> tuple[dict[str, Any] | None, str]:
    message = response.choices[0].message
    calls = getattr(message, "tool_calls", None) or []
    raw = ""
    if not calls:
        return None, message.content or ""
    function = calls[0].function
    raw = function.arguments or ""
    if getattr(function, "name", "") != "send_output":
        return None, raw
    try:
        arguments = json.loads(raw)
    except json.JSONDecodeError:
        return None, raw
    return normalize(arguments, schema), raw


def usage_tokens(response: Any) -> tuple[int, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if prompt is None or completion is None:
        return None
    return int(prompt), int(completion)


def render_requests() -> tuple[list[dict[str, Any]], dict[str, int]]:
    from quwarts.eval.legal_expert_fresh_theta50 import _routing_manifest
    from quwarts.eval.legal_expert_set_cover import (
        MODEL,
        SYSTEM,
        USER_TEMPLATE,
        load_documents,
        tools_for,
        truncate_messages,
    )

    schedule = json.loads(SCHEDULE.read_text())
    body = {key: value for key, value in schedule.items() if key != "schedule_sha256"}
    if sha(body) != EXPECTED_SCHEDULE:
        stop("schedule hash mismatch", {"schedule_sha256": sha(body)})
    experts = {row["query_id"]: row for row in json.loads((GATE / "experts.json").read_text())}
    projection = json.loads((GATE / "projection.json").read_text())
    expected_tokens = {
        (row["query_id"], row["doc_id"]): int(row["prompt_tokens"])
        for row in projection["per_document"]
        if row["query_id"] in PREFIX
    }
    stored_requests = json.loads((FROZEN / "requests.json").read_text())
    stored = {(row["query_id"], row["doc_id"]): row for row in stored_requests}
    compatibility = json.loads((GATE / "compatibility.json").read_text())
    query_ids_by_obs = {row["observable_id"]: list(row["query_ids"]) for row in compatibility["observables"]}
    compatible: dict[str, list[dict[str, Any]]] = {}
    for row in compatibility["matrix"]:
        if row["query_id"] not in PREFIX:
            continue
        compatible[row["query_id"]] = [
            {**cell, "query_ids": query_ids_by_obs[cell["observable_id"]]}
            for cell in row["cells"]
            if cell["compatible"]
        ]
    manifest = _routing_manifest(experts, compatible)
    if sha(manifest) != EXPECTED_ROUTING or sha(json.loads((FROZEN / "routing_manifest.json").read_text())) != EXPECTED_ROUTING:
        stop("routing hash mismatch", {"routing_sha256": sha(manifest)})

    env = Environment(undefined=StrictUndefined)
    documents = load_documents()
    if len(documents) != 570:
        stop("document count drifted", {"documents": len(documents)})
    rendered = []
    mismatches = 0
    for qid in PREFIX:
        expert = experts[qid]
        template = env.from_string(expert["user_template"])
        expected_user = USER_TEMPLATE.format(
            table="legal",
            sql=expert["sql"],
            field_list="\n".join(f"- {name}" for name in expert["fields"]),
            numeric_guidance=", ".join(name for name in expert["fields"] if expert["output_schema"][name] == "number") or "none",
        )
        if expert["system_prompt"] != SYSTEM or expert["user_template"] != expected_user:
            stop("prompt template drifted", {"query_id": qid})
        tools, choice = tools_for(expert["output_schema"])
        tool_tokens = count_tokens(json.dumps(tools, ensure_ascii=False, sort_keys=True))
        choice_tokens = count_tokens(json.dumps(choice, sort_keys=True))
        for doc_id, text in documents:
            user = template.render(input={"text": text, "doc_id": doc_id})
            messages = [
                {"role": "system", "content": expert["system_prompt"]},
                {"role": "user", "content": user},
            ]
            truncated, info = truncate_messages(messages, expert["truncation"]["max_input_tokens"])
            prompt = (
                count_tokens(truncated[0]["content"])
                + count_tokens(truncated[1]["content"])
                + tool_tokens
                + choice_tokens
            )
            request = {
                "model": MODEL,
                "messages": truncated,
                "tools": tools,
                "tool_choice": choice,
                "temperature": None,
                "max_tokens": None,
            }
            digest = hashlib.sha256(
                json.dumps(request, ensure_ascii=False, sort_keys=True, default=str).encode()
            ).hexdigest()
            prior = stored.get((qid, doc_id))
            if expected_tokens.get((qid, doc_id)) != prompt or prior is None or prior["request_sha256"] != digest:
                mismatches += 1
            rendered.append(
                {
                    "query_id": qid,
                    "doc_id": doc_id,
                    "prompt_tokens": prompt,
                    "truncated": bool(info["truncated"]),
                    "request_sha256": digest,
                    "messages": truncated,
                    "tools": tools,
                    "tool_choice": choice,
                    "schema": expert["output_schema"],
                    "fields": list(expert["fields"]),
                }
            )
        print(f"rendered {qid} mismatches_so_far={mismatches}", flush=True)
    if mismatches:
        stop("rendered requests do not match the frozen request hashes", {"mismatches": mismatches})
    totals = {}
    for name, experts_in_checkpoint in (("theta25", PREFIX[:3]), ("theta50", PREFIX)):
        rows = [row for row in rendered if row["query_id"] in experts_in_checkpoint]
        prompt = sum(row["prompt_tokens"] for row in rows)
        primary = prompt + MAX_TOKENS * len(rows)
        if prompt != EXPECTED_PROMPT[name] or primary != EXPECTED_PRIMARY[name]:
            stop(
                "primary reservation does not match the required preflight",
                {"checkpoint": name, "prompt": prompt, "primary": primary},
            )
        totals[name] = prompt
    return rendered, totals


def final_status(attempts: list[dict[str, Any]]) -> str | None:
    if not attempts:
        return None
    return attempts[-1]["status"]


def issue_request(client: OpenAI, journal: Journal, ledger: Ledger, item: dict[str, Any]) -> str:
    key = (item["query_id"], item["doc_id"])
    done = journal.attempts(key)
    if final_status(done) in {"success", "terminal"}:
        return final_status(done) or "terminal"
    if done and done[-1]["status"] == "issued":
        issued_count = sum(1 for row in done if row["status"] == "issued")
        status = "terminal" if issued_count >= MAX_ATTEMPTS else "retry"
        journal.append(
            {
                "query_id": item["query_id"],
                "doc_id": item["doc_id"],
                "request_sha256": item["request_sha256"],
                "attempt": issued_count,
                "kind": done[-1]["kind"],
                "cause": "connection",
                "status": status,
                "reserved": done[-1]["reserved"],
                "charged": 0,
                "prompt_tokens": None,
                "completion_tokens": None,
                "error": "lost_attempt",
            }
        )
        if status == "terminal":
            return "terminal"
        done = journal.attempts(key)
    attempts_done = sum(1 for row in done if row["status"] == "issued")
    reserve = item["prompt_tokens"] + MAX_TOKENS
    while attempts_done < MAX_ATTEMPTS:
        attempt = attempts_done + 1
        if attempt == 1:
            ledger.start_primary(reserve)
            cause = "primary"
        else:
            if not ledger.start_retry(reserve):
                journal.append(
                    {
                        "query_id": item["query_id"],
                        "doc_id": item["doc_id"],
                        "request_sha256": item["request_sha256"],
                        "attempt": attempt,
                        "kind": "retry",
                        "cause": "retry_pool_exhausted",
                        "status": "terminal",
                        "reserved": 0,
                        "charged": 0,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                    }
                )
                return "terminal"
            cause = done[-1].get("cause") or "retry"
        journal.append(
            {
                "query_id": item["query_id"],
                "doc_id": item["doc_id"],
                "request_sha256": item["request_sha256"],
                "attempt": attempt,
                "kind": "primary" if attempt == 1 else "retry",
                "cause": cause,
                "status": "issued",
                "reserved": reserve,
                "charged": reserve,
                "prompt_tokens": None,
                "completion_tokens": None,
            }
        )
        try:
            response = client.chat.completions.create(
                model=API_MODEL,
                messages=item["messages"],
                tools=item["tools"],
                tool_choice=item["tool_choice"],
                max_tokens=MAX_TOKENS,
                timeout=420,
            )
        except (RateLimitError, APIStatusError, APITimeoutError, APIConnectionError, TimeoutError) as exc:
            kind = classify(exc)
            retryable = kind in {"timeout", "http_5xx", "rate_limit", "connection"}
            attempts_done += 1
            status = "retry" if retryable and attempts_done < MAX_ATTEMPTS else "terminal"
            journal.append(
                {
                    "query_id": item["query_id"],
                    "doc_id": item["doc_id"],
                    "request_sha256": item["request_sha256"],
                    "attempt": attempt,
                    "kind": "primary" if attempt == 1 else "retry",
                    "cause": kind,
                    "status": status,
                    "reserved": reserve,
                    "charged": 0,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "error": type(exc).__name__,
                }
            )
            if status == "terminal":
                return "terminal"
            time.sleep(2 * attempt)
            done = journal.attempts(key)
            continue
        usage = usage_tokens(response)
        if usage is None:
            prompt_tokens = None
            completion_tokens = None
            delta = 0
        else:
            prompt_tokens, completion_tokens = usage
            ledger.reconcile(reserve, prompt_tokens + completion_tokens)
            delta = prompt_tokens + completion_tokens - reserve
        parsed, raw = parse_response(response, item["schema"])
        attempts_done += 1
        if parsed is None:
            status = "retry" if attempts_done < MAX_ATTEMPTS else "terminal"
            journal.append(
                {
                    "query_id": item["query_id"],
                    "doc_id": item["doc_id"],
                    "request_sha256": item["request_sha256"],
                    "attempt": attempt,
                    "kind": "primary" if attempt == 1 else "retry",
                    "cause": "malformed",
                    "status": status,
                    "reserved": reserve,
                    "charged": delta,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "raw_arguments": raw,
                }
            )
            if status == "terminal":
                return "terminal"
            done = journal.attempts(key)
            continue
        journal.append(
            {
                "query_id": item["query_id"],
                "doc_id": item["doc_id"],
                "request_sha256": item["request_sha256"],
                "attempt": attempt,
                "kind": "primary" if attempt == 1 else "retry",
                "cause": cause,
                "status": "success",
                "reserved": reserve,
                "charged": delta,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "raw_arguments": raw,
                "output": parsed,
            }
        )
        return "success"
    return "terminal"


def outputs_from_journal(journal: Journal, experts: list[str]) -> dict[str, dict[str, dict[str, Any]]]:
    found: dict[str, dict[str, dict[str, Any]]] = {qid: {} for qid in experts}
    for row in journal.lines:
        if row["status"] == "success" and row["query_id"] in found:
            found[row["query_id"]][row["doc_id"]] = row["output"]
    return found


def expert_complete(journal: Journal, qid: str, docs: list[str]) -> bool:
    for doc_id in docs:
        if final_status(journal.attempts((qid, doc_id))) not in {"success", "terminal"}:
            return False
    return True


def execute_checkpoint(
    client: OpenAI,
    journal: Journal,
    rendered: list[dict[str, Any]],
    experts: list[str],
    ceiling: int,
) -> None:
    pending = []
    for item in rendered:
        if item["query_id"] not in experts:
            continue
        if final_status(journal.attempts((item["query_id"], item["doc_id"]))) in {"success", "terminal"}:
            continue
        pending.append(item)
    unissued = sum(item["prompt_tokens"] + MAX_TOKENS for item in pending if not journal.attempts((item["query_id"], item["doc_id"])))
    ledger = Ledger(ceiling, journal.charged(), unissued)
    if ledger.charged + ledger.unissued > ceiling:
        raise RuntimeError(
            f"checkpoint cannot reserve primaries: charged {ledger.charged} unissued {ledger.unissued} ceiling {ceiling}"
        )
    print(
        json.dumps(
            {
                "checkpoint_ceiling": ceiling,
                "charged": ledger.charged,
                "unissued_primary": ledger.unissued,
                "retry_pool": ledger.pool(),
                "pending": len(pending),
            }
        ),
        flush=True,
    )
    if not pending:
        return
    completed = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(issue_request, client, journal, ledger, item) for item in pending]
        for future in as_completed(futures):
            future.result()
            completed += 1
            if completed % 25 == 0 or completed == len(pending):
                print(
                    json.dumps(
                        {
                            "completed": completed,
                            "pending": len(pending),
                            "charged": ledger.charged,
                            "unissued_primary": ledger.unissued,
                            "retry_pool": ledger.pool(),
                        }
                    ),
                    flush=True,
                )


def _entities(conn: sqlite3.Connection) -> dict[str, str]:
    return dict(conn.execute('SELECT doc_id, "__entity_id" FROM legal').fetchall())


def _copy(dest: Path) -> sqlite3.Connection:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    shutil.copy(PLUMBING, dest)
    return sqlite3.connect(dest)


def _overlay(conn: sqlite3.Connection, fields: list[str], rows: dict[str, dict[str, Any]], write_null: bool) -> int:
    written = 0
    for doc_id, row in rows.items():
        assignments = []
        values: list[Any] = []
        for field in fields:
            if field not in row:
                continue
            value = row[field]
            if value is None and not write_null:
                continue
            assignments.append(f'"{field}" = ?')
            values.append(value)
        if not assignments:
            continue
        values.append(doc_id)
        written += conn.execute(
            f'UPDATE legal SET {", ".join(assignments)} WHERE doc_id = ?',
            values,
        ).rowcount
    return written


def _truth(expression: str, attribute: str, value: Any) -> str | None:
    conn = sqlite3.connect(":memory:")
    conn.execute(f'CREATE TABLE t ("{attribute}")')
    conn.execute("INSERT INTO t VALUES (?)", (value,))
    try:
        row = conn.execute(f"SELECT ({expression}) FROM t").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None or row[0] is None:
        return None
    return "TRUE" if int(row[0]) != 0 else "FALSE"


def materialize(name: str, journal: Journal, experts: list[str]) -> dict[str, Any]:
    from quwarts.core.observable_sidecar import TABLE, bag_hash, compile_observables, write_specs
    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates

    queries = json.loads(MANIFEST.read_text())
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    inventory = compile_observables(queries)
    obs_by_id = {item.observable_id: item for item in inventory.observables}
    manifest = json.loads((FROZEN / "routing_manifest.json").read_text())
    outputs = outputs_from_journal(journal, experts)
    expert_meta = {row["query_id"]: row for row in json.loads((GATE / "experts.json").read_text())}
    plumbing_before = file_sha(PLUMBING)

    def run_bags(paths: dict[str, Path]) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, str]]]:
        bags: dict[str, list[dict[str, Any]]] = {}
        failures = []
        for qid, sql in statements.items():
            rewritten = official_sql(sql, paths[qid], predicates, query_id=qid)
            conn = sqlite3.connect(f"file:{paths[qid]}?mode=ro", uri=True)
            try:
                cursor = conn.execute(rewritten)
                columns = [item[0] for item in cursor.description] if cursor.description else []
                bags[qid] = [dict(zip(columns, record)) for record in cursor.fetchall()]
            except sqlite3.Error as exc:
                failures.append({"query_id": qid, "error": str(exc)})
                bags[qid] = []
            finally:
                conn.close()
        return bags, failures

    plumbing_paths = {qid: PLUMBING for qid in statements}
    plumbing_bags, plumbing_failures = run_bags(plumbing_paths)
    if plumbing_failures:
        raise RuntimeError(f"plumbing execution failed: {plumbing_failures}")

    result: dict[str, Any] = {"policies": {}}
    for policy in ("same_attribute", "conservative"):
        checkpoint = OUT / "databases" / policy / name
        if checkpoint.exists():
            shutil.rmtree(checkpoint)
        paths: dict[str, Path] = {}
        direct_targets = {
            row["target_query"]
            for row in manifest["official"][name]
            if row["mode"] == "direct"
        }
        if policy == "same_attribute":
            shared = _copy(checkpoint / "shared.db")
            for row in manifest["official"][name]:
                if row["mode"] != "shared" or not row["source_expert"]:
                    continue
                _overlay(shared, [row["attribute"]], outputs.get(row["source_expert"], {}), False)
            shared.commit()
            shared.close()
            for qid in statements:
                if qid in direct_targets:
                    dest = checkpoint / f"direct_{qid.replace(':', '_')}.db"
                    conn = _copy(dest)
                    fields = [row["attribute"] for row in manifest["official"][name] if row["target_query"] == qid and row["mode"] == "direct"]
                    _overlay(conn, fields, outputs.get(qid, {}), True)
                    conn.commit()
                    conn.close()
                    paths[qid] = dest
                else:
                    paths[qid] = checkpoint / "shared.db"
        else:
            shared = _copy(checkpoint / "shared.db")
            write_specs(shared, inventory)
            entities = _entities(shared)
            filled: set[tuple[str, str]] = set()
            for row in manifest["ablation"][name]:
                if row["mode"] != "role_compatible":
                    continue
                key = (row["target_query"], row["observable_id"])
                if key in filled or row["target_query"] in direct_targets:
                    continue
                obs = obs_by_id[row["observable_id"]]
                source = outputs.get(row["source_expert"], {})
                for doc_id, values in source.items():
                    if obs.attribute not in values or values[obs.attribute] is None:
                        continue
                    entity = entities.get(doc_id)
                    if entity is None:
                        continue
                    raw = values[obs.attribute]
                    if obs.kind in {"presence", "predicate"}:
                        truth = _truth(obs.expression, obs.attribute, raw)
                        if truth is None:
                            continue
                        shared.execute(
                            f"INSERT OR REPLACE INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, ?, NULL, ?)",
                            [obs.observable_id, entity, truth, f"fresh:{row['source_expert']}"],
                        )
                    else:
                        shared.execute(
                            f"INSERT OR REPLACE INTO {TABLE} (observable_id, entity_id, resolved, sql_truth, value_text, provenance) VALUES (?, ?, 1, NULL, ?, ?)",
                            [obs.observable_id, entity, str(raw), f"fresh:{row['source_expert']}"],
                        )
                filled.add(key)
            shared.commit()
            shared.close()
            for qid in statements:
                if qid in direct_targets:
                    dest = checkpoint / f"direct_{qid.replace(':', '_')}.db"
                    conn = _copy(dest)
                    fields = expert_meta[qid]["fields"]
                    _overlay(conn, fields, outputs.get(qid, {}), True)
                    conn.commit()
                    conn.close()
                    paths[qid] = dest
                else:
                    paths[qid] = checkpoint / "shared.db"
        bags, failures = run_bags(paths)
        bags_again, _ = run_bags(paths)
        if bags_again != bags:
            raise RuntimeError(f"{policy} {name} bags are not deterministic")
        payload = {
            "policy": policy,
            "experts": experts,
            "paths": {qid: str(path) for qid, path in paths.items()},
            "db_sha256": {qid: file_sha(path) for qid, path in sorted(paths.items())},
            "bag_sha256": bag_hash(bags),
            "empty_bags": [qid for qid, bag in bags.items() if not bag],
            "failures": failures,
            "changed_queries": [qid for qid, bag in bags.items() if bag != plumbing_bags[qid]],
            "gold_loaded": False,
        }
        (checkpoint / "bags_frozen.json").write_text(json.dumps(payload, indent=2))
        (checkpoint / "bags.json").write_text(json.dumps(bags, default=str))
        result["policies"][policy] = payload
        print(f"frozen {policy} {name} changed={len(payload['changed_queries'])} empty={len(payload['empty_bags'])}", flush=True)
    if file_sha(PLUMBING) != plumbing_before:
        raise RuntimeError("plumbing database changed")
    result["plumbing_bag_sha256"] = bag_hash(plumbing_bags)
    result["gold_loaded"] = False
    return result


def checkpoint_stats(journal: Journal, rendered: list[dict[str, Any]], experts: list[str], ceiling: int) -> dict[str, Any]:
    rows = [row for row in journal.lines if row["query_id"] in experts]
    by_request: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        by_request.setdefault((row["query_id"], row["doc_id"]), []).append(row)
    primary = 0
    retries: dict[str, int] = {}
    terminal = 0
    worst_case = 0
    actual_prompt = 0
    actual_completion = 0
    reserved = 0
    missing_usage = 0
    for attempts in by_request.values():
        issued = [row for row in attempts if row["status"] == "issued"]
        primary += sum(1 for row in issued if row["kind"] == "primary")
        for row in issued:
            reserved += int(row["reserved"])
        for row in attempts:
            if row["kind"] == "retry" and row["status"] in {"success", "retry", "terminal"} and row.get("cause") != "retry_pool_exhausted":
                retries[row.get("cause") or "unknown"] = retries.get(row.get("cause") or "unknown", 0) + 1
            if row.get("prompt_tokens") is not None and row["status"] in {"success", "retry", "terminal"}:
                actual_prompt += int(row["prompt_tokens"])
                actual_completion += int(row["completion_tokens"] or 0)
            if row["status"] in {"retry", "terminal"} and row.get("cause") in {"timeout", "http_5xx", "rate_limit", "connection"}:
                missing_usage += 1
                worst_case += int(row["reserved"])
        if attempts and attempts[-1]["status"] == "terminal":
            terminal += 1
    successes = {}
    missing_rows = {}
    for qid in experts:
        docs = [item["doc_id"] for item in rendered if item["query_id"] == qid]
        success_docs = {doc for (query, doc), attempts in by_request.items() if query == qid and attempts[-1]["status"] == "success"}
        successes[qid] = len(success_docs)
        missing_rows[qid] = len(docs) - len(success_docs)
    charged = sum(int(row["charged"]) for row in rows)
    unissued = sum(
        item["prompt_tokens"] + MAX_TOKENS
        for item in rendered
        if item["query_id"] in experts and not any(
            line["status"] == "issued" for line in journal.attempts((item["query_id"], item["doc_id"]))
        )
    )
    return {
        "primary_attempts": primary,
        "retries_by_cause": retries,
        "terminal_failures": terminal,
        "charged_worst_case_failures": worst_case,
        "missing_usage_attempts": missing_usage,
        "actual_prompt_tokens": actual_prompt,
        "actual_completion_tokens": actual_completion,
        "reserved_attempt_tokens": reserved,
        "reconciled_spend": charged,
        "unused_retry_pool": ceiling - unissued - charged,
        "experts_completed": [qid for qid in experts if expert_complete(journal, qid, [item["doc_id"] for item in rendered if item["query_id"] == qid])],
        "missing_document_rows": missing_rows,
        "successful_documents": successes,
        "request_hashes": {
            qid: hashlib.sha256(
                "".join(
                    item["request_sha256"]
                    for item in rendered
                    if item["query_id"] == qid
                ).encode()
            ).hexdigest()
            for qid in experts
        },
    }


def score_frozen(frozen: dict[str, Any]) -> dict[str, Any]:
    builtins.open = _ORIGINAL_OPEN
    from diagnostics.run_config_grid import load_ground_truth
    from quwarts.core.pipeline import official_sql
    from quwarts.core.signature import audit_workload, enumerate_predicates
    from quwarts.core.signature_realize import live_predicates
    from quwarts.eval.legal_coverage_transfer import score_db
    from quwarts.experiments.repair_art import mean_cell_f1_20, mean_per_query_product
    from quwarts.experiments.synthesize_case80 import gold_name, queries_for, score_with_rewrites

    queries = json.loads(MANIFEST.read_text())
    statements = {row["query_id"]: row["sql"] for row in queries}
    audit = audit_workload(queries)
    predicates = live_predicates(enumerate_predicates(audit.occurrences, audit.signature_eligible))
    gold = load_ground_truth(gold_name("Legal"))
    full = {row["query_id"]: row for row in queries_for("Legal")}
    scored: dict[str, Any] = {}
    for name, checkpoint in frozen["checkpoints"].items():
        scored[name] = {}
        for policy, payload in checkpoint["policies"].items():
            rewrites = {}
            for qid, sql in statements.items():
                path = payload["paths"][qid]
                rewrites[qid] = {"sql": official_sql(sql, path, predicates, query_id=qid), "sqlite_path": path}
            rows = [
                {"query_id": qid, "sql": sql, "pack": (full.get(qid) or {}).get("pack")}
                for qid, sql in statements.items()
            ]
            report = score_with_rewrites(rows, rewrites, PLUMBING, gold, "Legal")
            product = mean_per_query_product(report)
            scored[name][policy] = {
                "f2": float(report.get("mean_structure_f2") or 0.0),
                "f1": mean_cell_f1_20(report),
                "product": product,
                "beats_docetl": product > DOCETL_PRODUCT,
                "per_query": [
                    {
                        "query_id": row["query_id"],
                        "structure_f2": row.get("structure_f2"),
                        "cell_f1_20": row.get("cell_f1_20"),
                        "product": float(row.get("structure_f2") or 0.0) * float(row.get("cell_f1_20") or 0.0),
                    }
                    for row in report.get("per_query") or []
                ],
            }
            print(f"scored {policy} {name} product={product}", flush=True)
    plumbing = score_db(PLUMBING, statements, predicates, list(statements), gold)
    return {
        "checkpoints": scored,
        "plumbing_product": plumbing["mean_per_query_product"],
        "docetl_product": DOCETL_PRODUCT,
    }


def conclude(scored: dict[str, Any], complete: bool) -> str:
    if not complete:
        return "budget-aware retries still prevent a complete prefix"
    sharing = scored["checkpoints"]
    if sharing["theta25"]["same_attribute"]["product"] > DOCETL_PRODUCT:
        return "same-attribute sharing beats DocETL at theta25"
    if sharing["theta50"]["same_attribute"]["product"] > DOCETL_PRODUCT:
        return "same-attribute sharing beats DocETL at theta50"
    if sharing["theta50"]["same_attribute"]["product"] < DOCETL_PRODUCT:
        return "fresh sampling does not reproduce the diagnostic win"
    return "theta50 remains below DocETL"


def write_report(stats: dict[str, Any], frozen: dict[str, Any], scored: dict[str, Any], conclusion: str, cap: dict[str, Any]) -> None:
    lines = [
        "# Fresh Legal query-expert arm",
        "",
        f"Conclusion: `{conclusion}`",
        "",
        "Same-attribute sharing is the official materialization. Conservative routing is the ablation.",
        "",
        f"DocETL product: {DOCETL_PRODUCT}",
        "",
        "## Request policy",
        "",
        f"- max_tokens={MAX_TOKENS}. DocETL left the completion cap unset. This is the only budget-control change.",
        f"- Historical valid Legal DocETL completions: {cap['valid_rows']} rows, maximum framed tool-call {cap['max_framed_tokens']} tokens.",
        "- Attempts: 1 primary + at most 2 retries.",
        "- Retryable: timeout, provider HTTP 5xx, rate limit, connection error, and a malformed successful response when the retry reservation fits.",
        "- Missing usage on an issued attempt is charged at the full reserved prompt + 256.",
        "- θ25 terminal failures stay terminal at θ50.",
        "",
        "## Checkpoints",
        "",
    ]
    for name in ("theta25", "theta50"):
        row = stats[name]
        sharing = scored["checkpoints"][name]["same_attribute"]
        conservative = scored["checkpoints"][name]["conservative"]
        lines.extend(
            [
                f"### {name}",
                "",
                f"- primary attempts: {row['primary_attempts']}",
                f"- retries by cause: `{json.dumps(row['retries_by_cause'], sort_keys=True)}`",
                f"- terminal failures: {row['terminal_failures']}",
                f"- charged worst-case failures: {row['charged_worst_case_failures']}",
                f"- actual prompt tokens: {row['actual_prompt_tokens']}",
                f"- actual completion tokens: {row['actual_completion_tokens']}",
                f"- reserved attempt tokens: {row['reserved_attempt_tokens']}",
                f"- reconciled spend: {row['reconciled_spend']}",
                f"- unused retry pool: {row['unused_retry_pool']}",
                f"- experts completed: {', '.join(row['experts_completed'])}",
                f"- missing document rows: `{json.dumps(row['missing_document_rows'], sort_keys=True)}`",
                f"- request hashes: `{json.dumps(row['request_hashes'], sort_keys=True)}`",
                f"- journal prefix: {frozen['journal_prefix']}",
                f"- same-attribute product: {sharing['product']} (F2 {sharing['f2']}, F1 {sharing['f1']})",
                f"- conservative product: {conservative['product']} (F2 {conservative['f2']}, F1 {conservative['f1']})",
                f"- database hashes: `{json.dumps(frozen['checkpoints'][name]['policies']['same_attribute']['db_sha256'], sort_keys=True)}`",
                f"- same-attribute bag hash: {frozen['checkpoints'][name]['policies']['same_attribute']['bag_sha256']}",
                f"- conservative bag hash: {frozen['checkpoints'][name]['policies']['conservative']['bag_sha256']}",
                "",
                "| query | same-attribute product | conservative product |",
                "| --- | ---: | ---: |",
            ]
        )
        conservative_by_query = {item["query_id"]: item["product"] for item in conservative["per_query"]}
        for item in sharing["per_query"]:
            lines.append(
                f"| {item['query_id']} | {item['product']} | {conservative_by_query.get(item['query_id'])} |"
            )
        lines.append("")
    (FROZEN / "REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    cap = measure_historical_completions()
    if not cap["fits"]:
        stop(
            "a valid historical completion exceeds 256 tokens",
            {"required_safe_cap": cap["max_framed_tokens"], **cap},
        )
    rendered, totals = render_requests()
    if os.environ.get("FRESH_ARM_PREFLIGHT_ONLY") == "1":
        print(json.dumps({"preflight_ok": True, "requests": len(rendered), "prompt": totals, "cap": cap}, indent=2), flush=True)
        return
    load_env_file(ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        stop("OPENROUTER_API_KEY is not set", cap)
    policy = {
        "max_tokens": MAX_TOKENS,
        "max_attempts": MAX_ATTEMPTS,
        "retryable": ["timeout", "http_5xx", "rate_limit", "connection", "malformed"],
        "malformed_policy": "retry the same request when an attempt remains and the retry pool can reserve prompt+256; no separate repair prompt",
        "missing_usage_charge": "prompt+256",
        "api_model": API_MODEL,
        "route": "openrouter/qwen/qwen-2.5-7b-instruct",
        "historical_completion_cap": cap,
        "primary_reservation": "prompt+256",
        "theta25_terminal_failures_remain_terminal": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "policy_frozen.json").write_text(json.dumps(policy, indent=2))
    journal = Journal(OUT / "journal.jsonl")
    if journal.lines and journal.lines[0].get("request_sha256") not in {row["request_sha256"] for row in rendered}:
        stop("existing journal does not belong to this frozen request set", {"journal_lines": len(journal.lines)})
    client = OpenAI(base_url=OPENROUTER_URL, api_key=api_key, timeout=420.0, max_retries=0)
    execute_checkpoint(client, journal, rendered, PREFIX[:3], THETA25)
    docs = {qid: [row["doc_id"] for row in rendered if row["query_id"] == qid] for qid in PREFIX}
    if not all(expert_complete(journal, qid, docs[qid]) for qid in PREFIX[:3]):
        frozen_fail = {
            "conclusion": "budget-aware retries still prevent a complete prefix",
            "theta25_complete": False,
            "gold_loaded": False,
        }
        (OUT / "frozen.json").write_text(json.dumps(frozen_fail, indent=2))
        print(json.dumps(frozen_fail), flush=True)
        return
    theta25_lines = [row for row in journal.lines if row["query_id"] in PREFIX[:3]]
    (OUT / "journal_theta25.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in theta25_lines))
    materialized_25 = materialize("theta25", journal, PREFIX[:3])
    (OUT / "checkpoint_theta25.json").write_text(json.dumps(materialized_25, indent=2, default=str))
    execute_checkpoint(client, journal, rendered, PREFIX[3:], THETA50)
    if not all(expert_complete(journal, qid, docs[qid]) for qid in PREFIX):
        frozen_fail = {
            "conclusion": "budget-aware retries still prevent a complete prefix",
            "theta25_complete": True,
            "theta50_complete": False,
            "gold_loaded": False,
        }
        (OUT / "frozen.json").write_text(json.dumps(frozen_fail, indent=2))
        print(json.dumps(frozen_fail), flush=True)
        return
    prefix = (OUT / "journal_theta25.jsonl").read_text()
    full = (OUT / "journal.jsonl").read_text()
    if not full.startswith(prefix):
        stop_payload = {"conclusion": "run invalid", "reason": "theta25 journal is not a prefix of theta50", "model_calls_already_issued": True}
        (OUT / "frozen.json").write_text(json.dumps(stop_payload, indent=2))
        print(json.dumps(stop_payload), flush=True)
        return
    materialized_50 = materialize("theta50", journal, PREFIX)
    stats = {
        "theta25": checkpoint_stats(journal, rendered, PREFIX[:3], THETA25),
        "theta50": checkpoint_stats(journal, rendered, PREFIX, THETA50),
    }
    frozen = {
        "schedule_sha256": EXPECTED_SCHEDULE,
        "routing_sha256": EXPECTED_ROUTING,
        "journal_sha256": file_sha(OUT / "journal.jsonl"),
        "journal_theta25_sha256": file_sha(OUT / "journal_theta25.jsonl"),
        "journal_prefix": True,
        "checkpoints": {"theta25": materialized_25, "theta50": materialized_50},
        "stats": stats,
        "gold_loaded": False,
        "policy": policy,
    }
    (OUT / "frozen.json").write_text(json.dumps(frozen, indent=2, default=str))
    scored = score_frozen(frozen)
    conclusion = conclude(scored, True)
    (OUT / "scores.json").write_text(json.dumps({"conclusion": conclusion, **scored}, indent=2))
    write_report(stats, frozen, scored, conclusion, cap)
    print(json.dumps({"conclusion": conclusion, "products": {
        name: {policy: row["product"] for policy, row in policies.items()}
        for name, policies in scored["checkpoints"].items()
    }}, indent=2), flush=True)


if __name__ == "__main__":
    main()
