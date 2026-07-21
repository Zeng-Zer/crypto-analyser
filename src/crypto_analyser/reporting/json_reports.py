"""Build mode-isolated JSON reports from pipeline outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crypto_analyser._paths import data_root

VALID_MODES = {"derivatives_only", "derivatives_rag", "news_only"}
_DERIVATIVE_FIELDS = ("funding_rate_current", "funding_rate_avg_4h", "oi_current", "oi_change_4h")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _episode_report(
    symbol: str,
    episode: dict[str, Any],
    features: dict[str, Any] | None,
    classification: dict[str, Any] | None,
    mode: str,
) -> dict[str, Any]:
    derivatives = (
        {key: features[key] for key in _DERIVATIVE_FIELDS} if features and mode != "news_only" else None
    )
    return {
        "symbol": symbol,
        **episode,
        "derivatives": derivatives,
        "classification": (
            {
                "verdict": classification["classification"],
                "confidence": classification["confidence"],
                "synthesis": classification["synthesis"],
                "rationale": classification["rationale"],
                "mode": mode,
            }
            if classification
            else None
        ),
    }


def generate(
    symbol: str,
    start: str,
    end: str,
    mode: str,
    *,
    data_dir: Path | None = None,
) -> tuple[Path, list[Path]]:
    """Build summary and per-episode reports for one run."""
    if mode not in VALID_MODES:
        raise ValueError(f"invalid mode {mode!r}; expected one of {VALID_MODES}")
    root = data_dir or data_root()
    anomalies_path = root / "anomalies" / f"{symbol}_{start}_{end}.json"
    context_path = root / "context" / f"{symbol}_{start}_{end}_context.json"
    classifications_dir = root / "classifications" / mode

    episodes = _load(anomalies_path)["episodes"]
    features = _load(context_path)["features"] if context_path.exists() and mode != "news_only" else []
    feature_by_onset = {feature["onset_ts"]: feature for feature in features}
    classifications = [_load(path) for path in sorted(classifications_dir.glob(f"{symbol}_*.json"))]
    classification_by_onset = {item["onset_ts"]: item for item in classifications}

    reports_dir = root / "reports" / mode
    reports_dir.mkdir(parents=True, exist_ok=True)
    reports = []
    paths = []
    breakdown: dict[str, int] = {}
    for episode in episodes:
        onset = episode["onset_ts"]
        report = _episode_report(
            symbol,
            episode,
            feature_by_onset.get(onset),
            classification_by_onset.get(onset),
            mode,
        )
        path = reports_dir / f"{symbol}_{onset}_report.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        reports.append(report)
        paths.append(path)
        if report["classification"]:
            verdict = report["classification"]["verdict"]
            breakdown[verdict] = breakdown.get(verdict, 0) + 1

    summary = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "mode": mode,
        "episode_count": len(reports),
        "classification_breakdown": breakdown or None,
        "episodes": reports,
    }
    summary_path = reports_dir / f"{symbol}_{start}_{end}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary_path, paths
