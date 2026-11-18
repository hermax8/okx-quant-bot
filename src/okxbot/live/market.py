"""Données de marché en direct (API publique OKX, sans clé)."""
from __future__ import annotations

import pandas as pd

from okxbot.data.okx_public import OkxPublicClient

U20 = "BTC,ETH,SOL,XRP,DOGE,PEPE,NEAR,UNI,SUI,AAVE,FIL,BNB,ADA,LINK,AVAX,BCH,LTC,ICP,ARB,OP".split(",")


def daily_candles(client: OkxPublicClient, inst: str, days: int = 420) -> pd.DataFrame:
    """Bougies journalières UTC clôturées (les plus anciennes en premier)."""
    rows, after = [], None
    while len(rows) < days:
        params = {"instId": inst, "bar": "1Dutc", "limit": "100"}
        if after:
            params["after"] = after
        page = client.get("/api/v5/market/history-candles", params)
        if not page:
            break
        rows += page
        after = page[-1][0]
    df = pd.DataFrame([r[:9] for r in rows], columns=["ts", "open", "high", "low", "close", "vol", "vc", "vq", "confirm"])
    df = df[df["confirm"] == "1"].drop_duplicates("ts")
    df.index = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    df = df.sort_index()[["open", "high", "low", "close", "vq"]].astype(float).rename(columns={"vq": "vol_quote"})
    return df


def xperp_tickers(client: OkxPublicClient) -> dict[str, dict]:
    """{actif: {"instId", "last"}} pour les X-Perps (marché européen)."""
    out = {}
    for t in client.get("/api/v5/market/tickers", {"instType": "FUTURES"}):
        iid = t["instId"]
        if "-USD_UM_XPERP-" in iid:
            base = iid.split("-")[0]
            try:
                out[base] = {"instId": iid, "last": float(t["last"])}
            except (TypeError, ValueError):
                continue
    return out


def funding_since(client: OkxPublicClient, inst_id: str, since_ms: int) -> list[tuple[int, float]]:
    """Paiements de funding réglés après since_ms : [(heure_ms, taux)]."""
    out, after = [], None
    while True:
        params = {"instId": inst_id, "limit": "100"}
        if after:
            params["after"] = after
        page = client.get("/api/v5/public/funding-rate-history", params)
        if not page:
            break
        for r in page:
            t = int(r["fundingTime"])
            if t > since_ms:
                rate = r.get("realizedRate") or r.get("fundingRate")
                out.append((t, float(rate)))
        oldest = min(int(r["fundingTime"]) for r in page)
        if oldest <= since_ms or len(page) < 100:
            break
        after = str(oldest)
    return sorted(out)
