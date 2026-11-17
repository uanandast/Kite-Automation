"""Black-Scholes pricing, implied-volatility, and delta calculations."""

import numpy as np
from scipy.optimize import brentq, minimize_scalar
from scipy.special import ndtr

# Use scipy.special.ndtr directly for 200x+ faster Gaussian CDF calculation.
# ndtr operates seamlessly on both scalar floats and numpy arrays.
N = ndtr
_INV_SQRT_2PI = 0.3989422804014327


def BS_CALL(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return S * N(d1) - K * np.exp(-r * T) * N(d2)


def BS_PUT(S, K, T, r, sigma):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return K * np.exp(-r * T) * N(-d2) - S * N(-d1)


def implied_vol(opt_value, S, K, T, r, type_="call"):
    """Solve for IV using Newton-Raphson with fallback to brentq/bounded minimization."""
    if opt_value is None or opt_value <= 0 or S <= 0 or K <= 0 or T <= 0:
        return np.nan

    normalized_type = str(type_).strip().lower()
    if normalized_type in ("call", "ce"):
        is_call = True
        pricing_function = BS_CALL
    elif normalized_type in ("put", "pe"):
        is_call = False
        pricing_function = BS_PUT
    else:
        raise ValueError("type_ must be 'put' or 'call'")

    # Check intrinsic value lower bound
    exp_rT = np.exp(-r * T)
    intrinsic = max(0.0, (S - K * exp_rT) if is_call else (K * exp_rT - S))
    if opt_value < intrinsic:
        return np.nan

    # Fast Newton-Raphson solver (quadratic convergence)
    sqrt_T = np.sqrt(T)
    sigma = 0.25
    for _ in range(10):
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
        d2 = d1 - sigma * sqrt_T
        price = (
            S * N(d1) - K * exp_rT * N(d2)
            if is_call
            else K * exp_rT * N(-d2) - S * N(-d1)
        )
        diff = price - opt_value
        if abs(diff) < 1e-4:
            return float(sigma)

        vega = S * sqrt_T * _INV_SQRT_2PI * np.exp(-0.5 * d1**2)
        if vega < 1e-7:
            break
        step = diff / vega
        sigma -= step
        if sigma <= 0.001 or sigma > 3.0:
            break
    else:
        if 0.001 <= sigma <= 3.0 and abs(diff) < 1e-3:
            return float(sigma)

    # Fallback to brentq
    try:
        return brentq(
            lambda sig: pricing_function(S, K, T, r, sig) - opt_value, 0.001, 3.0
        )
    except Exception:
        # Fallback to bounded minimization
        try:
            result = minimize_scalar(
                lambda sig: abs(pricing_function(S, K, T, r, sig) - opt_value),
                bounds=(0.01, 3),
                method="bounded",
            )
            return float(result.x)
        except Exception:
            return np.nan


def bs_delta(S, K, T, r, sigma, option_type="call"):
    d1 = (np.log(S / K) + (r + sigma**2 / 2) * T) / (sigma * np.sqrt(T))
    opt_type = str(option_type).strip().lower()
    return N(d1) if opt_type in ("call", "ce") else -N(-d1)


def vectorized_iv_and_delta(
    opt_prices: np.ndarray,
    spot: float,
    future: float | None,
    strikes: np.ndarray,
    times: np.ndarray,
    r: float,
    is_call_mask: np.ndarray,
    max_iter: int = 8,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vectorized computation of Implied Volatility and Delta across multiple options.
    Uses array operations for simultaneous convergence across all strikes.
    """
    n = len(opt_prices)
    ivs = np.full(n, np.nan, dtype=np.float64)
    deltas = np.full(n, np.nan, dtype=np.float64)
    if n == 0 or spot <= 0:
        return ivs, deltas

    fut = future if (future is not None and future > 0) else spot
    sqrt_T = np.sqrt(np.maximum(times, 1e-8))
    exp_rT = np.exp(-r * times)

    # Intrinsic value check
    intrinsic = np.where(
        is_call_mask,
        np.maximum(0.0, spot - strikes * exp_rT),
        np.maximum(0.0, strikes * exp_rT - spot),
    )

    valid = (opt_prices > intrinsic) & (times > 0) & (strikes > 0)
    if not np.any(valid):
        return ivs, deltas

    sigmas = np.full(n, 0.25, dtype=np.float64)
    active = valid.copy()

    for _ in range(max_iter):
        if not np.any(active):
            break
        k_act = strikes[active]
        s_act = sigmas[active]
        t_act = times[active]
        sqt_act = sqrt_T[active]
        exp_act = exp_rT[active]
        p_act = opt_prices[active]
        call_act = is_call_mask[active]

        d1 = (np.log(spot / k_act) + (r + 0.5 * s_act**2) * t_act) / (s_act * sqt_act)
        d2 = d1 - s_act * sqt_act

        nd1 = N(d1)
        nd2 = N(d2)
        n_minus_d1 = N(-d1)
        n_minus_d2 = N(-d2)

        call_price = spot * nd1 - k_act * exp_act * nd2
        put_price = k_act * exp_act * n_minus_d2 - spot * n_minus_d1
        est_price = np.where(call_act, call_price, put_price)

        diff = est_price - p_act
        converged = np.abs(diff) < 1e-4

        vega = spot * sqt_act * _INV_SQRT_2PI * np.exp(-0.5 * d1**2)
        valid_vega = vega > 1e-7

        step = np.where(valid_vega, diff / np.maximum(vega, 1e-7), 0.0)
        s_act_new = s_act - step

        sigmas[active] = s_act_new
        in_bounds = (s_act_new >= 0.001) & (s_act_new <= 3.0)
        active_idx = np.where(active)[0]
        active[active_idx] = (~converged) & in_bounds & valid_vega

    # Record solved values
    solved = valid & (sigmas >= 0.001) & (sigmas <= 3.0)
    ivs[solved] = sigmas[solved]

    # For any unresolved valid items, fallback to scalar solver
    unresolved = valid & np.isnan(ivs)
    if np.any(unresolved):
        for idx in np.where(unresolved)[0]:
            opt_type = "call" if is_call_mask[idx] else "put"
            sig = implied_vol(
                opt_prices[idx], spot, strikes[idx], times[idx], r, opt_type
            )
            if not np.isnan(sig) and 0.001 <= sig <= 3.0:
                ivs[idx] = sig

    # Compute deltas for all solved items with fut
    has_iv = ~np.isnan(ivs)
    if np.any(has_iv):
        k_val = strikes[has_iv]
        s_val = ivs[has_iv]
        t_val = times[has_iv]
        sqt_val = sqrt_T[has_iv]
        d1_val = (np.log(fut / k_val) + (r + 0.5 * s_val**2) * t_val) / (
            s_val * sqt_val
        )
        deltas[has_iv] = np.where(is_call_mask[has_iv], N(d1_val), -N(-d1_val))

    return ivs, deltas

