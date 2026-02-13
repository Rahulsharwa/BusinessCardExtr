"""Google Drive service — list and download images from Drive folders."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict, List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from app.utils.logging import get_logger

logger = get_logger("drive_service")

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

IMAGE_MIME_TYPES = (
    "mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/webp'"
)


class DriveService:
    """Wraps Google Drive API v3 for listing and downloading images."""

    def __init__(self, service_account_json: str) -> None:
        creds = self._build_credentials(service_account_json)
        self.service = build("drive", "v3", credentials=creds)

    # ── Public API ──────────────────────────────────

    def list_files(
        self, folder_id: str, recursive: bool = False
    ) -> List[Dict[str, Any]]:
        """Return a list of image file metadata dicts in *folder_id*."""
        files = self._list_images_in_folder(folder_id)

        if recursive:
            subfolder_ids = self._list_subfolders(folder_id)
            for sub_id in subfolder_ids:
                files.extend(self.list_files(sub_id, recursive=True))

        logger.info("drive_files_listed", folder_id=folder_id, count=len(files))
        return files

    def download_file(self, file_id: str) -> bytes:
        """Download and return the raw bytes of *file_id*."""
        request = self.service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)

        done = False
        while not done:
            _, done = downloader.next_chunk()

        logger.info("drive_file_downloaded", file_id=file_id, size=buffer.tell())
        return buffer.getvalue()

    def check_connectivity(self) -> bool:
        """Quick connectivity check — try to list 1 file in root."""
        try:
            self.service.files().list(pageSize=1, fields="files(id)").execute()
            return True
        except Exception:
            return False

    # ── Private helpers ─────────────────────────────

    def _list_images_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        query = f"'{folder_id}' in parents and ({IMAGE_MIME_TYPES})"
        results: List[Dict[str, Any]] = []
        page_token = None

        while True:
            resp = (
                self.service.files()
                .list(
                    q=query,
                    fields="nextPageToken, files(id, name, webViewLink, mimeType)",
                    pageSize=1000,
                    pageToken=page_token,
                )
                .execute()
            )
            results.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return results

    def _list_subfolders(self, folder_id: str) -> List[str]:
        query = f"'{folder_id}' in parents and mimeType='application/vnd.google-apps.folder'"
        resp = (
            self.service.files()
            .list(q=query, fields="files(id)", pageSize=1000)
            .execute()
        )
        return [f["id"] for f in resp.get("files", [])]

    @staticmethod
    def _build_credentials(raw: str) -> service_account.Credentials:
        """Accept either a JSON string or a file path."""
        raw = raw.strip()
        if raw.startswith("{"):
            info = json.loads(raw)
        else:
            info = json.loads(Path(raw).read_text(encoding="utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
