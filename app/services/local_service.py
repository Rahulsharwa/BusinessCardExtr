"""Local file service — scan local directories for business card images."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Generator

from app.utils.logging import get_logger

logger = get_logger("local_service")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def scan_folder(folder_path: str) -> Generator[Dict[str, Any], None, None]:
    """Yield file-info dicts for every image in *folder_path* (recursive).

    Each dict mirrors the shape expected by the extractor:
    ``{fileName, filePath, fileId, fileLink}``
    """
    root = Path(folder_path)
    if not root.is_dir():
        raise FileNotFoundError(f"Local folder not found: {folder_path}")

    count = 0
    for ext in ALLOWED_EXTENSIONS:
        for img_path in root.rglob(f"*{ext}"):
            count += 1
            yield {
                "fileName": img_path.name,
                "filePath": str(img_path),
                "fileId": None,
                "fileLink": None,
            }

    logger.info("local_folder_scanned", folder=folder_path, images_found=count)
