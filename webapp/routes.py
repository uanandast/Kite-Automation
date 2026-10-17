"""Dashboard API routes; trading behavior stays in Core.Monitor."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from webapp.formatters import (
    format_cancel_sl_message,
    format_exit_message,
    format_selected_exit_message,
    format_shift_message,
    format_stoploss_message,
)
from webapp.schemas import ExitLegsRequest, IndexRequest, ShiftRequest
from webapp.state import RuntimeState


def create_router(state: RuntimeState, templates: Jinja2Templates) -> APIRouter:
    router = APIRouter()

    def monitor_or_503():
        if state.monitor_module is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        return state.monitor_module

    def reserve(operation: str, detail: str) -> None:
        if not state.start_operation(operation):
            raise HTTPException(status_code=409, detail=detail)

    def normalize_legs(
        legs: list[str | dict[str, Any]], include_quantity: bool
    ) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for leg in legs:
            if isinstance(leg, str):
                if symbol := leg.strip():
                    normalized.append({"tradingsymbol": symbol})
                continue
            symbol = str(leg.get("tradingsymbol", "")).strip()
            if not symbol:
                continue
            item: dict[str, Any] = {
                "tradingsymbol": symbol,
                "exchange": str(leg.get("exchange", "")).strip().upper(),
                "product": leg.get("product"),
            }
            if include_quantity and leg.get("new_qty") is not None:
                try:
                    item["new_qty"] = int(leg["new_qty"])
                except (TypeError, ValueError) as error:
                    raise HTTPException(
                        status_code=400, detail=f"Invalid new_qty for {symbol}"
                    ) from error
            normalized.append(item)
        return normalized

    @router.get("/", response_class=HTMLResponse)
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index_r.html")

    @router.get("/option_data")
    def iron_condor_data():
        data = state.latest_iron_condor_data.copy()
        data.update(
            {
                "previous_close": state.previous_day_close,
                "symbol": state.name,
                "selected_index": state.get_selected_index()
                if state.get_selected_index
                else "nifty",
            }
        )
        return data

    @router.get("/indices")
    def indices():
        if state.get_available_indices is None or state.get_selected_index is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        return {
            "available": state.get_available_indices(),
            "selected": state.get_selected_index(),
        }

    @router.post("/set_index")
    def set_index(payload: IndexRequest):
        if state.set_selected_index is None or state.get_previous_day_close is None:
            raise HTTPException(status_code=503, detail="Kite runtime not initialized")
        index_name = payload.index.strip().lower()
        if not index_name:
            raise HTTPException(status_code=400, detail="Missing index value")
        try:
            with state.index_update_lock:
                selected = state.set_selected_index(index_name)
                state.previous_day_close, state.name = state.get_previous_day_close()
                state.latest_iron_condor_data = {}
            return {
                "message": f"Index switched to {selected.upper()}",
                "selected": selected,
                "symbol": state.name,
            }
        except Exception as error:
            print(f"❌ Error while switching index: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Failed to switch index: {error!s}"
            ) from error

    @router.get("/pnl")
    def pnl():
        try:
            monitor = monitor_or_503()
            return {
                "net_pnl": monitor.pnl_total or 0.0,
                "straddle_price": state.latest_iron_condor_data.get(
                    "strangle_credit", 0.0
                )
                or 0.0,
                "timestamp": datetime.now(UTC).isoformat(),
                "Current_pos_credit": monitor.Current_pos_credit or 0.0,
                "margin": state.margin,
                "available_margin": getattr(monitor, "available_margin", 0.0),
                "nifty_value": state.latest_iron_condor_data.get("spot_price", 0.0),
            }
        except HTTPException:
            raise
        except Exception as error:
            print(f"Error in pnl endpoint: {error!s}")
            raise HTTPException(status_code=500, detail=str(error)) from error

    @router.post("/manual_exit")
    def manual_exit():
        reserve("exit", "Manual exit is already in progress")
        try:
            monitor = monitor_or_503()
            result = monitor.Exiting_position(monitor.kite.positions()["net"])
            return {"message": format_exit_message(result), "details": result}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error in manual exit: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Manual exit failed: {error!s}"
            ) from error
        finally:
            state.finish_operation("exit")

    @router.post("/manual_stoploss")
    def manual_stoploss():
        reserve("stoploss", "Manual stoploss is already in progress")
        try:
            result = monitor_or_503().stoploss_order_button()
            return {"message": format_stoploss_message(result), "details": result}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error in manual stoploss: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Manual stoploss failed: {error!s}"
            ) from error
        finally:
            state.finish_operation("stoploss")

    @router.post("/manual_cancel_sl")
    def manual_cancel_sl():
        reserve("cancel_sl", "Manual SL cancel is already in progress")
        try:
            result = monitor_or_503().cancel_all_sl_orders()
            return {"message": format_cancel_sl_message(result), "details": result}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error in manual SL cancel: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Manual SL cancel failed: {error!s}"
            ) from error
        finally:
            state.finish_operation("cancel_sl")

    @router.get("/open_option_positions")
    def open_option_positions():
        try:
            return {"positions": monitor_or_503().get_open_option_positions()}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error fetching open option positions: {error!s}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to fetch open option positions: {error!s}",
            ) from error

    @router.post("/shift_legs")
    def shift_legs(payload: ShiftRequest):
        reserve("shift", "Leg shift is already in progress")
        try:
            if not payload.legs:
                raise HTTPException(status_code=400, detail="Missing legs selection")
            if payload.shift == 0:
                raise HTTPException(status_code=400, detail="Shift cannot be 0")
            legs = normalize_legs(payload.legs, include_quantity=True)
            if not legs:
                raise HTTPException(status_code=400, detail="No valid legs supplied")
            result = monitor_or_503().shift_selected_legs(legs, payload.shift)
            return {"message": format_shift_message(result), "details": result}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error shifting legs: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Leg shift failed: {error!s}"
            ) from error
        finally:
            state.finish_operation("shift")

    @router.post("/exit_selected_legs")
    def exit_selected_legs(payload: ExitLegsRequest):
        reserve("selected_exit", "Selected legs exit already in progress")
        try:
            if not payload.legs:
                raise HTTPException(status_code=400, detail="Missing legs selection")
            legs = normalize_legs(payload.legs, include_quantity=False)
            if not legs:
                raise HTTPException(status_code=400, detail="No valid legs supplied")
            result = monitor_or_503().exit_selected_legs(legs)
            return {"message": format_selected_exit_message(result), "details": result}
        except HTTPException:
            raise
        except Exception as error:
            print(f"❌ Error exiting selected legs: {error!s}")
            raise HTTPException(
                status_code=500, detail=f"Exit selected legs failed: {error!s}"
            ) from error
        finally:
            state.finish_operation("selected_exit")

    return router
