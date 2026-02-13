"""Google Sheets service — append normalised rows to a spreadsheet."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.utils.logging import get_logger

logger = get_logger("sheets_service")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Exact column order (16 columns).
COLUMNS = [
    "timestamp",
    "fullName",
    "jobTitle",
    "company",
    "phone1",
    "phone2",
    "email1",
    "email2",
    "website",
    "address",
    "notes",
    "confidence",
    "rawText",
    "fileName",
    "fileId",
    "fileLink",
]


class SheetsService:
    """Wraps Google Sheets API v4 for appending rows."""

    def __init__(self, service_account_json: str) -> None:
        creds = self._build_credentials(service_account_json)
        self.service = build("sheets", "v4", credentials=creds)

    # ── Public API ──────────────────────────────────

    def append_rows(
        self,
        sheet_id: str,
        sheet_name: str,
        rows: List[Dict[str, Any]],
    ) -> int:
        """Append *rows* to the sheet and return the count appended."""
        if not rows:
            return 0

        values = [[row.get(col) for col in COLUMNS] for row in rows]

        body = {"values": values}
        result = (
            self.service.spreadsheets()
            .values()
            .append(
                spreadsheetId=sheet_id,
                range=f"{sheet_name}!A:P",
                valueInputOption="RAW",
                body=body,
            )
            .execute()
        )

        updates = result.get("updates", {})
        appended = updates.get("updatedRows", len(values))
        logger.info(
            "sheets_rows_appended",
            sheet_id=sheet_id,
            sheet_name=sheet_name,
            rows=appended,
        )
        return appended

    def check_connectivity(self, sheet_id: str | None = None) -> bool:
        """Quick connectivity check."""
        try:
            if sheet_id:
                self.service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            return True
        except Exception:
            return False

    # ── Private helpers ─────────────────────────────

    @staticmethod
    def _build_credentials(raw: str) -> service_account.Credentials:
        raw = raw.strip()
        if raw.startswith("{"):
            info = json.loads(raw)
        else:
            info = json.loads(Path(raw).read_text(encoding="utf-8"))
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
