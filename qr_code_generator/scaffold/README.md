# QR Code Generator

A FastAPI-based QR code generation service with short URL redirect, scan analytics, rate limiting, and expiry support.

## Features

- **Generate QR codes** — input any URL, get a short link + scannable QR image
- **Short URL redirect** — `/r/{token}` redirects to the original URL
- **Expiry support** — optionally set an expiration datetime; expired links return `410 Gone`
- **Soft delete** — delete a QR entry without removing DB records
- **Scan analytics** — track total scans and daily scan counts per token
- **Rate limiting** — 10 requests/minute per IP (via slowapi)
- **URL validation** — scheme check (http/https only), domain blocklist, URL normalization
- **In-memory cache** — non-expiring tokens are cached to skip DB on redirect

## Tech Stack

| Layer | Library |
|---|---|
| Web framework | FastAPI |
| ASGI server | Uvicorn |
| ORM | SQLAlchemy 2.x |
| Database | SQLite |
| QR generation | qrcode[pil] |
| Rate limiting | slowapi |

## Getting Started

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
uvicorn app.main:app --reload
```

Open http://localhost:8000 in your browser.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `POST` | `/api/qr/create` | Create QR code + short URL |
| `GET` | `/r/{token}` | Redirect to original URL |
| `GET` | `/api/qr/{token}` | Get QR entry info |
| `PATCH` | `/api/qr/{token}` | Update URL or expiry |
| `DELETE` | `/api/qr/{token}` | Soft-delete QR entry |
| `GET` | `/api/qr/{token}/image` | Get QR code PNG image |
| `GET` | `/api/qr/{token}/analytics` | Get scan analytics |

### Create QR Code

```bash
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "expires_at": "2026-12-31T23:59:59"}'
```

Response:
```json
{
  "token": "aB3xY9z",
  "short_url": "http://localhost:8000/r/aB3xY9z",
  "qr_code_url": "http://localhost:8000/api/qr/aB3xY9z/image",
  "original_url": "https://example.com"
}
```

## Project Structure

```
scaffold/
├── app/
│   ├── main.py          # FastAPI app entry point
│   ├── routes.py        # All API routes
│   ├── database.py      # SQLite connection (SQLAlchemy)
│   ├── models.py        # ORM models: UrlMapping, ScanEvent
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── token_gen.py     # SHA-256 + Base62 token generator
│   ├── url_validator.py # URL validation and normalization
│   └── limiter.py       # Rate limiter setup
└── requirements.txt
```

## Notes

- This is a **local prototype** — the SQLite database and `BASE_URL` are configured for localhost.
- Token generation uses SHA-256 with a nanosecond nonce and Base62 encoding, with collision retry up to 10 times.
