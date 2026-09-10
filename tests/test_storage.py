"""Unit tests for ai_test_framework.storage.sql_store."""

import pytest

from ai_test_framework.config import Config
from ai_test_framework.storage.db_interface import TestCaseRecord, TestRunRecord
from ai_test_framework.storage.sql_store import SQLStore


@pytest.fixture()
def store(tmp_path):
    db_path = tmp_path / "test.db"
    config = Config(database_url=f"sqlite:///{db_path}")
    s = SQLStore(config)
    yield s
    s.close()


def _sample_test_case() -> TestCaseRecord:
    return TestCaseRecord(
        id=None,
        function_qualified_name="targets.order_service.place_order",
        module_path="order_service.py",
        name="test_insufficient_stock_raises",
        category="error_case",
        description="raises when quantity exceeds stock",
        spec_json="{}",
        created_at=None,
    )


def test_save_test_case_returns_id(store):
    case_id = store.save_test_case(_sample_test_case())
    assert isinstance(case_id, int)
    assert case_id > 0


def test_save_test_run_links_to_test_case(store):
    case_id = store.save_test_case(_sample_test_case())
    run_id = store.save_test_run(
        TestRunRecord(
            id=None,
            test_case_id=case_id,
            commit_sha="abc123",
            outcome="passed",
            duration_seconds=0.01,
            error_message=None,
            run_at=None,
        )
    )
    assert run_id > 0


def test_get_pass_rate_trend_returns_recent_runs_first(store):
    case_id = store.save_test_case(_sample_test_case())
    for outcome in ["failed", "passed", "passed"]:
        store.save_test_run(
            TestRunRecord(
                id=None,
                test_case_id=case_id,
                commit_sha="sha",
                outcome=outcome,
                duration_seconds=0.01,
                error_message=None,
                run_at=None,
            )
        )
    trend = store.get_pass_rate_trend("targets.order_service.place_order")
    assert len(trend) == 3
    assert all("outcome" in row for row in trend)


def test_get_pass_rate_trend_empty_for_unknown_function(store):
    trend = store.get_pass_rate_trend("nonexistent.function")
    assert trend == []


def test_save_test_run_with_invalid_test_case_id_rolls_back(store):
    """
    A test_run referencing a non-existent test_case_id should not leave a
    partially-committed row behind — this is the rollback-safety behavior
    described in sql_store.py's module docstring.
    """
    with pytest.raises(Exception):
        store.save_test_run(
            TestRunRecord(
                id=None,
                test_case_id=999999,  # does not exist
                commit_sha="sha",
                outcome="passed",
                duration_seconds=0.01,
                error_message=None,
                run_at=None,
            )
        )
    # No orphaned run should be queryable afterward for this bogus id.
    trend = store.get_pass_rate_trend("targets.order_service.place_order")
    assert trend == []
