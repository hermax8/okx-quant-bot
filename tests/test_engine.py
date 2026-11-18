"""Tests du moteur : règles d'exécution et absence de look-ahead."""
import numpy as np
import pandas as pd
import pytest

from okxbot.backtest import engine
from okxbot.backtest.bars import align_higher, resample
from okxbot.backtest.engine import Costs, Signals

ZERO = Costs(0, 0, 0, 0, 0)


def fine_from_closes(closes, start="2021-01-01", highs=None, lows=None, opens=None):
    idx = pd.date_range(start, periods=len(closes), freq="1min", tz="UTC")
    c = np.asarray(closes, float)
    o = np.asarray(opens if opens is not None else np.r_[c[0], c[:-1]], float)
    h = np.asarray(highs if highs is not None else np.maximum(o, c), float)
    l = np.asarray(lows if lows is not None else np.minimum(o, c), float)
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "vol": 1.0, "vol_quote": c}, index=idx)


def sig_on_15m(fine, entries, stop, tp=0.0, max_hold=1000):
    idx = resample(fine, "15m").index
    e = np.zeros(len(idx), np.int8)
    for k, v in entries.items():
        e[k] = v
    return Signals(idx, "15m", e, np.full(len(idx), stop), np.full(len(idx), tp), None, None, None, max_hold)


def test_entry_at_next_bar_open_not_signal_bar():
    closes = np.r_[np.full(15, 100.0), np.full(15, 110.0), np.full(15, 110.0)]
    fine = fine_from_closes(closes)
    tr = engine.run(fine, sig_on_15m(fine, {0: 1}, stop=50), ZERO)
    assert tr.iloc[0]["entry_time"] == fine.index[15]   # ouverture de la bougie 15m suivante
    assert tr.iloc[0]["entry_px"] == fine["open"].iloc[15]


def test_millisecond_index_like_parquet():
    """Régression : les Parquet OKX donnent un index en ms ; le moteur doit le gérer."""
    closes = np.r_[np.full(15, 100.0), np.full(30, 110.0)]
    fine = fine_from_closes(closes)
    fine.index = fine.index.as_unit("ms")
    sig = sig_on_15m(fine, {0: 1}, stop=50, max_hold=1)
    tr = engine.run(fine, sig, ZERO)
    assert len(tr) == 1 and tr.iloc[0]["reason"] == "durée max"
    assert tr.iloc[0]["exit_time"] - tr.iloc[0]["entry_time"] == pd.Timedelta(minutes=16)


def test_one_position_at_a_time():
    closes = np.r_[np.full(15, 100.0), np.full(60, 101.0)]
    fine = fine_from_closes(closes)
    fine.index = fine.index.as_unit("ms")
    tr = engine.run(fine, sig_on_15m(fine, {0: 1, 1: 1, 2: 1}, stop=50, max_hold=2), ZERO)
    assert len(tr) >= 2
    nxt = tr["entry_time"].iloc[1:].reset_index(drop=True)
    prev_exit = tr["exit_time"].iloc[:-1].reset_index(drop=True)
    assert (nxt >= prev_exit - pd.Timedelta(minutes=1)).all()


def test_stop_and_tp_same_minute_takes_stop():
    closes = np.full(45, 100.0)
    highs = closes.copy(); lows = closes.copy()
    highs[20] = 110; lows[20] = 90          # une minute touche les deux
    fine = fine_from_closes(closes, highs=highs, lows=lows)
    tr = engine.run(fine, sig_on_15m(fine, {0: 1}, stop=5, tp=5), ZERO)
    assert tr.iloc[0]["reason"] == "stop" and tr.iloc[0]["exit_px"] == 95


def test_gap_through_stop_fills_at_open():
    closes = np.r_[np.full(20, 100.0), np.full(25, 80.0)]
    opens = np.r_[np.full(20, 100.0), np.full(25, 80.0)]
    fine = fine_from_closes(closes, opens=opens)
    tr = engine.run(fine, sig_on_15m(fine, {0: 1}, stop=5), ZERO)
    assert tr.iloc[0]["exit_px"] == 80   # pas 95 : le marché a sauté le stop


def test_short_pnl_and_costs():
    closes = np.r_[np.full(15, 100.0), np.linspace(100, 90, 30)]
    fine = fine_from_closes(closes)
    c = Costs(fee=0.0005, slip_market=0, slip_stop=0, funding_8h=0)
    tr = engine.run(fine, sig_on_15m(fine, {0: -1}, stop=50, max_hold=1), c)
    t = tr.iloc[0]
    assert t["dir"] == -1 and t["gross"] > 0
    assert t["net"] == pytest.approx(t["gross"] - 0.001)


def test_align_higher_uses_only_closed_bars():
    idx = pd.date_range("2021-01-01", periods=8 * 60, freq="1min", tz="UTC")
    fine = pd.DataFrame({"open": 1.0, "high": 1.0, "low": 1.0, "close": np.arange(len(idx), dtype=float),
                         "vol": 1.0, "vol_quote": 1.0}, index=idx)
    h4 = resample(fine, "4h")
    h1 = resample(fine, "1h")
    al = align_higher(h4["close"], "4h", h1.index, "1h")
    # bougie 1h ouverte à 02:00 clôture à 03:00 : la bougie 4h 00:00 n'est pas encore close -> NaN
    assert np.isnan(al.loc["2021-01-01 02:00"])
    # bougie 1h ouverte à 03:00 clôture à 04:00 : la bougie 4h 00:00 vient de clôturer
    assert al.loc["2021-01-01 03:00"] == h4["close"].iloc[0]


@pytest.mark.parametrize("name", ["S1_breakout", "S2_momentum", "S3_squeeze", "S4_meanrev"])
def test_strategies_no_lookahead(name):
    """Les signaux calculés sur des données tronquées doivent être identiques à ceux calculés
    sur les données complètes, pour toutes les bougies antérieures à la troncature."""
    from okxbot.strategies.first_wave import STRATEGIES
    rng = np.random.default_rng(0)
    n = 60 * 24 * 40
    ret = rng.standard_t(4, n) * 0.001
    c = 100 * np.exp(np.cumsum(ret))
    fine = fine_from_closes(c, highs=c * (1 + np.abs(ret)), lows=c * (1 - np.abs(ret)))
    fine["vol_quote"] = rng.lognormal(0, 1, n)
    fn, grid = STRATEGIES[name]
    params = {k: v[0] for k, v in grid.items()}
    full = fn(fine, **params)
    cut = fine.index[int(n * 0.7)]
    part = fn(fine[fine.index < cut], **params)
    m = len(part.index) - 2   # on exclut la dernière bougie, incomplète dans la version tronquée
    assert np.array_equal(full.entry[:m], part.entry[:m])
    np.testing.assert_allclose(np.nan_to_num(full.stop_dist[:m]), np.nan_to_num(part.stop_dist[:m]))


def _limit_sig(fine, lim, d=1):
    s = sig_on_15m(fine, {0: d}, stop=50, max_hold=1)
    s.limit_px = np.zeros(len(s.index)); s.limit_px[0] = lim
    return s


def test_limit_entry_needs_strict_cross():
    closes = np.r_[np.full(15, 100.0), np.full(30, 100.0)]
    lows = closes.copy(); lows[20] = 99.0          # touche 99 sans passer dessous
    fine = fine_from_closes(closes, lows=lows)
    assert engine.run(fine, _limit_sig(fine, 99.0), ZERO).empty
    lows[20] = 98.9
    fine = fine_from_closes(closes, lows=lows)
    tr = engine.run(fine, _limit_sig(fine, 99.0), ZERO)
    assert len(tr) == 1 and tr.iloc[0]["entry_px"] == 99.0 and tr.iloc[0]["entry_time"] == fine.index[20]


def test_limit_entry_cancelled_after_one_bar_and_maker_fee():
    closes = np.r_[np.full(15, 100.0), np.full(15, 100.0), np.full(15, 90.0)]
    fine = fine_from_closes(closes)
    assert engine.run(fine, _limit_sig(fine, 95.0), ZERO).empty   # la baisse arrive une bougie trop tard
    lows = closes.copy(); lows[16] = 94
    fine = fine_from_closes(closes, lows=lows)
    c = Costs(fee=0.0005, fee_maker=0.0002, slip_market=0, slip_stop=0, funding_8h=0)
    t = engine.run(fine, _limit_sig(fine, 95.0), c).iloc[0]
    assert bool(t["maker_entry"]) and t["net"] == pytest.approx(t["gross"] - 0.0007)


@pytest.mark.parametrize("name", ["S1b_breakout_4h", "S2b_momentum_4h", "S2c_momentum_1h_limit"])
def test_second_wave_no_lookahead(name):
    from okxbot.strategies.second_wave import STRATEGIES
    rng = np.random.default_rng(1)
    n = 60 * 24 * 120
    ret = rng.standard_t(4, n) * 0.001
    c = 100 * np.exp(np.cumsum(ret))
    fine = fine_from_closes(c, highs=c * (1 + np.abs(ret)), lows=c * (1 - np.abs(ret)))
    fine["vol_quote"] = rng.lognormal(0, 1, n)
    fn, grid = STRATEGIES[name]
    params = {k: v[-1] for k, v in grid.items()}
    full = fn(fine, **params)
    cut = fine.index[int(n * 0.7)]
    part = fn(fine[fine.index < cut], **params)
    m = len(part.index) - 2
    assert np.array_equal(full.entry[:m], part.entry[:m])
    np.testing.assert_allclose(np.nan_to_num(full.limit_px[:m]), np.nan_to_num(part.limit_px[:m]))


def test_portfolio_cap_scales_new_positions():
    from okxbot.backtest.portfolio import capped_portfolio
    t0 = pd.Timestamp("2021-01-01", tz="UTC")
    tr = pd.DataFrame({
        "entry_time": [t0, t0 + pd.Timedelta(hours=1), t0 + pd.Timedelta(hours=2)],
        "exit_time": [t0 + pd.Timedelta(hours=10)] * 3,
        "risk_pct": [0.005, 0.005, 0.005],      # chaque position voudrait 1x le capital
        "net": [0.01, 0.01, 0.01]})
    curve, out = capped_portfolio(tr, risk=0.005, cap=1.0)
    assert out["taken"].tolist() == [True, False, False]
    assert out["frac"].iloc[0] == pytest.approx(1.0)
    assert curve.iloc[-1] == pytest.approx(1.01)


def test_real_funding_signed():
    closes = np.r_[np.full(15, 100.0), np.full(45, 100.0)]
    fine = fine_from_closes(closes)
    fund = pd.Series([0.001, 0.002], index=pd.DatetimeIndex([fine.index[20], fine.index[40]]))
    c = Costs(0, 0, 0, 0, 0.0001)
    long_ = engine.run(fine, sig_on_15m(fine, {0: 1}, stop=50, max_hold=3), c, funding=fund).iloc[0]
    short = engine.run(fine, sig_on_15m(fine, {0: -1}, stop=50, max_hold=3), c, funding=fund).iloc[0]
    assert long_["net"] == pytest.approx(-0.003) and short["net"] == pytest.approx(0.003)
