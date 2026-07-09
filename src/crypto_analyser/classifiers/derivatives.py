"""LLM classifier execution wrapper (Task 18).

Renders the Task 17 prompt template per episode using the Task 14 bulk
episodes file + Task 15 bulk derivatives context, calls
:class:`~crypto_analyser.llm_client.LLMClient.classify` with OpenAI-style
structured output, validates the response, and writes one classification JSON
per episode to ``data/classifications/{derivatives_only,derivatives_rag}/``.

Run B (``derivatives_rag``) additionally composes a retrieved-news block.
Until Task 16 ships per-episode RAG blobs at
``data/rag/{symbol}_{onset_ts}_rag.json`` it runs with an empty news block per
the Task 17 prompt contract (the LLM falls back to the Run A category set).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from crypto_analyser._paths import repo_root
from crypto_analyser.config import Config, load_config
from crypto_analyser.llm_client import ClassificationResult, LLMClient

REPO_ROOT = repo_root()
PROMPT_PATH = REPO_ROOT / "prompts" / "classification_prompt.md"
DEFAULT_ANOMALIES = REPO_ROOT / "data" / "anomalies" / "LUNAUSDT_2022-05-07_2022-05-11.json"
CLASSIFICATIONS_DIR = REPO_ROOT / "data" / "classifications"
RAG_DIR = REPO_ROOT / "data" / "rag"

# Run B defaults for the not-yet-shipped Task 16 RAG step.
_RAG_K_DEFAULT = 5
_RAG_WINDOW_DEFAULT = "±24h"
_RAG_BLOCK_EMPTY = "(No retrieved news available — RAG retrieval stage not yet run.)"

MODE_TO_SUBDIR = {
    "derivatives_only": "derivatives_only",
    "derivatives_rag": "derivatives_rag",
}


_FENCE_RE = re.compile(r"```[a-zA-Z]*\n(.*?)```", re.DOTALL)
# Match only slot-shaped tokens like {symbol} or {peak_z_abs}; leaves prose
# comma-lists such as {explained_derivatives, unexplained, insufficient_data}
# in the Task 17 template untouched.
_SLOT_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class ClassificationValidationError(RuntimeError):
    """Raised when LLM output fails the classification JSON schema."""


class PromptTemplate:
    """Loads the three fenced prompt blocks from the Task 17 prompt file."""

    def __init__(self, system: str, user_run_a: str, user_run_b: str) -> None:
        self.system = system
        self.user_run_a = user_run_a
        self.user_run_b = user_run_b

    @classmethod
    def load(cls, path: Path = PROMPT_PATH) -> "PromptTemplate":
        text = path.read_text(encoding="utf-8")
        blocks = _FENCE_RE.findall(text)
        if len(blocks) < 3:
            raise ValueError(f"{path}: expected >=3 fenced prompt blocks, found {len(blocks)}")
        return cls(blocks[0].strip(), blocks[1].strip(), blocks[2].strip())


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
    """Return ``{rag_context_block, k, window}`` for the Run B template.

    Task 16 will write per-episode RAG blobs at
    ``data/rag/{symbol}_{onset_ts}_rag.json`` with at least ``block``, ``k``,
    and ``window`` keys. Until it ships an empty block is returned per the
    Task 17 contract.
    """
    rag_path = RAG_DIR / f"{symbol}_{onset_ts}_rag.json"
    if rag_path.exists():
        rag = json.loads(rag_path.read_text(encoding="utf-8"))
        return {
            "rag_context_block": rag.get("block") or _RAG_BLOCK_EMPTY,
            "k": str(rag.get("k", _RAG_K_DEFAULT)),
            "window": rag.get("window", _RAG_WINDOW_DEFAULT),
        }
    return {
        "rag_context_block": _RAG_BLOCK_EMPTY,
        "k": str(_RAG_K_DEFAULT),
        "window": _RAG_WINDOW_DEFAULT,
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
    system = _render(template.system, _threshold_vars(cfg))
    user_vars = _episode_vars(episode, features, anomalies_meta, event_reference)
    if mode == "derivatives_rag":
        user_vars.update(_rag_block(anomalies_meta["symbol"], episode["onset_ts"]))
        user = _render(template.user_run_b, user_vars)
    else:
        user = _render(template.user_run_a, user_vars)
    return system, user, event_reference


def _out_path(symbol: str, onset_ts: int, mode: str) -> Path:
    sub = MODE_TO_SUBDIR[mode]
    target = CLASSIFICATIONS_DIR / sub
    target.mkdir(parents=True, exist_ok=True)
    return target / f"{symbol}_{onset_ts}.json"


def _write_classification(result: ClassificationResult, episode: dict, symbol: str, mode: str) -> Path:
    out = _out_path(symbol, episode["onset_ts"], mode)
    out.write_text(
        json.dumps(
            {
                "event_reference": result.event_reference,
                "classification": result.classification,
                # severity: derived from Task 14's peak |Z|, written verbatim
                # from the canonical episode record — NOT LLM-emitted (ADR-0002).
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
    """Classify each episode; ``mode`` selects Run A (derivatives_only) or Run B (derivatives_rag)."""
    out: list[Path] = []
    for ep in episodes:
        feats = _episode_features(context, ep["onset_ts"])
        out.append(_run_one(client, template, ep, feats, anomalies_meta, cfg, mode))
    return out


def _main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="LLM classifier execution wrapper")
    p.add_argument(
        "--anomalies",
        type=Path,
        default=DEFAULT_ANOMALIES,
        help="Bulk anomaly episodes file (default: LUNA pre-crash window)",
    )
    p.add_argument(
        "--context",
        type=Path,
        default=None,
        help="Bulk derivatives context file (default: <anomalies_stem>_context.json)",
    )
    p.add_argument(
        "--mode",
        choices=("derivatives_only", "derivatives_rag"),
        default="derivatives_only",
        help="Which Run variant to execute",
    )
    args = p.parse_args(argv)

    if not args.anomalies.exists():
        print(f"anomalies file not found: {args.anomalies}", file=sys.stderr)
        return 2
    anomalies = json.loads(args.anomalies.read_text(encoding="utf-8"))

    context_path = args.context or args.anomalies.parent.parent / "context" / f"{args.anomalies.stem}_context.json"
    if not context_path.exists():
        print(f"derivatives context file not found: {context_path}", file=sys.stderr)
        return 2
    context = json.loads(context_path.read_text(encoding="utf-8"))

    cfg = load_config()
    template = PromptTemplate.load()
    client = LLMClient()

    print(f"classifier: {len(anomalies['episodes'])} episodes, mode={args.mode}")
    paths = classify_episodes(
        anomalies["episodes"],
        context,
        anomalies["meta"],
        client,
        template,
        cfg,
        args.mode,
    )
    print(f"  wrote {len(paths)} classifications to data/classifications/{args.mode}/")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
