"""
sql_store.py

SQLAlchemy-backed implementation of BaseStore. Works with SQLite (default,
zero-setup) or Postgres (set DATABASE_URL, e.g.
"postgresql+psycopg2://user:pass@host:5432/dbname").

Reliability decision (rollback / transactional integrity):
    Every write goes through `_session_scope()`, a context manager that
    commits on success and explicitly rolls back on any exception before
    re-raising. Without this, a failure mid-write (e.g. a dropped DB
    connection while saving a batch of test-run results) could leave a
    test_case row committed with no corresponding test_run rows, silently
    corrupting the trend-analysis data the whole feature depends on.

Serving/latency decision:
    `pool_size` and `pool_timeout` are configurable (see config.py) so a
    production Postgres deployment under concurrent CI runners doesn't
    starve for connections; SQLite ignores these (single-file, no pool).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import create_engine, desc, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """
    SQLite does not enforce FOREIGN KEY constraints unless explicitly told
    to per-connection. Without this, an invalid test_case_id on a TestRun
    would silently succeed instead of raising — defeating the rollback
    guarantee this module is built around. No-ops for non-SQLite drivers.
    """
    if type(dbapi_connection).__module__.startswith("sqlite3"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

from ai_test_framework.config import Config
from ai_test_framework.storage.db_interface import BaseStore, TestCaseRecord, TestRunRecord
from ai_test_framework.storage.models import Base, TestCase, TestRun

logger = logging.getLogger(__name__)


class SQLStore(BaseStore):
    def __init__(self, config: Config):
        engine_kwargs: dict[str, Any] = {}
        if not config.database_url.startswith("sqlite"):
            engine_kwargs["pool_size"] = config.db_pool_size
            engine_kwargs["pool_timeout"] = config.db_pool_timeout_seconds

        self._engine = create_engine(config.database_url, **engine_kwargs)
        Base.metadata.create_all(self._engine)
        self._SessionLocal = sessionmaker(bind=self._engine, expire_on_commit=False)

    @contextmanager
    def _session_scope(self) -> Iterator[Session]:
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()  # explicit rollback on any failure — see module docstring
            logger.exception("Transaction rolled back due to error")
            raise
        finally:
            session.close()

    def save_test_case(self, record: TestCaseRecord) -> int:
        with self._session_scope() as session:
            row = TestCase(
                function_qualified_name=record.function_qualified_name,
                module_path=record.module_path,
                name=record.name,
                category=record.category,
                description=record.description,
                spec_json=record.spec_json,
            )
            session.add(row)
            session.flush()  # populate row.id before commit
            return row.id

    def save_test_run(self, record: TestRunRecord) -> int:
        with self._session_scope() as session:
            row = TestRun(
                test_case_id=record.test_case_id,
                commit_sha=record.commit_sha,
                outcome=record.outcome,
                duration_seconds=record.duration_seconds,
                error_message=record.error_message,
            )
            session.add(row)
            session.flush()
            return row.id

    def get_pass_rate_trend(self, function_qualified_name: str, limit: int = 30) -> list[dict[str, Any]]:
        with self._session_scope() as session:
            rows = (
                session.query(TestRun, TestCase)
                .join(TestCase, TestRun.test_case_id == TestCase.id)
                .filter(TestCase.function_qualified_name == function_qualified_name)
                .order_by(desc(TestRun.run_at))
                .limit(limit)
                .all()
            )
            return [
                {
                    "run_at": run.run_at.isoformat(),
                    "outcome": run.outcome,
                    "test_case_name": case.name,
                    "category": case.category,
                    "commit_sha": run.commit_sha,
                }
                for run, case in rows
            ]

    def close(self) -> None:
        self._engine.dispose()
