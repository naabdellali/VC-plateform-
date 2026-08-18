"""
Stage-aware constraints (spec section 35.1). Represented as data, not
buried in a prompt, so they can be listed, audited and edited without
touching reasoning-module code. V1 scope: informs which findings the memo
should foreground, and captures which metrics should NOT be penalized
because they realistically don't exist yet at that stage.
"""
from app.models import Stage

STAGE_PRIORITIES: dict[str, dict] = {
    Stage.pre_seed.value: {
        "prioritize": ["founder_market_fit", "market_size", "product_insight", "early_customer_validation"],
        "do_not_penalize": ["arr", "nrr", "cac_payback", "unit_economics"],
    },
    Stage.seed.value: {
        "prioritize": ["founder_market_fit", "market_size", "early_traction", "velocity", "potential_moat"],
        "do_not_penalize": ["nrr", "sales_efficiency", "gross_margin_maturity"],
    },
    Stage.series_a.value: {
        "prioritize": ["repeatability", "retention", "early_unit_economics", "gtm_efficiency", "revenue_quality"],
        "do_not_penalize": ["multi_year_retention_cohorts"],
    },
    Stage.series_b_plus.value: {
        "prioritize": ["predictable_growth", "retention", "cac_efficiency", "margins", "burn_multiple", "market_share"],
        "do_not_penalize": [],
    },
    Stage.unknown.value: {
        "prioritize": ["founder_market_fit", "market_size", "traction"],
        "do_not_penalize": ["arr", "nrr", "cac_payback"],
    },
}


def get_stage_priorities(stage: Stage) -> dict:
    return STAGE_PRIORITIES.get(stage.value, STAGE_PRIORITIES[Stage.unknown.value])
