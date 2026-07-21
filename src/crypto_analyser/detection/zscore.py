"""Rolling z-score anomaly detection on OHLCV price data.

One anomaly = one contiguous *episode* of flagged bars (see ADR-0001), not a
per-bar flag. Episodes flow through derivatives fetch + LLM classification.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from crypto_analyser._paths import repo_root


def compute_anomalies(
    prices: pd.Series,
    window: int = 288,
    threshold: float = 2.5,
    drawdown_window: int = 48,
    drawdown_threshold: float = 0.50,
    return_window: int = 24,
    return_threshold: float = 0.25,
) -> pd.DataFrame:
    """
    Compute rolling z-score on price series and flag anomalies.

    Parameters
    ----------
    prices : pd.Series
        Price values indexed by epoch ms.
    window : int
        Rolling window size in bars (default 288 = 24h at 5m).
    threshold : float
        |Z| threshold for price anomaly flag (default 2.5).
    drawdown_window : int
        Rolling peak window in bars (default 48 = 4h at 5m).
    drawdown_threshold : float
        Peak-to-close decline required for drawdown flag (default 0.50).
    return_window : int
        Close-to-close return horizon in bars (default 24 = 2h at 5m).
    return_threshold : float
        Negative return magnitude required for return flag (default 0.25).

    Returns
    -------
    pd.DataFrame
        Price, z-score, 4h drawdown, 2h return, component flags, and their union.
        Index matches input index.
    """
    rolling_mean = prices.rolling(window=window, min_periods=window).mean()
    rolling_std = prices.rolling(window=window, min_periods=window).std()

    z_score = pd.Series(np.nan, index=prices.index, dtype=np.float64)
    mask = rolling_std > 0
    z_score[mask] = (prices[mask] - rolling_mean[mask]) / rolling_std[mask]
    # Where window is filled but std=0 (constant prices), z-score = 0
    zero_std = rolling_std.notna() & (rolling_std == 0)
    z_score[zero_std] = 0.0

    drawdown = prices / prices.rolling(drawdown_window, min_periods=drawdown_window).max() - 1
    horizon_return = prices.pct_change(return_window, fill_method=None)
    price_anomaly = z_score.abs() > threshold
    drawdown_anomaly = drawdown <= -drawdown_threshold
    return_anomaly = horizon_return <= -return_threshold
    anomaly_score = pd.concat(
        (
            z_score.abs() / threshold,
            drawdown.abs() / drawdown_threshold,
            horizon_return.clip(upper=0).abs() / return_threshold,
        ),
        axis=1,
    ).max(axis=1, skipna=True)

    return pd.DataFrame(
        {
            "price": prices,
            "z_score": z_score,
            "drawdown_4h": drawdown,
            "return_2h": horizon_return,
            "price_anomaly": price_anomaly,
            "drawdown_anomaly": drawdown_anomaly,
            "return_anomaly": return_anomaly,
            "anomaly_score": anomaly_score,
            "is_anomaly": price_anomaly | drawdown_anomaly | return_anomaly,
        },
        index=prices.index,
    )


# ponytail: severity bands are engine internals, not config-tunable.
_SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (2.0, "extreme"),
    (1.6, "high"),
    (1.2, "medium"),
    (1.0, "low"),
)


def _severity(score_ratio: float) -> str:
    for floor, label in _SEVERITY_BANDS:
        if score_ratio >= floor:
            return label
    return "low"





def extract_episodes(
    result: pd.DataFrame,
    prices: pd.Series,
    max_gap: int = 6,
    min_consecutive: int = 2,
) -> list[dict]:
    """Group per-bar anomaly flags into contiguous episodes.

    Parameters
    ----------
    result : pd.DataFrame
        Output of `compute_anomalies` (index aligned with `prices`).
    prices : pd.Series
        The close prices (same index as result), used for close/baseline.
    max_gap : int
        Tolerated consecutive non-flagged bars inside a run before splitting.
    min_consecutive : int
        Minimum flagged-bar count in a run to qualify as an episode.

    Returns
    -------
    list[dict]
        One record per episode: onset_ts, peak_ts, peak_z, severity,
        direction, close_onset, baseline_close, duration_bars.
    """
    flagged = result["is_anomaly"].to_numpy()
    z = result["z_score"].to_numpy()
    price_flagged = result.get("price_anomaly", result["is_anomaly"]).to_numpy()
    drawdown_flagged = result.get("drawdown_anomaly", pd.Series(False, index=result.index)).to_numpy()
    return_flagged = result.get("return_anomaly", pd.Series(False, index=result.index)).to_numpy()
    drawdown = result.get("drawdown_4h", pd.Series(np.nan, index=result.index)).to_numpy()
    horizon_return = result.get("return_2h", pd.Series(np.nan, index=result.index)).to_numpy()
    score = result.get("anomaly_score", result["z_score"].abs() / 2.5).to_numpy()
    closes = prices.to_numpy()
    idxs = prices.index.to_numpy()
    n = len(flagged)
    episodes: list[dict] = []
    i = 0
    while i < n:
        if not flagged[i]:
            i += 1
            continue
        start = i
        last_true = i
        j = i + 1
        while j < n:
            if flagged[j]:
                last_true = j
            elif (j - last_true) > max_gap:
                break
            j += 1
        end = last_true
        # Strongest normalized trigger among flagged bars within [start, end].
        seg_mask = flagged[start : end + 1]
        seg_z = z[start : end + 1]
        local = np.where(seg_mask, score[start : end + 1], -np.inf)
        peak_off = int(np.argmax(local))
        peak_idx = start + peak_off
        peak_z = float(z[peak_idx]) if not np.isnan(z[peak_idx]) else None
        flagged_count = int(seg_mask.sum())
        if flagged_count < min_consecutive:
            i = end + 1
            continue
        seg_z_vals = seg_z[seg_mask & ~np.isnan(seg_z)]
        direction = "spike" if seg_z_vals.size and float(np.mean(seg_z_vals)) >= 0 else "crash"
        trigger_series = (
            ("price_zscore", price_flagged[start : end + 1]),
            ("drawdown_4h", drawdown_flagged[start : end + 1]),
            ("return_2h", return_flagged[start : end + 1]),
        )
        triggers = [name for name, values in trigger_series if values.any()]
        onset_triggers = [name for name, values in trigger_series if values[0]]
        seg_drawdown = drawdown[start : end + 1]
        seg_return = horizon_return[start : end + 1]
        peak_drawdown = None if np.isnan(seg_drawdown).all() else float(np.nanmin(seg_drawdown))
        peak_return = None if np.isnan(seg_return).all() else float(np.nanmin(seg_return))
        episodes.append(
            {
                "onset_ts": int(idxs[start]),
                "peak_ts": int(idxs[peak_idx]),
                "peak_z": peak_z,
                "drawdown_onset_4h": None if np.isnan(drawdown[start]) else float(drawdown[start]),
                "peak_drawdown_4h": peak_drawdown,
                "return_onset_2h": None if np.isnan(horizon_return[start]) else float(horizon_return[start]),
                "peak_return_2h": peak_return,
                "triggers": triggers,
                "onset_triggers": onset_triggers,
                "severity": _severity(float(local[peak_off])),
                "direction": direction,
                "close_onset": float(closes[start]),
                "baseline_close": float(closes[start - 1]) if start > 0 else None,
                "duration_bars": int(end - start + 1),
            }
        )
        i = end + 1
    return episodes


def _load_parquet(symbol: str, start: str, end: str, data_dir: Path) -> pd.Series:
    """Load OHLCV close prices from Parquet for symbol within date range.

    Returns a Series indexed by open_time (epoch ms).
    """
    import duckdb

    con = duckdb.connect()
    # Glob all monthly parquet files for symbol so windows crossing a
    # calendar-month boundary load both months. SQL date-range filter
    # restricts to the requested window.
    parquet_glob = (data_dir / "ohlcv" / f"{symbol}_*.parquet").as_posix()
    import datetime
    import zoneinfo

    tz = zoneinfo.ZoneInfo("UTC")
    start_epoch = int(datetime.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=tz).timestamp() * 1000)
    end_epoch = int(datetime.datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=tz).timestamp() * 1000 + 86400_000 - 1)
    df = con.execute(f"""
        SELECT open_time, close
        FROM read_parquet('{parquet_glob}')
        WHERE open_time >= {start_epoch}
          AND open_time <= {end_epoch}
        ORDER BY open_time
    """).fetchdf()
    con.close()
    return df.set_index("open_time")["close"]


def detect_episodes(
    symbol: str,
    start: str,
    end: str,
    *,
    data_dir: Path | None = None,
    window_hours: float = 24,
    threshold: float = 2.5,
    drawdown_hours: float = 4,
    drawdown_threshold: float = 0.50,
    return_hours: float = 2,
    return_threshold: float = 0.25,
    max_gap: int = 6,
    min_consecutive: int = 2,
) -> dict:
    """Detect episodes from stored OHLCV and return the serializable batch."""
    window_bars = int(window_hours * 12)  # 5-minute candles
    prices = _load_parquet(symbol, start, end, data_dir or repo_root() / "data")
    drawdown_bars = int(drawdown_hours * 12)
    return_bars = int(return_hours * 12)
    result = compute_anomalies(
        prices,
        window=window_bars,
        threshold=threshold,
        drawdown_window=drawdown_bars,
        drawdown_threshold=drawdown_threshold,
        return_window=return_bars,
        return_threshold=return_threshold,
    )
    episodes = extract_episodes(result, prices, max_gap=max_gap, min_consecutive=min_consecutive)
    return {
        "meta": {
            "symbol": symbol,
            "start": start,
            "end": end,
            "window_hours": window_hours,
            "window_bars": window_bars,
            "threshold": threshold,
            "drawdown_hours": drawdown_hours,
            "drawdown_bars": drawdown_bars,
            "drawdown_threshold": drawdown_threshold,
            "return_hours": return_hours,
            "return_bars": return_bars,
            "return_threshold": return_threshold,
            "max_gap": max_gap,
            "min_consecutive": min_consecutive,
            "total_episodes": len(episodes),
        },
        "episodes": episodes,
    }
