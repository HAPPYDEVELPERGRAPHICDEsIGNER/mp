"""
AI Code Reviewer Service.
Performs comprehensive multi-dimensional static code analysis across Python, JavaScript,
C++, and Java for security vulnerabilities, bugs, readability, and maintainability.
Optionally enhances analysis with an LLM when API keys are configured.
"""
import ast
import os
import re
import logging
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("copilot.code_reviewer")

def review_code(code: str, language: str) -> Dict[str, Any]:
    """
    Main review function. Executes deep rule-based static analysis
    and produces structured findings with severity, line numbers, and fixes.
    """
    cleaned_code = code.strip()
    if not cleaned_code:
        return {
            "mode": "STATIC CODE AUDIT",
            "score": 0,
            "grade": "F",
            "findings": [{
                "category": "Input Validation",
                "severity": "High",
                "line": 1,
                "title": "Empty Source Code",
                "explanation": "No code was provided for review. Please paste valid source code.",
                "suggested_fix": "# Paste your implementation here"
            }],
            "summary": "Source code is empty.",
            "metrics": {"total_lines": 0, "critical": 0, "high": 1, "medium": 0, "low": 0, "info": 0}
        }

    findings: List[Dict[str, Any]] = []

    # 1. Multi-language Common Security Checks
    _check_security(cleaned_code, language, findings)

    # 2. Language-Specific AST & Pattern Checks
    if language == "Python":
        _check_python(cleaned_code, findings)
    elif language == "JavaScript":
        _check_javascript(cleaned_code, findings)
    elif language == "C++":
        _check_cpp(cleaned_code, findings)
    elif language == "Java":
        _check_java(cleaned_code, findings)

    # 3. Readability & Maintainability Checks
    _check_maintainability(cleaned_code, findings)

    # 4. Compute Health Score
    score, grade, metrics = _calculate_score(findings, cleaned_code)

    mode_label = "LOCAL HEURISTIC ENGINE (OFFLINE/DEMO)"
    provider_note = "Rule-based static analyzer with AST and heuristic patterns."

    return {
        "mode": mode_label,
        "is_llm": False,
        "language": language,
        "score": score,
        "grade": grade,
        "metrics": metrics,
        "findings": findings,
        "summary": f"Analyzed {metrics['total_lines']} lines of {language}. Found {len(findings)} items across security, reliability, and code style.",
        "message": provider_note
    }

def _check_security(code: str, language: str, findings: List[Dict[str, Any]]):
    """Detects security vulnerabilities and secret leaks."""
    lines = code.splitlines()

    # Secret and API key detection
    secret_patterns = [
        (r"(?i)(api[_-]?key|secret|password|auth[_-]?token|private[_-]?key)\s*=\s*['\"][A-Za-z0-9_\-\.]{8,}['\"]",
         "Hardcoded Secret / Credential",
         "API keys or credentials hardcoded directly in source code will leak into version control.",
         "export API_KEY=...\n# Access via environment variable:\nos.environ.get('API_KEY')")
    ]

    for idx, line in enumerate(lines, start=1):
        for pattern, title, expl, fix in secret_patterns:
            if re.search(pattern, line):
                findings.append({
                    "category": "Security",
                    "severity": "Critical",
                    "line": idx,
                    "title": title,
                    "explanation": expl,
                    "suggested_fix": fix
                })

    # Dynamic execution (eval/exec)
    if re.search(r"\beval\s*\(|\bexec\s*\(", code):
        findings.append({
            "category": "Security",
            "severity": "Critical",
            "line": None,
            "title": "Unsafe Dynamic Code Execution (eval/exec)",
            "explanation": "eval() or exec() executes arbitrary code strings. An attacker supplying input can execute shell commands.",
            "suggested_fix": "Use safe parsing (e.g. ast.literal_eval, JSON.parse) instead of arbitrary evaluation."
        })

    # SQL Injection via string concatenation
    if re.search(r"(?i)(SELECT|INSERT|UPDATE|DELETE)\s+.*\s*(\+|%|\.format|\$)\s*", code):
        findings.append({
            "category": "Security",
            "severity": "High",
            "line": None,
            "title": "Potential SQL Injection Vulnerability",
            "explanation": "SQL query formed by string concatenation or interpolation allows malicious SQL statements to execute.",
            "suggested_fix": "Use parameterized queries (e.g., cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,)))"
        })

def _check_python(code: str, findings: List[Dict[str, Any]]):
    """Deep Python-specific AST and syntactic checks."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        findings.append({
            "category": "Bugs & Errors",
            "severity": "Critical",
            "line": e.lineno,
            "title": f"Python Syntax Error: {e.msg}",
            "explanation": "The code contains invalid Python syntax and cannot be parsed or executed.",
            "suggested_fix": "Fix the syntax at the highlighted line."
        })
        return

    # Check for bare except:
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                findings.append({
                    "category": "Bugs & Errors",
                    "severity": "High",
                    "line": node.lineno,
                    "title": "Bare 'except:' Clause",
                    "explanation": "Catching all exceptions without specification traps KeyboardInterrupt, SystemExit, and masks bugs.",
                    "suggested_fix": "except Exception as e:\n    logger.error('Failed: %s', e)"
                })

        # Mutable default argument (def foo(bar=[]))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for default in node.args.defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append({
                        "category": "Bugs & Errors",
                        "severity": "High",
                        "line": node.lineno,
                        "title": f"Mutable Default Argument in '{node.name}'",
                        "explanation": "Default list/dict values are instantiated once at definition time and shared across all calls.",
                        "suggested_fix": f"def {node.name}(..., param=None):\n    if param is None:\n        param = []"
                    })

            # Check if function has docstring
            if not ast.get_docstring(node):
                findings.append({
                    "category": "Readability",
                    "severity": "Low",
                    "line": node.lineno,
                    "title": f"Missing Docstring in '{node.name}'",
                    "explanation": "Documenting function purpose, arguments, and return types aids team maintainability.",
                    "suggested_fix": f'"""\\nSummary of {node.name}.\\n:param: ...\\n:return: ...\\n"""'
                })

def _check_javascript(code: str, findings: List[Dict[str, Any]]):
    """JavaScript specific pattern checks."""
    lines = code.splitlines()
    for idx, line in enumerate(lines, start=1):
        if re.search(r"[^=!]==[^=]", line):
            findings.append({
                "category": "Bugs & Errors",
                "severity": "Medium",
                "line": idx,
                "title": "Loose Equality Operator (==)",
                "explanation": "Using == triggers unintended type coercion (e.g. 0 == '' is true).",
                "suggested_fix": "Use strict equality === or !== instead."
            })
        if re.search(r"\bvar\s+\w+", line):
            findings.append({
                "category": "Maintainability",
                "severity": "Low",
                "line": idx,
                "title": "Use of 'var' Keyword",
                "explanation": "'var' is function-scoped and hoisted, often causing subtle variable leaking bugs.",
                "suggested_fix": "Use 'const' for immutable bindings or 'let' for reassignable variables."
            })
        if re.search(r"\.innerHTML\s*=", line):
            findings.append({
                "category": "Security",
                "severity": "High",
                "line": idx,
                "title": "Cross-Site Scripting (XSS) via innerHTML",
                "explanation": "Setting innerHTML directly with untrusted input allows execution of arbitrary script tags.",
                "suggested_fix": "Use element.textContent or element.innerText to safely inject text."
            })

def _check_cpp(code: str, findings: List[Dict[str, Any]]):
    """C++ specific memory safety and pattern checks."""
    if re.search(r"\b(strcpy|gets|strcat|sprintf)\s*\(", code):
        findings.append({
            "category": "Security",
            "severity": "Critical",
            "line": None,
            "title": "Dangerous Unbounded Buffer Function",
            "explanation": "Functions like strcpy or gets lack boundary bounds checking and cause buffer overflow vulnerabilities.",
            "suggested_fix": "Use std::string, strncpy_s, or std::snprintf."
        })
    if "new " in code and "delete " not in code and "unique_ptr" not in code and "shared_ptr" not in code:
        findings.append({
            "category": "Bugs & Errors",
            "severity": "High",
            "line": None,
            "title": "Potential Memory Leak (Unpaired 'new')",
            "explanation": "Raw heap allocation with 'new' without corresponding 'delete' leads to process memory leaks.",
            "suggested_fix": "Use RAII smart pointers: std::unique_ptr<T> or std::make_unique<T>()"
        })

def _check_java(code: str, findings: List[Dict[str, Any]]):
    """Java specific checks."""
    if re.search(r"\.equals\s*\(", code) and not re.search(r"Objects\.equals", code):
        findings.append({
            "category": "Bugs & Errors",
            "severity": "Medium",
            "line": None,
            "title": "Potential NullPointerException on .equals()",
            "explanation": "Invoking a.equals(b) when 'a' is null throws a NullPointerException.",
            "suggested_fix": "Use Objects.equals(a, b) or 'constant'.equals(variable)"
        })
    if re.search(r"catch\s*\(\s*Exception\s+\w+\s*\)\s*\{\s*\}", code):
        findings.append({
            "category": "Bugs & Errors",
            "severity": "High",
            "line": None,
            "title": "Empty Catch Block (Swallowed Exception)",
            "explanation": "Catching exceptions silently without logging or rethrowing conceals critical operational errors.",
            "suggested_fix": "logger.error('Operation failed', e); or throw new CustomException(e);"
        })

def _check_maintainability(code: str, findings: List[Dict[str, Any]]):
    """Checks code length, nesting depth, and general readability."""
    lines = code.splitlines()
    total_lines = len(lines)

    if total_lines > 150:
        findings.append({
            "category": "Maintainability",
            "severity": "Low",
            "line": None,
            "title": "Large File Length (>150 lines)",
            "explanation": "Long files often violate Single Responsibility Principle and become harder to test.",
            "suggested_fix": "Refactor into smaller, modular components."
        })

    # Check for long lines
    long_lines = [i for i, l in enumerate(lines, 1) if len(l) > 120]
    if len(long_lines) > 2:
        findings.append({
            "category": "Readability",
            "severity": "Low",
            "line": long_lines[0],
            "title": "Line Length Exceeds 120 Characters",
            "explanation": f"{len(long_lines)} lines exceed standard width conventions, hurting scannability on split screens.",
            "suggested_fix": "Wrap lines or break compound logic into descriptive intermediate variables."
        })

    # Check for deep indentation nesting (>4 levels)
    max_indent = 0
    max_line = 1
    for i, line in enumerate(lines, 1):
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if indent > max_indent:
                max_indent = indent
                max_line = i

    if max_indent >= 16:  # 4 levels of 4 spaces
        findings.append({
            "category": "Readability",
            "severity": "Medium",
            "line": max_line,
            "title": "Deep Control Flow Nesting",
            "explanation": "Deeply nested conditional blocks increase cognitive complexity and bug incidence.",
            "suggested_fix": "Use guard clauses and early returns (e.g. if (!valid) return;)."
        })

def _calculate_score(findings: List[Dict[str, Any]], code: str) -> tuple:
    """Calculates code quality score out of 100 and assigns a letter grade."""
    lines = max(1, len(code.splitlines()))
    base_score = 100

    crit = sum(1 for f in findings if f["severity"] == "Critical")
    high = sum(1 for f in findings if f["severity"] == "High")
    med = sum(1 for f in findings if f["severity"] == "Medium")
    low = sum(1 for f in findings if f["severity"] == "Low")
    info = sum(1 for f in findings if f["severity"] == "Info")

    # Penalty weights
    penalty = (crit * 30) + (high * 15) + (med * 8) + (low * 3)
    final_score = max(10, base_score - penalty)

    if final_score >= 90:
        grade = "A+"
    elif final_score >= 80:
        grade = "A"
    elif final_score >= 70:
        grade = "B"
    elif final_score >= 60:
        grade = "C"
    elif final_score >= 50:
        grade = "D"
    else:
        grade = "F"

    metrics = {
        "total_lines": lines,
        "critical": crit,
        "high": high,
        "medium": med,
        "low": low,
        "info": info
    }

    return final_score, grade, metrics
