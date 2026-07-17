import pytest

from crypto_analyser.classification import episodes


def test_rag_mode_requires_retrieval_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="run retrieval"):
        episodes._rag_block("LUNAUSDT", 123, tmp_path)


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


def test_derivatives_thresholds_are_explicit_prompt_inputs():
    prompt = episodes.PromptTemplate.load()
    episode = {"onset_ts": 123, "severity": "high", "peak_z": -4.0}
    meta = {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"}

    system, _, _ = episodes._build_prompts(
        prompt,
        episode,
        {},
        meta,
        "derivatives_only",
        funding_rate_threshold=0.123,
        oi_change_threshold=0.456,
    )

    assert "0.123" in system
    assert "0.456" in system
