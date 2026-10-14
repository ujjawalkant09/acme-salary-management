from decimal import Decimal

import pytest

from app.services.stats import histogram, median, pct_diff, percentile, spread

D = Decimal


def test_percentile_interpolates_between_ranks():
    values = [D(10), D(20), D(30), D(40)]
    assert percentile(values, "0.5") == D("25.00")
    assert percentile(values, "0.25") == D("17.50")
    assert percentile(values, "0") == D("10.00")
    assert percentile(values, "1") == D("40.00")


def test_percentile_of_one_value_is_that_value():
    assert percentile([D(7)], "0.75") == D("7.00")


def test_percentile_of_nothing_fails_loudly():
    with pytest.raises(ValueError):
        percentile([], "0.5")


def test_median_sorts_first():
    assert median([D(3), D(1), D(2)]) == D("2.00")


def test_spread_and_outlier_fences():
    s = spread([D(v) for v in (100, 102, 104, 106, 108, 110, 112, 200)])
    assert (s.count, s.min, s.max) == (8, D("100.00"), D("200.00"))
    assert s.is_outlier(D(200))
    assert not s.is_outlier(D(110))
    assert s.is_outlier(D(50))


def test_small_groups_never_flag_outliers():
    s = spread([D(100), D(100), D(1000)])
    assert not s.is_outlier(D(1000))


def test_pct_diff_rounds_to_one_decimal_and_handles_zero():
    assert pct_diff(D(112), D(100)) == D("12.0")
    assert pct_diff(D(90), D(120)) == D("-25.0")
    assert pct_diff(D(5), D(0)) == D("0.0")


def test_histogram_counts_every_value_once():
    values = [D(v) for v in (0, 1, 2, 3, 4, 5, 6, 7, 8, 10)]
    bins = histogram(values, 5)
    assert len(bins) == 5
    assert sum(count for _, _, count in bins) == len(values)
    assert bins[0][0] == D("0.00") and bins[-1][1] == D("10.00")
    assert bins[-1][2] == 2  # the maximum lands in the last bin


def test_histogram_edge_cases():
    assert histogram([], 10) == []
    assert histogram([D(5), D(5)], 10) == [(D("5.00"), D("5.00"), 2)]
