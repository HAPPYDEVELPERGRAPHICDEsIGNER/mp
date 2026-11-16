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

def get_db_path() -> Path:
    """Returns the active SQLite database path, supporting dynamic env overrides."""
    return Path(os.getenv("COPILOT_DB", str(DEFAULT_DB_PATH)))

def init_db():
    """Initializes SQLite database tables and indices."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
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

        # Codebase Intelligence projects
        conn.execute("""
        CREATE TABLE IF NOT EXISTS codebase_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            file_count INTEGER DEFAULT 0,
            total_symbols INTEGER DEFAULT 0,
            total_chunks INTEGER DEFAULT 0,
            indexed_at TEXT NOT NULL
        )
        """)

        # Codebase Intelligence chunks and embeddings
        conn.execute("""
        CREATE TABLE IF NOT EXISTS codebase_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_path TEXT NOT NULL,
            file_path TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            symbol_type TEXT,
            name TEXT,
            start_line INTEGER,
            end_line INTEGER,
            content TEXT NOT NULL,
            embedding TEXT
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_project ON codebase_chunks(project_path)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file ON codebase_chunks(file_path)")

        # Safe AI Code Modifications (Diffs, Approvals, Rollbacks)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_changes (
            id TEXT PRIMARY KEY,
            file_path TEXT NOT NULL,
            original_content TEXT NOT NULL,
            proposed_content TEXT NOT NULL,
            unified_diff TEXT NOT NULL,
            explanation TEXT,
            status TEXT DEFAULT 'pending',
            backup_path TEXT,
            test_results TEXT,
            created_at TEXT NOT NULL,
            applied_at TEXT
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pending_changes_status ON pending_changes(status)")
        conn.commit()
    logger.info("Database initialized at %s", db_path)

@contextmanager
def connect():
    """Context manager for SQLite connections with row factory and WAL mode."""
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        yield conn
    finally:
        conn.close()
