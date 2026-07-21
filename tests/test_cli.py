from pathlib import Path

from crypto_analyser import cli


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
                "llm_model": "glm-5.2-short",
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


def test_evaluate_reports_missing_optional_dependencies(monkeypatch, capsys):
    from crypto_analyser import evaluation

    monkeypatch.setenv("DATABASE_URL", "db")
    monkeypatch.setenv("LLM_API_URL", "api")
    monkeypatch.setenv("LLM_API_KEY", "key")

    def missing(*_args):
        raise ImportError("ragas")

    monkeypatch.setattr(evaluation, "write_evaluation", missing)
    assert cli.main(["evaluate"]) == 1
    assert "install crypto-analyser[evaluation]" in capsys.readouterr().err


def test_missing_environment_returns_nonzero(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_dotenv", lambda *_: None)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert cli.main(["news", "embed"]) == 1
    assert "DATABASE_URL is required" in capsys.readouterr().err
