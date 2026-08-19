"""
The `claim_type` vocabulary - deliberately a plain Python list/set validated
at the application layer, not a Postgres-native enum column (see Claim
model docstring in app/models.py). This taxonomy is expected to grow as
real decks surface fields we haven't modeled yet; a String column needs no
migration to accept a new value, a DB enum does.

Grouped to mirror the analyst's own breakdown (Company / Product / Market /
Traction-Financial), plus a deliberately-scrutinized "other" escape hatch:
unlike the old extract_claims() categories, an "other" claim under this
taxonomy is meant to be reviewed and reclassified as its own claim_type
once a pattern emerges - not a bucket where things go to be forgotten.
"""
from __future__ import annotations

COMPANY_CLAIM_TYPES = [
    "company_identity",    # name, legal name, founding date, HQ, countries of operation
    "funding_history",     # round, amount raised, valuation, investors
    "ownership",
    "team_background",
]

PRODUCT_CLAIM_TYPES = [
    "product_description",
    "product_architecture",
    "product_roadmap",
    "pricing",
    "differentiation",
    "distribution",
    "dependency",
]

MARKET_CLAIM_TYPES = [
    "market_size",
    "market_definition",
    "market_growth",
    "competitive_position",
]

TRACTION_FINANCIAL_CLAIM_TYPES = [
    "traction_metric",
    "traction_projection",
    "financial_metric",
]

OTHER_CLAIM_TYPES = ["other"]

ALL_CLAIM_TYPES = (
    COMPANY_CLAIM_TYPES + PRODUCT_CLAIM_TYPES + MARKET_CLAIM_TYPES
    + TRACTION_FINANCIAL_CLAIM_TYPES + OTHER_CLAIM_TYPES
)

# Which claim_types each existing reasoning module currently consumes -
# single source of truth so nothing is "extracted, and then nobody reads
# it" without at least being visible as a deliberate, listed gap rather
# than a silent one. Modules not listed for a given claim_type simply
# haven't been wired to reason over it yet (Phase 2/3), but the Claim rows
# themselves are always persisted regardless.
CLAIM_TYPE_TO_MODULES = {
    "company_identity": [],
    "funding_history": ["memo"],
    "ownership": ["founders"],
    "team_background": ["founders"],
    "product_description": [],
    "product_architecture": ["technology"],
    "product_roadmap": [],
    "pricing": ["business_model"],
    "differentiation": ["moat"],
    "distribution": [],
    "dependency": ["technology"],
    "market_size": ["market"],
    "market_definition": ["market"],
    "market_growth": ["market_dynamics"],
    "competitive_position": ["competition"],
    "traction_metric": ["traction"],
    "traction_projection": ["traction"],
    "financial_metric": [],  # persisted, not yet consumed by a dedicated Financials module (Phase 2/3)
    "other": [],
}


def validate_claim_type(claim_type: str) -> str:
    """Fail loudly on an unrecognized claim_type rather than silently accepting
    a typo'd or made-up value that would then never be queried by anything -
    exactly the failure mode this taxonomy exists to prevent."""
    if claim_type not in ALL_CLAIM_TYPES:
        raise ValueError(f"Unknown claim_type {claim_type!r} - add it to app/services/claim_taxonomy.py first.")
    return claim_type
