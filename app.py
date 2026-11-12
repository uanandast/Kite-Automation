"""FastAPI entry point for the Kite options-trading dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from webapp.auth import DashboardAuthMiddleware
from webapp.routes import create_router
from webapp.runtime import TradingRuntime
from webapp.settings import load_settings
from webapp.state import RuntimeState

settings = load_settings()
state = RuntimeState()
runtime = TradingRuntime(settings, state)


@asynccontextmanager
async def lifespan(application: FastAPI):
    async with runtime.lifespan():
        yield


app = FastAPI(lifespan=lifespan)
app.state.settings = settings
# SessionMiddleware must wrap DashboardAuthMiddleware so request.session exists.
app.add_middleware(DashboardAuthMiddleware, settings=settings)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret or "local-development-session-secret-change-me",
    https_only=settings.is_production,
    same_site="lax",
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(create_router(state, Jinja2Templates(directory="templates")))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
