"""Environment configuration for the FastAPI application."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    environment: str


def load_settings() -> Settings:
    """Load the standard .env file when present.

    Docker Compose can inject the same values directly into the container, so
    the application never requires a file at runtime.
    """
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file, override=False)
    return Settings(environment=os.getenv("ENV", "local"))
