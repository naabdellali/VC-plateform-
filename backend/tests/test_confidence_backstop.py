import pytest

from app.models import Confidence
from app.services.reasoning.confidence import cap_confidence_by_source_count, mapped_and_capped_confidence


@pytest.mark.parametrize("reported,source_count,expected", [
    (Confidence.high, 3, Confidence.high),      # meets the minimum - not capped
    (Confidence.high, 5, Confidence.high),      # more sources than required - still high
    (Confidence.high, 2, Confidence.medium),    # one short of high's minimum - capped down
    (Confidence.high, 1, Confidence.low),
    (Confidence.high, 0, Confidence.unverified),
    (Confidence.medium, 2, Confidence.medium),  # meets medium's minimum
    (Confidence.medium, 1, Confidence.low),     # capped down
    (Confidence.medium, 0, Confidence.unverified),
    (Confidence.low, 1, Confidence.low),
    (Confidence.low, 0, Confidence.unverified),
])
def test_cap_confidence_demotes_when_source_count_is_insufficient(reported, source_count, expected):
    assert cap_confidence_by_source_count(reported, source_count) == expected


@pytest.mark.parametrize("reported,source_count", [
    (Confidence.low, 10),         # a model reporting LOW itself is never promoted, even with many sources
    (Confidence.unverified, 10),  # same for unverified
    (Confidence.medium, 100),
])
def test_cap_confidence_never_promotes_a_models_own_report(reported, source_count):
    assert cap_confidence_by_source_count(reported, source_count) == reported


def test_mapped_and_capped_confidence_maps_string_then_caps():
    assert mapped_and_capped_confidence("high", 1) == Confidence.low
    assert mapped_and_capped_confidence("high", 3) == Confidence.high


def test_mapped_and_capped_confidence_defaults_unknown_strings_to_unverified():
    assert mapped_and_capped_confidence("bogus", 10) == Confidence.unverified
    assert mapped_and_capped_confidence(None, 10) == Confidence.unverified
