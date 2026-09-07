"""Read-only, symlink-safe workspace scanner."""

from __future__ import annotations

import hashlib
import mimetypes
import os
from pathlib import Path
from typing import Any

from apps.projectIntelligence.domain.valueObjects.intelligenceTypes import (
    GENERATED_SUFFIXES,
    IGNORED_DIRECTORIES,
    SECRET_NAMES,
    TEMP_SUFFIXES,
    safeRelativePath,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


class SecureWorkspaceReader:
    def __init__(self, root: Path, maxFiles: int = 50000, maxFileBytes: int = 2_000_000) -> None:
        self.root = root.resolve()
        self.maxFiles = maxFiles
        self.maxFileBytes = maxFileBytes

    def resolve(self, relativePath: str) -> Path:
        candidate = (self.root / safeRelativePath(relativePath)).resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValidationFailedError("Workspace is outside the configured root.") from exc
        if not candidate.is_dir():
            raise ValidationFailedError("Workspace does not exist or is not a directory.")
        return candidate

    def scan(
        self, relativePath: str, previousFiles: tuple[dict[str, Any], ...] = ()
    ) -> tuple[dict[str, Any], ...]:
        base = self.resolve(relativePath)
        previous = {item["path"]: item for item in previousFiles}
        records = []
        for current, dirs, files in os.walk(base, followlinks=False):
            currentPath = Path(current)
            dirs[:] = sorted(
                d
                for d in dirs
                if d not in IGNORED_DIRECTORIES and not (currentPath / d).is_symlink()
            )
            for name in sorted(files):
                path = currentPath / name
                if path.is_symlink():
                    continue
                try:
                    resolved = path.resolve()
                    resolved.relative_to(base)
                    stat = resolved.stat()
                except (OSError, ValueError):
                    continue
                rel = resolved.relative_to(base).as_posix()
                prior = previous.get(rel)
                if (
                    prior
                    and prior.get("size") == stat.st_size
                    and prior.get("modifiedNs") == stat.st_mtime_ns
                ):
                    records.append(dict(prior))
                    if len(records) > self.maxFiles:
                        raise ValidationFailedError("Workspace exceeds the configured file limit.")
                    continue
                suffix = resolved.suffix.lower()
                ignored = any(p in IGNORED_DIRECTORIES for p in Path(rel).parts)
                temporary = name.endswith(TEMP_SUFFIXES)
                generated = name.endswith(GENERATED_SUFFIXES)
                secretNamed = (
                    bool(SECRET_NAMES.search(name))
                    or name.lower().startswith(".env")
                    or name.lower()
                    in {
                        "id_rsa",
                        "id_dsa",
                        "id_ed25519",
                        "credentials.json",
                    }
                )
                binary = self._binary(resolved)
                digest = self._hash(resolved)
                content = ""
                if (
                    not binary
                    and not ignored
                    and not secretNamed
                    and stat.st_size <= self.maxFileBytes
                ):
                    try:
                        content = resolved.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        content = ""
                if any(
                    marker in content
                    for marker in (
                        "-----BEGIN PRIVATE KEY-----",
                        "-----BEGIN RSA PRIVATE KEY-----",
                        "-----BEGIN OPENSSH PRIVATE KEY-----",
                    )
                ):
                    secretNamed = True
                    content = ""
                records.append(
                    {
                        "path": rel,
                        "name": name,
                        "extension": suffix,
                        "size": stat.st_size,
                        "modifiedNs": stat.st_mtime_ns,
                        "hash": digest,
                        "binary": binary,
                        "generated": generated,
                        "ignored": ignored,
                        "temporary": temporary,
                        "secretNamed": secretNamed,
                        "mime": mimetypes.guess_type(name)[0] or "",
                        "loc": 0 if binary else content.count("\n") + (1 if content else 0),
                        "content": content,
                    }
                )
                if len(records) > self.maxFiles:
                    raise ValidationFailedError("Workspace exceeds the configured file limit.")
        return tuple(records)

    def _hash(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(131072), b""):
                digest.update(block)
        return digest.hexdigest()

    def _binary(self, path: Path) -> bool:
        try:
            sample = path.open("rb").read(4096)
            return b"\0" in sample
        except OSError:
            return True
