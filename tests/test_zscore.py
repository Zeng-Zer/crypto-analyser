"""Tests for crypto_analyser.zscore.compute_anomalies."""
import pandas as pd
import numpy as np
from crypto_analyser.zscore import compute_anomalies


def test_flat_line_no_anomalies():
    """Constant prices should produce no anomaly flags."""
    prices = pd.Series([100.0] * 500)
    result = compute_anomalies(prices, window=48, threshold=2.5)
    assert not result["is_anomaly"].any(), "flat line should have no anomalies"
    valid_z = result["z_score"].dropna()
    assert (valid_z.abs() < 1e-10).all(), "flat line z-scores should be ~0"


def test_single_spike_detected():
    """A single bar 5 std above the mean should be flagged."""
    prices = pd.Series([100.0] * 200)
    prices.iloc[100] = 115.0
    result = compute_anomalies(prices, window=48, threshold=2.5)
    anomaly_indices = result.index[result["is_anomaly"]].tolist()
    assert anomaly_indices == [100], f"expected only index 100, got {anomaly_indices}"
    assert result.loc[100, "z_score"] > 2.5, "spike z-score should exceed threshold"


def test_window_affects_sensitivity():
    """Smaller window adapts faster, producing lower z-score for the same spike."""
    prices = pd.Series([100.0] * 200)
    prices.iloc[150] = 115.0

    result_small = compute_anomalies(prices, window=24, threshold=2.5)
    result_large = compute_anomalies(prices, window=96, threshold=2.5)

    z_small = result_small.loc[150, "z_score"]
    z_large = result_large.loc[150, "z_score"]

    assert abs(z_small) < abs(z_large), (
        f"small window z={z_small:.3f} should be smaller than large window z={z_large:.3f}"
    )


def test_threshold_filters_anomalies():
    """Higher threshold should produce fewer anomalies."""
    rng = np.random.default_rng(42)
    base = 100.0
    noise = rng.normal(0, 1.5, 500)
    prices = pd.Series(base + noise)

    result_loose = compute_anomalies(prices, window=48, threshold=3.5)
    result_tight = compute_anomalies(prices, window=48, threshold=1.5)

    assert result_loose["is_anomaly"].sum() < result_tight["is_anomaly"].sum(), (
        "higher threshold should flag fewer anomalies"
    )


def test_insufficient_data_returns_empty():
    """Less data than window should produce no anomalies."""
    prices = pd.Series([100.0] * 10)
    result = compute_anomalies(prices, window=48, threshold=2.5)
    assert result["z_score"].isna().all(), "all z-scores should be NaN"
    assert not result["is_anomaly"].any(), "no anomalies with insufficient data"
