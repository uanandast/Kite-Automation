"""Environment configuration for the FastAPI application."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    environment: str


def load_settings() -> Settings:
    """Load the environment selected by ENV or the available env-file fallback."""
    environment = os.getenv("ENV")
    if not environment:
        if Path(".env.local").exists():
            environment = "local"
        elif Path(".env.lightsail").exists():
            environment = "lightsail"
        else:
            print(
                "❌ ENV not set and no .env.local or .env.lightsail found. Script closing."
            )
            sys.exit(1)
    env_file = Path(f".env.{environment}")
    if not env_file.exists():
        print(f"❌ Environment file '{env_file}' not found. Script closing.")
        sys.exit(1)
    load_dotenv(env_file, override=True)
    return Settings(environment=os.getenv("ENV", environment))
