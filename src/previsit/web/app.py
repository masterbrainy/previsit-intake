"""FastAPI app factory: physician dashboard (basic auth) and patient pages (secret token link)."""

import logging
import secrets
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from previsit.config import Settings, get_settings
from previsit.db import init_db, make_engine, session_scope
from previsit.llm import LLMClient, OpenAILLM

logger = logging.getLogger(__name__)
WEB_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=WEB_DIR / "templates")
basic = HTTPBasic(realm="Pre-visit intake: physician")


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
        return response

    from previsit.web import patient, physician, uploads

    app.include_router(physician.router)
    app.include_router(uploads.router)
    app.include_router(patient.router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/dashboard")

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
