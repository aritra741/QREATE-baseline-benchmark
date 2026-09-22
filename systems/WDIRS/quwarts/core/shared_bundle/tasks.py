"""Gold-free document–bundle tasks and complete entity packages."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from quwarts.core.shared_bundle.graph import Bundle
from quwarts.core.shared_bundle.inventory import AttributeRecord


def _null(value: Any) -> bool:
    return value is None or value == "" or value == -1 or value == "-1"


@dataclass
class CandidateTask:
    entity_id: str
    document_id: str
    bundle_signature: str
    attributes: list[str]
    missing_attributes: list[str]
    impact: int
    role_counts: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "document_id": self.document_id,
            "bundle_signature": self.bundle_signature,
            "attributes": list(self.attributes),
            "missing_attributes": list(self.missing_attributes),
            "impact": self.impact,
            "role_counts": dict(self.role_counts),
        }


@dataclass
class EntityPackage:
    entity_id: str
    document_id: str
    tasks: list[CandidateTask]
    impact: int
    reserved_cost: int = 0
    efficiency: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "document_id": self.document_id,
            "n_tasks": len(self.tasks),
            "bundle_signatures": [task.bundle_signature for task in self.tasks],
            "impact": self.impact,
            "reserved_cost": self.reserved_cost,
            "efficiency": self.efficiency,
        }


def task_impact(missing: Iterable[str], records: dict[str, AttributeRecord]) -> int:
    total = 0
    for name in missing:
        rec = records[name]
        total += int(rec.occurrence_count) * int(rec.n_queries)
    return total


def build_tasks(
    *,
    rows: list[dict[str, Any]],
    bundles: list[Bundle],
    records: dict[str, AttributeRecord],
    entity_key: str = "__entity_id",
    document_key: str = "__provenance_label",
) -> list[CandidateTask]:
    tasks: list[CandidateTask] = []
    for row in rows:
        entity_id = str(row.get(entity_key) or "")
        document_id = str(row.get(document_key) or row.get("doc_id") or "")
        if not entity_id or not document_id:
            continue
        for bundle in bundles:
            missing = [name for name in bundle.attributes if _null(row.get(name))]
            if not missing:
                continue
            roles: dict[str, int] = {}
            for name in missing:
                for role, count in records[name].roles.items():
                    roles[role] = roles.get(role, 0) + int(count)
            tasks.append(
                CandidateTask(
                    entity_id=entity_id,
                    document_id=document_id,
                    bundle_signature=bundle.signature,
                    attributes=list(bundle.attributes),
                    missing_attributes=missing,
                    impact=task_impact(missing, records),
                    role_counts=roles,
                )
            )
    tasks.sort(key=lambda item: (item.entity_id, item.bundle_signature))
    return tasks


def build_packages(tasks: list[CandidateTask]) -> list[EntityPackage]:
    by_entity: dict[str, list[CandidateTask]] = {}
    docs: dict[str, str] = {}
    for task in tasks:
        by_entity.setdefault(task.entity_id, []).append(task)
        docs[task.entity_id] = task.document_id
    packages = []
    for entity_id, group in by_entity.items():
        group = sorted(group, key=lambda item: item.bundle_signature)
        packages.append(
            EntityPackage(
                entity_id=entity_id,
                document_id=docs[entity_id],
                tasks=group,
                impact=sum(item.impact for item in group),
            )
        )
    packages.sort(key=lambda item: item.entity_id)
    return packages


def attach_reserved_costs(
    packages: list[EntityPackage],
    reserved_by_task: dict[tuple[str, str], int],
) -> list[EntityPackage]:
    for package in packages:
        package.reserved_cost = sum(
            int(reserved_by_task[(task.entity_id, task.bundle_signature)]) for task in package.tasks
        )
        package.efficiency = (package.impact / package.reserved_cost) if package.reserved_cost else 0.0
    return packages


def schedule_packages(
    packages: list[EntityPackage],
    *,
    ceiling: int,
) -> list[EntityPackage]:
    ranked = sorted(packages, key=lambda item: (-item.efficiency, item.entity_id))
    scheduled: list[EntityPackage] = []
    used = 0
    for package in ranked:
        if package.reserved_cost <= 0:
            continue
        if used + package.reserved_cost <= ceiling:
            scheduled.append(package)
            used += package.reserved_cost
    return scheduled


def prefix_within(scheduled: list[EntityPackage], ceiling: int) -> list[EntityPackage]:
    out: list[EntityPackage] = []
    used = 0
    for package in scheduled:
        if used + package.reserved_cost > ceiling:
            break
        out.append(package)
        used += package.reserved_cost
    return out


def tasks_hash(tasks: list[CandidateTask]) -> str:
    return hashlib.sha256(json.dumps([item.as_dict() for item in tasks], sort_keys=True).encode()).hexdigest()


def packages_hash(packages: list[EntityPackage]) -> str:
    return hashlib.sha256(json.dumps([item.as_dict() for item in packages], sort_keys=True).encode()).hexdigest()
