"""Tâche 2 — vague 2 : S1/S2 sur 4 h, entrées limites, 5 actifs, combinaison S1+S2.

Période de développement uniquement (2020–2023). Walk-forward 12 mois / 3 mois, une config choisie
par stratégie pour TOUS les actifs (moins de degrés de liberté).
Usage : python research/experiments/t2_second_wave.py --data .../data/raw --out reports/t2_second_wave
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.backtest import engine, stats
from okxbot.backtest.bars import load_fine, resample
from okxbot.backtest.engine import Costs
from okxbot.strategies.second_wave import STRATEGIES

DEV_START, DEV_END, LAST = "2020-01-01", "2024-01-01", "2023-12-31"
ASSETS = {"BTC-USDT-SWAP": "1m", "ETH-USDT-SWAP": "1m", "SOL-USDT-SWAP": "5m", "XRP-USDT-SWAP": "5m",
          "DOGE-USDT-SWAP": "5m"}
RISK = 0.005
PRIOR_TRIALS = 130   # essais de la vague 1 (65 configs x 2 actifs), comptés dans le Deflated Sharpe


def grid(g):
    keys = list(g)
    for vals in itertools.product(*[g[k] for k in keys]):
        yield dict(zip(keys, vals))


def daily(tr, start=DEV_START, end=LAST):
    return engine.equity_curve(tr, RISK, 1.0, start, end).pct_change().fillna(0.0)


def sharpe(d):
    return float(d.mean() / d.std() * np.sqrt(365)) if d.std() > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t2_second_wave")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    fines = {s: load_fine(a.data, s, bar, DEV_START, DEV_END) for s, bar in ASSETS.items()}
    print(f"données chargées en {time.time()-t0:.0f}s", flush=True)

    trades, daily_port, daily_asset, log = {}, {}, {}, []
    for sname, (fn, g) in STRATEGIES.items():
        for cid, cfg in enumerate(grid(g)):
            port = None
            for s, f in fines.items():
                sig = fn(f, **cfg)
                for ck, c in (("x1", Costs()), ("x2", Costs().scaled(2))):
                    trades[(sname, cid, s, ck)] = engine.run(f, sig, c)
                tr = trades[(sname, cid, s, "x1")]
                d = daily(tr)
                daily_asset[(sname, cid, s)] = d
                port = d if port is None else port + d
                m = engine.metrics(tr, engine.equity_curve(tr, RISK, 1.0, DEV_START, LAST))
                fill = float(tr["maker_entry"].mean()) if len(tr) else np.nan
                log.append({"strategy": sname, "cfg_id": cid, "asset": s, **cfg, **m,
                            "signals": int((sig.entry != 0).sum()), "maker_share": fill,
                            "avg_gross_R": float((tr["gross"] / tr["risk_pct"]).mean()) if len(tr) else np.nan})
            daily_port[(sname, cid)] = port
        print(f"{sname} : {cid+1} configs ({time.time()-t0:.0f}s)", flush=True)
    pd.DataFrame(log).to_csv(out / "trial_log.csv", index=False)
    pd.DataFrame({f"{k[0]}#{k[1]}": v for k, v in daily_port.items()}).to_parquet(out / "grid_daily_returns.parquet")
    n_trials = PRIOR_TRIALS + len(log)
    sr_all = np.array([d.mean() / d.std() if d.std() > 0 else 0 for d in daily_port.values()])

    test_starts = pd.date_range("2021-01-01", "2023-10-01", freq="3MS", tz="UTC")
    summary, wf_daily, wf_trades = {}, {}, {}
    for sname, (fn, g) in STRATEGIES.items():
        cfgs = list(grid(g))
        chosen, oos = [], {"x1": [], "x2": []}
        for ts in test_starts:
            tr0, te1 = ts - pd.DateOffset(months=12), ts + pd.DateOffset(months=3)
            best, best_sc = 0, -np.inf
            for cid in range(len(cfgs)):
                d = daily_port[(sname, cid)]
                d = d[(d.index >= tr0) & (d.index < ts)]
                ntr = sum(((trades[(sname, cid, s, "x1")]["entry_time"] >= tr0) &
                           (trades[(sname, cid, s, "x1")]["entry_time"] < ts)).sum() for s in fines)
                sc = d.mean() / d.std() if d.std() > 0 and ntr >= 10 else -np.inf
                if sc > best_sc:
                    best, best_sc = cid, sc
            chosen.append({"test_start": str(ts.date()), "cfg_id": best, **cfgs[best]})
            for ck in oos:
                for s in fines:
                    t = trades[(sname, best, s, ck)]
                    t = t[(t["entry_time"] >= ts) & (t["entry_time"] < te1)].copy()
                    t["asset"] = s
                    oos[ck].append(t)
        res = {"chosen": chosen, "n_configs": len(cfgs)}
        for ck in oos:
            allt = pd.concat(oos[ck], ignore_index=True)
            per, port = {}, None
            for s in fines:
                t = allt[allt["asset"] == s]
                eq = engine.equity_curve(t, RISK, 1.0, "2021-01-01", LAST)
                per[s] = {"sharpe": sharpe(eq.pct_change().fillna(0)), "total_return_pct": 100 * (eq.iloc[-1] - 1),
                          "trades": len(t)}
                d = eq.pct_change().fillna(eq.iloc[0] - 1)
                port = d if port is None else port + d
            m = engine.metrics(allt, (1 + port).cumprod())
            m["per_asset"] = per
            if ck == "x1":
                wf_daily[sname] = port
                wf_trades[sname] = allt
                m["dsr_all_trials"] = stats.deflated_sharpe(port.to_numpy(), np.r_[sr_all, np.zeros(0)])
                fam = np.array([daily_port[(sname, c)].mean() / daily_port[(sname, c)].std()
                                if daily_port[(sname, c)].std() > 0 else 0 for c in range(len(cfgs))])
                m["dsr_family"] = stats.deflated_sharpe(port.to_numpy(), fam)
                m["by_year"] = {int(y): {"trades": len(x), "sum_R": float(x["R"].sum())}
                                for y, x in allt.groupby(allt["entry_time"].dt.year)}
                m["maker_share"] = float(allt["maker_entry"].mean()) if len(allt) else np.nan
                m["avg_gross_R"] = float((allt["gross"] / allt["risk_pct"]).mean()) if len(allt) else np.nan
                allt.to_csv(out / f"wf_trades_{sname}.csv", index=False)
            res[f"wf_{ck}"] = m
        w = [daily_port[(sname, c)] for c in range(len(cfgs))]
        sh_full = [sharpe(d) for d in w]
        sh_oos = [sharpe(d[d.index >= "2021-01-01"]) for d in w]
        res["grid"] = {"sharpe_median_2020_23": float(np.median(sh_full)), "sharpe_median_2021_23": float(np.median(sh_oos)),
                       "pct_positive_2021_23": float(100 * np.mean(np.array(sh_oos) > 0)),
                       "sharpe_max_2021_23": float(np.max(sh_oos)),
                       "pbo": stats.pbo_cscv(np.column_stack([d.to_numpy() for d in w]), 8)}
        summary[sname] = res
        print(f"{sname} walk-forward fait ({time.time()-t0:.0f}s)", flush=True)

    # Combinaison S1b + S2b (chacune choisie indépendamment en walk-forward), même risque par trade
    combo = wf_daily["S1b_breakout_4h"] + wf_daily["S2b_momentum_4h"]
    ct = pd.concat([wf_trades["S1b_breakout_4h"], wf_trades["S2b_momentum_4h"]], ignore_index=True)
    mc = engine.metrics(ct, (1 + combo).cumprod())
    mc["dsr_all_trials"] = stats.deflated_sharpe(combo.to_numpy(), sr_all)
    mc["corr_S1b_S2b_daily"] = float(wf_daily["S1b_breakout_4h"].corr(wf_daily["S2b_momentum_4h"]))
    summary["COMBO_S1b+S2b"] = {"wf_x1": mc}
    summary["_meta"] = {"n_trials_cumulative": n_trials, "assets": ASSETS, "dev": [DEV_START, LAST]}
    pd.DataFrame({**wf_daily, "COMBO_S1b+S2b": combo}).to_csv(out / "wf_daily_returns.csv")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    print(f"terminé en {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
