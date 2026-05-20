import subprocess
import sys
from pathlib import Path
from dotenv import load_dotenv
import os


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"

# Detect environment FIRST (must come from system or default file name)
env = os.getenv("ENV")

# If ENV is not set, try to infer from existing env files
if not env:
    if (PROJECT_ROOT / ".env.local").exists():
        env = "local"
    elif (PROJECT_ROOT / ".env.lightsail").exists():
        env = "lightsail"
    else:
        print("❌ ENV not set and no .env.local or .env.lightsail found. Script closing.")
        sys.exit(1)

# Now load the correct env file
env_file = PROJECT_ROOT / f".env.{env}"
if not env_file.exists():
    print(f"❌ Environment file '{env_file}' not found. Script closing.")
    sys.exit(1)

load_dotenv(env_file, override=True)

# Confirm ENV after loading
env = os.getenv("ENV")

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


