import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CRED_DIR = PROJECT_ROOT / "Cred"
ACCESS_TOKEN_PATH = CRED_DIR / "access_token.txt"


def _load_environment() -> None:
    """Load the standard project .env, then an optional environment override."""
    base_env_file = PROJECT_ROOT / ".env"
    if base_env_file.exists():
        load_dotenv(base_env_file, override=False)

    environment = os.getenv("ENV")
    if environment:
        environment_env_file = PROJECT_ROOT / f".env.{environment}"
        if environment_env_file.exists():
            load_dotenv(environment_env_file, override=True)


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


_load_environment()


@dataclass
class KiteCredentials:
    api_key: str
    api_secret: str
    user_id: str
    password: str
    totp_secret: str
    bot_token: str
    chat_id: str
    access_token: str | None = None

kite_credentials = KiteCredentials(
    api_key=_required_environment("KITE_API_KEY"),
    api_secret=_required_environment("KITE_API_SECRET"),
    user_id=_required_environment("KITE_USER_ID"),
    password=_required_environment("KITE_PASSWORD"),
    totp_secret=_required_environment("KITE_TOTP_SECRET"),
    bot_token=_required_environment("TELEGRAM_BOT_TOKEN"),
    chat_id=_required_environment("TELEGRAM_CHAT_ID"),
)
