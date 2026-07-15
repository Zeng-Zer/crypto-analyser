from pathlib import Path

import pytest

from crypto_analyser.classification import episodes


def test_rag_mode_requires_retrieval_file(monkeypatch, tmp_path):
    monkeypatch.setattr(episodes, "RAG_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="run retrieval"):
        episodes._rag_block("LUNAUSDT", 123)


def test_news_only_prompt_excludes_derivatives(monkeypatch, tmp_path):
    prompt = episodes.PromptTemplate.load(Path("prompts/classification_prompt.md"))
    monkeypatch.setattr(
        episodes,
        "_rag_block",
        lambda *_args: {"rag_context_block": "Terra UST depeg", "k": "5", "window": "24h before onset"},
    )
    episode = {"onset_ts": 123, "severity": "high", "peak_z": -4.0}
    meta = {"symbol": "LUNAUSDT", "start": "2022-05-07", "end": "2022-05-11"}

    system, user, _ = episodes._build_prompts(prompt, episode, {}, meta, {}, "news_only")

    assert "Do not infer or mention funding" in system
    assert "Terra UST depeg" in user
    assert "funding_rate_current" not in user
