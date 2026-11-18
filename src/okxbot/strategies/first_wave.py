"""Première vague de stratégies (Tâche 2) — 4 moteurs, chacun 3 à 5 paramètres.

Toutes les décisions utilisent uniquement des bougies clôturées. Chaque fonction reçoit
les bougies de l'unité de signal (et éventuellement l'unité supérieure) et renvoie un objet Signals.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from okxbot.backtest.bars import adx, align_higher, atr, ema, resample
from okxbot.backtest.engine import Signals


def s1_breakout(fine: pd.DataFrame, tf: str = "1h", n: int = 40, stop_atr: float = 2.0, trail_atr: float = 3.0,
                trend_ema: int = 50, max_hold: int = 72) -> Signals:
    """Cassure de canal de Donchian dans le sens de la tendance 4 h, stop ATR, stop suiveur (chandelier)."""
    b = resample(fine, tf)
    h4 = resample(fine, "4h")
    trend_up = align_higher(h4["close"] > ema(h4["close"], trend_ema), "4h", b.index, tf).fillna(False).astype(bool)
    trend_dn = align_higher(h4["close"] < ema(h4["close"], trend_ema), "4h", b.index, tf).fillna(False).astype(bool)
    hi = b["high"].rolling(n).max().shift(1)   # canal des n bougies PRÉCÉDENTES
    lo = b["low"].rolling(n).min().shift(1)
    a = atr(b, 14)
    long_ = (b["close"] > hi) & trend_up
    short = (b["close"] < lo) & trend_dn
    entry = np.where(long_, 1, np.where(short, -1, 0))
    ex_n = max(n // 2, 5)
    exit_long = b["close"] < b["low"].rolling(ex_n).min().shift(1)
    exit_short = b["close"] > b["high"].rolling(ex_n).max().shift(1)
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), None, exit_long.to_numpy(), exit_short.to_numpy(),
                   (trail_atr * a).to_numpy(), max_hold, {"bars": b})


def s2_momentum(fine: pd.DataFrame, tf: str = "1h", lookback: int = 12, z_thr: float = 1.5, vol_ratio: float = 1.2,
                hold: int = 8, stop_atr: float = 2.0) -> Signals:
    """Momentum intraday : rendement des `lookback` dernières bougies normalisé par la volatilité,
    confirmé par un volume supérieur à la moyenne ; sortie après `hold` bougies ou stop."""
    b = resample(fine, tf)
    lr = np.log(b["close"]).diff()
    vol = lr.rolling(24 * 7 if tf == "1h" else 96 * 7).std()
    mom = lr.rolling(lookback).sum() / (vol * np.sqrt(lookback))
    vr = b["vol_quote"].rolling(lookback).sum() / (b["vol_quote"].rolling(lookback * 20).mean() * lookback)
    a = atr(b, 14)
    ok = vr > vol_ratio
    entry = np.where((mom > z_thr) & ok, 1, np.where((mom < -z_thr) & ok, -1, 0))
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), None, None, None, None, hold, {"bars": b})


def s3_squeeze(fine: pd.DataFrame, tf: str = "1h", pct: float = 0.2, tp_atr: float = 4.0, stop_atr: float = 1.5,
               max_hold: int = 48) -> Signals:
    """Compression de volatilité (largeur des bandes de Bollinger dans le `pct` le plus bas des 500 dernières
    bougies, au cours des 5 dernières bougies), puis clôture hors des bandes : entrée dans le sens de la cassure."""
    b = resample(fine, tf)
    mid = b["close"].rolling(20).mean()
    sd = b["close"].rolling(20).std()
    up, dn = mid + 2 * sd, mid - 2 * sd
    width = (up - dn) / mid
    rank = width.rolling(500, min_periods=200).rank(pct=True)
    squeezed = (rank.shift(1) <= pct).rolling(5).max().astype(bool)
    a = atr(b, 14)
    entry = np.where(squeezed & (b["close"] > up), 1, np.where(squeezed & (b["close"] < dn), -1, 0))
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), (tp_atr * a).to_numpy(), None, None, None,
                   max_hold, {"bars": b})


def s4_mean_reversion(fine: pd.DataFrame, tf: str = "15m", z_thr: float = 2.0, adx_max: float = 20.0,
                      stop_atr: float = 2.0, max_hold: int = 16) -> Signals:
    """Retour à la moyenne, seulement quand la tendance 1 h est faible (ADX bas).
    Entrée quand le prix s'écarte de plus de z_thr écarts-types de sa moyenne 20, sortie au retour à la moyenne."""
    b = resample(fine, tf)
    h1 = resample(fine, "1h")
    adx1 = align_higher(adx(h1, 14), "1h", b.index, tf)
    mid = b["close"].rolling(20).mean()
    sd = b["close"].rolling(20).std()
    z = (b["close"] - mid) / sd
    a = atr(b, 14)
    rng = adx1 < adx_max
    entry = np.where((z < -z_thr) & rng, 1, np.where((z > z_thr) & rng, -1, 0))
    exit_long = (z >= 0).to_numpy()
    exit_short = (z <= 0).to_numpy()
    return Signals(b.index, tf, entry, (stop_atr * a).to_numpy(), None, exit_long, exit_short, None, max_hold,
                   {"bars": b})


STRATEGIES = {
    "S1_breakout": (s1_breakout, {
        "tf": ["1h"], "n": [20, 40, 80], "stop_atr": [1.5, 2.5], "trail_atr": [2.0, 3.0, 4.0], "trend_ema": [50],
        "max_hold": [72]}),
    "S2_momentum": (s2_momentum, {
        "tf": ["1h"], "lookback": [6, 12, 24], "z_thr": [1.0, 1.5, 2.0], "vol_ratio": [1.2], "hold": [4, 8, 16],
        "stop_atr": [2.0]}),
    "S3_squeeze": (s3_squeeze, {
        "tf": ["1h"], "pct": [0.1, 0.2], "tp_atr": [3.0, 5.0], "stop_atr": [1.5, 2.5], "max_hold": [48]}),
    "S4_meanrev": (s4_mean_reversion, {
        "tf": ["15m"], "z_thr": [2.0, 2.5, 3.0], "adx_max": [20.0, 25.0], "stop_atr": [1.5, 2.5], "max_hold": [16]}),
}
