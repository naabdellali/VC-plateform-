"""
Generic deterministic finance helpers.

Per the spec's architectural principle (#54): anything that can be computed
with a formula MUST be computed with a formula, never asked of an LLM. Every
function here returns a plain number so callers can wrap it in an Evidence
row with source_tier=SourceTier.calculation and a `methodology` string that
names the formula used - full auditability, zero ambiguity.
"""
from __future__ import annotations


def cagr(begin_value: float, end_value: float, periods: float) -> float:
    """Compound annual growth rate. `periods` is the number of years."""
    if begin_value <= 0 or periods <= 0:
        raise ValueError("begin_value and periods must be > 0")
    return (end_value / begin_value) ** (1 / periods) - 1


def percentage_change(old_value: float, new_value: float) -> float:
    if old_value == 0:
        raise ValueError("old_value must be non-zero")
    return (new_value - old_value) / old_value


def coefficient_of_variation(series: list[float]) -> float:
    """Std-dev / mean. Used to flag 'lumpy' revenue that doesn't behave like
    true recurring SaaS revenue."""
    n = len(series)
    if n == 0:
        raise ValueError("series must not be empty")
    mean = sum(series) / n
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in series) / n
    std_dev = variance ** 0.5
    return std_dev / mean


def month_over_month_deltas(series: list[float]) -> list[float]:
    return [series[i] - series[i - 1] for i in range(1, len(series))]


def count_declines(series: list[float]) -> int:
    return sum(1 for d in month_over_month_deltas(series) if d < 0)
