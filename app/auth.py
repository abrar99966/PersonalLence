"""Optional Google sign-in gate.

Auth is ENABLED only when GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are set in the
environment (i.e. in the cloud deploy). Locally, with no env vars, the app runs
open as before — so `run.ps1` still works without any Google setup.

Any Google account may sign in (no domain restriction). Set ALLOWED_EMAILS to a
comma-separated list to restrict to specific accounts.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")
# optional allow-list; empty = any Google account
ALLOWED_EMAILS = {e.strip().lower() for e in os.getenv("ALLOWED_EMAILS", "").split(",") if e.strip()}

AUTH_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

# paths reachable without a session
_OPEN_PATHS = ("/login", "/auth/callback", "/logout", "/health")

_LOGIN_PAGE = """<!doctype html><meta charset=utf-8>
<title>Parallax — sign in</title>
<style>
 body{margin:0;height:100vh;display:grid;place-items:center;background:
   radial-gradient(120% 90% at 50% 30%,#141d38,#06080f);color:#e6edf3;
   font:16px system-ui}
 .card{text-align:center;padding:40px 48px;border:1px solid #30363d;border-radius:16px;
   background:rgba(20,28,48,.5);backdrop-filter:blur(6px)}
 h1{margin:0 0 6px;font-size:26px} p{color:#8b949e;margin:0 0 24px}
 a.btn{display:inline-flex;gap:10px;align-items:center;background:#fff;color:#1f2328;
   text-decoration:none;padding:11px 18px;border-radius:10px;font-weight:600}
</style>
<div class=card>
 <h1>✦ Parallax</h1>
 <p>Triangulate a digital footprint across the galaxy.</p>
 <a class=btn href="/login">
   <svg width=18 height=18 viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.6l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.4 5.4 2.5 13.3l7.8 6.1C12.2 13.7 17.6 9.5 24 9.5z"/><path fill="#4285F4" d="M46.1 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.4c-.5 2.9-2.1 5.3-4.6 7l7.1 5.5C43.3 37.5 46.1 31.6 46.1 24.5z"/><path fill="#FBBC05" d="M10.3 28.6c-.5-1.4-.8-2.9-.8-4.6s.3-3.2.8-4.6l-7.8-6.1C.9 16.5 0 20.1 0 24s.9 7.5 2.5 10.7l7.8-6.1z"/><path fill="#34A853" d="M24 48c6.2 0 11.4-2 15.2-5.5l-7.1-5.5c-2 1.3-4.6 2.1-8.1 2.1-6.4 0-11.8-4.2-13.7-9.9l-7.8 6.1C6.4 42.6 14.6 48 24 48z"/></svg>
   Sign in with Google
 </a>
</div>"""

oauth = None


def setup_auth(app: FastAPI) -> None:
    """Wire session middleware + Google OAuth routes onto the app."""

    @app.middleware("http")
    async def gate(request: Request, call_next):
        if AUTH_ENABLED and not any(request.url.path.startswith(p) for p in _OPEN_PATHS):
            if not request.session.get("user"):
                if request.url.path.startswith("/api"):
                    return JSONResponse({"detail": "authentication required"}, status_code=401)
                return login_html()   # landing page with the Google button
        return await call_next(request)

    # Added AFTER the gate so SessionMiddleware is the outer layer — the gate must
    # see request.session already populated.
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax",
                       https_only=AUTH_ENABLED)

    @app.get("/health")
    async def health():
        return {"ok": True, "auth": AUTH_ENABLED}

    if not AUTH_ENABLED:
        return  # open mode — no Google routes needed

    global oauth
    from authlib.integrations.starlette_client import OAuth
    oauth = OAuth()
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )

    def redirect_uri(request: Request) -> str:
        # explicit override (set this on the host to your public callback URL)
        env = os.getenv("OAUTH_REDIRECT_URL")
        if env:
            return env
        return str(request.url_for("auth_callback"))

    @app.get("/login")
    async def login(request: Request):
        if request.session.get("user"):
            return RedirectResponse("/")
        return await oauth.google.authorize_redirect(request, redirect_uri(request))

    @app.get("/auth/callback", name="auth_callback")
    async def auth_callback(request: Request):
        try:
            token = await oauth.google.authorize_access_token(request)
        except Exception:
            return RedirectResponse("/login")
        info = token.get("userinfo") or {}
        email = (info.get("email") or "").lower()
        if not email or (ALLOWED_EMAILS and email not in ALLOWED_EMAILS):
            return HTMLResponse("<h3>Access denied for this account.</h3>"
                                "<a href='/logout'>try another</a>", status_code=403)
        request.session["user"] = {"email": email, "name": info.get("name"),
                                   "picture": info.get("picture")}
        return RedirectResponse("/")

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login")


def login_html() -> HTMLResponse:
    return HTMLResponse(_LOGIN_PAGE)
