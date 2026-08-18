"""
Independent market-size reconstruction (spec section 6).

The platform must never simply echo the company's TAM/SAM/SOM. These
functions produce the platform's OWN estimate from explicit, inspectable
inputs, so the reasoning layer can present:

    company claim  vs  platform estimate  vs  methodology  vs  assumptions

as separate, clearly-labelled Evidence rows.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MarketEstimate:
    value_eur: float
    methodology: str
    inputs: dict
    assumptions: list[str] = field(default_factory=list)

    def as_evidence_payload(self) -> dict:
        return {
            "value": round(self.value_eur, 2),
            "methodology": self.methodology,
            "inputs": self.inputs,
            "assumptions": self.assumptions,
        }


def tam_bottom_up(
    num_potential_customers: float,
    avg_annual_spend_eur: float,
    realistic_penetration: float = 1.0,
    assumptions: list[str] | None = None,
) -> MarketEstimate:
    """
    TAM = number of potential customers x realistic annual spend x penetration.

    `realistic_penetration` defaults to 1.0 (full TAM, no penetration cap) -
    pass < 1.0 to model SAM/SOM instead by reusing this same function.
    """
    if num_potential_customers < 0 or avg_annual_spend_eur < 0:
        raise ValueError("inputs must be non-negative")
    if not (0 < realistic_penetration <= 1):
        raise ValueError("realistic_penetration must be in (0, 1]")

    value = num_potential_customers * avg_annual_spend_eur * realistic_penetration
    return MarketEstimate(
        value_eur=value,
        methodology=(
            "Bottom-up: potential_customers x avg_annual_spend x penetration_rate"
        ),
        inputs={
            "num_potential_customers": num_potential_customers,
            "avg_annual_spend_eur": avg_annual_spend_eur,
            "realistic_penetration": realistic_penetration,
        },
        assumptions=assumptions or [],
    )


def tam_top_down(
    industry_size_eur: float,
    relevant_segment_pct: float,
    addressable_pct: float,
    assumptions: list[str] | None = None,
) -> MarketEstimate:
    """
    TAM = industry size x relevant segment % x realistically addressable %.
    """
    if industry_size_eur < 0:
        raise ValueError("industry_size_eur must be non-negative")
    if not (0 < relevant_segment_pct <= 1) or not (0 < addressable_pct <= 1):
        raise ValueError("percentages must be in (0, 1]")

    value = industry_size_eur * relevant_segment_pct * addressable_pct
    return MarketEstimate(
        value_eur=value,
        methodology=(
            "Top-down: industry_size x relevant_segment_pct x addressable_pct"
        ),
        inputs={
            "industry_size_eur": industry_size_eur,
            "relevant_segment_pct": relevant_segment_pct,
            "addressable_pct": addressable_pct,
        },
        assumptions=assumptions or [],
    )


def compare_estimates(company_value_eur: float, platform_estimate: MarketEstimate) -> dict:
    """
    Produces the "discrepancy explanation" payload used directly by
    ModuleResult.discrepancy_explanation.
    """
    if company_value_eur <= 0:
        ratio = None
    else:
        ratio = platform_estimate.value_eur / company_value_eur

    if ratio is None:
        verdict = "Company did not disclose a comparable figure or it was zero/invalid."
    elif ratio >= 0.85:
        verdict = "Platform estimate is broadly consistent with the company's claim."
    elif ratio >= 0.5:
        verdict = "Platform estimate is meaningfully lower than the company's claim - review market definition."
    else:
        verdict = "Platform estimate is substantially lower than the company's claim - market definition is likely overstated."

    return {
        "company_value_eur": company_value_eur,
        "platform_value_eur": round(platform_estimate.value_eur, 2),
        "ratio_platform_over_company": round(ratio, 3) if ratio is not None else None,
        "verdict": verdict,
        "methodology": platform_estimate.methodology,
        "assumptions": platform_estimate.assumptions,
    }
