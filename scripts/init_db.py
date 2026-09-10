"""
init_db.py

Creates all tables for the configured DATABASE_URL. Safe to run multiple
times (SQLAlchemy's create_all is idempotent — it only creates tables
that don't already exist, it never drops or alters existing ones).

Usage:
    python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ai_test_framework.config import get_config  # noqa: E402
from ai_test_framework.storage.sql_store import SQLStore  # noqa: E402


def main() -> None:
    config = get_config()
    print(f"Initializing schema at: {config.database_url}")
    store = SQLStore(config)
    store.close()
    print("Done.")


if __name__ == "__main__":
    main()
