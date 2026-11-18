"""Tests du bot en simulation (aucun accès réseau : marché et Telegram simulés)."""
import numpy as np
import pandas as pd
import pytest

from okxbot.live import paper, runner
from okxbot.live.telegram import Telegram, handle_commands

U = ["BTC", "ETH"]


class FakeMarket:
    def __init__(self, prices, trend=1, funding_rate=0.0004):
        self.p = prices; self.trend = trend; self.rate = funding_rate
    def tickers(self):
        return {b: {"instId": f"{b}-USD_UM_XPERP-310404", "last": px} for b, px in self.p.items()}
    def daily(self, base):
        if base not in self.p:
            raise KeyError(base)
        idx = pd.date_range(end="2026-11-17", periods=400, freq="D", tz="UTC")
        noise = np.random.default_rng(len(base)).normal(0, 0.02, 400)
        noise -= noise.mean()
        c = self.p[base] * np.exp(self.trend * np.linspace(-0.8, 0, 400) + np.cumsum(noise) - np.cumsum(noise)[-1])
        return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "vol_quote": 1.0}, index=idx)
    def funding(self, inst, since):
        t0 = pd.Timestamp("2026-11-01", tz="UTC").value // 10**6
        return [(t0 + k * 8 * 3_600_000, self.rate) for k in range(60) if t0 + k * 8 * 3_600_000 > since]


class FakeTG(Telegram):
    def __init__(self, updates=None):
        super().__init__(token="x", chat_id="42")
        self._u = updates or []
    def send(self, text):
        self.sent.append(text)
    def updates(self, offset):
        u, self._u = self._u, []
        return u


def test_t3_accounting_mark_fees_funding():
    st = paper.new_state(1000)
    paper.t3_rebalance(st, {"BTC": 0.5}, {"BTC": 100.0}, "d1")
    assert st["t3"]["cash"] == pytest.approx(500 - 250 * paper.T3_COST)
    paper.t3_mark(st, {"BTC": 110.0})                      # +10 % sur 250 € de notionnel
    assert st["t3"]["cash"] == pytest.approx(500 - 0.2 + 25)
    paper.apply_funding(st, "BTC", [(1, 0.001)], 110.0)    # un long paie
    assert st["t3"]["funding"] == pytest.approx(-st["t3"]["positions"]["BTC"]["qty"] * 110 * 0.001)


def test_stop_mode_only_reduces():
    st = paper.new_state(1000)
    paper.t3_rebalance(st, {"BTC": 0.5}, {"BTC": 100.0}, "d1")
    st["mode"] = "stop"
    paper.t3_rebalance(st, {"BTC": 0.9, "ETH": 0.3}, {"BTC": 100.0, "ETH": 10.0}, "d2")
    w = paper.t3_weights_now(st)
    assert w["BTC"] == pytest.approx(0.5, rel=1e-3) and "ETH" not in st["t3"]["positions"]
    paper.t3_rebalance(st, {"BTC": -0.5}, {"BTC": 100.0}, "d3")   # pas d'inversion : fermeture
    assert "BTC" not in st["t3"]["positions"]


def test_c1_entry_funding_exit():
    st = paper.new_state(1000)
    paper.c1_select(st, {"BTC": 0.0005, "ETH": 0.0001}, {"BTC": 100, "ETH": 10}, "d1")
    assert set(st["c1"]["positions"]) == {"BTC"}                  # ETH sous le seuil d'entrée
    n = st["c1"]["positions"]["BTC"]["notional"]
    assert n == pytest.approx(0.15 * 500)
    paper.apply_funding(st, "BTC", [(1, 0.0002)], 100)            # la jambe courte reçoit
    assert st["c1"]["funding"] == pytest.approx(n * 0.0002)
    paper.c1_select(st, {"BTC": -0.0001}, {"BTC": 100}, "d8")     # funding négatif : sortie
    assert st["c1"]["positions"] == {}


def test_full_cycle_and_commands():
    st = paper.new_state(1000)
    mkt = FakeMarket({"BTC": 100.0, "ETH": 10.0}, trend=1)
    tg = FakeTG()
    monday = pd.Timestamp("2026-11-16 00:23", tz="UTC").value // 10**6
    runner.cycle(st, mkt, tg, now_ms=monday)
    assert st["t3"]["positions"] and all(p["qty"] > 0 for p in st["t3"]["positions"].values())   # tendance haussière → achats
    assert set(st["c1"]["positions"]) == {"BTC", "ETH"}                                          # funding 0,12 %/jour
    assert any("Nouvelles opérations" in m for m in tg.sent)
    # commandes : un inconnu est ignoré, le chat autorisé peut suspendre
    tg2 = FakeTG([{"update_id": 5, "message": {"chat": {"id": 99}, "text": "/killswitch"}},
                  {"update_id": 6, "message": {"chat": {"id": 42}, "text": "/pause"}}])
    runner.cycle(st, mkt, tg2, now_ms=monday + 86_400_000)
    assert st["mode"] == "pause" and st["t3"]["positions"] and st["tg_offset"] == 7
    tg3 = FakeTG([{"update_id": 7, "message": {"chat": {"id": 42}, "text": "/killswitch"}}])
    runner.cycle(st, mkt, tg3, now_ms=monday + 2 * 86_400_000)
    assert st["t3"]["positions"] == {} and st["c1"]["positions"] == {} and st["mode"] == "pause"


def test_circuit_breaker():
    st = paper.new_state(1000)
    st["t3"]["cash"] = 300.0                       # capital total 800 → -20 % : rien
    assert paper.risk_check(st) is None and st["mode"] == "actif"
    st["t3"]["cash"] = 200.0                       # 700 → -30 %
    assert paper.risk_check(st) is not None and st["mode"] == "stop"
