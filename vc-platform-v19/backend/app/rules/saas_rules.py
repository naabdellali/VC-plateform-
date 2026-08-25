"""
Business-model rule library (spec section 36), SaaS only in V1 per the
agreed MVP scope. Declares the KPI set and the trigger rules that decide
which extra research/checks a company's claims should activate (spec
section 38's "IF ... THEN trigger" pattern), expressed as data.
"""

SAAS_KPI_SET = [
    "arr", "mrr", "revenue_growth", "nrr", "grr", "logo_churn",
    "cac", "ltv", "cac_payback_months", "gross_margin", "cogs",
    "sales_efficiency", "burn", "burn_multiple", "runway", "acv", "sales_cycle",
]

# Each rule: a condition over extracted claims/company fields, and the
# module(s) it should trigger. Evaluated by services/reasoning/rule_engine.py.
TRIGGER_RULES = [
    {
        "id": "us_expansion_claimed",
        "condition": {"claim_contains_any": ["united states", "us expansion", "u.s. market"]},
        "triggers": ["market", "competition"],
        "reason": "Geographic expansion claims require independent market/regulatory/competitive analysis for the target geography (spec section 7).",
    },
    {
        "id": "aggressive_growth_forecast",
        "condition": {"category": "financials", "claim_contains_any": ["x revenue", "10x", "5x", "growth of"]},
        "triggers": ["traction"],
        "reason": "Forecasts exceeding typical historical growth trigger assumption decomposition and benchmark comparison (spec section 13-14).",
    },
    {
        "id": "no_competitors_named",
        "condition": {"category": "competitors", "absent": True},
        "triggers": ["competition"],
        "reason": "Absence of a competitor claim itself must be independently checked (spec section 8): a real gap, not a signal of no competition.",
    },
]


def evaluate_trigger_rules(extracted_claims: list[dict]) -> list[dict]:
    """Returns the list of TRIGGER_RULES whose condition matches the deck's
    extracted claims - a minimal, inspectable rule engine (spec section 38)."""
    fired = []
    categories_present = {c.get("category") for c in extracted_claims}
    all_claim_text = " ".join((c.get("claim") or "") for c in extracted_claims).lower()

    for rule in TRIGGER_RULES:
        cond = rule["condition"]
        matched = False
        if cond.get("claim_contains_any"):
            matched = any(kw in all_claim_text for kw in cond["claim_contains_any"])
            if cond.get("category"):
                matched = matched and cond["category"] in categories_present
        elif cond.get("absent"):
            matched = cond["category"] not in categories_present
        if matched:
            fired.append(rule)
    return fired
