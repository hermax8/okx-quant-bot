"""Téléchargement des bougies historiques OKX, stockées en Parquet par mois.

Arborescence : <root>/okx/candles/<instId>/<bar>/<YYYY-MM>.parquet
Un mois terminé et déjà présent n'est jamais retéléchargé (reprise possible).
Les bougies non clôturées (confirm == "0") sont écartées.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .okx_public import OkxPublicClient

log = logging.getLogger(__name__)

HISTORY_PATH = "/api/v5/market/history-candles"
PAGE_LIMIT = 100
COLUMNS = ["ts", "open", "high", "low", "close", "vol", "vol_ccy", "vol_quote", "confirm"]
BAR_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000,
          "1H": 3_600_000, "2H": 7_200_000, "4H": 14_400_000}


@dataclass(frozen=True)
class Month:
    year: int
    month: int

    @property
    def start(self) -> pd.Timestamp:
        return pd.Timestamp(year=self.year, month=self.month, day=1, tz="UTC")

    @property
    def end(self) -> pd.Timestamp:  # exclusif
        return self.start + pd.offsets.MonthBegin(1)

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"


def months_between(start: str, end: str) -> list[Month]:
    s = pd.Timestamp(start).tz_localize(None).to_period("M")
    e = pd.Timestamp(end).tz_localize(None).to_period("M")
    return [Month(p.year, p.month) for p in pd.period_range(s, e, freq="M")]


def to_ms(ts: pd.Timestamp) -> int:
    return int(ts.timestamp() * 1000)


def rows_to_frame(rows: list[list[str]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=COLUMNS[:-1]).astype({"ts": "int64"})
    df = pd.DataFrame([r[: len(COLUMNS)] for r in rows], columns=COLUMNS)
    df = df[df["confirm"] == "1"].drop(columns="confirm")
    df["ts"] = df["ts"].astype("int64")
    for c in COLUMNS[1:-1]:
        df[c] = df[c].astype("float64")
    return df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)


def fetch_range(client: OkxPublicClient, inst_id: str, bar: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Toutes les bougies avec start_ms <= ts < end_ms, en remontant le temps par pages."""
    rows: list[list[str]] = []
    after = end_ms
    while True:
        page = client.get(HISTORY_PATH, {"instId": inst_id, "bar": bar, "after": str(after), "limit": str(PAGE_LIMIT)})
        if not page:
            break
        rows.extend(r for r in page if start_ms <= int(r[0]) < end_ms)
        oldest = min(int(r[0]) for r in page)
        if oldest <= start_ms or oldest >= after:
            break
        after = oldest
    return rows_to_frame(rows)


def month_path(root: Path, inst_id: str, bar: str, m: Month) -> Path:
    return root / "okx" / "candles" / inst_id / bar / f"{m.label}.parquet"


def download(client: OkxPublicClient, inst_id: str, bar: str, start: str, end: str, root: Path,
             now: pd.Timestamp | None = None) -> dict:
    now = now or pd.Timestamp.now(tz="UTC")
    summary = {"inst_id": inst_id, "bar": bar, "months": 0, "skipped": 0, "rows": 0, "empty_months": []}
    for m in months_between(start, end):
        if m.start > now:
            break
        path = month_path(root, inst_id, bar, m)
        complete = m.end <= now
        if path.exists() and complete:
            summary["skipped"] += 1
            continue
        df = fetch_range(client, inst_id, bar, to_ms(m.start), to_ms(min(m.end, now)))
        if df.empty:
            summary["empty_months"].append(m.label)
            log.info("%s %s %s : aucune donnée", inst_id, bar, m.label)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False, compression="zstd")
        summary["months"] += 1
        summary["rows"] += len(df)
        log.info("%s %s %s : %d bougies", inst_id, bar, m.label, len(df))
    summary["requests"] = client.n_requests
    return summary


def load(root: Path, inst_id: str, bar: str) -> pd.DataFrame:
    files = sorted((root / "okx" / "candles" / inst_id / bar).glob("*.parquet"))
    if not files:
        return pd.DataFrame()
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    df = df.drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    df.index = pd.to_datetime(df["ts"], unit="ms", utc=True)
    return df
