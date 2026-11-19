"""Kite runtime initialization and long-running background workers."""

import importlib
import math
import os
import time
from contextlib import asynccontextmanager
from threading import Thread

from core.kite_connection import KiteConnection
from core.send_notification import send_telegram
from core.shared_resources import get_monitoring_state, set_monitoring_state
from webapp.serializers import sanitize_for_json
from webapp.settings import Settings
from webapp.state import RuntimeState

DOCKER_WEBSITE_URL = "https://uanandast.duckdns.org"



class TradingRuntime:
    def __init__(self, settings: Settings, state: RuntimeState) -> None:
        self.settings = settings
        self.state = state
        self.kite_connection = KiteConnection(environment=settings.environment)

    def initialize(self) -> None:
        if not self.kite_connection.ensure_connection():
            raise RuntimeError("Kite session unavailable even after running login.py")
        # The login refresh runs in a child process.  Synchronize its token
        # into cred._base before importing modules that create Kite clients.
        self.kite_connection.sync_access_token()
        delta_module = importlib.import_module("core.delta_iv")
        monitor_module = importlib.import_module("core.monitor")
        self.state.monitor_module = monitor_module
        self.state.get_current_iron_condor = delta_module.get_current_iron_condor
        self.state.get_previous_day_close = delta_module.get_previous_day_close
        self.state.set_selected_index = delta_module.set_selected_index
        self.state.get_selected_index = delta_module.get_selected_index
        self.state.get_available_indices = delta_module.get_available_indices
        self.state.margin = monitor_module.get_margin()
        self.state.previous_day_close, self.state.name = (
            self.state.get_previous_day_close()
        )

    def start_workers(self) -> None:
        Thread(target=self._update_iron_condor_data, daemon=True).start()
        Thread(target=self._monitor_spreads, daemon=True).start()
        Thread(target=self._capture_pnl_history, daemon=True).start()

    def _monitor_spreads(self) -> None:
        monitor_module = self.state.monitor_module
        if monitor_module is None or get_monitoring_state():
            return
        try:
            set_monitoring_state(True)
            monitor_module.monitor_spreads()
        except Exception as error:
            print(f"❌ Error in monitor_spreads: {error!s}")
            time.sleep(1)
        finally:
            set_monitoring_state(False)

    def _update_iron_condor_data(self) -> None:
        if self.state.get_current_iron_condor is None:
            return
        last_values = None
        while True:
            try:
                with self.state.index_update_lock:
                    values = self.state.get_current_iron_condor()
                if values is not last_values:
                    (
                        result,
                        net_delta,
                        options_data,
                        strangle_credit,
                        future_price,
                        skew,
                        delta,
                        spot_price,
                        atm_strike,
                    ) = values
                    safe_net_delta = None
                    if net_delta is not None and not (math.isnan(net_delta) or math.isinf(net_delta)):
                        safe_net_delta = round(float(net_delta), 4)

                    self.state.latest_iron_condor_data = sanitize_for_json(
                        {
                            "legs": result,
                            "net_delta": safe_net_delta,
                            "chain": options_data,
                            "strangle_credit": strangle_credit,
                            "future_price": future_price,
                            "skew": skew,
                            "delta": delta,
                            "spot_price": spot_price,
                            "atm_strike": atm_strike,
                        }
                    )
                    last_values = values
                time.sleep(0.2)
            except Exception as error:
                print(f"Error in update_iron_condor_data: {error!s}")
                time.sleep(2)

    def _capture_pnl_history(self) -> None:
        """Record one live chart point per minute; data resets when the app restarts."""
        while True:
            try:
                monitor = self.state.monitor_module
                selected_index = self.state.get_selected_index
                if monitor is not None and selected_index is not None:
                    net_pnl = float(monitor.pnl_total or 0.0)
                    straddle_price = float(
                        self.state.latest_iron_condor_data.get("strangle_credit", 0.0)
                        or 0.0
                    )
                    if math.isfinite(net_pnl) and math.isfinite(straddle_price):
                        timestamp_ms = int(time.time() * 1000) // 60_000 * 60_000
                        self.state.record_pnl_sample(
                            selected_index(), timestamp_ms, net_pnl, straddle_price
                        )
            except Exception as error:
                print(f"Error recording P&L chart history: {error!s}")
            time.sleep(1)

    @asynccontextmanager
    async def lifespan(self):
        try:
            self.initialize()
            location = "MacBook" if self.settings.environment == "local" else "Docker"
            message = f"🚀 Trading bot started successfully on {location}"
            if location == "Docker":
                website_url = (
                    os.getenv("DASHBOARD_URL")
                    or os.getenv("WEBSITE_URL")
                    or DOCKER_WEBSITE_URL
                )
                message += f"\n🌐 {website_url}"
            send_telegram(message)
        except Exception as error:
            print(f"❌ Startup failed: {error}")
            send_telegram(f"❌ Trading bot failed to start: {error}")
            raise
        self.start_workers()
        yield
