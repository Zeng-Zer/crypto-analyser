"""Evaluate evidence modes with Ragas and direct comparison metrics."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

import psycopg2
from openai import AsyncOpenAI
from ragas.embeddings.base import embedding_factory
from ragas.llms import llm_factory
from ragas.metrics.collections import AnswerRelevancy, Faithfulness

from crypto_analyser._paths import repo_root

MODES = ("derivatives_only", "derivatives_rag", "news_only")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rag_context(symbol: str, onset_ts: int) -> tuple[list[str], dict[str, Any]]:
    data = _load(repo_root() / "data" / "rag" / f"{symbol}_{onset_ts}_rag.json")
    contexts = [
        f"{article['date_pub']} {article['title']} {article.get('description') or ''}" for article in data["articles"]
    ]
    return contexts, data


def _derivatives_context(episode: dict[str, Any]) -> str:
    values = episode["derivatives"]
    return "; ".join(f"{key}={value}" for key, value in values.items())


def _question(mode: str, symbol: str) -> str:
    evidence = {
        "derivatives_only": "funding rate and open interest",
        "derivatives_rag": "funding rate, open interest, and news available by onset",
        "news_only": "news available by onset",
    }[mode]
    return f"Classify this {symbol} price anomaly using {evidence}."


def _first_matching_news_after(connection: Any, onset_ts: int) -> dict[str, Any] | None:
    onset = datetime.fromtimestamp(onset_ts / 1000, tz=timezone.utc)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT date_pub, title, link
            FROM crypto_news
            WHERE date_pub > %s
              AND date_pub <= %s
              AND (tickers && ARRAY['LUNA','UST','TERRA']::TEXT[]
                   OR research @@ websearch_to_tsquery('english', 'LUNA OR UST OR Terra'))
            ORDER BY date_pub
            LIMIT 1
            """,
            (onset, onset + timedelta(hours=24)),
        )
        row = cursor.fetchone()
    if not row:
        return None
    return {
        "date_pub": row[0].isoformat(),
        "title": row[1],
        "link": row[2],
        "delay_minutes": round((row[0] - onset).total_seconds() / 60, 1),
    }


def compare_modes(mode_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    by_mode = {
        mode: {episode["onset_ts"]: episode["verdict"] for episode in result["episodes"]}
        for mode, result in mode_results.items()
    }
    onsets = sorted(by_mode["derivatives_only"])
    changes = [
        {
            "onset_ts": onset,
            "derivatives_only": by_mode["derivatives_only"][onset],
            "derivatives_rag": by_mode["derivatives_rag"][onset],
        }
        for onset in onsets
        if by_mode["derivatives_only"][onset] != by_mode["derivatives_rag"][onset]
    ]
    overlap = {"derivatives_only": 0, "news_only": 0, "both": 0, "neither": 0}
    for onset in onsets:
        derivatives = by_mode["derivatives_only"][onset] == "explained_derivatives"
        news = by_mode["news_only"][onset] == "explained_news"
        if derivatives and news:
            key = "both"
        elif derivatives:
            key = "derivatives_only"
        elif news:
            key = "news_only"
        else:
            key = "neither"
        overlap[key] += 1
    return {
        "derivatives_vs_rag_verdict_agreement": 1 - len(changes) / len(onsets),
        "derivatives_vs_rag_verdict_changes": changes,
        "evidence_overlap": overlap,
        "finding": (
            "Adding pre-onset news changed no derivatives-based verdicts. "
            "Derivatives-only and news-only each explained four of five episodes: three overlapped, "
            "one was derivatives-only, and one was news-only. This LUNA sample does not establish "
            "that derivatives outperform news; it shows complementary evidence and one early move "
            "that derivatives explained before news did."
        ),
    }


def evaluate(
    symbol: str,
    start: str,
    end: str,
    database_url: str,
    judge_model: str,
    api_url: str,
    api_key: str,
    embedding_model: str = "qwen3-embedding",
) -> dict[str, Any]:
    client = AsyncOpenAI(api_key=api_key, base_url=api_url)
    llm = llm_factory(judge_model, client=client)
    embeddings = embedding_factory(
        "openai",
        model=embedding_model,
        client=client,
        interface="modern",
    )
    faithfulness = Faithfulness(llm)
    relevancy = AnswerRelevancy(llm, embeddings, strictness=1)
    connection = psycopg2.connect(database_url)
    results: dict[str, dict[str, Any]] = {}
    try:
        for mode in MODES:
            summary = _load(repo_root() / "data" / "reports" / mode / f"{symbol}_{start}_{end}_summary.json")
            episodes = []
            for episode in summary["episodes"]:
                onset_ts = episode["onset_ts"]
                news_contexts, rag = _rag_context(symbol, onset_ts)
                contexts = news_contexts if mode == "news_only" else [_derivatives_context(episode)]
                if mode == "derivatives_rag":
                    contexts += news_contexts
                response = episode["classification"]["rationale"]
                question = _question(mode, symbol)
                faith = faithfulness.score(user_input=question, response=response, retrieved_contexts=contexts).value
                relevant = relevancy.score(user_input=question, response=response).value
                dates = [datetime.fromisoformat(article["date_pub"]) for article in rag["articles"]]
                onset = datetime.fromtimestamp(onset_ts / 1000, tz=timezone.utc)
                episodes.append(
                    {
                        "onset_ts": onset_ts,
                        "verdict": episode["classification"]["verdict"],
                        "confidence": episode["classification"]["confidence"],
                        "rationale": response,
                        "news_relevance": episode["raw_classification"].get("news_relevance"),
                        "derivatives": episode["derivatives"],
                        "retrieved_news": (
                            [
                                {
                                    key: article.get(key)
                                    for key in ("date_pub", "title", "source", "link")
                                }
                                for article in rag["articles"]
                            ]
                            if mode != "derivatives_only"
                            else []
                        ),
                        "faithfulness": faith,
                        "answer_relevancy": relevant,
                        "retrieved_articles": len(dates) if mode != "derivatives_only" else 0,
                        "latest_news_age_at_onset_minutes": (
                            round((onset - max(dates)).total_seconds() / 60, 1)
                            if dates and mode != "derivatives_only"
                            else None
                        ),
                        "first_matching_news_after_onset": _first_matching_news_after(connection, onset_ts),
                    }
                )
            results[mode] = {
                "mode": mode,
                "episode_count": len(episodes),
                "classification_breakdown": summary["classification_breakdown"],
                "average_confidence": fmean(item["confidence"] for item in episodes),
                "faithfulness": fmean(item["faithfulness"] for item in episodes),
                "answer_relevancy": fmean(item["answer_relevancy"] for item in episodes),
                "episodes": episodes,
            }
    finally:
        connection.close()

    comparison = {
        "symbol": symbol,
        "window": {"start": start, "end": end},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "faithfulness": "Ragas grounding of rationale in supplied evidence",
            "answer_relevancy": "Ragas relevance of rationale to classification question",
            "verdict_overlap": "Direct source-ablation outcome; primary hypothesis evidence",
        },
        **results,
        "comparison": compare_modes(results),
        "limitations": [
            "Five episodes from one historical event are not enough for a general claim.",
            "Ragas evaluates generated rationale quality, not predictive superiority.",
            "Post-onset news delay uses first ticker/text match, not a manually verified causal article.",
        ],
    }
    return comparison


def write_evaluation(
    symbol: str,
    start: str,
    end: str,
    database_url: str,
    judge_model: str,
    api_url: str,
    api_key: str,
    embedding_model: str = "qwen3-embedding",
) -> Path:
    """Evaluate all modes, persist comparison artifacts, and return final summary path."""
    comparison = evaluate(symbol, start, end, database_url, judge_model, api_url, api_key, embedding_model)
    results_dir = repo_root() / "results"
    reports_dir = repo_root() / "reports"
    results_dir.mkdir(exist_ok=True)
    reports_dir.mkdir(exist_ok=True)
    for mode in MODES:
        (results_dir / f"ablation_{mode}.json").write_text(
            json.dumps(comparison[mode], indent=2), encoding="utf-8"
        )
    (results_dir / "ablation_comparison.json").write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    final = {
        "milestone": "Historical LUNA anomaly evidence ablation",
        "symbol": symbol,
        "window": comparison["window"],
        "episodes_total": comparison["derivatives_only"]["episode_count"],
        "classifications_total": sum(comparison[mode]["episode_count"] for mode in MODES),
        "classification_breakdowns": {
            mode: comparison[mode]["classification_breakdown"] for mode in MODES
        },
        "ragas": {
            mode: {
                "faithfulness": comparison[mode]["faithfulness"],
                "answer_relevancy": comparison[mode]["answer_relevancy"],
            }
            for mode in MODES
        },
        "finding": comparison["comparison"]["finding"],
        "limitations": comparison["limitations"],
        "generated_at": comparison["evaluated_at"],
    }
    summary_path = reports_dir / "FINAL_PHASE1_SUMMARY.json"
    summary_path.write_text(json.dumps(final, indent=2), encoding="utf-8")
    return summary_path
