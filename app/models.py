"""Pydantic v2 request / response models."""

from __future__ import annotations

from typing import Any, List, Optional

from pydantic import BaseModel, field_validator, model_validator


# ── Request Models ──────────────────────────────────────


class BatchRequest(BaseModel):
    """POST /batch/folder request body."""

    driveFolderId: Optional[str] = None
    localFolderPath: Optional[str] = None
    recursive: bool = False
    sheetId: Optional[str] = None
    sheetName: Optional[str] = None
    dryRun: bool = False
    maxFiles: int = 200
    concurrency: int = 3
    model: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_source(self) -> "BatchRequest":
        has_drive = bool(self.driveFolderId)
        has_local = bool(self.localFolderPath)
        if has_drive == has_local:
            raise ValueError(
                "Provide exactly one of 'driveFolderId' or 'localFolderPath' (not both, not neither)."
            )
        return self

    @field_validator("concurrency")
    @classmethod
    def concurrency_range(cls, v: int) -> int:
        if v < 1 or v > 20:
            raise ValueError("concurrency must be between 1 and 20")
        return v

    @field_validator("maxFiles")
    @classmethod
    def max_files_range(cls, v: int) -> int:
        if v < 1:
            raise ValueError("maxFiles must be at least 1")
        return v


# ── Row / Data Models ──────────────────────────────────


class ExtractedRow(BaseModel):
    """A single normalized business-card row (16 fields)."""

    timestamp: Optional[str] = None
    fullName: Optional[str] = None
    jobTitle: Optional[str] = None
    company: Optional[str] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    email1: Optional[str] = None
    email2: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    notes: Optional[str] = None
    confidence: Optional[float] = None
    rawText: Optional[str] = None
    fileName: Optional[str] = None
    fileId: Optional[str] = None
    fileLink: Optional[str] = None


# ── Response Models ─────────────────────────────────────


class FileError(BaseModel):
    """Per-file error entry."""

    fileName: Optional[str] = None
    fileId: Optional[str] = None
    error: str


class BatchResponse(BaseModel):
    """POST /batch/folder response."""

    status: str = "ok"
    folderMode: str  # "drive" | "local"
    modelUsed: str
    filesFound: int
    filesProcessed: int
    rowsExtracted: int
    rowsAppended: int
    dryRun: bool = False
    errors: List[FileError] = []
    rows: List[dict[str, Any]] = []


class ModelsResponse(BaseModel):
    """GET /models response."""

    default: str
    allowed: List[str]


class ServiceStatus(BaseModel):
    """Individual service connectivity status."""

    openrouter: str = "unknown"
    google_drive: str = "unknown"
    google_sheets: str = "unknown"


class HealthResponse(BaseModel):
    """GET /healthz response."""

    status: str = "healthy"
    services: ServiceStatus = ServiceStatus()
    timestamp: Optional[str] = None
