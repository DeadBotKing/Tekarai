"""Bounded, read-only Git intelligence adapter."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


class ReadOnlyGitReader:
    def _run(self, workspace: Path, *args: str) -> str:
        try:
            done = subprocess.run(
                ["git", "-C", str(workspace), *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            )
            return done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    def inspect(self, workspace: Path) -> dict[str, Any]:
        head = self._run(workspace, "rev-parse", "HEAD")
        branch = self._run(workspace, "branch", "--show-current")
        count = self._run(workspace, "rev-list", "--count", "HEAD") if head else "0"
        porcelain = self._run(workspace, "status", "--porcelain=v1")
        changes = []
        for line in porcelain.splitlines():
            if len(line) >= 4:
                changes.append({"status": line[:2].strip(), "path": line[3:]})
        contributors = [
            x for x in self._run(workspace, "shortlog", "-sne", "HEAD").splitlines() if x
        ][:50]
        recent = [
            x
            for x in self._run(
                workspace, "log", "-20", "--pretty=format:%H%x09%aI%x09%an%x09%s"
            ).splitlines()
            if x
        ]
        commitFrequency: dict[str, int] = {}
        for item in recent:
            parts = item.split("\t")
            if len(parts) > 1:
                day = parts[1][:10]
                commitFrequency[day] = commitFrequency.get(day, 0) + 1
        names = self._run(workspace, "log", "-100", "--name-only", "--pretty=format:")
        freq: dict[str, int] = {}
        for name in names.splitlines():
            if name.strip():
                freq[name.strip()] = freq.get(name.strip(), 0) + 1
        return {
            "available": bool(head),
            "branch": branch,
            "commit": head,
            "commitCount": int(count or 0),
            "changes": changes,
            "modifiedFiles": [x["path"] for x in changes if "M" in x["status"]],
            "addedFiles": [x["path"] for x in changes if "A" in x["status"] or x["status"] == "??"],
            "deletedFiles": [x["path"] for x in changes if "D" in x["status"]],
            "renamedFiles": [x["path"] for x in changes if "R" in x["status"]],
            "contributors": contributors,
            "recentChanges": recent,
            "commitFrequency": dict(sorted(commitFrequency.items())),
            "hotFiles": [
                {"path": k, "changes": v}
                for k, v in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:20]
            ],
        }
