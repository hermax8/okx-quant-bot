"""Validation de la version candidate v0.1 (D-007) sur janvier 2024 → octobre 2025. Exécution UNIQUE.

Procédure strictement identique à la vague 2 + plafond d'exposition 1x (pré-enregistré dans D-007).
Les données à partir du 2025-11-01 ne sont pas chargées.
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.backtest import engine, stats
from okxbot.backtest.bars import load_fine
from okxbot.backtest.engine import Costs
from okxbot.backtest.portfolio import capped_portfolio
from okxbot.strategies.second_wave import STRATEGIES as ALL

STRATS = {k: ALL[k] for k in ("S1b_breakout_4h", "S2b_momentum_4h")}
ASSETS = {"BTC-USDT-SWAP": "1m", "ETH-USDT-SWAP": "1m", "SOL-USDT-SWAP": "5m", "XRP-USDT-SWAP": "5m",
          "DOGE-USDT-SWAP": "5m"}
LOAD_START, LOAD_END = "2022-09-01", "2025-11-01"     # rien après le 31/10/2025
VAL_START, VAL_LAST = "2024-01-01", "2025-10-31"
RISK, N_TRIALS = 0.005, 525


def grid(g):
    keys = list(g)
    return [dict(zip(keys, v)) for v in itertools.product(*[g[k] for k in keys])]


def sharpe(d):
    return float(d.mean() / d.std() * np.sqrt(365)) if d.std() > 0 else 0.0


def evaluate(trades, start, last, label, out):
    curve, t = capped_portfolio(trades, RISK, 1.0, start=start, end=last)
    tk = t[t["taken"]].copy()
    d = curve.pct_change().fillna(curve.iloc[0] - 1)
    m = engine.metrics(tk.assign(net=tk["pnl"] / tk["frac"]), curve)  # stats de trades
    pnl = tk["pnl"].to_numpy()
    m["profit_factor"] = float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum()) if (pnl < 0).any() else np.inf
    m["win_rate_pct"] = float(100 * (pnl > 0).mean())
    m["trades_skipped_by_cap"] = int((~t["taken"]).sum())
    m["trades_reduced_by_cap"] = int(((t["frac"] < np.minimum(RISK / t["risk_pct"], 1) - 1e-12) & t["taken"]).sum())
    q = curve.groupby(pd.PeriodIndex(curve.index.tz_localize(None), freq="Q")).last()
    qr = q.pct_change(); qr.iloc[0] = q.iloc[0] - 1
    m["quarters_positive"] = f"{int((qr > 0).sum())}/{len(qr)}"
    m["quarterly_returns_pct"] = {str(k): round(100 * v, 2) for k, v in qr.items()}
    by_a = tk.groupby("asset")["pnl"].sum(); m["profit_share_by_asset_pct"] = (100 * by_a / by_a.sum()).round(1).to_dict()
    by_s = tk.groupby("strategy")["pnl"].sum(); m["profit_share_by_strategy_pct"] = (100 * by_s / by_s.sum()).round(1).to_dict()
    by_y = tk.groupby(tk["entry_time"].dt.year)["pnl"].sum(); m["profit_share_by_year_pct"] = (100 * by_y / by_y.sum()).round(1).to_dict()
    m["per_strategy_sharpe_uncapped"] = {}
    tk.to_csv(out / f"trades_{label}.csv", index=False)
    curve.to_csv(out / f"equity_{label}.csv")
    return m, d


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--out", default="reports/t2_validation")
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    fines = {s: load_fine(a.data, s, bar, LOAD_START, LOAD_END) for s, bar in ASSETS.items()}
    assert max(f.index.max() for f in fines.values()) < pd.Timestamp(LOAD_END, tz="UTC")
    tests = pd.date_range(VAL_START, "2025-10-01", freq="3MS", tz="UTC")
    res, chosen_all, val = {}, {}, {"x1": [], "x2": []}
    for sname, (fn, g) in STRATS.items():
        cfgs = grid(g); tr = {}; port = {}
        for cid, cfg in enumerate(cfgs):
            p = None
            for s, f in fines.items():
                sig = fn(f, **cfg)
                for ck, c in (("x1", Costs()), ("x2", Costs().scaled(2))):
                    tr[(cid, s, ck)] = engine.run(f, sig, c)
                d = engine.equity_curve(tr[(cid, s, "x1")], RISK, 1.0, "2023-01-01", VAL_LAST).pct_change().fillna(0)
                p = d if p is None else p + d
            port[cid] = p
        chosen = []
        for ts in tests:
            tr0 = ts - pd.DateOffset(months=12); te1 = min(ts + pd.DateOffset(months=3), pd.Timestamp(LOAD_END, tz="UTC"))
            best, bsc = 0, -np.inf
            for cid in range(len(cfgs)):
                dd = port[cid][(port[cid].index >= tr0) & (port[cid].index < ts)]
                ntr = sum(((tr[(cid, s, "x1")]["entry_time"] >= tr0) & (tr[(cid, s, "x1")]["entry_time"] < ts)).sum() for s in fines)
                sc = dd.mean() / dd.std() if dd.std() > 0 and ntr >= 10 else -np.inf
                if sc > bsc: best, bsc = cid, sc
            chosen.append({"test_start": str(ts.date()), "cfg_id": best, **cfgs[best]})
            for ck in val:
                for s in fines:
                    t = tr[(best, s, ck)]
                    t = t[(t["entry_time"] >= ts) & (t["entry_time"] < te1)].copy()
                    t["asset"] = s; t["strategy"] = sname
                    val[ck].append(t)
        chosen_all[sname] = chosen
    sr_trials = []
    for f in ("reports/t2_first_wave/grid_daily_returns.parquet", "reports/t2_second_wave/grid_daily_returns.parquet"):
        gdf = pd.read_parquet(f); sr_trials += [gdf[c].mean() / gdf[c].std() for c in gdf.columns if gdf[c].std() > 0]
    for ck in val:
        allt = pd.concat(val[ck], ignore_index=True)
        m, d = evaluate(allt, VAL_START, VAL_LAST, f"combo_{ck}", out)
        if ck == "x1":
            m["dsr"] = stats.deflated_sharpe(d.to_numpy(), np.array(sr_trials), N_TRIALS)
            for sname in STRATS:
                ms, _ = evaluate(allt[allt["strategy"] == sname], VAL_START, VAL_LAST, f"{sname}_{ck}", out)
                m["per_strategy_sharpe_uncapped"][sname] = {"sharpe": ms["sharpe"], "total_return_pct": ms["total_return_pct"],
                                                            "max_dd_pct": ms["max_dd_pct"], "trades": ms["trades"]}
        res[f"validation_{ck}"] = m
    # référence : même combinaison plafonnée sur la période de développement (walk-forward vague 2)
    dev = pd.concat([pd.read_csv(f"reports/t2_second_wave/wf_trades_{s}.csv", parse_dates=["entry_time", "exit_time"]).assign(strategy=s)
                     for s in STRATS], ignore_index=True)
    res["dev_2021_2023_capped"], _ = evaluate(dev, "2021-01-01", "2023-12-31", "dev_combo", out)
    res["chosen"] = chosen_all
    bh = {}
    for s, f in fines.items():
        c = f["close"][(f.index >= VAL_START)]
        daily = c.resample("1D").last()
        bh[s] = {"total_return_pct": float(100 * (c.iloc[-1] / c.iloc[0] - 1)), "max_dd_pct": float(100 * (daily / daily.cummax() - 1).min())}
    res["buy_hold_2024_2025_10"] = bh
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=float))
    print("ok")


if __name__ == "__main__":
    main()
