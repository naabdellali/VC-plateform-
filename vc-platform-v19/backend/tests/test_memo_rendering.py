"""
Memo document rendering - targeted regression tests for a batch of analyst
feedback on the downloadable investment memo:

1. The Technology section had a literal "(s)" grammar artifact (e.g.
   "Élément(s) propriétaire(s) déclaré(s)") instead of correct French -
   fixed to plain, always-plural French labels.
2. Proprietary elements must render as written PROSE (proprietary_narrative),
   not a bare comma-joined tag list - the tags stay a separate, UI-only field.
3. Critical dependencies must render as an actual bullet list ("• " per
   line), not run-in prose joined by " ; ".
4. Moat must come AFTER Technology in the memo's section order, since a
   moat judgment is downstream of the technology read.
5. The Founders section previously had NO dedicated renderer at all and
   silently fell through to a one-line headline - it must now show the
   named founders plus the team-fit/synergy assessment.
6. The early-stage recommendation rationale should not parenthetically
   restate "(early-stage)" - the reader already knows the company's stage
   from the header chips.

These are pure rendering/ordering checks against directly-constructed
ModuleResult rows - no LLM call involved, so they run regardless of
mock/live mode.
"""
import json

from app.models import Company, Deck, ModuleResult, ModuleStatus, Stage
from app.services.reasoning import memo_module
from app.services.reasoning.memo_module import MODULES_IN_MEMO_ORDER


def _set_module_result(db_session, company, module, *, status=ModuleStatus.needs_review, headline=None, platform_value=None):
    mr = ModuleResult(
        company_id=company.id, module=module, status=status, headline=headline,
        deck_value=None, platform_value=platform_value, discrepancy_explanation=None,
        reasoning_json={"steps": []}, evidence_ids_json=[], llm_mode="live",
    )
    db_session.add(mr)
    db_session.flush()
    return mr


def _section(memo, title):
    return next(s for s in memo.sections_json if s["title"] == title)


def test_moat_comes_after_technology_in_memo_order():
    assert MODULES_IN_MEMO_ORDER.index("technology") < MODULES_IN_MEMO_ORDER.index("moat")


def test_technology_section_renders_prose_narrative_and_bullet_critical_deps(db_session, sample_company, sample_deck):
    tech_payload = {
        "tech_summary": "Moteur de scoring propriétaire entraîné sur des données propriétaires.",
        "proprietary_narrative": "Le moteur de scoring combine plusieurs signaux propriétaires pour estimer le risque.",
        "proprietary": ["moteur de scoring propriétaire"],
        "dependencies": [
            {"name": "AWS", "risk_note": "Dépendance d'infrastructure critique.", "critical": True},
            {"name": "Stripe", "risk_note": "Paiement, remplaçable.", "critical": False},
        ],
        "tech_grade": "Intermédiaire", "tech_grade_reason": "Architecture solide mais réplicable.",
    }
    _set_module_result(db_session, sample_company, "technology", platform_value=json.dumps(tech_payload))
    db_session.commit()

    memo = memo_module.generate_memo(db_session, sample_company)
    tech_section = _section(memo, memo_module.MODULE_LABELS["technology"])

    # No literal "(s)" grammar artifact anywhere in the rendered body.
    assert "(s)" not in tech_section["body"]
    # Proprietary elements rendered as the written prose, not a tag join.
    assert tech_payload["proprietary_narrative"] in tech_section["body"]
    # Critical dependency rendered as an actual bullet line.
    assert "• AWS" in tech_section["body"]
    # Non-critical dependency still listed, but not bulleted the same way.
    assert "Stripe" in tech_section["body"]


def test_technology_section_falls_back_to_plain_tag_listing_without_narrative(db_session, sample_company, sample_deck):
    # Older/mock-mode result with no proprietary_narrative field at all - must still
    # render grammatically correct French, never the "(s)" artifact.
    tech_payload = {
        "tech_summary": None, "proprietary_narrative": None,
        "proprietary": ["algorithme propriétaire"], "dependencies": [], "tech_grade": None, "tech_grade_reason": None,
    }
    _set_module_result(db_session, sample_company, "technology", platform_value=json.dumps(tech_payload))
    db_session.commit()

    memo = memo_module.generate_memo(db_session, sample_company)
    tech_section = _section(memo, memo_module.MODULE_LABELS["technology"])
    assert "(s)" not in tech_section["body"]
    assert "Éléments propriétaires déclarés" in tech_section["body"]


def test_founders_section_renders_named_founders_and_team_fit_assessment(db_session, sample_company, sample_deck):
    founders_payload = {
        "founders": [
            {"name": "Jane Doe", "title": "CEO", "status": "unverified", "status_label": "Non vérifié indépendamment"},
            {"name": "John Smith", "title": "CTO", "status": "positive", "status_label": "Background check : positif"},
        ],
        "team_fit_assessment": "Les deux profils se complètent : une dirigeante commerciale et un CTO technique.",
    }
    _set_module_result(db_session, sample_company, "founders", platform_value=json.dumps(founders_payload))
    db_session.commit()

    memo = memo_module.generate_memo(db_session, sample_company)
    founders_section = _section(memo, memo_module.MODULE_LABELS["founders"])
    assert "Jane Doe" in founders_section["body"]
    assert "John Smith" in founders_section["body"]
    assert founders_payload["team_fit_assessment"] in founders_section["body"]


def test_early_stage_recommendation_rationale_does_not_mention_early_stage_parenthetical(db_session, sample_company, sample_deck):
    sample_company.stage = Stage.seed
    db_session.commit()
    memo = memo_module.generate_memo(db_session, sample_company)
    rec_section = _section(memo, "Faut-il continuer ?")
    assert "(early-stage)" not in rec_section["body"]
