from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    module: str
    claim: str
    value: Optional[str] = None
    value_type: Optional[str] = None
    origin: str
    source_tier: str
    confidence: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_publication_date: Optional[str] = None
    retrieval_date: Optional[datetime] = None
    methodology: Optional[str] = None
    supporting_excerpt: Optional[str] = None
    assumptions_json: Optional[list] = None


class ModuleResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    module: str
    status: str
    headline: Optional[str] = None
    deck_value: Optional[str] = None
    platform_value: Optional[str] = None
    discrepancy_explanation: Optional[str] = None
    reasoning_json: Optional[dict] = None
    evidence_ids_json: Optional[list] = None
    llm_mode: Optional[str] = None
    updated_at: Optional[datetime] = None


class RedFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    module: Optional[str] = None
    category: str
    severity: str
    explanation: str
    evidence_id: Optional[str] = None
    potential_impact: Optional[str] = None
    resolving_information: Optional[str] = None


class MemoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: str
    sections_json: Optional[list] = None
    recommendation: Optional[str] = None
    key_questions_json: Optional[list] = None
    generated_at: Optional[datetime] = None


class DeckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    uploaded_at: Optional[datetime] = None
    extracted_claims_json: Optional[list] = None


class CompanyCreate(BaseModel):
    name: str


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    legal_name: Optional[str] = None
    stage: str
    business_model: str
    sector: Optional[str] = None
    industry_tag: Optional[str] = None
    hq_country: Optional[str] = None
    created_at: Optional[datetime] = None


class CompanyDetailOut(CompanyOut):
    decks: list[DeckOut] = []
    module_results: list[ModuleResultOut] = []
    red_flags: list[RedFlagOut] = []


class TrayTile(BaseModel):
    module: str
    label: str
    status: str
    headline: Optional[str] = None
    red_flag_count: int = 0


class AnalyzeResponse(BaseModel):
    company: CompanyOut
    modules_triggered: list[str]


class CompanyDashboardItem(BaseModel):
    """One dashboard row - CompanyOut's fields plus the aggregates the
    dashboard needs (latest recommendation, ask amount, red flag counts).
    Kept as its own model rather than stretched onto CompanyOut: these are
    derived/aggregated values (latest Memo, sum over RedFlag/Deck rows), not
    plain Company columns, and not every caller of CompanyOut wants them
    computed on every request."""

    id: str
    name: str
    sector: Optional[str] = None
    industry_tag: Optional[str] = None
    stage: str
    business_model: str
    # None until a memo has actually been generated for this company - never
    # guessed or defaulted to a "neutral" recommendation in the meantime.
    recommendation: Optional[str] = None
    recommendation_label: Optional[str] = None
    recommendation_color: Optional[str] = None
    ask_amount: Optional[float] = None
    red_flag_count: int = 0
    red_flag_critical_count: int = 0
    needs_review: bool = False


class DashboardActivityItem(BaseModel):
    type: str  # "deck_upload" | "red_flag" | "memo_generated"
    company_id: str
    company_name: str
    text: str
    severity: Optional[str] = None
    at: datetime


class DashboardTotals(BaseModel):
    active_count: int
    total_ask_amount: float
    # How many companies actually contributed a figure to total_ask_amount -
    # the dashboard needs this to say "sur 4 sur 5 dossiers" rather than
    # imply the total covers every company when some stated no ask at all.
    companies_with_ask: int
    prioritized_count: int
    needs_review_count: int


class DashboardSummaryOut(BaseModel):
    companies: list[CompanyDashboardItem]
    totals: DashboardTotals
    recent_activity: list[DashboardActivityItem]
