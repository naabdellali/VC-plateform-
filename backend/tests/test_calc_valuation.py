import pytest

from app.services.calc.valuation import implied_valuation_range, project_scenario_value


def test_implied_valuation_range_multiplies_revenue_by_each_bound():
    result = implied_valuation_range(1_000_000, 4.0, 10.0)
    assert result == {"low": 4_000_000, "high": 10_000_000}


def test_implied_valuation_range_swaps_inverted_multiples():
    # A caller passing (high, low) by mistake should not silently produce
    # a "low" bound greater than "high" - this normalizes rather than errors.
    result = implied_valuation_range(1_000_000, 10.0, 4.0)
    assert result == {"low": 4_000_000, "high": 10_000_000}


def test_implied_valuation_range_rejects_negative_revenue():
    with pytest.raises(ValueError):
        implied_valuation_range(-1, 4.0, 10.0)


def test_implied_valuation_range_rejects_negative_multiple():
    with pytest.raises(ValueError):
        implied_valuation_range(1_000_000, -1.0, 10.0)


def test_project_scenario_value_compounds_growth_then_applies_multiple():
    # 1,000,000 EUR at +100%/year for 2 years -> 4,000,000 EUR revenue,
    # then x5 multiple -> 20,000,000 EUR projected value.
    result = project_scenario_value(1_000_000, 1.0, 2, 5.0)
    assert result["projected_revenue"] == pytest.approx(4_000_000)
    assert result["projected_value"] == pytest.approx(20_000_000)


def test_project_scenario_value_handles_zero_years_as_a_no_op():
    result = project_scenario_value(1_000_000, 0.5, 0, 5.0)
    assert result["projected_revenue"] == pytest.approx(1_000_000)
    assert result["projected_value"] == pytest.approx(5_000_000)


def test_project_scenario_value_allows_a_genuine_decline_scenario():
    result = project_scenario_value(1_000_000, -0.20, 1, 5.0)
    assert result["projected_revenue"] == pytest.approx(800_000)


def test_project_scenario_value_rejects_impossible_decline_rate():
    with pytest.raises(ValueError):
        project_scenario_value(1_000_000, -1.0, 2, 5.0)


def test_project_scenario_value_rejects_negative_revenue():
    with pytest.raises(ValueError):
        project_scenario_value(-1, 0.5, 2, 5.0)
