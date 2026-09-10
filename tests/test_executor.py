"""Unit tests for ai_test_framework.executor.runner."""

import pytest

from ai_test_framework.executor.runner import run_generated_tests


@pytest.fixture()
def passing_and_failing_suite(tmp_path):
    (tmp_path / "test_mixed_generated.py").write_text(
        '''
import pytest

@pytest.mark.happy_path
def test_this_passes():
    assert 1 + 1 == 2

@pytest.mark.error_case
def test_this_fails():
    assert 1 + 1 == 3
'''
    )
    return tmp_path


def test_run_generated_tests_reports_correct_counts(passing_and_failing_suite):
    summary = run_generated_tests(passing_and_failing_suite)
    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1


def test_run_generated_tests_captures_individual_results(passing_and_failing_suite):
    summary = run_generated_tests(passing_and_failing_suite)
    outcomes = {r.node_id.split("::")[-1]: r.outcome for r in summary.results}
    assert outcomes["test_this_passes"] == "passed"
    assert outcomes["test_this_fails"] == "failed"


def test_run_generated_tests_raises_on_timeout(tmp_path, monkeypatch):
    (tmp_path / "test_slow.py").write_text(
        "import time\n\ndef test_slow():\n    time.sleep(5)\n"
    )
    with pytest.raises(RuntimeError, match="timed out"):
        run_generated_tests(tmp_path, timeout_seconds=1)
