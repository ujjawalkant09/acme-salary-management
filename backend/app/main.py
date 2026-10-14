from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.errors import NotFound, install_error_handlers
from app.core.logging import log_requests, setup_logging
from app.core.rate_limit import limiter, rate_limit_exceeded
from app.routers import auth, employees, files, imports, insights, meta

API_PREFIX = "/api/v1"

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline' "
        "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
        "frame-ancestors 'none'"
    ),
}


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)
    app = FastAPI(title="ACME Pay API", version="1.0", docs_url=f"{API_PREFIX}/docs",
                  openapi_url=f"{API_PREFIX}/openapi.json")  # fmt: skip

    install_error_handlers(app)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        if request.url.path == app.docs_url:  # Swagger UI loads its assets from a CDN
            del response.headers["Content-Security-Policy"]
        return response

    app.middleware("http")(log_requests)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="acme_session",
        max_age=settings.session_max_age_seconds,
        same_site="lax",
        https_only=settings.session_cookie_secure,
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    for router in (auth.router, meta.router, employees.router, insights.router,
                   imports.router, files.router):  # fmt: skip
        app.include_router(router, prefix=API_PREFIX)

    _serve_frontend(app, settings.frontend_dist)
    return app


def _serve_frontend(app: FastAPI, dist) -> None:
    """Serve the built React app (production image). Unknown paths get index.html so
    client-side routes like /people/42 work on reload."""
    index = dist / "index.html"
    if not index.is_file():
        return
    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist.resolve()):
            return FileResponse(candidate)
        if path.startswith("api/"):
            raise NotFound("Not found.")
        return FileResponse(index)


app = create_app()
