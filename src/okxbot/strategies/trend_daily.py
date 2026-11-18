"""T3 — Tendance multi-jours, longue et courte, sur un panier de cryptos (règles figées dans D-009).

Backtest vectorisé journalier : la décision à la clôture du jour t s'applique au rendement de t à t+1.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

LOOKBACKS = (10, 20, 40, 80, 160)


@dataclass
class T3Params:
    lookbacks: tuple = LOOKBACKS
    vol_span: int = 30
    cov_window: int = 90
    target_vol: float = 0.30
    asset_cap: float = 1.0
    gross_cap: float = 3.0
    min_history: int = 200
    trade_threshold: float = 0.02
    long_only: bool = False


def donchian_state(close: pd.Series, high: pd.Series, low: pd.Series, n: int) -> pd.Series:
    """État stop-and-reverse : +1 au-dessus du plus haut des n jours PRÉCÉDENTS, -1 sous le plus bas, sinon inchangé."""
    hh = high.rolling(n).max().shift(1)
    ll = low.rolling(n).min().shift(1)
    raw = pd.Series(np.where(close > hh, 1.0, np.where(close < ll, -1.0, np.nan)), index=close.index)
    return raw.ffill().fillna(0.0)


def scores(daily: dict[str, pd.DataFrame], p: T3Params) -> pd.DataFrame:
    out = {}
    idx = None
    for s, d in daily.items():
        idx = d.index if idx is None else idx.union(d.index)
    for s, d in daily.items():
        v = d.dropna(subset=["close"])            # avant cotation : pas de signal
        st = [donchian_state(v["close"], v["high"], v["low"], n) for n in p.lookbacks]
        sc = sum(st) / len(st)
        sc[np.arange(len(sc)) < p.min_history] = 0.0   # 200 jours d'historique PROPRE à l'actif
        if p.long_only:
            sc = sc.clip(lower=0)
        out[s] = sc.reindex(idx).fillna(0.0)
    return pd.DataFrame(out, index=idx)


def target_weights(daily: dict[str, pd.DataFrame], p: T3Params) -> pd.DataFrame:
    sc = scores(daily, p)
    close = pd.DataFrame({s: d["close"] for s, d in daily.items()}).reindex(sc.index)
    rets = np.log(close).diff()   # NaN avant cotation
    vol = rets.ewm(span=p.vol_span, min_periods=p.vol_span).std() * np.sqrt(365)
    raw = (sc / vol).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    w = pd.DataFrame(0.0, index=sc.index, columns=sc.columns)
    r = rets.fillna(0.0).to_numpy()
    rw = raw.to_numpy()
    for i in range(len(sc)):
        x = rw[i]
        if not np.any(x) or i < p.cov_window:
            continue
        cov = np.cov(r[i - p.cov_window + 1:i + 1].T) * 365
        pv = float(np.sqrt(max(x @ cov @ x, 1e-12)))
        y = x * (p.target_vol / pv)
        y = np.clip(y, -p.asset_cap, p.asset_cap)
        g = np.abs(y).sum()
        if g > p.gross_cap:
            y *= p.gross_cap / g
        w.iloc[i] = y
    return w


def apply_threshold(w: pd.DataFrame, thr: float) -> pd.DataFrame:
    held = np.zeros(w.shape[1]); out = np.zeros(w.shape)
    for i, row in enumerate(w.to_numpy()):
        chg = (np.abs(row - held) >= thr) | (np.sign(row) != np.sign(held))
        held = np.where(chg, row, held)
        out[i] = held
    return pd.DataFrame(out, index=w.index, columns=w.columns)


def backtest(daily: dict[str, pd.DataFrame], p: T3Params, cost: float = 0.0008,
             funding_daily: pd.DataFrame | None = None, funding_default_8h: float = 0.0001,
             cost_mult: float = 1.0) -> dict:
    """Renvoie rendements quotidiens nets, poids tenus, et composantes de coûts."""
    w = apply_threshold(target_weights(daily, p), p.trade_threshold)
    close = pd.DataFrame({s: d["close"] for s, d in daily.items()}).reindex(w.index)
    fwd = close.pct_change(fill_method=None).shift(-1).fillna(0.0)  # rendement de t à t+1
    gross = (w * fwd).sum(axis=1)
    turnover = w.diff().abs().fillna(w.abs()).sum(axis=1)
    trading = turnover * cost * cost_mult
    if funding_daily is None:
        fd = pd.DataFrame(3 * funding_default_8h, index=w.index, columns=w.columns)
    else:
        fd = funding_daily.reindex(index=w.index, columns=w.columns)
        fd = fd.fillna(3 * funding_default_8h)
    fund = (w * fd.shift(-1).fillna(3 * funding_default_8h)).sum(axis=1) * cost_mult  # payé pendant t→t+1
    net = gross - trading - fund
    return {"net": net.shift(1).fillna(0.0), "weights": w, "gross": gross.shift(1).fillna(0.0),
            "trading_cost": trading, "funding_cost": fund.shift(1).fillna(0.0), "turnover": turnover}


def daily_from_fine(fine: pd.DataFrame) -> pd.DataFrame:
    r = fine.resample("1D", label="left", closed="left")
    return pd.DataFrame({"open": r["open"].first(), "high": r["high"].max(), "low": r["low"].min(),
                         "close": r["close"].last(), "vol_quote": r["vol_quote"].sum()}).dropna(subset=["close"])
