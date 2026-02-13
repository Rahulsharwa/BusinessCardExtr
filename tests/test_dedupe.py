"""Unit tests for deduplication logic."""

from __future__ import annotations

from app.services.normalize_service import deduplicate_rows


class TestDeduplicateRows:
    def test_no_duplicates(self):
        rows = [
            {"email1": "a@b.com", "fullName": "Alice"},
            {"email1": "c@d.com", "fullName": "Bob"},
        ]
        assert len(deduplicate_rows(rows)) == 2

    def test_email_dedup(self):
        rows = [
            {"email1": "john@abc.com", "fullName": "John"},
            {"email1": "john@abc.com", "fullName": "Jane"},  # dup
            {"email1": "jane@xyz.com", "fullName": "Jane"},
        ]
        result = deduplicate_rows(rows)
        assert len(result) == 2
        assert result[0]["fullName"] == "John"
        assert result[1]["email1"] == "jane@xyz.com"

    def test_fallback_key_dedup(self):
        rows = [
            {"email1": None, "phone1": "9876543210", "fullName": "Bob", "company": "X"},
            {"email1": None, "phone1": "9876543210", "fullName": "Bob", "company": "X"},  # dup
            {"email1": None, "phone1": "1111111111", "fullName": "Alice", "company": "Y"},
        ]
        result = deduplicate_rows(rows)
        assert len(result) == 2

    def test_mixed_keys(self):
        rows = [
            {"email1": "john@abc.com", "phone1": "111", "fullName": "John", "company": "A"},
            {"email1": None, "phone1": "222", "fullName": "Bob", "company": "B"},
            {"email1": "john@abc.com", "phone1": "333", "fullName": "J. Doe", "company": "C"},  # dup by email
        ]
        result = deduplicate_rows(rows)
        assert len(result) == 2

    def test_empty_list(self):
        assert deduplicate_rows([]) == []

    def test_single_row(self):
        rows = [{"email1": "x@y.com", "fullName": "X"}]
        assert deduplicate_rows(rows) == rows

    def test_keeps_first_occurrence(self):
        rows = [
            {"email1": "same@mail.com", "fullName": "First"},
            {"email1": "same@mail.com", "fullName": "Second"},
        ]
        result = deduplicate_rows(rows)
        assert len(result) == 1
        assert result[0]["fullName"] == "First"
