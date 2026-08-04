import json

import pytest
import requests

from crypto_analyser.features import sentiment
from crypto_analyser.features.sentiment import at_or_before, enrich_features, parse_fear_greed, write_context


def test_fear_greed_parser_aligns_latest_non_future_observation():
    payload = {
        "data": [
            {"value": "10", "value_classification": "Extreme Fear", "timestamp": "200"},
            {"value": "20", "value_classification": "Fear", "timestamp": "100"},
            {"value": "101", "value_classification": "Invalid", "timestamp": "300"},
        ]
    }

    observations = parse_fear_greed(payload)
    features = [{"onset_ts": 150_000}, {"onset_ts": 250_000}]
    enrich_features(features, observations)

    assert [item["value"] for item in observations] == [20, 10]
    assert at_or_before(observations, 99_999) is None
    assert features == [
        {
            "onset_ts": 150_000,
            "fear_greed_value": 20,
            "fear_greed_classification": "Fear",
            "fear_greed_timestamp": 100_000,
        },
        {
            "onset_ts": 250_000,
            "fear_greed_value": 10,
            "fear_greed_classification": "Extreme Fear",
            "fear_greed_timestamp": 200_000,
        },
    ]


@pytest.mark.parametrize("payload", [{}, {"data": []}, {"data": [{"value": "bad"}]}])
def test_fear_greed_parser_rejects_payload_without_valid_observations(payload):
    with pytest.raises(ValueError, match="Fear & Greed"):
        parse_fear_greed(payload)


def test_sentiment_context_preserves_existing_derivatives(tmp_path):
    stem = "BTCUSDT_2026-08-04_2026-08-05"
    onset = 200_000
    for directory in ("anomalies", "context", "sentiment"):
        (tmp_path / directory).mkdir()
    anomalies = {
        "meta": {"symbol": "BTCUSDT", "start": "2026-08-04", "end": "2026-08-05"},
        "episodes": [{"onset_ts": onset}],
    }
    (tmp_path / "anomalies" / f"{stem}.json").write_text(json.dumps(anomalies))
    (tmp_path / "context" / f"{stem}_context.json").write_text(
        json.dumps({"meta": {"lookback_hours": 4}, "features": [{"onset_ts": onset, "oi_current": 123.0}]})
    )
    (tmp_path / "sentiment" / "fear_greed.json").write_text(
        json.dumps([{"timestamp": 100_000, "value": 25, "classification": "Extreme Fear"}])
    )

    output = write_context(tmp_path / "anomalies" / f"{stem}.json", tmp_path)
    context = json.loads(output.read_text())

    assert context["meta"]["lookback_hours"] == 4
    assert context["features"] == [
        {
            "onset_ts": onset,
            "oi_current": 123.0,
            "fear_greed_value": 25,
            "fear_greed_classification": "Extreme Fear",
            "fear_greed_timestamp": 100_000,
        }
    ]


def test_history_refresh_failure_preserves_valid_cache(monkeypatch, tmp_path):
    path = tmp_path / "sentiment" / "fear_greed.json"
    path.parent.mkdir()
    cached = [{"timestamp": 100_000, "value": 25, "classification": "Extreme Fear"}]
    path.write_text(json.dumps(cached))
    monkeypatch.setattr(
        sentiment,
        "fetch_fear_greed",
        lambda *_args: (_ for _ in ()).throw(requests.ConnectionError("offline")),
    )

    sentiment.write_history(tmp_path)

    assert json.loads(path.read_text()) == cached


def test_missing_history_yields_null_context(tmp_path):
    features = [{"onset_ts": 100_000}]

    enrich_features(features, sentiment.load_history(tmp_path))

    assert features[0]["fear_greed_value"] is None
