# AI-Powered Test Case Generation & Automation Framework

![CI](https://github.com/<your-username>/ai-test-framework/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

A framework that scans a Python codebase, uses an LLM to generate
realistic test cases (including the edge cases a human writing tests
under deadline pressure tends to skip), runs them via pytest, and stores
every result so pass/fail trends are tracked over time — not just
whatever the last CI run happened to show.

## Why this exists

Writing comprehensive tests — especially edge cases implied by a
docstring but not obvious from the happy path — is repetitive and easy
to under-invest in under deadline pressure. This framework treats test
generation as a repeatable pipeline step: point it at a module, get back
a pytest suite that already covers boundary values, documented
exceptions, and idempotency concerns, wired into CI from day one.

The included example isn't a toy `add(a, b)` function — it's an
e-commerce order-processing module with the edge cases that actually
matter in production commerce systems: insufficient stock, expired
discount codes, double-cancellation, and refund eligibility. See
[`docs/usage.md`](docs/usage.md) for the full before/after.

## Architecture

```
Scanner (ast) → Generator (LangChain+LLM) → Test Writer → Executor (pytest) → Storage (SQL)
```

Full data flow, and the reasoning behind each design decision (why
static analysis over dynamic import, why two related tables instead of
one flat table, how rollback safety and connection pooling are handled,
timeout/retry behavior), is written up in
[`docs/architecture.md`](docs/architecture.md).

## Tech stack

Python 3.10+ · pytest · LangChain (OpenAI / Hugging Face) · SQLAlchemy
(SQLite for local/dev, Postgres-ready) · Click (CLI) · GitHub Actions

## Quickstart

```bash
git clone https://github.com/<your-username>/ai-test-framework.git
cd ai-test-framework
python -m venv .venv && source .venv/bin/activate
pip install -e . && pip install -r requirements.txt
cp .env.example .env          # optionally add an OPENAI_API_KEY

python scripts/init_db.py

ai-test-gen generate \
  --target targets/sample_ecommerce_app \
  --import-path targets.sample_ecommerce_app.order_service

ai-test-gen run --tests-dir generated_tests
```

No API key configured? The framework automatically falls back to a
deterministic offline generator so the full pipeline is still runnable
end-to-end — see `NullLLMClient` in
`src/ai_test_framework/generator/llm_client.py`.

Full setup instructions: [`docs/setup.md`](docs/setup.md).
CLI usage and the before/after example: [`docs/usage.md`](docs/usage.md).

## CI/CD

Every push and pull request runs, across Python 3.10–3.12
([`.github/workflows/ci.yml`](.github/workflows/ci.yml)):

1. Lint (`ruff`) and type-check (`mypy`) the framework source
2. Run the framework's own unit tests (`tests/`) — these test the
   scanner, generator, executor, and storage layer in isolation
3. Generate tests against the sample target module
4. Execute the generated suite and fail the build on any test failure
5. Upload results (JUnit XML + generated files) as build artifacts

No secrets are required for CI to pass — the OpenAI-backed path is
exercised only if `OPENAI_API_KEY` is set as a repo secret; otherwise
generation falls back to the offline client automatically, so forked PRs
still get a real signal.

## Project layout

```
src/ai_test_framework/
├── scanner/     # ast-based function/docstring extraction
├── generator/   # LLM prompt building + provider-agnostic client + test writer
├── executor/    # runs generated pytest suite, captures structured results
├── storage/     # SQLAlchemy models + store, for historical trend analysis
└── cli.py       # `ai-test-gen generate|run|trend`

targets/sample_ecommerce_app/   # realistic sample module the framework generates tests for
generated_tests/                # output of `ai-test-gen generate` (one example checked in)
tests/                          # unit tests for the framework itself
docs/                           # architecture, setup, usage
```

## Roadmap

- [ ] Additional scanner backend for a non-Python target (C++ via clang
      AST, or C# via Roslyn) — the `FunctionInfo` contract in
      `scanner/repo_scanner.py` is already language-agnostic downstream
- [ ] MongoDB storage backend implementing `storage/db_interface.py`
- [ ] Mutation-testing pass to score generated-test quality, not just
      coverage
- [ ] Web dashboard over the trend data in `storage/`

## License

MIT — see [`LICENSE`](LICENSE).
