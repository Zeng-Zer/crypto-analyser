from pathlib import Path

import pytest

from crypto_analyser import cli


@pytest.fixture(autouse=True)
def model_environment(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "chat-model")
    monkeypatch.setenv("RAGAS_JUDGE_MODEL", "judge-model")


def test_run_command_routes_to_pipeline(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "run_pipeline",
        lambda *args, **kwargs: calls.append((args, kwargs)) or Path("summary.json"),
    )

    assert cli.main(["run", "--start", "2022-05-07", "--end", "2022-05-11", "--skip-download"]) == 0
    assert calls == [
        (
            ("LUNAUSDT", "2022-05-07", "2022-05-11", "derivatives_only"),
            {
                "data_dir": Path("data"),
                "skip_download": True,
                "force_download": False,
                "window_hours": 24.0,
                "threshold": 2.5,
                "drawdown_hours": 4.0,
                "drawdown_threshold": 0.5,
                "return_hours": 2.0,
                "return_threshold": 0.25,
                "max_gap": 6,
                "min_consecutive": 2,
                "llm_model": "chat-model",
            },
        )
    ]
    assert capsys.readouterr().out.strip() == "summary.json"


def test_news_load_routes_to_archive_loader(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setattr(cli, "load_archive", lambda path, url: (12, 10))

    assert cli.main(["news", "load", "--archive-dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out.strip() == "Read 12 articles; inserted 10 new rows."


def test_news_search_formats_results(monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", "db")
    monkeypatch.setenv("LLM_API_URL", "api")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setattr(
        cli,
        "search_news",
        lambda *args, **kwargs: [
            {"distance": 0.1, "title": "UST depeg", "date_pub": "2022-05-09", "source": "News"}
        ],
    )

    assert cli.main(["news", "search", "--query", "Terra"]) == 0
    assert "[90.0%] UST depeg" in capsys.readouterr().out


def test_live_command_routes_to_local_bridge(monkeypatch):
    from crypto_analyser import live

    calls = []
    monkeypatch.setenv("LLM_API_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setattr(live, "serve_live", lambda *args: calls.append(args))

    assert (
        cli.main(
            [
                "live",
                "--host",
                "0.0.0.0",
                "--port",
                "8765",
                "--news-api-url",
                "https://news.example/api",
            ]
        )
        == 0
    )
    assert calls == [
        (
            8765,
            "https://news.example/api",
            "https://llm.example/v1",
            "key",
            "postgresql://db",
            "qwen3-embedding",
            "chat-model",
            "judge-model",
            "0.0.0.0",
        )
    ]


def test_live_backfill_routes_to_recent_combined_pipeline(monkeypatch, capsys):
    from crypto_analyser import live

    calls = []
    monkeypatch.setenv("LLM_API_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setattr(
        live,
        "run_live_backfill",
        lambda *args: calls.append(args)
        or {"detected": 2, "complete": 1, "failed": [], "skipped_existing": 1},
    )

    assert cli.main(["live-backfill", "--days", "5"]) == 0
    assert calls == [
        (
            5,
            "http://127.0.0.1:3000/api/news",
            "https://llm.example/v1",
            "key",
            "postgresql://db",
            "qwen3-embedding",
            "chat-model",
            "judge-model",
        )
    ]
    assert capsys.readouterr().out.strip() == "Detected 2; completed 1; failed 0; skipped existing 1."


def test_live_event_routes_to_explicit_window(monkeypatch, tmp_path, capsys):
    from crypto_analyser import live

    news_file = tmp_path / "event.json"
    news_file.write_text('{"articles": []}')
    calls = []
    monkeypatch.setenv("LLM_API_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.setattr(
        live,
        "run_live_event",
        lambda *args: calls.append(args)
        or {"detected": 1, "complete": 1, "failed": [], "skipped_existing": 0},
    )

    assert cli.main(
        [
            "live-event",
            "--start",
            "2026-07-06T11:00:00Z",
            "--end",
            "2026-07-06T14:00:00Z",
            "--news-file",
            str(news_file),
        ]
    ) == 0
    assert calls == [
        (
            "2026-07-06T11:00:00Z",
            "2026-07-06T14:00:00Z",
            news_file,
            "http://127.0.0.1:3000/api/news",
            "https://llm.example/v1",
            "key",
            "postgresql://db",
            "qwen3-embedding",
            "chat-model",
            "judge-model",
        )
    ]
    assert capsys.readouterr().out.strip() == "Detected 1; completed 1; failed 0; skipped existing 0."


def test_evaluate_reports_missing_optional_dependencies(monkeypatch, capsys):
    from crypto_analyser import evaluation

    monkeypatch.setenv("DATABASE_URL", "db")
    monkeypatch.setenv("LLM_API_URL", "api")
    monkeypatch.setenv("LLM_API_KEY", "key")

    def missing(*_args):
        raise ImportError("ragas")

    monkeypatch.setattr(evaluation, "write_evaluation", missing)
    assert cli.main(["evaluate"]) == 1
    assert "evaluation dependencies unavailable: ragas" in capsys.readouterr().err


def test_missing_environment_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda *_: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main(["news", "embed"]) == 1
    assert "DATABASE_URL is required" in capsys.readouterr().err


def test_live_requires_models_from_environment(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda *_: None)
    monkeypatch.setenv("LLM_API_URL", "https://llm.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "key")
    monkeypatch.setenv("DATABASE_URL", "postgresql://db")
    monkeypatch.delenv("LLM_MODEL")

    assert cli.main(["live"]) == 1
    assert "LLM_MODEL is required" in capsys.readouterr().err
