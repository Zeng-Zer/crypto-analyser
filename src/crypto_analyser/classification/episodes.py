"""Classify anomaly episodes with structured LLM output.

``derivatives_rag`` consumes per-episode news retrieval files from
``data/rag/`` and fails when any are missing, preventing an empty-context run
from masquerading as a RAG experiment.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from crypto_analyser._paths import asset_path, repo_root
from crypto_analyser.config import Config, load_config
from crypto_analyser.llm_client import ClassificationResult, LLMClient

REPO_ROOT = repo_root()
PROMPT_PATH = asset_path("classification_prompt.md")

CLASSIFICATIONS_DIR = REPO_ROOT / "data" / "classifications"
RAG_DIR = REPO_ROOT / "data" / "rag"

_RAG_K_DEFAULT = 5
_RAG_WINDOW_DEFAULT = "24h before onset"


_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
# Match only slot-shaped tokens like {symbol} or {peak_z_abs}; leaves prose
# comma-lists such as {explained_derivatives, unexplained, insufficient_data}
# in the prompt template untouched.
_SLOT_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ClassificationValidationError(RuntimeError):
    """Raised when LLM output fails the classification JSON schema."""


class PromptTemplate:
    """Load system and user templates for all three evidence modes."""

    def __init__(self, system: str, user_run_a: str, user_run_b: str, system_run_c: str, user_run_c: str) -> None:
        self.system = system
        self.user_run_a = user_run_a
        self.user_run_b = user_run_b
        self.system_run_c = system_run_c
        self.user_run_c = user_run_c

    @classmethod
    def load(cls, path: Path = PROMPT_PATH) -> "PromptTemplate":
        text = path.read_text(encoding="utf-8")
        blocks = _FENCE_RE.findall(text)
        if len(blocks) < 5:
            raise ValueError(f"{path}: expected >=5 fenced prompt blocks, found {len(blocks)}")
        return cls(*(block.strip() for block in blocks[:5]))


def _render(template: str, variables: dict[str, Any]) -> str:
    """Substitute ``{slot_name}`` tokens only.

    Comma-list prose like ``{explained_derivatives, unexplained,
    insufficient_data}`` is left intact — regex matches slot-name-shaped
    tokens (letters, digits, underscore) only. Missing / None values render
    as ``null`` so the schema's ``insufficient_data`` category applies.
    """
    safe = {k: ("null" if v is None else str(v)) for k, v in variables.items()}

    def _repl(match: re.Match[str]) -> str:
        return safe.get(match.group(1), "null")

    return _SLOT_RE.sub(_repl, template)


def _episode_features(context: dict, onset_ts: int) -> dict | None:
    for feat in context["features"]:
        if feat["onset_ts"] == onset_ts:
            return feat
    return None


def _threshold_vars(cfg: Config) -> dict[str, Any]:
    th = cfg["anomaly_detection.derivatives_thresholds"]
    return {
        "funding_rate_mag_threshold": th["funding_rate_mag"],
        "oi_change_4h_threshold": th["oi_change_4h"],
    }


def _episode_vars(
    episode: dict,
    features: dict | None,
    anomalies_meta: dict,
    event_reference: str,
) -> dict[str, Any]:
    return {
        "symbol": anomalies_meta["symbol"],
        "start": anomalies_meta["start"],
        "end": anomalies_meta["end"],
        "onset_ts": episode["onset_ts"],
        "severity": episode["severity"],
        "peak_z_abs": abs(episode["peak_z"]),
        "event_reference": event_reference,
        "funding_rate_current": features.get("funding_rate_current") if features else None,
        "funding_rate_avg_4h": features.get("funding_rate_avg_4h") if features else None,
        "oi_current": features.get("oi_current") if features else None,
        "oi_change_4h": features.get("oi_change_4h") if features else None,
    }


def _rag_block(symbol: str, onset_ts: int) -> dict[str, str]:
    """Return ``{rag_context_block, k, window}`` for the Run B template."""
    rag_path = RAG_DIR / f"{symbol}_{onset_ts}_rag.json"
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
    anomalies_meta: dict,
    cfg: Config,
    mode: str,
) -> tuple[str, str, str]:
    """Return ``(system_prompt, user_prompt, event_reference)`` for one episode."""
    event_reference = f"{anomalies_meta['symbol']}_{episode['onset_ts']}"
    user_vars = _episode_vars(episode, features, anomalies_meta, event_reference)
    if mode == "news_only":
        system = template.system_run_c
        user_vars.update(_rag_block(anomalies_meta["symbol"], episode["onset_ts"]))
        user = _render(template.user_run_c, user_vars)
    else:
        system = _render(template.system, _threshold_vars(cfg))
        if mode == "derivatives_rag":
            user_vars.update(_rag_block(anomalies_meta["symbol"], episode["onset_ts"]))
            user = _render(template.user_run_b, user_vars)
        else:
            user = _render(template.user_run_a, user_vars)
    return system, user, event_reference


def _out_path(symbol: str, onset_ts: int, mode: str) -> Path:
    target = CLASSIFICATIONS_DIR / mode
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{symbol}_{onset_ts}.json"


def _write_classification(result: ClassificationResult, episode: dict, symbol: str, mode: str) -> Path:
    out = _out_path(symbol, episode["onset_ts"], mode)
    out.write_text(
        json.dumps(
            {
                "event_reference": result.event_reference,
                "classification": result.classification,
                # Derived from peak |Z| and copied from the canonical episode;
                # never emitted by the LLM (ADR-0002).
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
    return out


def _run_one(
    client: LLMClient,
    template: PromptTemplate,
    episode: dict,
    features: dict | None,
    anomalies_meta: dict,
    cfg: Config,
    mode: str,
) -> Path:
    system_prompt, user_prompt, event_reference = _build_prompts(template, episode, features, anomalies_meta, cfg, mode)
    try:
        result = client.classify(
            prompt=user_prompt,
            event_reference=event_reference,
            system_prompt=system_prompt,
        )
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ClassificationValidationError(
            f"LLM response failed schema validation for {event_reference}: {exc}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"LLM call failed for {event_reference}: {exc}") from exc
    return _write_classification(result, episode, anomalies_meta["symbol"], mode)


def classify_episodes(
    episodes: list[dict],
    context: dict,
    anomalies_meta: dict,
    client: LLMClient,
    template: PromptTemplate,
    cfg: Config,
    mode: str,
) -> list[Path]:
    """Classify each episode using derivatives-only, derivatives+RAG, or news-only evidence."""
    out: list[Path] = []
    for ep in episodes:
        feats = _episode_features(context, ep["onset_ts"])
        out.append(_run_one(client, template, ep, feats, anomalies_meta, cfg, mode))
    return out


def classify_batch(
    anomalies_path: Path,
    mode: str,
    *,
    context_path: Path | None = None,
    client: LLMClient | None = None,
) -> list[Path]:
    """Classify every episode in one anomaly batch."""
    anomalies = json.loads(anomalies_path.read_text(encoding="utf-8"))
    if mode == "news_only":
        context = {"features": []}
    else:
        context_path = context_path or anomalies_path.parent.parent / "context" / f"{anomalies_path.stem}_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
    return classify_episodes(
        anomalies["episodes"],
        context,
        anomalies["meta"],
        client or LLMClient(),
        PromptTemplate.load(),
        load_config(),
        mode,
    )
