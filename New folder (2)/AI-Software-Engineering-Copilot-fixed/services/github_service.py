"""
GitHub Assistant Service.
Safely queries the public GitHub REST API for repository inspection, file viewing,
README retrieval, commit history, and read-only Pull Request review analysis.
Supports optional server-side GITHUB_TOKEN for elevated rate limits.
"""
import os
import re
import json
import base64
import logging
from urllib.parse import urlparse
from typing import Dict, Any, Tuple, Optional, List
import httpx

logger = logging.getLogger("copilot.github_service")

GITHUB_API_BASE = "https://api.github.com"

def parse_repo_url(url: str) -> Tuple[str, str]:
    """Validates and extracts owner and repository name from GitHub URL."""
    cleaned = url.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("https", "http") or parsed.netloc not in ("github.com", "www.github.com"):
        raise ValueError("Invalid URL format. Please provide a valid GitHub repository URL (e.g., https://github.com/owner/repository).")

    parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(parts) < 2 or any(p in (".", "..") for p in parts[:2]):
        raise ValueError("Repository URL must contain both an owner/organization and repository name.")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    if not re.match(r"^[A-Za-z0-9_.\-]+$", owner) or not re.match(r"^[A-Za-z0-9_.\-]+$", repo):
        raise ValueError("Owner and repository name contain invalid characters.")

    return owner, repo

def _get_headers() -> Dict[str, str]:
    """Prepares safe request headers with optional server-side token."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "AI-Software-Engineering-Copilot"
    }
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

async def inspect_repository(url: str) -> Dict[str, Any]:
    """
    Fetches repository metadata, root file structure, and recent commits
    via GitHub REST API.
    """
    owner, repo = parse_repo_url(url)
    headers = _get_headers()

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        # 1. Fetch Repo Metadata
        repo_resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers)
        _check_status(repo_resp)
        meta = repo_resp.json()

        # 2. Fetch Root Directory Contents
        contents_resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents", headers=headers)
        files = []
        if contents_resp.status_code == 200:
            raw_contents = contents_resp.json()
            if isinstance(raw_contents, list):
                # Sort: directories first, then files alphabetically
                sorted_items = sorted(raw_contents, key=lambda x: (0 if x.get("type") == "dir" else 1, x.get("name", "").lower()))
                for item in sorted_items[:40]:
                    files.append({
                        "name": item.get("name"),
                        "path": item.get("path"),
                        "type": item.get("type"),
                        "size": item.get("size", 0),
                        "download_url": item.get("download_url")
                    })

        # 3. Fetch Recent Commits
        commits = []
        commits_resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits?per_page=5", headers=headers)
        if commits_resp.status_code == 200:
            raw_commits = commits_resp.json()
            if isinstance(raw_commits, list):
                for c in raw_commits:
                    commit_data = c.get("commit", {})
                    author_data = commit_data.get("author", {})
                    commits.append({
                        "sha": c.get("sha", "")[:7],
                        "message": commit_data.get("message", "").split("\n")[0][:100],
                        "author": author_data.get("name", "Unknown"),
                        "date": author_data.get("date", "")
                    })

    license_info = meta.get("license") or {}
    return {
        "mode": "PUBLIC GITHUB REST API",
        "repository": meta.get("full_name"),
        "name": meta.get("name"),
        "owner": owner,
        "description": meta.get("description") or "No description provided.",
        "html_url": meta.get("html_url"),
        "stars": meta.get("stargazers_count", 0),
        "forks": meta.get("forks_count", 0),
        "open_issues": meta.get("open_issues_count", 0),
        "language": meta.get("language") or "Mixed",
        "license": license_info.get("spdx_id") or "None",
        "default_branch": meta.get("default_branch", "main"),
        "topics": meta.get("topics", []),
        "files": files,
        "recent_commits": commits,
        "message": f"Successfully retrieved public repository telemetry for '{owner}/{repo}'."
    }

async def fetch_file_content(url: str, file_path: str) -> Dict[str, Any]:
    """Fetches and decodes source code of a specific file."""
    owner, repo = parse_repo_url(url)
    headers = _get_headers()

    clean_path = file_path.strip("/")
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{clean_path}", headers=headers)
        _check_status(resp)
        data = resp.json()

    if data.get("type") != "file":
        raise ValueError(f"Target '{clean_path}' is a directory, not a file.")

    raw_content = data.get("content", "")
    encoding = data.get("encoding", "base64")

    if encoding == "base64":
        decoded_text = base64.b64decode(raw_content).decode("utf-8", errors="replace")
    else:
        decoded_text = raw_content

    # Cap display text at 200KB for frontend performance
    truncated = len(decoded_text) > 200_000
    display_content = decoded_text[:200_000]

    return {
        "name": data.get("name"),
        "path": data.get("path"),
        "size": data.get("size", 0),
        "content": display_content,
        "truncated": truncated
    }

async def fetch_readme(url: str) -> Dict[str, Any]:
    """Fetches repository README file if present."""
    owner, repo = parse_repo_url(url)
    headers = _get_headers()

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/readme", headers=headers)
        if resp.status_code == 404:
            return {"found": False, "content": "No README.md found in this repository."}
        _check_status(resp)
        data = resp.json()

    raw_content = data.get("content", "")
    decoded_text = base64.b64decode(raw_content).decode("utf-8", errors="replace")
    return {"found": True, "content": decoded_text[:100_000]}

async def fetch_pull_requests(url: str) -> Dict[str, Any]:
    """
    Fetches open pull requests and performs automated read-only PR review analysis.
    NEVER merges or pushes changes.
    """
    owner, repo = parse_repo_url(url)
    headers = _get_headers()

    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        resp = await client.get(f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls?state=open&per_page=6", headers=headers)
        _check_status(resp)
        raw_pulls = resp.json()

    pull_requests = []
    for pr in raw_pulls:
        user_info = pr.get("user") or {}
        pr_number = pr.get("number")
        title = pr.get("title", "")
        body = pr.get("body") or "No description provided."

        # Read-only automated review analysis
        review_checklist = _generate_pr_review_checklist(title, body)

        pull_requests.append({
            "number": pr_number,
            "title": title,
            "author": user_info.get("login", "Unknown"),
            "author_avatar": user_info.get("avatar_url", ""),
            "html_url": pr.get("html_url"),
            "created_at": pr.get("created_at"),
            "head_branch": pr.get("head", {}).get("ref"),
            "base_branch": pr.get("base", {}).get("ref"),
            "body_snippet": body[:300],
            "review_analysis": review_checklist
        })

    return {
        "repository": f"{owner}/{repo}",
        "pull_requests_count": len(pull_requests),
        "pull_requests": pull_requests,
        "message": "PR review analysis performed in safe read-only mode. No repository modifications allowed."
    }

def _generate_pr_review_checklist(title: str, body: str) -> Dict[str, Any]:
    """Generates an intelligent automated review checklist for a pull request."""
    has_test_mention = bool(re.search(r"(?i)(test|spec|assert|coverage)", title + " " + body))
    has_issue_link = bool(re.search(r"(?i)(fixes|closes|resolves|#\d+)", body))
    has_docs = bool(re.search(r"(?i)(doc|readme|guide)", title + " " + body))
    is_breaking = bool(re.search(r"(?i)(breaking|deprecat)", title + " " + body))

    checklist = [
        {"item": "PR Title and Description Clarity", "status": "Pass" if len(title) > 8 else "Warning", "note": "Descriptive title provided"},
        {"item": "Automated Testing Coverage", "status": "Pass" if has_test_mention else "Needs Verification", "note": "Verify test cases are included in diff"},
        {"item": "Issue Tracking Link", "status": "Pass" if has_issue_link else "Info", "note": "Linked issue reference found" if has_issue_link else "No explicit issue link found"},
        {"item": "Documentation Updates", "status": "Pass" if has_docs else "Info", "note": "Documentation changes indicated" if has_docs else "Check if user docs require updates"},
        {"item": "Breaking Changes Risk", "status": "Caution" if is_breaking else "Low Risk", "note": "Potential breaking change flagged" if is_breaking else "No breaking changes indicated in description"}
    ]

    return {
        "checklist": checklist,
        "recommended_verdict": "Requires Manual Code Verification" if not has_test_mention else "Ready for Review"
    }

def _check_status(resp: httpx.Response):
    """Translates HTTP error codes to helpful user-facing errors."""
    if resp.status_code == 200:
        return
    if resp.status_code == 403:
        rate_limit_reset = resp.headers.get("x-ratelimit-reset")
        raise RuntimeError("GitHub API rate limit exceeded (60 requests/hr for unauthenticated IP). Configure GITHUB_TOKEN in .env for up to 5,000 requests/hr.")
    if resp.status_code == 404:
        raise RuntimeError("Repository not found or is private. Verify the URL is public and spelled correctly.")
    raise RuntimeError(f"GitHub API returned error HTTP {resp.status_code}: {resp.text[:120]}")
