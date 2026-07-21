"""Build the LUNA Context Atlas pages from canonical pipeline artifacts."""

from __future__ import annotations

import json
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from crypto_analyser.constants import FUNDING_RATE_THRESHOLD, OI_CHANGE_THRESHOLD
from crypto_analyser.detection.zscore import compute_anomalies

MODES = ("derivatives_only", "derivatives_rag", "news_only")
MODE_LABELS = {
    "derivatives_only": "Derivatives only",
    "derivatives_rag": "Derivatives + news",
    "news_only": "News only",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _market_bars(
    parquet: Path,
    start: str,
    end: str,
    window_bars: int,
    drawdown_bars: int,
    drawdown_threshold: float,
    return_bars: int,
    return_threshold: float,
) -> list[dict[str, float | int | None]]:
    start_ms = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(end).replace(tzinfo=timezone.utc).timestamp() * 1000 + 86_400_000 - 1)
    frame = duckdb.sql(
        "SELECT open_time, close FROM read_parquet(?) WHERE open_time BETWEEN ? AND ? ORDER BY open_time",
        params=[str(parquet), start_ms, end_ms],
    ).df()
    prices = pd.Series(frame["close"].to_numpy(), index=frame["open_time"].to_numpy())
    scored = compute_anomalies(
        prices,
        window=window_bars,
        drawdown_window=drawdown_bars,
        drawdown_threshold=drawdown_threshold,
        return_window=return_bars,
        return_threshold=return_threshold,
    )
    return [
        {
            "ts": int(ts),
            "close": round(float(row.price), 6),
            "z": None if pd.isna(row.z_score) else round(float(row.z_score), 4),
            "drawdown_4h": None if pd.isna(row.drawdown_4h) else round(float(row.drawdown_4h), 4),
            "return_2h": None if pd.isna(row.return_2h) else round(float(row.return_2h), 4),
        }
        for ts, row in scored.iterrows()
    ]


def _latest_at_or_before(timestamps: list[int], onset: int) -> int | None:
    index = bisect_right(timestamps, onset) - 1
    return timestamps[index] if index >= 0 else None


def build_snapshot(root: Path) -> dict[str, Any]:
    data = root / "data"
    symbol, start, end = "LUNAUSDT", "2022-05-07", "2022-05-11"
    stem = f"{symbol}_{start}_{end}"
    anomalies = _load(data / "anomalies" / f"{stem}.json")
    features = _load(data / "context" / f"{stem}_context.json")["features"]
    comparison = _load(root / "results" / "ablation_comparison.json")
    feature_by_onset = {item["onset_ts"]: item for item in features}
    funding_times = [
        int(row[0])
        for row in duckdb.sql(
            "SELECT calc_time FROM read_parquet(?) ORDER BY calc_time",
            params=[str(data / "funding" / f"{symbol}_2022-05.parquet")],
        ).fetchall()
    ]
    oi_times = [
        int(row[0])
        for row in duckdb.sql(
            "SELECT epoch_ms(create_time) FROM read_parquet(?) ORDER BY create_time",
            params=[str(data / "oi" / f"{symbol}_2022-05.parquet")],
        ).fetchall()
    ]
    reports = {
        mode: {
            item["onset_ts"]: item
            for item in _load(data / "reports" / mode / f"{stem}_summary.json")["episodes"]
        }
        for mode in MODES
    }
    evaluated = {
        mode: {item["onset_ts"]: item for item in comparison[mode]["episodes"]}
        for mode in MODES
    }

    episodes = []
    for index, episode in enumerate(anomalies["episodes"], 1):
        onset = episode["onset_ts"]
        rag = _load(data / "rag" / f"{symbol}_{onset}_rag.json")
        news = []
        for article in rag["articles"]:
            published = datetime.fromisoformat(article["date_pub"])
            onset_time = datetime.fromtimestamp(onset / 1000, tz=timezone.utc)
            news.append(
                {
                    "title": article["title"],
                    "description": article.get("description"),
                    "published": article["date_pub"],
                    "age_minutes": round((onset_time - published).total_seconds() / 60),
                    "id": article["id"],
                    "source": article.get("source"),
                    "rrf_score": article.get("rrf_score"),
                    "vector_rank": article.get("vector_rank"),
                    "text_rank": article.get("text_rank"),
                }
            )
        verdicts = {}
        for mode in MODES:
            report = reports[mode][onset]["classification"]
            verdicts[mode] = {
                "label": MODE_LABELS[mode],
                "verdict": report["verdict"],
                "confidence": report["confidence"],
                "synthesis": report["synthesis"],
            }
        episodes.append(
            {
                "index": index,
                **episode,
                "features": {
                    **feature_by_onset[onset],
                    "source_ts": {
                        "price": onset,
                        "funding": _latest_at_or_before(funding_times, onset),
                        "open_interest": _latest_at_or_before(oi_times, onset),
                    },
                },
                "news": news,
                "news_cutoff": rag["cutoff"],
                "verdicts": verdicts,
                "faithfulness": evaluated["derivatives_rag"][onset]["faithfulness"],
            }
        )

    bars = _market_bars(
        data / "ohlcv" / f"{symbol}_2022-05.parquet",
        start,
        end,
        anomalies["meta"]["window_bars"],
        anomalies["meta"]["drawdown_bars"],
        anomalies["meta"]["drawdown_threshold"],
        anomalies["meta"]["return_bars"],
        anomalies["meta"]["return_threshold"],
    )
    start_close, end_close = bars[0]["close"], bars[-1]["close"]
    snapshot = {
        "meta": {
            "title": "LUNA Context Atlas",
            "symbol": symbol,
            "start": start,
            "end": end,
            "generated_at": comparison["evaluated_at"],
            "bar_interval_minutes": 5,
            "snapshot_end_ts": bars[-1]["ts"],
            "episode_count": len(episodes),
            "classification_count": len(episodes) * len(MODES),
            "thresholds": {
                "z_score": anomalies["meta"]["threshold"],
                "drawdown_4h": anomalies["meta"]["drawdown_threshold"],
                "return_2h": anomalies["meta"]["return_threshold"],
                "funding_rate": FUNDING_RATE_THRESHOLD,
                "oi_change_4h": OI_CHANGE_THRESHOLD,
            },
            "start_close": start_close,
            "end_close": end_close,
            "drawdown": (end_close - start_close) / start_close,
        },
        "bars": bars,
        "episodes": episodes,
        "evaluation": {
            "metric": comparison["metrics"]["faithfulness"],
            "limitations": comparison["limitations"],
        },
    }
    validate_snapshot(snapshot)
    return snapshot


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    episodes = snapshot["episodes"]
    assert snapshot["bars"], "market bars missing"
    assert len(episodes) == snapshot["meta"]["episode_count"], "episode count mismatch"
    assert all(set(episode["verdicts"]) == set(MODES) for episode in episodes), "mode verdict missing"
    assert all(0 <= episode["faithfulness"] <= 1 for episode in episodes), "faithfulness invalid"
    for episode in episodes:
        available_refs = {"funding_rate_current", "oi_change_4h"} | {
            f"news_{article['id']}" for article in episode["news"]
        }
        for verdict in episode["verdicts"].values():
            synthesis = verdict["synthesis"]
            assert 1 <= len(synthesis["reasons"]) <= 3, "synthesis reason count invalid"
            assert all(0 < len(reason) <= 160 for reason in synthesis["reasons"]), "synthesis reason invalid"
            assert set(synthesis["supporting_refs"]) <= available_refs, "unknown supporting ref"
    assert all(
        timestamp <= episode["onset_ts"]
        for episode in episodes
        for timestamp in episode["features"]["source_ts"].values()
        if timestamp is not None
    ), "future context timestamp leaked into snapshot"
    assert all(article["age_minutes"] >= 0 for episode in episodes for article in episode["news"]), (
        "post-onset article leaked into RAG snapshot"
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    snapshot = build_snapshot(root)
    serialized = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = root / "visuals" / "template.html"
    output = root / "visuals" / "index.html"
    output.write_text(template.read_text(encoding="utf-8").replace("__ATLAS_DATA__", serialized), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
