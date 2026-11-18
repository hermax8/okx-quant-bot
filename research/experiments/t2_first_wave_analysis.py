"""Analyse complémentaire des premiers backtests : graphiques, coûts, robustesse 2021–2023."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from okxbot.backtest import stats

out = Path(sys.argv[1] if len(sys.argv) > 1 else "reports/t2_first_wave")
summary = json.loads((out / "summary.json").read_text())
wf = pd.read_csv(out / "wf_daily_returns.csv", index_col=0, parse_dates=True)
grid = pd.read_parquet(out / "grid_daily_returns.parquet")
gn = pd.read_csv(out / "gross_vs_net.csv")
NAMES = {"S1_breakout": "S1 Breakout/tendance", "S2_momentum": "S2 Momentum intraday",
         "S3_squeeze": "S3 Squeeze volatilité", "S4_meanrev": "S4 Retour à la moyenne"}
COL = {"S1_breakout": "#2a6fdb", "S2_momentum": "#1a9e5f", "S3_squeeze": "#d98e04", "S4_meanrev": "#c23b3b"}

extra = {}
w = grid[grid.index >= "2021-01-01"]
for s in NAMES:
    cols = [c for c in grid.columns if c.startswith(s + "#")]
    sh_all = np.array([w[c].mean() / w[c].std() * np.sqrt(365) if w[c].std() > 0 else 0 for c in cols])
    sr_daily = np.array([grid[c].mean() / grid[c].std() if grid[c].std() > 0 else 0 for c in cols])
    dsr_family = stats.deflated_sharpe(wf[s].to_numpy(), sr_daily)
    g = gn[(gn.strategy == s) & (gn.costs == "x1")]
    extra[s] = {
        "grid_2021_2023_sharpe_median": float(np.median(sh_all)),
        "grid_2021_2023_pct_positive": float(100 * (sh_all > 0).mean()),
        "grid_2021_2023_sharpe_max": float(sh_all.max()),
        "avg_gross_R": float((g.avg_gross_R * g.trades).sum() / g.trades.sum()),
        "avg_net_R": float((g.avg_net_R * g.trades).sum() / g.trades.sum()),
        "avg_risk_pct": float((g.avg_risk_pct * g.trades).sum() / g.trades.sum()),
        "dsr_family_only": dsr_family,
    }
(out / "analysis.json").write_text(json.dumps(extra, indent=1, default=float))

# Graphique 1 : courbes de capital walk-forward (hors échantillon), coûts normaux
fig, ax = plt.subplots(figsize=(10, 5), dpi=130)
for s in NAMES:
    eq = (1 + wf[s]).cumprod()
    ax.plot(eq.index, (eq - 1) * 100, label=f"{NAMES[s]} ({summary[s]['wf_x1']['sharpe']:+.2f})", color=COL[s], lw=1.6)
ax.axhline(0, color="#888", lw=0.8)
ax.set_title("Walk-forward hors échantillon 2021–2023, BTC + ETH, 0,5 % de risque par trade, coûts réels")
ax.set_ylabel("Rendement cumulé (%)"); ax.legend(title="Stratégie (Sharpe)", frameon=False, fontsize=9)
ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", alpha=0.25)
fig.tight_layout(); fig.savefig(out / "wf_equity.png"); plt.close(fig)

# Graphique 2 : Sharpe hors échantillon selon le niveau de coûts
fig, ax = plt.subplots(figsize=(8, 4), dpi=130)
x = np.arange(len(NAMES)); wd = 0.36
v1 = [summary[s]["wf_x1"]["sharpe"] for s in NAMES]; v2 = [summary[s]["wf_x2"]["sharpe"] for s in NAMES]
ax.bar(x - wd / 2, v1, wd, label="Coûts réels", color="#2a6fdb")
ax.bar(x + wd / 2, v2, wd, label="Coûts doublés", color="#9db8e8")
ax.axhline(1.0, color="#1a9e5f", ls="--", lw=1, label="Seuil de sélection (1,0)")
ax.axhline(0, color="#888", lw=0.8)
ax.set_xticks(x, [NAMES[s] for s in NAMES], fontsize=8)
ax.set_ylabel("Sharpe annualisé"); ax.set_title("Sharpe hors échantillon (walk-forward 2021–2023)")
ax.legend(frameon=False, fontsize=8); ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(); fig.savefig(out / "wf_sharpe_costs.png"); plt.close(fig)
print(json.dumps(extra, indent=1, default=float))
