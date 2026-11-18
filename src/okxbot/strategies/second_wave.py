"""Vague 2 (Tâche 2) : S1 et S2 sur horizon plus long (4 h), entrées au marché ou en ordre limite (maker).

Changements décidés AVANT les résultats (docs/research/2026-11-18_T2_premiers_backtests.md) :
1) horizon 4 h et durées de 12 h à 3 jours ; 2) entrées limites ; 3) combinaison S1+S2 et altcoins.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from okxbot.backtest.bars import TF, align_higher, atr, ema, resample
from okxbot.backtest.engine import Signals

LIMIT_ATR = 0.1   # ordre limite placé 0,1 ATR plus favorablement que la clôture du signal


def _bars_per_week(tf: str) -> int:
    return int(pd.Timedelta("7D") / pd.Timedelta(TF[tf]))


def _limit(entry: np.ndarray, close: pd.Series, a: pd.Series, mode: str) -> np.ndarray | None:
    if mode != "limit":
        return None
    px = np.where(entry == 1, close - LIMIT_ATR * a, np.where(entry == -1, close + LIMIT_ATR * a, 0.0))
    return np.nan_to_num(px)


def s1b_breakout(fine: pd.DataFrame, tf: str = "4h", n: int = 20, stop_atr: float = 2.0, trail_atr: float = 3.0,
                 trend_ema: int = 50, max_hold: int = 18, entry_mode: str = "market") -> Signals:
    """Cassure de Donchian sur `tf`, filtre de tendance journalier (EMA), stop ATR et stop suiveur."""
    b = resample(fine, tf)
    d1 = resample(fine, "1d")
    up = align_higher(d1["close"] > ema(d1["close"], trend_ema), "1d", b.index, tf).fillna(False).astype(bool)
    dn = align_higher(d1["close"] < ema(d1["close"], trend_ema), "1d", b.index, tf).fillna(False).astype(bool)
    hi = b["high"].rolling(n).max().shift(1)
    lo = b["low"].rolling(n).min().shift(1)
    a = atr(b, 14)
    entry = np.where((b["close"] > hi) & up, 1, np.where((b["close"] < lo) & dn, -1, 0))
    ex_n = max(n // 2, 5)
    exit_long = (b["close"] < b["low"].rolling(ex_n).min().shift(1)).to_numpy()
    exit_short = (b["close"] > b["high"].rolling(ex_n).max().shift(1)).to_numpy()
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), None, exit_long, exit_short,
                   (trail_atr * a).to_numpy(), max_hold, {}, _limit(entry, b["close"], a, entry_mode))


def s2b_momentum(fine: pd.DataFrame, tf: str = "4h", lookback: int = 6, z_thr: float = 1.5, vol_ratio: float = 1.2,
                 hold: int = 6, stop_atr: float = 2.0, entry_mode: str = "market") -> Signals:
    """Momentum normalisé par la volatilité (fenêtre d'une semaine), confirmé par le volume."""
    b = resample(fine, tf)
    lr = np.log(b["close"]).diff()
    vol = lr.rolling(max(_bars_per_week(tf), 20)).std()
    mom = lr.rolling(lookback).sum() / (vol * np.sqrt(lookback))
    vr = b["vol_quote"].rolling(lookback).sum() / (b["vol_quote"].rolling(lookback * 20).mean() * lookback)
    a = atr(b, 14)
    ok = vr > vol_ratio
    entry = np.where((mom > z_thr) & ok, 1, np.where((mom < -z_thr) & ok, -1, 0))
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), None, None, None, None, hold, {},
                   _limit(entry, b["close"], a, entry_mode))


STRATEGIES = {
    "S1b_breakout_4h": (s1b_breakout, {
        "tf": ["4h"], "n": [20, 40], "stop_atr": [2.0, 3.0], "trail_atr": [3.0, 4.0], "trend_ema": [50],
        "max_hold": [18], "entry_mode": ["market", "limit"]}),
    "S2b_momentum_4h": (s2b_momentum, {
        "tf": ["4h"], "lookback": [3, 6, 12], "z_thr": [1.0, 1.5], "vol_ratio": [1.2], "hold": [3, 6, 12],
        "stop_atr": [2.0], "entry_mode": ["market", "limit"]}),
    # S2 au même horizon que la vague 1 (1 h) mais en entrée limite : isole l'effet des frais maker
    "S2c_momentum_1h_limit": (s2b_momentum, {
        "tf": ["1h"], "lookback": [6, 12, 24], "z_thr": [1.0, 1.5, 2.0], "vol_ratio": [1.2], "hold": [4, 8, 16],
        "stop_atr": [2.0], "entry_mode": ["limit"]}),
}
