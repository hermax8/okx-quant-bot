"""Moteur de backtest événementiel (numba).

Règles d'exécution (réalistes, plutôt pessimistes) :
- Un signal est calculé à la CLÔTURE d'une bougie de signal ; l'ordre est exécuté à l'OUVERTURE
  de la bougie fine suivante (market), avec slippage.
- Stop et take-profit sont vérifiés minute par minute (bougies fines). Si stop et TP sont touchés
  dans la même bougie fine, on retient le STOP (pire cas). Si le prix ouvre au-delà du stop (gap),
  on sort au prix d'ouverture.
- Sorties sur signal ou sur durée maximale : à l'ouverture suivante, au marché.
- Frais taker des deux côtés, funding facturé quel que soit le sens (hypothèse prudente),
  taille de position par le risque, plafonnée à 1x le capital (pas de levier).
- Une seule position à la fois par actif et par stratégie.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numba as nb
import numpy as np
import pandas as pd

from .bars import TF

EXIT_STOP, EXIT_TP, EXIT_SIGNAL, EXIT_TIME, EXIT_END = 0, 1, 2, 3, 4
EXIT_NAMES = {0: "stop", 1: "take-profit", 2: "signal", 3: "durée max", 4: "fin de données"}


@dataclass
class Costs:
    fee: float = 0.0005          # taker X-Perps, par côté
    slip_market: float = 0.0001  # 1 pb sur les ordres au marché (entrées, sorties signal/durée)
    slip_stop: float = 0.0003    # 3 pb sur les stops
    funding_8h: float = 0.0001   # 0,01 % par 8 h, toujours payé (prudent)

    def scaled(self, k: float) -> "Costs":
        return Costs(self.fee * k, self.slip_market * k, self.slip_stop * k, self.funding_8h * k)


@dataclass
class Signals:
    """Tableaux alignés sur les bougies de signal (index = heure d'ouverture)."""
    index: pd.DatetimeIndex
    tf: str
    entry: np.ndarray                 # +1 / -1 / 0, connu à la clôture
    stop_dist: np.ndarray             # distance du stop initial (prix)
    tp_dist: np.ndarray | None = None  # 0 = pas de TP
    exit_long: np.ndarray | None = None
    exit_short: np.ndarray | None = None
    trail_dist: np.ndarray | None = None  # 0 = pas de stop suiveur
    max_hold: int = 10_000
    meta: dict = field(default_factory=dict)


@nb.njit(cache=True)
def _simulate(fo, fh, fl, fc, b_start, b_end, close, entry, stop_dist, tp_dist, exit_l, exit_s, trail,
              max_hold, slip_m, slip_s):
    nbars = len(b_start)
    max_tr = nbars
    t_ein = np.empty(max_tr, np.int64); t_eout = np.empty(max_tr, np.int64)
    t_dir = np.empty(max_tr, np.int8); t_pin = np.empty(max_tr); t_pout = np.empty(max_tr)
    t_risk = np.empty(max_tr); t_reason = np.empty(max_tr, np.int8); t_bin = np.empty(max_tr, np.int64)
    n = 0
    pos = 0; pin = 0.0; stop = 0.0; tp = 0.0; ein = 0; bin_ = 0; risk = 0.0
    pend_exit = -1  # raison de sortie en attente (à l'ouverture suivante)
    for i in range(1, nbars):
        j0 = b_start[i]; j1 = b_end[i]
        if j1 <= j0:
            continue
        # 1) ordres en attente à l'ouverture de la bougie i
        if pos != 0 and pend_exit >= 0:
            px = fo[j0] * (1.0 - pos * slip_m)
            t_ein[n] = ein; t_eout[n] = j0; t_dir[n] = pos; t_pin[n] = pin; t_pout[n] = px
            t_risk[n] = risk; t_reason[n] = pend_exit; t_bin[n] = bin_; n += 1
            pos = 0; pend_exit = -1
        if pos == 0 and entry[i - 1] != 0 and stop_dist[i - 1] > 0 and not np.isnan(stop_dist[i - 1]):
            pos = entry[i - 1]
            pin = fo[j0] * (1.0 + pos * slip_m)
            stop = pin - pos * stop_dist[i - 1]
            tp = pin + pos * tp_dist[i - 1] if tp_dist[i - 1] > 0 else 0.0
            risk = stop_dist[i - 1] / pin
            ein = j0; bin_ = i
        # 2) parcours minute par minute
        if pos != 0:
            for j in range(j0, j1):
                hit = -1; px = 0.0
                if pos == 1:
                    if fo[j] <= stop:
                        hit = EXIT_STOP; px = fo[j] * (1 - slip_s)
                    elif fl[j] <= stop:
                        hit = EXIT_STOP; px = stop * (1 - slip_s)
                    elif tp > 0 and fo[j] >= tp:
                        hit = EXIT_TP; px = fo[j]
                    elif tp > 0 and fh[j] >= tp:
                        hit = EXIT_TP; px = tp
                else:
                    if fo[j] >= stop:
                        hit = EXIT_STOP; px = fo[j] * (1 + slip_s)
                    elif fh[j] >= stop:
                        hit = EXIT_STOP; px = stop * (1 + slip_s)
                    elif tp > 0 and fo[j] <= tp:
                        hit = EXIT_TP; px = fo[j]
                    elif tp > 0 and fl[j] <= tp:
                        hit = EXIT_TP; px = tp
                if hit >= 0:
                    t_ein[n] = ein; t_eout[n] = j; t_dir[n] = pos; t_pin[n] = pin; t_pout[n] = px
                    t_risk[n] = risk; t_reason[n] = hit; t_bin[n] = bin_; n += 1
                    pos = 0
                    break
        # 3) à la clôture : stop suiveur, sortie sur signal, durée max
        if pos != 0:
            if trail[i] > 0:
                if pos == 1:
                    stop = max(stop, close[i] - trail[i])
                else:
                    stop = min(stop, close[i] + trail[i])
            if (pos == 1 and exit_l[i]) or (pos == -1 and exit_s[i]):
                pend_exit = EXIT_SIGNAL
            elif i - bin_ + 1 >= max_hold:
                pend_exit = EXIT_TIME
    if pos != 0:
        j = b_end[nbars - 1] - 1
        t_ein[n] = ein; t_eout[n] = j; t_dir[n] = pos; t_pin[n] = pin; t_pout[n] = fc[j]
        t_risk[n] = risk; t_reason[n] = EXIT_END; t_bin[n] = bin_; n += 1
    return t_ein[:n], t_eout[:n], t_dir[:n], t_pin[:n], t_pout[:n], t_risk[:n], t_reason[:n], t_bin[:n]


def run(fine: pd.DataFrame, sig: Signals, costs: Costs = Costs()) -> pd.DataFrame:
    """Renvoie la liste des trades (rendements nets, en fraction du notionnel)."""
    fts = fine.index.as_unit("ns").asi8   # même unité pour tout (les Parquet sont en ms)
    bts = sig.index.as_unit("ns").asi8
    step = pd.Timedelta(TF[sig.tf]).value
    b_start = np.searchsorted(fts, bts, side="left")
    b_end = np.searchsorted(fts, bts + step, side="left")
    nbar = len(bts)
    z = np.zeros(nbar)
    f = lambda a, d: (np.zeros(nbar, d) if a is None else np.nan_to_num(np.asarray(a, dtype=d)))
    closes = fine["close"].to_numpy()
    bar_close = np.where(b_end > b_start, closes[np.maximum(b_end - 1, 0)], np.nan)
    out = _simulate(fine["open"].to_numpy(), fine["high"].to_numpy(), fine["low"].to_numpy(), closes,
                    b_start, b_end, bar_close, f(sig.entry, np.int8), np.asarray(sig.stop_dist, float),
                    f(sig.tp_dist, float), f(sig.exit_long, np.bool_), f(sig.exit_short, np.bool_),
                    f(sig.trail_dist, float), int(sig.max_hold), costs.slip_market, costs.slip_stop)
    ein, eout, d, pin, pout, risk, reason, _ = out
    if len(ein) == 0:
        return pd.DataFrame(columns=["entry_time", "exit_time", "dir", "entry_px", "exit_px", "risk_pct",
                                     "reason", "hours", "gross", "net", "R"])
    t_in = fine.index[ein]; t_out = fine.index[eout] + pd.Timedelta(minutes=1)
    hours = (t_out - t_in).total_seconds() / 3600
    gross = d * (pout / pin - 1)
    net = gross - 2 * costs.fee - costs.funding_8h * hours / 8
    tr = pd.DataFrame({"entry_time": t_in, "exit_time": t_out, "dir": d, "entry_px": pin, "exit_px": pout,
                       "risk_pct": risk, "reason": [EXIT_NAMES[int(r)] for r in reason], "hours": hours,
                       "gross": gross, "net": net})
    tr["R"] = tr["net"] / tr["risk_pct"]
    return tr


# ---------------- Portefeuille et métriques ----------------

def equity_curve(trades: pd.DataFrame, risk: float = 0.005, max_lev: float = 1.0,
                 start: str | None = None, end: str | None = None) -> pd.Series:
    """Capital quotidien (base 1), PnL comptabilisé à la date de sortie, intérêts composés."""
    if trades.empty:
        idx = pd.date_range(start, end, freq="D", tz="UTC") if start else pd.DatetimeIndex([])
        return pd.Series(1.0, index=idx)
    f = np.minimum(risk / trades["risk_pct"].to_numpy(), max_lev)
    pnl = f * trades["net"].to_numpy()
    day = trades["exit_time"].dt.floor("D")
    daily_log = pd.Series(np.log1p(pnl), index=day).groupby(level=0).sum()
    idx = pd.date_range(start or day.min(), end or day.max(), freq="D", tz="UTC")
    daily_log = daily_log.reindex(idx, fill_value=0.0)
    return np.exp(daily_log.cumsum())


def metrics(trades: pd.DataFrame, eq: pd.Series, total_hours: float | None = None,
            risk: float = 0.005, max_lev: float = 1.0) -> dict:
    """Métriques. Taux de réussite, profit factor, gains/pertes moyens : en % du CAPITAL,
    avec le même dimensionnement que la courbe de capital."""
    r = eq.pct_change().fillna(eq.iloc[0] - 1 if len(eq) else 0)
    years = max(len(eq) / 365.0, 1e-9)
    dd = eq / eq.cummax() - 1
    downside = r[r < 0].std() * np.sqrt(365) if (r < 0).any() else np.nan
    monthly = eq.resample("ME").last().pct_change().dropna()
    m = {
        "trades": int(len(trades)),
        "total_return_pct": 100 * (eq.iloc[-1] - 1) if len(eq) else 0.0,
        "cagr_pct": 100 * (eq.iloc[-1] ** (1 / years) - 1) if len(eq) else 0.0,
        "monthly_mean_pct": 100 * monthly.mean() if len(monthly) else 0.0,
        "pct_months_positive": 100 * (monthly > 0).mean() if len(monthly) else 0.0,
        "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
        "sortino": float(r.mean() * 365 / downside) if downside and downside > 0 else 0.0,
        "max_dd_pct": 100 * dd.min() if len(dd) else 0.0,
    }
    if len(trades):
        pnl = np.minimum(risk / trades["risk_pct"].to_numpy(), max_lev) * trades["net"].to_numpy()
        wins = pnl[pnl > 0]; losses = pnl[pnl <= 0]
        m.update({
            "win_rate_pct": 100 * len(wins) / len(trades),
            "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else np.inf,
            "avg_R": float(trades["R"].mean()),
            "avg_win_pct": 100 * wins.mean() if len(wins) else 0.0,
            "avg_loss_pct": 100 * losses.mean() if len(losses) else 0.0,
            "share_capped_pct": 100 * float((risk / trades["risk_pct"] > max_lev).mean()),
            "avg_hours": float(trades["hours"].mean()),
            "trades_per_month": len(trades) / (years * 12),
            "exposure_pct": 100 * trades["hours"].sum() / total_hours if total_hours else np.nan,
            "long_share_pct": 100 * (trades["dir"] == 1).mean(),
        })
    return m
