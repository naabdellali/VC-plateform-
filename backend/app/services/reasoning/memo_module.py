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

from sqlalchemy.orm import Session

from app.models import Company, ModuleResult, RedFlag, RedFlagSeverity, Memo, Recommendation
from app.services.llm_client import get_llm_client

MODULES_IN_MEMO_ORDER = ["market", "competition", "traction", "founders"]
MODULE_LABELS = {
    "market": "Market",
    "competition": "Competition & Moat",
    "traction": "Traction & Business Model",
    "founders": "Team & Background",
}


def _score_recommendation(module_results: list[ModuleResult], red_flags: list[RedFlag]) -> tuple[Recommendation, str]:
    critical = [f for f in red_flags if f.severity == RedFlagSeverity.critical]
    major = [f for f in red_flags if f.severity == RedFlagSeverity.major]
    insufficient = [m for m in module_results if m.status.value == "insufficient_evidence"]

    if critical:
        return Recommendation.pass_, f"{len(critical)} critical red flag(s) identified - see Red Flags section."
    if len(insufficient) > len(module_results) / 2:
        return Recommendation.need_more_data, "Most modules lack sufficient evidence to reach a conclusion - deck and/or data room provide too little to verify independently."
    if len(major) >= 2:
        return Recommendation.watchlist, f"{len(major)} major red flag(s) require resolution before this can be underwritten."
    return Recommendation.need_more_data, "No disqualifying red flags found, but key independent calculations (market recalculation, MRR quality, CAC/LTV consistency) still require analyst-submitted inputs to complete - see module-level 'needs_review' items."


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

    sections = [
        {
            "title": "Company Overview",
            "body": f"{company.name} - stage: {company.stage.value}, business model: {company.business_model.value}, sector: {company.sector or 'n/a'}, HQ: {company.hq_country or 'n/a'}.",
            "evidence_ids": [],
        }
    ]

    for module_key in MODULES_IN_MEMO_ORDER:
        mr = by_module.get(module_key)
        if not mr:
            sections.append({"title": MODULE_LABELS[module_key], "body": "Not yet analyzed.", "evidence_ids": []})
            continue
        body = mr.headline or "No conclusion yet."
        if mr.discrepancy_explanation:
            body += f" | {mr.discrepancy_explanation}"
        body += f" [status: {mr.status.value}]"
        sections.append({"title": MODULE_LABELS[module_key], "body": body, "evidence_ids": mr.evidence_ids_json or []})

    if red_flags:
        flag_lines = [f"[{f.severity.value.upper()}] ({f.category}) {f.explanation}" for f in red_flags]
        sections.append({"title": "Red Flags", "body": "\n".join(flag_lines), "evidence_ids": [f.evidence_id for f in red_flags if f.evidence_id]})
    else:
        sections.append({"title": "Red Flags", "body": "No red flags identified by the automated pass.", "evidence_ids": []})

    recommendation, rationale = _score_recommendation(module_results, red_flags)
    sections.append({"title": "Recommendation", "body": f"{recommendation.value.upper()} - {rationale}", "evidence_ids": []})

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

    if llm.mode == "live" and sections:
        exec_summary = llm.reason(
            system=(
                "You write a concise executive summary paragraph (max 120 words) for a VC investment memo. "
                "You may ONLY use the facts given to you below - do not add any number, claim, or fact not present in them."
            ),
            user="\n".join(f"{s['title']}: {s['body']}" for s in sections),
        )
        if exec_summary.text and exec_summary.mode == "live":
            sections.insert(1, {"title": "Executive Summary", "body": exec_summary.text.strip(), "evidence_ids": []})

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
