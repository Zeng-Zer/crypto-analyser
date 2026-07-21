"""OpenAI-compatible LLM client with structured output support.

Calls with ``stream=True`` and ``chat_template_kwargs={"enable_thinking": False}``
because the proxy-served reasoning model fails the non-streaming path and times
out when allowed to emit chain-of-thought before the structured JSON — see
ADR-0004. Streaming here is not for token-by-token rendering; the SSE chunks are
accumulated into one string and ``json.loads``-ed exactly like a batch response."""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass
from typing import Any, Self

import requests

from crypto_analyser._paths import asset_path
from crypto_analyser.constants import LLM_MODEL

PLACEHOLDER_PATTERNS: tuple[str, ...] = ("changeme_", "your_", "placeholder")


class PlaceholderValueError(ValueError):
    """Raised when an API key or URL is still a placeholder value."""


@dataclass(frozen=True, slots=True)
class ClassificationSynthesis:
    """Concise reader-facing verdict reasons and supporting context refs."""

    reasons: tuple[str, ...]
    supporting_refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        if not isinstance(data["reasons"], list) or not isinstance(data["supporting_refs"], list):
            raise ValueError("synthesis reasons and supporting_refs must be arrays")
        reasons = tuple(data["reasons"])
        supporting_refs = tuple(data["supporting_refs"])
        if not 1 <= len(reasons) <= 3:
            raise ValueError("synthesis.reasons must contain 1-3 items")
        if any(not isinstance(reason, str) or not reason or len(reason) > 160 for reason in reasons):
            raise ValueError("each synthesis reason must be a non-empty string of at most 160 characters")
        if len(supporting_refs) > 7:
            raise ValueError("synthesis.supporting_refs must contain at most 7 items")
        if any(not isinstance(ref, str) or not ref for ref in supporting_refs):
            raise ValueError("synthesis.supporting_refs must contain non-empty strings")
        if len(set(supporting_refs)) != len(supporting_refs):
            raise ValueError("synthesis.supporting_refs must be unique")
        return cls(reasons, supporting_refs)


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    """Typed wrapper for LLM classification output.

    Note: `severity` is intentionally absent because detection derives it.
    Classification copies it directly from the episode record (ADR-0002).
    """

    event_reference: str
    classification: str
    confidence: float
    synthesis: ClassificationSynthesis
    rationale: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            event_reference=data["event_reference"],
            classification=data["classification"],
            confidence=float(data["confidence"]),
            synthesis=ClassificationSynthesis.from_dict(data["synthesis"]),
            rationale=data["rationale"],
        )


def _check_placeholder(name: str, value: str) -> None:
    """Raise if *value* still contains a placeholder token."""
    if not isinstance(value, str):
        return
    if any(pattern in value.lower() for pattern in PLACEHOLDER_PATTERNS):
        raise PlaceholderValueError(f"{name} contains a placeholder value: {value!r}. Fill it in .env.")


def _resolve_api_url() -> str:
    val = os.getenv("LLM_API_URL")
    if not val:
        raise RuntimeError("LLM_API_URL not set. Put it in .env (see .env.example).")
    return val


def _resolve_api_key() -> str:
    val = os.getenv("LLM_API_KEY")
    if not val:
        raise RuntimeError("LLM_API_KEY not set. Put it in .env (see .env.example).")
    return val


class LLMClient:
    """OpenAI-compatible chat completions client with JSON-schema structured outputs.

    Reads ``LLM_API_URL`` and ``LLM_API_KEY`` from the environment.
    Request limits and model use constructor defaults.
    """

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2000,
    ) -> None:
        api_url = api_url or _resolve_api_url()
        api_key = api_key or _resolve_api_key()
        model = model or LLM_MODEL

        _check_placeholder("LLM_API_URL", api_url)
        _check_placeholder("LLM_API_KEY", api_key)

        self._api_url = api_url.rstrip("/")
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

        # Retry adapter for transient failures
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self._session.mount("http://", HTTPAdapter(max_retries=retries))

    @staticmethod
    @functools.lru_cache(maxsize=1)
    def _load_schema() -> dict[str, Any]:
        schema_path = asset_path("classification.json")
        if not schema_path.exists():
            raise FileNotFoundError(f"Classification schema not found: {schema_path}")
        with open(schema_path, encoding="utf-8") as f:
            return json.load(f)

    def classify(
        self,
        prompt: str,
        event_reference: str = "",
        system_prompt: str | None = None,
    ) -> ClassificationResult:
        """Send a classification prompt to the LLM and return a typed result.

        Uses ``response_format={"type": "json_schema", "strict": true}`` for
        deterministic structured output. If *system_prompt* is None, a default
        crypto-analyst system message is used.
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
                    "content": system_prompt
                    or (
                        "You are a crypto market analyst. "
                        "Classify the price anomaly based on derivatives market structure."
                    ),
                },
                {"role": "user", "content": enriched_prompt},
            ],
            "response_format": response_format,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            # stream=true is required by some proxy-served models (e.g. glm-5.2-short-flex)
            # that fail with HTTP 500 / read-timeouts on the non-streaming path.
            "stream": True,
            # Disable reasoning-mode tokens so the model emits structured JSON directly
            # instead of spending budget on chain-of-thought before the answer.
            "chat_template_kwargs": {"enable_thinking": False},
        }

        resp = self._session.post(
            f"{self._api_url}/chat/completions",
            json=payload,
            timeout=120,
            stream=True,
        )
        resp.raise_for_status()

        # OpenAI-compatible SSE: each `data: {...}` chunk carries a `delta.content`
        # fragment; the stream terminates with `data: [DONE]`. We reassemble into
        # the same JSON string the non-streaming endpoint would have returned.
        chunks: list[str] = []
        for line in resp.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if not decoded.startswith("data: "):
                continue
            body = decoded[6:]
            if body == "[DONE]":
                break
            chunk_json = json.loads(body)
            if chunk_json.get("choices"):
                delta = chunk_json["choices"][0].get("delta") or {}
                if piece := delta.get("content"):
                    chunks.append(piece)
        content = "".join(chunks)
        parsed = json.loads(content)

        # Ensure event_reference is set even if the LLM missed it
        if not parsed.get("event_reference"):
            parsed["event_reference"] = event_reference or "unknown"

        return ClassificationResult.from_dict(parsed)
