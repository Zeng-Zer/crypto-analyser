"""Tests for crypto_analyser.detection.zscore.compute_anomalies."""

import numpy as np
import pandas as pd

from crypto_analyser.detection.zscore import compute_anomalies, extract_episodes


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


def test_four_hour_drawdown_detects_sustained_collapse_after_price_zscore_adapts():
    prices = pd.Series([100.0] * 300 + np.geomspace(100.0, 1.0, 120).tolist())

    result = compute_anomalies(prices, window=288, threshold=2.5)
    drawdown_only = result["drawdown_anomaly"] & ~result["price_anomaly"]

    assert drawdown_only.any()
    assert (result.loc[drawdown_only, "drawdown_4h"] <= -0.5).all()
    assert (
        result["is_anomaly"]
        == (result["price_anomaly"] | result["drawdown_anomaly"] | result["return_anomaly"])
    ).all()


def test_two_hour_return_detects_material_move_missed_by_other_signals():
    prices = pd.Series(([70.0, 130.0] * 150) + np.linspace(100.0, 70.0, 25).tolist())

    result = compute_anomalies(prices, window=288)
    final = result.iloc[-1]

    assert np.isclose(final["return_2h"], -0.3)
    assert final["return_anomaly"]
    assert not final["price_anomaly"]
    assert not final["drawdown_anomaly"]


def test_drawdown_episode_does_not_wait_for_zscore_warmup():
    prices = pd.Series([100.0] * 48 + [40.0, 39.0])
    result = compute_anomalies(prices, window=288, drawdown_window=48, return_threshold=0.90)

    episodes = extract_episodes(result, prices)

    assert len(episodes) == 1
    assert episodes[0]["triggers"] == ["drawdown_4h"]
    assert episodes[0]["onset_triggers"] == ["drawdown_4h"]
    assert episodes[0]["peak_z"] is None


def test_thirty_minute_gap_stays_in_one_episode():
    prices = pd.Series([100.0] * 30)
    result = compute_anomalies(prices, window=10)
    result.loc[[10, 11, 18, 19], ["price_anomaly", "is_anomaly"]] = True
    result.loc[[10, 11, 18, 19], "anomaly_score"] = 1.1

    assert len(extract_episodes(result, prices)) == 1
    assert len(extract_episodes(result, prices, max_gap=2)) == 2


def test_insufficient_data_returns_empty():
    """Less data than window should produce no anomalies."""
    prices = pd.Series([100.0] * 10)
    result = compute_anomalies(prices, window=48, threshold=2.5)
    assert result["z_score"].isna().all(), "all z-scores should be NaN"
    assert not result["is_anomaly"].any(), "no anomalies with insufficient data"
    assert result["drawdown_4h"].isna().all(), "drawdown needs a full lookback window"
