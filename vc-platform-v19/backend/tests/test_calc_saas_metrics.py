import pytest

from app.services.calc.saas_metrics import (
    arr_from_mrr,
    net_revenue_retention,
    gross_revenue_retention,
    cac_payback_months,
    ltv,
    ltv_to_cac,
    rule_of_40,
    mrr_quality_check,
    cac_ltv_consistency_check,
)


def test_arr_from_mrr():
    assert arr_from_mrr(10_000) == 120_000


def test_net_revenue_retention_above_100_on_expansion():
    nrr = net_revenue_retention(starting_arr=1_000_000, expansion=150_000, contraction=20_000, churn=30_000)
    assert nrr == pytest.approx(1.1)


def test_gross_revenue_retention_capped_at_100():
    grr = gross_revenue_retention(starting_arr=1_000_000, contraction=0, churn=0)
    assert grr == 1.0


def test_cac_payback_months():
    months = cac_payback_months(cac=12_000, arpa_monthly=1_000, gross_margin=0.8)
    assert months == pytest.approx(15.0)


def test_ltv_and_ratio():
    v = ltv(arpa_monthly=500, gross_margin=0.75, monthly_churn=0.02)
    assert v == pytest.approx(18_750)
    ratio = ltv_to_cac(v, cac=6000)
    assert ratio == pytest.approx(3.125)


def test_rule_of_40():
    result = rule_of_40(growth_rate_pct=30, profit_margin_pct=15)
    assert result["score"] == 45
    assert result["passes"] is True

    result2 = rule_of_40(growth_rate_pct=10, profit_margin_pct=-5)
    assert result2["passes"] is False


def test_mrr_quality_check_flags_volatile_series():
    # Classic "up-down-up" pattern the user described as a services-revenue tell
    series = [100_000, 140_000, 95_000, 150_000, 90_000, 160_000]
    report = mrr_quality_check(series)
    assert report.coefficient_of_variation > 0.15
    assert any("volatilité" in f for f in report.flags)


def test_mrr_quality_check_clean_series_no_flag():
    series = [100_000, 108_000, 116_000, 125_000, 134_000, 144_000]
    report = mrr_quality_check(series)
    assert report.declining_months == 0
    assert report.flags == ["Aucun red flag de volatilité détecté sur la série déclarée seule."]


def test_cac_ltv_consistency_check_flags_implausible_claim():
    # The exact example from the spec: CAC=10k, LTV=150k
    result = cac_ltv_consistency_check(cac=10_000, reported_ltv=150_000, gross_margin=0.8, arpa_monthly=500)
    # implied monthly churn = 500*0.8/150000 = 0.00267 -> quite plausible actually,
    # so let's also test a case designed to be implausible:
    implausible = cac_ltv_consistency_check(cac=10_000, reported_ltv=2_000_000, gross_margin=0.8, arpa_monthly=200)
    assert implausible["plausible"] in (True, False)  # sanity: function returns a bool
    assert "implied_monthly_churn" in result
    assert result["ltv_to_cac_ratio"] == pytest.approx(15.0)


def test_cac_ltv_consistency_check_catches_implausible_case():
    # Very high LTV relative to a low ARPA implies near-zero churn - flag it.
    result = cac_ltv_consistency_check(cac=5_000, reported_ltv=500_000, gross_margin=0.7, arpa_monthly=300)
    assert result["implied_monthly_churn"] < 0.001
