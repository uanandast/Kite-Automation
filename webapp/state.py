"""Mutable application state shared by runtime workers and HTTP handlers."""

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock
from types import ModuleType
from typing import Any


@dataclass
class RuntimeState:
    latest_iron_condor_data: dict[str, Any] = field(default_factory=dict)
    monitor_module: ModuleType | None = None
    get_current_iron_condor: Callable[..., Any] | None = None
    get_previous_day_close: Callable[..., tuple[float, str]] | None = None
    set_selected_index: Callable[[str], str] | None = None
    get_selected_index: Callable[[], str] | None = None
    get_available_indices: Callable[[], list[str]] | None = None
    margin: float = 0
    previous_day_close: float = 0
    name: str = "Unknown"
    pnl_history: dict[str, deque[dict[str, float | int]]] = field(default_factory=dict)
    pnl_history_lock: Lock = field(default_factory=Lock)
    index_update_lock: Lock = field(default_factory=Lock)
    operation_locks: dict[str, Lock] = field(
        default_factory=lambda: {
            key: Lock()
            for key in (
                "exit",
                "stoploss",
                "cancel_sl",
                "shift",
                "selected_exit",
                "recommended_entry",
                "close_account",
            )
        }
    )
    operations_in_progress: set[str] = field(default_factory=set)

    def start_operation(self, operation: str) -> bool:
        with self.operation_locks[operation]:
            if operation in self.operations_in_progress:
                return False
            self.operations_in_progress.add(operation)
            return True

    def finish_operation(self, operation: str) -> None:
        with self.operation_locks[operation]:
            self.operations_in_progress.discard(operation)

    def record_pnl_sample(
        self, index: str, timestamp_ms: int, net_pnl: float, straddle_price: float
    ) -> None:
        """Keep a compact, current-process chart buffer for one index."""
        index_key = index.strip().lower()
        sample = {
            "timestamp": timestamp_ms,
            "net_pnl": net_pnl,
            "straddle_price": straddle_price,
        }
        with self.pnl_history_lock:
            samples = self.pnl_history.setdefault(index_key, deque(maxlen=3600))
            if samples and samples[-1]["timestamp"] == timestamp_ms:
                samples[-1] = sample
            else:
                samples.append(sample)

    def get_pnl_history(self, index: str) -> list[dict[str, float | int]]:
        with self.pnl_history_lock:
            return list(self.pnl_history.get(index.strip().lower(), ()))
