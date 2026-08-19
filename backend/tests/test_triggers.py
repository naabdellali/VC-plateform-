"""
Unit tests for the trigger/signal engine (services/reasoning/triggers.py) -
the "store the triggers, not just the questions" primitive from the VC
Expert Questioning Framework. Tested in isolation from any module so the
registry's own behavior (matching, template-filling, bounding) is verified
independently of the Technology module pilot.
"""
from app.services.reasoning.triggers import Signal, evaluate, MAX_ACTIVATIONS_PER_CALL


def test_matching_signal_fires_and_fills_in_the_detail():
    signals = [Signal(name="third_party_tech_dependency", value=True, detail="OpenAI API", source_module="technology")]
    activations = evaluate(signals)

    assert len(activations) == 1
    act = activations[0]
    assert act["detail"] == "OpenAI API"
    assert "moat" in act["activates"]
    assert any("OpenAI API" in q for q in act["research_questions"])
    assert any("OpenAI API" in q for q in act["founder_questions"])


def test_non_matching_signal_name_does_not_fire():
    signals = [Signal(name="unrelated_signal", value=True, detail="n/a", source_module="technology")]
    assert evaluate(signals) == []


def test_falsy_value_does_not_pass_the_predicate():
    signals = [Signal(name="third_party_tech_dependency", value=False, detail="OpenAI API", source_module="technology")]
    assert evaluate(signals) == []


def test_activations_are_bounded_to_control_cost():
    signals = [
        Signal(name="third_party_tech_dependency", value=True, detail=f"Provider {i}", source_module="technology")
        for i in range(10)
    ]
    activations = evaluate(signals)
    assert len(activations) <= MAX_ACTIVATIONS_PER_CALL
