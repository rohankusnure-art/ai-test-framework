"""Unit tests for ai_test_framework.scanner.repo_scanner."""

from pathlib import Path

import pytest

from ai_test_framework.scanner.repo_scanner import scan_file, scan_repo


@pytest.fixture()
def sample_module(tmp_path: Path) -> Path:
    module = tmp_path / "sample.py"
    module.write_text(
        '''
def add(a: int, b: int = 0) -> int:
    """Add two numbers."""
    if a < 0:
        raise ValueError("a must be non-negative")
    return a + b


class Calculator:
    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

    def _internal_helper(self):
        return None
'''
    )
    return module


def test_scan_file_finds_top_level_function(sample_module: Path):
    functions = scan_file(sample_module)
    names = [f.name for f in functions]
    assert "add" in names


def test_scan_file_extracts_docstring_and_params(sample_module: Path):
    functions = scan_file(sample_module)
    add_func = next(f for f in functions if f.name == "add")
    assert add_func.docstring == "Add two numbers."
    assert [p.name for p in add_func.params] == ["a", "b"]
    assert add_func.params[1].default == "0"


def test_scan_file_detects_raised_exceptions(sample_module: Path):
    functions = scan_file(sample_module)
    add_func = next(f for f in functions if f.name == "add")
    assert "ValueError" in add_func.raises


def test_scan_file_extracts_class_methods(sample_module: Path):
    functions = scan_file(sample_module)
    method_names = [f.qualified_name for f in functions if f.is_method]
    assert "Calculator.multiply" in method_names


def test_scan_file_skips_private_helpers(sample_module: Path):
    functions = scan_file(sample_module)
    names = [f.name for f in functions]
    assert "_internal_helper" not in names


def test_scan_file_handles_syntax_error_gracefully(tmp_path: Path):
    bad_file = tmp_path / "broken.py"
    bad_file.write_text("def broken(:\n    pass")
    assert scan_file(bad_file) == []


def test_scan_repo_skips_common_noise_directories(tmp_path: Path):
    (tmp_path / "venv").mkdir()
    (tmp_path / "venv" / "ignored.py").write_text("def ignored(): pass")
    (tmp_path / "real.py").write_text("def real(): pass")

    functions = scan_repo(tmp_path)
    names = [f.name for f in functions]
    assert "real" in names
    assert "ignored" not in names
