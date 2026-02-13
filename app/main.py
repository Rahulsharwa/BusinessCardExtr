"""FastAPI application — Business Card Data Extraction System."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import (
    BatchRequest,
    BatchResponse,
    FileError,
    HealthResponse,
    ModelsResponse,
    ServiceStatus,
)
from app.services import local_service
from app.services.drive_service import DriveService
from app.services.extractor_service import process_batch
from app.services.normalize_service import deduplicate_rows
from app.services.openrouter_client import OpenRouterClient
from app.services.sheets_service import SheetsService
from app.utils.logging import get_logger, setup_logging
from app.utils.validators import validate_model_selection

# ── Bootstrap ───────────────────────────────────────────

settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = get_logger("main")

app = FastAPI(
    title="Business Card Extractor",
    version="1.0.0",
    description="Batch-extract business card data from images using vision models.",
)

# Mount static files to serve the frontend assets if needed, though we primarily use the root route
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# ── Endpoints ───────────────────────────────────────────


@app.get("/", include_in_schema=False)
async def read_root():
    """Serve the landing page."""
    return FileResponse("app/static/index.html")


@app.get("/models", response_model=ModelsResponse)

async def list_models() -> ModelsResponse:
    """Return the default and allowed OpenRouter models."""
    return ModelsResponse(
        default=settings.OPENROUTER_MODEL_DEFAULT,
        allowed=settings.allowed_models,
    )


@app.get("/healthz", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Report connectivity status for each backing service."""
    or_client = OpenRouterClient(settings.OPENROUTER_API_KEY)
    or_ok = await or_client.check_connectivity()

    drive_ok = False
    sheets_ok = False
    if settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            ds = DriveService(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            drive_ok = ds.check_connectivity()
        except Exception:
            pass
        try:
            ss = SheetsService(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            sheets_ok = ss.check_connectivity(settings.DEFAULT_SHEET_ID)
        except Exception:
            pass

    return HealthResponse(
        status="healthy" if (or_ok and drive_ok and sheets_ok) else "degraded",
        services=ServiceStatus(
            openrouter="ok" if or_ok else "error",
            google_drive="ok" if drive_ok else "error",
            google_sheets="ok" if sheets_ok else "error",
        ),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/batch/folder", response_model=BatchResponse)
async def batch_folder(req: BatchRequest) -> BatchResponse:
    """Main batch extraction endpoint."""

    # 1. Resolve model
    model, err = validate_model_selection(
        req.model,
        settings.OPENROUTER_MODEL_DEFAULT,
        settings.allowed_models,
    )
    if err:
        raise HTTPException(status_code=400, detail=err)

    # 2. Gather file list
    folder_mode: str
    files: list[dict[str, Any]]
    drive_svc: DriveService | None = None

    if req.driveFolderId:
        folder_mode = "drive"
        drive_svc = DriveService(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
        files = drive_svc.list_files(req.driveFolderId, recursive=req.recursive)
    else:
        folder_mode = "local"
        files = list(local_service.scan_folder(req.localFolderPath))  # type: ignore[arg-type]

    files_found = len(files)

    # 3. Apply maxFiles cap
    files = files[: req.maxFiles]

    # 4. Run extraction
    or_client = OpenRouterClient(settings.OPENROUTER_API_KEY)
    result = await process_batch(
        files=files,
        concurrency=req.concurrency,
        client=or_client,
        model=model,
        drive_service=drive_svc,
    )

    all_rows = result["rows"]
    errors = result["errors"]
    files_processed = result["files_processed"]

    # 5. Deduplicate
    unique_rows = deduplicate_rows(all_rows)

    # 6. Append to Sheets (unless dry-run)
    rows_appended = 0
    sheet_id = req.sheetId or settings.DEFAULT_SHEET_ID
    sheet_name = req.sheetName or settings.DEFAULT_SHEET_NAME or "Sheet1"

    if not req.dryRun and sheet_id:
        try:
            sheets_svc = SheetsService(settings.GOOGLE_SERVICE_ACCOUNT_JSON)
            rows_appended = sheets_svc.append_rows(sheet_id, sheet_name, unique_rows)
        except Exception as exc:
            logger.error("sheets_append_failed", error=str(exc))
            errors.append({"fileName": None, "fileId": None, "error": f"Sheets: {exc}"})

    logger.info(
        "batch_complete",
        folder_mode=folder_mode,
        model=model,
        files_found=files_found,
        files_processed=files_processed,
        rows_extracted=len(all_rows),
        rows_appended=rows_appended,
    )

    return BatchResponse(
        status="ok",
        folderMode=folder_mode,
        modelUsed=model,
        filesFound=files_found,
        filesProcessed=files_processed,
        rowsExtracted=len(all_rows),
        rowsAppended=rows_appended,
        dryRun=req.dryRun,
        errors=[FileError(**e) for e in errors],
        rows=unique_rows,
    )
