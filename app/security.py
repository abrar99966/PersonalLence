"""Security headers + a simple per-IP rate limiter."""
from __future__ import annotations

import time

# CSP: the app ships one inline <script>/<style> block, so inline is allowed, but
# everything else is locked to same-origin (plus https images for Google avatars).
_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "object-src 'none'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "connect-src 'self'; "
    "form-action 'self' https://accounts.google.com"
)

SECURITY_HEADERS = {
    "Content-Security-Policy": _CSP,
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), browsing-topics=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-XSS-Protection": "0",  # modern browsers: rely on CSP, disable legacy auditor
}


# ---- per-IP sliding-window rate limiter (in-memory) ----
_hits: dict[str, list[float]] = {}


def client_ip(request) -> str:
    """Real client IP, honoring the proxy's X-Forwarded-For (HF/Cloudflare/Render)."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(ip: str, limit: int, window: float) -> bool:
    """True if `ip` has already made `limit` hits within the last `window` seconds."""
    now = time.monotonic()
    q = _hits.setdefault(ip, [])
    cutoff = now - window
    while q and q[0] < cutoff:
        q.pop(0)
    if len(q) >= limit:
        return True
    q.append(now)
    # opportunistic cleanup so the dict can't grow unbounded
    if len(_hits) > 4096:
        for k in [k for k, v in list(_hits.items()) if not v or v[-1] < cutoff]:
            _hits.pop(k, None)
    return False
