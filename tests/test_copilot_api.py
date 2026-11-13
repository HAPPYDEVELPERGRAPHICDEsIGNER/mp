"""
Comprehensive automated tests for AI Software Engineering Copilot API routes.
Runs against an isolated temporary SQLite database and includes mock coverage
for external network dependencies (GitHub REST API).
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
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
from services import testing_service, github_service

@pytest.fixture(scope="module")
def client():
    """Module-level TestClient ensuring lifespan startup/shutdown executes."""
    with TestClient(app) as test_client:
        yield test_client

# ==========================================
# 1. UI & Static Files Tests
# ==========================================

def test_serve_home(client):
    """Verify home page route serves index.html single page app."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AI Software Engineering Copilot" in response.text

def test_static_assets(client):
    """Verify static assets are served properly."""
    css_resp = client.get("/static/css/styles.css")
    assert css_resp.status_code == 200
    assert "css" in css_resp.headers.get("content-type", "")

    js_resp = client.get("/static/js/app.js")
    assert js_resp.status_code == 200
    assert "javascript" in js_resp.headers.get("content-type", "")

# ==========================================
# 2. Health & Diagnostics Tests
# ==========================================

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

# ==========================================
# 3. Code Generation Tests
# ==========================================

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

# ==========================================
# 4. Automated Testing & Sandbox Tests
# ==========================================

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

def test_test_endpoint_alias(client):
    """Verify /api/test endpoint alias forwards to run_tests_endpoint."""
    user_code = '''def add(x: int, y: int) -> int:
    return x + y
'''
    resp = client.post("/api/test", json={"code": user_code, "allow_execution": True})
    assert resp.status_code == 200
    assert resp.json()["executed"] is True

def test_test_run_execution_disabled(client):
    """Verify allow_execution=False runs static AST validation without spawning subprocess."""
    user_code = '''def subtract(a: int, b: int) -> int:
    return a - b
'''
    resp = client.post("/api/test/run", json={"code": user_code, "allow_execution": False})
    assert resp.status_code == 200
    data = resp.json()
    assert data["executed"] is False
    assert "EXECUTION OFF" in data.get("mode", "")

def test_class_method_test_generation():
    """Verify AST generator detects methods within classes if no top-level functions exist."""
    code = '''class Calculator:
    def add(self, a: int, b: int) -> int:
        return a + b
'''
    res = testing_service.generate_test_suite(code)
    assert res["success"] is True
    assert "add" in res["functions_detected"]

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

# ==========================================
# 5. Code Reviewer Tests
# ==========================================

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
    assert "Critical" in severities
    assert any("Mutable Default" in f["title"] for f in data["findings"])
    assert any("Bare 'except:'" in f["title"] for f in data["findings"])
    # Verify line numbers are captured for eval
    eval_findings = [f for f in data["findings"] if "eval" in f["title"].lower()]
    assert len(eval_findings) >= 1
    assert eval_findings[0]["line"] == 7

def test_code_reviewer_multilanguage(client):
    """Verify code reviewer handles JavaScript, C++, and Java checks."""
    # JavaScript loose equality & var
    js_code = 'var x = 10;\nif (x == "10") { console.log(x); }'
    js_resp = client.post("/api/review", json={"code": js_code, "language": "JavaScript"})
    assert js_resp.status_code == 200
    assert any("Loose Equality" in f["title"] for f in js_resp.json()["findings"])
    assert any("var" in f["title"] for f in js_resp.json()["findings"])

    # C++ buffer overflow check
    cpp_code = '#include <cstring>\nvoid copy(char* dest, char* src) { strcpy(dest, src); }'
    cpp_resp = client.post("/api/review", json={"code": cpp_code, "language": "C++"})
    assert cpp_resp.status_code == 200
    assert any("Buffer" in f["title"] for f in cpp_resp.json()["findings"])

    # Java empty catch block check
    java_code = 'public class App { public static void main(String[] args) { try { } catch (Exception e) {} } }'
    java_resp = client.post("/api/review", json={"code": java_code, "language": "Java"})
    assert java_resp.status_code == 200
    assert any("Empty Catch" in f["title"] for f in java_resp.json()["findings"])

# ==========================================
# 6. GitHub Assistant Tests (URL Validation & Mocked API)
# ==========================================

def test_github_url_validation(client):
    """Verify GitHub endpoint validates URLs strictly and accepts schemeless URLs."""
    # Invalid domain
    resp = client.post("/api/github/inspect", json={"url": "https://gitlab.com/owner/repo"})
    assert resp.status_code == 400
    # Missing repo path
    resp2 = client.post("/api/github/inspect", json={"url": "https://github.com/onlyowner"})
    assert resp2.status_code == 400
    # Alias endpoint
    resp3 = client.post("/api/github", json={"url": "https://gitlab.com/owner/repo"})
    assert resp3.status_code == 400

def test_parse_repo_url_flexible():
    """Verify parse_repo_url accepts URLs with or without https://."""
    owner, repo = github_service.parse_repo_url("github.com/tiangolo/fastapi")
    assert owner == "tiangolo"
    assert repo == "fastapi"

@pytest.mark.anyio
async def test_github_mocked_endpoints(client):
    """Verify GitHub API routes function properly with simulated GitHub API responses."""
    # 1. Mock inspect
    mock_meta_resp = MagicMock()
    mock_meta_resp.status_code = 200
    mock_meta_resp.json.return_value = {
        "full_name": "tiangolo/fastapi",
        "name": "fastapi",
        "description": "FastAPI framework, high performance, easy to learn.",
        "html_url": "https://github.com/tiangolo/fastapi",
        "stargazers_count": 80000,
        "forks_count": 6000,
        "open_issues_count": 100,
        "language": "Python",
        "default_branch": "master"
    }

    mock_contents_resp = MagicMock()
    mock_contents_resp.status_code = 200
    mock_contents_resp.json.return_value = [
        {"name": "main.py", "path": "main.py", "type": "file", "size": 1024, "download_url": "https://raw.githubusercontent.com/..."},
        {"name": "docs", "path": "docs", "type": "dir", "size": 0, "download_url": None}
    ]

    mock_commits_resp = MagicMock()
    mock_commits_resp.status_code = 200
    mock_commits_resp.json.return_value = [
        {"sha": "abc12345678", "commit": {"message": "Update docs", "author": {"name": "Author", "date": "2026-10-15T00:00:00Z"}}}
    ]

    async def mock_get(url, *args, **kwargs):
        if url.endswith("/contents"):
            return mock_contents_resp
        elif "/commits" in url:
            return mock_commits_resp
        return mock_meta_resp

    with patch("httpx.AsyncClient.get", side_effect=mock_get):
        inspect_resp = client.post("/api/github/inspect", json={"url": "https://github.com/tiangolo/fastapi"})
        assert inspect_resp.status_code == 200
        data = inspect_resp.json()
        assert data["repository"] == "tiangolo/fastapi"
        assert len(data["files"]) == 2
        assert len(data["recent_commits"]) == 1

# ==========================================
# 7. Task History Tests
# ==========================================

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

def test_clear_all_history(client):
    """Verify clearing all history via DELETE /api/history."""
    # Ensure there is at least one item
    client.post("/api/generate", json={"prompt": "Sample task to clear", "language": "Python"})
    assert len(client.get("/api/history").json()) >= 1

    # Clear all
    clear_resp = client.delete("/api/history")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["cleared"] is True

    # Check history is empty
    empty_resp = client.get("/api/history")
    assert empty_resp.status_code == 200
    assert len(empty_resp.json()) == 0
