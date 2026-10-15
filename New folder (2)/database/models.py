"""
Data access and task models for AI Software Engineering Copilot.
Handles task persistence, query filtering, and dashboard metrics.
"""
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from .db import connect

def _serialize(obj: Any) -> str:
    """Safe JSON serialization helper."""
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, default=str)

def _deserialize(data: Optional[str]) -> Any:
    """Safe JSON deserialization helper."""
    if not data:
        return None
    try:
        return json.loads(data)
    except (json.JSONDecodeError, TypeError):
        return data

def save_task(
    module: str,
    title: str,
    description: str,
    result: Any,
    language: Optional[str] = None,
    input_data: Optional[Any] = None,
    status: str = "success"
) -> Dict[str, Any]:
    """Persists a new task entry in the SQLite database."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    serialized_input = _serialize(input_data) if input_data is not None else None
    serialized_result = _serialize(result)

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (module, title, description, language, input_data, result_data, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module,
                title[:200],
                description[:4000],
                language,
                serialized_input,
                serialized_result,
                status,
                now
            )
        )
        task_id = cursor.lastrowid
        conn.commit()

    return {
        "id": task_id,
        "module": module,
        "title": title[:200],
        "description": description[:4000],
        "language": language,
        "status": status,
        "result": result,
        "created_at": now
    }

def get_tasks(
    limit: int = 100,
    offset: int = 0,
    module: Optional[str] = None,
    search: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieves tasks with optional module filtering and text search."""
    query = "SELECT id, module, title, description, language, status, created_at, result_data, input_data FROM tasks WHERE 1=1"
    params = []

    if module and module != "all":
        query += " AND module = ?"
        params.append(module)

    if search:
        query += " AND (title LIKE ? OR description LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term])

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "module": r["module"],
                "title": r["title"],
                "description": r["description"],
                "language": r["language"],
                "status": r["status"],
                "created_at": r["created_at"],
                "result": _deserialize(r["result_data"]),
                "input_data": _deserialize(r["input_data"])
            })
        return result

def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """Retrieves a single task by its primary key ID."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, module, title, description, language, status, created_at, result_data, input_data FROM tasks WHERE id = ?",
            (task_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "module": row["module"],
            "title": row["title"],
            "description": row["description"],
            "language": row["language"],
            "status": row["status"],
            "created_at": row["created_at"],
            "result": _deserialize(row["result_data"]),
            "input_data": _deserialize(row["input_data"])
        }

def delete_task(task_id: int) -> bool:
    """Deletes a task by ID. Returns True if deleted, False if not found."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.commit()
        return cursor.rowcount > 0

def clear_all_tasks() -> int:
    """Clears all tasks from the database."""
    with connect() as conn:
        cursor = conn.execute("DELETE FROM tasks")
        conn.commit()
        return cursor.rowcount

def get_dashboard_stats() -> Dict[str, Any]:
    """Computes real metrics from the database without inventing numbers."""
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        rows = conn.execute(
            "SELECT module, COUNT(*) as count FROM tasks GROUP BY module"
        ).fetchall()
        counts = {r["module"]: r["count"] for r in rows}

        recent_rows = conn.execute(
            "SELECT id, module, title, description, language, status, created_at FROM tasks ORDER BY id DESC LIMIT 6"
        ).fetchall()
        recent = [dict(r) for r in recent_rows]

    return {
        "total_tasks": total,
        "code_generations": counts.get("generate", 0),
        "tests_executed": counts.get("test", 0),
        "code_reviews": counts.get("review", 0),
        "github_inquiries": counts.get("github", 0),
        "recent_activities": recent
    }
