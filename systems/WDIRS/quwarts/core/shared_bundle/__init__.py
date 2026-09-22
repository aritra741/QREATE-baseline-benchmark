"""Shared-bundle full-window extraction: one entity–attribute value, many queries."""

from quwarts.core.shared_bundle.config import (
    COMPLETION_SAFETY,
    LEDGER_SAFETY_MARGIN,
    MAX_BUNDLE_SIZE,
    MODEL_CONTEXT_LIMIT,
    TARGET_INPUT_HI,
    TARGET_INPUT_LO,
)
from quwarts.core.shared_bundle.graph import AttributeGraph, partition_bundles
from quwarts.core.shared_bundle.inventory import AttributeRecord, compile_attribute_inventory
from quwarts.core.shared_bundle.prompt import render_bundle_request
from quwarts.core.shared_bundle.router import derive_input_cap, route_prompt
from quwarts.core.shared_bundle.tasks import build_packages, build_tasks, schedule_packages

__all__ = [
    "COMPLETION_SAFETY",
    "LEDGER_SAFETY_MARGIN",
    "MAX_BUNDLE_SIZE",
    "MODEL_CONTEXT_LIMIT",
    "TARGET_INPUT_HI",
    "TARGET_INPUT_LO",
    "AttributeGraph",
    "AttributeRecord",
    "compile_attribute_inventory",
    "derive_input_cap",
    "partition_bundles",
    "build_packages",
    "build_tasks",
    "render_bundle_request",
    "route_prompt",
    "schedule_packages",
]
