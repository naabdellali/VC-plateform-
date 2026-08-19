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

from app.models import Company, Deck, ModuleResult, RedFlag, RedFlagSeverity, Memo, Recommendation, Stage
from app.services.calc.parsing import parse_money
from app.services.llm_client import get_llm_client

MODULES_IN_MEMO_ORDER = ["market", "market_dynamics", "competition", "moat", "technology", "traction", "founders"]
MODULE_LABELS = {
    "market": "Taille de marché (TAM / SAM / SOM)",
    "market_dynamics": "Dynamique de marché",
    "competition": "Paysage concurrentiel",
    "moat": "Moat (barrière à l'entrée)",
    "technology": "Technologie",
    "traction": "Traction",
    "founders": "Team & Background",
}

CATEGORY_LABEL_FR = {
    "market": "Marché",
    "market_dynamics": "Marché",
    "competition": "Concurrence",
    "moat": "Moat",
    "technology": "Technologie",
    "traction": "Traction",
    "financial": "Financier",
    "team": "Équipe",
    "founders": "Équipe",
    "business_model": "Business model",
}

_EARLY_STAGES = {Stage.pre_seed, Stage.seed}


def _score_recommendation(module_results: list[ModuleResult], red_flags: list[RedFlag], stage: Stage | None = None) -> tuple[Recommendation, str]:
    """The Recommendation enum stays internal/deterministic (spec section 53: no black-box
    conclusions) - the memo frontend reframes it as a simple "continue analyzing or not" call,
    per analyst feedback that "invest/pass/watchlist" reads like a premature verdict this early.
    Rationale is kept to one short French sentence (or two) - the point is a signal, not an essay."""
    critical = [f for f in red_flags if f.severity == RedFlagSeverity.critical]
    major = [f for f in red_flags if f.severity == RedFlagSeverity.major]
    insufficient = [m for m in module_results if m.status.value == "insufficient_evidence"]

    if critical:
        return Recommendation.pass_, f"{len(critical)} red flag(s) critique(s) identifié(s) - voir la section Red Flags."
    if len(insufficient) > len(module_results) / 2:
        return Recommendation.need_more_data, "Trop peu d'éléments vérifiables pour l'instant - le deck et/ou la data room ne permettent pas de conclure seuls."
    if len(major) >= 2:
        return Recommendation.watchlist, f"{len(major)} red flag(s) majeur(s) à lever avant d'aller plus loin."

    # At pre-seed/seed, precise financial modelling is premature by nature - what actually
    # de-risks the deal at this stage is evidence of product/market fit, not "calculs à
    # compléter" (which reads as a generic, checklist-style non-answer for a company this early).
    if stage in _EARLY_STAGES:
        return Recommendation.need_more_data, (
            "Aucun red flag disqualifiant. À ce stade (early-stage), l'enjeu n'est pas la précision des calculs "
            "financiers mais la preuve du product-market fit : clarté du problème adressé, retours clients réels "
            "et premiers signaux de rétention. C'est ce qu'il faut creuser avant de statuer."
        )
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

        # Market Dynamics: trend + consolidation/M&A as its own short paragraph, distinct from
        # the TAM/SAM/SOM size table right above it and the competitive landscape right below it.
        if module_key == "market_dynamics" and mr.platform_value:
            try:
                dyn = json.loads(mr.platform_value)
            except (ValueError, TypeError):
                dyn = None
            if isinstance(dyn, dict):
                paragraphs = []
                if dyn.get("trend_label"):
                    trend_p = dyn["trend_label"] + "."
                    if dyn.get("trend_reasoning"):
                        trend_p += f" {dyn['trend_reasoning']}"
                    paragraphs.append(trend_p)
                if dyn.get("consolidation"):
                    paragraphs.append(dyn["consolidation"])
                if dyn.get("key_drivers"):
                    paragraphs.append("Facteurs identifiés : " + ", ".join(dyn["key_drivers"]) + ".")
                if paragraphs:
                    sections.append({"title": MODULE_LABELS[module_key], "body": "\n\n".join(paragraphs), "evidence_ids": mr.evidence_ids_json or []})
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
                # One short paragraph per idea (what it is / grade / proprietary / risk), separated
                # by blank lines rather than run-on-comma prose - avoids the "vague and repetitive"
                # read where every sentence started with "Nous avons identifié..."/"Dépendance...".
                paragraphs = []
                if tech.get("tech_summary"):
                    paragraphs.append(tech["tech_summary"])
                if tech.get("tech_grade"):
                    grade_p = f"Niveau technique : {tech['tech_grade']}."
                    if tech.get("tech_grade_reason"):
                        grade_p += f" {tech['tech_grade_reason']}"
                    paragraphs.append(grade_p)
                if tech.get("proprietary"):
                    paragraphs.append(f"Élément(s) propriétaire(s) déclaré(s) : {', '.join(tech['proprietary'])}.")
                deps = tech.get("dependencies") or []
                critical_deps = [d for d in deps if d.get("critical")]
                other_deps = [d for d in deps if not d.get("critical")]
                if critical_deps:
                    dep_bits = [
                        f"{d['name']} — {d['risk_note']}" if d.get("risk_note") else d["name"]
                        for d in critical_deps
                    ]
                    paragraphs.append("Dépendance(s) jugée(s) critique(s) : " + " ; ".join(dep_bits) + ".")
                if other_deps:
                    paragraphs.append("Autre(s) dépendance(s), non critique(s) : " + ", ".join(d["name"] for d in other_deps) + ".")
                if paragraphs:
                    sections.append({"title": MODULE_LABELS[module_key], "body": "\n\n".join(paragraphs), "evidence_ids": mr.evidence_ids_json or []})
                    continue

        body = mr.headline or "Pas encore de conclusion."
        if mr.discrepancy_explanation:
            body += f" | {mr.discrepancy_explanation}"
        sections.append({"title": MODULE_LABELS[module_key], "body": body, "evidence_ids": mr.evidence_ids_json or []})

    SEV_LABEL_FR = {"critical": "Critique", "major": "Majeur", "watch": "À surveiller"}
    SEV_ORDER = {"critical": 0, "major": 1, "watch": 2}
    if red_flags:
        # Grouped by category (Marché, Concurrence, Moat...) rather than one flat list repeating
        # nothing about where each flag came from - each category gets its own short block, worst
        # severity first, so the reader can tell at a glance which part of the diligence is shakiest.
        by_category: dict[str, list[RedFlag]] = {}
        for f in red_flags:
            by_category.setdefault(f.category or "other", []).append(f)
        ordered_cats = sorted(
            by_category.keys(),
            key=lambda c: min(SEV_ORDER.get(f.severity.value, 9) for f in by_category[c]),
        )
        blocks = []
        for cat in ordered_cats:
            cat_flags = sorted(by_category[cat], key=lambda f: SEV_ORDER.get(f.severity.value, 9))
            cat_label = CATEGORY_LABEL_FR.get(cat, cat.replace("_", " ").title())
            narrative = None
            if llm.mode == "live":
                narr_result = llm.narrate_red_flags([{"severity": f.severity.value, "explanation": f.explanation} for f in cat_flags])
                narrative = (narr_result.parsed or {}).get("narrative")
                if narrative:
                    narrative = re.sub(r"^#+\s*", "", narrative.strip())
            if not narrative:
                # Mock mode / narration unavailable: fall back to a plain, honest listing
                # rather than fabricate connective prose we can't actually produce yet.
                narrative = "\n".join(f"[{SEV_LABEL_FR.get(f.severity.value, f.severity.value)}] {f.explanation}" for f in cat_flags)
            blocks.append(f"{cat_label} :\n{narrative}")
        body = "\n\n".join(blocks)
        sections.append({"title": "Red Flags", "body": body, "evidence_ids": [f.evidence_id for f in red_flags if f.evidence_id]})
    else:
        sections.append({"title": "Red Flags", "body": "Aucun red flag identifié par l'analyse automatique.", "evidence_ids": []})

    recommendation, rationale = _score_recommendation(module_results, red_flags, company.stage)
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
            sections.insert(1, {"title": "Executive Summary", "body": description, "evidence_ids": []})

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
