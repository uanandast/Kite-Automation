import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

# Docker may supply variables directly; loading .env is optional for local use.
env_file = PROJECT_ROOT / ".env"
if env_file.exists():
    load_dotenv(env_file, override=False)
env = os.getenv("ENV", "local")

def system_close():
    try:
        if env == "local":
            script_path = Path(__file__).parent / "Kill_Time.py"
        else:
            script_path = Path(__file__).parent / "Kill_Time_Prod.py"
        if not script_path.exists():
            print(f"Target script not found: {script_path}")
            return

        LOG_DIR.mkdir(exist_ok=True)
        log_path = LOG_DIR / "system_close.log"
        child_env = os.environ.copy()
        child_env["ENV"] = env

        with log_path.open("a", buffering=1) as log_file:
            process = subprocess.Popen(
                [sys.executable, str(script_path)],
                cwd=PROJECT_ROOT,
                env=child_env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        print(f"System close started: {script_path.name} (pid={process.pid}). Logs: {log_path}")
    except Exception as e:
        print(f"Error starting background process: {e}")

if __name__ == "__main__":
    try:
        system_close()
    except Exception as e:
        print(f"Error executing system close command: {e}")


