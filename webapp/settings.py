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
    """Load .env first, then an optional environment-specific override."""
    environment = os.getenv("ENV")
    if not environment:
        if Path(".env").exists():
            load_dotenv(".env", override=False)
            environment = os.getenv("ENV", "local")
        elif Path(".env.local").exists():
            environment = "local"
        elif Path(".env.lightsail").exists():
            environment = "lightsail"
        else:
            print(
                "❌ ENV not set and no .env.local or .env.lightsail found. Script closing."
            )
            sys.exit(1)
    env_file = Path(f".env.{environment}")
    if env_file.exists():
        load_dotenv(env_file, override=True)
    elif not Path(".env").exists():
        print(f"❌ Environment file '{env_file}' not found. Script closing.")
        sys.exit(1)
    return Settings(environment=os.getenv("ENV", environment))
