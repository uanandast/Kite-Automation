"""User-facing messages for order-management endpoint responses."""

from typing import Any


def format_cancel_sl_message(result: dict[str, Any]) -> str:
    if result.get("requested", 0) == 0:
        return "No open SL orders to cancel"
    message = f"Cancelled {result.get('cancelled', 0)} SL orders"
    if result.get("errors", 0) > 0:
        message += f" ({result.get('errors', 0)} errors)"
    return message


def format_stoploss_message(result: dict[str, Any]) -> str:
    if result.get("positions", 0) == 0:
        return "No option positions found for SL"
    message = f"Placed {result.get('placed_orders', 0)} SL orders"
    if result.get("skipped", 0) > 0:
        message += f", skipped {result.get('skipped', 0)} existing"
    if result.get("failed_positions", 0) > 0:
        message += f" ({result.get('failed_positions', 0)} failed)"
    return message


def format_exit_message(result: dict[str, Any]) -> str:
    if result.get("in_progress"):
        return result.get("error") or "Exit all is already in progress"
    if result.get("attempted", 0) == 0:
        return "No open positions to exit"
    short_done = result.get("short_confirmed", result.get("short_succeeded", 0))
    long_done = result.get("long_confirmed", result.get("long_succeeded", 0))
    message = f"Exited {short_done} short legs, then {long_done} long legs"
    if result.get("failed", 0) > 0:
        message += f" ({result.get('failed', 0)} failed)"
    if result.get("error"):
        message += f": {result.get('error')}"
    return message


def format_shift_message(result: dict[str, Any]) -> str:
    requested = result.get("requested", 0)
    if requested == 0:
        return "No legs selected for shift"
    message = f"Shifted {result.get('succeeded', 0)}/{requested} legs"
    if result.get("failed", 0) > 0:
        message += f" ({result.get('failed', 0)} failed)"
    return message


def format_selected_exit_message(result: dict[str, Any]) -> str:
    requested = result.get("requested", 0)
    if requested == 0:
        return "No legs selected for exit"
    message = f"Exited {result.get('succeeded', 0)}/{requested} selected legs"
    if result.get("failed", 0) > 0:
        message += f" ({result.get('failed', 0)} failed)"
    return message
