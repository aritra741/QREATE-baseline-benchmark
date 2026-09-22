"""Amortized attribute selection programs. Qwen compiles a DSL; the executor never emits values."""

from quwarts.core.amortized_select.config import OPERATOR
from quwarts.core.amortized_select.dsl import validate_spec
from quwarts.core.amortized_select.executor import execute_cell

__all__ = ["OPERATOR", "execute_cell", "validate_spec"]
