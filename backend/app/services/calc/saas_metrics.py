"""
SaaS-specific deterministic metrics (spec section 11, "SaaS" framework) plus
the MRR-forensics and CAC/LTV consistency checks called out explicitly by
the user (spec sections 12, 18, 46).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.calc.finance import coefficient_of_variation, count_declines


def arr_from_mrr(mrr: float) -> float:
    return mrr * 12


def net_revenue_retention(starting_arr: float, expansion: float, contraction: float, churn: float) -> float:
    """NRR = (starting_arr + expansion - contraction - churn) / starting_arr"""
    if starting_arr <= 0:
        raise ValueError("starting_arr must be > 0")
    return (starting_arr + expansion - contraction - churn) / starting_arr


def gross_revenue_retention(starting_arr: float, contraction: float, churn: float) -> float:
    """GRR = (starting_arr - contraction - churn) / starting_arr. Capped at 100%: GRR never reflects upsell."""
    if starting_arr <= 0:
        raise ValueError("starting_arr must be > 0")
    return min(1.0, (starting_arr - contraction - churn) / starting_arr)


def cac_payback_months(cac: float, arpa_monthly: float, gross_margin: float) -> float:
    """Months to recover CAC from gross-margin-adjusted monthly revenue per account."""
    if arpa_monthly <= 0 or gross_margin <= 0:
        raise ValueError("arpa_monthly and gross_margin must be > 0")
    return cac / (arpa_monthly * gross_margin)


def ltv(arpa_monthly: float, gross_margin: float, monthly_churn: float) -> float:
    """Simple LTV = ARPA x gross_margin / monthly_churn."""
    if monthly_churn <= 0:
        raise ValueError("monthly_churn must be > 0 (use a floor, e.g. 0.001, if churn is reported as 0)")
    return (arpa_monthly * gross_margin) / monthly_churn


def ltv_to_cac(ltv_value: float, cac: float) -> float:
    if cac <= 0:
        raise ValueError("cac must be > 0")
    return ltv_value / cac


def rule_of_40(growth_rate_pct: float, profit_margin_pct: float) -> dict:
    total = growth_rate_pct + profit_margin_pct
    return {"score": round(total, 2), "passes": total >= 40}


@dataclass
class MrrQualityReport:
    coefficient_of_variation: float
    declining_months: int
    total_months: int
    flags: list[str] = field(default_factory=list)

    def as_evidence_payload(self) -> dict:
        return {
            "coefficient_of_variation": round(self.coefficient_of_variation, 3),
            "declining_months": self.declining_months,
            "total_months": self.total_months,
            "flags": self.flags,
        }


def mrr_quality_check(mrr_series: list[float], cv_flag_threshold: float = 0.15, decline_ratio_flag_threshold: float = 0.3) -> MrrQualityReport:
    """
    Flags "MRR" figures that behave like project/service revenue rather than
    true recurring SaaS revenue: high month-to-month volatility, or a large
    share of months declining despite an overall "growing MRR" narrative.
    This directly operationalizes the user's example: "if MRR goes up then
    down then up, there's probably services revenue mixed in."
    """
    if len(mrr_series) < 2:
        raise ValueError("mrr_series needs at least 2 data points")

    cv = coefficient_of_variation(mrr_series)
    declines = count_declines(mrr_series)
    total_transitions = len(mrr_series) - 1
    decline_ratio = declines / total_transitions if total_transitions else 0.0

    flags = []
    if cv > cv_flag_threshold:
        flags.append(
            f"High month-to-month volatility (CV={cv:.2f} > {cv_flag_threshold}) - "
            "inconsistent with steady recurring revenue; investigate whether "
            "one-off services/project revenue is included in the reported MRR."
        )
    if decline_ratio > decline_ratio_flag_threshold:
        flags.append(
            f"{declines}/{total_transitions} months show a decline in MRR - "
            "a 'growing MRR' narrative should not show this much backsliding "
            "if the revenue base is truly recurring and sticky."
        )
    if not flags:
        flags.append("No volatility red flag detected from the reported series alone.")

    return MrrQualityReport(
        coefficient_of_variation=cv,
        declining_months=declines,
        total_months=len(mrr_series),
        flags=flags,
    )


def cac_ltv_consistency_check(cac: float, reported_ltv: float, gross_margin: float, arpa_monthly: float) -> dict:
    """
    Spec section 18/46 example: CAC=EUR10k, LTV=EUR150k -> what monthly churn
    would be REQUIRED for that LTV to be true, and is it plausible?
    implied_ltv = arpa_monthly * gross_margin / monthly_churn
      => monthly_churn = arpa_monthly * gross_margin / implied_ltv
    """
    if arpa_monthly <= 0 or gross_margin <= 0 or reported_ltv <= 0:
        raise ValueError("arpa_monthly, gross_margin and reported_ltv must be > 0")

    implied_monthly_churn = (arpa_monthly * gross_margin) / reported_ltv
    implied_annual_churn = 1 - (1 - implied_monthly_churn) ** 12
    ratio = reported_ltv / cac if cac > 0 else None

    plausible = 0.0 <= implied_monthly_churn <= 0.10  # >10%/month churn is very rarely credible for reported LTVs this high
    return {
        "implied_monthly_churn": round(implied_monthly_churn, 4),
        "implied_annual_churn": round(implied_annual_churn, 4),
        "ltv_to_cac_ratio": round(ratio, 2) if ratio is not None else None,
        "plausible": plausible,
        "explanation": (
            f"For the reported LTV of {reported_ltv:,.0f} to hold given ARPA of "
            f"{arpa_monthly:,.0f}/mo and {gross_margin:.0%} gross margin, monthly "
            f"churn would need to be {implied_monthly_churn:.2%} "
            f"({implied_annual_churn:.1%} annualized)."
            + ("" if plausible else " This is not a plausible retention rate - the reported LTV is likely inflated or inconsistent with the reported churn/ARPA.")
        ),
    }
