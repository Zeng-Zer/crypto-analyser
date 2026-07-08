"""Derivatives context extraction for anomaly episodes.

For each price episode from Task 14 (z-score), pull the derivatives market
snapshot anchored at the episode's ``onset_ts``: funding rate from the active
8h interval + open interest at 5-min granularity. Emits a feature vector per
episode that the LLM classifier (Task 17/18) consumes.

Anchor is ``onset_ts`` — the moment the deviation became statistically real —
not ``peak_ts`` (descriptive only). See ADR-0001.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

# ponytail: lookback matches the spec field suffixes (_avg_4h, _change_4h).
# 8h funding snapshots mean a 4h window captures at most one funding point,
# so funding_rate_avg_4h typically equals funding_rate_current. Correct
# behavior on sparse 8h data, not a bug. Widen if denser funding lands.
LOOKBACK_HOURS = 4


def _load_funding(symbol: str, month: str) -> pd.DataFrame:
    """Funding-rate parquet sorted by ``calc_time`` (epoch ms)."""
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT calc_time, last_funding_rate AS funding_rate
        FROM read_parquet('data/funding/{symbol}_{month}.parquet')
        ORDER BY calc_time
    """).fetchdf()
    con.close()
    return df


def _load_oi(symbol: str, month: str) -> pd.DataFrame:
    """Open-interest parquet sorted by ``create_time`` (epoch ms)."""
    con = duckdb.connect()
    df = con.execute(f"""
        SELECT epoch_ms(create_time) AS create_time_ms, sum_open_interest
        FROM read_parquet('data/oi/{symbol}_{month}.parquet')
        ORDER BY create_time_ms
    """).fetchdf()
    con.close()
    return df


def _nearest_before(times_ms: np.ndarray, target_ms: int) -> int:
    """Index of largest timestamp <= target. -1 if none precede it."""
    if times_ms.size == 0:
        return -1
    return int(np.searchsorted(times_ms, target_ms, side="right")) - 1


def extract_features(
    episodes: list[dict[str, Any]],
    funding: pd.DataFrame,
    oi: pd.DataFrame,
    lookback_hours: float = LOOKBACK_HOURS,
) -> list[dict[str, Any]]:
    """Build a per-episode derivatives feature vector anchored at onset_ts."""
    f_times = funding["calc_time"].to_numpy()
    f_rates = funding["funding_rate"].to_numpy()
    oi_times = oi["create_time_ms"].to_numpy()
    oi_vals = oi["sum_open_interest"].to_numpy()
    lookback_ms = int(lookback_hours * 3_600_000)

    features: list[dict[str, Any]] = []
    for ep in episodes:
        onset = int(ep["onset_ts"])

        # funding: step function — a snapshot stays in effect until the next
        # one, so avg over [onset-L, onset] is a time-weighted mean of the rate(s)
        # active in that window (at most 2, since L < 8h funding interval).
        cur_idx = _nearest_before(f_times, onset)
        funding_current = float(f_rates[cur_idx]) if cur_idx >= 0 else None
        prev_idx = _nearest_before(f_times, onset - lookback_ms)
        if cur_idx < 0 or prev_idx < 0:
            funding_avg_4h = None
        elif cur_idx == prev_idx:
            # one rate covers the whole window (the common case on 8h data)
            funding_avg_4h = float(f_rates[cur_idx])
        else:
            # boundary at calc_time[cur_idx] splits the window
            boundary = int(f_times[cur_idx])
            win_start = onset - lookback_ms
            before = max(boundary - win_start, 0)
            after = max(onset - boundary, 0)
            funding_avg_4h = (
                float((f_rates[prev_idx] * before + f_rates[cur_idx] * after) / (before + after))
                if (before + after) > 0
                else None
            )

        # open interest: value at onset + pct change vs lookback start
        oi_cur_idx = _nearest_before(oi_times, onset)
        oi_current = float(oi_vals[oi_cur_idx]) if oi_cur_idx >= 0 else None
        oi_prev_idx = _nearest_before(oi_times, onset - lookback_ms)
        oi_4h_ago = float(oi_vals[oi_prev_idx]) if oi_prev_idx >= 0 else None
        oi_change_4h = (
            (oi_current - oi_4h_ago) / oi_4h_ago if oi_current is not None and oi_4h_ago and oi_4h_ago != 0 else None
        )

        features.append(
            {
                "onset_ts": onset,
                "funding_rate_current": funding_current,
                "funding_rate_avg_4h": funding_avg_4h,
                "oi_current": oi_current,
                "oi_change_4h": oi_change_4h,
            }
        )
    return features


def main() -> None:
    """CLI: extract derivatives context for the episodes in an anomalies file."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract derivatives context (funding + OI) for anomaly episodes",
    )
    parser.add_argument(
        "--anomalies",
        required=True,
        help="Path to bulk anomalies JSON",
    )
    parser.add_argument(
        "--lookback-hours",
        type=float,
        default=None,
        help=f"Lookback window in hours (default {LOOKBACK_HOURS})",
    )
    args = parser.parse_args()

    anomalies_path = Path(args.anomalies)
    with open(anomalies_path, encoding="utf-8") as f:
        anomalies = json.load(f)
    meta = anomalies["meta"]
    episodes = anomalies["episodes"]
    symbol, start, end = meta["symbol"], meta["start"], meta["end"]
    # ponytail: single-month load (start[:7]); LUNA May 7-11 is in-bounds.
    month = start[:7]
    lookback = args.lookback_hours if args.lookback_hours is not None else LOOKBACK_HOURS

    funding = _load_funding(symbol, month)
    oi = _load_oi(symbol, month)
    features = extract_features(episodes, funding, oi, lookback_hours=lookback)

    output_path = Path(f"data/context/{symbol}_{start}_{end}_context.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "meta": {
            "symbol": symbol,
            "start": start,
            "end": end,
            "source_anomalies": str(anomalies_path),
            "lookback_hours": lookback,
            "total_features": len(features),
        },
        "features": features,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print(f"Wrote {len(features)} feature vectors to {output_path}")
    for feat in features:
        print(
            f"  onset {feat['onset_ts']}: funding={feat['funding_rate_current']}, oi_change_4h={feat['oi_change_4h']}"
        )


if __name__ == "__main__":
    main()
