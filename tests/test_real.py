"""Tests du bot réel avec un faux OKX (aucun appel réseau)."""
import base64, hashlib, hmac
import numpy as np
import pandas as pd
import pytest

from okxbot.live import real
from okxbot.live.okx_private import sign, fmt
from test_live import FakeMarket, FakeTG

INST = {"BTC": {"instId": "BTC-USD_UM_XPERP-310404", "ctVal": 0.0001, "lot": 1, "min": 1, "tick": 0.1},
        "ETH": {"instId": "ETH-USD_UM_XPERP-310404", "ctVal": 0.001, "lot": 1, "min": 1, "tick": 0.01}}


def test_signature_matches_okx_spec():
    ts, path, body = "2020-12-08T09:08:57.715Z", "/api/v5/account/balance?ccy=BTC", ""
    exp = base64.b64encode(hmac.new(b"secret", (ts + "GET" + path + body).encode(), hashlib.sha256).digest()).decode()
    assert sign("secret", ts, "GET", path, body) == exp
    assert fmt(3.0) == "3" and fmt(0.1) == "0.1"


def test_plan_open_reduce_close_reverse():
    px = {"BTC": 60000.0, "ETH": 2000.0}
    # BTC : 0 → +0.06 du capital de 1000 $ = 60 $ = 10 contrats ; ETH : -20 contrats → 0
    p = real.plan_orders({"BTC": 0.06}, {"ETH": {"ct": -20, "avg": 2000, "upl": 0}}, INST, px, 1000, "actif")
    assert p[0] == {"actif": "ETH", "instId": INST["ETH"]["instId"], "side": "buy", "sz": 20, "reduce_only": True}
    assert p[1]["actif"] == "BTC" and p[1]["side"] == "buy" and p[1]["sz"] == 10 and not p[1]["reduce_only"]
    # inversion : long 10 → court 5 = fermeture 10 puis vente 5
    p = real.plan_orders({"BTC": -0.03}, {"BTC": {"ct": 10, "avg": 60000, "upl": 0}}, INST, px, 1000, "actif")
    assert [(o["side"], o["sz"], o["reduce_only"]) for o in p] == [("sell", 10, True), ("sell", 5, False)]
    # petite variation sous le seuil de 2 % : rien
    assert real.plan_orders({"BTC": 0.061}, {"BTC": {"ct": 10, "avg": 1, "upl": 0}}, INST, px, 1000, "actif") == []
    # mode stop : pas d'ouverture ni d'inversion, fermeture seulement
    p = real.plan_orders({"BTC": -0.03, "ETH": 0.5}, {"BTC": {"ct": 10, "avg": 1, "upl": 0}}, INST, px, 1000, "stop")
    assert p == [{"actif": "BTC", "instId": INST["BTC"]["instId"], "side": "sell", "sz": 10, "reduce_only": True}]
    # sous la taille minimale : pas d'ordre
    assert real.plan_orders({"BTC": 0.0004}, {}, INST, px, 1000, "actif") == []


class FakeOkx:
    def __init__(self, pos_mode="net_mode", equity=500.0):
        self.pos_mode, self.equity, self.pos, self.sent, self.algos = pos_mode, equity, {}, [], []
    def config(self): return {"posMode": self.pos_mode}
    def balance(self): return {"totalEq": str(self.equity), "details": [{"ccy": "USD", "eq": str(self.equity), "availEq": str(self.equity)}]}
    def instruments(self, t="FUTURES"):
        return [{"instFamily": f"{b}-USD_UM_XPERP", "instId": v["instId"], "ruleType": "xperp", "state": "live",
                 "ctVal": str(v["ctVal"]), "lotSz": str(v["lot"]), "minSz": str(v["min"]), "tickSz": str(v["tick"])} for b, v in INST.items()]
    def positions(self, t="FUTURES"):
        return [{"instId": i, "pos": str(c), "avgPx": "100", "upl": "0"} for i, c in self.pos.items() if c]
    def pending_algos(self, t="FUTURES"): return list(self.algos)
    def cancel_algos(self, items): self.algos = []
    def set_leverage(self, i, l): pass
    def market_order(self, inst_id, side, sz, cl, reduce_only=False):
        self.sent.append((inst_id, side, sz, cl, reduce_only))
        self.pos[inst_id] = self.pos.get(inst_id, 0) + (sz if side == "buy" else -sz)
        return [{"sCode": "0"}]
    def stop_order(self, inst_id, side, sz, trig):
        self.algos.append({"algoId": str(len(self.algos)), "instId": inst_id, "side": side, "sz": sz, "trig": trig})


def run(okx, live, st=None, tg=None, day="2026-11-24 00:37", trend=-1, force=False):
    st = st or real.new_state()
    tg = tg or FakeTG()
    bot = real.RealBot(st, okx, FakeMarket({"BTC": 60000.0, "ETH": 2000.0}, trend=trend), tg, 1000.0, live)
    res = bot.cycle(now_ms=pd.Timestamp(day, tz="UTC").value // 10**6, force_plan=force)
    return st, tg, res


def test_dry_run_sends_nothing_live_sends_and_is_idempotent():
    okx = FakeOkx(equity=2000.0)
    st, tg, res = run(okx, live=False, force=True)
    assert res["plan"] and okx.sent == [] and okx.algos == [] and tg.sent == []      # à blanc : rien
    okx = FakeOkx(equity=2000.0)
    st, tg, res = run(okx, live=True)
    assert okx.sent and all(s[1] == "sell" for s in okx.sent)                       # tendance baissière → ventes
    assert len(okx.algos) == len([c for c in okx.pos.values() if c])                # un stop par position
    assert all(a["side"] == "buy" for a in okx.algos)                                # stops au-dessus pour les ventes
    assert sum("OUVERTURE" in m for m in tg.sent) == len(okx.algos) and len(tg.sent) == len(okx.algos)
    n = len(okx.sent)
    st, tg2, _ = run(okx, live=True, st=st, force=True)                               # relance le même jour
    assert len(okx.sent) == n and tg2.sent == []                                      # aucun ordre en double, aucun message


def test_capital_cap_and_wrong_pos_mode():
    okx = FakeOkx(equity=100000.0)
    st, tg, res = run(okx, live=False, force=True)
    notional = sum(o["sz"] * INST[o["actif"]]["ctVal"] * {"BTC": 60000, "ETH": 2000}[o["actif"]] for o in res["plan"])
    assert notional <= 3 * 1000 + 1                                                    # plafond 1 000 $ x levier max 3
    with pytest.raises(RuntimeError):
        run(FakeOkx(pos_mode="long_short_mode"), live=True)


def test_stop_hit_notifies_close_and_killswitch():
    okx = FakeOkx(equity=2000.0)
    st, tg, _ = run(okx, live=True)
    held = [i for i, c in okx.pos.items() if c]
    okx.pos[held[0]] = 0                                                               # un stop OKX s'est déclenché
    st, tg2, _ = run(okx, live=True, st=st, day="2026-11-24 04:37")
    assert len(tg2.sent) == 1 and "FERMETURE" in tg2.sent[0] and "stop" in tg2.sent[0]
    tg3 = FakeTG([{"update_id": 1, "message": {"chat": {"id": 42}, "text": "/killswitch"}}])
    st, tg3, _ = run(okx, live=True, st=st, tg=tg3, day="2026-11-24 08:37")
    assert all(c == 0 for c in okx.pos.values()) and okx.algos == [] and st["mode"] == "pause"


def test_okx_retries_transient_outage(monkeypatch):
    """Code 50001 (service indisponible) : on réessaie au lieu de planter le cycle."""
    import okxbot.live.okx_private as op
    monkeypatch.setattr(op.time, "sleep", lambda s: None)

    class R:
        def __init__(self, d): self.d = d
        def json(self): return self.d

    class S:
        def __init__(self): self.n = 0
        def request(self, *a, **k):
            self.n += 1
            return R({"code": "50001", "msg": "Service temporarily unavailable"} if self.n < 3
                     else {"code": "0", "data": [{"acctLv": "2"}]})

    s = S()
    c = op.OkxPrivate("k", "s", "p", session=s)
    assert c.config() == {"acctLv": "2"} and s.n == 3
