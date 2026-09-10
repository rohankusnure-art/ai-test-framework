# Setup

## Prerequisites
- Python 3.10+
- (Optional) A Postgres instance if you don't want to use the SQLite default
- (Optional) An OpenAI API key, or a Hugging Face Inference API token, if
  you want live LLM generation rather than the offline fallback

## Local install

```bash
git clone https://github.com/<your-username>/ai-test-framework.git
cd ai-test-framework

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e .
pip install -r requirements.txt
```

## Configure

```bash
cp .env.example .env
```

Edit `.env`:

- Leave `OPENAI_API_KEY` blank to run in offline mode (the framework
  falls back to a deterministic `NullLLMClient` — useful for trying the
  CLI end-to-end without any credentials).
- Set `OPENAI_API_KEY` and `LLM_PROVIDER=openai` for real LLM-generated
  test cases.
- Set `LLM_PROVIDER=huggingface` and `HUGGINGFACE_MODEL` to use an
  open-source model instead.
- `DATABASE_URL` defaults to a local SQLite file. For Postgres:
  ```
  DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/ai_test_framework
  ```
  (uncomment `psycopg2-binary` in `requirements.txt` first)

## Initialize the database

```bash
python scripts/init_db.py
```

## Verify the install

```bash
pytest tests/ -v
```

This runs the framework's own unit tests (scanner, generator, executor,
storage) — not the generated test suite. All of these are hermetic and
require no API keys or external database.
