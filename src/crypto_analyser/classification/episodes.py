"""Classify anomaly episodes with structured LLM output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_analyser._paths import asset_path, data_root
from crypto_analyser.constants import FUNDING_RATE_THRESHOLD, LLM_MODEL, OI_CHANGE_THRESHOLD
from crypto_analyser.llm_client import ClassificationResult, LLMClient

PROMPT_PATH = asset_path("classification_prompt.md")
_RAG_K_DEFAULT = 5
_RAG_WINDOW_DEFAULT = "24h before onset"
_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
_SLOT_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ClassificationValidationError(RuntimeError):
    """Raised when LLM output fails the classification JSON schema."""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    """System and user templates for all three evidence modes."""

    system: str
    user_run_a: str
    user_run_b: str
    system_run_c: str
    user_run_c: str

    @classmethod
    def load(cls, path: Path = PROMPT_PATH) -> "PromptTemplate":
        blocks = _FENCE_RE.findall(path.read_text(encoding="utf-8"))
        if len(blocks) < 5:
            raise ValueError(f"{path}: expected >=5 fenced prompt blocks, found {len(blocks)}")
        return cls(*(block.strip() for block in blocks[:5]))


def _render(template: str, variables: dict[str, Any]) -> str:
    """Substitute slot-shaped tokens while leaving comma-list prose intact."""
    safe = {key: "null" if value is None else str(value) for key, value in variables.items()}
    return _SLOT_RE.sub(lambda match: safe.get(match.group(1), "null"), template)


def _episode_features(context: dict, onset_ts: int) -> dict | None:
    return next((feature for feature in context["features"] if feature["onset_ts"] == onset_ts), None)


def _episode_vars(episode: dict, features: dict | None, meta: dict, event_reference: str) -> dict[str, Any]:
    return {
        "symbol": meta["symbol"],
        "start": meta["start"],
        "end": meta["end"],
        "onset_ts": episode["onset_ts"],
        "severity": episode["severity"],
        "peak_z_abs": abs(episode["peak_z"]),
        "event_reference": event_reference,
        "funding_rate_current": features.get("funding_rate_current") if features else None,
        "funding_rate_avg_4h": features.get("funding_rate_avg_4h") if features else None,
        "oi_current": features.get("oi_current") if features else None,
        "oi_change_4h": features.get("oi_change_4h") if features else None,
    }


def _rag_block(symbol: str, onset_ts: int, rag_dir: Path | None = None) -> dict[str, str]:
    rag_path = (rag_dir or data_root() / "rag") / f"{symbol}_{onset_ts}_rag.json"
    if not rag_path.exists():
        raise FileNotFoundError(f"RAG context not found: {rag_path}; run retrieval before derivatives_rag")
    rag = json.loads(rag_path.read_text(encoding="utf-8"))
    return {
        "rag_context_block": rag["block"],
        "k": str(rag.get("k", _RAG_K_DEFAULT)),
        "window": rag.get("window", _RAG_WINDOW_DEFAULT),
    }


def _build_prompts(
    template: PromptTemplate,
    episode: dict,
    features: dict | None,
    meta: dict,
    mode: str,
    *,
    funding_rate_threshold: float = FUNDING_RATE_THRESHOLD,
    oi_change_threshold: float = OI_CHANGE_THRESHOLD,
    rag_dir: Path | None = None,
) -> tuple[str, str, str]:
    event_reference = f"{meta['symbol']}_{episode['onset_ts']}"
    variables = _episode_vars(episode, features, meta, event_reference)
    if mode == "news_only":
        variables.update(_rag_block(meta["symbol"], episode["onset_ts"], rag_dir))
        return template.system_run_c, _render(template.user_run_c, variables), event_reference

    system = _render(
        template.system,
        {
            "funding_rate_mag_threshold": funding_rate_threshold,
            "oi_change_4h_threshold": oi_change_threshold,
        },
    )
    if mode == "derivatives_rag":
        variables.update(_rag_block(meta["symbol"], episode["onset_ts"], rag_dir))
        user = _render(template.user_run_b, variables)
    else:
        user = _render(template.user_run_a, variables)
    return system, user, event_reference


def _write_classification(
    result: ClassificationResult,
    episode: dict,
    symbol: str,
    mode: str,
    output_dir: Path,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{symbol}_{episode['onset_ts']}.json"
    path.write_text(
        json.dumps(
            {
                "event_reference": result.event_reference,
                "classification": result.classification,
                "severity": episode["severity"],
                "confidence": result.confidence,
                "rationale": result.rationale,
                "news_relevance": result.news_relevance,
                "mode": mode,
                "onset_ts": episode["onset_ts"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def classify_episodes(
    episodes: list[dict],
    context: dict,
    meta: dict,
    client: LLMClient,
    template: PromptTemplate,
    mode: str,
    *,
    data_dir: Path | None = None,
    funding_rate_threshold: float = FUNDING_RATE_THRESHOLD,
    oi_change_threshold: float = OI_CHANGE_THRESHOLD,
) -> list[Path]:
    root = data_dir or data_root()
    paths = []
    for episode in episodes:
        system_prompt, user_prompt, event_reference = _build_prompts(
            template,
            episode,
            _episode_features(context, episode["onset_ts"]),
            meta,
            mode,
            funding_rate_threshold=funding_rate_threshold,
            oi_change_threshold=oi_change_threshold,
            rag_dir=root / "rag",
        )
        try:
            result = client.classify(user_prompt, event_reference, system_prompt)
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise ClassificationValidationError(
                f"LLM response failed schema validation for {event_reference}: {exc}"
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"LLM call failed for {event_reference}: {exc}") from exc
        paths.append(_write_classification(result, episode, meta["symbol"], mode, root / "classifications" / mode))
    return paths


def classify_batch(
    anomalies_path: Path,
    mode: str,
    *,
    data_dir: Path | None = None,
    context_path: Path | None = None,
    client: LLMClient | None = None,
    model: str = LLM_MODEL,
    funding_rate_threshold: float = FUNDING_RATE_THRESHOLD,
    oi_change_threshold: float = OI_CHANGE_THRESHOLD,
) -> list[Path]:
    root = data_dir or data_root()
    anomalies = json.loads(anomalies_path.read_text(encoding="utf-8"))
    if mode == "news_only":
        context = {"features": []}
    else:
        context_path = context_path or root / "context" / f"{anomalies_path.stem}_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
    return classify_episodes(
        anomalies["episodes"],
        context,
        anomalies["meta"],
        client or LLMClient(model=model),
        PromptTemplate.load(),
        mode,
        data_dir=root,
        funding_rate_threshold=funding_rate_threshold,
        oi_change_threshold=oi_change_threshold,
    )
