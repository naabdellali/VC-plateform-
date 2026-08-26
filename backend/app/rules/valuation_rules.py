"""
Deterministic scenario growth-rate assumptions used by the valuation
module's Downside/Base/Upside revenue projection (Phase 2 of the roadmap,
"three-scenario financial modeling").

Represented as data, not buried in a prompt - same principle as
`stage_rules.py` - so it can be listed, audited and edited without
touching reasoning-module code. These are NOT a claim about any specific
company: they are widely-cited, stage-typical SaaS annual revenue growth
benchmarks (loosely anchored to the informal "T2D3" trajectory for
early-stage SaaS - triple, triple, double, double, double - tapering off
for later stages, where hypergrowth rarely persists). The valuation
module always surfaces the rate actually used and labels it explicitly
as a sector benchmark assumption, never as a prediction specific to the
company being analyzed.
"""
from app.models import Stage

# Annual (year-over-year) revenue growth rate assumption, by stage and
# scenario. Expressed as a fraction (0.50 = +50%/year).
SCENARIO_GROWTH_RATES: dict[str, dict[str, float]] = {
    Stage.pre_seed.value: {"downside": 0.50, "base": 1.50, "upside": 3.00},
    Stage.seed.value: {"downside": 0.30, "base": 1.00, "upside": 2.00},
    Stage.series_a.value: {"downside": 0.15, "base": 0.60, "upside": 1.20},
    Stage.series_b_plus.value: {"downside": 0.05, "base": 0.35, "upside": 0.70},
    Stage.unknown.value: {"downside": 0.15, "base": 0.50, "upside": 1.00},
}

# How many years out the scenario projection looks. Kept as a single
# named constant (rather than a magic number scattered through the
# module) since it shows up both in the growth-compounding formula and
# in every headline/label string that describes the projection.
PROJECTION_YEARS = 3


def get_scenario_growth_rates(stage: Stage) -> dict[str, float]:
    return SCENARIO_GROWTH_RATES.get(stage.value, SCENARIO_GROWTH_RATES[Stage.unknown.value])
