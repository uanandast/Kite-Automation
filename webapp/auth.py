"""Session authentication for the private trading dashboard."""

import hashlib
import hmac

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from webapp.settings import Settings


PUBLIC_PATHS = {"/login"}


def _login_required_response(request: Request) -> Response:
    """Redirect page loads while returning JSON to unauthenticated API callers."""
    accepts_html = "text/html" in request.headers.get("accept", "")
    if request.method == "GET" and accepts_html:
        return RedirectResponse(url="/login", status_code=303)
    return JSONResponse(status_code=401, content={"detail": "Authentication required"})


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    """Require a signed session for every dashboard and API route."""

    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.enabled = bool(
            settings.dashboard_username
            and settings.dashboard_password
            and settings.session_secret
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in PUBLIC_PATHS or path.startswith("/static/"):
            return await call_next(request)

        # Local development remains usable until credentials are configured.
        # Production is validated at startup and can never reach this branch.
        if not self.enabled:
            return await call_next(request)

        username = request.session.get("dashboard_user")
        if not isinstance(username, str):
            return _login_required_response(request)
        expected = request.app.state.settings.dashboard_username
        if not hmac.compare_digest(username, expected):
            request.session.clear()
            return _login_required_response(request)
        return await call_next(request)


def credentials_are_valid(settings: Settings, username: str, password: str) -> bool:
    """Constant-time comparison prevents credential guessing via timing."""
    username_ok = hmac.compare_digest(username, settings.dashboard_username)
    supplied = hashlib.sha256(password.encode()).digest()
    expected = hashlib.sha256(settings.dashboard_password.encode()).digest()
    return username_ok and hmac.compare_digest(supplied, expected)
