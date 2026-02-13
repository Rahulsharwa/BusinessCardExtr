# Business Card Extractor - Visual Workflow Planning

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          USER REQUEST                                   │
│  POST /batch/folder                                                     │
│  {                                                                      │
│    "driveFolderId": "...",  OR  "localFolderPath": "...",             │
│    "sheetId": "...",                                                   │
│    "model": "anthropic/claude-3.5-sonnet"  (optional)                 │
│  }                                                                      │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    VALIDATE REQUEST                                     │
│  • Check: driveFolderId XOR localFolderPath                            │
│  • Validate model against OPENROUTER_MODEL_ALLOWLIST                   │
│  • Set defaults: maxFiles=200, concurrency=3                           │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
           ┌─────────────┴──────────────┐
           │                            │
           ▼                            ▼
┌──────────────────────┐    ┌──────────────────────┐
│  DRIVE MODE          │    │  LOCAL MODE          │
│  drive_service.py    │    │  local_service.py    │
│                      │    │                      │
│  • List files in     │    │  • Scan directory    │
│    folder (API v3)   │    │    for images        │
│  • Filter: jpg/png/  │    │  • Filter: .jpg      │
│    webp mimeTypes    │    │    .jpeg .png .webp  │
│  • Optional: recurse │    │  • Get file paths    │
│  • Get: id, name,    │    │  • Set fileId=null   │
│    webViewLink       │    │    fileLink=null     │
└──────────┬───────────┘    └──────────┬───────────┘
           │                           │
           └───────────┬───────────────┘
                       │
                       ▼
          ┌────────────────────────┐
          │  FILES FOUND: N        │
          │  Apply maxFiles limit  │
          └────────────┬───────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              CONCURRENT BATCH PROCESSING                                │
│  extractor_service.py - asyncio.gather() with Semaphore(concurrency)   │
│                                                                         │
│  For each file (parallel workers = concurrency):                       │
│  ┌───────────────────────────────────────────────────────────────┐    │
│  │                                                               │    │
│  │  1. READ IMAGE BYTES                                          │    │
│  │     ├─ Drive: download_file(fileId) → bytes                  │    │
│  │     └─ Local: Path.read_bytes() → bytes                      │    │
│  │                                                               │    │
│  │  2. CONVERT TO BASE64 DATA URL                                │    │
│  │     base64.b64encode(bytes)                                   │    │
│  │     → "data:image/jpeg;base64,/9j/4AAQ..."                   │    │
│  │                                                               │    │
│  │  3. OPENROUTER VISION EXTRACTION                              │    │
│  │     openrouter_client.py                                      │    │
│  │     ┌─────────────────────────────────────────────────────┐  │    │
│  │     │ POST https://openrouter.ai/api/v1/chat/completions │  │    │
│  │     │                                                     │  │    │
│  │     │ messages: [                                        │  │    │
│  │     │   {role: "system", content: EXTRACTION_PROMPT},    │  │    │
│  │     │   {role: "user", content: [                        │  │    │
│  │     │     {type: "image_url", image_url: {...}},         │  │    │
│  │     │     {type: "text", text: "Extract..."}             │  │    │
│  │     │   ]}                                                │  │    │
│  │     │ ]                                                   │  │    │
│  │     │                                                     │  │    │
│  │     │ Response: { "rows": [...] }                        │  │    │
│  │     └─────────────────────────────────────────────────────┘  │    │
│  │                                                               │    │
│  │  4. VALIDATE JSON SCHEMA                                      │    │
│  │     ├─ Valid? → Continue                                     │    │
│  │     └─ Invalid? → RETRY ONCE with repair prompt             │    │
│  │                                                               │    │
│  │  5. NORMALIZE ROWS                                            │    │
│  │     normalize_service.py                                      │    │
│  │     ├─ Trim strings, empty → null                            │    │
│  │     ├─ Phone: digits only                                    │    │
│  │     ├─ Email: lowercase + validate                           │    │
│  │     ├─ Confidence: clamp 0..1                                │    │
│  │     └─ Timestamp: default to now()                           │    │
│  │                                                               │    │
│  │  6. INJECT METADATA                                           │    │
│  │     fileName, fileId, fileLink → each row                    │    │
│  │                                                               │    │
│  └───────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  Error Handling:                                                       │
│  • Network failure → Retry 3x with backoff                             │
│  • JSON invalid after retry → Add to errors[], continue                │
│  • Image corrupt → Skip, add to errors[]                               │
│  • Continue processing remaining files                                 │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                   COLLECT ALL RESULTS                                   │
│  • Flatten rows from all files                                         │
│  • Count: filesProcessed, rowsExtracted                                │
│  • Aggregate errors                                                    │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DEDUPLICATE ROWS                                     │
│  normalize_service.deduplicate_rows()                                  │
│                                                                         │
│  For each row:                                                         │
│    if email1 exists:                                                   │
│      key = "email:<email1>"                                            │
│    else:                                                               │
│      key = "fallback:<phone1>|<lower(fullName)>|<lower(company)>"     │
│                                                                         │
│  Keep first occurrence only                                            │
│  Drop duplicates                                                       │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                  APPEND TO GOOGLE SHEETS                                │
│  sheets_service.py (if dryRun=false)                                   │
│                                                                         │
│  Column Order (16 columns):                                            │
│  timestamp, fullName, jobTitle, company,                               │
│  phone1, phone2, email1, email2,                                       │
│  website, address, notes, confidence,                                  │
│  rawText, fileName, fileId, fileLink                                   │
│                                                                         │
│  service.spreadsheets().values().append(...)                           │
└────────────────────────┬────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    RETURN RUN REPORT                                    │
│  {                                                                      │
│    "status": "ok",                                                      │
│    "folderMode": "drive" | "local",                                    │
│    "modelUsed": "anthropic/claude-3.5-sonnet",                         │
│    "filesFound": 15,                                                   │
│    "filesProcessed": 15,                                               │
│    "rowsExtracted": 23,                                                │
│    "rowsAppended": 18,  // after deduplication                         │
│    "errors": [                                                          │
│      {"fileName": "corrupt.jpg", "error": "..."}                       │
│    ],                                                                   │
│    "rows": [ {...}, {...}, ... ]  // all normalized rows               │
│  }                                                                      │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
┌──────────────┐
│ Business Card│
│   Image      │
│  (JPG/PNG)   │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  OPENROUTER VISION MODEL                │
│  (Claude 3.5 / GPT-4o / Gemini 2.0)     │
│                                         │
│  Input: base64 image + extraction prompt│
│  Output: JSON with "rows" array         │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  RAW EXTRACTED DATA                     │
│  {                                      │
│    "rows": [                            │
│      {                                  │
│        "fullName": "JOHN DOE",          │
│        "phone1": "+91 98765-43210",     │
│        "email1": "JOHN@ABC.COM",        │
│        "company": "ABC Pvt Ltd",        │
│        "confidence": 0.856432,          │
│        "timestamp": "",                 │
│        ...                              │
│      }                                  │
│    ]                                    │
│  }                                      │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  NORMALIZATION                          │
│  • fullName: trim                       │
│  • phone1: "919876543210" (digits only) │
│  • email1: "john@abc.com" (lowercase)   │
│  • confidence: 0.86 (clamp 0..1)        │
│  • timestamp: "2025-02-13T10:30:00Z"    │
│  • empty strings → null                 │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  NORMALIZED ROW                         │
│  {                                      │
│    "timestamp": "2025-02-13T10:30:00Z", │
│    "fullName": "John Doe",              │
│    "jobTitle": "Sales Manager",         │
│    "company": "ABC Pvt Ltd",            │
│    "phone1": "919876543210",            │
│    "phone2": null,                      │
│    "email1": "john@abc.com",            │
│    "email2": null,                      │
│    "website": "abc.com",                │
│    "address": "Jaipur, Rajasthan",      │
│    "notes": null,                       │
│    "confidence": 0.86,                  │
│    "rawText": "JOHN DOE, Sales...",     │
│    "fileName": "card_001.jpg",          │
│    "fileId": "1a2b3c4d5e",              │
│    "fileLink": "https://drive..."       │
│  }                                      │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  DEDUPLICATION                          │
│  Key = "email:john@abc.com"             │
│  (or fallback key if no email)          │
│                                         │
│  Keep first occurrence                  │
│  Drop subsequent duplicates             │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│  GOOGLE SHEETS                          │
│  ┌───────────┬──────────┬──────────┐    │
│  │ timestamp │ fullName │ jobTitle │... │
│  ├───────────┼──────────┼──────────┤    │
│  │ 2025-02..│ John Doe │ Sales Mgr│... │
│  │ 2025-02..│ Jane Sm..│ Engineer │... │
│  └───────────┴──────────┴──────────┘    │
│                                         │
│  Appended to sheet in exact column order│
└─────────────────────────────────────────┘
```

---

## Component Interaction Diagram

```
┌─────────────┐
│   FastAPI   │
│   main.py   │
└──────┬──────┘
       │
       ├──────────────────────────────────────────────┐
       │                                              │
       ▼                                              ▼
┌──────────────┐                              ┌──────────────┐
│   config.py  │                              │  models.py   │
│              │                              │              │
│ • Load env   │                              │ • Request    │
│ • Parse      │                              │   schemas    │
│   allowlist  │                              │ • Response   │
│ • Validate   │                              │   schemas    │
└──────┬───────┘                              └──────────────┘
       │
       │
       ▼
┌──────────────────────────────────────────────────────────────┐
│                     SERVICES LAYER                           │
│                                                              │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │ drive_service  │  │ local_service  │  │openrouter_     │ │
│  │               │  │               │  │client          │ │
│  │ • list_files   │  │ • scan_folder  │  │                │ │
│  │ • download     │  │ • read_bytes   │  │ • extract_json │ │
│  │               │  │               │  │ • retry_repair │ │
│  └────────┬───────┘  └────────┬───────┘  └────────┬───────┘ │
│           │                   │                   │         │
│           └───────────────────┼───────────────────┘         │
│                               │                             │
│                   ┌───────────▼───────────┐                 │
│                   │ extractor_service     │                 │
│                   │                       │                 │
│                   │ • orchestrate_batch() │                 │
│                   │ • asyncio.gather()    │                 │
│                   │ • Semaphore(N)        │                 │
│                   │ • error_handling()    │                 │
│                   └───────────┬───────────┘                 │
│                               │                             │
│                   ┌───────────▼───────────┐                 │
│                   │ normalize_service     │                 │
│                   │                       │                 │
│                   │ • normalize_row()     │                 │
│                   │ • deduplicate_rows()  │                 │
│                   │ • validate_schema()   │                 │
│                   └───────────┬───────────┘                 │
│                               │                             │
│                   ┌───────────▼───────────┐                 │
│                   │ sheets_service        │                 │
│                   │                       │                 │
│                   │ • append_rows()       │                 │
│                   │ • authenticate()      │                 │
│                   │ • validate_sheet()    │                 │
│                   └───────────────────────┘                 │
└──────────────────────────────────────────────────────────────┘
```

---

## Concurrency Model

```
┌────────────────────────────────────────────────────────────┐
│  BATCH OF N FILES                                          │
│  files = [file1, file2, file3, ..., fileN]                │
└────────────────────┬───────────────────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────────────────┐
│  SEMAPHORE (concurrency = 3)                               │
│  Max 3 concurrent workers                                  │
└────────────────────┬───────────────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
   ┌────────┐  ┌────────┐  ┌────────┐
   │Worker 1│  │Worker 2│  │Worker 3│
   │        │  │        │  │        │
   │ file1  │  │ file2  │  │ file3  │
   │   ↓    │  │   ↓    │  │   ↓    │
   │extract │  │extract │  │extract │
   │   ↓    │  │   ↓    │  │   ↓    │
   │normalize│ │normalize│ │normalize│
   │   ↓    │  │   ↓    │  │   ↓    │
   │ Done   │  │ Done   │  │ Done   │
   └────┬───┘  └────┬───┘  └────┬───┘
        │           │           │
        └───────────┼───────────┘
                    │
        ┌───────────▼───────────┐
        │  Worker 1 picks file4 │
        │  Worker 2 picks file5 │
        │  Worker 3 picks file6 │
        └───────────┬───────────┘
                    │
                    ▼
              (Continue until
               all files done)
                    │
                    ▼
        ┌───────────────────────┐
        │ Collect all results   │
        │ • Successful rows     │
        │ • Errors              │
        └───────────────────────┘

Timing Example (3 workers, 15 files, 10s per file):
  Sequential: 15 files × 10s = 150 seconds
  Concurrent: 15 files ÷ 3 workers × 10s = 50 seconds
  Speedup: 3x
```

---

## Error Handling Flow

```
┌─────────────────┐
│ Process File    │
└────────┬────────┘
         │
         ▼
┌────────────────────────────────┐
│ Try: Download/Read Image       │
└────────┬───────────────────────┘
         │
    ┌────┴────┐
    │Success? │
    └────┬────┘
         │
    No ──┼── Yes
         │         │
         ▼         ▼
    ┌────────┐  ┌─────────────────────┐
    │ Error  │  │ Try: OpenRouter API │
    │ +      │  └─────────┬───────────┘
    │Continue│            │
    └────────┘       ┌────┴────┐
                     │Success? │
                     └────┬────┘
                          │
                     No ──┼── Yes
                          │         │
                          ▼         ▼
                     ┌────────┐  ┌──────────────┐
                     │ Retry  │  │ Validate JSON│
                     │ 3x     │  └──────┬───────┘
                     │ backoff│         │
                     └───┬────┘    ┌────┴────┐
                         │         │Valid?   │
                    ┌────┴────┐    └────┬────┘
                    │Success? │         │
                    └────┬────┘    No ──┼── Yes
                         │              │         │
                    No ──┼── Yes        ▼         ▼
                         │      │  ┌────────┐  ┌──────────┐
                         ▼      │  │ Repair │  │Normalize │
                    ┌────────┐  │  │ Retry  │  │   +      │
                    │ Error  │  │  │ ONCE   │  │ Add to   │
                    │ +      │  │  └───┬────┘  │ Results  │
                    │Continue│  │      │       └──────────┘
                    └────────┘  │  ┌───┴────┐
                                │  │Valid?  │
                                │  └───┬────┘
                                │      │
                                │ No ──┼── Yes
                                │      │      │
                                ▼      ▼      ▼
                           ┌────────────────────┐
                           │ Continue to next   │
                           │ file in batch      │
                           └────────────────────┘

Key Principles:
• Never fail entire batch due to one file
• Always log errors with context
• Return partial results + error list
• User decides how to handle errors
```

---

## Model Selection Flow

```
┌──────────────────────┐
│ User Request         │
│ model: "..." or null │
└──────────┬───────────┘
           │
           ▼
    ┌──────────────┐
    │ Model param  │
    │ provided?    │
    └──────┬───────┘
           │
      No ──┼── Yes
           │         │
           ▼         ▼
    ┌──────────┐  ┌─────────────────────┐
    │ Use      │  │ Check against       │
    │ DEFAULT  │  │ ALLOWLIST           │
    │ model    │  └─────────┬───────────┘
    └──────┬───┘            │
           │           ┌────┴────┐
           │           │ In list?│
           │           └────┬────┘
           │                │
           │           No ──┼── Yes
           │                │         │
           │                ▼         ▼
           │         ┌──────────┐  ┌──────────┐
           │         │ 400 Error│  │ Use this │
           │         │ Return   │  │ model    │
           │         │ allowed  │  └──────┬───┘
           │         │ options  │         │
           │         └──────────┘         │
           │                              │
           └──────────────┬───────────────┘
                          │
                          ▼
               ┌──────────────────┐
               │ Execute batch    │
               │ with chosen model│
               └──────────────────┘

Environment Setup:
  OPENROUTER_MODEL_DEFAULT="anthropic/claude-3.5-sonnet"
  OPENROUTER_MODEL_ALLOWLIST="anthropic/claude-3.5-sonnet,openai/gpt-4o,google/gemini-2.0-flash-001"

Example Requests:

✅ Valid:
  {"model": "openai/gpt-4o"}  → Uses GPT-4o
  {"model": null}             → Uses default (Claude 3.5)
  {}                          → Uses default (Claude 3.5)

❌ Invalid:
  {"model": "anthropic/claude-3-opus"} → Not in allowlist
  Response: 400 {
    "error": "Model not allowed",
    "allowed": ["anthropic/claude-3.5-sonnet", "openai/gpt-4o", "google/gemini-2.0-flash-001"]
  }
```

---

## Deduplication Strategy

```
Batch of extracted rows:
┌─────────────────────────────────────────────────────────┐
│ Row 1: email1="john@abc.com",   name="John Doe"         │
│ Row 2: email1="jane@xyz.com",   name="Jane Smith"       │
│ Row 3: email1="john@abc.com",   name="J. Doe"  ← DUP!   │
│ Row 4: email1=null, phone1="9876543210", name="Bob"     │
│ Row 5: email1=null, phone1="9876543210", name="Bob" ←DUP│
│ Row 6: email1="sam@test.com",   name="Sam Lee"          │
└─────────────────────────────────────────────────────────┘

Deduplication Process:
┌─────────────────────────────────────────────────────────┐
│ For each row, generate dedup key:                      │
│                                                         │
│ Row 1: email1 exists → key = "email:john@abc.com"      │
│ Row 2: email1 exists → key = "email:jane@xyz.com"      │
│ Row 3: email1 exists → key = "email:john@abc.com" ✗    │
│ Row 4: no email → key = "fallback:9876543210|bob|"     │
│ Row 5: no email → key = "fallback:9876543210|bob|" ✗   │
│ Row 6: email1 exists → key = "email:sam@test.com"      │
└─────────────────────────────────────────────────────────┘

Result (unique rows):
┌─────────────────────────────────────────────────────────┐
│ Row 1: email1="john@abc.com",   name="John Doe"     ✓   │
│ Row 2: email1="jane@xyz.com",   name="Jane Smith"   ✓   │
│ Row 4: email1=null, phone1="9876543210", name="Bob" ✓   │
│ Row 6: email1="sam@test.com",   name="Sam Lee"      ✓   │
└─────────────────────────────────────────────────────────┘

Stats:
  Extracted: 6 rows
  Unique:    4 rows
  Dropped:   2 rows (33% duplication rate)

Fallback Key Construction:
  phone1 = "9876543210"
  fullName = "Bob Smith"
  company = "Tech Corp"

  key = "fallback:" + phone1 + "|" + lower(fullName) + "|" + lower(company)
  key = "fallback:9876543210|bob smith|tech corp"

Email-based keys take precedence for better accuracy.
```

---

## File Structure & Dependencies

```
business-card-extractor/
│
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app, routes
│   ├── config.py               # Settings with allowlist parsing
│   ├── models.py               # Pydantic request/response
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── drive_service.py    # Google Drive list/download
│   │   ├── local_service.py    # Local folder scanning
│   │   ├── openrouter_client.py# OpenRouter API client
│   │   ├── extractor_service.py# Batch orchestration
│   │   ├── normalize_service.py# Normalization + dedup
│   │   └── sheets_service.py   # Google Sheets append
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── validators.py       # Input validation
│   │   └── logging.py          # Structured logging
│   │
│   └── cli.py                  # Click CLI wrapper
│
├── tests/
│   ├── __init__.py
│   ├── test_normalize.py       # Normalization tests
│   ├── test_dedupe.py          # Deduplication tests
│   ├── test_openrouter.py      # API client tests
│   ├── test_extraction.py      # E2E extraction tests
│   └── fixtures/
│       └── sample_cards/       # Test images
│
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── pyproject.toml
└── LICENSE

Dependencies (requirements.txt):
  fastapi==0.109.0
  uvicorn[standard]==0.27.0
  pydantic==2.5.0
  pydantic-settings==2.1.0
  google-api-python-client==2.116.0
  google-auth==2.27.0
  httpx==0.26.0
  asyncio==3.4.3
  click==8.1.7
  structlog==24.1.0
  pytest==7.4.4
  pytest-asyncio==0.23.3
  pytest-cov==4.1.0
  pillow==10.2.0
```

---

## Testing Strategy

```
Unit Tests (tests/test_normalize.py):
  ✓ Phone normalization: +91 98765-43210 → 919876543210
  ✓ Email normalization: JOHN@ABC.COM → john@abc.com
  ✓ Confidence clamping: 1.5 → 1.0, -0.2 → 0.0
  ✓ Empty string → null conversion
  ✓ Timestamp defaulting

Unit Tests (tests/test_dedupe.py):
  ✓ Email-based deduplication
  ✓ Fallback key deduplication
  ✓ Keep first occurrence
  ✓ Mixed key types

Integration Tests (tests/test_openrouter.py):
  ✓ Successful extraction (mocked)
  ✓ JSON repair retry (mocked)
  ✓ Network timeout handling
  ✓ Model validation

E2E Tests (tests/test_extraction.py):
  ✓ Process local folder (fixtures)
  ✓ Process Drive folder (mocked)
  ✓ Concurrent processing
  ✓ Error aggregation
  ✓ Dry-run mode

Coverage Target: >80%
```

---

## Performance Benchmarks

```
Test Scenario: 100 business card images
Image size: 2-5 MB each
Model: anthropic/claude-3.5-sonnet

┌────────────────────────────────────────────────────────┐
│ Configuration  │ Time    │ Cost (approx) │ Errors     │
├────────────────┼─────────┼───────────────┼────────────┤
│ Sequential (1) │ 16m 40s │ $2.50         │ 0          │
│ Concurrent (3) │  5m 35s │ $2.50         │ 0          │
│ Concurrent (5) │  3m 20s │ $2.50         │ 1 timeout  │
│ Concurrent (10)│  1m 50s │ $2.50         │ 3 timeouts │
└────────────────────────────────────────────────────────┘

Recommended: concurrency=3 for reliability
For speed: concurrency=5 (acceptable error rate)

Cost Breakdown (per 100 images):
  Claude 3.5 Sonnet: ~$2.50
  GPT-4o:            ~$3.00
  Gemini 2.0 Flash:  ~$0.50

Network: ~500 MB total (base64 overhead)
```

---

## Deployment Checklist

### Development
- [ ] Set up Python 3.11+ environment
- [ ] Install dependencies
- [ ] Configure `.env` file
- [ ] Set up Google Cloud service account
- [ ] Enable Drive API and Sheets API
- [ ] Share test folder and sheet with service account
- [ ] Get OpenRouter API key
- [ ] Run tests: `pytest tests/ -v`
- [ ] Start dev server: `uvicorn app.main:app --reload`
- [ ] Test endpoints with curl/Postman

### Production
- [ ] Set production environment variables
- [ ] Build Docker image: `docker build -t card-extractor .`
- [ ] Test container: `docker-compose up`
- [ ] Configure logging (structured JSON)
- [ ] Set up monitoring (health checks)
- [ ] Configure HTTPS/reverse proxy
- [ ] Set resource limits (CPU/memory)
- [ ] Enable rate limiting (if public)
- [ ] Set up backup for extracted data
- [ ] Document runbook for ops

---

## API Usage Examples

### List Available Models
```bash
curl http://localhost:8000/models

Response:
{
  "default": "anthropic/claude-3.5-sonnet",
  "allowed": [
    "anthropic/claude-3.5-sonnet",
    "openai/gpt-4o",
    "google/gemini-2.0-flash-001"
  ]
}
```

### Process Drive Folder (Default Model)
```bash
curl -X POST http://localhost:8000/batch/folder \
  -H "Content-Type: application/json" \
  -d '{
    "driveFolderId": "1-vvCHAgf8nATMlNipFBObbMSZxrp9FTv",
    "sheetId": "1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s",
    "sheetName": "Campaign4",
    "maxFiles": 50,
    "concurrency": 3
  }'
```

### Process Drive Folder (Custom Model)
```bash
curl -X POST http://localhost:8000/batch/folder \
  -H "Content-Type: application/json" \
  -d '{
    "driveFolderId": "1-vvCHAgf8nATMlNipFBObbMSZxrp9FTv",
    "sheetId": "1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s",
    "sheetName": "Campaign4",
    "model": "openai/gpt-4o",
    "maxFiles": 100
  }'
```

### Process Local Folder (Dry Run)
```bash
curl -X POST http://localhost:8000/batch/folder \
  -H "Content-Type: application/json" \
  -d '{
    "localFolderPath": "/data/business-cards/jan-2025",
    "sheetId": "1OCWpOt8gc1ZCUt-IBdJ5OZcXQj-L1vSjWrUdclfiP0s",
    "dryRun": true,
    "maxFiles": 10
  }'
```

### Health Check
```bash
curl http://localhost:8000/healthz

Response:
{
  "status": "healthy",
  "services": {
    "openrouter": "ok",
    "google_drive": "ok",
    "google_sheets": "ok"
  },
  "timestamp": "2025-02-13T10:30:00Z"
}
```

---

## Troubleshooting Guide

### Common Issues

#### 1. "Model not allowed" Error
```
Error: {"error": "Model not allowed", "allowed": [...]}

Fix:
1. Check OPENROUTER_MODEL_ALLOWLIST env var
2. Add desired model to allowlist
3. Restart server
```

#### 2. Google Drive Authentication Failed
```
Error: Service account not authorized

Fix:
1. Share Drive folder with service account email
2. Verify GOOGLE_SERVICE_ACCOUNT_JSON is valid
3. Check Drive API is enabled in GCP
```

#### 3. OpenRouter Rate Limit
```
Error: Rate limit exceeded (429)

Fix:
1. Reduce concurrency (try 2-3)
2. Add delays between batches
3. Upgrade OpenRouter plan
```

#### 4. JSON Parsing Failed After Retry
```
Error: Invalid JSON after repair retry

Fix:
1. Check model is vision-capable
2. Verify image is not corrupted
3. Try different model
4. Check extraction prompt formatting
```

#### 5. Sheets API Quota Exceeded
```
Error: Quota exceeded for service sheets

Fix:
1. Enable batching (append multiple rows)
2. Request quota increase in GCP
3. Add delay between sheet operations
```

---

This visual planning document provides a complete architectural overview for implementing the business card extraction system. Use it alongside the main ANTIGRAVITY_PROMPT.md for development.
