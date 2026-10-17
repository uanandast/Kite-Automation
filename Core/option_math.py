"""Black-Scholes pricing, implied-volatility, and delta calculations."""

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.stats import norm

N = norm.cdf


def BS_CALL(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * N(d1) - K * np.exp(-r * T) * N(d2)


def BS_PUT(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * N(-d2) - S * N(-d1)


def implied_vol(opt_value, S, K, T, r, type_="call"):
    """Solve for IV, using bounded minimization when a root is unavailable."""
    try:
        pricing_function = (
            BS_CALL if type_ == "call" else BS_PUT if type_ == "put" else None
        )
        if pricing_function is None:
            raise ValueError("type_ must be 'put' or 'call'")
        return brentq(
            lambda sigma: pricing_function(S, K, T, r, sigma) - opt_value, 0.001, 3.0
        )
    except Exception:  # noqa: BLE001
        try:
            pricing_function = BS_CALL if type_ == "call" else BS_PUT
            result = minimize_scalar(
                lambda sigma: abs(pricing_function(S, K, T, r, sigma) - opt_value),
                bounds=(0.01, 3),
                method="bounded",
            )
            return result.x
        except Exception:  # noqa: BLE001
            return np.nan


def bs_delta(S, K, T, r, sigma, option_type="call"):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    return N(d1) if option_type == "call" else -N(-d1)
