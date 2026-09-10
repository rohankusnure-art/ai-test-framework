# Architecture

## Data Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Scanner   │────▶│  Generator   │────▶│ Test Writer │────▶│   Executor   │────▶│   Storage    │
│  (ast-based)│     │ (LangChain + │     │ (spec→.py)  │     │  (pytest via │     │ (SQLAlchemy, │
│             │     │  LLM client) │     │             │     │  subprocess) │     │  SQL store)  │
└─────────────┘     └──────────────┘     └─────────────┘     └──────────────┘     └─────────────┘
      │                     │                    │                    │                    │
 FunctionInfo         JSON test specs      generated_tests/*.py   RunSummary          TestCase +
 (name, params,       (name, category,                            (pass/fail per      TestRun rows
  docstring,           inputs, expected)                           test)               (historical)
  raises)
```

Each stage has a narrow, typed contract with the next, so any stage can be
swapped independently — e.g. replacing the OpenAI-backed generator with a
Hugging Face one, or SQLite with Postgres, touches exactly one module.

## Component Decisions

### Scanner: static analysis over dynamic import
The scanner uses Python's `ast` module rather than importing target code.
Importing arbitrary third-party code just to introspect it means executing
untrusted code as a side effect of "scanning" — unacceptable for a tool
meant to run against someone else's repository in CI. AST parsing is
strictly safer, with no import-order or missing-dependency failures.

### Generator: provider-agnostic with an offline fallback
`llm_client.py` wraps LangChain so the concrete provider (OpenAI vs.
Hugging Face) is a config value, not a code change. A `NullLLMClient`
fallback activates automatically when no API key is configured, which
keeps the framework's own CI green and its logic testable without
live network calls or secrets — see `.github/workflows/ci.yml`.

### Latency & serving considerations
- **Bounded LLM calls**: `LLM_TIMEOUT_SECONDS` and `LLM_MAX_RETRIES` cap
  how long a single hung provider call can stall the pipeline, with capped
  exponential backoff between retries (max 8s) rather than unbounded retry
  loops.
- **Subprocess isolation for execution**: generated tests run in a
  separate `pytest` subprocess with an enforced timeout
  (`TEST_EXECUTION_TIMEOUT_SECONDS`), so a generated test that hangs or
  crashes the interpreter can't take down the orchestrating process.
- **Connection pooling**: `DB_POOL_SIZE` / `DB_POOL_TIMEOUT_SECONDS` are
  configurable for Postgres deployments so concurrent CI runners writing
  results don't starve each other for connections. SQLite (the local/dev
  default) ignores these — single-file, no pooling needed.
- **Structured result parsing**: the executor reads pytest's
  `--json-report` output rather than screen-scraping stdout, which is
  both faster to parse and doesn't break if pytest's human-readable
  output format changes between versions.

### Data design decisions
- **Money as integer cents, never float**, in the sample target module —
  avoids silent rounding-error corruption in financial calculations, a
  real and common source of commerce-system bugs.
- **Two related tables, not one flat table**: `test_cases` (the generated
  spec — what, from which function, why) and `test_runs` (each
  execution's outcome) are separate, joined by foreign key. The same
  generated test case is re-run on every push; keeping spec identity
  stable across many run rows is what makes "did this specific edge case
  start failing after commit X?" trend queries possible.
- **Indexed on the actual read pattern**: both tables index
  `function_qualified_name` (and `test_runs` additionally indexes
  `(test_case_id, run_at)`) because the primary query is "show recent
  history for function X" — without the index this degrades to a full
  table scan as CI history accumulates.

### Rollback / transactional integrity
Every write goes through a `_session_scope()` context manager in
`sql_store.py` that commits on success and explicitly rolls back on any
exception before re-raising. Without this, a failure partway through
persisting a batch of results (e.g. a dropped connection) could leave a
`test_case` row committed with no corresponding `test_run` rows —
silently corrupting the exact trend data the feature exists to produce.
SQLite's foreign-key enforcement is explicitly turned on per-connection
(off by default in SQLite) so this integrity constraint is actually
enforced, not just assumed.

## Real business problem, not a toy example
The sample target (`targets/sample_ecommerce_app/order_service.py`) is an
order-processing module with genuine commerce edge cases: insufficient
stock, expired/invalid discount codes, double-cancellation, and refund
eligibility rules. This is deliberate — generating tests for `def add(a,
b): return a + b` proves nothing about whether the framework surfaces
edge cases that actually matter in production systems.

## Extension points
- **Multi-language target**: `scanner/repo_scanner.py` is Python/AST-
  specific by design (see decision above); adding a C++/C# target means
  adding a sibling scanner (e.g. via `clang` AST dumps or Roslyn) behind
  the same `FunctionInfo` contract — no changes needed downstream.
- **NoSQL storage**: implement `BaseStore` (see `storage/db_interface.py`)
  against MongoDB; nothing outside `storage/` needs to change.
