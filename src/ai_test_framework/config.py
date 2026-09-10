"""
config.py

Centralized configuration loaded from environment variables. Nothing
sensitive is hardcoded; see .env.example for the full list of variables
a deployment needs to set.

Data/architecture decision:
    Configuration is a single frozen dataclass built once at process
    start (`get_config()` is cached) rather than scattered `os.environ`
    calls throughout the codebase. This keeps behavior predictable under
    concurrent test execution and makes it trivial to override config in
    unit tests via `Config(**overrides)`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Config:
    # LLM provider settings
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")  # "openai" | "huggingface"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    huggingface_model: str = os.getenv("HUGGINGFACE_MODEL", "bigcode/starcoder2-7b")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    llm_max_retries: int = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Storage settings
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./ai_test_framework.db")
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "5"))
    db_pool_timeout_seconds: int = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "10"))

    # Generation/execution settings
    generated_tests_dir: str = os.getenv("GENERATED_TESTS_DIR", "generated_tests")
    max_edge_cases_per_function: int = int(os.getenv("MAX_EDGE_CASES_PER_FUNCTION", "6"))
    test_execution_timeout_seconds: int = int(os.getenv("TEST_EXECUTION_TIMEOUT_SECONDS", "120"))


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Return the process-wide Config singleton (cached after first call)."""
    return Config()
