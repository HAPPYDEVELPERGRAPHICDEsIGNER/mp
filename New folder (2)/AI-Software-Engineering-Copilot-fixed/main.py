"""
AI Software Engineering Copilot — Main FastAPI Application.
Modular, production-ready, local-first developer dashboard.
"""
import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, status
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.requests import Request as StarletteRequest

# Load optional local .env configuration
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Import internal modules
from database.db import init_db, get_db_path
from database.models import (
    save_task,
    get_tasks,
    get_task_by_id,
    delete_task,
    clear_all_tasks,
    get_dashboard_stats
)
from services import ai_service, testing_service, code_reviewer, github_service

BASE_DIR = Path(__file__).resolve().parent

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("copilot")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown routines."""
    logger.info("Initializing AI Software Engineering Copilot database...")
    init_db()
    logger.info("Application ready. Running on local workspace.")
    yield
    logger.info("Shutting down AI Software Engineering Copilot.")

app = FastAPI(
    title="AI Software Engineering Copilot",
    description="Local-first AI developer assistant dashboard for code generation, testing, reviews, and repository exploration.",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static assets and template engine
static_path = BASE_DIR / "static"
static_path.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

templates_path = BASE_DIR / "templates"
templates_path.mkdir(parents=True, exist_ok=True)

# ==========================================
# Pydantic Request Schemas
# ==========================================

class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=4, max_length=5000, description="Programming requirement description")
    language: str = Field(..., pattern="^(Python|C\\+\\+|Java|JavaScript)$", description="Target programming language")
    style: Optional[str] = Field("standard", description="Architectural style (standard, oop, microservice)")

class TestSuiteRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=30000, description="Python source code to generate tests for")

class TestRunRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=30000, description="Python source code to test")
    test_code: Optional[str] = Field(None, max_length=30000, description="Optional custom test code")
    allow_execution: Optional[bool] = Field(True, description="Whether to execute tests in an isolated child process")

class CodeReviewRequest(BaseModel):
    code: str = Field(..., min_length=2, max_length=40000, description="Source code to analyze")
    language: str = Field(..., pattern="^(Python|C\\+\\+|Java|JavaScript)$", description="Programming language")

class GitHubInspectRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=300, description="Public GitHub repository URL")

class GitHubFileRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=300, description="Public GitHub repository URL")
    path: str = Field(..., min_length=1, max_length=500, description="Path to file within repository")

# ==========================================
# Frontend Page Routes
# ==========================================

@app.get("/", response_class=FileResponse)
async def serve_home():
    """Serves the single-page developer dashboard."""
    index_file = BASE_DIR / "templates" / "index.html"
    return FileResponse(str(index_file))

# ==========================================
# Health and Diagnostics API
# ==========================================

@app.get("/api/health")
async def health_check():
    """Returns application status, configured AI engine, and database path."""
    ai_info = ai_service.get_ai_provider_info()
    is_ai = ai_info["configured"]
    return {
        "status": "online",
        "mode": "LIVE AI" if is_ai else "DEMO MODE",
        "app_name": "AI Software Engineering Copilot",
        "version": "1.0.0",
        "ai_configured": is_ai,
        "ai_engine": ai_info,
        "database_file": str(get_db_path()),
        "isolated_sandbox_available": True,
        "execution_enabled": True,
        "github_token_configured": bool(os.getenv("GITHUB_TOKEN"))
    }

# ==========================================
# 1. Dashboard Metrics API
# ==========================================

@app.get("/api/dashboard")
async def get_dashboard():
    """Computes and returns real workspace metrics and recent activity from SQLite."""
    try:
        stats = get_dashboard_stats()
        return stats
    except Exception as e:
        logger.error("Error retrieving dashboard stats: %s", e)
        raise HTTPException(status_code=500, detail="Failed to load dashboard metrics.")

# ==========================================
# 2. AI Code Generator API
# ==========================================

@app.post("/api/generate")
async def generate_code_endpoint(body: GenerateRequest):
    """Generates idiomatic code based on the prompt and language."""
    try:
        result = await ai_service.generate_code(body.prompt, body.language, body.style or "standard")
        title = f"{body.language} Code Generation"
        task = save_task(
            module="generate",
            title=title,
            description=body.prompt,
            language=body.language,
            input_data={"prompt": body.prompt, "language": body.language, "style": body.style},
            result=result
        )
        return {**result, "task_id": task["id"]}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception("Code generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

# ==========================================
# 3. Automated Testing API
# ==========================================

@app.post("/api/test/generate-tests")
async def generate_tests_endpoint(body: TestSuiteRequest):
    """Inspects Python code via AST and synthesizes a runnable unittest test suite."""
    try:
        res = testing_service.generate_test_suite(body.code)
        if not res["success"]:
            raise HTTPException(status_code=400, detail=res["error"])
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to synthesize test suite: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate tests: {str(e)}")

@app.post("/api/test/run")
async def run_tests_endpoint(body: TestRunRequest):
    """Executes permitted tests in an isolated child process with timeout safeguards."""
    try:
        result = testing_service.run_tests_isolated(
            code=body.code,
            test_code=body.test_code,
            allow_execution=body.allow_execution if body.allow_execution is not None else True
        )
        task = save_task(
            module="test",
            title="Automated Test Execution",
            description=body.code[:150],
            language="Python",
            input_data={"code": body.code, "test_code": body.test_code},
            result=result,
            status="success" if result.get("failed", 0) == 0 else "warning"
        )
        return {**result, "task_id": task["id"]}
    except Exception as e:
        logger.exception("Automated testing run error: %s", e)
        raise HTTPException(status_code=500, detail=f"Test runner error: {str(e)}")

@app.post("/api/test")
async def test_endpoint_alias(body: TestRunRequest):
    """Alias for /api/test/run supporting standard requests."""
    return await run_tests_endpoint(body)

# ==========================================
# 4. AI Code Reviewer API
# ==========================================

@app.post("/api/review")
async def review_code_endpoint(body: CodeReviewRequest):
    """Analyzes source code for security, bug risks, readability, and maintainability."""
    try:
        result = code_reviewer.review_code(body.code, body.language)
        task = save_task(
            module="review",
            title=f"{body.language} Code Review (Score: {result['score']}/100)",
            description=body.code[:150],
            language=body.language,
            input_data={"code": body.code, "language": body.language},
            result=result
        )
        return {**result, "task_id": task["id"]}
    except Exception as e:
        logger.exception("Code review failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Code review failed: {str(e)}")

# ==========================================
# 5. GitHub Assistant API
# ==========================================

@app.post("/api/github/inspect")
async def inspect_github_endpoint(body: GitHubInspectRequest):
    """Fetches public repository telemetry, root file tree, and recent commits."""
    try:
        result = await github_service.inspect_repository(body.url)
        task = save_task(
            module="github",
            title=f"Inspected {result['repository']}",
            description=body.url,
            language=result.get("language"),
            input_data={"url": body.url},
            result=result
        )
        return {**result, "task_id": task["id"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("GitHub inspect failed: %s", e)
        raise HTTPException(status_code=502, detail="Failed to connect to GitHub. Check your network connection.")

@app.post("/api/github")
async def github_endpoint_alias(body: GitHubInspectRequest):
    """Alias for /api/github/inspect supporting standard requests."""
    return await inspect_github_endpoint(body)

@app.post("/api/github/file")
async def fetch_github_file_endpoint(body: GitHubFileRequest):
    """Fetches specific file content from a public repository."""
    try:
        return await github_service.fetch_file_content(body.url, body.path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception("GitHub file fetch error: %s", e)
        raise HTTPException(status_code=502, detail="Unable to retrieve requested file from repository.")

@app.post("/api/github/readme")
async def fetch_github_readme_endpoint(body: GitHubInspectRequest):
    """Fetches repository README file."""
    try:
        return await github_service.fetch_readme(body.url)
    except Exception as e:
        logger.exception("GitHub readme fetch error: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch README.")

@app.post("/api/github/pulls")
async def fetch_github_pulls_endpoint(body: GitHubInspectRequest):
    """Fetches open pull requests and performs automated PR review analysis (read-only)."""
    try:
        return await github_service.fetch_pull_requests(body.url)
    except Exception as e:
        logger.exception("GitHub pulls fetch error: %s", e)
        raise HTTPException(status_code=502, detail="Failed to fetch Pull Requests.")

# ==========================================
# 6. Task History API
# ==========================================

@app.get("/api/history")
async def get_history_endpoint(
    module: Optional[str] = Query(None, description="Filter by module: generate, test, review, github"),
    search: Optional[str] = Query(None, description="Search keyword in title or description"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """Retrieves saved tasks from SQLite."""
    try:
        tasks = get_tasks(limit=limit, offset=offset, module=module, search=search)
        return tasks
    except Exception as e:
        logger.error("Error reading history: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve history.")

@app.get("/api/history/{task_id}")
async def get_single_history_endpoint(task_id: int):
    """Retrieves a single task by ID."""
    task = get_task_by_id(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found in local database.")
    return task

@app.delete("/api/history/{task_id}")
async def delete_history_endpoint(task_id: int):
    """Deletes a single task."""
    deleted = delete_task(task_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Task not found.")
    return {"deleted": True, "id": task_id}

@app.delete("/api/history")
async def clear_all_history_endpoint():
    """Clears all tasks from history."""
    count = clear_all_tasks()
    return {"cleared": True, "count": count}
