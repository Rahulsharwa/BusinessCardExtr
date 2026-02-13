"""Unit tests for normalize_service — normalization rules."""

from __future__ import annotations

import re

import pytest

from app.services.normalize_service import (
    normalize_row,
    _clamp_confidence,
    _default_timestamp,
    _normalize_email,
    _normalize_phone,
    _normalize_website,
    _to_str,
)


# ── String normalisation ────────────────────────────────


class TestToStr:
    def test_none(self):
        assert _to_str(None) is None

    def test_empty_string(self):
        assert _to_str("") is None

    def test_whitespace_only(self):
        assert _to_str("   ") is None

    def test_normal(self):
        assert _to_str("  hello  ") == "hello"

    def test_number(self):
        assert _to_str(42) == "42"


# ── Phone normalisation ─────────────────────────────────


class TestNormalizePhone:
    def test_none(self):
        assert _normalize_phone(None) is None

    def test_empty(self):
        assert _normalize_phone("") is None

    def test_digits_only(self):
        assert _normalize_phone("9876543210") == "9876543210"

    def test_international_format(self):
        assert _normalize_phone("+91 98765 43210") == "919876543210"

    def test_us_format(self):
        assert _normalize_phone("(555) 123-4567") == "5551234567"

    def test_hyphens_and_spaces(self):
        assert _normalize_phone("98-765-43210") == "9876543210"

    def test_letters_stripped(self):
        assert _normalize_phone("call 123") == "123"


# ── Email normalisation ─────────────────────────────────


class TestNormalizeEmail:
    def test_none(self):
        assert _normalize_email(None) is None

    def test_valid_uppercase(self):
        assert _normalize_email("JOHN@ABC.COM") == "john@abc.com"

    def test_valid_mixed(self):
        assert _normalize_email("  Jane.Doe@Example.Org  ") == "jane.doe@example.org"

    def test_invalid_no_at(self):
        assert _normalize_email("invalid-email") is None

    def test_invalid_no_dot(self):
        assert _normalize_email("user@host") is None

    def test_empty(self):
        assert _normalize_email("") is None


# ── Website normalisation ───────────────────────────────


class TestNormalizeWebsite:
    def test_none(self):
        assert _normalize_website(None) is None

    def test_normal(self):
        assert _normalize_website("  example.com  ") == "example.com"

    def test_whitespace_removal(self):
        assert _normalize_website("ex ample .com") == "example.com"

    def test_empty(self):
        assert _normalize_website("") is None


# ── Confidence clamping ─────────────────────────────────


class TestClampConfidence:
    def test_none(self):
        assert _clamp_confidence(None) is None

    def test_normal(self):
        assert _clamp_confidence(0.86) == 0.86

    def test_over_one(self):
        assert _clamp_confidence(1.5) == 1.0

    def test_negative(self):
        assert _clamp_confidence(-0.2) == 0.0

    def test_string_number(self):
        assert _clamp_confidence("0.75") == 0.75

    def test_invalid_string(self):
        assert _clamp_confidence("not-a-number") is None


# ── Timestamp defaulting ────────────────────────────────


class TestDefaultTimestamp:
    def test_existing_value(self):
        assert _default_timestamp("2025-01-01T00:00:00Z") == "2025-01-01T00:00:00Z"

    def test_none_defaults(self):
        result = _default_timestamp(None)
        assert result is not None
        # Must look like an ISO timestamp
        assert "T" in result

    def test_empty_string_defaults(self):
        result = _default_timestamp("")
        assert "T" in result


# ── Full row normalisation ──────────────────────────────


class TestNormalizeRow:
    def test_full_row(self):
        raw = {
            "timestamp": None,
            "fullName": "  JOHN DOE  ",
            "jobTitle": "Sales Manager",
            "company": "ABC Pvt Ltd",
            "phone1": "+91 98765-43210",
            "phone2": "",
            "email1": "JOHN@ABC.COM",
            "email2": None,
            "website": "  abc.com  ",
            "address": "Jaipur",
            "notes": "",
            "confidence": 0.856,
            "rawText": "JOHN DOE, Sales Manager...",
            "fileName": "card.jpg",
            "fileId": "abc123",
            "fileLink": "https://drive.google.com/...",
        }
        result = normalize_row(raw)

        assert result["fullName"] == "JOHN DOE"
        assert result["phone1"] == "919876543210"
        assert result["phone2"] is None       # empty → None
        assert result["email1"] == "john@abc.com"
        assert result["email2"] is None
        assert result["website"] == "abc.com"
        assert result["notes"] is None        # empty → None
        assert result["confidence"] == 0.856
        assert result["timestamp"] is not None  # defaulted
