import json

from crypto_analyser.reporting import json_reports as report_json


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_ablation_modes_write_separate_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(report_json, "REPO", tmp_path)
    symbol, start, end, onset = "LUNAUSDT", "2022-05-07", "2022-05-11", 123
    stem = f"{symbol}_{start}_{end}"
    episode = {"onset_ts": onset, "peak_z": -4.2, "severity": "high", "direction": "down"}

    _write(
        tmp_path / "data" / "anomalies" / f"{stem}.json",
        {"meta": {"symbol": symbol, "start": start, "end": end}, "episodes": [episode]},
    )
    _write(
        tmp_path / "data" / "context" / f"{stem}_context.json",
        {
            "features": [
                {
                    "onset_ts": onset,
                    "funding_rate_current": 0,
                    "funding_rate_avg_4h": 0,
                    "oi_current": 1,
                    "oi_change_4h": 0,
                }
            ]
        },
    )
    classification = {
        "onset_ts": onset,
        "classification": "unexplained",
        "confidence": 0.8,
        "rationale": "No corroborating signal.",
        "news_relevance": None,
    }
    for mode in ("derivatives_only", "derivatives_rag"):
        _write(tmp_path / "data" / "classifications" / mode / f"{symbol}_{onset}.json", classification)

    run_a, _ = report_json.generate(symbol, start, end, "derivatives_only")
    run_b, _ = report_json.generate(symbol, start, end, "derivatives_rag")

    assert run_a.parent.name == "derivatives_only"
    assert run_b.parent.name == "derivatives_rag"
    assert run_a != run_b
    assert run_a.exists() and run_b.exists()
