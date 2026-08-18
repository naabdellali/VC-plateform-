import pytest

from app.services.calc.parsing import parse_money


@pytest.mark.parametrize(
    "text,expected",
    [
        ("TAM: EUR 10bn", 10_000_000_000),
        ("$2.5M", 2_500_000),
        ("Current MRR: EUR 85k", 85_000),
        ("SOM: EUR 200m", 200_000_000),
        ("no numbers here", None),
    ],
)
def test_parse_money(text, expected):
    assert parse_money(text) == expected
