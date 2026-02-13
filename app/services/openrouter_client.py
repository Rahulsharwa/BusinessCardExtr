"""OpenRouter vision client — extract business card data from images."""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
from typing import Any, Dict, List, Optional

import httpx

from app.utils.logging import get_logger

logger = get_logger("openrouter_client")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

EXTRACTION_SYSTEM_PROMPT = """\
You are a strict JSON extraction agent for business card images.

Objective:
Extract business card contact data from the provided image and return Google-Sheets-ready rows.

Input:
- One image per request.
- The image may contain multiple business cards.
- You will receive metadata (fileName, fileId, fileLink) in the user message.

Output Contract (NON-NEGOTIABLE):
- Return ONLY valid JSON (no markdown, no commentary, no code fences).
- The top-level JSON must be an object with exactly one key: "rows".
- "rows" must be an array.
- Each row object MUST contain ALL fields listed below.
- If a value is not visible, set it to null (not empty string).
- emails must be lowercase.
- phone numbers must be digits only (remove +, spaces, hyphens, brackets).
- confidence must be a number between 0 and 1 (example: 0.82).

Fields required in every row:
timestamp, fullName, jobTitle, company, phone1, phone2, email1, email2, website, address, notes, confidence, rawText, fileName, fileId, fileLink

Rules:
- If multiple cards exist, return multiple row objects.
- If no usable data exists, return { "rows": [] }.
- rawText should be short (max 300 chars) for audit.
- Deduplicate within the same image (emails/phones).

Return format example:
{
  "rows": [
    {
      "timestamp": null,
      "fullName": "John Doe",
      "jobTitle": "Sales Manager",
      "company": "ABC Pvt Ltd",
      "phone1": "9876543210",
      "phone2": null,
      "email1": "john@abc.com",
      "email2": null,
      "website": "abc.com",
      "notes": null,
      "confidence": 0.86,
      "rawText": "John Doe, Sales Manager, ABC Pvt Ltd...",
      "fileName": "IMG_123.jpg",
      "fileId": "1a2b3c4d5e",
      "fileLink": "https://drive.google.com/file/d/..."
    }
  ]
}
"""

REPAIR_PROMPT_TEMPLATE = (
    "The JSON you provided was invalid. Error: {error}\n"
    "Please fix and return ONLY valid JSON with no additional text."
)


class OpenRouterClient:
    """Async client for OpenRouter vision chat completions."""

    def __init__(self, api_key: str, timeout: float = 120.0) -> None:
        self.api_key = api_key
        self.timeout = timeout

    # ── Public API ──────────────────────────────────

    async def extract_card_data(
        self,
        image_bytes: bytes,
        mime_type: str,
        file_meta: Dict[str, Any],
        model: str,
    ) -> List[Dict[str, Any]]:
        """Send an image to the vision model and return the parsed rows.

        Includes one repair-retry if the first response is invalid JSON.
        """
        data_url = self._bytes_to_data_url(image_bytes, mime_type)
        user_text = (
            f"Extract contact data from this business card. "
            f"Metadata: fileName={file_meta.get('fileName')}, "
            f"fileId={file_meta.get('fileId')}, "
            f"fileLink={file_meta.get('fileLink')}. "
            f"Return ONLY valid JSON matching the schema."
        )

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": user_text},
                ],
            },
        ]

        # First attempt
        raw_text = await self._call_api(model, messages)
        rows, error = self._parse_rows(raw_text)
        if rows is not None:
            return rows

        # Repair retry (once)
        logger.warning(
            "json_parse_failed_retrying",
            file=file_meta.get("fileName"),
            error=error,
        )
        repair_msg = {"role": "user", "content": REPAIR_PROMPT_TEMPLATE.format(error=error)}
        messages.append({"role": "assistant", "content": raw_text})
        messages.append(repair_msg)

        raw_text = await self._call_api(model, messages)
        rows, error = self._parse_rows(raw_text)
        if rows is not None:
            return rows

        raise ValueError(f"Invalid JSON after repair retry: {error}")

    async def check_connectivity(self) -> bool:
        """Quick API reachability check."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://openrouter.ai/api/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ── Private helpers ─────────────────────────────

    async def _call_api(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        max_retries: int = 3,
    ) -> str:
        """POST to OpenRouter with exponential-backoff retry on network errors."""
        payload = {"model": model, "messages": messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Title": "Business Card Extractor",
        }

        last_exc: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        OPENROUTER_API_URL,
                        json=payload,
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
            except (httpx.HTTPStatusError, httpx.RequestError, KeyError) as exc:
                last_exc = exc
                wait = 2 ** attempt
                logger.warning(
                    "openrouter_request_failed",
                    attempt=attempt + 1,
                    wait=wait,
                    error=str(exc),
                )
                await asyncio.sleep(wait)

        raise RuntimeError(f"OpenRouter API failed after {max_retries} retries: {last_exc}")

    @staticmethod
    def _parse_rows(raw: str) -> tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Try to parse *raw* as the expected ``{"rows": [...]}`` JSON."""
        try:
            # Strip potential markdown fences
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            if not isinstance(data, dict) or "rows" not in data:
                return None, "Top-level JSON must have a 'rows' key"
            if not isinstance(data["rows"], list):
                return None, "'rows' must be an array"
            return data["rows"], None
        except json.JSONDecodeError as exc:
            return None, str(exc)

    @staticmethod
    def _bytes_to_data_url(image_bytes: bytes, mime_type: str) -> str:
        """Encode image bytes as a base64 data URL."""
        if not mime_type:
            mime_type = "image/jpeg"
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{mime_type};base64,{b64}"
