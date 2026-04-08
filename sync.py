"""Sync providers for vault synchronization."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

ALLOWED_SYNC_PROVIDERS: set[str] = {"obsidian", "dropbox"}


class SyncProvider(ABC):
    """Base class for vault sync providers."""

    @abstractmethod
    async def upload_file(self, local_path: Path, remote_path: str) -> None:
        """Upload a single file to the remote vault."""

    @abstractmethod
    async def start(self) -> None:
        """Initialize the provider."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown."""


class ObsidianSyncProvider(SyncProvider):
    """No-op provider. Obsidian Sync is managed by supervisord."""

    async def upload_file(self, local_path: Path, remote_path: str) -> None:
        pass

    async def start(self) -> None:
        logger.info("Obsidian Sync provider active (managed by supervisord)")

    async def stop(self) -> None:
        pass
