"""Bot RÉEL : stratégie T3 (tendance multi-jours) sur les X-Perps d'OKX Europe.

Sécurités (indépendantes de la stratégie) :
- aucun ordre tant que la variable LIVE_TRADING ne vaut pas exactement « oui » (sinon mode « à blanc ») ;
- capital utilisé plafonné à BOT_CAPITAL_USD, même si le compte contient plus ;
- levier total max 3x, 1x par actif ; levier de marge fixé à 3 ; compte obligatoirement en mode « net » ;
- stops de protection posés chez OKX à chaque rééquilibrage (ils protègent même si le bot tombe) ;
- coupe-circuit à -25 % depuis le plus haut ; commandes Telegram /pause /stop /resume /killswitch ;
- rééquilibrage par différence avec les positions RÉELLES lues chez OKX : relancer un cycle ne double jamais un ordre.
Messages Telegram : uniquement ouverture et fermeture de position, plus les alertes graves (anomalie, coupe-circuit).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import time
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.strategies.trend_daily import T3Params, target_weights

from . import market
from .okx_private import OkxError, OkxPrivate
from .runner import LiveMarket
from .telegram import Telegram

log = logging.getLogger("okxbot.real")
LEVER = 3
STOP_SIGMAS = 4.0          # stop de protection à 4 écarts-types journaliers
MAX_DRAWDOWN = 0.25
THRESHOLD = 0.02           # même seuil de rotation que le backtest (2 % du capital)


def new_state() -> dict:
    return {"version": 1, "mode": "actif", "peak_equity": None, "last_rebalance_day": None, "positions": {},
            "lever_set": [], "orders": [], "history": [], "events": [], "tg_offset": 0, "last_plan": None}


def instrument_map(okx: OkxPrivate) -> dict[str, dict]:
    out = {}
    for x in okx.instruments("FUTURES"):
        iid = x.get("instId", "")
        if "-USD_UM_XPERP-" in iid and x.get("state", "live") == "live":
            b = iid.split("-")[0]
            if b in market.U20:
                out[b] = {"instId": iid, "ctVal": float(x["ctVal"]), "lot": float(x["lotSz"]),
                          "min": float(x["minSz"]), "tick": float(x["tickSz"])}
    return out


def read_positions(okx: OkxPrivate, inst: dict) -> dict[str, dict]:
    by_id = {v["instId"]: b for b, v in inst.items()}
    out = {}
    for p in okx.positions("FUTURES"):
        b = by_id.get(p.get("instId"))
        pos = float(p.get("pos") or 0)
        if b and pos != 0:
            out[b] = {"ct": pos, "avg": float(p.get("avgPx") or 0), "upl": float(p.get("upl") or 0)}
    return out


def round_lot(x: float, lot: float) -> float:
    n = round(x / lot)
    return round(n * lot, 10)


def plan_orders(target_w: dict[str, float], cur: dict[str, dict], inst: dict, prices: dict, capital: float,
                mode: str) -> list[dict]:
    """Ordres nécessaires pour passer des positions réelles aux poids cibles. Réductions d'abord."""
    reduce, increase = [], []
    for b in sorted(set(target_w) | set(cur)):
        if b not in inst or b not in prices:
            continue
        i, px = inst[b], prices[b]
        c_now = cur.get(b, {}).get("ct", 0.0)
        c_tgt = round_lot(target_w.get(b, 0.0) * capital / (px * i["ctVal"]), i["lot"])
        if abs(c_tgt) < i["min"]:
            c_tgt = 0.0
        if mode == "stop":   # réductions seulement
            c_tgt = math.copysign(min(abs(c_tgt), abs(c_now)), c_now) if c_tgt * c_now > 0 else 0.0
        if c_tgt == c_now:
            continue
        same_side = c_tgt * c_now > 0
        if same_side and abs(c_tgt - c_now) * i["ctVal"] * px < THRESHOLD * capital:
            continue
        o = {"actif": b, "instId": i["instId"]}
        if c_now != 0 and not same_side:                       # fermeture (et éventuelle inversion)
            reduce.append({**o, "side": "sell" if c_now > 0 else "buy", "sz": abs(c_now), "reduce_only": True})
            if c_tgt != 0:
                increase.append({**o, "side": "buy" if c_tgt > 0 else "sell", "sz": abs(c_tgt), "reduce_only": False})
        elif same_side and abs(c_tgt) < abs(c_now):            # réduction
            reduce.append({**o, "side": "sell" if c_now > 0 else "buy",
                           "sz": round_lot(abs(c_now) - abs(c_tgt), i["lot"]), "reduce_only": True})
        else:                                                  # ouverture ou renforcement
            increase.append({**o, "side": "buy" if c_tgt > 0 else "sell",
                             "sz": round_lot(abs(c_tgt) - abs(c_now), i["lot"]), "reduce_only": False})
    return reduce + increase


def daily_sigma(d: pd.DataFrame) -> float:
    r = np.log(d["close"]).diff().dropna()
    s = float(r.ewm(span=30).std().iloc[-1]) if len(r) > 30 else 0.05
    return min(max(s, 0.03), 0.25)


def fmt_usd(x: float) -> str:
    return f"{x:,.2f} $".replace(",", " ")


class RealBot:
    def __init__(self, st: dict, okx: OkxPrivate, mkt, tg: Telegram, capital_cap: float, live: bool):
        self.st, self.okx, self.mkt, self.tg, self.cap, self.live = st, okx, mkt, tg, capital_cap, live

    # ---------- commandes Telegram ----------
    def commands(self, equity: float, cur: dict) -> bool:
        kill = False
        for u in self.tg.updates(self.st.get("tg_offset", 0)):
            self.st["tg_offset"] = u["update_id"] + 1
            msg = u.get("message") or {}
            if str(msg.get("chat", {}).get("id", "")) != self.tg.chat_id or not msg.get("text"):
                continue
            cmd = msg["text"].strip().split()[0].split("@")[0].lower()
            self.st["events"].append({"ts": int(time.time() * 1000), "commande": cmd})
            if cmd in ("/start", "/resume"):
                self.st["mode"] = "actif"; self.tg.send("Bot réel : trading repris.")
            elif cmd == "/pause":
                self.st["mode"] = "pause"; self.tg.send("Bot réel : en pause, aucune opération jusqu'à /resume.")
            elif cmd == "/stop":
                self.st["mode"] = "stop"; self.tg.send("Bot réel : plus de nouvelles positions (réductions seulement).")
            elif cmd == "/killswitch":
                kill = True
            elif cmd in ("/status", "/balance", "/positions", "/report", "/performance"):
                lines = [f"Bot réel ({'RÉEL' if self.live else 'À BLANC'}) — mode {self.st['mode']}",
                         f"Capital du compte : {fmt_usd(equity)} (plafond utilisé : {fmt_usd(self.cap)})"]
                for b, p in sorted(cur.items()):
                    lines.append(f"{b} : {'ACHAT' if p['ct'] > 0 else 'VENTE'} {abs(p['ct']):g} contrats, résultat latent {fmt_usd(p['upl'])}")
                self.tg.send("\n".join(lines) if cur else "\n".join(lines + ["Aucune position."]))
            else:
                self.tg.send("Commandes : /status /pause /resume /stop /killswitch")
        return kill

    # ---------- exécution ----------
    def send(self, o: dict, day: str, k: int) -> dict:
        cl = f"t3{day.replace('-', '')}{o['actif'].lower()}{k}"[:32]
        rec = {**o, "clOrdId": cl, "ts": int(time.time() * 1000), "envoye": self.live}
        if self.live:
            if o["instId"] not in self.st["lever_set"] and not o["reduce_only"]:
                try:
                    self.okx.set_leverage(o["instId"], LEVER)
                    self.st["lever_set"].append(o["instId"])
                except OkxError as exc:
                    log.warning("Levier non fixé pour %s : %s", o["instId"], exc)
            res = self.okx.market_order(o["instId"], o["side"], o["sz"], cl, o["reduce_only"])
            rec["reponse"] = res
        self.st["orders"].append(rec)
        return rec

    def protective_stops(self, cur: dict, inst: dict, prices: dict, sig: dict) -> None:
        ours = {v["instId"] for v in inst.values()}
        pend = [a for a in self.okx.pending_algos("FUTURES") if a.get("instId") in ours]
        if self.live:
            self.okx.cancel_algos([{"algoId": a["algoId"], "instId": a["instId"]} for a in pend])
        for b, p in cur.items():
            i, px, s = inst[b], prices[b], sig.get(b, 0.08)
            trig = px * (1 - STOP_SIGMAS * s) if p["ct"] > 0 else px * (1 + STOP_SIGMAS * s)
            trig = round(round(trig / i["tick"]) * i["tick"], 10)
            if self.live:
                self.okx.stop_order(i["instId"], "sell" if p["ct"] > 0 else "buy", abs(p["ct"]), trig)

    def notify_changes(self, before: dict, after: dict, prices: dict, inst: dict, cause: str = "") -> None:
        for b in sorted(set(before) | set(after)):
            p0, p1 = before.get(b), after.get(b)
            if p0 is None and p1 is not None:
                self.tg.send(f"OUVERTURE {'ACHAT' if p1['ct'] > 0 else 'VENTE À DÉCOUVERT'} {b} : {abs(p1['ct']):g} contrats "
                             f"(≈ {fmt_usd(abs(p1['ct']) * inst[b]['ctVal'] * prices[b])}) à {prices[b]:g}")
            elif p0 is not None and (p1 is None or np.sign(p1["ct"]) != np.sign(p0["ct"])):
                pnl = (prices[b] - p0["avg"]) * p0["ct"] * inst[b]["ctVal"]
                self.tg.send(f"FERMETURE {b}{cause} : {'achat' if p0['ct'] > 0 else 'vente'} de {abs(p0['ct']):g} contrats "
                             f"à {prices[b]:g}, résultat ≈ {fmt_usd(pnl)} (frais non inclus)")
                if p1 is not None:
                    self.tg.send(f"OUVERTURE {'ACHAT' if p1['ct'] > 0 else 'VENTE À DÉCOUVERT'} {b} : {abs(p1['ct']):g} contrats à {prices[b]:g}")

    def cycle(self, now_ms: int | None = None, force_plan: bool = False) -> dict:
        now = pd.Timestamp(now_ms or int(time.time() * 1000), unit="ms", tz="UTC")
        today = str(now.date())
        cfg = self.okx.config()
        if cfg.get("posMode") != "net_mode":
            raise RuntimeError(f"Le compte OKX doit être en mode de position « net » (actuel : {cfg.get('posMode')})")
        inst = instrument_map(self.okx)
        tick = self.mkt.tickers()
        prices = {b: v["last"] for b, v in tick.items()}
        bal = self.okx.balance()
        equity = float(bal.get("totalEq") or 0)
        cur = read_positions(self.okx, inst)

        prev = {b: v for b, v in self.st["positions"].items()}
        stopped = {b: v for b, v in prev.items() if b not in cur}
        if stopped and self.live:   # disparue entre deux cycles : stop OKX (ou fermeture manuelle)
            self.notify_changes(stopped, {}, prices, inst, " (stop de protection touché)")

        if self.commands(equity, cur):
            orders = plan_orders({}, cur, inst, prices, min(equity, self.cap), "stop")
            for k, o in enumerate(orders):
                self.send(o, today + "kill", k)
            if self.live:
                self.okx.cancel_algos([{"algoId": a["algoId"], "instId": a["instId"]}
                                       for a in self.okx.pending_algos("FUTURES")])
            self.st["mode"] = "pause"
            after = read_positions(self.okx, inst) if self.live else {}
            self.notify_changes(cur, after, prices, inst, " (kill switch)")
            self.tg.send("KILL SWITCH : positions fermées, bot en pause.")
            cur = after

        peak = max(self.st["peak_equity"] or equity, equity)
        self.st["peak_equity"] = peak
        if peak > 0 and equity / peak - 1 <= -MAX_DRAWDOWN and self.st["mode"] == "actif":
            self.st["mode"] = "stop"
            self.tg.send(f"COUPE-CIRCUIT : baisse de {100*(equity/peak-1):.1f} % depuis le plus haut. "
                         "Plus de nouvelles positions jusqu'à /resume.")

        plan = None
        if self.st["mode"] != "pause" and (self.st["last_rebalance_day"] != today or force_plan):
            daily = {}
            for b in market.U20:
                try:
                    d = self.mkt.daily(b)
                    daily[b] = d[d.index < now.floor("D")]
                except Exception as exc:
                    log.warning("données %s indisponibles : %s", b, exc)
            idx = None
            for d in daily.values():
                idx = d.index if idx is None else idx.union(d.index)
            daily = {b: d.reindex(idx) for b, d in daily.items()}
            w = target_weights(daily, T3Params()).iloc[-1]
            capital = min(equity, self.cap)
            target = {b: float(x) for b, x in w.items() if abs(x) > 1e-6}
            plan = plan_orders(target, cur, inst, prices, capital, self.st["mode"])
            self.st["last_plan"] = {"jour": today, "capital_utilise": capital, "poids": target, "ordres": plan}
            sent = [self.send(o, today, k) for k, o in enumerate(plan)]
            after = read_positions(self.okx, inst) if self.live and sent else cur
            if self.live:
                self.notify_changes(cur, after, prices, inst)
                sig = {b: daily_sigma(daily[b].dropna()) for b in after if b in daily}
                self.protective_stops(after, inst, prices, sig)
            cur = after
            if not force_plan:
                self.st["last_rebalance_day"] = today

        self.st["positions"] = cur
        self.st["history"].append([int(now.value // 10**6), equity])
        self.st["history"] = self.st["history"][-3000:]
        self.st["orders"] = self.st["orders"][-2000:]
        return {"equity": equity, "positions": cur, "plan": plan, "posMode": cfg.get("posMode"),
                "balance_details": [{"ccy": d.get("ccy"), "eq": d.get("eq"), "availEq": d.get("availEq")}
                                    for d in bal.get("details", [])]}


def verification_text(res: dict, st: dict, cap: float, live_var: str, inst_n: int) -> str:
    plan = res["plan"] or []
    lines = ["VÉRIFICATION DU BOT RÉEL (aucun ordre envoyé)",
             f"Connexion OKX : OK — mode de position : {res['posMode']}",
             f"Capital du compte : {fmt_usd(res['equity'])} — plafond du bot : {fmt_usd(cap)}",
             "Soldes : " + ", ".join(f"{d['ccy']} {float(d['eq'] or 0):.2f}" for d in res["balance_details"]) if res["balance_details"] else "Soldes : aucun",
             f"X-Perps du panier trouvés : {inst_n}/20",
             f"Positions actuelles : {len(res['positions'])}",
             f"Ordres que le bot passerait maintenant : {len(plan)}"]
    for o in plan[:25]:
        lines.append(f"  {o['actif']} : {'achat' if o['side']=='buy' else 'vente'} {o['sz']:g} contrats{' (réduction)' if o['reduce_only'] else ''}")
    lines.append(f"Trading réel activé (LIVE_TRADING) : {'OUI' if live_var == 'oui' else 'non'}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="state/live_state.json")
    ap.add_argument("--verification", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    path = Path(a.state)
    st = json.loads(path.read_text()) if path.exists() else new_state()
    tg = Telegram()
    live_var = os.environ.get("LIVE_TRADING", "").strip().lower()
    cap = float(os.environ.get("BOT_CAPITAL_USD") or 0)
    live = live_var == "oui" and not a.verification
    rc = 0
    try:
        if cap <= 0:
            raise RuntimeError("La variable BOT_CAPITAL_USD (capital confié au bot, en dollars) n'est pas définie.")
        okx = OkxPrivate(os.environ.get("OKX_API_KEY", ""), os.environ.get("OKX_API_SECRET", ""),
                         os.environ.get("OKX_API_PASSPHRASE", ""))
        bot = RealBot(st, okx, LiveMarket(), tg, cap, live)
        res = bot.cycle(force_plan=a.verification)
        log.info("Résultat : %s", json.dumps(res, default=str)[:4000])
        if a.verification:
            tg.send(verification_text(res, st, cap, live_var, len(instrument_map(okx))))
    except Exception:
        rc = 1
        err = traceback.format_exc()
        log.error(err)
        tg.send("ANOMALIE du bot réel :\n" + err[-1200:])
    finally:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(st, indent=1, default=float))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
