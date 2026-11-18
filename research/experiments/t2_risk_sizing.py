"""Quel risque par trade fait le plus grossir le capital à long terme ? (S2b, données dev + validation uniquement)

Méthode : rendements quotidiens du portefeuille S2b à 0,5 % de risque (walk-forward 2021–2023 et validation
2024–oct. 2025), mis à l'échelle pour d'autres niveaux de risque, puis rééchantillonnage par blocs de 30 jours
(5 000 trajectoires d'un an). Aucune donnée du test scellé n'est utilisée.
"""
import json
import numpy as np
import pandas as pd

dev = pd.read_csv("reports/t2_second_wave/wf_daily_returns.csv", index_col=0, parse_dates=True)["S2b_momentum_4h"]
val = pd.read_csv("reports/t2_validation/equity_S2b_momentum_4h_x1.csv", index_col=0, parse_dates=True).iloc[:, 0]
val = val.pct_change().fillna(val.iloc[0] - 1)
rng = np.random.default_rng(7)
BASE = 0.005
levels = [0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02, 0.03, 0.04, 0.06]
out = {}
for name, r in (("validation_2024_2025", val), ("dev_plus_validation", pd.concat([dev, val]))):
    r = r.to_numpy()
    n, B, H, N = len(r), 30, 365, 5000
    starts = rng.integers(0, n - B, size=(N, H // B + 1))
    paths = np.concatenate([r[s:s + B] for s in starts.ravel()]).reshape(N, -1)[:, :H]
    res = {}
    for lv in levels:
        k = lv / BASE
        x = np.clip(k * paths, -0.99, None)
        eq = np.cumprod(1 + x, axis=1)
        dd = (eq / np.maximum.accumulate(eq, axis=1) - 1).min(axis=1)
        g = np.log1p(np.clip(k * r, -0.99, None)).mean() * 365
        res[f"{100*lv:.2f}%"] = {
            "croissance_log_annuelle": float(g),
            "rendement_1an_median_pct": float(100 * (np.median(eq[:, -1]) - 1)),
            "rendement_1an_p10_pct": float(100 * (np.percentile(eq[:, -1], 10) - 1)),
            "dd_max_median_pct": float(100 * np.median(dd)),
            "dd_max_p95_pct": float(100 * np.percentile(dd, 5)),
            "proba_perte_1an_pct": float(100 * (eq[:, -1] < 1).mean()),
            "proba_dd_sup_50pct": float(100 * (dd < -0.5).mean()),
        }
    mu, var = r.mean(), r.var()
    res["kelly_risque_par_trade_pct"] = float(100 * BASE * mu / var)
    out[name] = res
json.dump(out, open("reports/t2_risk_sizing/summary.json", "w"), indent=1)
for name, res in out.items():
    print("==", name, "| Kelly ≈ %.2f %% par trade" % res["kelly_risque_par_trade_pct"])
    for lv, m in res.items():
        if lv.startswith("kelly"): continue
        print(f"{lv:>6} : croissance {m['croissance_log_annuelle']:+.2f}  médiane 1 an {m['rendement_1an_median_pct']:+7.1f}%  p10 {m['rendement_1an_p10_pct']:+7.1f}%  DD méd {m['dd_max_median_pct']:6.1f}%  DD p95 {m['dd_max_p95_pct']:6.1f}%  P(perte) {m['proba_perte_1an_pct']:4.1f}%  P(DD>50%) {m['proba_dd_sup_50pct']:4.1f}%")
