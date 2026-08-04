"""Fetch and align Alternative.me Fear & Greed observations to episodes."""

from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path
from typing import Any

import requests

from crypto_analyser._paths import data_root

FEAR_GREED_API_URL = "https://api.alternative.me/fng/"
FEAR_GREED_SOURCE_URL = "https://alternative.me/crypto/fear-and-greed-index/"


def _observations(rows: Any, *, timestamp_scale: int, classification_key: str) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("Fear & Greed response must contain data")
    observations: dict[int, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        try:
            value = int(raw.get("value"))
            timestamp = int(raw.get("timestamp")) * timestamp_scale
        except (TypeError, ValueError):
            continue
        classification = raw.get(classification_key)
        if 0 <= value <= 100 and timestamp > 0 and isinstance(classification, str) and classification.strip():
            observations[timestamp] = {
                "timestamp": timestamp,
                "value": value,
                "classification": classification.strip()[:100],
            }
    if not observations:
        raise ValueError("Fear & Greed response contained no valid observations")
    return [observations[timestamp] for timestamp in sorted(observations)]


def parse_fear_greed(payload: Any) -> list[dict[str, Any]]:
    """Validate API payload and return unique observations oldest first."""
    if not isinstance(payload, dict):
        raise ValueError("Fear & Greed response must contain data")
    return _observations(payload.get("data"), timestamp_scale=1_000, classification_key="value_classification")


def fetch_fear_greed(limit: int = 0, base_url: str = FEAR_GREED_API_URL) -> list[dict[str, Any]]:
    """Fetch current or historical daily index observations."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("Fear & Greed limit must be a non-negative integer")
    response = requests.get(base_url, params={"limit": limit}, timeout=(2, 20))
    response.raise_for_status()
    return parse_fear_greed(response.json())


def at_or_before(observations: list[dict[str, Any]], timestamp: int) -> dict[str, Any] | None:
    """Return latest daily observation available by timestamp."""
    if isinstance(timestamp, bool) or not isinstance(timestamp, int) or timestamp <= 0:
        raise ValueError("timestamp must be a positive integer")
    times = [int(item["timestamp"]) for item in observations]
    index = bisect_right(times, timestamp) - 1
    return observations[index] if index >= 0 else None


def enrich_features(features: list[dict[str, Any]], observations: list[dict[str, Any]]) -> None:
    """Add non-causal daily sentiment context to episode feature rows in place."""
    for feature in features:
        observation = at_or_before(observations, int(feature["onset_ts"]))
        feature.update(
            {
                "fear_greed_value": observation["value"] if observation else None,
                "fear_greed_classification": observation["classification"] if observation else None,
                "fear_greed_timestamp": observation["timestamp"] if observation else None,
            }
        )


def write_history(data_dir: str | Path = "data", *, base_url: str = FEAR_GREED_API_URL) -> Path:
    """Download complete daily history to one reusable JSON artifact."""
    path = data_root(data_dir) / "sentiment" / "fear_greed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        observations = fetch_fear_greed(0, base_url)
    except (requests.RequestException, ValueError, TypeError):
        try:
            load_history(data_dir)
        except (OSError, ValueError, TypeError):
            path.write_text("[]\n", encoding="utf-8")
        return path
    path.write_text(json.dumps(observations, indent=2), encoding="utf-8")
    return path


def load_history(data_dir: str | Path = "data") -> list[dict[str, Any]]:
    path = data_root(data_dir) / "sentiment" / "fear_greed.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [] if rows == [] else _observations(rows, timestamp_scale=1, classification_key="classification")


def write_context(anomalies_path: Path, data_dir: Path | None = None) -> Path:
    """Persist sentiment-only feature rows for a news-only pipeline run."""
    root = data_dir or data_root()
    anomalies_path = anomalies_path if anomalies_path.is_absolute() else root.parent / anomalies_path
    anomalies = json.loads(anomalies_path.read_text(encoding="utf-8"))
    meta = anomalies["meta"]
    output_path = root / "context" / f"{meta['symbol']}_{meta['start']}_{meta['end']}_context.json"
    existing = json.loads(output_path.read_text(encoding="utf-8")) if output_path.exists() else {"features": []}
    by_onset = {feature["onset_ts"]: feature for feature in existing["features"]}
    features = [
        {**by_onset.get(episode["onset_ts"], {}), "onset_ts": episode["onset_ts"]}
        for episode in anomalies["episodes"]
    ]
    enrich_features(features, load_history(root))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "meta": {
                    **existing.get("meta", {}),
                    "symbol": meta["symbol"],
                    "start": meta["start"],
                    "end": meta["end"],
                    "source_anomalies": str(anomalies_path),
                    "total_features": len(features),
                },
                "features": features,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path
