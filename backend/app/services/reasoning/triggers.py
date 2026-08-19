"""
Trigger/signal engine - the "the platform thinks, not checklists" primitive
from the VC Expert Questioning Framework.

The framework's explicit instruction: "Do not store only the questions.
Store the triggers." A reasoning module, having grounded a fact in real
evidence (e.g. a named third-party API dependency actually found in the
deck), emits a Signal. This registry maps that signal to what it implies
elsewhere - which OTHER modules' territory it has consequences for, which
follow-up questions are concretely researchable (get a real grounded
search + LLM-synthesis pass, same as any module's normal research step),
and which are pure judgment calls that no search can verify (surfaced as
founder/analyst questions instead of pretend-verified facts).

Deliberately small and declarative for this first pass (one entry, piloted
on the Technology module - see technology_module.py). The intent is that
this registry grows as each new dimension (Product, Timing, Geography,
Macro) is added, rather than each module re-implementing its own ad hoc
cross-module logic.

Bounded on purpose: `evaluate()` caps how many activations fire per call,
because every activation can spawn a real web-search + LLM call downstream
- unbounded triggering would make a single deck upload arbitrarily slow
and expensive. Callers should treat this as a deliberate cost/latency
guard, not an oversight.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

MAX_ACTIVATIONS_PER_CALL = 4


@dataclass
class Signal:
    """A grounded fact a module discovered - not speculation. `detail` is
    the concrete value (e.g. the dependency's actual name) that gets
    interpolated into the trigger's question templates below."""
    name: str
    value: Any
    detail: str
    source_module: str
    evidence_id: str | None = None


@dataclass
class Trigger:
    signal_name: str
    predicate: Callable[[Any], bool]
    rationale: str
    # Modules whose conclusion this signal has implications for. This does
    # NOT rewrite that module's own output - it surfaces a cross-module
    # pointer (typically a red flag tagged with that module's category) so
    # the connection is visible without one module silently overwriting
    # another's independently-reasoned conclusion.
    activates: list[str]
    # Concrete, independently researchable follow-up questions - each gets
    # a real grounded search + LLM-synthesis pass, restricted to retrieved
    # sources, exactly like any module's normal research step.
    research_questions: list[str] = field(default_factory=list)
    # Judgment questions no search can verify - become founder/analyst
    # questions (key_questions_json in the memo), never asserted as fact.
    founder_questions: list[str] = field(default_factory=list)


TRIGGER_REGISTRY: list[Trigger] = [
    Trigger(
        signal_name="third_party_tech_dependency",
        predicate=lambda v: bool(v),
        rationale=(
            "Une dépendance technique tierce critique peut affaiblir le moat (la brique n'est pas "
            "propriétaire), exposer la marge brute au pricing du fournisseur, et créer un risque "
            "concurrentiel si le fournisseur lance une fonctionnalité concurrente."
        ),
        activates=["moat", "competition"],
        research_questions=[
            "Quelles alternatives existent à {dep}, et comment se comparent-elles en prix et en capacités ?",
        ],
        founder_questions=[
            "Quelle part du produit dépend réellement de {dep} ?",
            "Que devient la marge brute si le prix de {dep} double ?",
            "Le fournisseur de {dep} pourrait-il lancer une fonctionnalité directement concurrente ?",
        ],
    ),
]


def evaluate(signals: list[Signal]) -> list[dict]:
    """Match emitted signals against the registry. Returns a bounded list of
    activation dicts, each with the trigger's question templates already
    filled in with the signal's concrete detail."""
    activations: list[dict] = []
    for sig in signals:
        for trig in TRIGGER_REGISTRY:
            if trig.signal_name != sig.name or not trig.predicate(sig.value):
                continue
            activations.append({
                "signal": sig.name,
                "detail": sig.detail,
                "source_module": sig.source_module,
                "rationale": trig.rationale,
                "activates": trig.activates,
                "research_questions": [q.format(dep=sig.detail) for q in trig.research_questions],
                "founder_questions": [q.format(dep=sig.detail) for q in trig.founder_questions],
            })
            if len(activations) >= MAX_ACTIVATIONS_PER_CALL:
                return activations
    return activations
