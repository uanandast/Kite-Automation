"""FastAPI entry point for the Kite options-trading dashboard."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(create_router(state, Jinja2Templates(directory="templates")))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
