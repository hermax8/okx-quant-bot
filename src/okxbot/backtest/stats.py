"""Contrôles statistiques anti-surapprentissage : Deflated Sharpe Ratio et PBO (CSCV)."""
from __future__ import annotations

import itertools

import numpy as np
from scipy import stats


def deflated_sharpe(daily_ret: np.ndarray, sr_trials: np.ndarray) -> dict:
    """DSR de Bailey & López de Prado (2014). Sharpe en unités quotidiennes (non annualisées).
    sr_trials : Sharpe quotidien de TOUS les essais réalisés (pour estimer la barre de chance)."""
    r = np.asarray(daily_ret, float)
    t = len(r)
    sr = r.mean() / r.std(ddof=1) if r.std(ddof=1) > 0 else 0.0
    n = max(len(sr_trials), 2)
    v = np.var(sr_trials, ddof=1) if len(sr_trials) > 1 else 0.0
    g = 0.5772156649
    sr0 = np.sqrt(v) * ((1 - g) * stats.norm.ppf(1 - 1 / n) + g * stats.norm.ppf(1 - 1 / (n * np.e)))
    sk = stats.skew(r)
    ku = stats.kurtosis(r, fisher=False)
    denom = np.sqrt(max(1 - sk * sr + (ku - 1) / 4 * sr ** 2, 1e-12))
    dsr = stats.norm.cdf((sr - sr0) * np.sqrt(t - 1) / denom)
    return {"sr_daily": sr, "sr_annual": sr * np.sqrt(365), "sr0_annual": sr0 * np.sqrt(365),
            "n_trials": int(n), "dsr": float(dsr)}


def pbo_cscv(perf: np.ndarray, n_blocks: int = 8) -> float:
    """Probabilité de surapprentissage (Bailey et al. 2014). perf : matrice T x N de rendements quotidiens
    (une colonne par configuration). Renvoie la part des découpages où la meilleure config IS finit
    sous la médiane OOS."""
    t, n = perf.shape
    if n < 2:
        return np.nan
    blocks = np.array_split(np.arange(t), n_blocks)
    logits = []
    for is_idx in itertools.combinations(range(n_blocks), n_blocks // 2):
        oos_idx = [b for b in range(n_blocks) if b not in is_idx]
        is_rows = np.concatenate([blocks[b] for b in is_idx])
        oos_rows = np.concatenate([blocks[b] for b in oos_idx])
        def sharpe(x):
            s = x.std(axis=0)
            return np.where(s > 0, x.mean(axis=0) / np.where(s > 0, s, 1), 0)
        best = np.argmax(sharpe(perf[is_rows]))
        oos_sr = sharpe(perf[oos_rows])
        rank = (oos_sr < oos_sr[best]).sum() + 0.5 * ((oos_sr == oos_sr[best]).sum() - 1)
        w = (rank + 1) / (n + 1)
        logits.append(np.log(w / (1 - w)))
    return float(np.mean(np.array(logits) <= 0))
