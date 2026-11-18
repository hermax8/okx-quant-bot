"""Portefeuille multi-stratégies / multi-actifs avec plafond d'exposition notionnelle totale."""
from __future__ import annotations

import heapq

import numpy as np
import pandas as pd


def capped_portfolio(trades: pd.DataFrame, risk: float = 0.005, cap: float = 1.0, min_frac: float = 0.01,
                     start: str | None = None, end: str | None = None, pos_cap: float = 1.0) -> tuple[pd.Series, pd.DataFrame]:
    """Rejoue les trades dans l'ordre chronologique. Chaque position vise `risk` du capital ; la somme des
    notionnels ouverts ne dépasse jamais `cap` x capital (la nouvelle position est réduite, ou ignorée si
    la place restante est < min_frac). Renvoie le capital quotidien (base 1) et les trades avec leur taille."""
    t = trades.sort_values("entry_time").reset_index(drop=True).copy()
    eq = 1.0
    open_heap: list[tuple[pd.Timestamp, int]] = []
    open_frac = {}
    frac = np.zeros(len(t)); pnl = np.zeros(len(t)); taken = np.zeros(len(t), bool)

    def close_until(ts):
        nonlocal eq
        while open_heap and open_heap[0][0] <= ts:
            _, k = heapq.heappop(open_heap)
            f = open_frac.pop(k)
            pnl[k] = f * t.at[k, "net"]
            eq *= 1 + pnl[k]

    for k in range(len(t)):
        close_until(t.at[k, "entry_time"])
        want = min(risk / t.at[k, "risk_pct"], pos_cap)
        room = cap - sum(open_frac.values())
        f = min(want, room)
        if f < min_frac:
            continue
        frac[k] = f; taken[k] = True
        open_frac[k] = f
        heapq.heappush(open_heap, (t.at[k, "exit_time"], k))
    close_until(pd.Timestamp.max.tz_localize("UTC"))
    t["frac"] = frac; t["pnl"] = pnl; t["taken"] = taken
    tk = t[taken]
    day = tk["exit_time"].dt.floor("D")
    lg = pd.Series(np.log1p(tk["pnl"].to_numpy()), index=day).groupby(level=0).sum()
    idx = pd.date_range(start or day.min(), end or day.max(), freq="D", tz="UTC")
    curve = np.exp(lg.reindex(idx, fill_value=0.0).cumsum())
    return curve, t
