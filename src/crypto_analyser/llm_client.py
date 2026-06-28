"""OpenAI-compatible LLM client with structured output support."""
from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import requests

from crypto_analyser.config import Config, load_config

PLACEHOLDER_PATTERNS: tuple[str, ...] = ("changeme_", "your_", "placeholder")


class PlaceholderValueError(ValueError):
    """Raised when an API key or URL is still a placeholder value."""


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Typed wrapper for LLM classification output."""

    event_reference: str
    classification: str
    severity: str
    confidence: float
    rationale: str
    news_relevance: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            event_reference=data["event_reference"],
            classification=data["classification"],
            severity=str(data["severity"]),
            confidence=float(data["confidence"]),
            rationale=data["rationale"],
            news_relevance=data.get("news_relevance"),
        )


def _check_placeholder(name: str, value: str) -> None:
    """Raise if *value* still contains a placeholder token."""
    if not isinstance(value, str):
        return
    if any(pattern in value.lower() for pattern in PLACEHOLDER_PATTERNS):
        raise PlaceholderValueError(
            f"{name} contains a placeholder value: {value!r}. "
            f"Please fill it in config/settings.yaml."
        )


def _resolve_api_url(cfg: Config) -> str:
    try:
        return cfg.api_keys["llm_api_url"]
    except KeyError as exc:
        raise RuntimeError(
            f"Config missing 'api_keys.llm_api_url': {exc}"
        ) from exc


def _resolve_api_key(cfg: Config) -> str:
    try:
        return cfg.api_keys["llm_api_key"]
    except KeyError as exc:
        raise RuntimeError(
            f"Config missing 'api_keys.llm_api_key': {exc}"
        ) from exc


def _resolve_model(cfg: Config) -> str:
    try:
        return cfg.llm["model"]
    except KeyError as exc:
        raise RuntimeError(
            f"Config missing 'llm.model': {exc}"
        ) from exc


class LLMClient:
    """OpenAI-compatible chat completions client with JSON-schema structured outputs.

    Loads API URL and key from ``config/settings.yaml`` via
    :func:`crypto_analyser.config.load_config`.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
        trace_enabled: bool = False,
    ) -> None:
        cfg = load_config()

        api_url = api_url or _resolve_api_url(cfg)
        api_key = api_key or _resolve_api_key(cfg)
        model = model or _resolve_model(cfg)

        _check_placeholder("API_URL", api_url)
        _check_placeholder("API_KEY", api_key)

        self._api_url = api_url.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._trace_enabled = trace_enabled
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

        # Retry adapter for transient failures
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retries = Retry(
            total=3, backoff_factor=1, status_forcelist=[502, 503, 504]
        )
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._session.mount("http://", HTTPAdapter(max_retries=retries))

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _load_schema() -> dict[str, Any]:
        schema_path = (
            Path(__file__).resolve().parent.parent.parent / "schemas" / "classification.json"
        )
        if not schema_path.exists():
            raise FileNotFoundError(f"Classification schema not found: {schema_path}")
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)

    def classify(
        self,
        prompt: str,
        event_reference: str = "",
    ) -> ClassificationResult:
        """Send a classification prompt to the LLM and return a typed result.

        Uses ``response_format={"type": "json_schema", "strict": true}`` for
        deterministic structured output.
        """
        schema = self._load_schema()

        # Build OpenAI-compatible JSON Schema request
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema["title"],
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        k: {sk: sv for sk, sv in v.items() if sk != "description"}
                        for k, v in schema["properties"].items()
                    },
                    "required": schema["required"],
                    "additionalProperties": schema.get("additionalProperties", False),
                },
            },
        }

        # Inject event_reference into the user prompt so the LLM populates it
        enriched_prompt = prompt
        if event_reference:
            enriched_prompt += f"\n\n[event_reference: {event_reference}]"

        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a crypto market analyst. "
                        "Classify the price anomaly based on derivatives market structure."
                    ),
                },
                {"role": "user", "content": enriched_prompt},
            ],
            "response_format": response_format,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        resp = self._session.post(
            f"{self._api_url}/chat/completions",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)

        # Ensure event_reference is set even if the LLM missed it
        if not parsed.get("event_reference"):
            parsed["event_reference"] = event_reference or "unknown"

        return ClassificationResult.from_dict(parsed)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Raw chat completion without structured output.

        Useful for ad-hoc queries or Ragas evaluation.
        """
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self._temperature),
            "max_tokens": kwargs.get("max_tokens", self._max_tokens),
        }

        resp = self._session.post(
            f"{self._api_url}/chat/completions",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]

        if self._trace_enabled:
            self._trace_chat(payload, content)

        return content

    def _trace_chat(self, payload: dict[str, Any], response: str) -> None:
        """Best-effort Langfuse trace for observability."""
        try:
            from langfuse import Langfuse

            lf = Langfuse()
            trace = lf.trace(name="llm_chat")
            trace.generation(
                name="chat_completion",
                model=self._model,
                input=payload["messages"],
                output=response,
            )
        except Exception:
            # Tracing is best-effort; never fail the main operation
            pass
