"""
Deterministic valuation math. Per the spec's architectural principle (#54,
see finance.py): anything that can be computed with a formula MUST be
computed with a formula, never asked of an LLM. The LLM's only job in the
valuation module is to research and synthesize a defensible comps
multiple range (grounded in cited sources) - everything downstream of
that (implied valuation, scenario projections) is plain arithmetic here,
wrapped by the caller in an Evidence row with source_tier=calculation and
an explicit methodology string.
"""
from __future__ import annotations


def implied_valuation_range(revenue: float, low_multiple: float, high_multiple: float) -> dict:
    """Revenue x a comps multiple range -> an implied valuation range.

    `revenue` is whatever revenue figure the caller passed in (e.g. a
    deck-declared ARR/MRR run-rate) - this function does not know or care
    whether that figure has been independently verified; that caveat
    belongs in the caller's methodology string, not here.
    """
    if revenue < 0:
        raise ValueError("revenue must be >= 0")
    if low_multiple < 0 or high_multiple < 0:
        raise ValueError("multiples must be >= 0")
    if high_multiple < low_multiple:
        low_multiple, high_multiple = high_multiple, low_multiple
    return {
        "low": revenue * low_multiple,
        "high": revenue * high_multiple,
    }


def project_scenario_value(revenue: float, growth_rate: float, years: int, multiple: float) -> dict:
    """Compound `revenue` at `growth_rate`/year for `years` years, then
    apply `multiple` to the projected revenue to get a projected value.

    `growth_rate` is a fraction (0.50 = +50%/year) and may be negative
    (a genuine decline scenario), but a rate at or below -100%/year makes
    no arithmetic sense (revenue cannot go negative by compounding).
    """
    if revenue < 0:
        raise ValueError("revenue must be >= 0")
    if years < 0:
        raise ValueError("years must be >= 0")
    if growth_rate <= -1:
        raise ValueError("growth_rate must be > -1 (a >=100% annual decline is not a compounding rate)")
    if multiple < 0:
        raise ValueError("multiple must be >= 0")
    projected_revenue = revenue * ((1 + growth_rate) ** years)
    return {
        "projected_revenue": projected_revenue,
        "projected_value": projected_revenue * multiple,
    }
