"""
Automated Test Suite for AI Software Engineering Copilot — Gemini Edition.
Tests Gemini model selection, error handling, Codebase Intelligence (indexing, chunking, RAG),
safe code modification (proposals, diffs, backups, rollbacks), and API endpoints.
Uses unittest.mock to test Gemini cloud features predictably without requiring real API calls.
"""
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from main import app
from database.db import init_db
from database import models
from services import gemini_service, codebase_service, diff_service, ai_service, testing_service

@pytest.fixture(scope="module", autouse=True)
def setup_test_environment():
    """Ensure database is initialized and clean for Gemini Edition tests."""
    init_db()
    yield

@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)

# ============================================================================
# 1. Gemini Configuration & Model Selection Tests
# ============================================================================

def test_missing_api_key_behavior():
    """Verify system detects missing/empty Gemini API key and reports offline status."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        assert gemini_service.is_gemini_configured() is False
        info = gemini_service.get_models_info()
        assert info["configured"] is False
        assert len(info["models"]) >= 5
        assert info["active_model"] in [m["id"] for m in info["models"]]

        # Direct generation without key should raise GeminiConfigurationError
        with pytest.raises(gemini_service.GeminiConfigurationError):
            gemini_service.generate_content("hello")

def test_model_selection_and_validation(client):
    """Test user model selection, session persistence, and validation rules."""
    # 1. Valid model selection
    res = client.post("/api/models/select", json={"model": "gemini-2.5-pro"})
    assert res.status_code == 200
    assert res.json()["active_model"] == "gemini-2.5-pro"
    assert gemini_service.get_selected_model() == "gemini-2.5-pro"

    # 2. Revert to default
    res = client.post("/api/models/select", json={"model": "gemini-2.5-flash"})
    assert res.status_code == 200
    assert res.json()["active_model"] == "gemini-2.5-flash"

    # 3. Invalid model selection rejected with 400
    res = client.post("/api/models/select", json={"model": "gpt-4-turbo"})
    assert res.status_code == 400
    assert "not supported" in res.json()["detail"]

def test_models_endpoint(client):
    """Verify GET /api/models returns complete model metadata and active selection."""
    res = client.get("/api/models")
    assert res.status_code == 200
    data = res.json()
    assert "models" in data
    assert "active_model" in data
    assert any(m["id"] == "gemini-2.5-flash" for m in data["models"])
    assert any(m["id"] == "gemini-2.5-pro" for m in data["models"])

# ============================================================================
# 2. Mocked Gemini API Generation & Error Handling Tests
# ============================================================================

def test_gemini_mocked_content_generation():
    """Verify Gemini generation works with mocked SDK response."""
    mock_response = MagicMock()
    mock_response.text = "def calculate_sum(a, b):\n    return a + b"
    mock_response.usage_metadata.total_token_count = 42

    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyMockKeyForTesting12345"}), \
         patch("services.gemini_service.genai.Client") as mock_client_cls:

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_client_cls.return_value = mock_client

        res = gemini_service.generate_content(
            prompt="Write a sum function",
            model="gemini-2.5-flash",
            system_instruction="You are a python assistant",
            temperature=0.1
        )

        assert res["text"] == mock_response.text
        assert res["model"] == "gemini-2.5-flash"
        assert res["tokens"] == 42
        mock_client.models.generate_content.assert_called_once()

def test_gemini_rate_limit_and_error_handling():
    """Verify rate limits and API exceptions are properly captured and raised."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyMockKeyForTesting12345"}), \
         patch("services.gemini_service.genai.Client") as mock_client_cls:

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("ResourceExhausted: 429 Rate limit exceeded")
        mock_client_cls.return_value = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            gemini_service.generate_content("test prompt")
        assert "rate limit exceeded" in str(exc_info.value).lower()

# ============================================================================
# 3. Codebase Intelligence Tests (Scan, Chunk, AST, Q&A)
# ============================================================================

def test_codebase_scanner_exclusions_and_traversal(tmp_path):
    """Verify scanner ignores .venv, .git, .env and enforces path traversal guards."""
    # Create test folder structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "app.py").write_text("def run():\n    return 'running'\n")

    # Excluded directories
    venv_dir = tmp_path / ".venv"
    venv_dir.mkdir()
    (venv_dir / "lib.py").write_text("# ignored venv file")

    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("# ignored git config")

    # Excluded file
    (tmp_path / ".env").write_text("SECRET=12345")

    # Perform scan
    res = codebase_service.codebase_service.scan_and_index(str(tmp_path))
    assert res["file_count"] == 1
    assert any("app.py" in f for f in res["scanned_files"])
    assert not any(".venv" in f for f in res["scanned_files"])
    assert not any(".git" in f for f in res["scanned_files"])
    assert not any(".env" in f for f in res["scanned_files"])

def test_codebase_python_ast_extraction():
    """Verify AST extraction captures functions, classes, and imports correctly."""
    sample_code = """import os
from datetime import datetime

class DataPipeline:
    \"\"\"Processes data batches.\"\"\"
    def __init__(self):
        pass

    def run_pipeline(self, batch_id: int):
        return True

def standalone_helper(x):
    \"\"\"Helper function.\"\"\"
    return x * 2
"""
    symbols, imports = codebase_service.extract_python_ast(sample_code)
    assert "os" in imports
    assert "datetime.datetime" in imports

    sym_names = [s["name"] for s in symbols]
    assert "DataPipeline" in sym_names
    assert "standalone_helper" in sym_names

    class_sym = next(s for s in symbols if s["name"] == "DataPipeline")
    assert "run_pipeline" in class_sym["methods"]

def test_codebase_query_offline_mode():
    """Verify querying an indexed project returns honest offline notice and cited chunks when no key."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        res = codebase_service.codebase_service.query_codebase(".", "where is database initialization?")
        assert res["ai_generated"] is False
        assert "Offline Mode" in res["answer"]
        assert len(res["relevant_chunks"]) > 0
        # Should cite actual files in project
        cited_files = [c["file_path"] for c in res["relevant_chunks"]]
        assert any("database" in f or "main.py" in f for f in cited_files)

def test_codebase_query_with_mocked_gemini():
    """Verify querying with Gemini produces grounded synthesized answer."""
    mock_resp = MagicMock()
    mock_resp.text = "Database initialization is defined in `database/db.py` inside `init_db()`."
    mock_resp.usage_metadata.total_token_count = 55

    with patch.dict(os.environ, {"GEMINI_API_KEY": "AIzaSyMockKeyForTesting12345"}), \
         patch("services.gemini_service.genai.Client") as mock_client_cls:

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        res = codebase_service.codebase_service.query_codebase(".", "Where is database initialized?")
        assert res["ai_generated"] is True
        assert "database/db.py" in res["answer"]
        assert len(res["relevant_chunks"]) > 0

# ============================================================================
# 4. Safe AI Code Modification & Diff Lifecycle Tests
# ============================================================================

def test_diff_service_full_lifecycle(tmp_path):
    """
    Test complete safe code modification lifecycle:
    1. Propose change (no disk modification)
    2. Inspect unified diff
    3. User approves change (applies change, creates .backup, runs syntax check)
    4. User rolls back change (restores original from backup)
    """
    test_file = tmp_path / "calculator.py"
    original_code = "def add(a, b):\n    return a + b\n"
    test_file.write_text(original_code)

    # 1. Propose change
    proposal = diff_service.diff_service.propose_change(
        file_path_str=str(test_file),
        instruction="Add detailed docstring"
    )
    change_id = proposal["change_id"]
    assert proposal["status"] == "pending"
    assert "--- a/calculator.py" in proposal["unified_diff"]
    assert "+++ b/calculator.py" in proposal["unified_diff"]

    # File on disk MUST be untouched during proposal
    assert test_file.read_text() == original_code

    # 2. Approve and Apply change
    applied = diff_service.diff_service.apply_change(change_id)
    assert applied["status"] == "applied"
    assert Path(applied["backup_path"]).exists()
    assert applied["test_results"]["syntax_valid"] is True

    # File on disk is now updated
    assert test_file.read_text() != original_code

    # 3. Rollback change
    rolled_back = diff_service.diff_service.rollback_change(change_id)
    assert rolled_back["status"] == "rolled_back"

    # File on disk is restored to exact original code
    assert test_file.read_text() == original_code

def test_diff_service_rejection(tmp_path):
    """Verify rejected changes are flagged in database and never modify the file on disk."""
    test_file = tmp_path / "service.py"
    content = "class Service:\n    pass\n"
    test_file.write_text(content)

    proposal = diff_service.diff_service.propose_change(str(test_file), "refactor")
    change_id = proposal["change_id"]

    res = diff_service.diff_service.reject_change(change_id)
    assert res["status"] == "rejected"

    # Confirm record and file state
    record = models.get_pending_change(change_id)
    assert record["status"] == "rejected"
    assert test_file.read_text() == content

def test_diff_service_blocks_sensitive_files():
    """Verify diff service refuses to modify .env or restricted system files."""
    with pytest.raises(ValueError) as exc_info:
        diff_service.diff_service.propose_change(".env", "modify key")
    assert "strictly forbidden" in str(exc_info.value)

# ============================================================================
# 5. FastAPI Endpoints Integration Tests for Gemini Edition
# ============================================================================

def test_api_codebase_endpoints(client):
    """Test /api/codebase/scan, /api/codebase/status, and /api/codebase/query."""
    # Status check
    res = client.get("/api/codebase/status?path=.")
    assert res.status_code == 200

    # Architecture trace
    arch_res = client.post("/api/codebase/architecture", json={"path": "."})
    assert arch_res.status_code == 200
    assert "entry_points" in arch_res.json()
    assert "total_files" in arch_res.json()

    # Query endpoint
    q_res = client.post("/api/codebase/query", json={"path": ".", "query": "database tables"})
    assert q_res.status_code == 200
    assert "answer" in q_res.json()
    assert "relevant_chunks" in q_res.json()

def test_api_diff_endpoints(client, tmp_path):
    """Test diff proposal, apply, and history via HTTP API."""
    temp_target = tmp_path / "module.py"
    temp_target.write_text("def test_me():\n    pass\n")

    # Propose
    prop_res = client.post("/api/diff/propose", json={
        "file_path": str(temp_target),
        "instruction": "add docstring"
    })
    assert prop_res.status_code == 200
    change_id = prop_res.json()["change_id"]

    # History contains pending
    hist_res = client.get("/api/diff/history")
    assert hist_res.status_code == 200
    assert any(c["id"] == change_id for c in hist_res.json())

    # Apply
    apply_res = client.post("/api/diff/apply", json={"change_id": change_id})
    assert apply_res.status_code == 200
    assert apply_res.json()["status"] == "applied"

    # Rollback
    rollback_res = client.post("/api/diff/rollback", json={"change_id": change_id})
    assert rollback_res.status_code == 200
    assert rollback_res.json()["status"] == "rolled_back"

def test_api_explain_and_improve_endpoints(client):
    """Test /api/explain and /api/improve with code snippets."""
    code = "def fib(n):\n    return n if n <= 1 else fib(n-1) + fib(n-2)"

    # Explain
    exp_res = client.post("/api/explain", json={"code": code, "language": "python"})
    assert exp_res.status_code == 200
    assert "explanation" in exp_res.json()

    # Improve
    imp_res = client.post("/api/improve", json={"code": code, "language": "python", "focus": "performance"})
    assert imp_res.status_code == 200
    assert "recommendations" in imp_res.json()

def test_health_check_sandbox_disclaimer(client):
    """Verify health check includes sandbox process isolation disclosure."""
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert "notice" in data
    assert "process isolation" in data["notice"].lower()
    assert "active_model" in data
