"""
Codebase Intelligence Service for AI Software Engineering Copilot (Gemini Edition).
Scans local repositories, extracts symbols and AST structures, creates chunks,
builds vector/token embeddings, and performs grounded Q&A with Gemini.
"""
import ast
import json
import math
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

from database import models
from services import gemini_service

logger = logging.getLogger("copilot.codebase")

# Directories to exclude from indexing
EXCLUDED_DIRS = {
    ".git", ".github", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".idea", ".vscode",
    ".gemini", "dist", "build", "eggs", "bin", "obj", ".tox"
}

# Sensitive / ignored files
EXCLUDED_FILES = {
    ".env", ".env.local", ".env.production", ".DS_Store", "Thumbs.db",
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock"
}

# Permitted source code extensions
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css",
    ".json", ".md", ".sql", ".sh", ".yml", ".yaml", ".ini",
    ".cfg", ".toml", ".java", ".cpp", ".c", ".h", ".cs",
    ".go", ".rs", ".dart", ".txt"
}

MAX_FILE_SIZE_BYTES = 512 * 1024  # 500 KB limit per file

def validate_project_path(raw_path: str) -> Path:
    """
    Validates the directory path to ensure it exists, is a directory,
    and prevents dangerous root indexing or directory traversal.
    """
    if not raw_path or not raw_path.strip():
        raise ValueError("Project path cannot be empty.")

    p = Path(raw_path.strip()).resolve()
    if not p.exists():
        raise ValueError(f"Specified path does not exist: {p}")
    if not p.is_dir():
        raise ValueError(f"Specified path is a file, not a directory: {p}")

    # Prevent indexing system roots on Windows or Unix
    root_parts = p.parts
    if len(root_parts) <= 1 or (len(root_parts) == 2 and root_parts[0].endswith(":\\") and root_parts[1].lower() in ["windows", "program files"]):
        raise ValueError(f"Indexing system directories is disallowed for safety: {p}")

    return p

def is_binary_file(file_path: Path) -> bool:
    """Checks if file contains null bytes or binary characters."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            if b"\x00" in chunk:
                return True
        return False
    except Exception:
        return True

def extract_python_ast(code: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Parses Python source code with ast to extract classes, functions,
    methods, line ranges, docstrings, and imported modules.
    """
    symbols = []
    imports = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return symbols, imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}")

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node) or ""
            symbols.append({
                "type": "function",
                "name": node.name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "docstring": doc.strip()
            })
        elif isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node) or ""
            class_methods = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    class_methods.append(item.name)
            symbols.append({
                "type": "class",
                "name": node.name,
                "start_line": node.lineno,
                "end_line": getattr(node, "end_lineno", node.lineno),
                "docstring": doc.strip(),
                "methods": class_methods
            })

    return symbols, sorted(list(set(imports)))

def extract_generic_symbols(code: str, ext: str) -> List[Dict[str, Any]]:
    """Regex fallback for JS, TS, Java, Go, etc."""
    symbols = []
    lines = code.splitlines()

    # Function patterns
    fn_pattern = re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(")
    class_pattern = re.compile(r"^\s*(?:export\s+)?class\s+([A-Za-z0-9_]+)")

    for idx, line in enumerate(lines, start=1):
        fn_match = fn_pattern.search(line)
        if fn_match:
            symbols.append({
                "type": "function",
                "name": fn_match.group(1),
                "start_line": idx,
                "end_line": min(idx + 30, len(lines)),
                "docstring": ""
            })
            continue

        class_match = class_pattern.search(line)
        if class_match:
            symbols.append({
                "type": "class",
                "name": class_match.group(1),
                "start_line": idx,
                "end_line": min(idx + 50, len(lines)),
                "docstring": ""
            })

    return symbols

def _tokenize(text: str) -> List[str]:
    """Extracts alphanumeric words from code/text for offline token vectors."""
    return [w.lower() for w in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text)]

def _compute_token_vector(text: str) -> Dict[str, float]:
    """Generates a normalized term-frequency sparse vector for pure-Python similarity."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0.0) + 1.0

    length = math.sqrt(sum(v * v for v in tf.values()))
    if length > 0:
        for k in tf:
            tf[k] /= length
    return tf

def _cosine_sparse(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """Computes cosine similarity between two normalized sparse term vectors."""
    if not vec1 or not vec2:
        return 0.0
    # Iterate over smaller dict
    if len(vec1) > len(vec2):
        vec1, vec2 = vec2, vec1
    score = 0.0
    for k, v in vec1.items():
        if k in vec2:
            score += v * vec2[k]
    return score

def _cosine_dense(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two dense float embedding vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def chunk_file(file_path: Path, rel_path: str, content: str) -> List[Dict[str, Any]]:
    """Breaks a source file into logical chunks (by symbol or sliding window)."""
    chunks = []
    lines = content.splitlines()
    total_lines = len(lines)
    ext = file_path.suffix.lower()

    if ext == ".py":
        symbols, imports = extract_python_ast(content)
    else:
        symbols = extract_generic_symbols(content, ext)
        imports = []

    # File overview chunk
    overview_text = f"File: {rel_path}\nTotal Lines: {total_lines}\n"
    if imports:
        overview_text += f"Imports: {', '.join(imports[:15])}\n"
    if symbols:
        sym_names = [f"{s['type']} {s['name']}" for s in symbols[:15]]
        overview_text += f"Key Symbols: {', '.join(sym_names)}\n"
    header_preview = "\n".join(lines[:30])
    overview_text += f"Preview:\n{header_preview}"

    chunks.append({
        "file_path": rel_path,
        "chunk_id": f"{rel_path}#overview",
        "symbol_type": "file_overview",
        "name": file_path.name,
        "start_line": 1,
        "end_line": min(30, total_lines),
        "content": overview_text
    })

    # Symbol chunks
    for s in symbols:
        start = max(1, s["start_line"])
        end = min(total_lines, s["end_line"])
        symbol_code = "\n".join(lines[start - 1:end])
        chunks.append({
            "file_path": rel_path,
            "chunk_id": f"{rel_path}#{s['name']}:L{start}-L{end}",
            "symbol_type": s["type"],
            "name": s["name"],
            "start_line": start,
            "end_line": end,
            "content": f"# File: {rel_path}:{start}-{end} ({s['type']} {s['name']})\n{symbol_code}"
        })

    # If no symbols found and file is moderately sized, use window chunks
    if not symbols and total_lines > 10:
        window_size = 50
        overlap = 10
        step = max(1, window_size - overlap)
        for i in range(0, total_lines, step):
            chunk_lines = lines[i:i + window_size]
            start = i + 1
            end = min(total_lines, i + len(chunk_lines))
            chunks.append({
                "file_path": rel_path,
                "chunk_id": f"{rel_path}:L{start}-L{end}",
                "symbol_type": "window",
                "name": f"{file_path.name}:L{start}",
                "start_line": start,
                "end_line": end,
                "content": f"# File: {rel_path}:{start}-{end}\n" + "\n".join(chunk_lines)
            })
            if end >= total_lines:
                break

    return chunks

class CodebaseService:
    """Manages repository scanning, indexing, vector search, and grounded Q&A."""

    def __init__(self):
        self.gemini = gemini_service

    def scan_and_index(self, project_path_str: str) -> Dict[str, Any]:
        """
        Scans a directory, parses files into chunks, creates embeddings,
        and saves everything into SQLite for persistent retrieval.
        """
        project_path = validate_project_path(project_path_str)
        project_norm = str(project_path)
        project_name = project_path.name

        logger.info("Scanning codebase at: %s", project_norm)

        scanned_files = []
        all_chunks = []
        total_symbols = 0

        # Traverse directory
        for p in project_path.rglob("*"):
            # Exclude directory matches in path
            if any(part in EXCLUDED_DIRS for part in p.parts):
                continue
            if p.is_dir():
                continue
            if p.name in EXCLUDED_FILES or p.name.startswith("."):
                continue
            if p.suffix.lower() not in ALLOWED_EXTENSIONS:
                continue

            # Size check
            try:
                st = p.stat()
                if st.st_size > MAX_FILE_SIZE_BYTES or st.st_size == 0:
                    continue
            except OSError:
                continue

            # Binary check
            if is_binary_file(p):
                continue

            rel_path = str(p.relative_to(project_path)).replace("\\", "/")
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning("Could not read file %s: %s", p, e)
                continue

            file_chunks = chunk_file(p, rel_path, content)
            for c in file_chunks:
                if c["symbol_type"] in ("function", "class"):
                    total_symbols += 1
            all_chunks.extend(file_chunks)
            scanned_files.append(rel_path)

        # Generate embeddings (dense Gemini if available, sparse token vector fallback)
        has_api_key = self.gemini.is_configured()
        for chunk in all_chunks:
            embedding = None
            if has_api_key:
                try:
                    # Attempt Gemini embedding
                    embedding = self.gemini.generate_embedding(chunk["content"][:2000])
                except Exception as ex:
                    logger.debug("Gemini embedding fallback for chunk %s: %s", chunk["chunk_id"], ex)

            if not embedding:
                # Sparse token vector representation for reliable offline similarity
                embedding = {"sparse": _compute_token_vector(chunk["content"])}

            chunk["embedding"] = embedding

        # Persist to database
        models.save_codebase_project(
            path=project_norm,
            name=project_name,
            file_count=len(scanned_files),
            total_symbols=total_symbols,
            total_chunks=len(all_chunks)
        )
        models.save_codebase_chunks(project_norm, all_chunks)

        return {
            "project_path": project_norm,
            "project_name": project_name,
            "file_count": len(scanned_files),
            "total_symbols": total_symbols,
            "total_chunks": len(all_chunks),
            "scanned_files": scanned_files[:50],  # sample
            "gemini_embeddings_enabled": has_api_key
        }

    def get_project_status(self, project_path_str: str) -> Optional[Dict[str, Any]]:
        """Checks if a project has already been indexed."""
        try:
            p = validate_project_path(project_path_str)
            return models.get_codebase_project(str(p))
        except Exception:
            return None

    def query_codebase(
        self,
        project_path_str: str,
        query: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves top relevant code chunks and generates a grounded response.
        If Gemini API key is missing, provides an offline structured reference summary.
        """
        project_path = validate_project_path(project_path_str)
        project_norm = str(project_path)

        project_meta = models.get_codebase_project(project_norm)
        if not project_meta:
            # Auto-index if not yet indexed
            self.scan_and_index(project_norm)

        chunks = models.get_codebase_chunks(project_norm)
        if not chunks:
            return {
                "answer": "No indexed code chunks found for this project.",
                "relevant_chunks": [],
                "ai_generated": False
            }

        # Retrieve top relevant chunks
        ranked_chunks = self._rank_chunks(query, chunks, top_k=5)

        # Grounded context construction
        context_blocks = []
        for c in ranked_chunks:
            context_blocks.append(
                f"--- File: {c['file_path']} (lines {c['start_line']}-{c['end_line']}) [{c['symbol_type']} {c['name']}] ---\n"
                f"{c['content']}"
            )
        context_str = "\n\n".join(context_blocks)

        if not self.gemini.is_configured():
            # Honest offline fallback
            snippets_summary = []
            for c in ranked_chunks:
                snippets_summary.append(
                    f"• `{c['file_path']}` (Lines {c['start_line']}-{c['end_line']}) — {c['symbol_type']}: **{c['name']}**"
                )
            answer = (
                "**[Offline Mode - Gemini API Key Required for AI Synthesis]**\n\n"
                f"Your query **\"{query}\"** retrieved {len(ranked_chunks)} relevant code reference(s) from the indexed codebase:\n\n"
                + "\n".join(snippets_summary) + "\n\n"
                "To get deep semantic synthesis and full code explanations from Gemini, "
                "configure `GEMINI_API_KEY` in your `.env` file."
            )
            return {
                "answer": answer,
                "relevant_chunks": ranked_chunks,
                "ai_generated": False,
                "model_used": None
            }

        # Formulate grounded prompt for Gemini
        system_instruction = (
            "You are an expert AI Software Engineering Architect analyzing a codebase. "
            "Answer the developer's question grounded strictly in the provided code snippets. "
            "Always cite the exact file path and line numbers when referencing code. "
            "If the snippets do not contain enough information to answer definitively, state what is known and what is missing."
        )

        prompt = f"""### Grounded Codebase Context:
{context_str}

### Developer Question:
{query}

Provide a concise, high-quality, architect-level explanation with code references and file citations."""

        result = self.gemini.generate_content(
            prompt=prompt,
            model=model,
            system_instruction=system_instruction,
            temperature=0.2
        )

        return {
            "answer": result.get("text", ""),
            "relevant_chunks": ranked_chunks,
            "ai_generated": True,
            "model_used": result.get("model")
        }

    def trace_architecture(self, project_path_str: str) -> Dict[str, Any]:
        """
        Extracts key modules, entry points, and dependency relationships from the codebase.
        """
        project_path = validate_project_path(project_path_str)
        project_norm = str(project_path)

        chunks = models.get_codebase_chunks(project_norm)
        if not chunks:
            self.scan_and_index(project_norm)
            chunks = models.get_codebase_chunks(project_norm)

        file_summaries = {}
        entry_points = []
        classes_found = []
        functions_found = []

        for c in chunks:
            f = c["file_path"]
            if f not in file_summaries:
                file_summaries[f] = {"functions": 0, "classes": 0}
            if c["symbol_type"] == "function":
                file_summaries[f]["functions"] += 1
                functions_found.append(f"{f}:{c['name']}")
                if c["name"] in ("main", "app", "cli", "run"):
                    entry_points.append(f"{f} -> {c['name']}")
            elif c["symbol_type"] == "class":
                file_summaries[f]["classes"] += 1
                classes_found.append(f"{f}:{c['name']}")

        # Common main files
        for f in file_summaries:
            base = Path(f).name.lower()
            if base in ("main.py", "app.py", "index.js", "server.js", "manage.py", "wsgi.py", "asgi.py"):
                if f not in entry_points:
                    entry_points.insert(0, f)

        return {
            "project_path": project_norm,
            "total_files": len(file_summaries),
            "entry_points": entry_points[:10],
            "total_classes": len(classes_found),
            "total_functions": len(functions_found),
            "top_modules": sorted(file_summaries.items(), key=lambda x: (x[1]["classes"] + x[1]["functions"]), reverse=True)[:15]
        }

    def _rank_chunks(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        """Ranks chunks using hybrid search (exact symbol match + vector/token similarity)."""
        query_tokens = _tokenize(query)
        query_sparse = _compute_token_vector(query)

        query_dense = None
        if self.gemini.is_configured():
            try:
                query_dense = self.gemini.generate_embedding(query)
            except Exception:
                query_dense = None

        scored = []
        for c in chunks:
            emb = c.get("embedding")
            sim = 0.0

            # 1. Dense cosine if both query and chunk have float vectors
            if query_dense and isinstance(emb, list) and len(emb) == len(query_dense):
                sim = _cosine_dense(query_dense, emb)
            # 2. Sparse token cosine fallback
            elif isinstance(emb, dict) and "sparse" in emb:
                sim = _cosine_sparse(query_sparse, emb["sparse"])
            elif isinstance(emb, list) and not query_dense:
                # Chunk has dense vector but query couldn't generate one: compute sparse from chunk content
                chunk_sparse = _compute_token_vector(c["content"])
                sim = _cosine_sparse(query_sparse, chunk_sparse)

            # 3. Boost for exact symbol name or file path match
            name = (c.get("name") or "").lower()
            fpath = (c.get("file_path") or "").lower()
            bonus = 0.0
            for t in query_tokens:
                if t == name:
                    bonus += 0.35
                elif t in fpath:
                    bonus += 0.15

            total_score = sim + bonus
            scored.append((total_score, c))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]

# Singleton service instance
codebase_service = CodebaseService()
