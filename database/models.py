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

    clean_title = (title or "")[:200]
    clean_description = (description or "")[:4000]

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (module, title, description, language, input_data, result_data, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                module,
                clean_title,
                clean_description,
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
        "title": clean_title,
        "description": clean_description,
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

# ============================================================================
# Codebase Intelligence Persistence
# ============================================================================

def save_codebase_project(
    path: str,
    name: str,
    file_count: int,
    total_symbols: int,
    total_chunks: int
) -> Dict[str, Any]:
    """Saves or updates a scanned codebase project."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO codebase_projects (path, name, file_count, total_symbols, total_chunks, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name = excluded.name,
                file_count = excluded.file_count,
                total_symbols = excluded.total_symbols,
                total_chunks = excluded.total_chunks,
                indexed_at = excluded.indexed_at
            """,
            (path, name, file_count, total_symbols, total_chunks, now)
        )
        conn.commit()
    return {
        "path": path,
        "name": name,
        "file_count": file_count,
        "total_symbols": total_symbols,
        "total_chunks": total_chunks,
        "indexed_at": now
    }

def get_codebase_project(path: str) -> Optional[Dict[str, Any]]:
    """Retrieves metadata for an indexed project."""
    with connect() as conn:
        row = conn.execute(
            "SELECT id, path, name, file_count, total_symbols, total_chunks, indexed_at FROM codebase_projects WHERE path = ?",
            (path,)
        ).fetchone()
        if not row:
            return None
        return dict(row)

def list_codebase_projects() -> List[Dict[str, Any]]:
    """Returns all indexed codebase projects."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, path, name, file_count, total_symbols, total_chunks, indexed_at FROM codebase_projects ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

def save_codebase_chunks(project_path: str, chunks: List[Dict[str, Any]]):
    """Replaces chunks for a given project."""
    with connect() as conn:
        conn.execute("DELETE FROM codebase_chunks WHERE project_path = ?", (project_path,))
        for c in chunks:
            conn.execute(
                """
                INSERT INTO codebase_chunks (
                    project_path, file_path, chunk_id, symbol_type, name,
                    start_line, end_line, content, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_path,
                    c.get("file_path", ""),
                    c.get("chunk_id", ""),
                    c.get("symbol_type"),
                    c.get("name"),
                    c.get("start_line", 0),
                    c.get("end_line", 0),
                    c.get("content", ""),
                    _serialize(c.get("embedding"))
                )
            )
        conn.commit()

def get_codebase_chunks(project_path: str) -> List[Dict[str, Any]]:
    """Retrieves all chunks for a project."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, project_path, file_path, chunk_id, symbol_type, name,
                   start_line, end_line, content, embedding
            FROM codebase_chunks WHERE project_path = ?
            """,
            (project_path,)
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["embedding"] = _deserialize(d["embedding"])
            result.append(d)
        return result

def delete_codebase_project(project_path: str) -> bool:
    """Deletes an indexed codebase project and its chunks."""
    with connect() as conn:
        conn.execute("DELETE FROM codebase_chunks WHERE project_path = ?", (project_path,))
        cursor = conn.execute("DELETE FROM codebase_projects WHERE path = ?", (project_path,))
        conn.commit()
        return cursor.rowcount > 0

# ============================================================================
# Safe AI Code Modification (Pending Changes, Diffs, Approvals)
# ============================================================================

def save_pending_change(
    change_id: str,
    file_path: str,
    original_content: str,
    proposed_content: str,
    unified_diff: str,
    explanation: str
) -> Dict[str, Any]:
    """Records a newly proposed AI code change awaiting user approval."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO pending_changes (
                id, file_path, original_content, proposed_content,
                unified_diff, explanation, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (change_id, file_path, original_content, proposed_content, unified_diff, explanation, now)
        )
        conn.commit()
    return {
        "id": change_id,
        "file_path": file_path,
        "unified_diff": unified_diff,
        "explanation": explanation,
        "status": "pending",
        "created_at": now
    }

def get_pending_change(change_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a pending change by its unique ID."""
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id, file_path, original_content, proposed_content,
                   unified_diff, explanation, status, backup_path,
                   test_results, created_at, applied_at
            FROM pending_changes WHERE id = ?
            """,
            (change_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["test_results"] = _deserialize(d["test_results"])
        return d

def update_pending_change_status(
    change_id: str,
    status: str,
    backup_path: Optional[str] = None,
    test_results: Optional[Any] = None
) -> bool:
    """Updates status ('applied', 'rejected', 'rolled_back') of a code change."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    serialized_tests = _serialize(test_results) if test_results is not None else None
    with connect() as conn:
        cursor = conn.execute(
            """
            UPDATE pending_changes
            SET status = ?,
                backup_path = COALESCE(?, backup_path),
                test_results = COALESCE(?, test_results),
                applied_at = CASE WHEN ? = 'applied' THEN ? ELSE applied_at END
            WHERE id = ?
            """,
            (status, backup_path, serialized_tests, status, now, change_id)
        )
        conn.commit()
        return cursor.rowcount > 0

def list_pending_changes(status: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Lists code changes, optionally filtered by status."""
    query = "SELECT id, file_path, unified_diff, explanation, status, backup_path, test_results, created_at, applied_at FROM pending_changes"
    params = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["test_results"] = _deserialize(d["test_results"])
            result.append(d)
        return result
