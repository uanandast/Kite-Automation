
import os
import subprocess
import sys
from pathlib import Path

from kiteconnect import KiteConnect

from Cred._base import ACCESS_TOKEN_PATH, kite_credentials


class KiteConnection:
    """Load, validate, and refresh the Kite API connection."""

    def __init__(self, environment: str, project_root: Path | None = None):
        self.environment = environment
        self.project_root = project_root or Path(__file__).resolve().parent.parent

    def _read_access_token(self) -> str | None:
        if not ACCESS_TOKEN_PATH.exists():
            return None
        token = ACCESS_TOKEN_PATH.read_text().strip()
        return token or None

    def sync_access_token(self, access_token: str | None = None) -> str | None:
        """Keep the shared credentials object in sync with the token file.

        ``Core.Delta_IV`` and ``Core.Monitor`` create their Kite clients at
        import time.  Updating only the token file (or a child login process)
        leaves those clients with the old ``None``/expired in-memory token.
        """
        token = access_token or self._read_access_token()
        kite_credentials.access_token = token
        return token

    def verify(self) -> bool:
        access_token = self.sync_access_token()
        if not access_token:
            print("⚠️ access_token.txt missing/empty.")
            return False

        try:
            kite = KiteConnect(api_key=kite_credentials.api_key)
            kite.set_access_token(access_token)
            kite.profile()
            print("✅ Kite connection check passed.")
            return True
        except Exception as error:  # noqa: BLE001
            print(f"❌ Kite connection check failed: {error}")
            return False

    def refresh(self) -> None:
        login_name = "login.py" if self.environment == "local" else "login_prod.py"
        login_path = self.project_root / "Auth" / login_name
        print("🔐 Running login.py to refresh access token...")

        child_env = os.environ.copy()
        existing_pythonpath = child_env.get("PYTHONPATH")
        child_env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(self.project_root), existing_pythonpath) if part
        )
        subprocess.run(
            [sys.executable, str(login_path)],
            check=True,
            cwd=self.project_root,
            env=child_env,
        )

    def ensure_connection(self) -> bool:
        if self.verify():
            return True

        try:
            self.refresh()
        except Exception as error:  # noqa: BLE001
            print(f"❌ Failed to run login.py: {error}")
            return False

        return self.verify()
