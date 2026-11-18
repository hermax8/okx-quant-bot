"""Construction des bougies multi-unités à partir des bougies fines, sans fuite d'information.

Convention : une bougie est indexée par son heure d'OUVERTURE ; ses valeurs ne sont connues
qu'à open_time + durée. `align_higher` décale donc une série d'unité supérieure à son heure
de CLÔTURE avant de la projeter sur l'unité inférieure.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TF = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def load_fine(root: str, inst: str, bar: str, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    from okxbot.data.candles import load
    from pathlib import Path
    df = load(Path(root), inst, bar)[["open", "high", "low", "close", "vol", "vol_quote"]]
    if start:
        df = df[df.index >= pd.Timestamp(start, tz="UTC")]
    if end:
        df = df[df.index < pd.Timestamp(end, tz="UTC")]
    return df


def resample(fine: pd.DataFrame, tf: str) -> pd.DataFrame:
    r = fine.resample(TF[tf], label="left", closed="left")
    out = pd.DataFrame({
        "open": r["open"].first(), "high": r["high"].max(), "low": r["low"].min(),
        "close": r["close"].last(), "vol": r["vol"].sum(), "vol_quote": r["vol_quote"].sum(),
    }).dropna(subset=["open"])
    return out


def align_higher(higher: pd.Series, higher_tf: str, lower_index: pd.DatetimeIndex, lower_tf: str) -> pd.Series:
    """Valeur de la dernière bougie supérieure CLÔTURÉE au moment où la bougie inférieure clôture."""
    h = higher.copy()
    h.index = h.index + pd.Timedelta(TF[higher_tf])          # heure de clôture
    lower_close = lower_index + pd.Timedelta(TF[lower_tf])
    vals = h.reindex(h.index.union(lower_close)).ffill().reindex(lower_close)
    return pd.Series(vals.to_numpy(), index=lower_index)


# --- Indicateurs (tous causaux) ---

def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus = np.where((up > dn) & (up > 0), up, 0.0)
    minus = np.where((dn > up) & (dn > 0), dn, 0.0)
    a = atr(df, n)
    pdi = 100 * pd.Series(plus, index=df.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    mdi = 100 * pd.Series(minus, index=df.index).ewm(alpha=1 / n, adjust=False, min_periods=n).mean() / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
