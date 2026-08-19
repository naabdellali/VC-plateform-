"""
Investment memo synthesis (spec section 22-23, 26).

Deliberately template-driven, not "one LLM call writes the memo": every
section is assembled from ModuleResult/Evidence/RedFlag rows that already
exist and are already sourced. The LLM is only used (in live mode) to
smooth the executive-summary prose - it is given the already-verified
structured findings as its only input, and forbidden from introducing new
numbers, per spec section 22 ("the thesis must incorporate the findings of
the entire platform," not invent new ones).

The recommendation itself is produced by a deterministic rule over
red-flag severities and module completeness, not asked of the LLM
directly - consistent with spec section 53 ("no black box conclusions").
"""
from __future__ import annotations

import json
import re

from sqlalchemy.orm import Session

from app.models import Company, Deck, ModuleResult, RedFlag, RedFlagSeverity, Memo, Recommendation
from app.services.calc.parsing import parse_money
from app.services.llm_client import get_llm_client

MODULES_IN_MEMO_ORDER = ["market", "competition", "moat", "technology", "traction", "founders"]
MODULE_LABELS = {
    "market": "Taille de marché (TAM / SAM / SOM)",
    "competition": "Paysage concurrentiel",
    "moat": "Moat (barrière à l'entrée)",
    "technology": "Technologie",
    "traction": "Traction",
    "founders": "Team & Background",
}


def _score_recommendation(module_results: list[ModuleResult], red_flags: list[RedFlag]) -> tuple[Recommendation, str]:
    """The Recommendation enum stays internal/deterministic (spec section 53: no black-box
    conclusions) - the memo frontend reframes it as a simple "continue analyzing or not" call,
    per analyst feedback that "invest/pass/watchlist" reads like a premature verdict this early.
    Rationale is kept to one short French sentence - the point is a signal, not a essay."""
    critical = [f for f in red_flags if f.severity == RedFlagSeverity.critical]
    major = [f for f in red_flags if f.severity == RedFlagSeverity.major]
    insufficient = [m for m in module_results if m.status.value == "insufficient_evidence"]

    if critical:
        return Recommendation.pass_, f"{len(critical)} red flag(s) critique(s) identifié(s) - voir la section Red Flags."
    if len(insufficient) > len(module_results) / 2:
        return Recommendation.need_more_data, "Trop peu d'éléments vérifiables pour l'instant - le deck et/ou la data room ne permettent pas de conclure seuls."
    if len(major) >= 2:
        return Recommendation.watchlist, f"{len(major)} red flag(s) majeur(s) à lever avant d'aller plus loin."
    return Recommendation.need_more_data, "Aucun red flag disqualifiant, mais des calculs clés restent à compléter avec des données analyste (marché, MRR, CAC/LTV)."


def generate_memo(db: Session, company: Company) -> Memo:
    llm = get_llm_client()

    module_results = (
        db.query(ModuleResult)
        .filter(ModuleResult.company_id == company.id)
        .all()
    )
    red_flags = (
        db.query(RedFlag)
        .filter(RedFlag.company_id == company.id)
        .order_by(RedFlag.severity)
        .all()
    )
    by_module = {m.module: m for m in module_results}
    deck = db.query(Deck).filter_by(company_id=company.id).order_by(Deck.uploaded_at.desc()).first()

    # Ask amount, if the deck states one - deliberately deck-derived, not invented; omitted
    # entirely (not shown as "n/a") if nothing was extracted, per "never fabricate a figure."
    ask_amount = None
    if deck and deck.extracted_claims_json:
        for c in deck.extracted_claims_json:
            if c.get("category") == "fundraising_history":
                ask_amount = parse_money(c.get("value") or c.get("claim", ""))
                if ask_amount:
                    break

    overview_tags = [t for t in [
        company.industry_tag or (company.sector.split(",")[0][:24] if company.sector else None),
        company.stage.value.replace("_", " ").title() if company.stage else None,
        f"Ask {ask_amount:,.0f} EUR".replace(",", " ") if ask_amount else None,
    ] if t]

    sections = [
        {"title": "Aperçu", "kind": "overview_tags", "data": {"tags": overview_tags}, "body": "", "evidence_ids": []}
    ]

    for module_key in MODULES_IN_MEMO_ORDER:
        mr = by_module.get(module_key)
        if not mr:
            sections.append({"title": MODULE_LABELS[module_key], "body": "Non analysé.", "evidence_ids": []})
            continue

        # Market and competition carry a structured, document-ready payload (TAM/SAM/SOM table
        # and reasoning, or the function x geography landscape matrix) - embed it directly so the
        # memo reads like the analyst document it should be, not a one-line status string.
        structured = None
        if module_key == "market" and mr.platform_value:
            try:
                parsed = json.loads(mr.platform_value)
                if isinstance(parsed, dict) and parsed.get("tam") and parsed.get("sam") and parsed.get("som"):
                    structured = parsed
            except (ValueError, TypeError):
                pass
        elif module_key == "competition" and mr.platform_value:
            try:
                parsed = json.loads(mr.platform_value)
                if isinstance(parsed, dict) and parsed.get("matrix"):
                    structured = parsed
            except (ValueError, TypeError):
                pass
        elif module_key == "moat" and mr.platform_value:
            try:
                parsed = json.loads(mr.platform_value)
                if isinstance(parsed, dict) and parsed.get("grade"):
                    structured = parsed
            except (ValueError, TypeError):
                pass

        if structured:
            kind = {"market": "tam_sam_som", "competition": "competitive_landscape", "moat": "moat"}[module_key]
            sections.append({"title": MODULE_LABELS[module_key], "kind": kind, "data": structured, "body": "", "evidence_ids": mr.evidence_ids_json or []})
            continue

        # Technology: describe what the tech actually IS before mentioning any
        # dependency - leading with "critical dependency" with no context read
        # as alarmist and left the reader with no idea what the product does.
        if module_key == "technology" and mr.platform_value:
            try:
                tech = json.loads(mr.platform_value)
            except (ValueError, TypeError):
                tech = None
            if isinstance(tech, dict):
                parts = []
                if tech.get("tech_summary"):
                    parts.append(tech["tech_summary"])
                if tech.get("proprietary"):
                    parts.append(f"Ils sont propriétaires de : {', '.join(tech['proprietary'])}.")
                critical_deps = [d["name"] for d in (tech.get("dependencies") or []) if d.get("critical")]
                other_deps = [d["name"] for d in (tech.get("dependencies") or []) if not d.get("critical")]
                if critical_deps:
                    parts.append(f"Nous avons identifié une dépendance potentiellement critique à : {', '.join(critical_deps)}.")
                if other_deps:
                    parts.append(f"Dépendance(s) non critique(s) : {', '.join(other_deps)}.")
                if parts:
                    sections.append({"title": MODULE_LABELS[module_key], "body": " ".join(parts), "evidence_ids": mr.evidence_ids_json or []})
                    continue

        body = mr.headline or "Pas encore de conclusion."
        if mr.discrepancy_explanation:
            body += f" | {mr.discrepancy_explanation}"
        sections.append({"title": MODULE_LABELS[module_key], "body": body, "evidence_ids": mr.evidence_ids_json or []})

    SEV_LABEL_FR = {"critical": "Critique", "major": "Majeur", "watch": "À surveiller"}
    if red_flags:
        narrative = None
        if llm.mode == "live":
            narr_result = llm.narrate_red_flags([{"severity": f.severity.value, "explanation": f.explanation} for f in red_flags])
            narrative = (narr_result.parsed or {}).get("narrative")
            if narrative:
                narrative = re.sub(r"^#+\s*", "", narrative.strip())
        if narrative:
            body = narrative
        else:
            # Mock mode / narration unavailable: fall back to a plain, honest listing
            # rather than fabricate connective prose we can't actually produce yet.
            flag_lines = [f"[{SEV_LABEL_FR.get(f.severity.value, f.severity.value)}] {f.explanation}" for f in red_flags]
            body = "\n".join(flag_lines)
        sections.append({"title": "Red Flags", "body": body, "evidence_ids": [f.evidence_id for f in red_flags if f.evidence_id]})
    else:
        sections.append({"title": "Red Flags", "body": "Aucun red flag identifié par l'analyse automatique.", "evidence_ids": []})

    recommendation, rationale = _score_recommendation(module_results, red_flags)
    CONTINUE_LABEL = {
        "invest": "Continuer — dossier prioritaire",
        "pass": "Ne pas continuer",
        "watchlist": "Continuer, avec vigilance",
        "need_more_data": "Continuer — données manquantes",
    }
    sections.append({
        "title": "Faut-il continuer ?",
        "kind": "recommendation", "body": rationale,
        "data": {"label": CONTINUE_LABEL.get(recommendation.value, recommendation.value), "value": recommendation.value},
        "evidence_ids": [],
    })

    # Key questions: pulled from red flags' resolving_information + each
    # module's "identify_unknowns" trace step - never generic boilerplate.
    key_questions = []
    for f in red_flags:
        if f.resolving_information:
            key_questions.append(f.resolving_information)
    for mr in module_results:
        steps = (mr.reasoning_json or {}).get("steps", [])
        for s in steps:
            if s["step"] == "identify_unknowns":
                content = s["content"]
                if isinstance(content, list):
                    key_questions.extend(content)

    if llm.mode == "live" and deck and deck.raw_text:
        # Deliberately fed ONLY a plain company description (see describe_company) - not the
        # market/competition sections - so the executive summary introduces the company, not a
        # market-size number or a competitive-intensity label that belong in their own sections.
        desc_result = llm.describe_company(deck.raw_text)
        description = (desc_result.parsed or {}).get("description")
        if description:
            # Defensive: strip any stray markdown heading/fence the model might emit despite
            # being told not to, so it never renders as a literal "#" in the document.
            description = re.sub(r"^#+\s*", "", description.strip())
            sections.insert(1, {"title": "Résumé", "body": description, "evidence_ids": []})

    memo = Memo(
        company_id=company.id,
        version="v1",
        sections_json=sections,
        recommendation=recommendation,
        key_questions_json=key_questions[:15],
    )
    db.add(memo)
    db.flush()
    return memo
