"""
backend/middleware.py
---------------------
Security & observability middleware for arac-hasar-v2.

Owned by: Security Engineer.

Wire-up (in main.py):

    from middleware import install_security_middleware, limiter
    from slowapi.errors import RateLimitExceeded
    from slowapi import _rate_limit_exceeded_handler

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    install_security_middleware(app)

Then on routes:

    from middleware import limiter

    @router.post("/auth/login")
    @limiter.limit("5/minute")
    async def login(request: Request, ...): ...

    @router.post("/api/v1/inspect")
    @limiter.limit("60/minute", key_func=user_or_ip_key)
    async def inspect(request: Request, ...): ...

Components
==========
1. RequestIDMiddleware   - X-Request-ID propagation (accept inbound, mint if absent).
2. AccessLogMiddleware   - Structured JSON access log per request.
3. SecurityHeadersMiddleware - HSTS, CSP (API-deny-all), XFO, etc.
4. limiter               - slowapi Limiter; Redis storage if configured, in-memory otherwise.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from security import ALLOWED_ORIGINS, ENVIRONMENT, RATE_LIMIT_REDIS_URL, verify_token

access_log = logging.getLogger("backend.access")
sec_log = logging.getLogger("backend.security")


# ---------------------------------------------------------------------------
# Rate limiting (slowapi)
# ---------------------------------------------------------------------------

def user_or_ip_key(request: Request) -> str:
    """
    Rate-limit key:
      - If a valid access token is present, key by user_id (cross-IP fairness).
      - Otherwise fall back to client IP.
    """
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1].strip()
        try:
            payload = verify_token(token, expected_type="access")
            return f"user:{payload.sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=user_or_ip_key,
    default_limits=["200/minute"],          # global per-IP / per-user default
    storage_uri=RATE_LIMIT_REDIS_URL or "memory://",
    # NOT: headers_enabled=True her rate-limited endpoint imzasinda zorunlu
    # `response: Response` parametresi ister; bu olmayinca slowapi 0.1.9
    # `_inject_headers` cagrisi `Exception: parameter response must be ...`
    # firlatir. Frontend RateLimit-* header'larini kullanmiyor; header
    # injection'i kapaliyoruz, decorator yine 429 dondurur.
    headers_enabled=False,
    strategy="fixed-window",
)


# Suggested per-route decorators (applied at route definitions in routers):
#   /auth/login         -> @limiter.limit("5/minute", key_func=get_remote_address)
#   /api/v1/inspect     -> @limiter.limit("60/minute")  # uses user_or_ip_key
#   default             -> 200/minute (from default_limits)


# ---------------------------------------------------------------------------
# Request ID
# ---------------------------------------------------------------------------

_REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE_MAX_LEN = 128


def _coerce_request_id(value: Optional[str]) -> str:
    """Accept inbound header only if it looks safe; otherwise mint a uuid4."""
    if not value:
        return uuid.uuid4().hex
    value = value.strip()
    if not value or len(value) > _REQUEST_ID_RE_MAX_LEN:
        return uuid.uuid4().hex
    # whitelist: hex/uuid/url-safe chars
    if not all(c.isalnum() or c in "-_" for c in value):
        return uuid.uuid4().hex
    return value


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = _coerce_request_id(request.headers.get(_REQUEST_ID_HEADER))
        request.state.request_id = rid
        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = rid
        return response


# ---------------------------------------------------------------------------
# Access log (structured JSON)
# ---------------------------------------------------------------------------

# Endpoints whose request bodies / query strings might contain secrets -> redact.
_SENSITIVE_PATH_FRAGMENTS = ("/auth/", "/login", "/token", "/refresh", "/password")


def _client_ip(request: Request) -> str:
    # Trust X-Forwarded-For only behind a known proxy. For pilot scope this is
    # informational; do NOT use this value for auth decisions.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "-"


def _current_user_id(request: Request) -> Optional[str]:
    """Best-effort: pulled from request.state if a route dependency set it."""
    return getattr(request.state, "user_id", None)


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = request.url.path
            log_event = {
                "ts": int(time.time() * 1000),
                "level": "info",
                "event": "http.access",
                "method": request.method,
                "path": path,
                "status": status_code,
                "duration_ms": duration_ms,
                "ip": _client_ip(request),
                "user_id": _current_user_id(request),
                "request_id": getattr(request.state, "request_id", None),
                "ua": request.headers.get("user-agent", "-")[:200],
            }
            # NEVER include Authorization / Cookie / body. Query string only for
            # non-sensitive endpoints.
            if not any(frag in path for frag in _SENSITIVE_PATH_FRAGMENTS):
                qs = request.url.query
                if qs:
                    log_event["query"] = qs[:500]
            access_log.info(json.dumps(log_event, separators=(",", ":")))


# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

# CSP for an API: deny everything; the API does not serve HTML/JS. This
# neutralises XSS payloads that try to render via a misconfigured client.
_API_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        h.setdefault("Content-Security-Policy", _API_CSP)
        h.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
        )
        h.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        h.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # HSTS only meaningful over HTTPS. Enable in staging/prod (assumes TLS
        # terminator in front of FastAPI). 1 year, includeSubDomains, preload.
        if ENVIRONMENT in ("staging", "production"):
            h.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains; preload",
            )
        # Strip server fingerprinting where we can.
        if "server" in h:
            del h["server"]
        return response


# ---------------------------------------------------------------------------
# Public installer
# ---------------------------------------------------------------------------

def install_security_middleware(
    app: FastAPI,
    *,
    cors_origins: Optional[list[str]] = None,
) -> None:
    """
    Install the full stack. Order matters: outermost first (added last in Starlette
    semantics is outermost), but Starlette executes middleware in REVERSE order of
    registration, so register from innermost -> outermost.

    Final on-the-wire order (request path):
      CORS -> SecurityHeaders -> AccessLog -> RequestID -> app
    """
    origins = cors_origins if cors_origins is not None else ALLOWED_ORIGINS

    # Innermost first.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS outermost so preflights short-circuit cleanly.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or [],
        allow_credentials=False,    # JWT in Authorization header, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "RateLimit-Limit", "RateLimit-Remaining"],
        max_age=600,
    )

    if not origins and ENVIRONMENT in ("staging", "production"):
        sec_log.warning(
            "ALLOWED_ORIGINS is empty in %s; all cross-origin requests will be rejected",
            ENVIRONMENT,
        )


__all__ = [
    "limiter",
    "user_or_ip_key",
    "RequestIDMiddleware",
    "AccessLogMiddleware",
    "SecurityHeadersMiddleware",
    "install_security_middleware",
]
