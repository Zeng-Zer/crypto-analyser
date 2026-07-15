import pytest

from scripts.run_pipeline import _months_in_range


def test_months_in_range_crosses_year_boundary():
    assert _months_in_range("2022-12-25", "2023-02-01") == ["2022-12", "2023-01", "2023-02"]


def test_months_in_range_rejects_reversed_dates():
    with pytest.raises(ValueError, match="start date"):
        _months_in_range("2022-05-11", "2022-05-07")
