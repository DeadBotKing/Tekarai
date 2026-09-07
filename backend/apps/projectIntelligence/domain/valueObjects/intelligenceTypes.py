"""Framework-independent Project Intelligence types and integrity rules."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

PROJECT_STATES = ("INITIALIZING", "SCANNING", "ANALYZING", "READY", "CHANGED", "STALE", "ERROR")
SEVERITIES = ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL")
DECISIONS = ("ACCEPT", "REJECT", "DEFER", "REVIEW_REQUIRED")
JOB_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
ANALYSIS_STATUSES = ("RUNNING", "COMPLETED", "PARTIAL", "FAILED")
IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
        "coverage",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        "target",
        "projectIntelligenceArtifacts",
    }
)
TEMP_SUFFIXES = (".tmp", ".temp", ".swp", "~")
GENERATED_SUFFIXES = (".min.js", ".min.css", ".map", ".pyc", ".lock")
LANGUAGES = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".html": "HTML",
    ".css": "CSS",
    ".sql": "SQL",
    ".ps1": "PowerShell",
    ".cs": "C#",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".sh": "Shell",
}
SECRET_NAMES = re.compile(
    r"(^|[._-])(secret|password|credential|private[_-]?key|token)([._-]|$)", re.I
)


def canonicalJson(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def integrityHash(value: Any) -> str:
    return hashlib.sha256(canonicalJson(value).encode()).hexdigest()


def requireChoice(value: str, choices: tuple[str, ...], field: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in choices:
        raise ValidationFailedError(
            f"Invalid {field}.", fieldErrors={field: f"expected one of {choices}"}
        )
    return normalized


def safeRelativePath(value: str) -> str:
    supplied = value.replace("\\", "/").strip()
    if supplied.startswith(("~", "/")) or re.match(r"^[A-Za-z]:", supplied):
        raise ValidationFailedError("Workspace path escapes the configured boundary.")
    raw = supplied or "."
    path = PurePosixPath(raw)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationFailedError("Workspace path escapes the configured boundary.")
    return "." if str(path) == "." else str(path)


def safeTask(value: str, maxLength: int = 2000) -> str:
    task = str(value).strip()
    if not task or len(task) > maxLength:
        raise ValidationFailedError("Task is required and must be at most 2000 characters.")
    return task
