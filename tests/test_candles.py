"""Tests du collecteur avec un faux serveur OKX au format réel de /history-candles."""
from pathlib import Path

import pandas as pd

from okxbot.data import candles, quality

MIN = 60_000


class FakeClient:
    """Imite OKX : renvoie au plus `limit` bougies avec ts < after, de la plus récente à la plus ancienne."""

    def __init__(self, first_ms: int, last_ms: int, missing: set[int] = frozenset(), unconfirmed_last=True):
        self.ts = [t for t in range(first_ms, last_ms + 1, MIN) if t not in missing]
        self.last_ms = last_ms
        self.unconfirmed_last = unconfirmed_last
        self.n_requests = 0
        self.calls = []

    def get(self, path, params):
        self.n_requests += 1
        self.calls.append(params)
        after, limit = int(params["after"]), int(params["limit"])
        sel = [t for t in self.ts if t < after][-limit:][::-1]
        return [[str(t), "100", "101", "99", "100.5", "10", "0.1", "1005", "0" if (t == self.last_ms and self.unconfirmed_last) else "1"] for t in sel]


def ms(s):
    return candles.to_ms(pd.Timestamp(s, tz="UTC"))


def test_fetch_range_exact_bounds_and_pagination():
    cl = FakeClient(ms("2020-01-31 20:00"), ms("2020-02-01 04:00"), unconfirmed_last=False)
    df = candles.fetch_range(cl, "X", "1m", ms("2020-01-31 22:00"), ms("2020-02-01 00:00"))
    assert len(df) == 120
    assert df["ts"].min() == ms("2020-01-31 22:00")
    assert df["ts"].max() == ms("2020-01-31 23:59")
    assert df["ts"].is_monotonic_increasing and not df["ts"].duplicated().any()
    assert cl.n_requests >= 2  # pagination effective (100 par page)


def test_unconfirmed_candle_dropped():
    cl = FakeClient(ms("2020-01-01 00:00"), ms("2020-01-01 00:09"))
    df = candles.fetch_range(cl, "X", "1m", ms("2020-01-01"), ms("2020-01-02"))
    assert len(df) == 9 and df["ts"].max() == ms("2020-01-01 00:08")


def test_stops_when_history_ends():
    cl = FakeClient(ms("2020-03-15"), ms("2020-03-15 01:00"), unconfirmed_last=False)
    df = candles.fetch_range(cl, "X", "1m", ms("2020-03-01"), ms("2020-04-01"))
    assert len(df) == 61
    assert cl.n_requests <= 3


def test_download_monthly_files_and_resume(tmp_path: Path):
    cl = FakeClient(ms("2020-01-31 23:00"), ms("2020-02-01 00:59"), unconfirmed_last=False)
    now = pd.Timestamp("2020-03-10", tz="UTC")
    s1 = candles.download(cl, "X", "1m", "2020-01-01", "2020-02-29", tmp_path, now=now)
    assert s1["months"] == 2 and s1["rows"] == 120
    assert (tmp_path / "okx/candles/X/1m/2020-01.parquet").exists()
    n = cl.n_requests
    s2 = candles.download(cl, "X", "1m", "2020-01-01", "2020-02-29", tmp_path, now=now)
    assert s2["skipped"] == 2 and cl.n_requests == n  # rien de retéléchargé
    df = candles.load(tmp_path, "X", "1m")
    assert len(df) == 120 and df.index.is_monotonic_increasing


def test_quality_detects_gaps(tmp_path: Path):
    missing = {ms("2020-01-01 00:10"), ms("2020-01-01 00:11")}
    cl = FakeClient(ms("2020-01-01 00:00"), ms("2020-01-01 00:59"), missing=missing, unconfirmed_last=False)
    df = candles.fetch_range(cl, "X", "1m", ms("2020-01-01"), ms("2020-01-02"))
    q = quality.check(df, "1m")
    assert q["n_gaps"] == 1 and q["missing_bars"] == 2 and q["bad_ohlc"] == 0 and q["duplicates"] == 0


def test_real_okx_sample_parses():
    # Réponse réelle d'OKX (BTC-USDT-SWAP, 1m, 31/01/2020), obtenue le 17/11/2026
    rows = [["1580515140000", "9352.5", "9356.7", "9352.1", "9356", "87575", "8.7575", "81920.5011875", "1"],
            ["1580515080000", "9348.6", "9356.3", "9348.6", "9352.8", "153632", "15.3632", "143670.11704", "1"]]
    df = candles.rows_to_frame(rows)
    assert list(df["ts"]) == [1580515080000, 1580515140000]
    assert df["close"].iloc[-1] == 9356.0
