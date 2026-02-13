# Business Card Data Extraction System

Batch-extract contact data from business card images using OpenRouter vision models (Claude 3.5 / GPT-4o / Gemini 2.0 Flash). Reads images from **Google Drive** or a **local folder**, normalises & deduplicates the data, and appends the results to **Google Sheets**.

## Key Features

- **Runtime model selection** — choose the vision model per request from a configurable allowlist
- **Google Drive & local folder** support
- **Concurrent processing** — configurable parallel workers via `asyncio.Semaphore`
- **Normalisation & deduplication** — phone digits-only, email lowercase, confidence clamping, composite-key dedup
- **Google Sheets integration** — auto-append to a specified spreadsheet
- **Dry-run mode** — test extraction without touching Sheets
- **CLI + REST API** interfaces
- **Docker-ready** deployment

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- [OpenRouter API key](https://openrouter.ai/)
- Google Cloud service account with Drive & Sheets API enabled

### 2. Install

```bash
pip install -r requirements.txt
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — set OPENROUTER_API_KEY, GOOGLE_SERVICE_ACCOUNT_JSON, etc.
```

### 4. Run

```bash
uvicorn app.main:app --reload --port 8000
```

---

## API Reference

### `GET /models`

```bash
curl http://localhost:8000/models
```

```json
{
  "default": "anthropic/claude-3.5-sonnet",
  "allowed": [
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "google/gemini-2.0-flash-001"
  ]
}
```

### `GET /healthz`

```bash
curl http://localhost:8000/healthz
```

### `POST /batch/folder`

**Google Drive folder:**

```bash
curl -X POST http://localhost:8000/batch/folder \
  -H "Content-Type: application/json" \
  -d '{
    "driveFolderId": "YOUR_FOLDER_ID",
    "sheetId": "YOUR_SHEET_ID",
    "sheetName": "Campaign4",
    "model": "anthropic/claude-3.5-sonnet",
    "maxFiles": 50,
    "concurrency": 3
  }'
```

**Local folder (dry-run):**

```bash
curl -X POST http://localhost:8000/batch/folder \
  -H "Content-Type: application/json" \
  -d '{
    "localFolderPath": "/path/to/images",
    "dryRun": true,
    "maxFiles": 10
  }'
```

**Response:**

```json
{
  "status": "ok",
  "folderMode": "drive",
  "modelUsed": "anthropic/claude-3.5-sonnet",
  "filesFound": 15,
  "filesProcessed": 15,
  "rowsExtracted": 23,
  "rowsAppended": 18,
  "errors": [],
  "rows": [ ... ]
}
```

---

## CLI Usage

```bash
# List models
python -m app.cli models

# Process local folder (dry-run)
python -m app.cli batch --local-folder ./images --dry-run --max-files 5

# Process Drive folder
python -m app.cli batch \
  --drive-folder-id YOUR_ID \
  --sheet-id YOUR_SHEET \
  --sheet-name Campaign4 \
  --model openai/gpt-4o
```

---

## Google Cloud Setup

1. Create a GCP project and enable **Drive API** + **Sheets API**
2. Create a **Service Account** and download the JSON key
3. Share your Drive folder and Google Sheet with the service account email
4. Set `GOOGLE_SERVICE_ACCOUNT_JSON` in `.env` (paste JSON or file path)

---

## Architecture

```
User Request → Validate → List Images → Concurrent Extraction → Normalise → Deduplicate → Sheets Append → Report
```

| Component | File | Purpose |
|---|---|---|
| Config | `app/config.py` | Env vars + model allowlist |
| Models | `app/models.py` | Pydantic request/response |
| Drive | `app/services/drive_service.py` | List + download from Drive |
| Local | `app/services/local_service.py` | Scan local directories |
| Vision | `app/services/openrouter_client.py` | OpenRouter API integration |
| Extractor | `app/services/extractor_service.py` | Batch orchestration |
| Normalise | `app/services/normalize_service.py` | Data cleaning + dedup |
| Sheets | `app/services/sheets_service.py` | Append to Google Sheets |
| API | `app/main.py` | FastAPI endpoints |
| CLI | `app/cli.py` | Click CLI wrapper |

---

## Testing

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

---

## Docker

```bash
docker-compose up --build
```

---

## Model Selection

| Model | Speed | Accuracy | Cost/100 images |
|---|---|---|---|
| `google/gemini-2.0-flash-001` | ⚡ Fast | Good | ~$0.50 |
| `openai/gpt-4o` | Medium | High | ~$3.00 |
| `anthropic/claude-3.5-sonnet` | Medium | Highest | ~$2.50 |

Configure via `OPENROUTER_MODEL_ALLOWLIST` in `.env`.

---

## Troubleshooting

| Error | Fix |
|---|---|
| Model not allowed | Add to `OPENROUTER_MODEL_ALLOWLIST` and restart |
| Service account auth failed | Share folder/sheet with SA email; verify JSON |
| Rate limit (429) | Lower `concurrency` to 2–3 |
| JSON parse after retry | Try a different model; check image quality |
| Sheets quota exceeded | Batch calls; request GCP quota increase |

## License

MIT
