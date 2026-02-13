"""Extractor service — orchestrate concurrent batch processing."""

from __future__ import annotations

import mimetypes
from asyncio import Semaphore, gather
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.services.normalize_service import normalize_row
from app.services.openrouter_client import OpenRouterClient
from app.utils.logging import get_logger

logger = get_logger("extractor_service")


async def process_batch(
    files: List[Dict[str, Any]],
    concurrency: int,
    client: OpenRouterClient,
    model: str,
    drive_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """Process a batch of image files concurrently.

    Parameters
    ----------
    files : list of file-info dicts (must include ``fileName`` and either
            ``filePath`` for local or ``id`` for Drive).
    concurrency : max parallel workers.
    client : configured ``OpenRouterClient``.
    model : OpenRouter model identifier.
    drive_service : optional ``DriveService`` instance for Drive mode.

    Returns
    -------
    dict with keys ``rows``, ``errors``, ``files_processed``.
    """
    semaphore = Semaphore(concurrency)

    async def _process_one(file_info: Dict[str, Any]) -> Dict[str, Any]:
        async with semaphore:
            file_name = file_info.get("fileName") or file_info.get("name", "unknown")
            try:
                # 1. Read image bytes
                image_bytes, mime_type = await _read_image(file_info, drive_service)

                # 2. Build file metadata for the prompt
                file_meta = {
                    "fileName": file_name,
                    "fileId": file_info.get("fileId") or file_info.get("id"),
                    "fileLink": file_info.get("fileLink") or file_info.get("webViewLink"),
                }

                # 3. Extract via vision model
                raw_rows = await client.extract_card_data(
                    image_bytes, mime_type, file_meta, model
                )

                # 4. Normalise each row + inject metadata
                normalised = []
                for row in raw_rows:
                    row.setdefault("fileName", file_meta["fileName"])
                    row.setdefault("fileId", file_meta["fileId"])
                    row.setdefault("fileLink", file_meta["fileLink"])
                    normalised.append(normalize_row(row))

                logger.info(
                    "file_processed",
                    file_name=file_name,
                    rows_extracted=len(normalised),
                )
                return {"status": "ok", "rows": normalised}

            except Exception as exc:
                logger.error(
                    "file_processing_failed",
                    file_name=file_name,
                    error=str(exc),
                )
                return {
                    "status": "error",
                    "fileName": file_name,
                    "fileId": file_info.get("fileId") or file_info.get("id"),
                    "error": str(exc),
                }

    # Launch all tasks
    results = await gather(
        *[_process_one(f) for f in files],
        return_exceptions=True,
    )

    # Aggregate
    all_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    processed = 0

    for res in results:
        if isinstance(res, Exception):
            errors.append({"fileName": "unknown", "error": str(res)})
            continue
        processed += 1
        if res["status"] == "ok":
            all_rows.extend(res["rows"])
        else:
            errors.append(
                {
                    "fileName": res.get("fileName"),
                    "fileId": res.get("fileId"),
                    "error": res.get("error"),
                }
            )

    return {
        "rows": all_rows,
        "errors": errors,
        "files_processed": processed,
    }


# ── Private helpers ─────────────────────────────────────


async def _read_image(
    file_info: Dict[str, Any],
    drive_service: Optional[Any],
) -> tuple[bytes, str]:
    """Return ``(bytes, mime_type)`` for a file, from local disk or Drive."""
    local_path = file_info.get("filePath")
    if local_path:
        p = Path(local_path)
        if not p.is_file():
            raise FileNotFoundError(f"Image not found: {local_path}")
        mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
        return p.read_bytes(), mime

    # Drive mode
    file_id = file_info.get("id") or file_info.get("fileId")
    if not file_id or not drive_service:
        raise ValueError("Cannot determine image source (no filePath or Drive fileId)")

    image_bytes = drive_service.download_file(file_id)
    mime = file_info.get("mimeType") or "image/jpeg"
    return image_bytes, mime
