"""
Comprehensive automated tests for AI Software Engineering Copilot API routes.
Runs against an isolated temporary SQLite database.
"""
import os
import sys
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure root directory is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Create an isolated temporary test database before importing main app
_temp_dir = tempfile.TemporaryDirectory()
os.environ["COPILOT_DB"] = str(Path(_temp_dir.name) / "test_copilot.db")

from main import app

@pytest.fixture(scope="module")
def client():
    """Module-level TestClient ensuring lifespan startup/shutdown executes."""
    with TestClient(app) as test_client:
        yield test_client

def test_health_check(client):
    """Verify health and diagnostics endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "ai_engine" in data
    assert data["isolated_sandbox_available"] is True

def test_dashboard_metrics(client):
    """Verify dashboard metrics endpoint returns real database counts."""
    response = client.get("/api/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert "total_tasks" in data
    assert "code_generations" in data
    assert "tests_executed" in data
    assert "code_reviews" in data
    assert "github_inquiries" in data
    assert isinstance(data["recent_activities"], list)

def test_code_generation_and_history(client):
    """Verify deterministic code generation and task persistence."""
    req = {
        "prompt": "Write a Python factorial calculation function with validation",
        "language": "Python",
        "style": "standard"
    }
    response = client.post("/api/generate", json=req)
    assert response.status_code == 200
    data = response.json()
    assert "code" in data
    assert "def factorial" in data["code"]
    assert "task_id" in data
    task_id = data["task_id"]

    # Check task exists in history
    history_resp = client.get(f"/api/history/{task_id}")
    assert history_resp.status_code == 200
    assert history_resp.json()["module"] == "generate"

    # Delete task
    del_resp = client.delete(f"/api/history/{task_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True

def test_generate_input_validation(client):
    """Verify input validation rejects bad inputs with 422."""
    # Too short prompt
    assert client.post("/api/generate", json={"prompt": "hi", "language": "Python"}).status_code == 422
    # Unsupported language
    assert client.post("/api/generate", json={"prompt": "valid requirement here", "language": "Ruby"}).status_code == 422

def test_automated_test_generation_and_run(client):
    """Verify automated AST test generation and safe execution."""
    user_code = '''def multiply(a: int, b: int) -> int:
    return a * b
'''
    # 1. Generate tests
    gen_resp = client.post("/api/test/generate-tests", json={"code": user_code})
    assert gen_resp.status_code == 200
    assert gen_resp.json()["success"] is True
    assert "test_multiply_basic" in gen_resp.json()["generated_tests"]

    # 2. Run tests in isolated subprocess
    run_resp = client.post("/api/test/run", json={"code": user_code, "allow_execution": True})
    assert run_resp.status_code == 200
    data = run_resp.json()
    assert data["executed"] is True
    assert data["passed"] >= 1
    assert data["failed"] == 0

def test_security_guardrail_blocks_dangerous_code(client):
    """Verify AST security guardrail intercepts malicious code without executing it."""
    malicious_code = '''import os
def exploit():
    os.system("echo hacked")
'''
    response = client.post("/api/test/run", json={"code": malicious_code, "allow_execution": True})
    assert response.status_code == 200
    data = response.json()
    assert data["executed"] is False
    assert data["security_blocked"] is True
    assert any("Disallowed import" in v for v in data["violations"])

def test_code_reviewer(client):
    """Verify static analysis engine detects vulnerabilities, bugs, and readability issues."""
    vulnerable_code = '''import os

api_key = "AIzaSySecretApiKey12345678"

def compute(x=[]):
    try:
        val = eval("x + 1")
    except:
        val = 0
    return val
'''
    response = client.post("/api/review", json={"code": vulnerable_code, "language": "Python"})
    assert response.status_code == 200
    data = response.json()
    assert data["score"] < 80
    assert data["grade"] in ("C", "D", "F")
    severities = [f["severity"] for f in data["findings"]]
    assert "Critical" in severities  # from hardcoded secret or eval
    assert any("Mutable Default" in f["title"] for f in data["findings"])
    assert any("Bare 'except:'" in f["title"] for f in data["findings"])

def test_github_url_validation(client):
    """Verify GitHub endpoint validates URLs strictly."""
    # Invalid domain
    resp = client.post("/api/github/inspect", json={"url": "https://gitlab.com/owner/repo"})
    assert resp.status_code == 400
    # Missing repo path
    resp2 = client.post("/api/github/inspect", json={"url": "https://github.com/onlyowner"})
    assert resp2.status_code == 400

def test_history_crud(client):
    """Verify task history retrieval, filtering, and deletion."""
    # Create a task via generate
    client.post("/api/generate", json={"prompt": "Write a binary search algorithm in Python", "language": "Python"})
    
    # List history
    list_resp = client.get("/api/history")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1

    # Filter by module
    filter_resp = client.get("/api/history?module=generate")
    assert filter_resp.status_code == 200
    assert all(i["module"] == "generate" for i in filter_resp.json())

    # Get non-existent task
    assert client.get("/api/history/999999").status_code == 404
    assert client.delete("/api/history/999999").status_code == 404
