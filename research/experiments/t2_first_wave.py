"""Tâche 2 — premiers backtests des 4 stratégies sur la période de DÉVELOPPEMENT (2020–2023).

Les données 2024+ ne sont pas chargées (validation et test scellé).
Usage : python research/experiments/t2_first_wave.py --data /chemin/vers/data/raw --out reports/t2_first_wave
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
from okxbot.strategies.first_wave import STRATEGIES

DEV_START, DEV_END = "2020-01-01", "2024-01-01"
ASSETS = ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
RISK = 0.005
WF_TRAIN_M, WF_TEST_M = 12, 3


def grid(g: dict):
    keys = list(g)
    for vals in itertools.product(*[g[k] for k in keys]):
        yield dict(zip(keys, vals))


def daily_returns(trades: pd.DataFrame, start=DEV_START, end="2023-12-31") -> pd.Series:
    return engine.equity_curve(trades, RISK, 1.0, start, end).pct_change().fillna(0.0)


def regimes(fine: pd.DataFrame) -> pd.DataFrame:
    """Régime connu à l'entrée (calculé sur les jours précédents) : tendance sur 30 j et volatilité."""
    d = resample(fine, "1d")
    r30 = d["close"].pct_change(30)
    vol = np.log(d["close"]).diff().rolling(30).std()
    vol_med = vol.rolling(365, min_periods=90).median()
    out = pd.DataFrame({
        "trend": np.where(r30 > 0.15, "haussier", np.where(r30 < -0.15, "baissier", "latéral")),
        "vol": np.where(vol > vol_med, "forte vol", "faible vol"),
    }, index=d.index + pd.Timedelta("1D"))   # disponible le lendemain
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="reports/t2_first_wave")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    fines = {s: load_fine(a.data, s, "1m", DEV_START, DEV_END) for s in ASSETS}
    total_hours = (pd.Timestamp(DEV_END) - pd.Timestamp(DEV_START)).total_seconds() / 3600
    regs = {s: regimes(f) for s, f in fines.items()}
    print(f"données chargées en {time.time()-t0:.0f}s", flush=True)

    trial_log = []          # journal de TOUS les essais
    trades_store = {}       # (strat, cfg_id, asset, costs) -> trades
    daily_store = {}        # (strat, cfg_id) -> rendements quotidiens portefeuille BTC+ETH
    for sname, (fn, g) in STRATEGIES.items():
        for cid, cfg in enumerate(grid(g)):
            port = None
            for s in ASSETS:
                sig = fn(fines[s], **cfg)
                for ck, c in (("x1", Costs()), ("x2", Costs().scaled(2))):
                    tr = engine.run(fines[s], sig, c)
                    trades_store[(sname, cid, s, ck)] = tr
                tr = trades_store[(sname, cid, s, "x1")]
                dr = daily_returns(tr)
                port = dr if port is None else port + dr
                m = engine.metrics(tr, engine.equity_curve(tr, RISK, 1.0, DEV_START, "2023-12-31"), total_hours)
                trial_log.append({"strategy": sname, "cfg_id": cid, "asset": s, **cfg, **m})
            daily_store[(sname, cid)] = port
            print(f"{sname} cfg{cid} {cfg} ok ({time.time()-t0:.0f}s)", flush=True)

    log = pd.DataFrame(trial_log)
    log.to_csv(out / "trial_log.csv", index=False)
    pd.DataFrame({f"{k[0]}#{k[1]}": v for k, v in daily_store.items()}).to_parquet(out / "grid_daily_returns.parquet")
    gross = [{"strategy": k[0], "cfg_id": k[1], "asset": k[2], "costs": k[3], "trades": len(t),
              "avg_gross_R": float((t["gross"] / t["risk_pct"]).mean()) if len(t) else np.nan,
              "avg_net_R": float(t["R"].mean()) if len(t) else np.nan,
              "avg_risk_pct": float(t["risk_pct"].mean()) if len(t) else np.nan}
             for k, t in trades_store.items()]
    pd.DataFrame(gross).to_csv(out / "gross_vs_net.csv", index=False)

    # Sharpe quotidien de tous les essais (barre de chance pour le DSR)
    sr_trials = np.array([d.mean() / d.std() if d.std() > 0 else 0 for d in daily_store.values()])

    # --- Walk-forward : 12 mois d'apprentissage, 3 mois de test, décalage de 3 mois ---
    test_starts = pd.date_range("2021-01-01", "2023-10-01", freq="3MS", tz="UTC")
    summary = {}
    wf_daily = {}
    for sname, (fn, g) in STRATEGIES.items():
        cfgs = list(grid(g))
        chosen = []
        oos = {ck: {s: [] for s in ASSETS} for ck in ("x1", "x2")}
        for ts in test_starts:
            tr_start, te_end = ts - pd.DateOffset(months=WF_TRAIN_M), ts + pd.DateOffset(months=WF_TEST_M)
            best, best_score = 0, -np.inf
            for cid in range(len(cfgs)):
                d = daily_store[(sname, cid)]
                d = d[(d.index >= tr_start) & (d.index < ts)]
                n_tr = sum(((trades_store[(sname, cid, s, 'x1')]['entry_time'] >= tr_start) &
                            (trades_store[(sname, cid, s, 'x1')]['entry_time'] < ts)).sum() for s in ASSETS)
                score = d.mean() / d.std() if d.std() > 0 and n_tr >= 10 else -np.inf
                if score > best_score:
                    best, best_score = cid, score
            chosen.append({"test_start": str(ts.date()), "cfg_id": best, **cfgs[best],
                           "train_sharpe_ann": float(best_score * np.sqrt(365)) if np.isfinite(best_score) else None})
            for ck in ("x1", "x2"):
                for s in ASSETS:
                    t = trades_store[(sname, best, s, ck)]
                    oos[ck][s].append(t[(t["entry_time"] >= ts) & (t["entry_time"] < te_end)])
        res = {"chosen": chosen}
        for ck in ("x1", "x2"):
            port_d = None; all_tr = []
            per_asset = {}
            for s in ASSETS:
                t = pd.concat(oos[ck][s], ignore_index=True) if oos[ck][s] else pd.DataFrame()
                t["asset"] = s
                all_tr.append(t)
                eq = engine.equity_curve(t, RISK, 1.0, "2021-01-01", "2023-12-31")
                per_asset[s] = engine.metrics(t, eq, total_hours * 0.75)
                d = eq.pct_change().fillna(eq.iloc[0] - 1)
                port_d = d if port_d is None else port_d + d
            all_t = pd.concat(all_tr, ignore_index=True)
            port_eq = (1 + port_d).cumprod()
            m = engine.metrics(all_t, port_eq, total_hours * 0.75 * len(ASSETS))
            m["per_asset"] = per_asset
            if ck == "x1":
                wf_daily[sname] = port_d
                m["dsr"] = stats.deflated_sharpe(port_d.to_numpy(), sr_trials)
                # années et régimes
                all_t["year"] = all_t["entry_time"].dt.year
                m["by_year"] = {int(y): {"trades": len(x), "sum_R": float(x["R"].sum()), "avg_R": float(x["R"].mean())}
                                for y, x in all_t.groupby("year")}
                rg = []
                for s in ASSETS:
                    t = all_t[all_t["asset"] == s].copy()
                    r = regs[s].reindex(t["entry_time"].dt.floor("D")).reset_index(drop=True)
                    rg.append(pd.concat([t.reset_index(drop=True), r], axis=1))
                rg = pd.concat(rg)
                m["by_trend"] = {k: {"trades": len(x), "avg_R": float(x["R"].mean()), "win_pct": float(100 * (x["net"] > 0).mean())}
                                 for k, x in rg.groupby("trend")}
                m["by_vol"] = {k: {"trades": len(x), "avg_R": float(x["R"].mean()), "win_pct": float(100 * (x["net"] > 0).mean())}
                               for k, x in rg.groupby("vol")}
                m["exit_reasons"] = all_t["reason"].value_counts().to_dict()
                all_t.to_csv(out / f"wf_trades_{sname}.csv", index=False)
            res[f"wf_{ck}"] = m
        # robustesse de la grille sur toute la période de développement (portefeuille)
        sh = [daily_store[(sname, c)].mean() / daily_store[(sname, c)].std() * np.sqrt(365)
              if daily_store[(sname, c)].std() > 0 else 0 for c in range(len(cfgs))]
        perf = np.column_stack([daily_store[(sname, c)].to_numpy() for c in range(len(cfgs))])
        res["grid"] = {"n_configs": len(cfgs), "sharpe_median": float(np.median(sh)), "sharpe_min": float(np.min(sh)),
                       "sharpe_max": float(np.max(sh)), "pct_configs_positive": float(100 * np.mean(np.array(sh) > 0)),
                       "pbo": stats.pbo_cscv(perf, 8)}
        # référence : entrées aléatoires, même fréquence et mêmes sorties que la meilleure config de la grille
        best_c = int(np.argmax(sh)); cfg = cfgs[best_c]
        rnd_sh = []
        rng = np.random.default_rng(42)
        for rep in range(20):
            port = None
            for s in ASSETS:
                sig = fn(fines[s], **cfg)
                e = sig.entry.copy()
                k = int((e != 0).sum())
                newe = np.zeros_like(e)
                pos = rng.choice(len(e), size=k, replace=False)
                newe[pos] = rng.choice([1, -1], size=k)
                sig.entry = newe
                d = daily_returns(engine.run(fines[s], sig, Costs()))
                port = d if port is None else port + d
            rnd_sh.append(port.mean() / port.std() * np.sqrt(365) if port.std() > 0 else 0)
        res["random_benchmark"] = {"best_cfg": cfg, "best_cfg_sharpe": float(sh[best_c]),
                                   "random_sharpe_median": float(np.median(rnd_sh)),
                                   "random_sharpe_p90": float(np.percentile(rnd_sh, 90))}
        summary[sname] = res
        print(f"{sname} walk-forward fait ({time.time()-t0:.0f}s)", flush=True)

    pd.DataFrame(wf_daily).to_csv(out / "wf_daily_returns.csv")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    # référence achat-conservation (BTC+ETH, 50/50) sur la même fenêtre OOS
    bh = {}
    for s in ASSETS:
        d = resample(fines[s], "1d")["close"]
        d = d[(d.index >= "2021-01-01")]
        bh[s] = {"total_return_pct": float(100 * (d.iloc[-1] / d.iloc[0] - 1)),
                 "max_dd_pct": float(100 * (d / d.cummax() - 1).min()),
                 "sharpe": float(d.pct_change().mean() / d.pct_change().std() * np.sqrt(365))}
    (out / "buy_hold.json").write_text(json.dumps(bh, indent=1))
    print(f"terminé en {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
