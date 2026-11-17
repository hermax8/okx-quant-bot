"""Données de référence OKX : historique du funding et liste des instruments."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd

from .okx_public import OkxApiError, OkxPublicClient

log = logging.getLogger(__name__)


def fetch_funding_history(client: OkxPublicClient, inst_id: str) -> pd.DataFrame:
    """Tout l'historique de funding que l'API publique accepte de renvoyer (profondeur limitée par OKX)."""
    rows: list[dict] = []
    after: str | None = None
    while True:
        params = {"instId": inst_id, "limit": "100"}
        if after:
            params["after"] = after
        page = client.get("/api/v5/public/funding-rate-history", params)
        if not page:
            break
        rows.extend(page)
        oldest = min(int(r["fundingTime"]) for r in page)
        if after is not None and oldest >= int(after):
            break
        after = str(oldest)
    if not rows:
        return pd.DataFrame(columns=["funding_time", "funding_rate", "realized_rate"])
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "funding_time": df["fundingTime"].astype("int64"),
        "funding_rate": pd.to_numeric(df["fundingRate"], errors="coerce"),
        "realized_rate": pd.to_numeric(df.get("realizedRate"), errors="coerce"),
    })
    return out.drop_duplicates("funding_time").sort_values("funding_time").reset_index(drop=True)


def dump_instruments(client: OkxPublicClient, inst_types: list[str], out_dir: Path, tag: str) -> dict:
    """Enregistre les spécifications d'instruments (tailles minimales, pas de prix, valeur du contrat)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for t in inst_types:
        try:
            data = client.get("/api/v5/public/instruments", {"instType": t})
        except OkxApiError as exc:
            log.warning("%s %s : %s", tag, t, exc)
            counts[t] = f"erreur {exc.code}"
            continue
        (out_dir / f"{tag}_{t}.json").write_text(json.dumps(data, indent=1))
        counts[t] = len(data)
    return counts
