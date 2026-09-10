"""
cli.py

Command-line entry point. Wires together:
    scan -> generate -> write -> execute -> persist

Usage:
    ai-test-gen generate --target ./targets/sample_ecommerce_app --import-path targets.sample_ecommerce_app.order_service
    ai-test-gen run --tests-dir ./generated_tests
    ai-test-gen trend --function targets.sample_ecommerce_app.order_service.place_order
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from ai_test_framework.config import get_config
from ai_test_framework.executor.runner import run_generated_tests
from ai_test_framework.generator.llm_client import get_llm_client
from ai_test_framework.generator.prompt_templates import SYSTEM_PROMPT, build_user_prompt
from ai_test_framework.generator.test_writer import write_test_file
from ai_test_framework.scanner.repo_scanner import scan_repo
from ai_test_framework.storage.db_interface import TestCaseRecord
from ai_test_framework.storage.sql_store import SQLStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@click.group()
def cli() -> None:
    """AI-Powered Test Case Generation & Automation Framework."""


@cli.command()
@click.option("--target", required=True, type=click.Path(exists=True, path_type=Path), help="Directory to scan.")
@click.option("--import-path", required=True, help="Dotted import path generated tests should use, e.g. targets.sample_ecommerce_app.order_service")
@click.option("--output-dir", default="generated_tests", type=click.Path(path_type=Path), help="Where to write generated test files.")
def generate(target: Path, import_path: str, output_dir: Path) -> None:
    """Scan TARGET, generate test cases via the configured LLM, and write pytest files."""
    config = get_config()
    llm_client = get_llm_client(config)
    store = SQLStore(config)

    functions = scan_repo(target)
    if not functions:
        click.echo("No functions found to generate tests for.", err=True)
        sys.exit(1)

    total_written = 0
    for func in functions:
        user_prompt = build_user_prompt(func, max_cases=config.max_edge_cases_per_function)
        try:
            specs = llm_client.generate_test_specs(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:  # noqa: BLE001
            logger.error("Skipping %s: generation failed (%s)", func.qualified_name, exc)
            continue

        if not specs:
            continue

        write_test_file(func, specs, output_dir, import_path)
        for spec in specs:
            store.save_test_case(
                TestCaseRecord(
                    id=None,
                    function_qualified_name=f"{import_path}.{func.name}",
                    module_path=func.module_path,
                    name=spec.get("name", "unnamed"),
                    category=spec.get("category", "edge_case"),
                    description=spec.get("description", ""),
                    spec_json=json.dumps(spec),
                    created_at=None,  # set by DB default
                )
            )
        total_written += len(specs)

    store.close()
    click.echo(f"Generated {total_written} test case(s) across {len(functions)} function(s) -> {output_dir}/")


@cli.command()
@click.option("--tests-dir", default="generated_tests", type=click.Path(exists=True, path_type=Path))
def run(tests_dir: Path) -> None:
    """Execute the generated test suite and print a summary."""
    config = get_config()
    summary = run_generated_tests(tests_dir, timeout_seconds=config.test_execution_timeout_seconds)
    click.echo(
        f"Total: {summary.total}  Passed: {summary.passed}  Failed: {summary.failed}  "
        f"Errors: {summary.errors}  Skipped: {summary.skipped}  ({summary.duration_seconds:.2f}s)"
    )
    if summary.failed or summary.errors:
        sys.exit(1)


@cli.command()
@click.option("--function", required=True, help="Fully qualified function name, e.g. targets.sample_ecommerce_app.order_service.place_order")
@click.option("--limit", default=30, type=int)
def trend(function: str, limit: int) -> None:
    """Show recent pass/fail history for a given function's generated tests."""
    config = get_config()
    store = SQLStore(config)
    rows = store.get_pass_rate_trend(function, limit=limit)
    store.close()
    for row in rows:
        click.echo(f"{row['run_at']}  {row['outcome']:8s}  {row['category']:12s}  {row['test_case_name']}")
    if not rows:
        click.echo("No run history found for this function yet.")


if __name__ == "__main__":
    cli()
