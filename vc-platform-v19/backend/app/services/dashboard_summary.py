"""
Dashboard aggregation: everything the company-list dashboard needs, computed
from real rows (Memo, Deck, RedFlag) - no synthetic/guessed figures.

Kept as a standalone, directly-testable function (rather than inline in the
router) per this codebase's convention of unit-testing reasoning/aggregation
logic against a db_session fixture, with routers staying thin wrappers.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Company, Deck, Memo, RedFlag, RedFlagSeverity
from app.schemas import CompanyDashboardItem, DashboardActivityItem, DashboardTotals, DashboardSummaryOut
from app.services.reasoning.memo_module import CONTINUE_LABEL, CONTINUE_COLOR, extract_ask_amount

_ACTIVITY_FEED_LIMIT = 8
_ACTIVITY_QUERY_LIMIT = 15  # per activity type, before merging + trimming to _ACTIVITY_FEED_LIMIT


def build_dashboard_summary(db: Session) -> DashboardSummaryOut:
    companies = db.query(Company).order_by(Company.created_at.desc()).all()
    company_ids = [c.id for c in companies]
    company_name_by_id = {c.id: c.name for c in companies}

    # Latest Memo/Deck per company - a company can accumulate several of
    # each over time, but the dashboard only ever cares about the newest.
    latest_memo_by_company: dict[str, Memo] = {}
    for memo in db.query(Memo).filter(Memo.company_id.in_(company_ids)).order_by(Memo.generated_at.desc()).all():
        latest_memo_by_company.setdefault(memo.company_id, memo)

    latest_deck_by_company: dict[str, Deck] = {}
    for deck in db.query(Deck).filter(Deck.company_id.in_(company_ids)).order_by(Deck.uploaded_at.desc()).all():
        latest_deck_by_company.setdefault(deck.company_id, deck)

    flag_count_by_company: dict[str, int] = {}
    critical_count_by_company: dict[str, int] = {}
    for f in db.query(RedFlag).filter(RedFlag.company_id.in_(company_ids)).all():
        flag_count_by_company[f.company_id] = flag_count_by_company.get(f.company_id, 0) + 1
        if f.severity == RedFlagSeverity.critical:
            critical_count_by_company[f.company_id] = critical_count_by_company.get(f.company_id, 0) + 1

    items: list[CompanyDashboardItem] = []
    total_ask = 0.0
    companies_with_ask = 0
    prioritized_count = 0
    needs_review_count = 0
    for c in companies:
        memo = latest_memo_by_company.get(c.id)
        deck = latest_deck_by_company.get(c.id)
        # None (not a guessed default) until a memo has actually been generated.
        rec_value = memo.recommendation.value if memo and memo.recommendation else None
        ask_amount = extract_ask_amount(deck)
        red_count = flag_count_by_company.get(c.id, 0)
        critical_count = critical_count_by_company.get(c.id, 0)
        needs_review = critical_count > 0 or rec_value in ("watchlist", "pass")

        if ask_amount:
            total_ask += ask_amount
            companies_with_ask += 1
        if rec_value == "invest":
            prioritized_count += 1
        if needs_review:
            needs_review_count += 1

        items.append(CompanyDashboardItem(
            id=c.id, name=c.name, sector=c.sector, industry_tag=c.industry_tag,
            stage=c.stage.value, business_model=c.business_model.value,
            recommendation=rec_value,
            recommendation_label=CONTINUE_LABEL.get(rec_value) if rec_value else None,
            recommendation_color=CONTINUE_COLOR.get(rec_value) if rec_value else None,
            ask_amount=ask_amount, red_flag_count=red_count, red_flag_critical_count=critical_count,
            needs_review=needs_review,
        ))

    # Recent activity: three real, timestamped signal types merged and sorted -
    # nothing synthetic (no fabricated trend/sparkline data anywhere here).
    activity: list[DashboardActivityItem] = []
    for deck in (
        db.query(Deck).filter(Deck.company_id.in_(company_ids))
        .order_by(Deck.uploaded_at.desc()).limit(_ACTIVITY_QUERY_LIMIT).all()
    ):
        name = company_name_by_id.get(deck.company_id, "?")
        activity.append(DashboardActivityItem(
            type="deck_upload", company_id=deck.company_id, company_name=name,
            text=f"Deck déposé pour {name}", severity=None, at=deck.uploaded_at,
        ))
    for f in (
        db.query(RedFlag).filter(RedFlag.company_id.in_(company_ids))
        .order_by(RedFlag.created_at.desc()).limit(_ACTIVITY_QUERY_LIMIT).all()
    ):
        name = company_name_by_id.get(f.company_id, "?")
        activity.append(DashboardActivityItem(
            type="red_flag", company_id=f.company_id, company_name=name,
            text=f"Nouveau red flag ({f.severity.value}) sur {name}", severity=f.severity.value, at=f.created_at,
        ))
    for memo in (
        db.query(Memo).filter(Memo.company_id.in_(company_ids))
        .order_by(Memo.generated_at.desc()).limit(_ACTIVITY_QUERY_LIMIT).all()
    ):
        name = company_name_by_id.get(memo.company_id, "?")
        activity.append(DashboardActivityItem(
            type="memo_generated", company_id=memo.company_id, company_name=name,
            text=f"Mémo généré pour {name}", severity=None, at=memo.generated_at,
        ))
    activity.sort(key=lambda a: a.at, reverse=True)

    return DashboardSummaryOut(
        companies=items,
        totals=DashboardTotals(
            active_count=len(companies), total_ask_amount=total_ask, companies_with_ask=companies_with_ask,
            prioritized_count=prioritized_count, needs_review_count=needs_review_count,
        ),
        recent_activity=activity[:_ACTIVITY_FEED_LIMIT],
    )
