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
from sqlalchemy.orm import relationship

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
    hq_country = Column(String, nullable=True)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    decks = relationship("Deck", back_populates="company", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="company", cascade="all, delete-orphan")
    module_results = relationship("ModuleResult", back_populates="company", cascade="all, delete-orphan")
    red_flags = relationship("RedFlag", back_populates="company", cascade="all, delete-orphan")
    memos = relationship("Memo", back_populates="company", cascade="all, delete-orphan")


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
