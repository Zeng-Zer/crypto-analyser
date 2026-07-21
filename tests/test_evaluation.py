import json
import sys
from types import ModuleType, SimpleNamespace

from crypto_analyser.evaluation import _episode_context, compare_modes, evaluate


def test_compare_modes_reports_overlap_and_verdict_changes():
    results = {
        "derivatives_only": {
            "episodes": [
                {"onset_ts": 1, "verdict": "explained_derivatives"},
                {"onset_ts": 2, "verdict": "unexplained"},
            ]
        },
        "derivatives_rag": {
            "episodes": [
                {"onset_ts": 1, "verdict": "explained_derivatives"},
                {"onset_ts": 2, "verdict": "explained_news"},
            ]
        },
        "news_only": {
            "episodes": [
                {"onset_ts": 1, "verdict": "unexplained"},
                {"onset_ts": 2, "verdict": "explained_news"},
            ]
        },
    }

    comparison = compare_modes(results)

    assert comparison["derivatives_vs_rag_verdict_agreement"] == 0.5
    assert comparison["context_overlap"] == {
        "derivatives_only": 1,
        "news_only": 1,
        "both": 0,
        "neither": 0,
    }
    assert comparison["finding"].startswith("Pre-onset news changed 1 of 2 combined verdicts.")


def test_episode_context_matches_classifier_inputs():
    context = _episode_context(
        {
            "symbol": "LUNAUSDT",
            "onset_ts": 123,
            "severity": "medium",
            "onset_triggers": ["price_zscore"],
            "peak_z": -3.5,
            "drawdown_onset_4h": -0.193,
            "return_onset_2h": -0.143,
            "derivatives": {
                "funding_rate_current": -0.00046,
                "funding_rate_avg_4h": -0.00046,
                "oi_current": 4_687_480,
                "oi_change_4h": -0.0118,
            },
        }
    )

    assert "drawdown_onset_4h=-0.193" in context
    assert "return_onset_2h=-0.143" in context
    assert "funding_rate_current=-0.0460%" in context
    assert "oi_change_4h=-1.18%" in context
    assert "funding_rate_threshold=0.0500%" in context
    assert "oi_change_4h_threshold=10%" in context


def test_evaluate_scores_only_combined_rationale(monkeypatch, tmp_path):
    calls = []

    class _Faithfulness:
        def __init__(self, _llm):
            pass

        def score(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(value=0.75)

    openai = ModuleType("openai")
    openai.AsyncOpenAI = lambda **_kwargs: object()
    ragas = ModuleType("ragas")
    ragas.__path__ = []
    ragas_llms = ModuleType("ragas.llms")
    ragas_llms.llm_factory = lambda *_args, **_kwargs: object()
    ragas_metrics = ModuleType("ragas.metrics")
    ragas_metrics.__path__ = []
    ragas_collections = ModuleType("ragas.metrics.collections")
    ragas_collections.Faithfulness = _Faithfulness
    for name, module in {
        "openai": openai,
        "ragas": ragas,
        "ragas.llms": ragas_llms,
        "ragas.metrics": ragas_metrics,
        "ragas.metrics.collections": ragas_collections,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    episode = {
        "symbol": "LUNAUSDT",
        "onset_ts": 123,
        "severity": "medium",
        "onset_triggers": ["price_zscore"],
        "peak_z": -3.5,
        "drawdown_onset_4h": -0.193,
        "return_onset_2h": -0.143,
        "derivatives": {
            "funding_rate_current": -0.00046,
            "funding_rate_avg_4h": -0.00046,
            "oi_current": 4_687_480,
            "oi_change_4h": -0.0118,
        },
        "classification": {
            "verdict": "explained_news",
            "synthesis": {"reasons": ["News explains move."], "supporting_refs": ["news_1"]},
            "rationale": "The drawdown and cited news support this result.",
        },
    }
    stem = "LUNAUSDT_2022-05-07_2022-05-11_summary.json"
    for mode in ("derivatives_only", "derivatives_rag", "news_only"):
        path = tmp_path / "reports" / mode / stem
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps({"classification_breakdown": {"explained_news": 1}, "episodes": [episode]}),
            encoding="utf-8",
        )
    rag_path = tmp_path / "rag" / "LUNAUSDT_123_rag.json"
    rag_path.parent.mkdir()
    rag_path.write_text(
        json.dumps(
            {
                "articles": [
                    {"id": 1, "date_pub": "2022-05-09T00:00:00+00:00", "title": "UST depeg", "description": "UST fell."}
                ]
            }
        ),
        encoding="utf-8",
    )

    result = evaluate("LUNAUSDT", "2022-05-07", "2022-05-11", "judge", "url", "key", tmp_path)

    assert len(calls) == 1
    assert result["derivatives_only"]["episodes"][0]["faithfulness"] is None
    assert result["news_only"]["episodes"][0]["faithfulness"] is None
    assert result["news_only"]["episodes"][0]["retrieved_news"][0]["title"] == "UST depeg"
    assert result["derivatives_rag"]["episodes"][0]["faithfulness"] == 0.75
    assert "drawdown_onset_4h=-0.193" in calls[0]["retrieved_contexts"][0]
    assert "source_ref: news_1" in calls[0]["retrieved_contexts"][1]
