"""Integration-level tests for the extraction pipeline and API endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


# ── GET /models ─────────────────────────────────────────


class TestModelsEndpoint:
    def test_returns_models(self):
        resp = client.get("/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "default" in data
        assert "allowed" in data
        assert isinstance(data["allowed"], list)


# ── POST /batch/folder — Validation ────────────────────


class TestBatchFolderValidation:
    def test_no_source(self):
        resp = client.post("/batch/folder", json={})
        assert resp.status_code == 422  # validation error

    def test_both_sources(self):
        resp = client.post(
            "/batch/folder",
            json={
                "driveFolderId": "abc",
                "localFolderPath": "/tmp",
            },
        )
        assert resp.status_code == 422

    def test_invalid_model(self):
        resp = client.post(
            "/batch/folder",
            json={
                "localFolderPath": "/tmp/nonexistent",
                "model": "some/unknown-model",
            },
        )
        assert resp.status_code == 400

    def test_concurrency_out_of_range(self):
        resp = client.post(
            "/batch/folder",
            json={
                "localFolderPath": "/tmp",
                "concurrency": 0,
            },
        )
        assert resp.status_code == 422


# ── POST /batch/folder — Dry-run with mocked extraction ─


class TestBatchFolderDryRun:
    @patch("app.main.local_service.scan_folder")
    @patch("app.main.process_batch", new_callable=AsyncMock)
    def test_local_dry_run(self, mock_batch, mock_scan):
        mock_scan.return_value = [
            {"fileName": "test.jpg", "filePath": "/tmp/test.jpg", "fileId": None, "fileLink": None}
        ]
        mock_batch.return_value = {
            "rows": [
                {
                    "timestamp": "2025-01-01T00:00:00Z",
                    "fullName": "Test User",
                    "email1": "test@example.com",
                    "phone1": "1234567890",
                    "company": None,
                    "jobTitle": None,
                    "phone2": None,
                    "email2": None,
                    "website": None,
                    "address": None,
                    "notes": None,
                    "confidence": 0.9,
                    "rawText": "Test",
                    "fileName": "test.jpg",
                    "fileId": None,
                    "fileLink": None,
                }
            ],
            "errors": [],
            "files_processed": 1,
        }

        resp = client.post(
            "/batch/folder",
            json={
                "localFolderPath": "/tmp/images",
                "dryRun": True,
                "maxFiles": 1,
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["folderMode"] == "local"
        assert data["dryRun"] is True
        assert data["rowsAppended"] == 0
        assert len(data["rows"]) >= 1
