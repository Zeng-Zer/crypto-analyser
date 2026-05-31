"""Rolling z-score anomaly detection on OHLCV price data."""

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


def _extract_anomalies(result: pd.DataFrame) -> list[dict]:
    """Return anomaly records from a compute_anomalies result."""
    anomalies = result[result["is_anomaly"]].copy()
    if anomalies.empty:
        return []
    records = []
    for idx, row in anomalies.iterrows():
        z = abs(row["z_score"])
        if z >= 5.0:
            severity = "extreme"
        elif z >= 4.0:
            severity = "high"
        elif z >= 3.0:
            severity = "medium"
        else:
            severity = "low"
        records.append({
            "timestamp": int(idx),
            "close": float(row["price"]),
            "z_score": float(row["z_score"]),
            "severity": severity,
        })
    return records


def _load_parquet(symbol: str, start: str, end: str) -> pd.Series:
    """Load OHLCV close prices from Parquet for symbol within date range.

    Returns a Series indexed by open_time (epoch ms).
    """
    import duckdb

    con = duckdb.connect()
    month = start[:7]  # "2022-05"
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
    """CLI entry point for z-score anomaly detection."""
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Detect price anomalies via rolling z-score")
    parser.add_argument("--symbol", default="LUNAUSDT")
    parser.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    parser.add_argument("--window", type=int, default=288, help="Rolling window in bars (default 288 = 24h)")
    parser.add_argument("--threshold", type=float, default=2.5, help="|Z| threshold (default 2.5)")
    args = parser.parse_args()

    prices = _load_parquet(args.symbol, args.start, args.end)
    result = compute_anomalies(prices, window=args.window, threshold=args.threshold)
    anomalies = _extract_anomalies(result)

    output_path = Path(f"data/anomalies/{args.symbol}_{args.start}_{args.end}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "meta": {
            "symbol": args.symbol,
            "start": args.start,
            "end": args.end,
            "window": args.window,
            "threshold": args.threshold,
            "total_anomalies": len(anomalies),
        },
        "anomalies": anomalies,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(anomalies)} anomalies to {output_path}")


if __name__ == "__main__":
    main()
