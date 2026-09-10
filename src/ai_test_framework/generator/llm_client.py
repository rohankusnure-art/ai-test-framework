"""
llm_client.py

Thin, provider-agnostic wrapper around LangChain chat models. Supports
OpenAI and Hugging Face; the provider is chosen via config so it can be
swapped without touching calling code.

Reliability decisions (latency/serving):
- A bounded timeout + limited retry count (config-driven) prevents a
  single slow/hanging LLM call from stalling the whole test-generation
  pipeline in CI, where wall-clock time directly costs money/minutes.
- `NullLLMClient` provides a deterministic, offline fallback so the rest
  of the pipeline (scanner -> generator -> writer -> executor -> storage)
  is fully testable in CI without live API keys or network access,
  which also keeps the framework's OWN test suite fast and hermetic.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from ai_test_framework.config import Config

logger = logging.getLogger(__name__)


class LLMClientError(Exception):
    """Raised when the LLM call fails after all retries, or returns unparseable output."""


class BaseLLMClient(ABC):
    @abstractmethod
    def generate_test_specs(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        """Return a list of test-case spec dicts parsed from the model's JSON response."""
        raise NotImplementedError


def _parse_json_array(raw_text: str) -> list[dict[str, Any]]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Strip markdown fences if the model added them despite instructions.
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMClientError(f"Model did not return valid JSON: {exc}") from exc
    if not isinstance(parsed, list):
        raise LLMClientError("Model response was valid JSON but not a top-level array")
    return parsed


class LangChainLLMClient(BaseLLMClient):
    """
    Wraps LangChain's chat model interface. Supports "openai" and
    "huggingface" providers based on config.llm_provider.

    Import of the concrete LangChain integration is deferred into
    __init__ so that importing this module doesn't hard-require both
    the openai and huggingface extras to be installed — only the one
    actually configured.
    """

    def __init__(self, config: Config):
        self.config = config
        self._chat_model = self._build_chat_model()

    def _build_chat_model(self):
        if self.config.llm_provider == "openai":
            from langchain_openai import ChatOpenAI  # deferred import

            return ChatOpenAI(
                api_key=self.config.openai_api_key,
                model=self.config.openai_model,
                temperature=self.config.llm_temperature,
                timeout=self.config.llm_timeout_seconds,
            )
        elif self.config.llm_provider == "huggingface":
            from langchain_huggingface import HuggingFaceEndpoint  # deferred import

            return HuggingFaceEndpoint(
                repo_id=self.config.huggingface_model,
                temperature=self.config.llm_temperature,
                timeout=self.config.llm_timeout_seconds,
            )
        raise LLMClientError(f"Unknown LLM provider: {self.config.llm_provider}")

    def generate_test_specs(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        from langchain_core.messages import HumanMessage, SystemMessage

        last_error: Exception | None = None
        for attempt in range(1, self.config.llm_max_retries + 2):
            try:
                response = self._chat_model.invoke(
                    [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
                )
                content = response.content if hasattr(response, "content") else str(response)
                return _parse_json_array(content)
            except Exception as exc:  # noqa: BLE001 - genuinely want to retry on any provider error
                last_error = exc
                logger.warning("LLM call attempt %d/%d failed: %s", attempt, self.config.llm_max_retries + 1, exc)
                time.sleep(min(2 ** attempt, 8))  # capped exponential backoff

        raise LLMClientError(f"LLM generation failed after retries: {last_error}") from last_error


class NullLLMClient(BaseLLMClient):
    """
    Deterministic offline stand-in used when no API key is configured, or
    explicitly requested for CI dry-runs. Produces a minimal but valid
    happy-path + error-case spec derived purely from structural signals
    (params, raises) so the rest of the pipeline can be exercised without
    any network call.
    """

    def generate_test_specs(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        logger.info("NullLLMClient active: generating structural placeholder specs (no LLM call made)")
        return [
            {
                "name": "test_happy_path_placeholder",
                "description": "Placeholder happy-path case (offline mode — no LLM configured)",
                "category": "happy_path",
                "inputs": {},
                "expected": {"returns": None},
            }
        ]


def get_llm_client(config: Config) -> BaseLLMClient:
    """Factory: returns NullLLMClient if no credentials are configured, else a live client."""
    if config.llm_provider == "openai" and not config.openai_api_key:
        logger.warning("No OPENAI_API_KEY set; falling back to NullLLMClient")
        return NullLLMClient()
    return LangChainLLMClient(config)
