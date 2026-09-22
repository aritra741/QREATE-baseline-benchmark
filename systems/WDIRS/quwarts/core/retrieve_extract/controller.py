"""First-pass coverage, routing, extraction, and bounded repair."""

from __future__ import annotations

import hashlib
import json
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from quwarts.core.amplify import attach_amplification
from quwarts.core.ledger import BudgetExhausted, BudgetedCaller, TokenLedger
from quwarts.core.models import EvidenceRecord, SourceDocument, Workload
from quwarts.core.provenance import entity_id, source_document_hash
from quwarts.core.retrieve_extract.bundle import Bundle, pack_bundles
from quwarts.core.retrieve_extract.cache import VerifiedCache
from quwarts.core.retrieve_extract.config import (
    EXPAND_SYSTEM,
    FROZEN,
    MODEL,
    PLANNER_SYSTEM,
    config_hash,
    prompt_hash,
)
from quwarts.core.retrieve_extract.extract import (
    can_afford,
    complete,
    estimate_cost,
    run_extract,
)
from quwarts.core.retrieve_extract.index import DocumentIndex, index_document
from quwarts.core.retrieve_extract.parse import STATUSES, extract_json
from quwarts.core.retrieve_extract.repair import apply_normalization_repair, decide_action
from quwarts.core.retrieve_extract.retrieve import (
    Hit,
    RetrievalSpec,
    build_specs,
    concentration,
    outline,
    pack_chunks,
    retrieve,
    sections_for,
)
from quwarts.core.retrieve_extract.route import (
    decide_deterministic,
    feasible_modes,
    is_borderline,
    measure,
    parse_planner,
    planner_prompt,
    prompt_and_schema_tokens,
)
from quwarts.core.retrieve_extract.tokens import count_tokens


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


class ExtractController:
    def __init__(
        self,
        *,
        corpus_id: str,
        documents: list[SourceDocument],
        workload: Workload,
        caller: BudgetedCaller,
        cache: VerifiedCache,
        catalog: dict[str, dict[str, Any]],
        artifact_dir: Path,
    ):
        self.corpus_id = corpus_id
        self.documents = documents
        self.workload = workload
        self.caller = caller
        self.cache = cache
        self.catalog = catalog
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.indexes: dict[str, DocumentIndex] = {}
        self.specs: dict[str, RetrievalSpec] = {}
        self.descriptions: dict[str, str] = {}
        self.dtypes: dict[str, str] = {}
        self.priority: dict[str, float] = {}
        self.schema_hash = ""
        self.cells: dict[tuple[str, str], dict[str, Any]] = {}
        self.route_log: list[dict[str, Any]] = []
        self.extract_log: list[dict[str, Any]] = []
        self.repair_log: list[dict[str, Any]] = []
        self.mode_tokens = Counter()
        self.mode_counts = Counter()
        self.mode_switches = Counter()
        self.switch_reasons = Counter()
        self.repair_counts = Counter()
        self.status_by_attr: dict[str, Counter] = defaultdict(Counter)
        self.bundle_sizes: list[int] = []
        self.context_tokens: list[int] = []
        self.doc_tokens: list[int] = []
        self.n_chunks = 0
        self.n_retrieval = 0
        self.n_expansion = 0
        self.grounded = 0
        self.found_attempts = 0
        self.calls = Counter()
        attach_amplification(workload)
        attributes = sorted(workload.requirements)
        for name in attributes:
            req = workload.requirements[name]
            bare = name.split(".")[-1]
            info = catalog.get(bare.lower()) or catalog.get(bare) or {}
            self.descriptions[name] = str(info.get("description") or "")
            self.dtypes[name] = req.dtype or "string"
            self.priority[name] = float(req.freq_weight or 1.0) * float(req.amp or 1.0)
        self.schema_hash = hashlib.sha256(
            json.dumps({name: self.descriptions[name] for name in attributes}, sort_keys=True).encode()
        ).hexdigest()

    def run(self) -> list[EvidenceRecord]:
        self._index()
        self._expand_and_specs()
        jobs = self._first_pass_jobs()
        self._execute(jobs, "first_pass")
        refine = self._refine_jobs()
        self._execute(refine, "refine")
        return self._records()

    def _index(self) -> None:
        workers = min(int(FROZEN["workers"]), max(1, len(self.documents)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(index_document, doc.doc_id, doc.text): doc for doc in self.documents}
            for fut in as_completed(futs):
                index = fut.result()
                self.indexes[index.doc_id] = index
                self.doc_tokens.append(index.document_tokens)
                self.n_chunks += len(index.chunks)

    def _expand_and_specs(self) -> None:
        expansions: dict[str, list[str]] = {}
        if self.caller.ledger.remaining() >= int(FROZEN["query_expansion_min_remaining"]):
            for name in sorted(self.workload.requirements):
                extra = self._expand(name)
                if extra:
                    expansions[name] = extra
                    self.n_expansion += 1
        self.specs = build_specs(self.workload.requirements, self.workload, self.catalog, expansions)

    def _expand(self, attribute: str) -> list[str]:
        description = self.descriptions.get(attribute, "")
        prompt = (
            "Propose up to "
            f"{int(FROZEN['query_expansion_max_terms'])} lexical retrieval terms "
            "for this attribute. No gold values, no dataset names.\n"
            f"attribute={attribute.split('.')[-1]}\n"
            f"description={description}\n"
            'Reply {"terms":["..."]}\n'
        )
        cost = estimate_cost(prompt)
        if not can_afford(self.caller.ledger, cost):
            return []
        spec_hash = hashlib.sha256(f"{attribute}\n{description}".encode()).hexdigest()
        manifest = {
            "corpus_id": self.corpus_id,
            "source_document_hash": spec_hash,
            "entity_identity": "attribute_spec",
            "attribute_bundle": [attribute],
            "context_mode": "query_expand",
            "context_hashes": [self.schema_hash],
            "schema_hash": self.schema_hash,
            "prompt_hash": prompt_hash(),
            "model_id": MODEL,
            "configuration_hash": config_hash(),
            "operator": "query_expand",
            "tier": FROZEN["tier"],
        }
        cached = self.cache.get(manifest)
        if cached is not None:
            return list((cached.get("record") or {}).get("terms") or [])
        try:
            raw, _used = complete(self.caller, prompt, "query_expand", EXPAND_SYSTEM)
        except BudgetExhausted:
            return []
        self.calls["planner"] += 1
        try:
            payload = extract_json(raw)
            terms = [str(item).lower() for item in payload.get("terms") or [] if item]
        except Exception:
            terms = []
        terms = list(dict.fromkeys(terms))[: int(FROZEN["query_expansion_max_terms"])]
        self.cache.put(manifest, {"terms": terms, "raw": raw})
        return terms

    def _hits(self, index: DocumentIndex, name: str, exclude: set[str] | None = None) -> list[Hit]:
        with self.lock:
            self.n_retrieval += 1
        return retrieve(index, self.specs[name], exclude=exclude)

    def _route(
        self,
        index: DocumentIndex,
        attributes: list[str],
        hits: list[Hit],
        remaining: int,
        allow_planner: bool = False,
    ) -> dict[str, Any]:
        prompt_tokens = prompt_and_schema_tokens(attributes, self.descriptions)
        packed, _, _ = pack_chunks(hits)
        packed_tokens = count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"])
        measurements = measure(index.document_tokens, prompt_tokens, packed_tokens)
        conc = concentration(hits)
        feasible = feasible_modes(measurements, remaining, conc)
        mode, reason = decide_deterministic(measurements, remaining, conc)
        planner_ask = planner_out = None
        if allow_planner and is_borderline(measurements, conc, remaining) and len(feasible) > 1:
            ask = planner_prompt(measurements, remaining, conc, feasible)
            cost = estimate_cost(ask)
            if can_afford(self.caller.ledger, cost):
                try:
                    planner_out, _used = complete(self.caller, ask, "context_router", PLANNER_SYSTEM)
                    planner_ask = ask
                    chosen, planner_reason = parse_planner(planner_out, feasible)
                    self.calls["planner"] += 1
                    if chosen:
                        mode, reason = chosen, planner_reason
                except BudgetExhausted:
                    pass
        if mode not in feasible:
            mode, reason = decide_deterministic(measurements, remaining, conc)
        decision = {
            "mode": mode,
            "feasible": feasible,
            "measurements": measurements.__dict__,
            "retrieval_concentration": conc,
            "estimated_cost": measurements.estimated_call_cost,
            "remaining_budget": remaining,
            "reason": reason,
            "router_prompt": planner_ask,
            "router_response": planner_out,
        }
        with self.lock:
            self.route_log.append(
                {k: v for k, v in decision.items() if k not in {"router_prompt", "router_response"}}
                | {"doc_id": index.doc_id, "attributes": attributes}
            )
        return decision

    def _first_pass_jobs(self) -> list[Job]:
        jobs_by_doc: dict[str, list[Job]] = {}
        attributes = sorted(self.workload.requirements, key=lambda name: (-self.priority[name], name))
        for doc in self.documents:
            index = self.indexes[doc.doc_id]
            digest = source_document_hash(doc.doc_id, doc.text)
            ident = entity_id(self.corpus_id, digest, 0)
            hits_by_attr = {name: self._hits(index, name) for name in attributes}
            remaining = self.caller.ledger.remaining()
            mode_by_attr = {}
            for name in attributes:
                decision = self._route(index, [name], hits_by_attr[name], remaining)
                mode_by_attr[name] = decision["mode"]
            bundles = pack_bundles(attributes, mode_by_attr, hits_by_attr, self.priority)
            jobs = []
            for bundle in bundles:
                decision = self._route(index, bundle.attributes, bundle.hits, remaining, allow_planner=True)
                mode = decision["mode"]
                if mode != bundle.mode:
                    self.mode_switches[f"{bundle.mode}->{mode}"] += 1
                    self.switch_reasons[decision["reason"]] += 1
                jobs.append(
                    Job(
                        doc_id=doc.doc_id,
                        entity_identity=ident,
                        attributes=list(bundle.attributes),
                        mode=mode,
                        hits=list(bundle.hits),
                        priority=bundle.priority,
                    )
                )
                self.bundle_sizes.append(len(bundle.attributes))
            jobs_by_doc[doc.doc_id] = jobs
        layered: list[Job] = []
        depth = max((len(items) for items in jobs_by_doc.values()), default=0)
        for rank in range(depth):
            for doc in self.documents:
                items = jobs_by_doc.get(doc.doc_id) or []
                if rank < len(items):
                    layered.append(items[rank])
        available = int(self.caller.ledger.remaining() * (1.0 - float(FROZEN["first_pass_reserve_frac"])))
        selected: list[Job] = []
        spent = 0
        for job in layered:
            index = self.indexes[job.doc_id]
            packed, _, _ = pack_chunks(job.hits)
            cost = measure(
                index.document_tokens,
                prompt_and_schema_tokens(job.attributes, self.descriptions),
                count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"]),
            ).estimated_call_cost
            if job.mode != "whole_document":
                cost = min(cost, int(FROZEN["retrieve_context_cap"]) + 400)
            if spent + cost > available:
                continue
            selected.append(job)
            spent += cost
        if selected:
            return selected
        # Budget cannot cover the layered plan; keep highest-priority singletons.
        fallback: list[Job] = []
        spent = 0
        for job in sorted(layered, key=lambda item: (-item.priority, item.doc_id)):
            cost = int(FROZEN["retrieve_context_cap"]) + 400
            if spent + cost > available:
                break
            job.attributes = job.attributes[:1]
            fallback.append(job)
            spent += cost
        return fallback

    def _context(self, job: Job, mode: str) -> tuple[str, list[str], list[str]]:
        index = self.indexes[job.doc_id]
        if mode == "whole_document":
            return index.text, [index.doc_id], [index.digest]
        if mode == "section_map":
            section_ids = []
            for hit in job.hits:
                for section in index.sections:
                    if int(section["start"]) <= hit.chunk.start < int(section["end"]):
                        section_ids.append(section["section_id"])
            if not section_ids:
                section_ids = [str(section["section_id"]) for section in index.sections[:3]]
            return sections_for(index, list(dict.fromkeys(section_ids)))
        packed, source_ids, digests = pack_chunks(job.hits)
        job.used.update(source_ids)
        return packed, source_ids, digests

    def _execute(self, jobs: list[Job], phase: str) -> None:
        if not jobs:
            return
        workers = min(int(FROZEN["workers"]), max(1, len(jobs)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(self._run_job, job, phase) for job in jobs]
            done = 0
            for fut in as_completed(futs):
                fut.result()
                done += 1
                if done == 1 or done % 25 == 0 or done == len(jobs):
                    print(
                        f"{self.corpus_id} {phase} {done}/{len(jobs)} spent={self.caller.ledger.spent}",
                        flush=True,
                    )

    def _run_job(self, job: Job, phase: str) -> None:
        try:
            self._run_job_inner(job, phase)
        except BudgetExhausted:
            return

    def _run_job_inner(self, job: Job, phase: str) -> None:
        index = self.indexes[job.doc_id]
        doc = next(item for item in self.documents if item.doc_id == job.doc_id)
        digest = source_document_hash(doc.doc_id, doc.text)
        mode = job.mode
        context, source_ids, hashes = self._context(job, mode)
        if not context:
            return
        self.context_tokens.append(count_tokens(context) if mode != "whole_document" else index.document_tokens)
        result = run_extract(
            self.caller,
            self.cache,
            corpus_id=self.corpus_id,
            source_document_hash=digest,
            entity_identity=job.entity_identity,
            attributes=job.attributes,
            mode=mode,
            context=context,
            source_ids=source_ids,
            context_hashes=hashes,
            schema_hash=self.schema_hash,
            descriptions=self.descriptions,
            dtypes=self.dtypes,
            purpose=phase,
        )
        if result is None:
            return
        with self.lock:
            self.calls["extractor"] += 0 if result.from_cache else 1
            self.mode_counts[mode] += 1
            self.mode_tokens[mode] += result.actual_tokens
            self.extract_log.append(
                {
                    "doc_id": job.doc_id,
                    "attributes": job.attributes,
                    "mode": mode,
                    "phase": phase,
                    "from_cache": result.from_cache,
                    "errors": result.parsed.get("errors"),
                    "counts": result.parsed.get("counts"),
                }
            )
        self._accept(job.doc_id, result.parsed)
        if result.parsed.get("ok"):
            return
        self._repair(job, result.parsed, mode, context, source_ids, hashes, digest, phase)

    def _repair(
        self,
        job: Job,
        parsed: dict[str, Any],
        mode: str,
        context: str,
        source_ids: list[str],
        hashes: list[str],
        digest: str,
        phase: str,
    ) -> None:
        index = self.indexes[job.doc_id]
        packed, _, _ = pack_chunks(job.hits)
        measurements = measure(
            index.document_tokens,
            prompt_and_schema_tokens(job.attributes, self.descriptions),
            count_tokens(packed) if packed else int(FROZEN["retrieve_context_cap"]),
        )
        attempts = 0
        current = parsed
        current_mode = mode
        current_context = context
        current_ids = source_ids
        current_hashes = hashes
        while attempts < int(FROZEN["max_repairs_per_job"]):
            decision = decide_action(
                self.caller,
                current,
                current_mode,
                measurements,
                job.actions,
                job.malformed_retries,
                attempts,
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
                    }
                )
                self.repair_counts[f"{action}:attempted"] += 1
                if decision["tokens"]:
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
                self._accept(job.doc_id, current)
                self.repair_counts["repair_normalization:accepted"] += 1
                return
            if action == "retry_single_attribute" and len(job.attributes) > 1:
                for name in job.attributes:
                    child = Job(
                        doc_id=job.doc_id,
                        entity_identity=job.entity_identity,
                        attributes=[name],
                        mode=current_mode,
                        hits=list(job.hits),
                        priority=self.priority.get(name, 0.0),
                        phase="repair",
                        used=set(job.used),
                    )
                    self._run_job_inner(child, "repair")
                self.repair_counts["retry_single_attribute:accepted"] += 1
                return
            next_mode = current_mode
            extra_hits = list(job.hits)
            if action == "retry_format":
                job.malformed_retries += 1
            elif action == "repair_missing_field":
                job.malformed_retries += 1
            elif action == "retrieve_alternate":
                alt: list[Hit] = []
                for name in job.attributes:
                    alt.extend(self._hits(index, name, exclude=job.used))
                extra_hits = alt or extra_hits
                next_mode = "retrieved_chunks"
            elif action == "expand_adjacent":
                by_id = index.chunk_map()
                added = []
                for hit in job.hits:
                    for neighbor in (hit.chunk.adjacent_prev, hit.chunk.adjacent_next):
                        chunk = by_id.get(neighbor or "")
                        if chunk:
                            added.append(Hit(chunk=chunk, score=hit.score * 0.5))
                extra_hits = list(job.hits) + added
                next_mode = "retrieved_chunks"
            elif action == "switch_to_whole_document":
                if not (measurements.hard_fit and measurements.effective_fit):
                    self.repair_counts[f"{action}:failed"] += 1
                    return
                next_mode = "whole_document"
            elif action == "switch_to_retrieved_chunks":
                next_mode = "retrieved_chunks"
            elif action == "build_section_map":
                next_mode = "section_map"
            if next_mode != current_mode:
                with self.lock:
                    self.mode_switches[f"{current_mode}->{next_mode}"] += 1
                    self.switch_reasons[action] += 1
            job.hits = extra_hits
            current_mode = next_mode
            current_context, current_ids, current_hashes = self._context(job, current_mode)
            if not current_context:
                self.repair_counts[f"{action}:failed"] += 1
                return
            result = run_extract(
                self.caller,
                self.cache,
                corpus_id=self.corpus_id,
                source_document_hash=digest,
                entity_identity=job.entity_identity,
                attributes=job.attributes,
                mode=current_mode,
                context=current_context,
                source_ids=current_ids,
                context_hashes=current_hashes,
                schema_hash=self.schema_hash,
                descriptions=self.descriptions,
                dtypes=self.dtypes,
                purpose="repair",
            )
            attempts += 1
            if result is None:
                self.repair_counts[f"{action}:failed"] += 1
                return
            self._accept(job.doc_id, result.parsed)
            current = result.parsed
            if result.parsed.get("ok"):
                self.repair_counts[f"{action}:accepted"] += 1
                return
            self.repair_counts[f"{action}:failed"] += 1
            if result.parsed.get("malformed") and job.malformed_retries >= int(FROZEN["max_malformed_retry"]):
                return

    def _accept(self, doc_id: str, parsed: dict[str, Any]) -> None:
        rank = {"found": 3, "uncertain": 1, "not_found": 0, "malformed": -1}
        for name, item in (parsed.get("items") or {}).items():
            status = item.get("status")
            grounded = bool(item.get("grounded"))
            if status == "found":
                with self.lock:
                    self.found_attempts += 1
                    if grounded:
                        self.grounded += 1
            key = (doc_id, name)
            with self.lock:
                self.status_by_attr[name][status or "malformed"] += 1
                if item.get("errors"):
                    for err in item["errors"]:
                        if err == "grounding_failure":
                            self.status_by_attr[name]["grounding_failure"] += 1
                current = self.cells.get(key)
                score = rank.get(status, -1)
                if status == "found" and not grounded:
                    score = 0
                cur_score = rank.get((current or {}).get("status"), -2)
                if current and current.get("status") == "found" and not current.get("grounded"):
                    cur_score = 0
                if current is None or score > cur_score:
                    self.cells[key] = item

    def _refine_jobs(self) -> list[Job]:
        unresolved: list[Job] = []
        for doc in self.documents:
            index = self.indexes[doc.doc_id]
            digest = source_document_hash(doc.doc_id, doc.text)
            ident = entity_id(self.corpus_id, digest, 0)
            for name in self.workload.requirements:
                item = self.cells.get((doc.doc_id, name))
                if item and item.get("status") == "found" and item.get("grounded"):
                    continue
                hits = self._hits(index, name)
                remaining = self.caller.ledger.remaining()
                decision = self._route(index, [name], hits, remaining)
                unresolved.append(
                    Job(
                        doc_id=doc.doc_id,
                        entity_identity=ident,
                        attributes=[name],
                        mode=decision["mode"],
                        hits=hits,
                        priority=self.priority[name],
                        phase="refine",
                    )
                )
        unresolved.sort(key=lambda job: (-job.priority, job.doc_id, job.attributes[0]))
        # Round-robin attributes so one field cannot consume leftover budget.
        by_attr: dict[str, list[Job]] = defaultdict(list)
        for job in unresolved:
            by_attr[job.attributes[0]].append(job)
        ordered: list[Job] = []
        while any(by_attr.values()):
            for name in sorted(by_attr, key=lambda item: (-self.priority[item], item)):
                if by_attr[name]:
                    ordered.append(by_attr[name].pop(0))
        available = self.caller.ledger.remaining()
        selected = []
        spent = 0
        for job in ordered:
            cost = int(FROZEN["retrieve_context_cap"]) + 400
            if spent + cost > available:
                break
            selected.append(job)
            spent += cost
        return selected

    def _records(self) -> list[EvidenceRecord]:
        records: list[EvidenceRecord] = []
        cfg = config_hash()
        for doc in self.documents:
            for name in self.workload.requirements:
                item = self.cells.get((doc.doc_id, name)) or {
                    "attribute": name,
                    "status": "not_found",
                    "raw_value": None,
                    "normalized_value": None,
                    "unit": None,
                    "period": None,
                    "evidence": [],
                    "errors": ["unattempted"],
                    "grounded": False,
                }
                status = item.get("status")
                grounded = bool(item.get("grounded"))
                surface = item.get("raw_value") if status == "found" and grounded else None
                parsed = item.get("normalized_value") if surface is not None else None
                if surface is not None and parsed is None and not item.get("norm_error"):
                    parsed = surface
                if status in {"not_found", "uncertain"} or not grounded:
                    surface = None
                    parsed = None
                key = hashlib.sha256(f"{self.corpus_id}|{doc.doc_id}|{name}|{cfg}".encode()).hexdigest()
                records.append(
                    EvidenceRecord(
                        key=key,
                        segment_id=(item.get("evidence") or [{}])[0].get("source_id") or doc.doc_id,
                        doc_id=doc.doc_id,
                        attribute=name,
                        surface_value=None if surface in (None, "") else str(surface),
                        parsed_value=parsed,
                        original_unit=item.get("unit"),
                        null_reason=None if surface is not None else (status if status in STATUSES else "unresolved"),
                        candidate_keys={
                            "status": str(status or "unresolved"),
                            "raw": "" if item.get("raw_value") is None else str(item.get("raw_value")),
                            "period": "" if item.get("period") is None else str(item.get("period")),
                            "errors": ",".join(item.get("errors") or []),
                            "evidence": json.dumps(item.get("evidence") or [], default=str),
                        },
                        confidence=1.0 if grounded else 0.0,
                        extractor_cfg_hash=cfg,
                        quality_tier="expensive",
                        stage=1,
                    )
                )
        return records

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
        return {
            "documents": len(self.documents),
            "entities": len(self.documents),
            "document_token_distribution": _dist(self.doc_tokens),
            "context_modes": {
                mode: {"count": int(self.mode_counts[mode]), "tokens": int(self.mode_tokens[mode])}
                for mode in ("whole_document", "retrieved_chunks", "section_map")
            },
            "mode_switches": dict(self.mode_switches),
            "mode_switch_reasons": dict(self.switch_reasons),
            "chunks_indexed": self.n_chunks,
            "retrieval_queries": self.n_retrieval,
            "query_expansions": self.n_expansion,
            "bundle_size_distribution": _dist(self.bundle_sizes),
            "context_token_distribution": _dist(self.context_tokens),
            "spend_by_purpose": dict(by_purpose),
            "calls": dict(self.calls),
            "cache": {
                "lookups": self.cache.lookups,
                "hits": self.cache.hits,
                "misses": self.cache.misses,
                "rejected": self.cache.rejected,
                "hit_rate": self.cache.hit_rate(),
            },
            "status_by_attribute": {name: dict(counter) for name, counter in self.status_by_attr.items()},
            "repair": dict(self.repair_counts),
            "exact_span_grounding_rate": (self.grounded / self.found_attempts) if self.found_attempts else 0.0,
            "found_attempts": self.found_attempts,
            "grounded_found": self.grounded,
        }
