import json

import pytest

from crypto_analyser.classification import episodes
from crypto_analyser.llm_client import ClassificationResult


def test_rag_mode_requires_retrieval_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="run retrieval"):
        episodes._rag_block("LUNAUSDT", 123, tmp_path)


def test_rag_block_adds_stable_article_refs(tmp_path):
    path = tmp_path / "LUNAUSDT_123_rag.json"
    path.write_text(
        json.dumps(
            {
                "k": 1,
                "window": "24h before onset",
                "articles": [
                    {
                        "id": 42,
                        "date_pub": "2022-05-09T21:03:14+00:00",
                        "title": "UST falls below $0.95",
                        "description": "TerraUSD lost its peg.",
                    }
                ],
            }
        )
    )

    block = episodes._rag_block("LUNAUSDT", 123, tmp_path)

    assert "[source_ref: news_42]" in block["rag_context_block"]


def test_news_only_prompt_excludes_derivatives(monkeypatch, tmp_path):
    prompt = episodes.PromptTemplate.load()
    monkeypatch.setattr(
        episodes,
        "_rag_block",
        lambda *_args: {"rag_context_block": "Terra UST depeg", "k": "5", "window": "24h before onset"},
    )
    episode = {"onset_ts": 123, "severity": "high", "peak_z": -4.0}
    meta = {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"}

    system, user, _ = episodes._build_prompts(prompt, episode, {}, meta, "news_only")

    assert "Do not infer or mention funding" in system
    assert "Terra UST depeg" in user
    assert "funding_rate_current" not in user


def test_invalid_or_verdict_inconsistent_supporting_refs_fail(tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "LUNAUSDT_123_rag.json").write_text(json.dumps({"articles": [{"id": 42}]}))
    result = ClassificationResult.from_dict(
        {
            "event_reference": "LUNAUSDT_123",
            "classification": "explained_news",
            "confidence": 0.9,
            "synthesis": {
                "reasons": ["Pre-onset UST depeg reporting provides an event-specific explanation."],
                "supporting_refs": ["funding_rate_current", "news_42"],
            },
            "rationale": "Detailed rationale.",
        }
    )

    with pytest.raises(ValueError, match="requires news refs and no derivative refs"):
        episodes._validate_supporting_refs(
            result,
            "derivatives_rag",
            {"onset_ts": 123},
            {"funding_rate_current": 0, "oi_change_4h": 0},
            {"symbol": "LUNAUSDT"},
            tmp_path,
        )


def test_derivative_breach_rejects_news_verdict(tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir()
    (rag_dir / "LUNAUSDT_123_rag.json").write_text(json.dumps({"articles": [{"id": 42}]}))
    result = ClassificationResult.from_dict(
        {
            "event_reference": "LUNAUSDT_123",
            "classification": "explained_news",
            "confidence": 0.9,
            "synthesis": {"reasons": ["News explains the move."], "supporting_refs": ["news_42"]},
            "rationale": "Detailed rationale.",
        }
    )

    with pytest.raises(ValueError, match="breached derivatives require explained_derivatives"):
        episodes._validate_supporting_refs(
            result,
            "derivatives_rag",
            {"onset_ts": 123},
            {"funding_rate_current": 0.001, "oi_change_4h": 0},
            {"symbol": "LUNAUSDT"},
            tmp_path,
        )


def test_missing_derivative_rejects_explanatory_verdict(tmp_path):
    result = ClassificationResult.from_dict(
        {
            "event_reference": "LUNAUSDT_123",
            "classification": "unexplained",
            "confidence": 0.9,
            "synthesis": {"reasons": ["No explanation."], "supporting_refs": []},
            "rationale": "Detailed rationale.",
        }
    )

    with pytest.raises(ValueError, match="missing derivatives require insufficient_data"):
        episodes._validate_supporting_refs(
            result,
            "derivatives_only",
            {"onset_ts": 123},
            {"funding_rate_current": None, "oi_change_4h": 0},
            {"symbol": "LUNAUSDT"},
            tmp_path,
        )


def test_complete_derivatives_reject_insufficient_data(tmp_path):
    result = ClassificationResult.from_dict(
        {
            "event_reference": "LUNAUSDT_123",
            "classification": "insufficient_data",
            "confidence": 0.9,
            "synthesis": {"reasons": ["Data missing."], "supporting_refs": []},
            "rationale": "Detailed rationale.",
        }
    )

    with pytest.raises(ValueError, match="insufficient_data requires missing derivatives"):
        episodes._validate_supporting_refs(
            result,
            "derivatives_only",
            {"onset_ts": 123},
            {"funding_rate_current": 0, "oi_change_4h": 0},
            {"symbol": "LUNAUSDT"},
            tmp_path,
        )


def test_synthesis_rejects_verbose_reasons():
    with pytest.raises(ValueError, match="at most 160"):
        ClassificationResult.from_dict(
            {
                "event_reference": "LUNAUSDT_123",
                "classification": "unexplained",
                "confidence": 0.8,
                "synthesis": {"reasons": ["x" * 161], "supporting_refs": []},
                "rationale": "Detailed rationale.",
            }
        )


def test_derivatives_thresholds_are_fixed_prompt_inputs():
    prompt = episodes.PromptTemplate.load()
    episode = {"onset_ts": 123, "severity": "high", "peak_z": -4.0}
    meta = {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"}

    system, _, _ = episodes._build_prompts(prompt, episode, {}, meta, "derivatives_only")

    assert "0.0500%" in system
    assert "10%" in system


def test_derivatives_prompt_formats_rates_as_percentages():
    prompt = episodes.PromptTemplate.load()
    episode = {"onset_ts": 123, "severity": "high", "peak_z": -4.0}
    features = {
        "funding_rate_current": -0.00046004,
        "funding_rate_avg_4h": -0.0004,
        "oi_current": 4_687_480,
        "oi_change_4h": 0.11575157,
    }
    meta = {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"}

    _, user, _ = episodes._build_prompts(prompt, episode, features, meta, "derivatives_only")

    assert "funding_rate_current  : -0.0460%" in user
    assert "funding_rate_avg_4h   : -0.0400%" in user
    assert "oi_change_4h          : 11.58%" in user
