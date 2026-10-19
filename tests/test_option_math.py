import numpy as np
import pytest

from Core.option_math import (
    BS_CALL,
    BS_PUT,
    bs_delta,
    implied_vol,
    vectorized_iv_and_delta,
)


def test_black_scholes_call_and_put():
    S = 24000.0
    K = 24000.0
    T = 10 / 365.0
    r = 0.08
    sigma = 0.15

    call_price = BS_CALL(S, K, T, r, sigma)
    put_price = BS_PUT(S, K, T, r, sigma)

    assert call_price > 0
    assert put_price > 0
    # Put-Call Parity: C - P = S - K * exp(-r * T)
    parity_diff = (call_price - put_price) - (S - K * np.exp(-r * T))
    assert abs(parity_diff) < 1e-4


def test_implied_vol_accuracy():
    S = 24500.0
    K = 24600.0
    T = 7 / 365.0
    r = 0.08
    target_sigma = 0.18

    call_price = BS_CALL(S, K, T, r, target_sigma)
    put_price = BS_PUT(S, K, T, r, target_sigma)

    solved_call_iv = implied_vol(call_price, S, K, T, r, "call")
    solved_put_iv = implied_vol(put_price, S, K, T, r, "put")

    assert abs(solved_call_iv - target_sigma) < 1e-3
    assert abs(solved_put_iv - target_sigma) < 1e-3


def test_implied_vol_invalid_inputs():
    assert np.isnan(implied_vol(-10.0, 24000, 24000, 0.05, 0.08, "call"))
    assert np.isnan(implied_vol(100.0, 0, 24000, 0.05, 0.08, "call"))
    assert np.isnan(implied_vol(100.0, 24000, 24000, 0, 0.08, "call"))

    with pytest.raises(ValueError):
        implied_vol(100.0, 24000, 24000, 0.05, 0.08, "invalid_type")


def test_bs_delta():
    S = 24000.0
    K = 24000.0
    T = 15 / 365.0
    r = 0.08
    sigma = 0.16

    call_delta = bs_delta(S, K, T, r, sigma, "call")
    put_delta = bs_delta(S, K, T, r, sigma, "put")

    assert 0.4 < call_delta < 0.6
    assert -0.6 < put_delta < -0.4
    # Call Delta - Put Delta should be approximately 1.0 (or exp(-q*T))
    assert abs((call_delta - put_delta) - 1.0) < 1e-2


def test_vectorized_iv_and_delta():
    S = 24200.0
    future = 24220.0
    strikes = np.array([24000.0, 24200.0, 24400.0, 24000.0, 24200.0, 24400.0])
    is_call = np.array([True, True, True, False, False, False])
    times = np.full(6, 6 / 365.0)
    r = 0.08
    true_sigmas = np.array([0.16, 0.15, 0.17, 0.16, 0.15, 0.17])

    prices = []
    for i in range(len(strikes)):
        if is_call[i]:
            prices.append(BS_CALL(S, strikes[i], times[i], r, true_sigmas[i]))
        else:
            prices.append(BS_PUT(S, strikes[i], times[i], r, true_sigmas[i]))
    prices = np.array(prices)

    ivs, deltas = vectorized_iv_and_delta(prices, S, future, strikes, times, r, is_call)

    assert len(ivs) == 6
    assert len(deltas) == 6
    for i in range(6):
        assert abs(ivs[i] - true_sigmas[i]) < 1e-3
        if is_call[i]:
            assert 0 < deltas[i] < 1.0
        else:
            assert -1.0 < deltas[i] < 0
