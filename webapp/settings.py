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
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    entra_client_secret: str = ""
    entra_redirect_uri: str = ""
    entra_allowed_emails: str = ""

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def entra_enabled(self) -> bool:
        return all(
            (
                self.entra_tenant_id,
                self.entra_client_id,
                self.entra_client_secret,
                self.entra_redirect_uri,
                self.session_secret,
            )
        )

    @property
    def allowed_entra_emails(self) -> set[str]:
        return {
            email.strip().lower()
            for email in self.entra_allowed_emails.split(",")
            if email.strip()
        }

    def validate_dashboard_auth(self) -> None:
        """Fail closed when the dashboard is deployed without login settings."""
        has_legacy_auth = all(
            (self.dashboard_username, self.dashboard_password, self.session_secret)
        )
        if self.is_production and not (has_legacy_auth or self.entra_enabled):
            raise RuntimeError(
                "Configure DASHBOARD_USERNAME/DASHBOARD_PASSWORD or Entra ID, "
                "and set SESSION_SECRET when ENV=production"
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
        entra_tenant_id=os.getenv("ENTRA_TENANT_ID", ""),
        entra_client_id=os.getenv("ENTRA_CLIENT_ID", ""),
        entra_client_secret=os.getenv("ENTRA_CLIENT_SECRET", ""),
        entra_redirect_uri=os.getenv("ENTRA_REDIRECT_URI", ""),
        entra_allowed_emails=os.getenv("ENTRA_ALLOWED_EMAILS", ""),
    )
    settings.validate_dashboard_auth()
    return settings
