"""Comptabilité du paper trading : deux poches (T3 tendance, C1 portage), état sérialisable en JSON.

Aucun ordre réel : les exécutions sont simulées au dernier prix des X-Perps, frais et slippage inclus.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

T3_COST = 0.0008      # frais taker 0,05 % + slippage 3 pb
C1_SIDE_COST = 0.0024  # D-010
T3_THRESHOLD = 0.02
MAX_DRAWDOWN = 0.25    # coupe-circuit : au-delà, plus de nouvelles positions + alerte

MODES = ("actif", "stop", "pause")   # stop = pas de nouvelles positions ; pause = aucune opération


def new_state(capital: float = 1000.0) -> dict:
    now = int(time.time() * 1000)
    return {
        "version": 1, "created_ms": now, "mode": "actif", "initial_capital": capital, "peak_equity": capital,
        "t3": {"cash": capital / 2, "positions": {}, "fees": 0.0, "funding": 0.0, "last_rebalance_day": None},
        "c1": {"cash": capital / 2, "positions": {}, "fees": 0.0, "funding": 0.0, "last_selection_day": None},
        "funding_ts": {}, "equity_history": [], "trades": [], "events": [], "tg_offset": 0,
    }


def _sgn(x: float) -> int:
    return (x > 0) - (x < 0)


# ---------------- Poche T3 (positions directionnelles en X-Perps) ----------------

def t3_mark(st: dict, prices: dict[str, float]) -> None:
    for b, pos in st["t3"]["positions"].items():
        if b in prices:
            st["t3"]["cash"] += pos["qty"] * (prices[b] - pos["last_px"])
            pos["last_px"] = prices[b]


def t3_equity(st: dict) -> float:
    return st["t3"]["cash"]          # marquage au marché déjà réalisé dans la trésorerie


def t3_weights_now(st: dict) -> dict[str, float]:
    eq = t3_equity(st)
    return {b: p["qty"] * p["last_px"] / eq for b, p in st["t3"]["positions"].items()} if eq > 0 else {}


def t3_rebalance(st: dict, target: dict[str, float], prices: dict[str, float], day: str) -> list[dict]:
    """Applique les poids cibles (fraction du capital de la poche). En mode stop : réductions seulement."""
    trades = []
    eq = t3_equity(st)
    cur = t3_weights_now(st)
    for b in sorted(set(target) | set(cur)):
        if b not in prices:
            continue
        w_old, w_new = cur.get(b, 0.0), target.get(b, 0.0)
        if st["mode"] == "stop":                     # réductions seulement, jamais d'ouverture ni d'inversion
            w_new = _sgn(w_old) * min(abs(w_new), abs(w_old)) if _sgn(w_new) == _sgn(w_old) else 0.0
        if abs(w_new - w_old) < T3_THRESHOLD and _sgn(w_new) == _sgn(w_old):
            continue
        p = prices[b]
        q_old = st["t3"]["positions"].get(b, {}).get("qty", 0.0)
        q_new = w_new * eq / p
        fee = abs(q_new - q_old) * p * T3_COST
        st["t3"]["cash"] -= fee
        st["t3"]["fees"] += fee
        if abs(q_new) < 1e-12:
            st["t3"]["positions"].pop(b, None)
        else:
            st["t3"]["positions"][b] = {"qty": q_new, "last_px": p}
        trades.append({"ts": int(time.time() * 1000), "poche": "T3", "actif": b, "prix": p,
                       "poids_avant": round(w_old, 4), "poids_apres": round(w_new, 4),
                       "notionnel": round((q_new - q_old) * p, 2), "frais": round(fee, 4)})
    st["t3"]["last_rebalance_day"] = day
    return trades


# ---------------- Poche C1 (portage : spot long + X-Perp court) ----------------

def c1_equity(st: dict) -> float:
    return st["c1"]["cash"]          # jambes compensées : seule la trésorerie (funding - frais) varie


def c1_select(st: dict, scores: dict[str, float], prices: dict[str, float], day: str,
              slots: int = 5, notional_total: float = 0.75, enter_min: float = 0.0003,
              keep_rank: int = 8) -> list[dict]:
    trades = []
    ranked = sorted(scores, key=lambda b: scores[b], reverse=True)
    rank = {b: i + 1 for i, b in enumerate(ranked)}
    held = set(st["c1"]["positions"])
    keep = {b for b in held if b in scores and scores[b] >= 0 and rank[b] <= keep_rank}
    new = set(keep)
    if st["mode"] == "actif":
        for b in ranked:
            if len(new) >= slots:
                break
            if scores[b] >= enter_min and b in prices:
                new.add(b)
    slot = notional_total / slots * c1_equity(st)
    for b in held - new:                                     # sorties
        n = st["c1"]["positions"].pop(b)["notional"]
        fee = n * C1_SIDE_COST
        st["c1"]["cash"] -= fee; st["c1"]["fees"] += fee
        trades.append({"ts": int(time.time() * 1000), "poche": "C1", "actif": b, "action": "sortie",
                       "notionnel": round(n, 2), "frais": round(fee, 4)})
    for b in new - held:                                     # entrées
        fee = slot * C1_SIDE_COST
        st["c1"]["cash"] -= fee; st["c1"]["fees"] += fee
        st["c1"]["positions"][b] = {"notional": slot, "entry_px": prices[b], "score": scores[b]}
        trades.append({"ts": int(time.time() * 1000), "poche": "C1", "actif": b, "action": "entrée",
                       "notionnel": round(slot, 2), "frais": round(fee, 4),
                       "funding_moyen_14j_pct_jour": round(100 * scores[b], 4)})
    st["c1"]["last_selection_day"] = day
    return trades


# ---------------- Funding, capital total, coupe-circuit ----------------

def apply_funding(st: dict, base: str, payments: list[tuple[int, float]], price: float) -> float:
    """Long T3 paie un taux positif ; la jambe courte de C1 le reçoit."""
    total = 0.0
    for t, rate in payments:
        if t <= st["funding_ts"].get(base, 0):
            continue
        if base in st["t3"]["positions"]:
            amt = -st["t3"]["positions"][base]["qty"] * price * rate
            st["t3"]["cash"] += amt; st["t3"]["funding"] += amt; total += amt
        if base in st["c1"]["positions"]:
            amt = st["c1"]["positions"][base]["notional"] * rate
            st["c1"]["cash"] += amt; st["c1"]["funding"] += amt; total += amt
        st["funding_ts"][base] = t
    return total


def total_equity(st: dict) -> float:
    return t3_equity(st) + c1_equity(st)


def risk_check(st: dict) -> str | None:
    eq = total_equity(st)
    st["peak_equity"] = max(st["peak_equity"], eq)
    dd = eq / st["peak_equity"] - 1
    if dd <= -MAX_DRAWDOWN and st["mode"] == "actif":
        st["mode"] = "stop"
        return f"COUPE-CIRCUIT : baisse de {100*dd:.1f} % depuis le plus haut. Plus de nouvelles positions jusqu'à /resume."
    return None
