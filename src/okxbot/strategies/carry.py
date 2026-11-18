"""C1 — Portage du funding (règles figées dans D-010). Backtest journalier."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class C1Params:
    notional_total: float = 0.75
    slots: int = 5
    enter_min: float = 0.0003      # funding moyen par jour (0,03 %)
    keep_min: float = 0.0
    keep_rank: int = 8
    lookback: int = 14
    side_cost: float = 0.0024      # par entrée OU sortie, par unité de notionnel
    rebalance_move: float = 0.25


def select_weights(funding_daily: pd.DataFrame, p: C1Params) -> pd.DataFrame:
    """Poids (notionnel / capital) décidés chaque lundi 00:00 UTC avec le funding des jours PRÉCÉDENTS."""
    score = funding_daily.rolling(p.lookback, min_periods=p.lookback).mean().shift(1)
    slot = p.notional_total / p.slots
    held: set = set()
    w = pd.DataFrame(0.0, index=funding_daily.index, columns=funding_daily.columns)
    for d in funding_daily.index:
        if d.dayofweek == 0:
            sc = score.loc[d].dropna().sort_values(ascending=False)
            rank = {a: i + 1 for i, a in enumerate(sc.index)}
            held = {a for a in held if a in sc and sc[a] >= p.keep_min and rank[a] <= p.keep_rank}
            for a in sc.index:
                if len(held) >= p.slots:
                    break
                if sc[a] >= p.enter_min:
                    held.add(a)
        for a in held:
            w.at[d, a] = slot
    return w


def backtest(funding_daily: pd.DataFrame, close: pd.DataFrame, p: C1Params, cost_mult: float = 1.0) -> dict:
    w = select_weights(funding_daily, p)
    carry = (w * funding_daily.fillna(0.0)).sum(axis=1)                  # funding encaissé le jour même
    turnover = w.diff().abs().fillna(w.abs()).sum(axis=1)
    trade_cost = turnover * p.side_cost * cost_mult
    # rééquilibrage de marge quand le prix a bougé de plus de 25 % depuis le dernier rééquilibrage
    reb = pd.Series(0.0, index=w.index)
    ref = {}
    c = close.reindex(w.index).ffill()
    for d in w.index:
        for a in w.columns:
            if w.at[d, a] > 0:
                px = c.at[d, a]
                if a not in ref or np.isnan(ref[a]):
                    ref[a] = px
                elif abs(px / ref[a] - 1) > p.rebalance_move:
                    reb[d] += w.at[d, a] * p.side_cost * cost_mult
                    ref[a] = px
            else:
                ref.pop(a, None)
    net = carry - trade_cost - reb
    return {"net": net, "weights": w, "carry": carry, "trade_cost": trade_cost, "rebalance_cost": reb}
