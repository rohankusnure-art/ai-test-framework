"""
repo_scanner.py

Walks a target Python repository and extracts a structured inventory of
functions/methods, their signatures, type hints, and docstrings, using
the `ast` module rather than importing the target code.

Architecture decision:
    Static analysis (ast.parse) is used instead of `importlib` + runtime
    introspection. Importing arbitrary target code to introspect it would
    mean executing untrusted code as a side effect of "just scanning" —
    a real security and reliability problem for a tool meant to run
    against someone else's repo in CI. AST parsing is slower per-file to
    write but strictly safer and has no import-order/dependency issues.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ParamInfo:
    name: str
    annotation: str | None = None
    default: str | None = None


@dataclass
class FunctionInfo:
    name: str
    qualified_name: str  # e.g. "order_service.place_order" or "OrderService.cancel"
    module_path: str
    params: list[ParamInfo] = field(default_factory=list)
    return_annotation: str | None = None
    docstring: str | None = None
    is_method: bool = False
    class_name: str | None = None
    raises: list[str] = field(default_factory=list)  # best-effort, parsed from docstring/body
    lineno: int = 0


def _unparse(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - defensive, ast.unparse rarely fails
        return None


def _extract_raises(func_node: ast.FunctionDef) -> list[str]:
    """Best-effort scan of `raise SomeError(...)` statements in the function body."""
    raised: set[str] = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Raise) and node.exc is not None:
            target = node.exc
            if isinstance(target, ast.Call):
                target = target.func
            name = _unparse(target)
            if name:
                raised.add(name)
    return sorted(raised)


def _extract_function(node: ast.FunctionDef, module_path: str, class_name: str | None) -> FunctionInfo:
    params = []
    args = node.args
    defaults = [None] * (len(args.args) - len(args.defaults)) + [
        _unparse(d) for d in args.defaults
    ]
    for arg, default in zip(args.args, defaults):
        params.append(
            ParamInfo(name=arg.arg, annotation=_unparse(arg.annotation), default=default)
        )

    qualified = f"{class_name}.{node.name}" if class_name else node.name
    return FunctionInfo(
        name=node.name,
        qualified_name=qualified,
        module_path=module_path,
        params=params,
        return_annotation=_unparse(node.returns),
        docstring=ast.get_docstring(node),
        is_method=class_name is not None,
        class_name=class_name,
        raises=_extract_raises(node),
        lineno=node.lineno,
    )


def scan_file(file_path: Path) -> list[FunctionInfo]:
    """Parse a single .py file and return FunctionInfo for every top-level and class method."""
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as exc:
        logger.warning("Skipping %s: syntax error (%s)", file_path, exc)
        return []

    module_path = str(file_path)
    functions: list[FunctionInfo] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue  # skip private helpers by default
            functions.append(_extract_function(node, module_path, class_name=None))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if item.name.startswith("_") and item.name != "__init__":
                        continue
                    functions.append(_extract_function(item, module_path, class_name=node.name))

    return functions


def scan_repo(root: Path, include_patterns: tuple[str, ...] = ("*.py",)) -> list[FunctionInfo]:
    """
    Recursively scan `root` for Python files and return FunctionInfo for
    every discovered function/method. Skips common non-source directories.
    """
    skip_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", "generated_tests", "tests"}
    all_functions: list[FunctionInfo] = []

    for pattern in include_patterns:
        for path in root.rglob(pattern):
            if any(part in skip_dirs for part in path.parts):
                continue
            all_functions.extend(scan_file(path))

    logger.info("Scanned %s: found %d functions/methods", root, len(all_functions))
    return all_functions
