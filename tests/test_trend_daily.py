import numpy as np
import pandas as pd
import pytest

from okxbot.strategies.trend_daily import T3Params, backtest, donchian_state, target_weights


def synth(n=900, seed=0, k=4):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="D", tz="UTC")
    out = {}
    for j in range(k):
        r = rng.normal(0.0005 * (j - 1), 0.03, n)
        c = 100 * np.exp(np.cumsum(r))
        out[f"A{j}"] = pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "vol_quote": 1.0}, index=idx)
    return out


def test_donchian_state_reverses():
    idx = pd.date_range("2020-01-01", periods=8, freq="D")
    c = pd.Series([10, 10, 10, 12, 11, 11, 8, 9], index=idx, dtype=float)
    st = donchian_state(c, c, c, 3)
    assert list(st) == [0, 0, 0, 1, 1, 1, -1, -1]


def test_no_lookahead_weights():
    d = synth()
    p = T3Params(min_history=200)
    full = target_weights(d, p)
    cut = {k: v.iloc[:700] for k, v in d.items()}
    part = target_weights(cut, p)
    pd.testing.assert_frame_equal(full.iloc[:700], part, check_freq=False)


def test_caps_and_costs():
    d = synth()
    p = T3Params()
    res = backtest(d, p, cost=0.001)
    w = res["weights"]
    assert (w.abs().sum(axis=1) <= p.gross_cap + 1e-9).all() and (w.abs() <= p.asset_cap + 1e-9).all().all()
    # le coût d'un jour = rotation x coût unitaire
    i = int(np.argmax(res["turnover"].to_numpy()))
    assert res["trading_cost"].iloc[i] == pytest.approx(res["turnover"].iloc[i] * 0.001)
    # long-only : jamais de poids négatif
    assert (backtest(d, T3Params(long_only=True))["weights"] >= 0).all().all()


def test_late_listing_waits_own_history():
    d = synth(n=900)
    d["A3"].loc[d["A3"].index < d["A3"].index[500], ["open", "high", "low", "close"]] = np.nan
    w = target_weights(d, T3Params(min_history=200))
    assert (w["A3"].iloc[:700] == 0).all()
