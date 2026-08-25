"""
Dashboard aggregation (app/services/dashboard_summary.py) - backs the
redesigned company-list dashboard. Everything it reports must come from
real rows, never a guessed/default status:

1. A company with no Memo generated yet reports recommendation=None (not a
   fabricated "neutral" status) and is excluded from prioritized/needs_review.
2. The ask amount is read from the deck's extracted_claims_json via the same
   extract_ask_amount() the memo document itself uses - one source of truth.
3. Red flag counts (total + critical) are per-company, and a critical flag
   alone is enough to mark a company needs_review even with no memo yet.
4. The recent-activity feed merges deck uploads, red flags and memo
   generations across companies and sorts by real timestamp, newest first.
"""
import json
from datetime import datetime, timedelta

from app.models import Company, Deck, Memo, RedFlag, RedFlagSeverity, Recommendation, Stage, BusinessModel
from app.services.dashboard_summary import build_dashboard_summary


def _make_company(db_session, name, **kwargs):
    company = Company(name=name, stage=Stage.seed, business_model=BusinessModel.saas, **kwargs)
    db_session.add(company)
    db_session.flush()
    return company


def test_company_with_no_memo_has_null_recommendation_and_is_not_prioritized(db_session, sample_company):
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.recommendation is None
    assert item.recommendation_label is None
    assert item.needs_review is False
    assert summary.totals.prioritized_count == 0
    assert summary.totals.needs_review_count == 0


def test_ask_amount_matches_extract_ask_amount_used_by_the_memo(db_session, sample_company, sample_deck):
    # sample_deck's extracted_claims_json has no fundraising_history claim, so
    # this proves the "never fabricate a figure" contract end to end.
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.ask_amount is None
    assert summary.totals.companies_with_ask == 0
    assert summary.totals.total_ask_amount == 0.0


def test_ask_amount_extracted_when_deck_states_one(db_session, sample_company):
    deck = Deck(
        company_id=sample_company.id, filename="deck.pptx", raw_text="",
        extracted_claims_json=[{"category": "fundraising_history", "claim": "Raising EUR 800k seed round", "value": "EUR 800k"}],
    )
    db_session.add(deck)
    db_session.flush()
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.ask_amount == 800_000
    assert summary.totals.companies_with_ask == 1
    assert summary.totals.total_ask_amount == 800_000


def test_recommendation_from_latest_memo_drives_prioritized_and_needs_review_buckets(db_session, sample_company):
    db_session.add(Memo(company_id=sample_company.id, sections_json=[], recommendation=Recommendation.invest))
    db_session.flush()
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.recommendation == "invest"
    assert item.recommendation_label == "Continuer — dossier prioritaire"
    assert item.needs_review is False
    assert summary.totals.prioritized_count == 1


def test_only_the_latest_memo_recommendation_counts(db_session, sample_company):
    older = Memo(company_id=sample_company.id, sections_json=[], recommendation=Recommendation.pass_,
                 generated_at=datetime.utcnow() - timedelta(days=1))
    newer = Memo(company_id=sample_company.id, sections_json=[], recommendation=Recommendation.invest,
                 generated_at=datetime.utcnow())
    db_session.add_all([older, newer])
    db_session.flush()
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.recommendation == "invest"


def test_critical_red_flag_alone_marks_needs_review_even_without_a_memo(db_session, sample_company):
    db_session.add(RedFlag(
        company_id=sample_company.id, category="moat", severity=RedFlagSeverity.critical,
        explanation="Un acteur bien financé occupe déjà ce marché.",
    ))
    db_session.flush()
    summary = build_dashboard_summary(db_session)
    item = next(i for i in summary.companies if i.id == sample_company.id)
    assert item.recommendation is None
    assert item.red_flag_critical_count == 1
    assert item.needs_review is True
    assert summary.totals.needs_review_count == 1


def test_recent_activity_merges_and_sorts_across_companies_newest_first(db_session, sample_company):
    other = _make_company(db_session, "Other Co")
    now = datetime.utcnow()
    db_session.add(Deck(company_id=sample_company.id, filename="a.pptx", uploaded_at=now - timedelta(hours=3)))
    db_session.add(RedFlag(
        company_id=other.id, category="market", severity=RedFlagSeverity.major,
        explanation="...", created_at=now - timedelta(hours=1),
    ))
    db_session.add(Memo(company_id=sample_company.id, sections_json=[], generated_at=now - timedelta(hours=2)))
    db_session.flush()

    summary = build_dashboard_summary(db_session)
    types_in_order = [a.type for a in summary.recent_activity]
    assert types_in_order[0] == "red_flag"  # most recent (1h ago)
    assert types_in_order[1] == "memo_generated"  # 2h ago
    assert types_in_order[2] == "deck_upload"  # 3h ago
    assert summary.recent_activity[0].company_name == "Other Co"
