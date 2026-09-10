"""
runner.py

Executes the generated pytest suite and captures structured, per-test
results (rather than just an overall exit code) so they can be persisted
for historical trend analysis.

Latency/serving decision:
    Uses pytest's `--json-report` plugin output rather than screen-scraping
    stdout. This is both faster to parse reliably and avoids brittleness
    if pytest's human-readable output format changes between versions —
    important since this runs unattended in CI on every push.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    node_id: str
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    duration_seconds: float
    category: str | None = None
    error_message: str | None = None


@dataclass
class RunSummary:
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int
    duration_seconds: float
    results: list[TestResult]


def run_generated_tests(target_dir: Path, timeout_seconds: int = 120) -> RunSummary:
    """
    Run all generated tests under `target_dir` via `pytest --json-report`
    in a subprocess (isolation: a generated test that crashes the
    interpreter can't take down the framework process itself).
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        report_path = Path(tmp.name)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(target_dir),
        "--json-report",
        f"--json-report-file={report_path}",
        "-q",
    ]

    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            text=True,
            check=False,  # pytest exits non-zero on test failures; that's expected, not a crash
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("Test run exceeded %ds timeout", timeout_seconds)
        raise RuntimeError(f"Generated test suite timed out after {timeout_seconds}s") from exc

    if not report_path.exists() or report_path.stat().st_size == 0:
        raise RuntimeError("pytest did not produce a JSON report; is pytest-json-report installed?")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    report_path.unlink(missing_ok=True)

    results = []
    for test in report.get("tests", []):
        results.append(
            TestResult(
                node_id=test.get("nodeid", "unknown"),
                outcome=test.get("outcome", "unknown"),
                duration_seconds=test.get("duration", 0.0),
                category=next(
                    (k for k in test.get("keywords", {}) if k in
                     {"happy_path", "edge_case", "error_case", "boundary"}),
                    None,
                ),
                error_message=(test.get("call", {}) or {}).get("longrepr"),
            )
        )

    summary = report.get("summary", {})
    return RunSummary(
        total=summary.get("total", len(results)),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        errors=summary.get("error", 0),
        skipped=summary.get("skipped", 0),
        duration_seconds=report.get("duration", 0.0),
        results=results,
    )
