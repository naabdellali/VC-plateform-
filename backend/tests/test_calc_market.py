import pytest

from app.services.calc.market import tam_bottom_up, tam_top_down, compare_estimates
from app.services.calc.finance import cagr


def test_tam_bottom_up_basic():
    est = tam_bottom_up(
        num_potential_customers=50_000,
        avg_annual_spend_eur=2_000,
        realistic_penetration=0.3,
        assumptions=["30% realistic penetration based on comparable category maturity"],
    )
    assert est.value_eur == pytest.approx(50_000 * 2_000 * 0.3)
    assert "Bottom-up" in est.methodology
    assert len(est.assumptions) == 1


def test_tam_bottom_up_rejects_bad_penetration():
    with pytest.raises(ValueError):
        tam_bottom_up(1000, 100, realistic_penetration=1.5)


def test_tam_top_down_basic():
    est = tam_top_down(
        industry_size_eur=50_000_000_000,
        relevant_segment_pct=0.08,
        addressable_pct=0.25,
    )
    assert est.value_eur == pytest.approx(50_000_000_000 * 0.08 * 0.25)


def test_compare_estimates_flags_overstated_claim():
    platform_est = tam_top_down(10_000_000_000, 0.1, 0.3)  # = 300,000,000
    result = compare_estimates(company_value_eur=8_000_000_000, platform_estimate=platform_est)
    assert result["ratio_platform_over_company"] < 0.5
    assert "surestimée" in result["verdict"]


def test_compare_estimates_flags_consistent_claim():
    platform_est = tam_bottom_up(100_000, 1_000)  # = 100,000,000
    result = compare_estimates(company_value_eur=105_000_000, platform_estimate=platform_est)
    assert "cohérente" in result["verdict"]


def test_cagr_matches_known_value():
    # 100 -> 200 over 3 years => CAGR ~ 25.99%
    rate = cagr(100, 200, 3)
    assert rate == pytest.approx(0.2599, abs=1e-3)
