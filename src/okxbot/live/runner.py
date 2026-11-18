"""Exécution d'un cycle du bot en SIMULATION (lancé toutes les 4 h par GitHub Actions).

Usage : python -m okxbot.live.runner --state state/paper_state.json
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.data.okx_public import OkxPublicClient
from okxbot.strategies.trend_daily import T3Params, target_weights

from . import market, paper
from .telegram import Telegram, history_text, performance_text, status_text

log = logging.getLogger("okxbot.live")


class LiveMarket:
    def __init__(self):
        self.c = OkxPublicClient()

    def tickers(self):
        return market.xperp_tickers(self.c)

    def daily(self, base):
        return market.daily_candles(self.c, f"{base}-USDT-SWAP")

    def funding(self, inst_id, since_ms):
        return market.funding_since(self.c, inst_id, since_ms)


def close_all(st: dict, prices: dict[str, float]) -> list[dict]:
    trades = paper.t3_rebalance(st, {}, prices, st["t3"].get("last_rebalance_day"))
    saved = st["mode"]; st["mode"] = "stop"
    trades += paper.c1_select(st, {}, prices, st["c1"].get("last_selection_day"))
    st["mode"] = saved
    return trades


def c1_scores(mkt, tick: dict, now_ms: int) -> dict[str, float]:
    """Funding moyen par jour des X-Perps sur les 14 derniers jours complets."""
    scores = {}
    start = now_ms - 15 * 86_400_000
    for b in market.U20:
        if b not in tick:
            continue
        pays = mkt.funding(tick[b]["instId"], start)
        if not pays:
            continue
        s = pd.Series([r for _, r in pays], index=pd.to_datetime([t for t, _ in pays], unit="ms", utc=True))
        day = s.resample("1D").sum()
        day = day[day.index < pd.Timestamp(now_ms, unit="ms", tz="UTC").floor("D")].tail(14)
        if len(day) >= 14:
            scores[b] = float(day.mean())
    return scores


def cycle(st: dict, mkt, tg: Telegram, now_ms: int | None = None) -> None:
    now_ms = now_ms or int(time.time() * 1000)
    now = pd.Timestamp(now_ms, unit="ms", tz="UTC")
    today = str(now.date())
    tick = mkt.tickers()
    prices = {b: v["last"] for b, v in tick.items()}

    from .telegram import handle_commands
    handle_commands(st, tg, lambda: st["trades"].extend(close_all(st, prices)))

    paper.t3_mark(st, prices)
    for b in set(st["t3"]["positions"]) | set(st["c1"]["positions"]):
        if b in tick:
            since = st["funding_ts"].get(b, now_ms - 8 * 3_600_000)
            paper.apply_funding(st, b, mkt.funding(tick[b]["instId"], since), prices[b])

    new_trades = []
    if st["mode"] != "pause" and st["t3"]["last_rebalance_day"] != today:
        daily = {}
        for b in market.U20:
            try:
                d = mkt.daily(b)
                daily[b] = d[d.index < now.floor("D")]      # jours complets uniquement
            except Exception as exc:                          # un actif en panne ne bloque pas les autres
                log.warning("données %s indisponibles : %s", b, exc)
        idx = None
        for d in daily.values():
            idx = d.index if idx is None else idx.union(d.index)
        daily = {b: d.reindex(idx) for b, d in daily.items()}
        w = target_weights(daily, T3Params()).iloc[-1]
        target = {b: float(x) for b, x in w.items() if abs(x) > 1e-6 and b in prices}
        new_trades += paper.t3_rebalance(st, target, prices, today)
    if st["mode"] != "pause" and now.dayofweek == 0 and st["c1"]["last_selection_day"] != today:
        new_trades += paper.c1_select(st, c1_scores(mkt, tick, now_ms), prices, today)

    st["trades"] += new_trades
    alert = paper.risk_check(st)
    eq = paper.total_equity(st)
    first_of_day = not st["equity_history"] or pd.Timestamp(st["equity_history"][-1][0], unit="ms", tz="UTC").date() != now.date()
    st["equity_history"].append([now_ms, eq, paper.t3_equity(st), paper.c1_equity(st)])

    if new_trades:
        lines = ["[SIMULATION] Nouvelles opérations"]
        for t in new_trades:
            if t["poche"] == "T3":
                sens = "ACHAT" if t["poids_apres"] > 0 else ("VENTE" if t["poids_apres"] < 0 else "FERMETURE")
                lines.append(f"T3 {t['actif']} : {sens}, poids {t['poids_avant']:+.2f} → {t['poids_apres']:+.2f} à {t['prix']:g}")
            else:
                lines.append(f"C1 {t['actif']} : {t['action']} du portage ({t['notionnel']:.0f} €)")
        tg.send("\n".join(lines))
    if alert:
        tg.send(alert)
    if first_of_day:
        tg.send("Point quotidien\n" + status_text(st) + "\n" + performance_text(st).split("\n", 1)[1])
        if now.dayofweek == 0:
            tg.send("Rapport hebdomadaire\n" + performance_text(st) + "\n\n" + history_text(st, 20))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state/paper_state.json")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(a.state)
    st = json.loads(path.read_text()) if path.exists() else paper.new_state()
    tg = Telegram()
    if not path.exists():
        tg.send("Bot de trading SIMULÉ démarré avec 1 000 € fictifs (500 € tendance T3, 500 € portage C1). "
                "Aucun ordre réel n'est passé. Tape /report pour un point complet.")
    rc = 0
    try:
        cycle(st, LiveMarket(), tg)
    except Exception:
        rc = 1
        err = traceback.format_exc()
        log.error(err)
        tg.send("ANOMALIE TECHNIQUE (simulation) :\n" + err[-1500:])
    finally:
        st["equity_history"] = st["equity_history"][-5000:]
        st["trades"] = st["trades"][-2000:]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(st, indent=1, default=float))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
