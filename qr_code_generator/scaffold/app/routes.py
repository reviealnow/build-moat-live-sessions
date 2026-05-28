import io
from datetime import datetime

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .limiter import limiter
from .models import ScanEvent, UrlMapping
from .schemas import CreateRequest, CreateResponse, QRInfoResponse, UpdateRequest
from .token_gen import generate_token
from .url_validator import validate_url

router = APIRouter()

# In-memory cache (simulates Redis for prototype)
redirect_cache: dict[str, str] = {}

BASE_URL = "http://localhost:8000"


@router.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Code Generator</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: system-ui, sans-serif; background: #f5f5f5; display: flex; justify-content: center; padding: 48px 16px; }
    .card { background: white; border-radius: 12px; padding: 36px; width: 100%; max-width: 480px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
    h1 { font-size: 1.4rem; margin-bottom: 24px; color: #111; }
    label { display: block; font-size: 0.85rem; color: #555; margin-bottom: 6px; margin-top: 16px; }
    input { width: 100%; padding: 10px 12px; border: 1px solid #ddd; border-radius: 8px; font-size: 0.95rem; outline: none; }
    input:focus { border-color: #4f46e5; }
    button { margin-top: 20px; width: 100%; padding: 11px; background: #4f46e5; color: white; border: none; border-radius: 8px; font-size: 1rem; cursor: pointer; }
    button:hover { background: #4338ca; }
    button:disabled { background: #a5b4fc; cursor: not-allowed; }
    #result { margin-top: 28px; text-align: center; display: none; }
    #result img { width: 200px; height: 200px; border: 1px solid #eee; border-radius: 8px; }
    .meta { margin-top: 14px; font-size: 0.88rem; color: #444; text-align: left; background: #f9f9f9; border-radius: 8px; padding: 12px 14px; }
    .meta a { color: #4f46e5; word-break: break-all; }
    .meta span { font-weight: 600; }
    #error { margin-top: 16px; color: #dc2626; font-size: 0.88rem; background: #fef2f2; border-radius: 8px; padding: 10px 12px; display: none; }
  </style>
</head>
<body>
  <div class="card">
    <h1>QR Code Generator</h1>
    <form id="form">
      <label for="url">URL</label>
      <input type="url" id="url" placeholder="https://example.com" required>
      <label for="expires_at">Expiration (optional)</label>
      <input type="datetime-local" id="expires_at">
      <button type="submit" id="btn">Generate QR Code</button>
    </form>
    <div id="error"></div>
    <div id="result">
      <img id="qr-img" alt="QR Code">
      <div class="meta">
        <div>Short URL: <a id="short-url" target="_blank"></a></div>
        <div style="margin-top:6px">Token: <span id="token"></span></div>
        <div style="margin-top:6px">Original: <span id="original-url"></span></div>
      </div>
    </div>
  </div>
  <script>
    const form = document.getElementById('form');
    const btn = document.getElementById('btn');
    const resultDiv = document.getElementById('result');
    const errorDiv = document.getElementById('error');

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      btn.disabled = true;
      btn.textContent = 'Generating...';
      errorDiv.style.display = 'none';
      resultDiv.style.display = 'none';

      const body = { url: document.getElementById('url').value };
      const exp = document.getElementById('expires_at').value;
      if (exp) body.expires_at = new Date(exp).toISOString();

      try {
        const resp = await fetch('/api/qr/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!resp.ok) {
          errorDiv.textContent = data.detail || 'Something went wrong';
          errorDiv.style.display = 'block';
        } else {
          document.getElementById('qr-img').src = data.qr_code_url;
          const link = document.getElementById('short-url');
          link.href = data.short_url;
          link.textContent = data.short_url;
          document.getElementById('token').textContent = data.token;
          document.getElementById('original-url').textContent = data.original_url;
          resultDiv.style.display = 'block';
        }
      } catch (err) {
        errorDiv.textContent = 'Network error: ' + err.message;
        errorDiv.style.display = 'block';
      } finally {
        btn.disabled = false;
        btn.textContent = 'Generate QR Code';
      }
    });
  </script>
</body>
</html>"""


@router.post("/api/qr/create", response_model=CreateResponse)
@limiter.limit("10/minute")
def create_qr(req: CreateRequest, request: Request, db: Session = Depends(get_db)):
    try:                                                                                                                                                           
        normalized_url = validate_url(req.url)                
    except ValueError as e:                                                                                                                                        
        raise HTTPException(status_code=422, detail=str(e))
    token = generate_token(normalized_url, db)

    mapping = UrlMapping(
        token=token,
        original_url=normalized_url,
        expires_at=req.expires_at,
    )
    db.add(mapping)
    db.commit()

    short_url = f"{BASE_URL}/r/{token}"

    # Only cache tokens with no expiry — expiring tokens must always hit DB for the 410 check
    if req.expires_at is None:
        redirect_cache[token] = normalized_url

    return CreateResponse(
        token=token,
        short_url=short_url,
        qr_code_url=f"{BASE_URL}/api/qr/{token}/image",
        original_url=normalized_url,
    )


@router.get("/r/{token}")
def redirect(token: str, request: Request, db: Session = Depends(get_db)):
    """Redirect fallback flow: Cache -> DB -> 404/410 (from slides mermaid diagram)"""
    # Cache hit
    if token in redirect_cache:
        _record_scan(token, request, db)
        return RedirectResponse(url=redirect_cache[token], status_code=302)

    # Cache miss — query DB
    mapping = db.query(UrlMapping).filter(UrlMapping.token == token).first()

    if mapping is None:
        raise HTTPException(status_code=404, detail="Not Found")

    if mapping.is_deleted or (
        mapping.expires_at is not None and mapping.expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=410, detail="Gone")

    # Warm cache only if no expiry
    if mapping.expires_at is None:
        redirect_cache[token] = mapping.original_url
    _record_scan(token, request, db)
    return RedirectResponse(url=mapping.original_url, status_code=302)


@router.get("/api/qr/{token}", response_model=QRInfoResponse)
def get_qr_info(token: str, db: Session = Depends(get_db)):
    mapping = _get_mapping_or_404(token, db)
    return mapping


@router.patch("/api/qr/{token}", response_model=QRInfoResponse)
def update_qr(token: str, req: UpdateRequest, db: Session = Depends(get_db)):
    mapping = _get_mapping_or_404(token, db)

    if req.url is not None:
        try:
            mapping.original_url = validate_url(req.url)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        # Invalidate cache
        redirect_cache.pop(token, None)

    if req.expires_at is not None:
        mapping.expires_at = req.expires_at
        # Invalidate cache
        redirect_cache.pop(token, None)

    db.commit()
    db.refresh(mapping)
    return mapping


@router.delete("/api/qr/{token}")
def delete_qr(token: str, db: Session = Depends(get_db)):
    mapping = _get_mapping_or_404(token, db)
    mapping.is_deleted = True
    db.commit()
    # Invalidate cache
    redirect_cache.pop(token, None)
    return {"detail": "Deleted"}


@router.get("/api/qr/{token}/image")
def get_qr_image(token: str, db: Session = Depends(get_db)):
    _get_mapping_or_404(token, db)
    short_url = f"{BASE_URL}/r/{token}"

    img = qrcode.make(short_url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/api/qr/{token}/analytics")
def get_analytics(token: str, db: Session = Depends(get_db)):
    _get_mapping_or_404(token, db)

    total = db.query(func.count(ScanEvent.id)).filter(ScanEvent.token == token).scalar()

    daily = (
        db.query(
            func.date(ScanEvent.scanned_at).label("date"),
            func.count(ScanEvent.id).label("count"),
        )
        .filter(ScanEvent.token == token)
        .group_by(func.date(ScanEvent.scanned_at))
        .all()
    )

    return {
        "token": token,
        "total_scans": total,
        "scans_by_day": [{"date": str(row.date), "count": row.count} for row in daily],
    }


def _get_mapping_or_404(token: str, db: Session) -> UrlMapping:
    mapping = db.query(UrlMapping).filter(UrlMapping.token == token).first()
    if mapping is None or mapping.is_deleted:
        raise HTTPException(status_code=404, detail="Not Found")
    return mapping


def _record_scan(token: str, request: Request, db: Session):
    event = ScanEvent(
        token=token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
    )
    db.add(event)
    db.commit()
