"""Historique du funding Binance USDⓈ-M (data.binance.vision), utilisé comme approximation
du funding OKX avant la fenêtre récente que l'API OKX accepte de renvoyer (~3 mois).

Fichiers mensuels : futures/um/monthly/fundingRate/<SYM>/<SYM>-fundingRate-YYYY-MM.zip
"""
from __future__ import annotations

import io
import logging
import zipfile

import pandas as pd
import requests

from .candles import months_between

log = logging.getLogger(__name__)
BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"


def parse_funding_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw))
    cols = {c.lower(): c for c in df.columns}
    if "calc_time" not in cols:  # anciens fichiers sans en-tête
        df = pd.read_csv(io.BytesIO(raw), header=None, names=["calc_time", "funding_interval_hours", "last_funding_rate"])
        cols = {c: c for c in df.columns}
    interval = (pd.to_numeric(df[cols["funding_interval_hours"]], errors="coerce")
                if "funding_interval_hours" in cols else 8)
    return pd.DataFrame({
        "funding_time": pd.to_numeric(df[cols["calc_time"]], errors="coerce").astype("int64"),
        "funding_rate": pd.to_numeric(df[cols["last_funding_rate"]], errors="coerce"),
        "interval_h": interval,
    })


def download_funding(symbol: str, start: str, end: str, session: requests.Session | None = None) -> tuple[pd.DataFrame, list[str]]:
    s = session or requests.Session()
    frames, missing = [], []
    for m in months_between(start, end):
        url = f"{BASE}/{symbol}/{symbol}-fundingRate-{m.label}.zip"
        r = s.get(url, timeout=30)
        if r.status_code != 200:
            missing.append(m.label)
            continue
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            frames.append(parse_funding_csv(z.read(z.namelist()[0])))
    if not frames:
        return pd.DataFrame(columns=["funding_time", "funding_rate", "interval_h"]), missing
    df = pd.concat(frames).drop_duplicates("funding_time").sort_values("funding_time").reset_index(drop=True)
    return df, missing
