"""Deterministic-router additive extraction onto a frozen plumbing database."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quwarts.core.ledger import BudgetExhausted, BudgetedCaller
from quwarts.core.models import SourceDocument, Workload
from quwarts.core.provenance import document_stem, source_document_hash
from quwarts.core.retrieve_extract.bundle import pack_bundles
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.config import EXTRACT_SYSTEM, FROZEN
from quwarts.core.retrieve_extract.extract import can_afford, estimate_cost, run_extract
from quwarts.core.retrieve_extract.index import DocumentIndex, index_document
from quwarts.core.retrieve_extract.parse import STATUSES
from quwarts.core.retrieve_extract.repair import (
    FIRST_PASS_ACTIONS,
    REFINE_ACTIONS,
    apply_normalization_repair,
    decide_action,
)
from quwarts.core.retrieve_extract.retrieve import (
    Hit,
    adjacent_chunks,
    build_specs,
    concentration,
    pack_chunks,
    retrieve,
    section_map_from_hits,
)
from quwarts.core.retrieve_extract.route import decide_coverage_route, measure, prompt_and_schema_tokens
from quwarts.core.retrieve_extract.tokens import count_tokens

OPERATOR = "finan_additive"


@dataclass
class Job:
    doc_id: str
    entity_identity: str
    attributes: list[str]
    mode: str
    hits: list[Hit]
    priority: float
    phase: str = "first_pass"
    used: set[str] = field(default_factory=set)
    actions: list[str] = field(default_factory=list)
    malformed_retries: int = 0


class AdditiveExtractor:
    def __init__(
        self,
        *,
        corpus_id: str,
        documents: list[SourceDocument],
        workload: Workload,
        caller: BudgetedCaller,
        cache: VerifiedCache,
        catalog: dict[str, dict[str, Any]],
        ranked: list[dict[str, Any]],
        missing_by_entity: dict[str, set[str]],
        entity_by_doc: dict[str, str],
        configuration_hash: str,
        artifact_dir: Path,
    ):
        self.corpus_id = corpus_id
        self.documents = documents
        self.workload = workload
        self.caller = caller
        self.cache = cache
        self.catalog = catalog
        self.ranked = ranked
        self.missing_by_entity = {key: set(value) for key, value in missing_by_entity.items()}
        self.entity_by_doc = entity_by_doc
        self.configuration_hash = configuration_hash
        self.artifact_dir = Path(artifact_dir)
        self.lock = threading.Lock()
        self.indexes: dict[str, DocumentIndex] = {}
        self.docs = {doc.doc_id: doc for doc in documents}
        self.descriptions = {
            name: str((catalog.get(name.split(".")[-1].lower()) or {}).get("description") or "")
            for name in workload.requirements
        }
        self.dtypes = {name: req.dtype or "string" for name, req in workload.requirements.items()}
        self.priority = {row["attribute"]: float(row["priority"]) for row in ranked}
        self.schema_hash = hashlib.sha256(
            json.dumps({name: self.descriptions[name] for name in sorted(workload.requirements)}, sort_keys=True).encode()
        ).hexdigest()
        self.cells: dict[tuple[str, str], dict[str, Any]] = {}
        self.route_log: list[dict[str, Any]] = []
        self.extract_log: list[dict[str, Any]] = []
        self.repair_log: list[dict[str, Any]] = []
        self.mode_counts = Counter()
        self.mode_tokens = Counter()
        self.bundle_sizes: list[int] = []
        self.context_tokens: list[int] = []
        self.doc_tokens: list[int] = []
        self.status_by_attr: dict[str, Counter] = defaultdict(Counter)
        self.repair_counts = Counter()
        self.calls = Counter()
        self.n_chunks = 0
        self.n_retrieval = 0
        self.grounded = 0
        self.found_attempts = 0
        self.specs = build_specs(workload.requirements, workload, catalog, {})
        self._hit_cache: dict[tuple[str, str, tuple[str, ...]], list[Hit]] = {}

    def run(self) -> dict[tuple[str, str], dict[str, Any]]:
        self._index()
        first = self._first_pass_jobs()
        plan = [
            {
                "doc_id": job.doc_id,
                "entity_id": job.entity_identity,
                "attributes": job.attributes,
                "mode": job.mode,
                "priority": job.priority,
            }
            for job in first
        ]
        (self.artifact_dir / "first_pass_plan.json").write_text(json.dumps(plan, indent=2))
        print(f"{self.corpus_id} first_pass_jobs={len(first)} remaining={self.caller.ledger.remaining()}", flush=True)
        self._execute(first, "first_pass", FIRST_PASS_ACTIONS)
        refine = self._refine_jobs()
        print(f"{self.corpus_id} refine_jobs={len(refine)} remaining={self.caller.ledger.remaining()}", flush=True)
        self._execute(refine, "refine", REFINE_ACTIONS)
        return self.cells

    def _index(self) -> None:
        workers = min(int(FROZEN["workers"]), max(1, len(self.documents)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(index_document, doc.doc_id, doc.text): doc for doc in self.documents}
            for fut in as_completed(futs):
                index = fut.result()
                self.indexes[index.doc_id] = index
                self.doc_tokens.append(index.document_tokens)
                self.n_chunks += len(index.chunks)

    def _hits(self, index: DocumentIndex, name: str, exclude: set[str] | None = None) -> list[Hit]:
        key = (index.doc_id, name, tuple(sorted(exclude or ())))
        cached = self._hit_cache.get(key)
        if cached is not None:
            return cached
        with self.lock:
            self.n_retrieval += 1
        hits = retrieve(index, self.specs[name], exclude=exclude)
        self._hit_cache[key] = hits
        return hits

    def _route(self, index: DocumentIndex, attributes: list[str], hits: list[Hit]) -> dict[str, Any]:
        prompt_tokens = prompt_and_schema_tokens(attributes, self.descriptions)
        packed, _, _ = pack_chunks(hits, extra=adjacent_chunks(index, hits))
        packed_tokens = count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"])
        measurements = measure(index.document_tokens, prompt_tokens, packed_tokens)
        conc = concentration(hits)
        mode, reason = decide_coverage_route(measurements, conc)
        remaining = self.caller.ledger.remaining()
        decision = {
            "mode": mode,
            "feasible": ["whole_document"] if measurements.hard_fit and measurements.effective_fit else ["retrieved_chunks", "section_map"],
            "measurements": measurements.__dict__,
            "retrieval_concentration": conc,
            "estimated_cost": measurements.estimated_call_cost if mode == "whole_document" else packed_tokens + prompt_tokens + int(FROZEN["reserved_completion_tokens"]),
            "remaining_budget": remaining,
            "reason": reason,
            "doc_id": index.doc_id,
            "attributes": attributes,
            "router_tokens": 0,
        }
        with self.lock:
            self.route_log.append(decision)
        return decision

    def _context(self, job: Job, mode: str) -> tuple[str, list[str], list[str]]:
        index = self.indexes[job.doc_id]
        cap = min(
            int(FROZEN["retrieve_context_cap"]),
            max(256, int(FROZEN["effective_input_limit"]) - prompt_and_schema_tokens(job.attributes, self.descriptions)),
        )
        if mode == "whole_document":
            return index.text, [index.doc_id], [index.digest]
        if mode == "section_map":
            packed, source_ids, digests = section_map_from_hits(index, job.hits, cap=cap)
            job.used.update(source_ids)
            return packed, source_ids, digests
        extra = adjacent_chunks(index, job.hits)
        packed, source_ids, digests = pack_chunks(job.hits, cap=cap, extra=extra)
        job.used.update(source_ids)
        return packed, source_ids, digests

    def _job_cost(self, job: Job) -> int:
        index = self.indexes[job.doc_id]
        packed, _, _ = self._context(job, job.mode)
        tokens = count_tokens(packed) if packed and job.mode != "whole_document" else index.document_tokens
        return measure(
            index.document_tokens,
            prompt_and_schema_tokens(job.attributes, self.descriptions),
            tokens,
        ).estimated_call_cost

    def _make_job(self, doc_id: str, attributes: list[str], phase: str) -> Job | None:
        index = self.indexes[doc_id]
        ident = self.entity_by_doc[doc_id]
        hits_by_attr = {name: self._hits(index, name) for name in attributes}
        remaining = {name: name for name in attributes}
        modes = {}
        for name in attributes:
            decision = self._route(index, [name], hits_by_attr[name])
            modes[name] = decision["mode"]
        bundles = pack_bundles(list(remaining), modes, hits_by_attr, self.priority)
        if not bundles:
            return None
        bundle = bundles[0]
        decision = self._route(index, bundle.attributes, bundle.hits)
        job = Job(
            doc_id=doc_id,
            entity_identity=ident,
            attributes=list(bundle.attributes),
            mode=decision["mode"],
            hits=list(bundle.hits),
            priority=sum(self.priority.get(name, 0.0) for name in bundle.attributes),
            phase=phase,
        )
        self.bundle_sizes.append(len(job.attributes))
        return job

    def _first_pass_jobs(self) -> list[Job]:
        missing_ents: dict[str, list[str]] = defaultdict(list)
        doc_by_entity = {eid: doc_id for doc_id, eid in self.entity_by_doc.items()}
        attrs = [row["attribute"] for row in self.ranked]
        entities = [self.entity_by_doc[doc.doc_id] for doc in self.documents]
        for attr in attrs:
            for eid in entities:
                if attr in self.missing_by_entity.get(eid, set()):
                    missing_ents[attr].append(eid)
        scheduled: set[tuple[str, str]] = set()
        jobs: list[Job] = []
        reserve = int(self.caller.ledger.remaining() * float(FROZEN["first_pass_reserve_frac"]))
        available = self.caller.ledger.remaining() - reserve
        spent = 0
        depth = max((len(items) for items in missing_ents.values()), default=0)
        for index in range(depth):
            for attr in attrs:
                ents = missing_ents.get(attr) or []
                if index >= len(ents):
                    continue
                eid = ents[index]
                if (eid, attr) in scheduled:
                    continue
                doc_id = doc_by_entity[eid]
                mates = [attr]
                index_doc = self.indexes[doc_id]
                seed_hits = self._hits(index_doc, attr)
                seed_src = {hit.chunk.source_id for hit in seed_hits}
                for other in attrs:
                    if other == attr or (eid, other) in scheduled:
                        continue
                    if other not in self.missing_by_entity.get(eid, set()):
                        continue
                    other_hits = self._hits(index_doc, other)
                    other_src = {hit.chunk.source_id for hit in other_hits}
                    if seed_src and other_src and len(seed_src & other_src) / len(seed_src | other_src) >= float(FROZEN["bundle_jaccard"]):
                        mates.append(other)
                    if len(mates) >= int(FROZEN["max_bundle_size"]):
                        break
                job = self._make_job(doc_id, mates, "first_pass")
                if job is None:
                    continue
                cost = min(self._job_cost(job), int(FROZEN["retrieve_context_cap"]) + 400)
                if spent + cost > available:
                    continue
                jobs.append(job)
                spent += cost
                for name in job.attributes:
                    scheduled.add((eid, name))
        return jobs

    def _refine_jobs(self) -> list[Job]:
        jobs: list[Job] = []
        doc_by_entity = {eid: doc_id for doc_id, eid in self.entity_by_doc.items()}
        for row in self.ranked:
            attr = row["attribute"]
            for eid, missing in self.missing_by_entity.items():
                if attr not in missing:
                    continue
                item = self.cells.get((eid, attr))
                if item and item.get("status") == "found" and item.get("grounded"):
                    continue
                doc_id = doc_by_entity.get(eid)
                if not doc_id:
                    continue
                job = self._make_job(doc_id, [attr], "refine")
                if job:
                    jobs.append(job)
        reserve_left = 32
        selected = []
        spent = 0
        available = max(0, self.caller.ledger.remaining() - reserve_left)
        for job in jobs:
            cost = int(FROZEN["retrieve_context_cap"]) + 400
            if spent + cost > available:
                break
            selected.append(job)
            spent += cost
        return selected

    def _execute(self, jobs: list[Job], phase: str, allowed: tuple[str, ...]) -> None:
        if not jobs:
            return
        workers = min(int(FROZEN["workers"]), max(1, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(self._run_job, job, phase, allowed) for job in jobs]
            done = 0
            for fut in as_completed(futs):
                fut.result()
                done += 1
                if done == 1 or done % 25 == 0 or done == len(jobs):
                    print(
                        f"{self.corpus_id} {phase} {done}/{len(jobs)} spent={self.caller.ledger.spent}",
                        flush=True,
                    )

    def _run_job(self, job: Job, phase: str, allowed: tuple[str, ...]) -> None:
        try:
            self._run_job_inner(job, phase, allowed)
        except BudgetExhausted:
            return

    def _run_job_inner(self, job: Job, phase: str, allowed: tuple[str, ...]) -> None:
        doc = self.docs[job.doc_id]
        digest = source_document_hash(doc.doc_id, doc.text)
        context, source_ids, hashes = self._context(job, job.mode)
        if not context:
            return
        self.context_tokens.append(count_tokens(context) if job.mode != "whole_document" else self.indexes[job.doc_id].document_tokens)
        result = run_extract(
            self.caller,
            self.cache,
            corpus_id=self.corpus_id,
            source_document_hash=digest,
            entity_identity=job.entity_identity,
            attributes=job.attributes,
            mode=job.mode,
            context=context,
            source_ids=source_ids,
            context_hashes=hashes,
            schema_hash=self.schema_hash,
            descriptions=self.descriptions,
            dtypes=self.dtypes,
            purpose=phase,
            system=EXTRACT_SYSTEM,
            operator=OPERATOR,
            configuration_hash=self.configuration_hash,
        )
        if result is None:
            return
        with self.lock:
            self.calls["extractor"] += 0 if result.from_cache else 1
            self.mode_counts[job.mode] += 1
            self.mode_tokens[job.mode] += result.actual_tokens
            self.extract_log.append(
                {
                    "doc_id": job.doc_id,
                    "entity_id": job.entity_identity,
                    "attributes": job.attributes,
                    "mode": job.mode,
                    "phase": phase,
                    "from_cache": result.from_cache,
                    "errors": result.parsed.get("errors"),
                    "counts": result.parsed.get("counts"),
                    "raw": result.raw,
                }
            )
        self._accept(job.entity_identity, result.parsed)
        if result.parsed.get("ok"):
            return
        self._repair(job, result.parsed, digest, phase, allowed)

    def _repair(
        self,
        job: Job,
        parsed: dict[str, Any],
        digest: str,
        phase: str,
        allowed: tuple[str, ...],
    ) -> None:
        index = self.indexes[job.doc_id]
        packed, _, _ = pack_chunks(job.hits, extra=adjacent_chunks(index, job.hits))
        measurements = measure(
            index.document_tokens,
            prompt_and_schema_tokens(job.attributes, self.descriptions),
            count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"]),
        )
        attempts = 0
        current = parsed
        while attempts < int(FROZEN["max_repairs_per_job"]):
            decision = decide_action(
                self.caller,
                current,
                job.mode,
                measurements,
                job.actions,
                job.malformed_retries,
                attempts,
                allowed=allowed,
                planner=(phase != "first_pass"),
            )
            action = decision["action"]
            job.actions.append(action)
            with self.lock:
                self.repair_log.append(
                    {
                        "doc_id": job.doc_id,
                        "attributes": job.attributes,
                        "action": action,
                        "reason": decision["reason"],
                        "eligible": decision["eligible"],
                        "phase": phase,
                        "prompt": decision.get("prompt"),
                        "response": decision.get("response"),
                        "tokens": decision.get("tokens"),
                    }
                )
                self.repair_counts[f"{action}:attempted"] += 1
                if decision.get("tokens"):
                    self.calls["repair"] += 1
            if action == "abstain":
                self.repair_counts["abstain"] += 1
                return
            if action == "repair_normalization":
                items = current.get("items") or {}
                for name, item in items.items():
                    if item.get("norm_error") and item.get("raw_value"):
                        items[name] = apply_normalization_repair(item, self.dtypes.get(name, "string"))
                current["items"] = items
                self._accept(job.entity_identity, current)
                self.repair_counts["repair_normalization:accepted"] += 1
                return
            if action == "retry_single_attribute" and len(job.attributes) > 1:
                for name in job.attributes:
                    child = Job(
                        doc_id=job.doc_id,
                        entity_identity=job.entity_identity,
                        attributes=[name],
                        mode=job.mode,
                        hits=list(job.hits),
                        priority=self.priority.get(name, 0.0),
                        phase="repair",
                        used=set(job.used),
                    )
                    self._run_job_inner(child, "repair", allowed)
                self.repair_counts["retry_single_attribute:accepted"] += 1
                return
            if action == "retry_format":
                job.malformed_retries += 1
            elif action == "repair_missing_field":
                job.malformed_retries += 1
            elif action == "retrieve_alternate":
                alt: list[Hit] = []
                for name in job.attributes:
                    alt.extend(self._hits(index, name, exclude=job.used))
                job.hits = alt or job.hits
                job.mode = "retrieved_chunks"
            elif action == "expand_adjacent":
                extra = adjacent_chunks(index, job.hits)
                job.hits = list(job.hits) + [Hit(chunk=chunk, score=0.5) for chunk in extra]
                job.mode = "retrieved_chunks"
            context, source_ids, hashes = self._context(job, job.mode)
            if not context:
                self.repair_counts[f"{action}:failed"] += 1
                return
            result = run_extract(
                self.caller,
                self.cache,
                corpus_id=self.corpus_id,
                source_document_hash=digest,
                entity_identity=job.entity_identity,
                attributes=job.attributes,
                mode=job.mode,
                context=context,
                source_ids=source_ids,
                context_hashes=hashes,
                schema_hash=self.schema_hash,
                descriptions=self.descriptions,
                dtypes=self.dtypes,
                purpose="repair",
                operator=OPERATOR,
                configuration_hash=self.configuration_hash,
            )
            attempts += 1
            if result is None:
                self.repair_counts[f"{action}:failed"] += 1
                return
            self._accept(job.entity_identity, result.parsed)
            current = result.parsed
            if result.parsed.get("ok"):
                self.repair_counts[f"{action}:accepted"] += 1
                return
            self.repair_counts[f"{action}:failed"] += 1
            if result.parsed.get("malformed") and job.malformed_retries >= int(FROZEN["max_malformed_retry"]):
                return

    def _accept(self, entity_id: str, parsed: dict[str, Any]) -> None:
        rank = {"found": 3, "uncertain": 1, "not_found": 0, "malformed": -1}
        for name, item in (parsed.get("items") or {}).items():
            status = item.get("status")
            grounded = bool(item.get("grounded"))
            if status == "found":
                with self.lock:
                    self.found_attempts += 1
                    if grounded:
                        self.grounded += 1
            key = (entity_id, name)
            with self.lock:
                self.status_by_attr[name][status or "malformed"] += 1
                if "grounding_failure" in (item.get("errors") or []):
                    self.status_by_attr[name]["grounding_failure"] += 1
                current = self.cells.get(key)
                score = rank.get(status, -1)
                if status == "found" and not grounded:
                    score = 0
                cur = rank.get((current or {}).get("status"), -2)
                if current and current.get("status") == "found" and not current.get("grounded"):
                    cur = 0
                if current is None or score > cur:
                    self.cells[key] = item

    def report(self) -> dict[str, Any]:
        def _dist(values: list[int]) -> dict[str, Any]:
            if not values:
                return {"n": 0}
            ordered = sorted(values)
            return {
                "n": len(ordered),
                "min": ordered[0],
                "p50": ordered[len(ordered) // 2],
                "p90": ordered[int(len(ordered) * 0.9)],
                "max": ordered[-1],
                "mean": sum(ordered) / len(ordered),
            }

        by_purpose = Counter()
        for row in self.caller.ledger.records:
            by_purpose[row.purpose] += row.tokens
        covered: dict[str, set[str]] = defaultdict(set)
        docs_covered: dict[str, set[str]] = defaultdict(set)
        doc_by_entity = {eid: doc_id for doc_id, eid in self.entity_by_doc.items()}
        for (eid, attr), item in self.cells.items():
            if item.get("status") == "found" and item.get("grounded"):
                covered[attr].add(eid)
                if eid in doc_by_entity:
                    docs_covered[attr].add(doc_by_entity[eid])
        first_pass_tokens = int(by_purpose.get("first_pass") or 0)
        refine_tokens = int(by_purpose.get("refine") or 0) + int(by_purpose.get("repair") or 0)
        return {
            "documents": len(self.documents),
            "entities": len(self.entity_by_doc),
            "document_token_distribution": _dist(self.doc_tokens),
            "context_modes": {
                mode: {"count": int(self.mode_counts[mode]), "tokens": int(self.mode_tokens[mode])}
                for mode in ("whole_document", "retrieved_chunks", "section_map")
            },
            "chunks_indexed": self.n_chunks,
            "retrieval_queries": self.n_retrieval,
            "bundle_size_distribution": _dist(self.bundle_sizes),
            "context_token_distribution": _dist(self.context_tokens),
            "spend_by_purpose": dict(by_purpose),
            "first_pass_tokens": first_pass_tokens,
            "refinement_tokens": refine_tokens,
            "calls": dict(self.calls),
            "router_qwen_calls": 0,
            "cache": {
                "lookups": self.cache.lookups,
                "hits": self.cache.hits,
                "misses": self.cache.misses,
                "rejected": self.cache.rejected,
                "hit_rate": self.cache.hit_rate(),
            },
            "status_totals": dict(sum(self.status_by_attr.values(), Counter())),
            "status_by_attribute": {name: dict(counter) for name, counter in self.status_by_attr.items()},
            "repair": dict(self.repair_counts),
            "exact_span_grounding_rate": (self.grounded / self.found_attempts) if self.found_attempts else 0.0,
            "entities_covered_per_attribute": {name: len(ids) for name, ids in covered.items()},
            "documents_covered_per_attribute": {name: len(ids) for name, ids in docs_covered.items()},
        }
