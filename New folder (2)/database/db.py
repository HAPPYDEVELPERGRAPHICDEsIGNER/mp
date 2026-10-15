"""
Database connection and initialization module for AI Software Engineering Copilot.
Uses SQLite with WAL mode for safe, local concurrent operations.
"""
import os
import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

logger = logging.getLogger("copilot.db")

# Default database location inside database/ directory
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "copilot.db"
DB_PATH = Path(os.getenv("COPILOT_DB", str(DEFAULT_DB_PATH)))

def get_db_path() -> Path:
    return DB_PATH

def init_db():
    """Initializes SQLite database tables and indices."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            module TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            language TEXT,
            input_data TEXT,
            result_data TEXT NOT NULL,
            status TEXT DEFAULT 'success',
            created_at TEXT NOT NULL
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_module ON tasks(module)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created ON tasks(created_at DESC)")
        conn.commit()
    logger.info("Database initialized at %s", DB_PATH)

@contextmanager
def connect():
    """Context manager for SQLite connections with row factory and WAL mode."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()
