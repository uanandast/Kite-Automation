import os
import sys
import time
import importlib
import subprocess
import configparser
from pathlib import Path
from datetime import datetime
from threading import Thread, Lock
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Any, Dict, Union
from dotenv import load_dotenv

import requests
from kiteconnect import KiteConnect

from Core.shared_resources import set_monitoring_state, get_monitoring_state

# --- Environment Setup ---
# Detect environment FIRST (must come from system or default file name)
env = os.getenv("ENV")

# If ENV is not set, try to infer from existing env files
if not env:
    if os.path.exists(".env.local"):
        env = "local"
    elif os.path.exists(".env.lightsail"):
        env = "lightsail"
    else:
        print("❌ ENV not set and no .env.local or .env.lightsail found. Script closing.")
        sys.exit(1)

# Now load the correct env file
env_file = f".env.{env}"
if not os.path.exists(env_file):
    print(f"❌ Environment file '{env_file}' not found. Script closing.")
    sys.exit(1)

load_dotenv(env_file, override=True)

# Confirm ENV after loading
env = os.getenv("ENV")

# --- Global State ---
latest_iron_condor_data = {}
manual_exit_lock = Lock()
manual_exit_in_progress = False
manual_stoploss_lock = Lock()
manual_stoploss_in_progress = False
manual_cancel_sl_lock = Lock()
manual_cancel_sl_in_progress = False
manual_shift_lock = Lock()
manual_shift_in_progress = False
manual_selected_exit_lock = Lock()
manual_selected_exit_in_progress = False

kite_monitor_final = None
get_current_iron_condor = None
get_previous_day_close = None
set_selected_index = None
get_selected_index = None
get_available_indices = None
margin = 0
previous_day_close = 0
name = "Unknown"
index_update_lock = Lock()

config = configparser.ConfigParser()
config.read('Cred/Cred_kite_PREM.ini')

# --- Helper Functions ---
def send_telegram(message):
    BOT_TOKEN = config.get('Kite', 'BOT_TOKEN', fallback=None)
    CHAT_ID = config.get('Kite', 'CHAT_ID', fallback=None)
    if not BOT_TOKEN or not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.get(url, params=params, timeout=5)
        print("📩 Telegram alert sent")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def _read_kite_credentials():
    config = configparser.ConfigParser()
    config.read('Cred/Cred_kite_PREM.ini')
    return config['Kite']['api_key']

def _read_access_token():
    token_path = Path("Cred/access_token.txt")
    if not token_path.exists():
        return None
    token = token_path.read_text().strip()
    return token or None

def verify_kite_connection():
    try:
        api_key = _read_kite_credentials()
        access_token = _read_access_token()
        if not access_token:
            print("⚠️ access_token.txt missing/empty.")
            return False

        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)
        kite.profile()
        print("✅ Kite connection check passed.")
        return True
    except Exception as e:
        print(f"❌ Kite connection check failed: {e}")
        return False

def run_login_script():
    if env == "local":
        login_path = Path(__file__).parent / "Auth" / "login.py"
    else:
        login_path = Path(__file__).parent / "Auth" / "login_prod.py"
    print("🔐 Running login.py to refresh access token...")
    subprocess.run([sys.executable, str(login_path)], check=True)

def ensure_kite_connection():
    if verify_kite_connection():
        return True

    try:
        run_login_script()
    except Exception as e:
        print(f"❌ Failed to run login.py: {e}")
        return False

    return verify_kite_connection()

def initialize_runtime():
    global kite_monitor_final, get_current_iron_condor, get_previous_day_close
    global set_selected_index, get_selected_index, get_available_indices
    global margin, previous_day_close, name

    if not ensure_kite_connection():
        raise RuntimeError("Kite session unavailable even after running login.py")

    delta_module = importlib.import_module("Core.Delta_IV")
    kite_monitor_final = importlib.import_module("Core.Monitor")

    get_current_iron_condor = delta_module.get_current_iron_condor
    get_previous_day_close = delta_module.get_previous_day_close
    set_selected_index = delta_module.set_selected_index
    get_selected_index = delta_module.get_selected_index
    get_available_indices = delta_module.get_available_indices

    margin = kite_monitor_final.get_margin()
    previous_day_close, name = get_previous_day_close()

def monitor_spreads_loop():
    if kite_monitor_final is None:
        return
    if get_monitoring_state():
        return
    try:
        set_monitoring_state(True)
        kite_monitor_final.monitor_spreads()
    except Exception as e:
        print(f"❌ Error in monitor_spreads: {str(e)}")
        time.sleep(1)
    finally:
        set_monitoring_state(False)

def update_iron_condor_data():
    global latest_iron_condor_data
    if get_current_iron_condor is None:
        return
    refresh_interval_seconds = 0.2
    while True:
        try:
            with index_update_lock:
                result, net_delta, options_data, strangle_credit, future_price, Skew, delta, spot_price, atm_strike = get_current_iron_condor()

            latest_iron_condor_data = {
                'legs': result,
                'net_delta': round(net_delta, 4) if net_delta is not None else None,
                'chain': options_data,
                'strangle_credit': strangle_credit,
                'future_price': future_price,
                'skew': Skew,
                'delta': delta,
                'spot_price': spot_price,
                'atm_strike': atm_strike
            }
            time.sleep(refresh_interval_seconds)
        except Exception as e:  
            print(f"Error in update_iron_condor_data: {str(e)}")
            time.sleep(2)

# --- FastAPI Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        initialize_runtime()
        if env == "local":  
            send_telegram("🚀 Trading bot started successfully on MacBook")
        else:
            send_telegram("🚀 Trading bot started successfully on Lightsail")
    except Exception as e:
        print(f"❌ Startup failed: {e}")
        send_telegram(f"❌ Trading bot failed to start: {e}")
        # Not exiting the whole process so the user can see errors, 
        # or we can keep sys.exit(1) based on old app.
        sys.exit(1)

    thread1 = Thread(target=update_iron_condor_data, daemon=True)
    thread1.start()
    thread2 = Thread(target=monitor_spreads_loop, daemon=True)
    thread2.start()
    
    yield
    # Shutdown logic (if any)
    pass

# --- FastAPI App ---
app = FastAPI(lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# --- Pydantic Models ---
class IndexRequest(BaseModel):
    index: str

class LegSelection(BaseModel):
    tradingsymbol: Optional[str] = None
    exchange: Optional[str] = None
    product: Optional[str] = None
    new_qty: Optional[int] = None

class ShiftRequest(BaseModel):
    legs: List[Union[str, Dict[str, Any]]]
    shift: int

class ExitLegsRequest(BaseModel):
    legs: List[Union[str, Dict[str, Any]]]

# --- Formatting Helpers ---
def _format_cancel_sl_message(result):
    if result.get("requested", 0) == 0:
        return "No open SL orders to cancel"
    msg = f"Cancelled {result.get('cancelled', 0)} SL orders"
    if result.get("errors", 0) > 0:
        msg += f" ({result.get('errors', 0)} errors)"
    return msg

def _format_stoploss_message(result):
    if result.get("positions", 0) == 0:
        return "No option positions found for SL"
    msg = f"Placed {result.get('placed_orders', 0)} SL orders"
    if result.get("skipped", 0) > 0:
        msg += f", skipped {result.get('skipped', 0)} existing"
    if result.get("failed_positions", 0) > 0:
        msg += f" ({result.get('failed_positions', 0)} failed)"
    return msg

def _format_exit_message(result):
    if result.get("in_progress"):
        return result.get("error") or "Exit all is already in progress"
    if result.get("attempted", 0) == 0:
        return "No open positions to exit"
    short_done = result.get("short_confirmed", result.get("short_succeeded", 0))
    long_done = result.get("long_confirmed", result.get("long_succeeded", 0))
    msg = (
        f"Exited {short_done} short legs, "
        f"then {long_done} long legs"
    )
    if result.get("failed", 0) > 0:
        msg += f" ({result.get('failed', 0)} failed)"
    if result.get("error"):
        msg += f": {result.get('error')}"
    return msg

def _format_shift_message(result):
    requested = result.get("requested", 0)
    succeeded = result.get("succeeded", 0)
    failed = result.get("failed", 0)
    if requested == 0:
        return "No legs selected for shift"
    msg = f"Shifted {succeeded}/{requested} legs"
    if failed > 0:
        msg += f" ({failed} failed)"
    return msg

def _format_selected_exit_message(result):
    requested = result.get("requested", 0)
    succeeded = result.get("succeeded", 0)
    failed = result.get("failed", 0)
    if requested == 0:
        return "No legs selected for exit"
    msg = f"Exited {succeeded}/{requested} selected legs"
    if failed > 0:
        msg += f" ({failed} failed)"
    return msg

# --- Endpoints ---

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request=request, name="index_r.html")

@app.get("/option_data")
def iron_condor_data():
    data = latest_iron_condor_data.copy()
    data['previous_close'] = previous_day_close
    data['symbol'] = name
    data['selected_index'] = get_selected_index() if get_selected_index else "nifty"
    return data

@app.get("/indices")
def indices():
    if get_available_indices is None or get_selected_index is None:
        raise HTTPException(status_code=503, detail="Kite runtime not initialized")
    return {
        "available": get_available_indices(),
        "selected": get_selected_index()
    }

@app.post("/set_index")
def set_index(payload: IndexRequest):
    global previous_day_close, name, latest_iron_condor_data
    if set_selected_index is None:
        raise HTTPException(status_code=503, detail="Kite runtime not initialized")

    index_name = payload.index.strip().lower()
    if not index_name:
        raise HTTPException(status_code=400, detail="Missing index value")

    try:
        with index_update_lock:
            selected = set_selected_index(index_name)
            previous_day_close, name = get_previous_day_close()
            latest_iron_condor_data = {}
        return {
            "message": f"Index switched to {selected.upper()}",
            "selected": selected,
            "symbol": name
        }
    except Exception as e:
        print(f"❌ Error while switching index: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to switch index: {str(e)}")

@app.get("/pnl")
def pnl():
    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        straddle_price = latest_iron_condor_data.get('strangle_credit', 0.0)
        data = {
            "net_pnl": kite_monitor_final.pnl_total if kite_monitor_final.pnl_total is not None else 0.0,
            "straddle_price": straddle_price if straddle_price is not None else 0.0,
            "timestamp": datetime.now().isoformat(),
            "Current_pos_credit": kite_monitor_final.Current_pos_credit if kite_monitor_final.Current_pos_credit is not None else 0.0,
            "margin": margin,
            "available_margin": getattr(kite_monitor_final, "available_margin", 0.0),
            "nifty_value": latest_iron_condor_data.get('spot_price', 0.0)
        }
        return data
    except Exception as e:
        print(f"Error in pnl endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/manual_exit")
def manual_exit():
    global manual_exit_in_progress
    with manual_exit_lock:
        if manual_exit_in_progress:
            raise HTTPException(status_code=409, detail="Manual exit is already in progress")
        manual_exit_in_progress = True

    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        positions = kite_monitor_final.kite.positions()["net"]
        result = kite_monitor_final.Exiting_position(positions)
        return {"message": _format_exit_message(result), "details": result}
    except Exception as e:
        print(f"❌ Error in manual exit: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Manual exit failed: {str(e)}")
    finally:
        with manual_exit_lock:
            manual_exit_in_progress = False

@app.post("/manual_stoploss")
def manual_stoploss():
    global manual_stoploss_in_progress
    with manual_stoploss_lock:
        if manual_stoploss_in_progress:
            raise HTTPException(status_code=409, detail="Manual stoploss is already in progress")
        manual_stoploss_in_progress = True

    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        result = kite_monitor_final.stoploss_order_button()
        return {"message": _format_stoploss_message(result), "details": result}
    except Exception as e:
        print(f"❌ Error in manual stoploss: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Manual stoploss failed: {str(e)}")
    finally:
        with manual_stoploss_lock:
            manual_stoploss_in_progress = False

@app.post("/manual_cancel_sl")
def manual_cancel_sl():
    global manual_cancel_sl_in_progress
    with manual_cancel_sl_lock:
        if manual_cancel_sl_in_progress:
            raise HTTPException(status_code=409, detail="Manual SL cancel is already in progress")
        manual_cancel_sl_in_progress = True

    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        result = kite_monitor_final.cancel_all_sl_orders()
        return {"message": _format_cancel_sl_message(result), "details": result}
    except Exception as e:
        print(f"❌ Error in manual SL cancel: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Manual SL cancel failed: {str(e)}")
    finally:
        with manual_cancel_sl_lock:
            manual_cancel_sl_in_progress = False

@app.get("/open_option_positions")
def open_option_positions():
    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        positions = kite_monitor_final.get_open_option_positions()
        return {"positions": positions}
    except Exception as e:
        print(f"❌ Error fetching open option positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch open option positions: {str(e)}")

@app.post("/shift_legs")
def shift_legs(payload: ShiftRequest):
    global manual_shift_in_progress
    with manual_shift_lock:
        if manual_shift_in_progress:
            raise HTTPException(status_code=409, detail="Leg shift is already in progress")
        manual_shift_in_progress = True

    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")

        legs = payload.legs
        shift = payload.shift

        if not legs:
            raise HTTPException(status_code=400, detail="Missing legs selection")
        if shift == 0:
            raise HTTPException(status_code=400, detail="Shift cannot be 0")

        normalized_legs = []
        for leg in legs:
            if isinstance(leg, str):
                symbol = leg.strip()
                if symbol:
                    normalized_legs.append({"tradingsymbol": symbol})
                continue
            if isinstance(leg, dict):
                symbol = str(leg.get("tradingsymbol", "")).strip()
                if not symbol:
                    continue
                normalized_legs.append({
                    "tradingsymbol": symbol,
                    "exchange": str(leg.get("exchange", "")).strip().upper(),
                    "product": leg.get("product"),
                })
                if leg.get("new_qty") is not None:
                    try:
                        normalized_legs[-1]["new_qty"] = int(leg.get("new_qty"))
                    except (TypeError, ValueError):
                        raise HTTPException(status_code=400, detail=f"Invalid new_qty for {symbol}")

        if not normalized_legs:
            raise HTTPException(status_code=400, detail="No valid legs supplied")

        result = kite_monitor_final.shift_selected_legs(normalized_legs, shift)
        return {
            "message": _format_shift_message(result),
            "details": result
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Error shifting legs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Leg shift failed: {str(e)}")
    finally:
        with manual_shift_lock:
            manual_shift_in_progress = False

@app.post("/exit_selected_legs")
def exit_selected_legs(payload: ExitLegsRequest):
    global manual_selected_exit_in_progress
    with manual_selected_exit_lock:
        if manual_selected_exit_in_progress:
            raise HTTPException(status_code=409, detail="Selected legs exit already in progress")
        manual_selected_exit_in_progress = True

    try:
        if kite_monitor_final is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")

        legs = payload.legs
        if not legs:
            raise HTTPException(status_code=400, detail="Missing legs selection")

        normalized_legs = []
        for leg in legs:
            if isinstance(leg, str):
                symbol = leg.strip()
                if symbol:
                    normalized_legs.append({"tradingsymbol": symbol})
                continue
            if isinstance(leg, dict):
                symbol = str(leg.get("tradingsymbol", "")).strip()
                if not symbol:
                    continue
                normalized_legs.append({
                    "tradingsymbol": symbol,
                    "exchange": str(leg.get("exchange", "")).strip().upper(),
                    "product": leg.get("product"),
                })

        if not normalized_legs:
            raise HTTPException(status_code=400, detail="No valid legs supplied")

        result = kite_monitor_final.exit_selected_legs(normalized_legs)
        return {
            "message": _format_selected_exit_message(result),
            "details": result
        }
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"❌ Error exiting selected legs: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Exit selected legs failed: {str(e)}")
    finally:
        with manual_selected_exit_lock:
            manual_selected_exit_in_progress = False

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
