# QR Code Generator — Exercise

## How to Use

1. Read `PROMPT.md`
2. Answer the Design Questions (write your answers directly in `PROMPT.md`)
3. Build the prototype:
   - **Challenge Track:** Build from scratch using `PROMPT.md` as your spec
   - **Guided Track:** Go to `scaffold/`, fill in the TODOs
4. Verify with the curl tests at the bottom of `PROMPT.md`
5. Bring your Design Questions answers to live session for discussion

## Choose Your Track

**Challenge Track** — You decide the architecture, file structure, and implementation. Any language/framework is OK (Python + FastAPI recommended). Read `PROMPT.md` to get started.

**Guided Track** — File structure and boilerplate are provided. Fill in the core logic marked with `TODO`. Go to `scaffold/` and follow the instructions below.

## Guided Track Setup

**Prerequisite:** Python 3.10 or higher

```bash
cd scaffold
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Files to Fill In

| File | TODO | Design Decision |
|------|------|-----------------|
| `app/token_gen.py` | `generate_token()` | How to generate unique, URL-safe short tokens |
| `app/url_validator.py` | `validate_url()` | URL normalization and malicious URL blocking |
| `app/routes.py` | `redirect()` | Cache → DB lookup → 410/404 fallback flow |

### Run and Verify

```bash
uvicorn app.main:app --reload
```

Then run the verification tests from `PROMPT.md`.

## Bonus Challenges

- Build a simple frontend (input URL → display QR code image)
- Add rate limiting to the create endpoint
- Add expiration support with automatic 410 responses

---

## Completed Implementation (2026-05-14)

This section documents the actual setup steps used to get the scaffold running end-to-end, including bonus challenges.

### Prerequisites

- Python 3.10+
- `pip` (bundled with Python)

### Full Setup

```bash
# 1. Clone / enter the project
cd qr_code_generator/scaffold

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows

# 3. Install dependencies (includes slowapi for rate limiting)
pip install -r requirements.txt

# 4. Start the server
uvicorn app.main:app --reload
```

The server starts at `http://localhost:8000`.  
SQLite database (`qr_code.db`) is created automatically on first launch.

### What's Running

| URL | Description |
|-----|-------------|
| `http://localhost:8000/` | Frontend — paste a URL, get a QR code |
| `http://localhost:8000/api/qr/create` | `POST` — create a new QR code |
| `http://localhost:8000/r/{token}` | `GET` — redirect to original URL |
| `http://localhost:8000/api/qr/{token}` | `GET` / `PATCH` / `DELETE` — manage a QR code |
| `http://localhost:8000/api/qr/{token}/image` | `GET` — download QR code as PNG |
| `http://localhost:8000/api/qr/{token}/analytics` | `GET` — scan count by day |
| `http://localhost:8000/docs` | Swagger UI — interactive API docs |

### Storage

| Data | Where |
|------|-------|
| Token ↔ URL mappings, expiry, deleted state | `qr_code.db` (SQLite, persisted to disk) |
| Per-scan records (for analytics) | `qr_code.db` → `scan_events` table |
| Redirect cache | In-memory `dict` — cleared on server restart |
| Rate limit counters | In-memory (slowapi) — cleared on server restart |

### Implemented TODOs

| File | Function | Implementation |
|------|----------|----------------|
| `app/token_gen.py` | `generate_token()` | SHA-256 of `(url + time_ns nonce)` → Base62, 7 chars, retry up to 10× on collision |
| `app/url_validator.py` | `validate_url()` | Validates scheme/length/blocklist; normalizes to `https`, lowercase host, strips default port and trailing slash |
| `app/routes.py` | `redirect()` | Cache-first → DB fallback; returns 302 on hit, 404 if not found, 410 if deleted or expired |

### Implemented Bonus Challenges

| Bonus | Details |
|-------|---------|
| Frontend | `GET /` returns an HTML page — input URL + optional expiry, displays QR image and short URL |
| Rate limiting | `slowapi` — `POST /api/qr/create` limited to **10 requests / minute / IP**; returns `429` on excess |
| Expiration | Pass `expires_at` (ISO 8601) on create or update; expired links return `410 Gone` on redirect |

### Known Behavior

- Tokens with `expires_at` are **not** cached in the redirect cache — every hit goes to the DB to check expiry. Tokens with no expiry are cached after the first DB lookup.
- The in-memory redirect cache and rate limit counters reset on every server restart. For production, replace with Redis.
- `qr_code.db` persists across restarts. Delete it to reset all data.
