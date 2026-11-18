"""Interface Telegram : notifications et commandes. Seul le chat autorisé (TELEGRAM_CHAT_ID) est obéi.

Sans TELEGRAM_BOT_TOKEN, les messages sont seulement écrits dans le journal.
"""
from __future__ import annotations

import logging
import os
import time

import requests

from . import paper

log = logging.getLogger(__name__)
HELP = ("Commandes : /status /balance /positions /performance /history /risk /report "
        "/pause /resume /stop /start /killswitch")


class Telegram:
    def __init__(self, token: str | None = None, chat_id: str | None = None, session=None):
        self.token = token if token is not None else os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = str(chat_id if chat_id is not None else os.environ.get("TELEGRAM_CHAT_ID", ""))
        self.s = session or requests.Session()
        self.sent: list[str] = []

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.chat_id)

    def send(self, text: str) -> None:
        self.sent.append(text)
        log.info("TELEGRAM> %s", text.replace("\n", " | "))
        if not self.enabled:
            return
        for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)]:
            try:
                self.s.post(f"https://api.telegram.org/bot{self.token}/sendMessage",
                            data={"chat_id": self.chat_id, "text": chunk}, timeout=20)
            except requests.RequestException as exc:
                log.warning("Envoi Telegram impossible : %s", exc)

    def updates(self, offset: int) -> list[dict]:
        if not self.enabled:
            return []
        try:
            r = self.s.get(f"https://api.telegram.org/bot{self.token}/getUpdates",
                           params={"offset": offset, "timeout": 0}, timeout=20)
            return r.json().get("result", [])
        except (requests.RequestException, ValueError) as exc:
            log.warning("Lecture Telegram impossible : %s", exc)
            return []


def fmt_eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ")


def status_text(st: dict) -> str:
    eq = paper.total_equity(st)
    pnl = eq - st["initial_capital"]
    return (f"[SIMULATION] Mode : {st['mode']}\nCapital : {fmt_eur(eq)} ({100*pnl/st['initial_capital']:+.2f} %)\n"
            f"Poche tendance T3 : {fmt_eur(paper.t3_equity(st))} — {len(st['t3']['positions'])} positions\n"
            f"Poche portage C1 : {fmt_eur(paper.c1_equity(st))} — {len(st['c1']['positions'])} positions")


def positions_text(st: dict) -> str:
    lines = ["[SIMULATION] Positions"]
    w = paper.t3_weights_now(st)
    for b, p in sorted(st["t3"]["positions"].items(), key=lambda kv: -abs(w.get(kv[0], 0))):
        lines.append(f"T3 {b} : {'ACHAT' if p['qty'] > 0 else 'VENTE'} {abs(w.get(b,0))*100:.0f} % de la poche, prix {p['last_px']:g}")
    for b, p in st["c1"]["positions"].items():
        lines.append(f"C1 {b} : portage {fmt_eur(p['notional'])}")
    return "\n".join(lines) if len(lines) > 1 else "[SIMULATION] Aucune position."


def performance_text(st: dict) -> str:
    h = st["equity_history"]
    eq = paper.total_equity(st)
    def ret_since(ms):
        past = [e for e in h if e[0] <= ms]
        return 100 * (eq / past[-1][1] - 1) if past else None
    now = int(time.time() * 1000)
    parts = []
    for lab, d in (("24 h", 1), ("7 j", 7), ("30 j", 30)):
        r = ret_since(now - d * 86_400_000)
        parts.append(f"{lab} : {r:+.2f} %" if r is not None else f"{lab} : n/d")
    dd = 100 * (eq / st["peak_equity"] - 1)
    return (f"[SIMULATION] Performance\nDepuis le début : {100*(eq/st['initial_capital']-1):+.2f} %\n" + " | ".join(parts) +
            f"\nBaisse depuis le plus haut : {dd:.2f} %\nFrais payés : {fmt_eur(st['t3']['fees']+st['c1']['fees'])} | "
            f"Funding net : {fmt_eur(st['t3']['funding']+st['c1']['funding'])}")


def risk_text(st: dict) -> str:
    return ("[SIMULATION] Risque\nT3 : volatilité visée 30 %/an, 1x max par actif, 3x max au total, rééquilibrage quotidien\n"
            "C1 : 5 portages max, 0,75x du capital de la poche, entrée si funding moyen 14 j ≥ 0,03 %/jour\n"
            f"Coupe-circuit : baisse de {int(paper.MAX_DRAWDOWN*100)} % depuis le plus haut → plus de nouvelles positions")


def history_text(st: dict, n: int = 10) -> str:
    if not st["trades"]:
        return "[SIMULATION] Aucune transaction."
    lines = ["[SIMULATION] Dernières transactions"]
    for t in st["trades"][-n:]:
        d = time.strftime("%d/%m %H:%M", time.gmtime(t["ts"] / 1000))
        if t["poche"] == "T3":
            lines.append(f"{d} T3 {t['actif']} poids {t['poids_avant']:+.2f} → {t['poids_apres']:+.2f} (frais {t['frais']:.2f} €)")
        else:
            lines.append(f"{d} C1 {t['actif']} {t['action']} {t['notionnel']:.0f} € (frais {t['frais']:.2f} €)")
    return "\n".join(lines)


def handle_commands(st: dict, tg: Telegram, close_all) -> None:
    for u in tg.updates(st.get("tg_offset", 0)):
        st["tg_offset"] = u["update_id"] + 1
        msg = u.get("message") or u.get("edited_message") or {}
        chat = str(msg.get("chat", {}).get("id", ""))
        text = (msg.get("text") or "").strip().split()[0].split("@")[0].lower() if msg.get("text") else ""
        if chat != tg.chat_id:
            log.warning("Commande ignorée d'un chat non autorisé : %s", chat)
            continue
        st["events"].append({"ts": int(time.time() * 1000), "commande": text})
        if text in ("/start", "/resume"):
            st["mode"] = "actif"; tg.send("Trading simulé repris.\n" + status_text(st))
        elif text == "/pause":
            st["mode"] = "pause"; tg.send("Trading simulé suspendu : aucune opération jusqu'à /resume.")
        elif text == "/stop":
            st["mode"] = "stop"; tg.send("Plus de nouvelles positions (les positions existantes peuvent être réduites). /resume pour reprendre.")
        elif text == "/killswitch":
            close_all(); st["mode"] = "pause"; tg.send("KILL SWITCH : toutes les positions simulées sont fermées, trading suspendu.")
        elif text in ("/status", "/balance"):
            tg.send(status_text(st))
        elif text == "/positions":
            tg.send(positions_text(st))
        elif text == "/performance":
            tg.send(performance_text(st))
        elif text == "/history":
            tg.send(history_text(st))
        elif text == "/risk":
            tg.send(risk_text(st))
        elif text == "/report":
            tg.send("\n\n".join([status_text(st), performance_text(st), positions_text(st), risk_text(st)]))
        else:
            tg.send(HELP)
