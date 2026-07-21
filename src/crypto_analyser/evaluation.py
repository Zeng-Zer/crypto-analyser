"""Compare context modes and check combined rationales with Ragas."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any

from crypto_analyser._paths import data_root, repo_root
from crypto_analyser.constants import FUNDING_RATE_THRESHOLD, OI_CHANGE_THRESHOLD

MODES = ("derivatives_only", "derivatives_rag", "news_only")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _rag_context(symbol: str, onset_ts: int, data_dir: Path) -> tuple[list[str], dict[str, Any]]:
    data = _load(data_dir / "rag" / f"{symbol}_{onset_ts}_rag.json")
    contexts = [
        (
            f"[source_ref: news_{article['id']}] "
            f"{article['date_pub']} {article['title']} {article.get('description') or ''}"
        )
        for article in data["articles"]
    ]
    return contexts, data


def _percent(value: float | None, places: int) -> str | None:
    return None if value is None else f"{value * 100:.{places}f}%"


def _episode_context(episode: dict[str, Any]) -> str:
    """Return every episode fact supplied to the combined classifier."""
    derivatives = episode["derivatives"]
    facts = {
        "event_reference": f"{episode['symbol']}_{episode['onset_ts']}",
        "symbol": episode["symbol"],
        "onset_ts": episode["onset_ts"],
        "severity": episode["severity"],
        "detection_triggers": episode.get("onset_triggers", episode.get("triggers")),
        "peak_z_abs": abs(episode["peak_z"]) if episode.get("peak_z") is not None else None,
        "drawdown_onset_4h": episode.get("drawdown_onset_4h"),
        "return_onset_2h": episode.get("return_onset_2h"),
        "funding_rate_current": _percent(derivatives["funding_rate_current"], 4),
        "funding_rate_avg_4h": _percent(derivatives["funding_rate_avg_4h"], 4),
        "oi_current": derivatives["oi_current"],
        "oi_change_4h": _percent(derivatives["oi_change_4h"], 2),
        "funding_rate_threshold": _percent(FUNDING_RATE_THRESHOLD, 4),
        "oi_change_4h_threshold": _percent(OI_CHANGE_THRESHOLD, 0),
    }
    return "; ".join(f"{key}={value}" for key, value in facts.items())


def _question(symbol: str) -> str:
    return f"Classify this {symbol} price anomaly using market data and news available by onset."


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
    total = len(onsets)
    derivatives_explained = overlap["derivatives_only"] + overlap["both"]
    news_explained = overlap["news_only"] + overlap["both"]
    return {
        "derivatives_vs_rag_verdict_agreement": 1 - len(changes) / total,
        "derivatives_vs_rag_verdict_changes": changes,
        "context_overlap": overlap,
        "finding": (
            f"Pre-onset news changed {len(changes)} of {total} combined verdicts. "
            f"Derivatives-only explained {derivatives_explained}; news-only explained {news_explained}; "
            f"{overlap['both']} overlapped, {overlap['derivatives_only']} was derivatives-only, "
            f"{overlap['news_only']} was news-only, and {overlap['neither']} was unexplained by either. "
            "This LUNA sample shows evidence overlap; it does not establish general source superiority."
        ),
    }


def evaluate(
    symbol: str,
    start: str,
    end: str,
    judge_model: str,
    api_url: str,
    api_key: str,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import Faithfulness

    root = data_dir or data_root()
    client = AsyncOpenAI(api_key=api_key, base_url=api_url)
    faithfulness = Faithfulness(llm_factory(judge_model, client=client, max_tokens=4096))
    results: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        summary = _load(root / "reports" / mode / f"{symbol}_{start}_{end}_summary.json")
        episodes = []
        for episode in summary["episodes"]:
            classification = episode["classification"]
            faith = None
            retrieved_news = []
            if mode != "derivatives_only":
                news_contexts, rag = _rag_context(symbol, episode["onset_ts"], root)
                retrieved_news = [
                    {key: article.get(key) for key in ("date_pub", "title", "source", "link")}
                    for article in rag["articles"]
                ]
            if mode == "derivatives_rag":
                faith = faithfulness.score(
                    user_input=_question(symbol),
                    response=classification["rationale"],
                    retrieved_contexts=[_episode_context(episode), *news_contexts],
                ).value
            episodes.append(
                {
                    "onset_ts": episode["onset_ts"],
                    "verdict": classification["verdict"],
                    "synthesis": classification["synthesis"],
                    "rationale": classification["rationale"],
                    "faithfulness": faith,
                    "retrieved_news": retrieved_news,
                }
            )
        scores = [episode["faithfulness"] for episode in episodes if episode["faithfulness"] is not None]
        results[mode] = {
            "mode": mode,
            "episode_count": len(episodes),
            "classification_breakdown": summary["classification_breakdown"],
            "faithfulness": fmean(scores) if scores else None,
            "episodes": episodes,
        }

    return {
        "symbol": symbol,
        "window": {"start": start, "end": end},
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "faithfulness": "Ragas share of combined-rationale claims supported by supplied context",
            "verdict_comparison": "Controlled outcome when classifier context changes",
        },
        **results,
        "comparison": compare_modes(results),
        "limitations": [
            "Ragas Faithfulness evaluates rationale support, not whether the verdict is correct.",
            "One eight-episode LUNA case study does not prove causality or source superiority.",
        ],
    }


def write_evaluation(
    symbol: str,
    start: str,
    end: str,
    judge_model: str,
    api_url: str,
    api_key: str,
    data_dir: Path | None = None,
) -> Path:
    """Evaluate combined rationales, persist comparison artifacts, and return final summary path."""
    comparison = evaluate(symbol, start, end, judge_model, api_url, api_key, data_dir)
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
        "milestone": "Historical LUNA anomaly context comparison",
        "symbol": symbol,
        "window": comparison["window"],
        "episodes_total": comparison["derivatives_only"]["episode_count"],
        "classifications_total": sum(comparison[mode]["episode_count"] for mode in MODES),
        "classification_breakdowns": {
            mode: comparison[mode]["classification_breakdown"] for mode in MODES
        },
        "ragas": {
            "derivatives_rag": {"faithfulness": comparison["derivatives_rag"]["faithfulness"]}
        },
        "finding": comparison["comparison"]["finding"],
        "limitations": comparison["limitations"],
        "generated_at": comparison["evaluated_at"],
    }
    summary_path = reports_dir / "FINAL_PHASE1_SUMMARY.json"
    summary_path.write_text(json.dumps(final, indent=2), encoding="utf-8")
    return summary_path
