"""OpenAI-compatible LLM client with structured output support."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import requests


PLACEHOLDER_PATTERNS: tuple[str, ...] = ("changeme_", "your_", "placeholder")


class PlaceholderValueError(ValueError):
    """Raised when an API key or URL is still a placeholder value."""


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Typed wrapper for LLM classification output."""

    classification: str
    severity: int
    confidence: float
    rationale: str
    news_relevance: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            classification=data["classification"],
            severity=int(data["severity"]),
            confidence=float(data["confidence"]),
            rationale=data["rationale"],
            news_relevance=data.get("news_relevance"),
        )


def _check_placeholder(name: str, value: str) -> None:
    """Raise if *value* still contains a placeholder token."""
    if any(pattern in value.lower() for pattern in PLACEHOLDER_PATTERNS):
        raise PlaceholderValueError(
            f"{name} contains a placeholder value: {value!r}. "
            f"Please fill it in config/settings.yaml."
        )


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
    ) -> None:
        api_url = api_url or self._resolve_api_url()
        api_key = api_key or self._resolve_api_key()
        model = model or self._resolve_model()

        _check_placeholder("API_URL", api_url)
        _check_placeholder("API_KEY", api_key)

        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
        )

    def _resolve_api_url(self) -> str:
        try:
            from crypto_analyser.config import load_config

            return load_config().api_keys["llm_api_url"]
        except Exception:
            return "https://api.openai.com/v1"

    def _resolve_api_key(self) -> str:
        try:
            from crypto_analyser.config import load_config

            return load_config().api_keys["llm_api_key"]
        except Exception:
            return "changeme_"

    def _resolve_model(self) -> str:
        try:
            from crypto_analyser.config import load_config

            return load_config().llm["model"]
        except Exception:
            return "gpt-4o"

    def _load_schema(self) -> dict[str, Any]:
        schema_path = (
            Path(__file__).resolve().parent.parent.parent / "schemas" / "classification.json"
        )
        if not schema_path.exists():
            raise FileNotFoundError(f"Classification schema not found: {schema_path}")
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)

    def classify(self, prompt: str) -> ClassificationResult:
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
                {"role": "user", "content": prompt},
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

        return resp.json()["choices"][0]["message"]["content"]
