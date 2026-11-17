"""Contrôles qualité des bougies : trous, doublons, incohérences OHLC, valeurs aberrantes."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .candles import BAR_MS


def check(df: pd.DataFrame, bar: str) -> dict:
    if df.empty:
        return {"rows": 0}
    step = BAR_MS[bar]
    ts = df["ts"].to_numpy()
    diffs = np.diff(ts)
    gaps = diffs[diffs > step]
    expected = (ts[-1] - ts[0]) // step + 1
    bad_ohlc = ((df["high"] < df[["open", "close"]].max(axis=1)) |
                (df["low"] > df[["open", "close"]].min(axis=1)) |
                (df["low"] <= 0)).sum()
    ret = np.log(df["close"]).diff().abs()
    return {
        "rows": int(len(df)),
        "first": pd.to_datetime(ts[0], unit="ms", utc=True).isoformat(),
        "last": pd.to_datetime(ts[-1], unit="ms", utc=True).isoformat(),
        "coverage_pct": round(100 * len(df) / expected, 3),
        "duplicates": int(df["ts"].duplicated().sum()),
        "n_gaps": int(len(gaps)),
        "missing_bars": int((gaps // step - 1).sum()),
        "largest_gap_min": float(gaps.max() / 60_000) if len(gaps) else 0.0,
        "bad_ohlc": int(bad_ohlc),
        "zero_volume_bars": int((df["vol"] == 0).sum()),
        "max_abs_logret": float(ret.max()),
        "n_logret_over_10pct": int((ret > 0.10).sum()),
    }
