import json

from crypto_analyser.reporting import json_reports


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_ablation_modes_write_separate_reports(tmp_path):
    symbol, start, end, onset = "LUNAUSDT", "2022-05-07", "2022-05-11", 123
    stem = f"{symbol}_{start}_{end}"
    episode = {"onset_ts": onset, "peak_z": -4.2, "severity": "high", "direction": "crash"}
    _write(
        tmp_path / "anomalies" / f"{stem}.json",
        {"meta": {"symbol": symbol, "start": start, "end": end}, "episodes": [episode]},
    )
    _write(
        tmp_path / "context" / f"{stem}_context.json",
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
        "synthesis": {"reasons": ["No supplied context explains the move."], "supporting_refs": []},
        "rationale": "No corroborating signal.",
    }
    for mode in ("derivatives_only", "derivatives_rag", "news_only"):
        _write(tmp_path / "classifications" / mode / f"{symbol}_{onset}.json", classification)

    paths = [json_reports.generate(symbol, start, end, mode, data_dir=tmp_path)[0] for mode in json_reports.VALID_MODES]

    assert {path.parent.name for path in paths} == json_reports.VALID_MODES
    news_summary = json.loads((tmp_path / "reports" / "news_only" / f"{stem}_summary.json").read_text())
    assert news_summary["episodes"][0]["derivatives"] is None
    assert news_summary["episodes"][0]["classification"]["synthesis"]["reasons"]
    assert "news_relevance" not in news_summary["episodes"][0]["classification"]
    assert "raw_episode" not in news_summary["episodes"][0]
