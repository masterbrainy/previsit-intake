"""FastAPI app factory: front page, physician dashboard (basic auth) and patient portal (one-time-code sign-in)."""

import logging
import secrets
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exception_handlers import http_exception_handler
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from previsit.config import Settings, get_settings
from previsit.db import init_db, make_engine, session_scope
from previsit.llm import LLMClient, OpenAILLM

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
basic = HTTPBasic(realm="Pre-visit intake: physician")
# Pages with patient data are never stored by the browser or a shared cache.
PRIVATE_PATHS = ("/portal", "/p/", "/patients", "/dashboard", "/results")


def require_physician(request: Request, credentials: HTTPBasicCredentials = Depends(basic)) -> str:
    settings: Settings = request.app.state.settings
    password = settings.physician_password.get_secret_value()
    if not password:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "PHYSICIAN_PASSWORD is not configured")
    user_ok = secrets.compare_digest(credentials.username.encode(), settings.physician_username.encode())
    pass_ok = secrets.compare_digest(credentials.password.encode(), password.encode())
    if not (user_ok and pass_ok):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return credentials.username


def create_app(settings: Settings | None = None, llm: LLMClient | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Pre-visit intake", docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    init_db(app.state.engine)
    app.state.llm = llm
    secret = settings.portal_secret.get_secret_value()
    app.state.portal_key = secret.encode() if secret else secrets.token_bytes(32)
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    @app.middleware("http")
    async def same_origin_posts(request: Request, call_next):
        # Basic-auth credentials are sent automatically by browsers, so block cross-site form posts (CSRF).
        if request.method == "POST":
            source = request.headers.get("origin") or request.headers.get("referer")
            if source and urlparse(source).netloc != request.url.netloc:
                return templates.TemplateResponse(
                    request, "error.html", {"message": "Cross-site request blocked."}, status_code=403
                )
        response = await call_next(request)
        # Only our own origin may frame pages (used by the demo recorder's side-by-side stage).
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
        # same-origin keeps patient link tokens from leaking to other sites. ("no-referrer" would make browsers send
        # Origin: null on our own form posts, which the CSRF check above rightly rejects.)
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith(PRIVATE_PATHS):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(StarletteHTTPException)
    async def friendly_errors(request: Request, exc: StarletteHTTPException):
        # Redirects (e.g. to portal sign-in) and API-style intake calls keep their plain form; pages get a readable error.
        if exc.status_code < 400 or "/intake/" in request.url.path or exc.status_code == 401:
            return await http_exception_handler(request, exc)
        message = "We couldn't find that page." if exc.status_code == 404 else str(exc.detail)
        return templates.TemplateResponse(
            request, "error.html", {"message": message}, status_code=exc.status_code, headers=exc.headers
        )

    from previsit.web import patient, physician, portal, portal_booking, uploads

    app.include_router(portal.router)
    app.include_router(portal_booking.router)
    app.include_router(physician.router)
    app.include_router(uploads.router)
    app.include_router(patient.router)
    return app


def get_session(request: Request) -> Iterator[Session]:
    with session_scope(request.app.state.engine) as session:
        yield session


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_llm(request: Request) -> LLMClient:
    if request.app.state.llm is None:
        request.app.state.llm = OpenAILLM(request.app.state.settings)
    return request.app.state.llm


def lazy_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return create_app()
