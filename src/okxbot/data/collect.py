"""Point d'entrée de la collecte (utilisé par GitHub Actions).

Exemples :
    python -m okxbot.data.collect candles --inst BTC-USDT-SWAP --bar 1m --start 2020-01-01
    python -m okxbot.data.collect funding --inst BTC-USDT-SWAP
    python -m okxbot.data.collect instruments
    python -m okxbot.data.collect quality --inst BTC-USDT-SWAP --bar 1m
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from . import binance_public, candles, quality, reference
from .okx_public import EEA_HOST, GLOBAL_HOST, OkxPublicClient


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="okxbot.data.collect")
    p.add_argument("--root", default="data/raw")
    p.add_argument("--host", default=GLOBAL_HOST)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("candles")
    c.add_argument("--inst", required=True)
    c.add_argument("--bar", default="1m")
    c.add_argument("--start", default="2020-01-01")
    c.add_argument("--end", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))

    cm = sub.add_parser("candles-many")
    cm.add_argument("--insts", required=True, help="liste séparée par des virgules")
    cm.add_argument("--bar", default="4H")
    cm.add_argument("--start", default="2020-01-01")
    cm.add_argument("--end", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))

    f = sub.add_parser("funding")
    f.add_argument("--inst", required=True)

    sub.add_parser("instruments")

    b = sub.add_parser("binance-funding")
    b.add_argument("--symbol", required=True)
    b.add_argument("--start", default="2020-01-01")
    b.add_argument("--end", default=pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d"))

    q = sub.add_parser("quality")
    q.add_argument("--inst", required=True)
    q.add_argument("--bar", default="1m")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    root = Path(a.root)
    client = OkxPublicClient(a.host)

    if a.cmd == "candles":
        out = candles.download(client, a.inst, a.bar, a.start, a.end, root)
    elif a.cmd == "candles-many":
        out = []
        for inst in a.insts.split(","):
            try:
                summ = candles.download(client, inst, a.bar, a.start, a.end, root)
                out.append({**summ, **quality.check(candles.load(root, inst, a.bar), a.bar)})
            except Exception as exc:  # un actif en erreur ne bloque pas les autres
                logging.exception("%s en erreur", inst)
                out.append({"inst_id": inst, "error": repr(exc)})
    elif a.cmd == "funding":
        df = reference.fetch_funding_history(client, a.inst)
        path = root / "okx" / "funding" / f"{a.inst}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():  # on accumule : l'API ne renvoie qu'une fenêtre récente
            df = pd.concat([pd.read_parquet(path), df]).drop_duplicates("funding_time").sort_values("funding_time")
        df.to_parquet(path, index=False)
        out = {"inst_id": a.inst, "rows": len(df),
               "first": pd.to_datetime(df["funding_time"].min(), unit="ms", utc=True).isoformat() if len(df) else None}
    elif a.cmd == "instruments":
        d = root / "okx" / "instruments"
        out = {
            "global": reference.dump_instruments(OkxPublicClient(GLOBAL_HOST), ["SPOT", "SWAP", "FUTURES"], d, "global"),
            "eea": reference.dump_instruments(OkxPublicClient(EEA_HOST), ["SPOT", "SWAP", "FUTURES"], d, "eea"),
        }
    elif a.cmd == "binance-funding":
        df, missing = binance_public.download_funding(a.symbol, a.start, a.end)
        path = root / "binance" / "funding" / f"{a.symbol}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        out = {"symbol": a.symbol, "rows": len(df), "missing_months": missing,
               "first": pd.to_datetime(df["funding_time"].min(), unit="ms", utc=True).isoformat() if len(df) else None}
    else:
        out = {"inst_id": a.inst, "bar": a.bar, **quality.check(candles.load(root, a.inst, a.bar), a.bar)}
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
