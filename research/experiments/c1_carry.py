"""C1 portage du funding (D-010) : backtest 2020–2026 (funding Binance) + contrôle sur les X-Perps."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.backtest.bars import load_fine
from okxbot.strategies.carry import C1Params, backtest

R = "/home/claude/okxdata/data/raw"
U20 = "BTC,ETH,SOL,XRP,DOGE,PEPE,NEAR,UNI,SUI,AAVE,FIL,BNB,ADA,LINK,AVAX,BCH,LTC,ICP,ARB,OP".split(",")
out = Path("reports/c1_carry"); out.mkdir(parents=True, exist_ok=True)


def fser(path):
    x = pd.read_parquet(path)
    return pd.Series(x["funding_rate"].to_numpy(), index=pd.to_datetime(x["funding_time"], unit="ms", utc=True))


fund, close, missing = {}, {}, []
for b in U20:
    f = Path(R) / "binance" / "funding" / f"{b}USDT.parquet"
    if not f.exists():
        missing.append(b); continue
    fund[b] = fser(f).resample("1D").sum()
    close[b] = load_fine(R, f"{b}-USDT-SWAP", "4H", "2020-01-01", "2026-11-17")["close"].resample("1D").last()
idx = pd.date_range("2020-01-01", "2026-10-31", freq="D", tz="UTC")
F = pd.DataFrame(fund).reindex(idx)
F = F.where(F != 0)                      # jours sans donnée -> NaN (pas de sélection)
C = pd.DataFrame(close).reindex(idx)


def stats(r):
    eq = (1 + r).cumprod(); dd = eq / eq.cummax() - 1
    return {"total_pct": 100 * (eq.iloc[-1] - 1), "cagr_pct": 100 * (eq.iloc[-1] ** (365 / len(r)) - 1),
            "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0, "max_dd_pct": 100 * dd.min()}


res = {"missing_binance_funding": missing}
for name, mult in (("base", 1.0), ("couts_x2", 2.0)):
    bt = backtest(F, C, C1Params(), mult)
    r = bt["net"]
    m = stats(r[r.index >= "2020-02-01"])
    m["by_year_pct"] = {int(y): round(100 * ((1 + x).prod() - 1), 2) for y, x in r.groupby(r.index.year)}
    m["carry_by_year_pct"] = {int(y): round(100 * x.sum(), 2) for y, x in bt["carry"].groupby(r.index.year)}
    m["costs_by_year_pct"] = {int(y): round(100 * x.sum(), 2) for y, x in (bt["trade_cost"] + bt["rebalance_cost"]).groupby(r.index.year)}
    m["avg_invested_x"] = float(bt["weights"].sum(axis=1).mean())
    m["last_12m"] = stats(r[r.index >= "2025-11-01"])
    m["most_held"] = (bt["weights"] > 0).mean().sort_values(ascending=False).head(8).round(2).to_dict()
    res[name] = m
    if name == "base":
        r.to_csv(out / "daily_returns.csv"); bt["weights"].to_csv(out / "weights.csv")
b = res["base"]
yrs = [2021, 2022, 2023, 2024, 2025]
res["criteria"] = {"all_years_2021_2025_positive": all(b["by_year_pct"][y] > 0 for y in yrs),
                   "sharpe>=1.5": b["sharpe"] >= 1.5, "max_dd<=10": b["max_dd_pct"] >= -10,
                   "last12m_positive": b["last_12m"]["total_pct"] > 0}
res["criteria"]["PASS"] = all(res["criteria"].values())

# contrôle d'information : vrai funding des X-Perps (période disponible) vs Binance sur la même période
chk = {}
for p in sorted(Path(R, "okx", "funding").glob("*XPERP*.parquet")):
    b = p.name.split("-")[0]
    x = fser(p).resample("1D").sum()
    if b in F:
        s, e = x.index.min(), min(x.index.max(), F.index.max())
        chk[b] = {"start": str(s.date()), "xperp_pct_per_year": round(100 * 365 * x[s:e].mean(), 2),
                  "binance_pct_per_year": round(100 * 365 * F[b][s:e].mean(), 2)}
res["xperp_vs_binance_funding"] = chk
(out / "summary.json").write_text(json.dumps(res, indent=1, default=float))
for k in ("base", "couts_x2"):
    m = res[k]
    print(f"{k}: CAGR {m['cagr_pct']:.2f}%  Sharpe {m['sharpe']:.2f}  DD {m['max_dd_pct']:.2f}%  investi moyen {m['avg_invested_x']:.2f}x  12m {m['last_12m']['total_pct']:+.2f}%")
    print("   net par an", m["by_year_pct"]); print("   funding encaissé", m["carry_by_year_pct"]); print("   coûts", m["costs_by_year_pct"])
print("souvent détenus", res["base"]["most_held"]); print(res["criteria"]); print("X-Perps vs Binance", chk, "manquants", missing)
