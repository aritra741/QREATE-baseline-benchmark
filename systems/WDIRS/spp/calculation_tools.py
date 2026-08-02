"""Small deterministic tools available to contract derivation prompts."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Sequence


def _decimal(value: object) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean operands are not numeric")
    try:
        result = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid numeric operand: {value!r}") from exc
    if not result.is_finite():
        raise ValueError("calculator operands must be finite")
    return result


def calculate(operation: str, operands: Sequence[object]) -> int | float:
    """Execute one allowlisted arithmetic operation."""

    if operation == "count":
        return len(operands)
    values = tuple(_decimal(value) for value in operands)
    if operation == "add" and values:
        result = sum(values, Decimal(0))
    elif operation == "subtract" and len(values) == 2:
        result = values[0] - values[1]
    elif operation == "multiply" and values:
        result = Decimal(1)
        for value in values:
            result *= value
    elif operation == "divide" and len(values) == 2 and values[1] != 0:
        result = values[0] / values[1]
    elif operation == "minimum" and values:
        result = min(values)
    elif operation == "maximum" and values:
        result = max(values)
    else:
        raise ValueError(f"unsupported calculator request: {operation}")
    if result == result.to_integral_value():
        return int(result)
    return float(result)


def operands_are_grounded(
    operands: Sequence[object],
    source_operands: Sequence[object],
    span: str,
    *,
    corpus_reference_year: object = None,
) -> bool:
    """Require every operand to come from evidence or one declared context tool."""

    unmatched = list(operands)
    for source_value in source_operands:
        if str(source_value) not in span:
            return False
        index = next(
            (
                candidate
                for candidate, operand in enumerate(unmatched)
                if operand == source_value or str(operand) == str(source_value)
            ),
            None,
        )
        if index is None:
            return False
        unmatched.pop(index)
    return all(
        corpus_reference_year is not None
        and (
            operand == corpus_reference_year
            or str(operand) == str(corpus_reference_year)
        )
        for operand in unmatched
    )


__all__ = ["calculate", "operands_are_grounded"]
