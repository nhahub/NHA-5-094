"""Asynchronous object-storage boundary and local filesystem implementation."""
from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Protocol

from app.core.config import settings


class StorageError(RuntimeError):
    """Base exception for storage adapter failures."""


class StorageBackendUnavailable(StorageError):
    """Configured storage provider does not have an installed adapter."""


class StorageBackend(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str) -> str: ...
    async def download(self, reference: str) -> bytes: ...
    async def delete(self, reference: str) -> None: ...
    async def exists(self, reference: str) -> bool: ...


class LocalFileStorage:
    """Store object bytes outside PostgreSQL under a contained local root."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, reference: str) -> Path:
        if not reference or "\\" in reference:
            raise StorageError("Storage reference is invalid.")
        key = PurePosixPath(reference)
        if key.is_absolute() or any(part in ("", ".", "..") for part in key.parts):
            raise StorageError("Storage reference is invalid.")
        target = (self.root / Path(*key.parts)).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Storage reference escapes the configured storage root.") from exc
        return target

    async def upload(self, key: str, data: bytes, content_type: str) -> str:
        del content_type  # MIME metadata is stored in PostgreSQL, not the object key.
        target = self._resolve(key)
        await asyncio.to_thread(self._write_atomic, target, data)
        return key

    @staticmethod
    def _write_atomic(target: Path, data: bytes) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".upload-", delete=False) as temp:
                temporary_path = temp.name
                temp.write(data)
                temp.flush()
                os.fsync(temp.fileno())
            os.replace(temporary_path, target)
        finally:
            if temporary_path and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    async def download(self, reference: str) -> bytes:
        target = self._resolve(reference)
        try:
            return await asyncio.to_thread(target.read_bytes)
        except FileNotFoundError as exc:
            raise StorageError("Stored object was not found.") from exc

    async def delete(self, reference: str) -> None:
        target = self._resolve(reference)
        try:
            await asyncio.to_thread(target.unlink)
        except FileNotFoundError:
            return

    async def exists(self, reference: str) -> bool:
        target = self._resolve(reference)
        return await asyncio.to_thread(target.is_file)


def get_storage_backend() -> StorageBackend:
    """Build the configured adapter; deployment-specific adapters can replace this factory."""
    backend = settings.STORAGE_BACKEND.strip().lower()
    if backend != "local":
        raise StorageBackendUnavailable(
            f"Storage backend '{backend}' is configured but no adapter is installed."
        )
    root = Path(settings.STORAGE_LOCAL_PATH).expanduser()
    if not root.is_absolute():
        module_path = Path(__file__).resolve()
        repository_root = module_path.parents[4]
        application_root = module_path.parents[3]
        # In source checkouts, keep data beside backend; in Docker, the app root is /app.
        base = repository_root if (repository_root / "backend").is_dir() else application_root
        root = base / root
    return LocalFileStorage(root)


__all__ = [
    "LocalFileStorage",
    "StorageBackend",
    "StorageBackendUnavailable",
    "StorageError",
    "get_storage_backend",
]
