"""Sync providers for vault synchronization."""

from __future__ import annotations

import asyncio
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


class DropboxSyncProvider(SyncProvider):
    """Uploads files to Dropbox via API."""

    def __init__(self, app_key: str, app_secret: str, refresh_token: str, base_path: str) -> None:
        self._app_key = app_key
        self._app_secret = app_secret
        self._refresh_token = refresh_token
        self._base_path = base_path.rstrip("/")
        self._client = None

    async def start(self) -> None:
        import dropbox
        self._client = dropbox.Dropbox(
            oauth2_refresh_token=self._refresh_token,
            app_key=self._app_key,
            app_secret=self._app_secret,
        )
        account = await asyncio.to_thread(self._client.users_get_current_account)
        logger.info("Dropbox provider active (account: %s)", account.email)

    async def stop(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    async def upload_file(self, local_path: Path, remote_path: str) -> None:
        if self._client is None:
            logger.error("Dropbox client not initialized, skipping upload: %s", remote_path)
            return
        import dropbox
        dest = f"{self._base_path}/{remote_path}"
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                content = await asyncio.to_thread(local_path.read_bytes)
                await asyncio.to_thread(
                    self._client.files_upload,
                    content,
                    dest,
                    mode=dropbox.files.WriteMode.overwrite,
                )
                logger.info("Uploaded to Dropbox: %s", dest)
                return
            except dropbox.exceptions.AuthError:
                logger.exception("Dropbox auth failed (check credentials): %s", dest)
                return
            except (dropbox.exceptions.ApiError, OSError):
                if attempt == max_retries:
                    logger.exception("Dropbox upload failed after %d attempts: %s", max_retries, dest)
                    return
                wait = 2 ** attempt
                logger.warning("Dropbox upload attempt %d failed, retrying in %ds: %s", attempt, wait, dest)
                await asyncio.sleep(wait)
            except Exception:
                logger.exception("Unexpected error uploading to Dropbox: %s", dest)
                return
