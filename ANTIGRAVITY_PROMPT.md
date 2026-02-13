# Google Antigravity Prompt: Business Card Data Extraction System

## Project Overview
Build a production-grade Python FastAPI application that batch-extracts visiting card/business card data from images in Google Drive folders or local directories, using OpenRouter multimodal vision models for OCR/extraction, with runtime model selection and automatic Google Sheets integration.

## System Architecture

### Core Components
1. **FastAPI REST API** - Main application server
2. **OpenRouter Vision Client** - Multimodal OCR extraction using vision models
3. **Google Drive Service** - List and download images from Drive folders
4. **Local File Service** - Scan and process local image directories
5. **Extraction Service** - Coordinate vision model extraction with retry logic
6. **Normalization Service** - Clean, validate, and deduplicate extracted data
7. **Google Sheets Service** - Append normalized rows to spreadsheets
8. **CLI Interface** - Command-line wrapper for batch operations

---

## High-Level Workflow

```
User Request (Drive folder or local path)
    ↓
List all images (jpg/jpeg/png/webp)
    ↓
For each image (with concurrency control):
    ↓
    Read image bytes
    ↓
    Convert to base64 data URL
    ↓
    Send to OpenRouter vision model
    ↓
    Extract strict JSON with schema validation
    ↓
    Retry once if JSON is invalid
    ↓
    Normalize fields (phone, email, confidence, etc.)
    ↓
    Deduplicate across batch
    ↓
Append all rows to Google Sheets
    ↓
Return comprehensive run report
```

---

## Detailed Requirements

### 1. OpenRouter Integration (CRITICAL)

#### Model Selection Strategy
- **Environment Variables**:
  - `OPENROUTER_API_KEY` - API authentication
  - `OPENROUTER_MODEL_DEFAULT` - Default model (e.g., `anthropic/claude-3.5-sonnet`)
  - `OPENROUTER_MODEL_ALLOWLIST` - Comma-separated allowed models (e.g., `anthropic/claude-3.5-sonnet,openai/gpt-4o,google/gemini-2.0-flash-001`)

- **Runtime Selection**:
  - Request body can include `"model": "openrouter/model-id"`
  - If not specified, use `OPENROUTER_MODEL_DEFAULT`
  - If specified but not in `OPENROUTER_MODEL_ALLOWLIST`, return **400 Bad Request** with allowed options

- **GET /models Endpoint**:
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

#### OpenRouter Client Implementation
**File**: `app/services/openrouter_client.py`

```python
# Use OpenAI-compatible API endpoint
# POST https://openrouter.ai/api/v1/chat/completions
# Headers:
#   - Authorization: Bearer {OPENROUTER_API_KEY}
#   - HTTP-Referer: {optional}
#   - X-Title: {optional}

# Vision Input Format (base64 data URL):
{
  "model": "anthropic/claude-3.5-sonnet",
  "messages": [
    {
      "role": "system",
      "content": "You are a strict JSON extraction agent for business card images..."
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,/9j/4AAQSkZJRg..."
          }
        },
        {
          "type": "text",
          "text": "Extract contact data from this business card. Return ONLY valid JSON..."
        }
      ]
    }
  ]
}
```

#### Extraction Prompt (System Message)
```
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
```

#### JSON Repair Retry Logic
1. First attempt: Send image with extraction prompt
2. If response is invalid JSON:
   - Parse error message
   - Send **repair prompt** as new message in conversation:
     ```
     The JSON you provided was invalid. Error: {error_message}
     Please fix and return ONLY valid JSON with no additional text.
     ```
3. Retry ONCE with repair prompt
4. If still invalid, mark file as error and continue batch

---

### 2. Required Output Schema

**All keys are REQUIRED** (use `null` if missing):

```python
{
  "timestamp": str | None,      # ISO 8601 format or null
  "fullName": str | None,
  "jobTitle": str | None,
  "company": str | None,
  "phone1": str | None,         # Digits only
  "phone2": str | None,         # Digits only
  "email1": str | None,         # Lowercase
  "email2": str | None,         # Lowercase
  "website": str | None,
  "address": str | None,
  "notes": str | None,
  "confidence": float | None,   # 0.0 to 1.0
  "rawText": str | None,        # Max 300 chars
  "fileName": str | None,
  "fileId": str | None,         # Google Drive ID or null
  "fileLink": str | None        # Google Drive URL or null
}
```

---

### 3. Normalization & Deduplication

**File**: `app/services/normalize_service.py`

#### Normalization Rules (Exact Implementation)

```python
def normalize_row(row: dict) -> dict:
    """Apply strict normalization rules"""
    
    # String normalization (trim, empty -> null)
    def to_str(val):
        if not val or str(val).strip() == "":
            return None
        return str(val).strip()
    
    # Phone normalization (digits only)
    def normalize_phone(val):
        if not val:
            return None
        digits = re.sub(r'[^\d]', '', str(val))
        return digits if digits else None
    
    # Email normalization (lowercase, validate)
    def normalize_email(val):
        if not val:
            return None
        email = str(val).strip().lower()
        if re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            return email
        return None
    
    # Website normalization
    def normalize_website(val):
        if not val:
            return None
        site = str(val).strip()
        site = re.sub(r'\s+', '', site)  # Remove whitespace
        return site if site else None
    
    # Confidence clamping
    def clamp_confidence(val):
        if val is None:
            return None
        try:
            conf = float(val)
            return max(0.0, min(1.0, conf))
        except:
            return None
    
    # Timestamp defaulting
    def default_timestamp(val):
        if val:
            return val
        return datetime.utcnow().isoformat() + "Z"
    
    return {
        "timestamp": default_timestamp(row.get("timestamp")),
        "fullName": to_str(row.get("fullName")),
        "jobTitle": to_str(row.get("jobTitle")),
        "company": to_str(row.get("company")),
        "phone1": normalize_phone(row.get("phone1")),
        "phone2": normalize_phone(row.get("phone2")),
        "email1": normalize_email(row.get("email1")),
        "email2": normalize_email(row.get("email2")),
        "website": normalize_website(row.get("website")),
        "address": to_str(row.get("address")),
        "notes": to_str(row.get("notes")),
        "confidence": clamp_confidence(row.get("confidence")),
        "rawText": to_str(row.get("rawText")),
        "fileName": to_str(row.get("fileName")),
        "fileId": to_str(row.get("fileId")),
        "fileLink": to_str(row.get("fileLink"))
    }
```

#### Deduplication Rules (Exact Implementation)

```python
def deduplicate_rows(rows: list[dict]) -> list[dict]:
    """
    Deduplicate across the entire batch using composite keys.
    Keep first occurrence only.
    """
    seen_keys = set()
    unique_rows = []
    
    for row in rows:
        # Generate dedup key
        if row.get("email1"):
            key = f"email:{row['email1']}"
        else:
            # Fallback key
            phone = row.get("phone1") or ""
            name = (row.get("fullName") or "").lower()
            company = (row.get("company") or "").lower()
            key = f"fallback:{phone}|{name}|{company}"
        
        if key not in seen_keys:
            seen_keys.add(key)
            unique_rows.append(row)
    
    return unique_rows
```

---

### 4. Folder Selection Modes

#### A) Google Drive Folder
**File**: `app/services/drive_service.py`

```python
# Use Google Drive API v3
# Service account authentication from GOOGLE_SERVICE_ACCOUNT_JSON

# List files in folder
service.files().list(
    q=f"'{folder_id}' in parents and (mimeType='image/jpeg' or mimeType='image/png' or mimeType='image/webp')",
    fields="files(id, name, webViewLink, mimeType)",
    pageSize=1000
).execute()

# Optional recursive listing
if recursive:
    # Find all subfolders
    # List files in each subfolder
    # Flatten results

# Download file bytes
request = service.files().get_media(fileId=file_id)
fh = io.BytesIO()
downloader = MediaIoBaseDownload(fh, request)
# ... download logic
```

#### B) Local Folder
**File**: `app/services/local_service.py`

```python
# Scan for images
from pathlib import Path

extensions = {'.jpg', '.jpeg', '.png', '.webp'}
images = []

for ext in extensions:
    images.extend(Path(folder_path).rglob(f'*{ext}'))

# Return file info
for img_path in images:
    yield {
        "fileName": img_path.name,
        "filePath": str(img_path),
        "fileId": None,
        "fileLink": None
    }
```

---

### 5. API Endpoints

#### POST /batch/folder

**Request Body**:
```json
{
  "driveFolderId": "1-vvCHAgf8nATMlNipFBObbMSZxrp9FTv",  // OR
  "localFolderPath": "/path/to/images",                  // OR
  "recursive": false,
  "sheetId": "1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s",
  "sheetName": "Campaign4",
  "dryRun": false,
  "maxFiles": 200,
  "concurrency": 3,
  "model": "anthropic/claude-3.5-sonnet"  // Optional override
}
```

**Response**:
```json
{
  "status": "ok",
  "folderMode": "drive",
  "modelUsed": "anthropic/claude-3.5-sonnet",
  "filesFound": 15,
  "filesProcessed": 15,
  "rowsExtracted": 23,
  "rowsAppended": 18,
  "errors": [
    {
      "fileName": "corrupt.jpg",
      "fileId": "abc123",
      "error": "Invalid JSON after retry"
    }
  ],
  "rows": [
    {
      "timestamp": "2025-02-13T10:30:00Z",
      "fullName": "John Doe",
      // ... all fields
    }
  ]
}
```

**Validation**:
- Must provide EITHER `driveFolderId` OR `localFolderPath` (not both)
- If `model` provided, validate against `OPENROUTER_MODEL_ALLOWLIST`
- Default `maxFiles` = 200, `concurrency` = 3

#### GET /models

**Response**:
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

#### GET /healthz

**Response**:
```json
{
  "status": "healthy",
  "services": {
    "openrouter": "ok",
    "google_drive": "ok",
    "google_sheets": "ok"
  }
}
```

---

### 6. Concurrency Control

**File**: `app/services/extractor_service.py`

```python
import asyncio
from asyncio import Semaphore

async def process_batch(
    files: list,
    concurrency: int,
    openrouter_client,
    model: str
):
    semaphore = Semaphore(concurrency)
    
    async def process_file(file_info):
        async with semaphore:
            try:
                # Read image bytes
                # Extract with vision model
                # Normalize rows
                return {"status": "ok", "rows": [...]}
            except Exception as e:
                return {"status": "error", "error": str(e)}
    
    tasks = [process_file(f) for f in files]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    return results
```

---

### 7. Google Sheets Integration

**File**: `app/services/sheets_service.py`

```python
# Use Google Sheets API v4
# Service account authentication

# Column order (EXACT):
COLUMNS = [
    "timestamp", "fullName", "jobTitle", "company",
    "phone1", "phone2", "email1", "email2",
    "website", "address", "notes", "confidence",
    "rawText", "fileName", "fileId", "fileLink"
]

def append_rows(sheet_id: str, sheet_name: str, rows: list[dict]):
    """Append rows to sheet in exact column order"""
    
    # Convert rows to 2D array
    values = []
    for row in rows:
        values.append([row.get(col) for col in COLUMNS])
    
    # Append to sheet
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A:P",  # 16 columns
        valueInputOption="RAW",
        body={"values": values}
    ).execute()
```

**If dryRun=true**: Skip append, return rows in response only.

---

### 8. Project Structure

```
business-card-extractor/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app
│   ├── config.py                  # Pydantic Settings
│   ├── models.py                  # Request/Response models
│   ├── services/
│   │   ├── __init__.py
│   │   ├── drive_service.py       # Google Drive API
│   │   ├── local_service.py       # Local file scanning
│   │   ├── openrouter_client.py   # OpenRouter vision API
│   │   ├── extractor_service.py   # Orchestration + concurrency
│   │   ├── normalize_service.py   # Normalization + dedup
│   │   └── sheets_service.py      # Google Sheets API
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── validators.py          # Input validation
│   │   └── logging.py             # Structured logging
│   └── cli.py                     # CLI wrapper
├── tests/
│   ├── __init__.py
│   ├── test_normalize.py
│   ├── test_openrouter.py
│   └── test_extraction.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── pyproject.toml
```

---

### 9. Environment Variables

**File**: `.env.example`

```bash
# Server
PORT=8000
LOG_LEVEL=INFO

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-...
OPENROUTER_MODEL_DEFAULT=anthropic/claude-3.5-sonnet
OPENROUTER_MODEL_ALLOWLIST=anthropic/claude-3.5-sonnet,openai/gpt-4o,google/gemini-2.0-flash-001

# Google Cloud (Service Account JSON)
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account",...}
# OR
GOOGLE_SERVICE_ACCOUNT_JSON=/path/to/service-account.json

# Google Sheets Defaults
DEFAULT_SHEET_ID=1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s
DEFAULT_SHEET_NAME=Campaign4

# Optional
MAX_FILES_DEFAULT=200
CONCURRENCY_DEFAULT=3
```

**Config Implementation** (`app/config.py`):
```python
from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"
    
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL_DEFAULT: str
    OPENROUTER_MODEL_ALLOWLIST: str
    
    GOOGLE_SERVICE_ACCOUNT_JSON: str
    DEFAULT_SHEET_ID: str | None = None
    DEFAULT_SHEET_NAME: str | None = None
    
    MAX_FILES_DEFAULT: int = 200
    CONCURRENCY_DEFAULT: int = 3
    
    @property
    def allowed_models(self) -> List[str]:
        """Parse comma-separated allowlist"""
        return [m.strip() for m in self.OPENROUTER_MODEL_ALLOWLIST.split(",")]
    
    class Config:
        env_file = ".env"
```

---

### 10. CLI Interface

**File**: `app/cli.py`

```bash
# Usage examples:

# Process Google Drive folder
python -m app.cli batch \
  --drive-folder-id 1-vvCHAgf8nATMlNipFBObbMSZxrp9FTv \
  --sheet-id 1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s \
  --sheet-name Campaign4 \
  --model anthropic/claude-3.5-sonnet \
  --max-files 50 \
  --concurrency 5

# Process local folder
python -m app.cli batch \
  --local-folder /path/to/images \
  --sheet-id 1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s \
  --dry-run

# List available models
python -m app.cli models
```

**Implementation**:
```python
import click
import httpx

@click.group()
def cli():
    pass

@cli.command()
@click.option('--drive-folder-id')
@click.option('--local-folder')
@click.option('--sheet-id')
@click.option('--sheet-name')
@click.option('--model')
@click.option('--max-files', type=int, default=200)
@click.option('--concurrency', type=int, default=3)
@click.option('--dry-run', is_flag=True)
def batch(**kwargs):
    """Run batch extraction"""
    # Call API endpoint
    pass

@cli.command()
def models():
    """List available models"""
    # Call GET /models
    pass
```

---

### 11. Error Handling & Logging

**Per-File Error Handling**:
- Vision extraction fails → Log error, add to `errors` array, continue
- JSON parse fails after retry → Log error, add to `errors` array, continue
- Network timeout → Retry with exponential backoff (max 3 retries)
- Invalid image format → Skip file, add to `errors`

**Structured Logging** (`app/utils/logging.py`):
```python
import structlog

logger = structlog.get_logger()

# Usage
logger.info(
    "file_processed",
    file_name="card1.jpg",
    rows_extracted=2,
    confidence=0.89
)
```

---

### 12. Testing Requirements

**File**: `tests/test_normalize.py`

```python
def test_phone_normalization():
    assert normalize_phone("+91 98765 43210") == "919876543210"
    assert normalize_phone("(555) 123-4567") == "5551234567"
    assert normalize_phone("") is None

def test_email_normalization():
    assert normalize_email("JOHN@ABC.COM") == "john@abc.com"
    assert normalize_email("invalid-email") is None

def test_deduplication():
    rows = [
        {"email1": "john@abc.com", "fullName": "John"},
        {"email1": "john@abc.com", "fullName": "Jane"},  # Duplicate
        {"email1": "jane@xyz.com", "fullName": "Jane"}
    ]
    unique = deduplicate_rows(rows)
    assert len(unique) == 2
```

**Run tests**:
```bash
pytest tests/ -v --cov=app
```

---

### 13. Docker Deployment

**Dockerfile**:
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./local_images:/data/images  # For local folder mode
```

**Run**:
```bash
docker-compose up --build
```

---

### 14. README.md Requirements

#### Sections to Include:

1. **Overview**
   - What the system does
   - Key features (model selection, Drive/local support, deduplication)

2. **Setup Instructions**
   - Python 3.11+
   - Install dependencies: `pip install -r requirements.txt`
   - Create `.env` from `.env.example`
   - Set up Google Cloud service account
   - Set OpenRouter API key

3. **Google Cloud Setup**
   - Enable Drive API and Sheets API
   - Create service account
   - Download JSON key
   - Share Drive folder and Sheet with service account email

4. **Quick Start**
   ```bash
   # Start server
   uvicorn app.main:app --reload
   
   # List available models
   curl http://localhost:8000/models
   
   # Process Drive folder
   curl -X POST http://localhost:8000/batch/folder \
     -H "Content-Type: application/json" \
     -d '{
       "driveFolderId": "1-vvCHAgf8nATMlNipFBObbMSZxrp9FTv",
       "sheetId": "1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s",
       "sheetName": "Campaign4",
       "model": "anthropic/claude-3.5-sonnet",
       "maxFiles": 50
     }'
   ```

5. **Architecture Diagram**
   - ASCII diagram showing workflow
   - Mirror n8n workflow structure

6. **API Reference**
   - Document all endpoints
   - Request/response examples
   - Error codes

7. **Model Selection Guide**
   - How to configure allowlist
   - Recommended models for accuracy/speed/cost
   - Model comparison table

8. **Troubleshooting**
   - Common errors
   - Debug logging
   - Service account permissions

---

### 15. Comparison to n8n Workflow

**Mapping**:
```
n8n Node                    →  Python Component
─────────────────────────────────────────────────────
Google Drive Trigger        →  drive_service.py (list_files)
Download Image1             →  drive_service.py (list_files)
Loop Over Files             →  extractor_service.py (asyncio batch)
Limit                       →  Request validation (maxFiles)
Workflow Configuration      →  Metadata injection (fileName, etc.)
Download Image2             →  drive_service.py (download_file)
OpenRouter Chat Model       →  openrouter_client.py
Business Card Extractor     →  extractor_service.py (with prompt)
Structured Output Parser    →  JSON validation + repair retry
Split Rows                  →  Normalization + deduplication
Append to Google Sheets     →  sheets_service.py
```

**Key Improvements Over n8n**:
1. **Batch processing** instead of sequential loops
2. **Concurrent extraction** (configurable workers)
3. **Model selection** per request
4. **Comprehensive error handling** with detailed reports
5. **CLI + API** interfaces
6. **Docker deployment** ready
7. **Automated testing** suite

---

## Implementation Checklist

### Phase 1: Core Infrastructure
- [ ] Project structure setup
- [ ] Pydantic config with allowlist parsing
- [ ] Request/response models
- [ ] Structured logging setup
- [ ] Error handling framework

### Phase 2: Google Integrations
- [ ] Drive service (list + download)
- [ ] Sheets service (append with column order)
- [ ] Service account authentication
- [ ] Local folder scanning

### Phase 3: OpenRouter Vision
- [ ] Client implementation (base64 data URLs)
- [ ] Extraction prompt engineering
- [ ] JSON repair retry logic
- [ ] Model validation against allowlist

### Phase 4: Data Processing
- [ ] Normalization rules (exact spec)
- [ ] Deduplication logic
- [ ] Schema validation
- [ ] Confidence clamping

### Phase 5: Orchestration
- [ ] Async batch processing
- [ ] Concurrency control (semaphore)
- [ ] Per-file error handling
- [ ] Run report generation

### Phase 6: API & CLI
- [ ] FastAPI endpoints
- [ ] Click CLI wrapper
- [ ] Health check endpoint
- [ ] Model listing endpoint

### Phase 7: Testing & Docs
- [ ] Unit tests (normalization, dedup)
- [ ] Integration tests (mocked APIs)
- [ ] README with examples
- [ ] Docker setup
- [ ] .env.example

---

## Success Criteria

✅ **Functional**:
- Process 100 business card images in <5 minutes (3 workers)
- Extract structured data with >90% field accuracy
- Handle corrupt images gracefully
- Deduplicate correctly across batch

✅ **Reliable**:
- Retry failed extractions automatically
- Graceful degradation on API failures
- Comprehensive error reporting

✅ **Configurable**:
- Runtime model selection
- Adjustable concurrency
- Dry-run mode for testing

✅ **Production-Ready**:
- Docker deployable
- Structured logging
- Health monitoring
- Service account authentication

---

## Example Use Cases

### Use Case 1: Conference Badge Collection
```bash
# Scan 200 conference attendee cards
# Use fast model for speed
curl -X POST /batch/folder -d '{
  "driveFolderId": "conference-2025",
  "sheetId": "attendees-sheet",
  "model": "google/gemini-2.0-flash-001",
  "maxFiles": 200,
  "concurrency": 10
}'
```

### Use Case 2: Sales Lead Extraction
```bash
# High-accuracy extraction for sales leads
# Use Claude for best OCR quality
curl -X POST /batch/folder -d '{
  "localFolderPath": "/sales/leads/jan2025",
  "sheetId": "crm-import",
  "model": "anthropic/claude-3.5-sonnet",
  "maxFiles": 50,
  "concurrency": 3
}'
```

### Use Case 3: Testing New Model
```bash
# Dry-run to compare models
curl -X POST /batch/folder -d '{
  "driveFolderId": "test-cards",
  "model": "openai/gpt-4o",
  "dryRun": true,
  "maxFiles": 10
}'
```

---

## Final Notes

This prompt provides a complete specification for building a production-grade business card extraction system that mirrors your n8n workflow but with significant enhancements:

1. **Better Performance**: Batch processing with concurrency
2. **More Flexibility**: Runtime model selection from allowlist
3. **Better Observability**: Structured logging and detailed reports
4. **Better Testing**: Automated test suite
5. **Better Deployment**: Docker + docker-compose ready

The system should be built with **clean architecture**, **type hints**, **comprehensive error handling**, and **extensive documentation**.

All code must be **runnable out-of-the-box** after setting environment variables.
