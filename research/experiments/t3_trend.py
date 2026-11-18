"""T3 tendance multi-jours (D-009). Usage :
  python research/experiments/t3_trend.py --data .../data/raw --universe u5 --out reports/t3_u5
  python research/experiments/t3_trend.py --data .../data/raw --universe u20 --out reports/t3_u20
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from okxbot.backtest.bars import load_fine
from okxbot.strategies.trend_daily import T3Params, backtest, daily_from_fine

U20 = "BTC,ETH,SOL,XRP,DOGE,PEPE,NEAR,UNI,SUI,AAVE,FIL,BNB,ADA,LINK,AVAX,BCH,LTC,ICP,ARB,OP".split(",")
U5 = {"BTC": "1m", "ETH": "1m", "SOL": "5m", "XRP": "5m", "DOGE": "5m"}
END = "2026-11-17"


def load_universe(root, universe):
    out = {}
    if universe == "u5":
        for b, bar in U5.items():
            out[b] = daily_from_fine(load_fine(root, f"{b}-USDT-SWAP", bar, "2020-01-01", END))
    else:
        for b in U20:
            try:
                out[b] = daily_from_fine(load_fine(root, f"{b}-USDT-SWAP", "4H", "2020-01-01", END))
            except Exception as exc:
                print("manquant", b, exc)
    idx = pd.date_range(min(d.index.min() for d in out.values()), max(d.index.max() for d in out.values()), freq="D", tz="UTC")
    full = {}
    for b, d in out.items():
        d = d.reindex(idx)
        first = d["close"].first_valid_index()
        d = d.ffill()
        d.loc[d.index < first] = np.nan
        full[b] = d
    return full


def funding_daily(root, names, idx):
    cols = {}
    for b in names:
        f = Path(root) / "binance" / "funding" / f"{b}USDT.parquet"
        if f.exists():
            x = pd.read_parquet(f)
            s = pd.Series(x["funding_rate"].to_numpy(), index=pd.to_datetime(x["funding_time"], unit="ms", utc=True))
            cols[b] = s.resample("1D").sum().reindex(idx)
    return pd.DataFrame(cols, index=idx)


def stats(r: pd.Series) -> dict:
    r = r[r.index >= r.ne(0).idxmax()] if r.ne(0).any() else r
    eq = (1 + r).cumprod()
    dd = eq / eq.cummax() - 1
    yrs = len(r) / 365
    return {"start": str(r.index[0].date()), "total_return_pct": 100 * (eq.iloc[-1] - 1),
            "cagr_pct": 100 * (eq.iloc[-1] ** (1 / yrs) - 1), "vol_pct": 100 * r.std() * np.sqrt(365),
            "sharpe": float(r.mean() / r.std() * np.sqrt(365)) if r.std() > 0 else 0.0,
            "sortino": float(r.mean() * 365 / (r[r < 0].std() * np.sqrt(365))) if (r < 0).any() else 0.0,
            "max_dd_pct": 100 * dd.min()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True); ap.add_argument("--universe", default="u5"); ap.add_argument("--out", required=True)
    a = ap.parse_args(); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    daily = load_universe(a.data, a.universe)
    idx = next(iter(daily.values())).index
    # pour éviter la journée en cours incomplète
    daily = {b: d[d.index < pd.Timestamp("2026-11-17", tz="UTC")] for b, d in daily.items()}
    fund = funding_daily(a.data, daily.keys(), daily["BTC"].index)
    # actifs absents au début : on retire les lignes NaN dans les calculs via fillna sur close
    for b, d in daily.items():
        daily[b] = d.fillna({"close": np.nan})
    res = {"universe": list(daily), "funding_available": list(fund.columns)}
    runs = {"base": (T3Params(), 1.0), "couts_x2": (T3Params(), 2.0),
            "info_acheteur_seul": (T3Params(long_only=True), 1.0),
            "info_vol20": (T3Params(target_vol=0.20), 1.0), "info_vol40": (T3Params(target_vol=0.40), 1.0)}
    series = {}
    for name, (p, mult) in runs.items():
        filled = daily   # NaN avant cotation : aucun signal, aucun rendement
        bt = backtest(filled, p, cost=0.0008, funding_daily=fund, cost_mult=mult)
        r = bt["net"]
        series[name] = r
        m = stats(r)
        m["by_year_pct"] = {int(y): round(100 * ((1 + x).prod() - 1), 1) for y, x in r.groupby(r.index.year)}
        last = r[r.index >= "2025-11-17"]
        m["last_12m"] = stats(last)
        m["avg_gross_leverage"] = float(bt["weights"].abs().sum(axis=1)[bt["weights"].abs().sum(axis=1) > 0].mean())
        m["max_gross_leverage"] = float(bt["weights"].abs().sum(axis=1).max())
        m["avg_net_exposure"] = float(bt["weights"].sum(axis=1).mean())
        m["annual_turnover_x"] = float(bt["turnover"].sum() / (len(r) / 365))
        m["trading_cost_pct_per_year"] = float(100 * bt["trading_cost"].sum() / (len(r) / 365))
        m["funding_cost_pct_per_year"] = float(100 * bt["funding_cost"].sum() / (len(r) / 365))
        m["long_pnl_share_pct"] = float(100 * (bt["weights"].clip(lower=0) * pd.DataFrame({b: d["close"] for b, d in filled.items()}).pct_change(fill_method=None).shift(-1)).sum().sum()
                                        / (bt["weights"] * pd.DataFrame({b: d["close"] for b, d in filled.items()}).pct_change(fill_method=None).shift(-1)).sum().sum())
        res[name] = m
        if name == "base":
            bt["weights"].to_csv(out / "weights_base.csv")
    pd.DataFrame(series).to_csv(out / "daily_returns.csv")
    b = res["base"]; c = res["couts_x2"]
    full_years = [y for y in range(2020, 2026) if y in b["by_year_pct"]]
    pos_years = sum(b["by_year_pct"][y] > 0 for y in full_years)
    res["criteria"] = {"sharpe_full>=0.8": b["sharpe"] >= 0.8, "sharpe_costx2>=0.5": c["sharpe"] >= 0.5,
                       "years_positive": f"{pos_years}/{len(full_years)}", "years_ok": pos_years >= 4,
                       "last12m_positive": b["last_12m"]["total_return_pct"] > 0, "max_dd<=35": b["max_dd_pct"] >= -35}
    res["criteria"]["PASS"] = all(v for k, v in res["criteria"].items() if isinstance(v, bool))
    bh = pd.DataFrame({k: v["close"] for k, v in daily.items()})
    res["buy_hold_last12m_pct"] = {k: round(100 * (bh[k].iloc[-1] / bh[k][bh.index >= "2025-11-17"].iloc[0] - 1), 1) for k in bh}
    (out / "summary.json").write_text(json.dumps(res, indent=1, default=float))
    for k in runs:
        m = res[k]
        print(f"{k:18s} CAGR {m['cagr_pct']:6.1f}%  Sharpe {m['sharpe']:.2f}  DD {m['max_dd_pct']:6.1f}%  vol {m['vol_pct']:.0f}%  12m {m['last_12m']['total_return_pct']:+.1f}%  levier moy {m['avg_gross_leverage']:.2f} max {m['max_gross_leverage']:.2f}  rotation {m['annual_turnover_x']:.0f}x  frais {m['trading_cost_pct_per_year']:.1f}%/an funding {m['funding_cost_pct_per_year']:+.1f}%/an  part longs {m['long_pnl_share_pct']:.0f}%")
        print("    années", m["by_year_pct"])
    print(res["criteria"]); print("B&H 12m", res["buy_hold_last12m_pct"])


if __name__ == "__main__":
    main()
