"""Tests for OpenRouter client — JSON parsing, retry, and data-URL encoding."""

from __future__ import annotations

import json

import pytest

from app.services.openrouter_client import OpenRouterClient


class TestParseRows:
    """Unit tests for the static _parse_rows helper."""

    def test_valid_json(self):
        raw = json.dumps({"rows": [{"fullName": "Alice"}]})
        rows, err = OpenRouterClient._parse_rows(raw)
        assert err is None
        assert rows == [{"fullName": "Alice"}]

    def test_empty_rows(self):
        raw = json.dumps({"rows": []})
        rows, err = OpenRouterClient._parse_rows(raw)
        assert err is None
        assert rows == []

    def test_invalid_json(self):
        rows, err = OpenRouterClient._parse_rows("not json at all")
        assert rows is None
        assert err is not None

    def test_missing_rows_key(self):
        raw = json.dumps({"data": [1, 2]})
        rows, err = OpenRouterClient._parse_rows(raw)
        assert rows is None
        assert "rows" in err

    def test_rows_not_array(self):
        raw = json.dumps({"rows": "not an array"})
        rows, err = OpenRouterClient._parse_rows(raw)
        assert rows is None
        assert "array" in err

    def test_strips_markdown_fences(self):
        raw = '```json\n{"rows": [{"fullName": "Bob"}]}\n```'
        rows, err = OpenRouterClient._parse_rows(raw)
        assert err is None
        assert rows == [{"fullName": "Bob"}]


class TestBytesToDataUrl:
    def test_jpeg(self):
        url = OpenRouterClient._bytes_to_data_url(b"\xff\xd8\xff", "image/jpeg")
        assert url.startswith("data:image/jpeg;base64,")

    def test_png(self):
        url = OpenRouterClient._bytes_to_data_url(b"\x89PNG", "image/png")
        assert url.startswith("data:image/png;base64,")

    def test_default_mime(self):
        url = OpenRouterClient._bytes_to_data_url(b"bytes", "")
        assert url.startswith("data:image/jpeg;base64,")
