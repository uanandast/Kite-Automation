"""Environment configuration for the FastAPI application."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    environment: str
    dashboard_username: str
    dashboard_password: str
    session_secret: str

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    def validate_dashboard_auth(self) -> None:
        """Fail closed when the dashboard is deployed without login settings."""
        if self.is_production and not all(
            (self.dashboard_username, self.dashboard_password, self.session_secret)
        ):
            raise RuntimeError(
                "DASHBOARD_USERNAME, DASHBOARD_PASSWORD, and SESSION_SECRET are "
                "required when ENV=production"
            )
        if self.session_secret and len(self.session_secret) < 32:
            raise RuntimeError("SESSION_SECRET must be at least 32 characters long")


def load_settings() -> Settings:
    """Load the standard .env file when present.

    Docker Compose can inject the same values directly into the container, so
    the application never requires a file at runtime.
    """
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file, override=False)
    settings = Settings(
        environment=os.getenv("ENV", "local"),
        dashboard_username=os.getenv("DASHBOARD_USERNAME", ""),
        dashboard_password=os.getenv("DASHBOARD_PASSWORD", ""),
        session_secret=os.getenv("SESSION_SECRET", ""),
    )
    settings.validate_dashboard_auth()
    return settings
