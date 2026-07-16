from pathlib import Path

import pytest

from crypto_analyser import pipeline
from crypto_analyser.config import Config


def test_months_in_range_crosses_year_boundary():
    assert pipeline.months_in_range("2022-12-25", "2023-02-01") == ["2022-12", "2023-01", "2023-02"]


def test_months_in_range_rejects_reversed_dates():
    with pytest.raises(ValueError, match="start date"):
        pipeline.months_in_range("2022-05-11", "2022-05-07")


def test_pipeline_composes_library_functions_without_subprocess(monkeypatch, tmp_path):
    calls = []
    cfg = Config(
        {
            "anomaly_detection": {"window_hours": 24, "threshold": 2.5, "min_consecutive": 2},
            "paths": {"anomalies_dir": str(tmp_path / "anomalies")},
        }
    )
    monkeypatch.setattr(
        pipeline,
        "detect_episodes",
        lambda *args, **kwargs: {
            "meta": {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"},
            "episodes": [],
        },
    )
    monkeypatch.setattr(pipeline, "write_context", lambda path: calls.append(("context", path)))
    monkeypatch.setattr(pipeline, "classify_batch", lambda path, mode: calls.append(("classify", path, mode)))
    expected = tmp_path / "summary.json"
    monkeypatch.setattr(pipeline, "generate", lambda *args: (expected, []))

    result = pipeline.run_pipeline(
        "LUNAUSDT",
        "2022-05-07",
        "2022-05-11",
        skip_download=True,
        config=cfg,
    )

    anomaly_path = tmp_path / "anomalies" / "LUNAUSDT_2022-05-07_2022-05-11.json"
    assert result == expected
    assert anomaly_path.exists()
    assert calls == [("context", anomaly_path), ("classify", anomaly_path, "derivatives_only")]


def test_news_only_skips_derivatives(monkeypatch, tmp_path):
    cfg = Config(
        {
            "anomaly_detection": {"window_hours": 24, "threshold": 2.5, "min_consecutive": 2},
            "paths": {"anomalies_dir": str(tmp_path)},
        }
    )
    monkeypatch.setattr(
        pipeline,
        "detect_episodes",
        lambda *args, **kwargs: {
            "meta": {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"},
            "episodes": [],
        },
    )
    monkeypatch.setattr(pipeline, "write_context", lambda *_: pytest.fail("derivatives should be skipped"))
    monkeypatch.setattr(
        pipeline,
        "_require_environment",
        lambda *_: {"DATABASE_URL": "db", "LLM_API_URL": "api", "LLM_API_KEY": "key"},
    )
    monkeypatch.setattr(pipeline, "write_episode_contexts", lambda *args: [])
    monkeypatch.setattr(pipeline, "classify_batch", lambda *args: [])
    monkeypatch.setattr(pipeline, "generate", lambda *args: (Path("summary.json"), []))

    assert pipeline.run_pipeline(
        "LUNAUSDT", "2022-05-07", "2022-05-11", "news_only", skip_download=True, config=cfg
    ) == Path("summary.json")
