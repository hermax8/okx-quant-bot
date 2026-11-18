"""TEST SCELLÉ de la v0.2 (D-008) : 1er novembre 2025 → 16 novembre 2026. Exécution UNIQUE."""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.backtest import engine
from okxbot.backtest.bars import load_fine
from okxbot.backtest.engine import Costs
from okxbot.backtest.portfolio import capped_portfolio
from okxbot.strategies.second_wave import s2b_momentum, STRATEGIES

GRID = STRATEGIES["S2b_momentum_4h"][1]
ASSETS = {"BTC-USDT-SWAP": "1m", "ETH-USDT-SWAP": "1m", "SOL-USDT-SWAP": "5m", "XRP-USDT-SWAP": "5m", "DOGE-USDT-SWAP": "5m"}
BINANCE = {"BTC-USDT-SWAP": "BTCUSDT", "ETH-USDT-SWAP": "ETHUSDT", "SOL-USDT-SWAP": "SOLUSDT", "XRP-USDT-SWAP": "XRPUSDT", "DOGE-USDT-SWAP": "DOGEUSDT"}
LOAD_START, LOAD_END = "2024-07-01", "2026-11-17"
TEST_START, TEST_LAST = "2025-11-01", "2026-11-16"
RISK, POS_CAP, CAP = 0.01, 2.0, 3.0
COSTS = Costs(fee=0.0005, fee_maker=0.0002, slip_market=0.0003, slip_stop=0.0008, funding_8h=0.0001)


def funding_series(root, inst):
    b = pd.read_parquet(f"{root}/binance/funding/{BINANCE[inst]}.parquet")
    b = pd.Series(b["funding_rate"].to_numpy(), index=pd.to_datetime(b["funding_time"], unit="ms", utc=True))
    b = b[b.index < "2026-11-01"]
    o = pd.read_parquet(f"{root}/okx/funding/{inst}.parquet")
    o = pd.Series(o["funding_rate"].to_numpy(), index=pd.to_datetime(o["funding_time"], unit="ms", utc=True))
    return pd.concat([b, o[o.index >= "2026-11-01"]]).sort_index()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", default="reports/t2_sealed_test")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fines = {s: load_fine(a.data, s, bar, LOAD_START, LOAD_END) for s, bar in ASSETS.items()}
    funds = {s: funding_series(a.data, s) for s in ASSETS}
    keys = list(GRID); cfgs = [dict(zip(keys, v)) for v in itertools.product(*[GRID[k] for k in keys])]
    tr, port = {}, {}
    for cid, cfg in enumerate(cfgs):
        p = None
        for s, f in fines.items():
            sig = s2b_momentum(f, **cfg)
            tr[(cid, s, "x1")] = engine.run(f, sig, COSTS, funds[s])
            tr[(cid, s, "x2")] = engine.run(f, sig, COSTS.scaled(2), funds[s])
            d = engine.equity_curve(tr[(cid, s, "x1")], 0.005, 1.0, "2024-11-01", TEST_LAST).pct_change().fillna(0)
            p = d if p is None else p + d
        port[cid] = p
    starts = [pd.Timestamp(x, tz="UTC") for x in ("2025-11-01", "2026-01-01", "2026-04-01", "2026-07-01", "2026-10-01")]
    ends = starts[1:] + [pd.Timestamp("2026-11-17", tz="UTC")]
    chosen, sel = [], {"x1": [], "x2": []}
    for ts, te in zip(starts, ends):
        tr0 = ts - pd.DateOffset(months=12)
        best, bsc = 0, -np.inf
        for cid in range(len(cfgs)):
            dd = port[cid][(port[cid].index >= tr0) & (port[cid].index < ts)]
            ntr = sum(((tr[(cid, s, "x1")]["entry_time"] >= tr0) & (tr[(cid, s, "x1")]["entry_time"] < ts)).sum() for s in fines)
            sc = dd.mean() / dd.std() if dd.std() > 0 and ntr >= 10 else -np.inf
            if sc > bsc: best, bsc = cid, sc
        chosen.append({"test_start": str(ts.date()), "cfg_id": best, **cfgs[best]})
        for ck in sel:
            for s in fines:
                t = tr[(best, s, ck)]; t = t[(t["entry_time"] >= ts) & (t["entry_time"] < te)].copy(); t["asset"] = s
                sel[ck].append(t)
    res = {"chosen": chosen}
    for ck in sel:
        allt = pd.concat(sel[ck], ignore_index=True)
        curve, t = capped_portfolio(allt, RISK, CAP, start=TEST_START, end=TEST_LAST, pos_cap=POS_CAP)
        tk = t[t["taken"]]
        pnl = tk["pnl"].to_numpy()
        r = curve.pct_change().fillna(curve.iloc[0] - 1)
        dd = curve / curve.cummax() - 1
        ev = pd.concat([pd.Series(tk["frac"].values, index=tk["entry_time"]), pd.Series(-tk["frac"].values, index=tk["exit_time"])]).sort_index().cumsum()
        mth = curve.resample("ME").last(); mr = mth.pct_change(); mr.iloc[0] = mth.iloc[0] - 1
        by_a = tk.groupby("asset")["pnl"].sum()
        res[ck] = {
            "trades": int(len(tk)), "skipped_by_cap": int((~t["taken"]).sum()),
            "total_return_pct": float(100 * (curve.iloc[-1] - 1)),
            "sharpe": float(r.mean() / r.std() * np.sqrt(365)),
            "sortino": float(r.mean() * 365 / (r[r < 0].std() * np.sqrt(365))),
            "max_dd_pct": float(100 * dd.min()),
            "profit_factor": float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum()),
            "win_rate_pct": float(100 * (pnl > 0).mean()),
            "avg_hours": float(tk["hours"].mean()),
            "max_notional_x": float(ev.max()), "avg_notional_x_when_open": float(ev[ev > 1e-9].mean()),
            "funding_cost_pct_of_pnl": None,
            "monthly_returns_pct": {str(k.date())[:7]: round(100 * v, 2) for k, v in mr.items()},
            "profit_share_by_asset_pct": (100 * by_a / by_a.sum()).round(1).to_dict(),
            "long_share_pct": float(100 * (tk["dir"] == 1).mean()),
        }
        curve.to_csv(out / f"equity_{ck}.csv"); tk.to_csv(out / f"trades_{ck}.csv", index=False)
    bh = {}
    for s, f in fines.items():
        c = f["close"][f.index >= TEST_START].resample("1D").last()
        bh[s] = {"total_return_pct": float(100 * (c.iloc[-1] / c.iloc[0] - 1)), "max_dd_pct": float(100 * (c / c.cummax() - 1).min())}
    res["buy_hold"] = bh
    m = res["x1"]
    passed = m["total_return_pct"] > 0 and m["sharpe"] >= 0.5 and m["profit_factor"] >= 1.1 and m["max_dd_pct"] > -34
    res["verdict"] = ("RÉUSSITE NETTE" if passed and m["sharpe"] >= 1.0 else "RÉUSSITE") if passed else "ÉCHEC"
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=float))
    print(json.dumps({k: v for k, v in res.items() if k != "chosen"}, indent=1, default=float))
    print("configs :", [c["cfg_id"] for c in chosen])


if __name__ == "__main__":
    main()
