"""
prompt_templates.py

Prompt construction for the LLM test-generation step. Kept separate from
llm_client.py so prompts can be iterated on/versioned independently of
the API wiring, and so they're unit-testable as pure string functions.
"""

from __future__ import annotations

from ai_test_framework.scanner.repo_scanner import FunctionInfo

SYSTEM_PROMPT = """You are a senior QA automation engineer generating pytest test cases.
Given a function's signature, type hints, docstring, and any exceptions it raises, produce a
JSON array of test case specifications. Each test case must have:
- "name": a descriptive snake_case test function name (must start with "test_")
- "description": one sentence describing what is being verified
- "category": one of "happy_path", "edge_case", "error_case", "boundary"
- "inputs": a dict of argument name -> literal Python value (as a string) to pass
- "expected": either {"returns": <literal>} or {"raises": "<ExceptionClassName>"}

Focus especially on edge cases implied by the docstring (e.g. "must be positive", "expired",
"already cancelled") and by any exceptions the function is documented to raise. Prefer
boundary values (0, negative numbers, empty strings, exact limits) over arbitrary ones.
Respond with ONLY the JSON array — no prose, no markdown fences."""


def build_user_prompt(func: FunctionInfo, max_cases: int = 6) -> str:
    params_desc = "\n".join(
        f"  - {p.name}: {p.annotation or 'Any'}"
        + (f" = {p.default}" if p.default is not None else "")
        for p in func.params
    )
    raises_desc = ", ".join(func.raises) if func.raises else "(none explicitly detected)"

    return f"""Function: {func.qualified_name}
Module: {func.module_path}
Parameters:
{params_desc or "  (none)"}
Return type: {func.return_annotation or "Any"}
Docstring:
\"\"\"
{func.docstring or "(no docstring provided)"}
\"\"\"
Exceptions raised in function body: {raises_desc}

Generate at most {max_cases} test case specifications as a JSON array, per the system
instructions. Prioritize at least one happy_path case and at least one case per distinct
exception type raised."""
