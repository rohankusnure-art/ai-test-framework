"""
db_interface.py

Abstract storage interface. Concrete implementations (sql_store.py for
SQLAlchemy/Postgres, or a future mongo_store.py) must satisfy this
contract so the rest of the framework never depends on a specific
database technology.

Data decision:
    We store TWO things separately: (1) the generated test-case spec
    itself (what was generated, from which function, on which commit),
    and (2) each execution's result against that spec. This is a
    deliberate 1-to-many design: the same generated test case is re-run
    on every push, and trend analysis ("did this specific edge case
    start failing after commit X?") requires keeping spec identity
    stable across many result rows rather than flattening everything
    into one wide table.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class TestCaseRecord:
    id: Optional[int]
    function_qualified_name: str
    module_path: str
    name: str
    category: str
    description: str
    spec_json: str  # raw JSON spec, for full reproducibility
    created_at: datetime


@dataclass
class TestRunRecord:
    id: Optional[int]
    test_case_id: int
    commit_sha: Optional[str]
    outcome: str
    duration_seconds: float
    error_message: Optional[str]
    run_at: datetime


class BaseStore(ABC):
    @abstractmethod
    def save_test_case(self, record: TestCaseRecord) -> int:
        """Persist a generated test-case spec; returns its assigned id."""

    @abstractmethod
    def save_test_run(self, record: TestRunRecord) -> int:
        """Persist a single execution result; returns its assigned id."""

    @abstractmethod
    def get_pass_rate_trend(self, function_qualified_name: str, limit: int = 30) -> list[dict[str, Any]]:
        """Return recent run outcomes for a given function, most recent first."""

    @abstractmethod
    def close(self) -> None:
        """Release any held connections/resources."""
