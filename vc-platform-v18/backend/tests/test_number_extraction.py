"""
Pass A (number recognition) is pure regex, no LLM - so it's fully testable
deterministically. This is the piece the analyst's "€8m could mean revenue,
ARR, funding, TAM, valuation, GMV" example depends on: recognition must
never silently drop a candidate, and must never guess a meaning at this
stage (that's Pass B, tested separately in test_extraction_pipeline.py).
"""
from app.services.number_extraction import extract_number_candidates, structure_number_candidate, guess_period_hint


def test_extracts_currency_prefix_and_suffix_forms():
    text = "--- Slide 1: Traction ---\nARR de 2M€ en decembre 2025, porte par 35 clients payants."
    candidates = extract_number_candidates(text)
    raw = [c.raw_text for c in candidates]
    assert "2M€" in raw
    assert "35 clients" in raw
    # a bare 4-digit year with no currency/%/suffix signal is noise, not a metric
    assert "2025" not in raw


def test_extracts_french_and_english_magnitude_suffixes():
    text = "TAM estime a 64 milliards de dollars, SAM 7.4bn, SOM 740M."
    candidates = {c.raw_text: c for c in extract_number_candidates(text)}
    assert "64 milliards" in candidates
    assert "7.4bn" in candidates
    assert "740M" in candidates


def test_extracts_percentages_and_multiples():
    text = "Croissance de 120% en glissement annuel. Multiple de 3.2x sur le dernier tour."
    raw = [c.raw_text for c in extract_number_candidates(text)]
    assert "120%" in raw
    assert "3.2x" in raw


def test_slide_reference_tracks_nearest_marker():
    text = (
        "--- Slide 3: Marche ---\nTAM de 10M€.\n\n"
        "--- Slide 7: Concurrence ---\nLevee de 3M€."
    )
    by_raw = {c.raw_text: c for c in extract_number_candidates(text)}
    assert by_raw["10M€"].slide_reference == "3"
    assert by_raw["3M€"].slide_reference == "7"


def test_bare_short_numbers_without_signal_are_dropped():
    text = "Voir slide 4 pour plus de details. Contactez-nous au 5."
    candidates = extract_number_candidates(text)
    assert candidates == []


def test_structure_number_candidate_applies_magnitude_and_currency():
    text = "Levee de 3.5M EUR en seed."
    cand = extract_number_candidates(text)[0]
    structured = structure_number_candidate(cand)
    assert structured["value"] == 3_500_000.0
    assert structured["currency"] == "EUR"


def test_structure_number_candidate_recovers_spelled_out_currency():
    text = "TAM estime a 64 milliards de dollars pour ce secteur."
    cand = extract_number_candidates(text)[0]
    structured = structure_number_candidate(cand)
    assert structured["value"] == 64_000_000_000.0
    assert structured["currency"] == "USD"


def test_structure_number_candidate_never_interprets_meaning():
    # Pass A must not decide semantic_category - that's Pass B's job entirely.
    # structure_number_candidate's return dict has no such key at all.
    text = "ARR de 2M€."
    cand = extract_number_candidates(text)[0]
    structured = structure_number_candidate(cand)
    assert "semantic_category" not in structured


def test_guess_period_hint_recognizes_common_period_phrasing():
    assert guess_period_hint("ARR as of December 2025") is not None
    assert guess_period_hint("no date mentioned here at all") is None


def test_slide_label_adjacent_to_year_does_not_fuse_into_a_bogus_number():
    # "Q1 2025" must not be read as a thousands-grouped "1 202" (1202.0) with the
    # trailing "5" silently dropped - a real regression found while building the
    # Phase 1 demo: the digit right after "Q" and the leading 3 digits of the
    # following year were fusing into a spurious candidate.
    text = "Q1 2025: 400K EUR de revenue. Q2 2025: 600K EUR de revenue."
    raw = [c.raw_text for c in extract_number_candidates(text)]
    assert "1 202" not in raw
    assert "2 202" not in raw
    assert "400K EUR" in raw
    assert "600K EUR" in raw


def test_context_window_does_not_cross_a_slide_boundary():
    text = (
        "--- Slide 3: Traction ---\n35 clients payants a ce jour.\n\n"
        "--- Slide 4: Marche ---\nTAM estime a 64 milliards de dollars."
    )
    candidates = {c.raw_text: c for c in extract_number_candidates(text)}
    # the "35 clients" candidate's context must not leak "TAM" from the next slide
    assert "TAM" not in candidates["35 clients"].context
    assert "market" in candidates["35 clients"].context.lower() or "traction" in candidates["35 clients"].context.lower()
