"""Serialization helpers to guarantee JSON compliance."""

import math
from typing import Any

import numpy as np


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize data structures for JSON serialization.
    Replaces NaN, Infinity, and -Infinity float values with None (JSON null).
    Converts numpy numeric and boolean types to native Python types.
    """
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return float(obj)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    return obj
