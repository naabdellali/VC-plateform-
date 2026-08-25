"""
Data model.

The whole "no hallucination" promise of the product depends on this file:
every number that ever reaches a screen must trace back to a row in
`Evidence`, and every Evidence row must declare its `origin` (did the
company say it, did we find it externally, did we calculate it, did we
infer it) and its `confidence`. Nothing is allowed to skip this table.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, Enum, JSON, Float, Boolean
)
from sqlalchemy.orm import relationship, backref

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Stage(str, enum.Enum):
    pre_seed = "pre_seed"
    seed = "seed"
    series_a = "series_a"
    series_b_plus = "series_b_plus"
    unknown = "unknown"


class BusinessModel(str, enum.Enum):
    saas = "saas"
    marketplace = "marketplace"
    hardware = "hardware"
    consumer = "consumer"
    fintech = "fintech"
    deeptech = "deeptech"
    other = "other"


class ModuleStatus(str, enum.Enum):
    complete = "complete"
    incomplete = "incomplete"
    insufficient_evidence = "insufficient_evidence"
    high_risk = "high_risk"
    needs_review = "needs_review"
    pending = "pending"


class EvidenceOrigin(str, enum.Enum):
    company_claim = "company_claim"            # A: what the company claims
    external_source = "external_source"         # B: what external sources say
    platform_calculation = "platform_calculation"  # C: what the platform calculates
    platform_inference = "platform_inference"    # D: what the platform infers
    unknown = "unknown"                          # E: remains unverified


class SourceTier(str, enum.Enum):
    tier1_primary = "tier1_primary"
    tier2_secondary = "tier2_secondary"
    tier3_low_confidence = "tier3_low_confidence"
    deck = "deck"                # the pitch deck itself
    calculation = "calculation"  # deterministic platform math
    llm_inference = "llm_inference"
    not_applicable = "not_applicable"


class Confidence(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unverified = "unverified"


class RedFlagSeverity(str, enum.Enum):
    critical = "critical"
    major = "major"
    watch = "watch"


class NumberSemanticCategory(str, enum.Enum):
    """What a given extracted number actually IS - assigned in a second pass,
    deliberately separate from the first pass that just recognizes the number
    exists (see Number model + services/number_extraction.py). "€8m" means
    nothing on its own; it needs the rest of the deck as context before it
    can be labelled revenue vs. ARR vs. funding vs. TAM."""
    revenue = "revenue"
    arr = "arr"
    mrr = "mrr"
    gmv = "gmv"
    users = "users"
    customers = "customers"
    growth_rate = "growth_rate"
    retention = "retention"
    churn = "churn"
    cac = "cac"
    ltv = "ltv"
    acv = "acv"
    gross_margin = "gross_margin"
    cogs = "cogs"
    burn = "burn"
    runway = "runway"
    pipeline = "pipeline"
    conversion = "conversion"
    sales_cycle = "sales_cycle"
    order_volume = "order_volume"
    units_sold = "units_sold"
    utilization = "utilization"
    engagement = "engagement"
    funding_amount = "funding_amount"
    valuation = "valuation"
    market_size_tam = "market_size_tam"
    market_size_sam = "market_size_sam"
    market_size_som = "market_size_som"
    headcount = "headcount"
    other_kpi = "other_kpi"
    unclassified = "unclassified"  # default right after pass A, before pass B runs


class ClaimKind(str, enum.Enum):
    """The epistemic status of a Claim row - NOT its subject matter
    (that's claim_type). These four must never be interchangeable
    (per-analyst instruction): a fact is descriptive and directly
    supported; a company_claim is management's own assertion and starts
    unverified; an assumption is a condition a claim/forecast depends on;
    an inference is a conclusion OUR reasoning produced, never extracted."""
    fact = "fact"
    company_claim = "company_claim"
    assumption = "assumption"
    inference = "inference"


class ClaimVerificationStatus(str, enum.Enum):
    unverified = "unverified"
    supported = "supported"
    contradicted = "contradicted"
    insufficient_evidence = "insufficient_evidence"


class ClaimRelationship(str, enum.Enum):
    """Only meaningful when parent_claim_id is set - the minimal relationship
    vocabulary for Phase 1. Deliberately NOT a general graph-traversal engine
    (that's Phase 3) - just enough to record "this assumption underpins that
    forecast" and "this inference was derived from that claim"."""
    assumption_of = "assumption_of"
    derived_from = "derived_from"
    contradicts = "contradicts"
    supports = "supports"


class Recommendation(str, enum.Enum):
    invest = "invest"
    pass_ = "pass"
    watchlist = "watchlist"
    need_more_data = "need_more_data"


class Company(Base):
    __tablename__ = "companies"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    legal_name = Column(String, nullable=True)
    stage = Column(Enum(Stage), default=Stage.unknown, nullable=False)
    business_model = Column(Enum(BusinessModel), default=BusinessModel.other, nullable=False)
    sector = Column(String, nullable=True)
    # Short (1-3 word) display category, e.g. "Insuretech" - distinct from `sector`, which is a
    # longer, precise phrase used to drive research queries. Never shown as a research finding,
    # just a compact tray/header label.
    industry_tag = Column(String, nullable=True)
    hq_country = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    decks = relationship("Deck", back_populates="company", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="company", cascade="all, delete-orphan")
    module_results = relationship("ModuleResult", back_populates="company", cascade="all, delete-orphan")
    red_flags = relationship("RedFlag", back_populates="company", cascade="all, delete-orphan")
    memos = relationship("Memo", back_populates="company", cascade="all, delete-orphan")
    numbers = relationship("Number", back_populates="company", cascade="all, delete-orphan")
    claims = relationship("Claim", back_populates="company", cascade="all, delete-orphan")


class Deck(Base):
    __tablename__ = "decks"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    filename = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=_now)
    raw_text = Column(Text, nullable=True)
    # Structured, per-slide extraction: [{"slide": 1, "title": ..., "text": ..., "claims": [...]}]
    slides_json = Column(JSON, nullable=True)
    # Claims extracted by the LLM extraction pass, before verification:
    # [{"category": "market_size", "claim": "TAM of 10bn EUR", "slide": 4}, ...]
    extracted_claims_json = Column(JSON, nullable=True)

    company = relationship("Company", back_populates="decks")


class Claim(Base):
    """
    Phase 1: the canonical, first-class representation of everything a deck
    (or later, an external source, or our own reasoning) says about a
    company - unifying Fact / Company claim / Assumption / Inference under
    one table distinguished by `kind`, rather than four near-identical
    tables. `claim_type` is the subject-matter taxonomy (company identity,
    funding history, market size, traction metric...) and is deliberately a
    plain String (app-validated, see services/claim_taxonomy.py) rather than
    a native DB enum, since this taxonomy is expected to keep growing as
    real decks are run through it - a String needs no migration to extend,
    a Postgres native enum does.

    This table is what modules should query going forward instead of
    Deck.extracted_claims_json (kept only as a raw-output audit trail) -
    the fix for claims being extracted once and then silently dropped for
    categories no module happened to read.
    """
    __tablename__ = "claims"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    deck_id = Column(String, ForeignKey("decks.id"), nullable=True)  # null for a pure platform-reasoning inference

    kind = Column(Enum(ClaimKind), nullable=False)
    claim_type = Column(String, nullable=False)  # see services/claim_taxonomy.py for the validated vocabulary

    text = Column(Text, nullable=False)         # verbatim wording (fact/company_claim) or synthesized statement
    context = Column(Text, nullable=True)       # surrounding text / rationale
    slide_reference = Column(String, nullable=True)
    source = Column(String, nullable=True)      # "deck" | "external_source" | "platform_reasoning"

    verification_status = Column(Enum(ClaimVerificationStatus), default=ClaimVerificationStatus.unverified, nullable=False)
    required_evidence = Column(Text, nullable=True)    # what would verify/refute this claim
    potential_challenge = Column(Text, nullable=True)  # how a sharp VC would push back on this
    related_modules = Column(JSON, nullable=True)      # list of module keys this claim is relevant to

    parent_claim_id = Column(String, ForeignKey("claims.id"), nullable=True)
    relationship_type = Column(Enum(ClaimRelationship), nullable=True)

    created_at = Column(DateTime, default=_now)

    company = relationship("Company", back_populates="claims")
    deck = relationship("Deck")
    numbers = relationship("Number", back_populates="claim")
    children = relationship("Claim", backref=backref("parent_claim", remote_side=[id]))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind.value if self.kind else None,
            "claim_type": self.claim_type,
            "text": self.text,
            "context": self.context,
            "slide_reference": self.slide_reference,
            "source": self.source,
            "verification_status": self.verification_status.value if self.verification_status else None,
            "required_evidence": self.required_evidence,
            "potential_challenge": self.potential_challenge,
            "related_modules": self.related_modules or [],
            "parent_claim_id": self.parent_claim_id,
            "relationship_type": self.relationship_type.value if self.relationship_type else None,
        }


class Number(Base):
    """
    Phase 1: numbers get their own extraction pass, deliberately separate
    from interpretation (per-analyst instruction: "do not interpret a
    number before preserving the raw evidence"). A Number row is created by
    a deterministic/regex-assisted recognition pass BEFORE any semantic
    meaning is assigned; `semantic_category` starts at "unclassified" and is
    filled in by a later pass that sees the whole deck - the raw row is
    never overwritten, only annotated.
    """
    __tablename__ = "numbers"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    deck_id = Column(String, ForeignKey("decks.id"), nullable=False)

    raw_text = Column(String, nullable=False)     # verbatim, e.g. "€8m"
    value = Column(Float, nullable=True)          # normalized float, null if unparseable
    unit = Column(String, nullable=True)          # "EUR" | "USD" | "%" | "count" | "months" | "x" ...
    currency = Column(String, nullable=True)
    period = Column(String, nullable=True)        # free text as stated, e.g. "Q4 2025"
    as_of_date = Column(String, nullable=True)    # free text explicit date if stated
    definition = Column(Text, nullable=True)      # how the deck defines this number, if stated
    slide_reference = Column(String, nullable=True)
    context = Column(Text, nullable=True)         # verbatim surrounding sentence(s)

    semantic_category = Column(Enum(NumberSemanticCategory), default=NumberSemanticCategory.unclassified, nullable=False)
    semantic_confidence = Column(String, nullable=True)  # "high" | "medium" | "low"
    candidate_categories = Column(JSON, nullable=True)   # kept when genuinely ambiguous

    claim_id = Column(String, ForeignKey("claims.id"), nullable=True)

    created_at = Column(DateTime, default=_now)

    company = relationship("Company", back_populates="numbers")
    deck = relationship("Deck")
    claim = relationship("Claim", back_populates="numbers")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "raw_text": self.raw_text,
            "value": self.value,
            "unit": self.unit,
            "currency": self.currency,
            "period": self.period,
            "as_of_date": self.as_of_date,
            "definition": self.definition,
            "slide_reference": self.slide_reference,
            "context": self.context,
            "semantic_category": self.semantic_category.value if self.semantic_category else None,
            "semantic_confidence": self.semantic_confidence,
            "candidate_categories": self.candidate_categories or [],
            "claim_id": self.claim_id,
        }


class Evidence(Base):
    """
    The atomic unit of the anti-hallucination system.
    One row = one traceable fact, claim, calculation or inference.
    """
    __tablename__ = "evidence"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    module = Column(String, nullable=False)  # "market" | "competition" | "traction" | "founders" | "red_flags" | "memo"

    claim = Column(Text, nullable=False)          # human-readable: what this evidence is about
    value = Column(Text, nullable=True)            # the value/number/text, serialized
    value_type = Column(String, nullable=True)     # "currency_eur" | "percentage" | "text" | "count" ...

    origin = Column(Enum(EvidenceOrigin), nullable=False)
    source_tier = Column(Enum(SourceTier), nullable=False, default=SourceTier.not_applicable)
    confidence = Column(Enum(Confidence), nullable=False, default=Confidence.unverified)

    source_name = Column(String, nullable=True)
    source_url = Column(String, nullable=True)
    source_publication_date = Column(String, nullable=True)  # free text: often only a year/quarter is known
    retrieval_date = Column(DateTime, default=_now)

    methodology = Column(Text, nullable=True)          # how a calculation/estimate was produced
    supporting_excerpt = Column(Text, nullable=True)   # verbatim snippet backing the claim
    assumptions_json = Column(JSON, nullable=True)      # list of assumption strings used to get here

    # Phase 1 (canonical deal representation): which Claim this Evidence verifies/refutes,
    # if any - closes the provenance chain deck -> slide -> Claim/Number -> Evidence ->
    # ModuleResult into real foreign keys instead of text matching. Nullable: plenty of
    # Evidence (e.g. a platform_calculation) isn't "verifying a claim" in this sense.
    claim_id = Column(String, ForeignKey("claims.id"), nullable=True)

    created_at = Column(DateTime, default=_now)

    company = relationship("Company", back_populates="evidence")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "module": self.module,
            "claim": self.claim,
            "value": self.value,
            "value_type": self.value_type,
            "origin": self.origin.value if self.origin else None,
            "source_tier": self.source_tier.value if self.source_tier else None,
            "confidence": self.confidence.value if self.confidence else None,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_publication_date": self.source_publication_date,
            "retrieval_date": self.retrieval_date.isoformat() if self.retrieval_date else None,
            "methodology": self.methodology,
            "supporting_excerpt": self.supporting_excerpt,
            "assumptions": self.assumptions_json or [],
        }


class ModuleResult(Base):
    """
    One row per (company, module). Holds the level-1 conclusion (for the
    memo/tray tile) and the full step-by-step reasoning trace that a user
    drills into. Every step should reference Evidence ids, never restate
    a number without pointing at where it came from.
    """
    __tablename__ = "module_results"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    module = Column(String, nullable=False)

    status = Column(Enum(ModuleStatus), default=ModuleStatus.pending, nullable=False)
    headline = Column(Text, nullable=True)     # e.g. "Market size: EUR45M (platform) vs EUR120M (deck)"
    deck_value = Column(Text, nullable=True)
    platform_value = Column(Text, nullable=True)
    discrepancy_explanation = Column(Text, nullable=True)

    # The 10-step reasoning loop trace, each step referencing evidence ids:
    # {"extract": {...}, "identify_unknowns": [...], "research": [...], "verify": [...],
    #  "calculate": {...}, "benchmark": {...}, "reality_check": {...},
    #  "contradictions": [...], "assumptions": [...], "investment_implication": "..."}
    reasoning_json = Column(JSON, nullable=True)
    evidence_ids_json = Column(JSON, nullable=True)  # ordered list of Evidence.id referenced by this module

    llm_mode = Column(String, nullable=True)   # "live" | "mock" - transparency on how this was produced
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    company = relationship("Company", back_populates="module_results")


class RedFlag(Base):
    __tablename__ = "red_flags"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    module = Column(String, nullable=True)
    category = Column(String, nullable=False)   # market | competition | moat | team | financial | execution ...
    severity = Column(Enum(RedFlagSeverity), nullable=False)
    explanation = Column(Text, nullable=False)
    evidence_id = Column(String, ForeignKey("evidence.id"), nullable=True)
    potential_impact = Column(Text, nullable=True)
    resolving_information = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    company = relationship("Company", back_populates="red_flags")


class Memo(Base):
    __tablename__ = "memos"

    id = Column(String, primary_key=True, default=_uuid)
    company_id = Column(String, ForeignKey("companies.id"), nullable=False)
    version = Column(String, default="v1")
    sections_json = Column(JSON, nullable=True)  # ordered list of {"title": ..., "body": ..., "evidence_ids": [...]}
    recommendation = Column(Enum(Recommendation), nullable=True)
    key_questions_json = Column(JSON, nullable=True)
    generated_at = Column(DateTime, default=_now)

    company = relationship("Company", back_populates="memos")
