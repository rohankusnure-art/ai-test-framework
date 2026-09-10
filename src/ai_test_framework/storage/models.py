"""
models.py

SQLAlchemy ORM models. Works against SQLite (local/dev/CI default) and
Postgres (production — set DATABASE_URL) without code changes, since
both are ANSI-SQL enough for this schema.

Data decision (indexing):
    `function_qualified_name` is indexed on both tables because the
    primary read pattern is "show me the trend for function X" — without
    the index, trend queries would degrade to a full table scan as the
    history grows across CI runs.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class TestCase(Base):
    __tablename__ = "test_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    function_qualified_name = Column(String(512), nullable=False)
    module_path = Column(String(1024), nullable=False)
    name = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False)
    description = Column(Text, nullable=True)
    spec_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    runs = relationship("TestRun", back_populates="test_case", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_test_cases_function_qualified_name", "function_qualified_name"),
    )


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_case_id = Column(Integer, ForeignKey("test_cases.id"), nullable=False)
    commit_sha = Column(String(64), nullable=True)
    outcome = Column(String(32), nullable=False)  # passed | failed | error | skipped
    duration_seconds = Column(Float, nullable=False, default=0.0)
    error_message = Column(Text, nullable=True)
    run_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    test_case = relationship("TestCase", back_populates="runs")

    __table_args__ = (
        Index("ix_test_runs_test_case_id_run_at", "test_case_id", "run_at"),
    )
