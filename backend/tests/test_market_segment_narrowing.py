"""
Market module: precise target-segment identification. This exists because
of direct analyst feedback that TAM/SAM/SOM was being sized against a
broad category (e.g. "insurance software") instead of the company's
actual niche (e.g. "parametric underwriting software for agricultural
insurers") - `company.sector` alone, whether typed by the analyst or
inferred from the deck, was the only thing ever searched for.

Three things this must prove:
1. identify_target_segment always runs (even when `sector` is a plain,
   analyst-typed broad category) and its result reaches the search query
   AND the context passed to estimate_tam_sam_som - not just recorded
   and ignored.
2. When the deck doesn't support narrowing beyond the broad category,
   the module falls back to the old sector-only behavior rather than
   crashing or inventing a fake segment.
3. `sector` is never dropped - it still appears as an explicit fallback/
   adjacent-market query even when a segment was identified.
"""
from app.models import ModuleResult, ModuleStatus
from app.services.llm_client import get_llm_client, LlmResult
from app.services.search_client import get_search_client, SearchResponse, SearchResult
from app.services.reasoning import market_module


def test_segment_description_drives_the_primary_tam_query(db_session, sample_company, sample_deck, monkeypatch):
    llm = get_llm_client()
    monkeypatch.setattr(llm, "identify_target_segment", lambda *a, **k: LlmResult(
        mode="live", text="stub",
        parsed={
            "segment_description": "logiciels de gestion des notes de frais pour PME du secteur du conseil",
            "buyer_persona": "DAF de cabinets de conseil de 50 à 500 salariés",
            "confidence": "high",
        },
    ))

    seen_queries = {}
    search = get_search_client()

    def fake_search(query, max_results=4):
        seen_queries.setdefault("queries", []).append(query)
        return SearchResponse(mode="live", query=query, results=[
            SearchResult(title="Segment report", url="https://example.com/segment", content="Segment-specific market data."),
        ])

    monkeypatch.setattr(search, "search", fake_search)

    seen_context = {}

    def fake_estimate(context, sources):
        seen_context.update(context)
        return LlmResult(mode="live", text="stub", parsed={"insufficient": True, "reason": "stub - test only checks query/context wiring"})

    monkeypatch.setattr(llm, "estimate_tam_sam_som", fake_estimate)

    market_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    # The segment description (not just the broad sector) actually reached a search query.
    assert any("notes de frais" in q for q in seen_queries["queries"])
    # ... and the broad sector is still searched for too, as the explicit fallback anchor.
    assert any(sample_company.sector in q for q in seen_queries["queries"])
    # ... and estimate_tam_sam_som received the segment in its context, not just the module.
    assert seen_context["segment_description"] == "logiciels de gestion des notes de frais pour PME du secteur du conseil"
    assert seen_context["buyer_persona"] == "DAF de cabinets de conseil de 50 à 500 salariés"

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="market").one()
    assert result.status in (ModuleStatus.insufficient_evidence, ModuleStatus.complete)  # ran without crashing


def test_falls_back_to_sector_only_query_when_deck_does_not_support_narrowing(db_session, sample_company, sample_deck, monkeypatch):
    llm = get_llm_client()
    monkeypatch.setattr(llm, "identify_target_segment", lambda *a, **k: LlmResult(
        mode="live", text="stub", parsed={"segment_description": None, "buyer_persona": None, "confidence": "unverified"},
    ))

    seen_queries = {}
    search = get_search_client()

    def fake_search(query, max_results=4):
        seen_queries.setdefault("queries", []).append(query)
        return SearchResponse(mode="live", query=query, results=[])

    monkeypatch.setattr(search, "search", fake_search)

    market_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    # No segment identified -> behaves exactly like before: sector-only queries, no crash,
    # and no fabricated segment string anywhere in the queries.
    assert all(sample_company.sector in q or "North America" in q for q in seen_queries["queries"])

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="market").one()
    assert result.status == ModuleStatus.insufficient_evidence  # no search results -> honest, not fabricated


def test_segment_identification_runs_even_when_sector_was_manually_typed(db_session, sample_company, sample_deck, monkeypatch):
    # Simulates the exact analyst complaint: sector was typed in the upload form as a broad
    # category, not inferred from the deck - the narrowing step must still run.
    sample_company.sector = "logiciel d'assurance"
    db_session.flush()

    llm = get_llm_client()
    calls = {"count": 0}

    def fake_identify_target_segment(deck_text, sector):
        calls["count"] += 1
        assert sector == "logiciel d'assurance"
        return LlmResult(mode="live", text="stub", parsed={"segment_description": None, "buyer_persona": None, "confidence": "unverified"})

    monkeypatch.setattr(llm, "identify_target_segment", fake_identify_target_segment)

    market_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    assert calls["count"] == 1
