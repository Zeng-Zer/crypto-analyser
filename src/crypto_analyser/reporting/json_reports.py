"""Build mode-isolated JSON reports from pipeline outputs.

Reports are written under ``data/reports/{mode}/`` so ablation runs cannot
overwrite one another.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from crypto_analyser._paths import repo_root

REPO = repo_root()
VALID_MODES = {"derivatives_only", "derivatives_rag"}


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _episode_report(
    symbol: str,
    episode: dict[str, Any],
    features: dict[str, Any] | None,
    classification: dict[str, Any] | None,
    mode: str,
) -> dict[str, Any]:
    """Merge one episode with its derivatives features and classification."""
    onset = episode["onset_ts"]
    deriv = (
        {k: features[k] for k in ("funding_rate_current", "funding_rate_avg_4h", "oi_current", "oi_change_4h")}
        if features
        else None
    )
    rag_context = None
    news_relevance = classification.get("news_relevance") if classification else None
    if classification and news_relevance is not None:
        rag_context = {"news_relevance": news_relevance}
    verdict = classification.get("classification") if classification else None
    return {
        "symbol": symbol,
        "onset_ts": onset,  # spec: timestamp
        "peak_z": episode.get("peak_z"),  # spec: Z-score
        "severity": episode.get("severity"),
        "direction": episode.get("direction"),
        "derivatives": deriv,  # spec: derivatives features
        "rag_context": rag_context,  # spec: RAG context (optional)
        "classification": {
            "verdict": verdict,
            "confidence": classification.get("confidence") if classification else None,
            "rationale": classification.get("rationale") if classification else None,
            "mode": mode,
        }
        if classification
        else None,
        # ponytail: passthrough of intermediate-file fields for traceability;
        # the headline fields above are the report's user-facing read. Keys are
        # named after their semantic source (episode / features / classification),
        # NOT after internal plan task numbers — schema must outlive renumbering.
        "raw_episode": episode,
        "raw_features": features,
        "raw_classification": classification,
    }


def generate(
    symbol: str,
    start: str,
    end: str,
    mode: str,
) -> tuple[Path, list[Path]]:
    """Build reports. Returns ``summary_path`` + per-episode report paths (for this run only)."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")

    anomalies_path = REPO / "data" / "anomalies" / f"{symbol}_{start}_{end}.json"
    context_path = REPO / "data" / "context" / f"{symbol}_{start}_{end}_context.json"
    cls_dir = REPO / "data" / "classifications" / mode

    anom = _load_json(anomalies_path)
    episodes = anom["episodes"]

    if context_path.exists():
        ctx = _load_json(context_path)
        feat_by_onset = {f["onset_ts"]: f for f in ctx["features"]}
    else:
        feat_by_onset = {}

    cls_by_onset: dict[int, dict[str, Any]] = {}
    if cls_dir.exists():
        for cf in sorted(cls_dir.glob(f"{symbol}_*.json")):
            cd = _load_json(cf)
            cls_by_onset[cd["onset_ts"]] = cd

    reports_dir = REPO / "data" / "reports" / mode
    reports_dir.mkdir(parents=True, exist_ok=True)

    summary_episodes: list[dict[str, Any]] = []
    per_paths: list[Path] = []
    breakdown: dict[str, int] = {}
    for ep in episodes:
        onset = ep["onset_ts"]
        features = feat_by_onset.get(onset)
        classification = cls_by_onset.get(onset)

        per = _episode_report(symbol, ep, features, classification, mode)
        per_path = reports_dir / f"{symbol}_{onset}_report.json"
        with per_path.open("w", encoding="utf-8") as f:
            json.dump(per, f, indent=2, ensure_ascii=False)
        per_paths.append(per_path)
        summary_episodes.append(per)

        if classification and (verdict := classification.get("classification")):
            breakdown[verdict] = breakdown.get(verdict, 0) + 1

    summary = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "mode": mode,
        "sources": {
            "anomalies": str(anomalies_path.relative_to(REPO)),
            "context": str(context_path.relative_to(REPO)) if context_path.exists() else None,
            "classifications_dir": str(cls_dir.relative_to(REPO)),
        },
        "episode_count": len(summary_episodes),
        "classification_breakdown": breakdown or None,
        "episodes": summary_episodes,
    }
    summary_path = reports_dir / f"{symbol}_{start}_{end}_summary.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary_path, per_paths


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="crypto_analyser.reporting.json_reports",
        description="Build JSON reports from anomalies + derivatives + classification.",
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--mode",
        required=True,
        choices=sorted(VALID_MODES),
        help="Classification run mode (determines input directory).",
    )
    args = parser.parse_args()

    summary_path, per_paths = generate(args.symbol, args.start, args.end, args.mode)

    print(f"report_generator: symbol={args.symbol} mode={args.mode}")
    print(f"  summary:  {summary_path.relative_to(REPO)}")
    print(f"  episodes: {len(per_paths)} per-episode reports under data/reports/{args.mode}/")


if __name__ == "__main__":
    main()
