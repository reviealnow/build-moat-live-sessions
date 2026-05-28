# QR Code Generator Prototype

## System Requirements

Build a dynamic QR code system where:
- Users submit a long URL and get back a short URL token + QR code image
- The QR code encodes a short URL that redirects (302) to the original URL via your server
- Users can modify the target URL after QR code creation
- Users can delete a QR code (soft delete)
- Users can optionally set an expiration timestamp on create or update
- Deleted or expired links return appropriate HTTP status codes
- URL validation: format check, normalization, malicious URL blocking

## Design Questions

Answer these before you start coding:

1. **Static vs Dynamic QR Code:** Why does this system use dynamic QR codes (encode short URL) instead of static (encode original URL directly)? When would you choose static instead?

   **Answer:** Dynamic QR codes encode a short URL (e.g. `https://yourapp.com/r/abc123`) that points back to our server, so the actual destination lives in the database and can be changed, disabled, or tracked at any time — without reprinting the QR code. Static QR codes encode the final URL directly into the image, so they cannot be updated after printing. Choose static when the destination is permanent, analytics are not needed, and the device scanning it may be offline (e.g. Wi-Fi password on a router sticker).

2. **Token Generation:** How will you generate short URL tokens? What happens when two different URLs produce the same token? How does collision probability change as the number of tokens grows?

   **Answer:** We use SHA-256 hash of `(url + time_ns nonce)` encoded in Base62, truncated to 7 characters (62^7 ≈ 3.5 trillion combinations). On each attempt we check the database for a collision; if one is found we vary the nonce and retry (up to 10 times). Collision probability follows the birthday paradox: negligible at 1M tokens (~0.09%), but starts to matter around 100M tokens — at that point we'd extend the token length from 7 to 8 characters.

3. **Redirect Strategy:** Why 302 (temporary) instead of 301 (permanent)? What are the trade-offs for analytics, URL modification, and latency?

   **Answer:** 302 tells browsers and proxies not to cache the redirect, so every scan hits our server — enabling accurate analytics counts and allowing the destination URL to be changed at any time. 301 (permanent) causes browsers to cache the redirect locally, which means subsequent scans bypass our server entirely: analytics break, and even if we update the destination in the database the old cached URL is still used. The trade-off is one extra network round-trip per scan, which is acceptable for a dynamic system.

4. **URL Normalization:** What normalization rules do you need? Why is `http://Example.com/` and `https://example.com` potentially the same URL?

   **Answer:** `http://Example.com/` and `https://example.com` are functionally identical because hostnames are case-insensitive and the trailing slash on a root path is redundant. Our normalization rules: (1) upgrade scheme to `https`, (2) lowercase the hostname, (3) remove default ports (`:80`, `:443`), (4) strip trailing slash from root path. We also block `javascript:` / `data:` schemes and private IP ranges (SSRF prevention). Without normalization, the same destination would create multiple tokens.

5. **Error Semantics:** What should happen when someone scans a deleted link vs a non-existent link? Should the HTTP status codes be different?

   **Answer:** Yes, they must be different. `410 Gone` means the resource existed but has been permanently removed — used for soft-deleted or expired QR codes. `404 Not Found` means the token never existed — used when someone scans a random or mistyped token. The distinction matters for search engines (410 signals "remove from index"; 404 means "try again later"), for API clients deciding whether to retry, and for end-user experience ("this link was deactivated" vs "this link doesn't exist").

## Verification

Your prototype should pass all of these:

```bash
# Create a QR code
curl -X POST http://localhost:8000/api/qr/create \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}'
# → 200, returns {"token": "...", "short_url": "...", "qr_code_url": "...", "original_url": "..."}

# Redirect
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 302

# Get info
curl http://localhost:8000/api/qr/{token}
# → 200, returns token metadata

# Update target URL
curl -X PATCH http://localhost:8000/api/qr/{token} \
  -H "Content-Type: application/json" \
  -d '{"url": "https://new-url.com"}'
# → 200

# Redirect now goes to new URL
curl -o /dev/null -w "%{redirect_url}" http://localhost:8000/r/{token}
# → https://new-url.com

# Delete
curl -X DELETE http://localhost:8000/api/qr/{token}
# → 200

# Redirect after delete
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/{token}
# → 410

# Non-existent token
curl -o /dev/null -w "%{http_code}" http://localhost:8000/r/INVALID
# → 404

# QR code image
# (create a new one first, then)
curl -o /dev/null -w "%{http_code} %{content_type}" http://localhost:8000/api/qr/{token}/image
# → 200 image/png

# Analytics
curl http://localhost:8000/api/qr/{token}/analytics
# → 200, returns {"token": "...", "total_scans": N, "scans_by_day": [...]}
```

## Suggested Tech Stack

Python + FastAPI recommended, but you may use any language/framework.
