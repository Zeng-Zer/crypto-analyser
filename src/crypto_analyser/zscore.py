"""Rolling z-score anomaly detection on OHLCV price data.

One anomaly = one contiguous *episode* of flagged bars (see ADR-0001), not a
per-bar flag. Episodes flow through derivatives fetch + LLM classification.
"""

from __future__ import annotations

import pandas as pd
import numpy as np


def compute_anomalies(
    prices: pd.Series,
    window: int = 288,
    threshold: float = 2.5,
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
        |Z| threshold for anomaly flag (default 2.5).

    Returns
    -------
    pd.DataFrame
        Columns: price (input), z_score (NaN before window fills), is_anomaly.
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

    is_anomaly = z_score.abs() > threshold

    return pd.DataFrame(
        {"price": prices, "z_score": z_score, "is_anomaly": is_anomaly},
        index=prices.index,
    )


# ponytail: severity bands are engine internals, not config-tunable. \|Z|>=5
# (extreme) is rarely reached on raw-price z-score during a single crash;
# observed LUNA peak is 4.31. Kept as documented ceiling; other events may hit it.
_SEVERITY_BANDS: tuple[tuple[float, str], ...] = (
    (5.0, "extreme"),
    (4.0, "high"),
    (3.0, "medium"),
    (0.0, "low"),
)


def _severity(peak_z_abs: float) -> str:
    for floor, label in _SEVERITY_BANDS:
        if peak_z_abs >= floor:
            return label
    return "low"


def _parse_window_hours(raw: str | int | float) -> float:
    """Parse a --window value as hours: '12', '12h', '24H' -> 12.0 / 24.0."""
    s = str(raw).strip()
    if s and s[-1] in ("h", "H"):
        s = s[:-1]
    return float(s)


def extract_episodes(
    result: pd.DataFrame,
    prices: pd.Series,
    max_gap: int = 2,
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
    closes = prices.to_numpy()
    idxs = prices.index.to_numpy()
    n = len(flagged)
    episodes: list[dict] = []
    i = 0
    while i < n:
        if not flagged[i] or np.isnan(z[i]):
            i += 1
            continue
        start = i
        last_true = i
        j = i + 1
        while j < n:
            if flagged[j] and not np.isnan(z[j]):
                last_true = j
            elif (j - last_true) > max_gap:
                break
            j += 1
        end = last_true
        # peak |Z| among flagged bars within [start, end]
        seg_mask = flagged[start : end + 1] & ~np.isnan(z[start : end + 1])
        seg_z = z[start : end + 1]
        local = np.where(seg_mask, np.abs(seg_z), -np.inf)
        peak_off = int(np.argmax(local))
        peak_idx = start + peak_off
        peak_z = float(z[peak_idx])
        flagged_count = int(seg_mask.sum())
        if flagged_count < min_consecutive:
            i = end + 1
            continue
        seg_z_vals = seg_z[seg_mask]
        mean_z = float(np.mean(seg_z_vals)) if seg_z_vals.size else 0.0
        direction = "spike" if mean_z >= 0 else "crash"
        episodes.append({
            "onset_ts": int(idxs[start]),
            "peak_ts": int(idxs[peak_idx]),
            "peak_z": peak_z,
            "severity": _severity(abs(peak_z)),
            "direction": direction,
            "close_onset": float(closes[start]),
            "baseline_close": float(closes[start - 1]) if start > 0 else None,
            "duration_bars": int(end - start + 1),
        })
        i = end + 1
    return episodes


def _load_parquet(symbol: str, start: str, end: str) -> pd.Series:
    """Load OHLCV close prices from Parquet for symbol within date range.

    Returns a Series indexed by open_time (epoch ms).
    """
    import duckdb

    con = duckdb.connect()
    month = start[:7]  # "2022-05"
    # ponytail: only one month file is loaded (start[:7]). Windows crossing a
    # calendar-month boundary would silently drop the other month. LUNA's
    # May 7-11 window is in-bounds; fix when Task 19/20 extends ranges.
    parquet_path = f"data/ohlcv/{symbol}_{month}.parquet"
    import datetime, zoneinfo
    tz = zoneinfo.ZoneInfo("UTC")
    start_epoch = int(datetime.datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=tz).timestamp() * 1000)
    end_epoch = int(datetime.datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=tz).timestamp() * 1000 + 86400_000 - 1)
    df = con.execute(f"""
        SELECT open_time, close
        FROM read_parquet('{parquet_path}')
        WHERE open_time >= {start_epoch}
          AND open_time <= {end_epoch}
        ORDER BY open_time
    """).fetchdf()
    con.close()
    return df.set_index("open_time")["close"]


def main():
    """CLI entry point: detect price anomalies as contiguous episodes."""
    import argparse
    import json
    from pathlib import Path

    import yaml as _yaml

    # ponytail: read anomaly_detection directly, bypassing load_config()'s
    # placeholder gate which would crash on unfilled LLM API keys. Z-score CLI
    # has nothing to do with LLM keys.
    cfg_path = Path(__file__).resolve().parent.parent.parent / "config" / "settings.yaml"
    with open(cfg_path, encoding="utf-8") as _f:
        _raw = _yaml.safe_load(_f) or {}
    ad = _raw.get("anomaly_detection", {}) or {}
    cfg_window_hours = float(ad.get("window_hours", 24))
    cfg_threshold = float(ad.get("threshold", 2.5))
    cfg_min_consecutive = int(ad.get("min_consecutive", 2))

    # ponytail: 5m klines per plan. If other intervals land, derive from data.
    bars_per_hour = 12

    parser = argparse.ArgumentParser(description="Detect price anomalies via rolling z-score, grouped into episodes")
    parser.add_argument("--symbol", default="LUNAUSDT")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--window", default=None,
                        help="Rolling window in hours, optional 'h' suffix (default: config window_hours). '12', '12h', '24h'")
    parser.add_argument("--threshold", type=float, default=None,
                        help=f"|Z| threshold (default: config threshold = {cfg_threshold})")
    parser.add_argument("--max-gap", type=int, default=2,
                        help="Tolerated consecutive non-flagged bars inside a run before splitting (default: 2)")
    parser.add_argument("--min-consecutive", type=int, default=None,
                        help=f"Minimum flagged bars to form an episode (default: config min_consecutive = {cfg_min_consecutive})")
    args = parser.parse_args()

    window_hours = _parse_window_hours(args.window) if args.window is not None else cfg_window_hours
    window_bars = int(window_hours * bars_per_hour)
    threshold = args.threshold if args.threshold is not None else cfg_threshold
    min_consecutive = args.min_consecutive if args.min_consecutive is not None else cfg_min_consecutive

    prices = _load_parquet(args.symbol, args.start, args.end)
    result = compute_anomalies(prices, window=window_bars, threshold=threshold)
    episodes = extract_episodes(result, prices, max_gap=args.max_gap, min_consecutive=min_consecutive)

    output_path = Path(f"data/anomalies/{args.symbol}_{args.start}_{args.end}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "meta": {
            "symbol": args.symbol,
            "start": args.start,
            "end": args.end,
            "window_hours": window_hours,
            "window_bars": window_bars,
            "threshold": threshold,
            "max_gap": args.max_gap,
            "min_consecutive": min_consecutive,
            "total_episodes": len(episodes),
        },
        "episodes": episodes,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(episodes)} episodes to {output_path}")
    if episodes:
        from collections import Counter
        sev = Counter(e["severity"] for e in episodes)
        peak = max(episodes, key=lambda e: abs(e["peak_z"]))
        print(f"Severity distribution: {dict(sev)}")
        print(f"Peak |Z|: {abs(peak['peak_z']):.2f} at onset {peak['onset_ts']} (severity={peak['severity']})")


if __name__ == "__main__":
    main()
