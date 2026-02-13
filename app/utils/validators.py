"""Input validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import List

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def is_valid_image_extension(filename: str) -> bool:
    """Check whether *filename* has an allowed image extension."""
    return Path(filename).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS


def validate_model_selection(
    requested_model: str | None,
    default_model: str,
    allowed_models: List[str],
) -> tuple[str, str | None]:
    """Resolve which model to use.

    Returns
    -------
    (model_id, error_message | None)
        If error_message is not None the caller should return 400.
    """
    if not requested_model:
        return default_model, None

    if requested_model in allowed_models:
        return requested_model, None

    return "", f"Model '{requested_model}' not allowed. Allowed: {allowed_models}"
