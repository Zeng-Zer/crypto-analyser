from crypto_analyser.evaluation import compare_modes


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
    assert comparison["evidence_overlap"] == {
        "derivatives_only": 1,
        "news_only": 1,
        "both": 0,
        "neither": 0,
    }
