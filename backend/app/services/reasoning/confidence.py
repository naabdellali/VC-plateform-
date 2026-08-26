"""
Deterministic confidence backstop (direct analyst feedback: the platform
was trusting each LLM call's own self-reported confidence label at face
value, with nothing independently checking it against how much
corroborating material it actually had to go on - a model can say
"high confidence" off a single thin source just as easily as off five
corroborating ones).

`cap_confidence_by_source_count` does not replace the model's self-report
- it CAPS it. A call that reports "high" confidence from a single
source is capped down to "low"; the floor is `unverified` when there are
no sources at all. This is deliberately ONE-DIRECTIONAL: it only ever
demotes a reported confidence, never promotes it - a model reporting its
own confidence as low/unverified is very likely right to, and second-
guessing that upward would be exactly the kind of fabricated certainty
this whole product exists to avoid.

This is about EXTERNALLY-sourced research confidence specifically (how
many independent web sources corroborate a synthesized answer) - it is
not applied to confidence about what the deck itself says (e.g.
identify_target_segment's confidence in market_module), since source
count has no bearing on how clearly a document states something.
"""
from app.models import Confidence

_ORDER = [Confidence.unverified, Confidence.low, Confidence.medium, Confidence.high]

# Minimum corroborating source count required to be ALLOWED to reach each
# confidence level - not a claim about how many sources are "enough" in
# any absolute sense, just a floor beneath which a model's own high/medium
# self-report should not be trusted at face value.
_MIN_SOURCES_FOR = {
    Confidence.high: 3,
    Confidence.medium: 2,
    Confidence.low: 1,
    Confidence.unverified: 0,
}


def cap_confidence_by_source_count(reported: Confidence, source_count: int) -> Confidence:
    """Return `reported`, or a lower Confidence level if `source_count` doesn't meet
    the minimum required for `reported`'s level. Never returns a HIGHER confidence
    than `reported`."""
    ceiling = Confidence.unverified
    for level in reversed(_ORDER):
        if source_count >= _MIN_SOURCES_FOR[level]:
            ceiling = level
            break
    return reported if _ORDER.index(reported) <= _ORDER.index(ceiling) else ceiling


def mapped_and_capped_confidence(confidence_str: str | None, source_count: int) -> Confidence:
    """Convenience wrapper for the extremely common call pattern across reasoning
    modules: map an LLM's self-reported "high"/"medium"/"low" string to the
    Confidence enum (defaulting to `unverified` for anything else), then cap it by
    how many sources actually back it."""
    reported = {"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
        confidence_str, Confidence.unverified
    )
    return cap_confidence_by_source_count(reported, source_count)
