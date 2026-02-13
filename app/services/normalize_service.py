"""Normalization and deduplication for extracted business card rows."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ── Normalization ───────────────────────────────────────


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Apply strict normalization rules to a single extracted row."""
    return {
        "timestamp": _default_timestamp(row.get("timestamp")),
        "fullName": _to_str(row.get("fullName")),
        "jobTitle": _to_str(row.get("jobTitle")),
        "company": _to_str(row.get("company")),
        "phone1": _normalize_phone(row.get("phone1")),
        "phone2": _normalize_phone(row.get("phone2")),
        "email1": _normalize_email(row.get("email1")),
        "email2": _normalize_email(row.get("email2")),
        "website": _normalize_website(row.get("website")),
        "address": _to_str(row.get("address")),
        "notes": _to_str(row.get("notes")),
        "confidence": _clamp_confidence(row.get("confidence")),
        "rawText": _to_str(row.get("rawText")),
        "fileName": _to_str(row.get("fileName")),
        "fileId": _to_str(row.get("fileId")),
        "fileLink": _to_str(row.get("fileLink")),
    }


# ── Deduplication ───────────────────────────────────────


def deduplicate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate across the entire batch using composite keys.

    Keep first occurrence only.
    """
    seen_keys: set[str] = set()
    unique_rows: List[Dict[str, Any]] = []

    for row in rows:
        key = _dedup_key(row)
        if key not in seen_keys:
            seen_keys.add(key)
            unique_rows.append(row)

    return unique_rows


# ── Private helpers ─────────────────────────────────────


def _to_str(val: Any) -> Optional[str]:
    """Trim; convert empty / whitespace-only to ``None``."""
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalize_phone(val: Any) -> Optional[str]:
    """Strip everything except digits."""
    if val is None:
        return None
    digits = re.sub(r"[^\d]", "", str(val))
    return digits if digits else None


def _normalize_email(val: Any) -> Optional[str]:
    """Lowercase + basic validation."""
    if val is None:
        return None
    email = str(val).strip().lower()
    if re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return email
    return None


def _normalize_website(val: Any) -> Optional[str]:
    """Remove internal whitespace."""
    if val is None:
        return None
    site = re.sub(r"\s+", "", str(val).strip())
    return site if site else None


def _clamp_confidence(val: Any) -> Optional[float]:
    """Clamp to [0, 1]."""
    if val is None:
        return None
    try:
        conf = float(val)
        return max(0.0, min(1.0, conf))
    except (ValueError, TypeError):
        return None


def _default_timestamp(val: Any) -> str:
    """Return the existing value or default to UTC now in ISO-8601."""
    if val:
        s = str(val).strip()
        if s:
            return s
    return datetime.now(timezone.utc).isoformat()


def _dedup_key(row: Dict[str, Any]) -> str:
    """Generate a composite dedup key for a row."""
    if row.get("email1"):
        return f"email:{row['email1']}"
    phone = row.get("phone1") or ""
    name = (row.get("fullName") or "").lower()
    company = (row.get("company") or "").lower()
    return f"fallback:{phone}|{name}|{company}"
